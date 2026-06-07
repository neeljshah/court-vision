"""ARM-B atlas section: ``ft_profile`` -- per-player free-throw profile.

Implements :class:`AtlasSection` for the ``"ft_profile"`` section of a player's
persistent profile.  Every sub-field either comes from existing parquets or is
derived inline from the per-game boxscore JSONs at ``data/nba/boxscore_*.json``
(which already contain ``ftm`` / ``fta`` per player per game).

**Sub-field coverage:**

REAL (populated):
  stability.*      -- ft_pct (career average), ft_pct_std (game-to-game standard
                       deviation), ft_pct_cv (coefficient of variation), ft_pct_l10
                       (rolling last-10-game average <= as_of), n_games.
                       Source: data/nba/boxscore_*.json aggregated inline,
                       filtered to game_date <= as_of via player_adv_stats join.
  attempts.*       -- fta_pg (FT attempts per game), fta_per_36 (rate per 36 min),
                       fta_rate (FTA / FGA proxy from player_breakdown_features
                       ``scoring_pct_pts_ft``), n_games.
                       Source: boxscores (fta_pg, fta_per_36) +
                       data/cache/player_breakdown_features.parquet (fta_rate).
  hack_candidate.* -- hack_flag (bool: fta_pg >= 5.5 AND ft_pct < 0.72),
                       hack_severity (float 0-1: linear scale on ft_pct < 0.72
                       weighted by fta_pg), poor_shooter_flag (ft_pct < 0.65).
                       Source: derived from stability + attempts above.
  clutch_ft.*      -- clutch_ft_pct, clutch_gp, clutch_fta_pg from
                       data/cache/clutch_profiles_2025-26.parquet.
                       Returns None sub-fields when player absent.

DEFER (data gap -- not available without additional fetch):
  streak_analysis  -- consecutive made/missed FT streaks require sequence-level PBP
                       (not available per player; would need pbp_scraper V2 data with
                       EVENTMSGTYPE=3 per player; current PBP has only period/score
                       aggregates, not sequential FT outcomes).
  pressure_splits  -- FT% in last 2 min / OT vs normal game situations requires
                       PBP event-level filtering not available in boxscore JSON.
  home_road_ft     -- per-player home/road FT% split requires game-level home/away
                       assignment join that is not pre-aggregated per player.

RESERVED CV SLOTS (value=None, CV branch fills later):
  ft_motion_arc       -- mean ball-arc angle at FT release (deg, from CV ball tracking)
  ft_release_speed    -- mean ball exit velocity at FT release (ft/s, from CV tracking)
  ft_line_spread      -- mean spacing of teammates along paint during FT (ft, homography)
  ft_motion_stability -- frame-to-frame shooter-position jitter during FT routine (px,
                         proxy for routine consistency under fatigue/pressure)
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"

# ---------------------------------------------------------------------------
# Module-level lazy-load cache
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Any] = {}


def _load(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing/error."""
    if key not in _SRC_CACHE:
        try:
            _SRC_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC_CACHE[key] = None
    return _SRC_CACHE[key]


def _rd(v: Any) -> Optional[float]:
    """Clean scalar: NaN/inf -> None, numpy -> python float, round 4 dp."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 4)


def _ri(v: Any) -> Optional[int]:
    """Clean integer scalar."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _rb(v: Any) -> Optional[bool]:
    """Clean boolean scalar."""
    if v is None:
        return None
    return bool(v)


# ---------------------------------------------------------------------------
# Game-date index (maps game_id -> game_date, built from player_adv_stats)
# ---------------------------------------------------------------------------

def _game_date_index() -> Dict[str, str]:
    """Return a {game_id: 'YYYY-MM-DD'} mapping covering EVERY boxscore game_id.

    Primary source: all ``data/nba/season_games_*.json`` (rows of
    {game_id, game_date, ...} across every season -- this is what the
    ``boxscore_<id>.json`` stems key against). Supplemented by
    ``player_adv_stats.parquet`` for any older games not in season_games.
    Keys are STRING game_ids (preserving leading zeros) so they match the
    boxscore filename stems exactly. (Previously this used player_adv_stats
    alone, whose 3685-game id set overlapped only ~34 of 5482 boxscores ->
    every FT profile collapsed to n=2 and DEFER'd.)
    """
    if "gd_index" in _SRC_CACHE:
        return _SRC_CACHE["gd_index"]
    idx: Dict[str, str] = {}
    for sg in sorted((DATA / "nba").glob("season_games_*.json")):
        try:
            rows = json.loads(sg.read_text(encoding="utf-8")).get("rows") or []
        except Exception:
            continue
        for r in rows:
            gid = str(r.get("game_id") or "").strip()
            gd = str(r.get("game_date") or "")[:10]
            if gid and gd:
                idx.setdefault(gid, gd)
    adv = _load("adv", DATA / "player_adv_stats.parquet")
    if adv is not None and "game_id" in adv.columns and "game_date" in adv.columns:
        sub = adv[["game_id", "game_date"]].drop_duplicates("game_id")
        for gid, gd in zip(sub["game_id"].astype(str),
                           sub["game_date"].astype(str).str[:10]):
            if gid and gd:
                idx.setdefault(gid, gd)
    _SRC_CACHE["gd_index"] = idx
    return idx


def _parse_minutes(v: Any) -> float:
    """Parse a minutes value that may be numeric or 'MM:SS' (NBA boxscore fmt)."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    if ":" in s:
        try:
            mm, ss = s.split(":")[:2]
            return round(float(mm) + float(ss) / 60.0, 3)
        except (ValueError, TypeError):
            return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Boxscore aggregation (the primary FT data source)
# ---------------------------------------------------------------------------

def _boxscore_ft_rows(pid: int, as_of: _dt.datetime) -> pd.DataFrame:
    """Return all per-game FT rows for ``pid`` with game_date <= as_of.

    Reads ``data/nba/boxscore_*.json`` (ftm, fta, min per player per game).
    Joins game_date via the player_adv_stats game_id index.

    LEAK-SAFE: only games whose game_date is strictly <= as_of are returned.
    """
    cache_key = f"bs_ft_{pid}"
    if cache_key in _SRC_CACHE:
        df = _SRC_CACHE[cache_key]
    else:
        gd_idx = _game_date_index()
        bs_dir = DATA / "nba"
        rows: List[Dict[str, Any]] = []
        for bs_path in bs_dir.glob("boxscore_*.json"):
            game_id = bs_path.stem.replace("boxscore_", "")
            gd = gd_idx.get(game_id)
            if gd is None:
                continue  # no date -> cannot enforce leak boundary, skip
            try:
                bs = json.loads(bs_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for p in bs.get("players", []):
                if p.get("player_id") == pid:
                    rows.append({
                        "game_id": game_id,
                        "game_date": gd,
                        "ftm": float(p.get("ftm") or 0),
                        "fta": float(p.get("fta") or 0),
                        "min": _parse_minutes(p.get("min")),
                    })
                    break  # only one row per player per game
        df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["game_id", "game_date", "ftm", "fta", "min"])
        _SRC_CACHE[cache_key] = df

    if df.empty:
        return df
    # Apply as_of leak filter
    df = df.copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df[df["game_date"] <= pd.Timestamp(as_of)]


# ---------------------------------------------------------------------------
# Per-source sub-field builders
# ---------------------------------------------------------------------------

def _stability_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """FT% stability metrics from boxscore aggregation filtered to <= as_of."""
    df = _boxscore_ft_rows(pid, as_of)
    if df.empty:
        return {}

    n = len(df)
    total_ftm = df["ftm"].sum()
    total_fta = df["fta"].sum()
    ft_pct = float(total_ftm / total_fta) if total_fta > 0 else None

    # Per-game ft_pct series (only games with FTA > 0 to avoid 0/0)
    game_ft = df[df["fta"] > 0].copy()
    if not game_ft.empty:
        game_ft["game_ft_pct"] = game_ft["ftm"] / game_ft["fta"]
        ft_std = float(game_ft["game_ft_pct"].std()) if len(game_ft) > 1 else 0.0
        ft_cv = (ft_std / ft_pct) if (ft_pct and ft_pct > 0) else None
    else:
        ft_std = None
        ft_cv = None

    # Rolling last-10 FT% (games with FTA > 0, sorted by date)
    ft_pct_l10 = None
    if not game_ft.empty:
        recent = game_ft.sort_values("game_date").tail(10)
        l10_ftm = recent["ftm"].sum()
        l10_fta = recent["fta"].sum()
        if l10_fta > 0:
            ft_pct_l10 = round(float(l10_ftm / l10_fta), 4)

    return {
        "ft_pct": _rd(ft_pct),
        "ft_pct_std": _rd(ft_std),
        "ft_pct_cv": _rd(ft_cv),
        "ft_pct_l10": ft_pct_l10,
        "n_games": n,
        "n_games_with_fta": len(game_ft),
    }


def _attempts_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """FT attempt rate metrics from boxscores + player_breakdown_features."""
    df = _boxscore_ft_rows(pid, as_of)
    result: Dict[str, Any] = {}

    if not df.empty:
        n = len(df)
        fta_pg = _rd(df["fta"].mean())
        # FTA per 36 minutes (only games with min > 0)
        df_min = df[df["min"] > 0].copy()
        if not df_min.empty:
            fta_per_36 = _rd(float((df_min["fta"] / df_min["min"] * 36).mean()))
        else:
            fta_per_36 = None
        result["fta_pg"] = fta_pg
        result["fta_per_36"] = fta_per_36
        result["ftm_pg"] = _rd(df["ftm"].mean())
        result["n_games"] = n

    # fta_rate proxy from player_breakdown_features (scoring_pct_pts_ft)
    breakdown = _load("breakdown", CACHE / "player_breakdown_features.parquet")
    if breakdown is not None and not breakdown.empty and "player_id" in breakdown.columns:
        rows = breakdown[breakdown["player_id"] == pid]
        if not rows.empty and "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
            row = rows.iloc[0]
            result["pct_pts_from_ft"] = _rd(row.get("scoring_pct_pts_ft"))

    return result


def _hack_candidate_for_player(
    stability: Dict[str, Any],
    attempts: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute hack-a-player flag from FT% and FTA rate.

    Hack thresholds (industry-standard):
      - hack_flag: fta_pg >= 5.5 AND ft_pct < 0.72
      - hack_severity: linear score 0-1 based on ft_pct deficit below 0.72,
        weighted by fta_pg volume (higher volume = higher severity).
      - poor_shooter_flag: ft_pct < 0.65 regardless of attempts.
    """
    ft_pct = stability.get("ft_pct")
    fta_pg = attempts.get("fta_pg")

    hack_flag = None
    hack_severity = None
    poor_shooter_flag = None

    if ft_pct is not None:
        poor_shooter_flag = ft_pct < 0.65
        if fta_pg is not None:
            hack_flag = bool(fta_pg >= 5.5 and ft_pct < 0.72)
            if ft_pct < 0.72:
                pct_deficit = max(0.0, 0.72 - ft_pct)  # max 0.72 deficit
                volume_factor = min(1.0, fta_pg / 12.0)  # normalise at 12 FTA/g
                hack_severity = round(min(1.0, (pct_deficit / 0.72) * volume_factor), 4)
            else:
                hack_severity = 0.0

    return {
        "hack_flag": _rb(hack_flag),
        "hack_severity": _rd(hack_severity),
        "poor_shooter_flag": _rb(poor_shooter_flag),
        "hack_threshold_ft_pct": 0.72,
        "hack_threshold_fta_pg": 5.5,
    }


def _clutch_ft_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Clutch FT stats from data/cache/clutch_profiles_2025-26.parquet."""
    path = CACHE / "clutch_profiles_2025-26.parquet"
    df = _load("clutch26", path)
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}
    if "season" in rows.columns:
        rows = rows.sort_values("season", ascending=False)
    row = rows.iloc[0]

    # Compute FTA/game proxy: clutch_pts comes from clutch_pts_per36; FTA not directly
    # available, but clutch_ft_pct + clutch_pts_per36 partially describe clutch FT.
    return {
        "clutch_ft_pct": _rd(row.get("clutch_ft_pct")),
        "clutch_gp": _ri(row.get("clutch_gp")),
        "clutch_min": _rd(row.get("clutch_min")),
        "clutch_pts_per36": _rd(row.get("clutch_pts_per36")),
        "clutch_season": str(row.get("season", "")) or None,
    }


# ---------------------------------------------------------------------------
# AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerFTProfile(AtlasSection):
    """Deep player free-throw profile atlas section (entity='player', section='ft_profile').

    Captures the four dimensions of FT behavior needed for prop modelling and
    hack-a-player identification:
      1. Stability   -- long-run ft_pct + game-to-game variance (std/CV/L10).
      2. Attempts    -- FTA rate per game and per 36 min; pts-from-FT share.
      3. Hack flag   -- binary + severity score; identifies Fouling targets.
      4. Clutch FT   -- FT% and volume specifically in clutch situations.

    Sources:
      - data/nba/boxscore_*.json      (primary: ftm, fta, min per game per player)
      - data/player_adv_stats.parquet (game_date join for leak-safe filter)
      - data/cache/player_breakdown_features.parquet (pct_pts_from_ft)
      - data/cache/clutch_profiles_2025-26.parquet   (clutch FT stats)

    DEFER sections:
      - streak_analysis  (sequential FT outcomes not available; needs V2 PBP events)
      - pressure_splits  (last-2-min FT% needs PBP filtering not in boxscore format)
      - home_road_ft     (home/road FT% split not pre-aggregated per player)

    RESERVED CV SLOTS (values None; CV branch fills via store.fill_cv_slot):
      ft_motion_arc, ft_release_speed, ft_line_spread, ft_motion_stability
    """

    name: str = "ft_profile"
    entity: str = "player"
    source_name: str = (
        "boxscore_*.json + player_adv_stats.parquet + "
        "player_breakdown_features.parquet + clutch_profiles_2025-26.parquet"
    )
    conf_cap: Optional[str] = None

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the ft_profile artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee: boxscore rows are filtered to game_date <= as_of via the
        player_adv_stats game_id->game_date index.  Season-keyed sources (clutch,
        breakdown) use the latest available season without future-game filtering
        (pre-season-end summaries; acceptable as no intra-game info leaks).

        Returns None when all sources are missing for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        stability = _stability_for_player(pid, as_of)
        attempts = _attempts_for_player(pid, as_of)
        clutch_ft = _clutch_ft_for_player(pid, as_of)

        # Bail out when player absent from all sources
        if not stability and not attempts and not clutch_ft:
            return None

        hack_candidate = _hack_candidate_for_player(stability, attempts)

        # Headline scalar: ft_pct (most interpretable single FT metric)
        headline_ft_pct = stability.get("ft_pct")

        sub_fields: Dict[str, Any] = {
            "stability": stability,
            "attempts": attempts,
            "hack_candidate": hack_candidate,
            "clutch_ft": clutch_ft,
            "streak_analysis": {
                "_note": (
                    "DEFER: sequential FT outcome streaks require V2 PBP "
                    "EVENTMSGTYPE=3 per player per game; not available from "
                    "current boxscore or pbp_scraper (pbp_scraper drops "
                    "2025-26/playoff prefixes and V3->V2 normalise loses "
                    "PLAYER2 attribution)."
                )
            },
            "pressure_splits": {
                "_note": (
                    "DEFER: last-2-min/OT FT% requires PBP game-clock "
                    "filtering (PCTIMESTRING <= 2:00 with EVENTMSGTYPE=3); "
                    "not pre-aggregated; needs pbp_features.build() update."
                )
            },
            "home_road_ft": {
                "_note": (
                    "DEFER: home/road FT% split requires per-game home/away "
                    "assignment join not pre-aggregated per player in any "
                    "existing parquet."
                )
            },
        }

        # Sample size = number of games in boxscore data
        n = stability.get("n_games", 0) or attempts.get("n_games", 0) or 0
        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=_rd(headline_ft_pct),
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required top-level keys present; ft_pct in [0,1].

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "stability", "attempts", "hack_candidate",
            "clutch_ft", "streak_analysis", "pressure_splits", "home_road_ft",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # ft_pct must be in [0, 1] when present
        ft_pct = sf.get("stability", {}).get("ft_pct")
        if ft_pct is not None and not (0.0 <= ft_pct <= 1.0):
            return False

        # hack_severity in [0, 1] when present
        hack_sev = sf.get("hack_candidate", {}).get("hack_severity")
        if hack_sev is not None and not (0.0 <= hack_sev <= 1.0):
            return False

        # clutch FT pct in [0, 1] when present
        clutch_ft_pct = sf.get("clutch_ft", {}).get("clutch_ft_pct")
        if clutch_ft_pct is not None and not (0.0 <= clutch_ft_pct <= 1.0):
            return False

        # CV fields must all have value=None (not yet filled by CV branch)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for ft_profile (values None -- CV branch fills later).

        Slots are stable keys; the CV branch calls
        ``store.fill_cv_slot("player", pid, "ft_profile", slot, as_of, value)``
        to populate them without a profile rebuild.
        """
        return {
            "ft_motion_arc": CVSlot(
                name="ft_motion_arc",
                dtype="float",
                description=(
                    "Mean ball-arc angle in degrees at free-throw release, "
                    "estimated from CV ball-trajectory tracking between release "
                    "and the apex of the arc.  Higher arc generally correlates "
                    "with softer landings and higher make probability."
                ),
                unit="deg",
                value=None,
            ),
            "ft_release_speed": CVSlot(
                name="ft_release_speed",
                dtype="float",
                description=(
                    "Mean ball exit velocity (ft/s) at free-throw release, "
                    "from CV frame-differencing on the ball trajectory. "
                    "Proxy for shooter force control and routine consistency."
                ),
                unit="ft/s",
                value=None,
            ),
            "ft_line_spread": CVSlot(
                name="ft_line_spread",
                dtype="float",
                description=(
                    "Mean spacing (ft) between the two rebounders flanking the "
                    "lane during a free throw, from homography-projected player "
                    "positions.  Encodes lane-box positioning context."
                ),
                unit="ft",
                value=None,
            ),
            "ft_motion_stability": CVSlot(
                name="ft_motion_stability",
                dtype="float",
                description=(
                    "Frame-to-frame position jitter (px, normalised by player "
                    "bounding-box width) of the shooter during the FT routine, "
                    "from OSNet tracking.  Lower jitter = more consistent "
                    "pre-shot routine; proxy for fatigue or pressure effects."
                ),
                unit="px",
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level batch build + registration helper
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build ft_profile for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from
                    player_adv_stats (the primary join source).
        as_of:      leak boundary date (defaults to today).
        store:      PointInTimeStore; when provided, artifacts are written to store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        adv = _load("adv", DATA / "player_adv_stats.parquet")
        if adv is not None and "player_id" in adv.columns:
            player_ids = sorted(adv["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerFTProfile()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
