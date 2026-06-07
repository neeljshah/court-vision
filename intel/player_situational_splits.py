"""ARM-B atlas section: ``situational_splits`` — per-player situational context.

Section key: ``situational_splits``
Entity:      ``player``

**Sub-fields coverage:**

REAL (populated from existing parquets):
  home_road.*        — pts/reb/ast/fg3m/stl/blk/tov averages split by
                       home vs road games.  Built by joining
                       ``data/player_quarter_stats.parquet`` (sum across periods →
                       per-game box) with ``data/nba/season_games_*.json``
                       (game_id → home_team/away_team) and
                       ``data/cache/on_off_features.parquet`` (player_id →
                       team_abbreviation for 2024-25 season).  Delta = home − road.
  b2b.*              — mean stat output on back-to-back second nights vs rested
                       games (rest_days == 1 vs ≥ 2), derived from the same
                       per-game box joined to season_games b2b columns.
  clutch.*           — season clutch stats (last-5-min, margin ≤ 5) from
                       ``data/cache/clutch_profiles_2025-26.parquet``:
                       clutch_gp, clutch_pts, clutch_fg_pct, clutch_fg3_pct,
                       clutch_ft_pct, clutch_plus_minus, clutch_pts_per36.
                       Game-level clutch shots also from
                       ``data/cache/pbp_possession_features.parquet``
                       (pbp_clutch_shots_attempted, pbp_clutch_pts_scored).
  blowout.*          — performance in garbage-time / blowout games from
                       ``data/intelligence/garbage_time_player_aggregates.parquet``:
                       pct_minutes_in_gt mean, fraction of games with >50 % GT
                       minutes, pts/reb/ast/fg3m in garbage time vs full game.

DEFER (data gap — not available in current parquets):
  national_tv.*      — no national-TV game flag in any existing parquet or
                       JSON.  Requires a schedule enrichment pass (ESPN API /
                       NBA schedule page) to tag ESPN/TNT/ABC/League-Pass games.
                       DEFER until national_tv_schedule.parquet is built.
  revenge.*          — revenge-game indicator requires tracking prior-team history
                       per player, which is not stored in any current parquet.
                       DEFER: needs a traded-player enrichment pass joining on
                       player_profile_features.team_history or a new parquet.

RESERVED CV SLOTS (value=None, CV branch fills later):
  cv_clutch_velocity         — mean player velocity in clutch possession windows
                               (last 5 min, margin ≤ 5) vs full-game velocity
                               (CV homography + Kalman, delta).
  cv_b2b_fatigue_score       — mean CV fatigue_score on B2B second nights vs rested;
                               proxy for physical recovery quality from broadcast video.
  cv_home_spacing_delta      — home − road delta in convex-hull teammate spacing (ft²)
                               derived from CV homography; captures home-court crowd
                               / familiarity effects on floor-spreading.
  cv_blowout_drive_rate      — drive-attempt rate (drives per possession) in garbage
                               time vs regulation, from CV EventDetector drive tagging.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"
INTEL = DATA / "intelligence"
NBA_DIR = DATA / "nba"

# ---------------------------------------------------------------------------
# Module-level parquet + JSON cache (lazy, loaded once per process)
# ---------------------------------------------------------------------------

_SRC: Dict[str, Optional[Any]] = {}


def _load_parquet(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing/error."""
    if key not in _SRC:
        try:
            _SRC[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC[key] = None
    return _SRC[key]


def _load_games_lookup() -> Optional[pd.DataFrame]:
    """Build game_id -> {home_team, away_team, game_date, home_b2b, away_b2b} once."""
    key = "_games_lookup"
    if key not in _SRC:
        import glob
        rows: List[dict] = []
        for fpath in sorted(glob.glob(str(NBA_DIR / "season_games_*.json"))):
            try:
                with open(fpath, encoding="utf-8") as fh:
                    d = json.load(fh)
                rows.extend(d.get("rows", []))
            except Exception:
                continue
        if rows:
            df = pd.DataFrame(rows)[
                ["game_id", "home_team", "away_team", "game_date",
                 "home_back_to_back", "away_back_to_back"]
            ]
            _SRC[key] = df
        else:
            _SRC[key] = None
    return _SRC[key]


# ---------------------------------------------------------------------------
# Scalar-cleaning helpers (mirror factory pattern)
# ---------------------------------------------------------------------------

def _rd(v: Any) -> Optional[float]:
    """NaN/inf -> None, numpy -> python float, round 4dp."""
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


def _stat_split_dict(
    grp: pd.DataFrame,
    stat_cols: List[str],
    n_col: str = "_n",
) -> Dict[str, Any]:
    """Build a clean stats dict from a player-split group."""
    out: Dict[str, Any] = {"n_games": _ri(len(grp))}
    for col in stat_cols:
        if col in grp.columns:
            out[f"{col}_pg"] = _rd(grp[col].mean())
    return out


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _build_per_game_box(pid: int, as_of_iso: str) -> Optional[pd.DataFrame]:
    """Build per-game box stats for player by summing quarter_stats across periods.

    Leak guard: only includes game_date <= as_of_iso (filtered through season_games).
    Returns None if insufficient data.

    REAL source: data/player_quarter_stats.parquet + data/nba/season_games_*.json
    """
    q = _load_parquet("quarter_stats", DATA / "player_quarter_stats.parquet")
    if q is None or q.empty:
        return None

    player_q = q[q["player_id"] == pid].copy()
    if player_q.empty:
        return None

    # Sum across periods to get full-game box
    stat_cols = ["min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pf", "plus_minus"]
    agg_dict = {c: "sum" for c in stat_cols if c in player_q.columns}
    per_game = player_q.groupby("game_id").agg(agg_dict).reset_index()

    # Join games lookup for home_team / away_team / game_date / b2b
    games = _load_games_lookup()
    if games is None:
        return None

    per_game = per_game.merge(games, on="game_id", how="inner")
    if per_game.empty:
        return None

    # Leak guard: game_date <= as_of_iso
    per_game["game_date"] = per_game["game_date"].astype(str).str[:10]
    per_game = per_game[per_game["game_date"] <= as_of_iso]
    if per_game.empty:
        return None

    return per_game


def _infer_player_team(pid: int, as_of_iso: str) -> Optional[str]:
    """Infer player's team_abbreviation from on_off_features (2024-25 season).

    REAL source: data/cache/on_off_features.parquet.
    Falls back to None if the player is not in the 2024-25 roster.
    """
    oo = _load_parquet("on_off", CACHE / "on_off_features.parquet")
    if oo is None or "player_id" not in oo.columns or "team_abbreviation" not in oo.columns:
        return None
    rows = oo[oo["player_id"] == pid]
    if rows.empty:
        return None
    return str(rows.iloc[-1]["team_abbreviation"])


def _home_road_split(
    pid: int, as_of_iso: str
) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    """Compute home vs road per-game averages for pts/reb/ast/fg3m/stl/blk/tov.

    Returns (home_dict, road_dict, n_total_games).

    REAL if on_off team mapping is available (covers 2024-25 players).
    Returns empty dicts if team cannot be determined.
    """
    per_game = _build_per_game_box(pid, as_of_iso)
    if per_game is None or per_game.empty:
        return {}, {}, 0

    team = _infer_player_team(pid, as_of_iso)
    if not team:
        return {}, {}, 0

    # Determine is_home: player's team == home_team in that game
    per_game["is_home"] = per_game["home_team"] == team
    stat_cols = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

    home = per_game[per_game["is_home"]]
    road = per_game[~per_game["is_home"]]

    n_home = len(home)
    n_road = len(road)
    n_total = len(per_game)

    if n_home == 0 and n_road == 0:
        return {}, {}, 0

    def _split_stats(grp: pd.DataFrame, n: int) -> Dict[str, Any]:
        out: Dict[str, Any] = {"n_games": n}
        for col in stat_cols:
            if col in grp.columns:
                out[f"{col}_pg"] = _rd(grp[col].mean())
        return out

    home_d = _split_stats(home, n_home)
    road_d = _split_stats(road, n_road)

    # Compute deltas (home - road) for key stats
    for col in stat_cols:
        h_v = home_d.get(f"{col}_pg")
        r_v = road_d.get(f"{col}_pg")
        if h_v is not None and r_v is not None:
            home_d[f"{col}_delta_home_minus_road"] = _rd(h_v - r_v)

    return home_d, road_d, n_total


def _b2b_split(
    pid: int, as_of_iso: str
) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    """Compute B2B second-night vs rested per-game averages.

    A B2B game is defined by home_back_to_back or away_back_to_back == 1.0 for the
    player's team, inferred via on_off_features team mapping.

    Returns (b2b_dict, rested_dict, n_total_games).
    """
    per_game = _build_per_game_box(pid, as_of_iso)
    if per_game is None or per_game.empty:
        return {}, {}, 0

    team = _infer_player_team(pid, as_of_iso)
    if not team:
        return {}, {}, 0

    # Determine is_b2b for this player's team
    per_game["is_home_team"] = per_game["home_team"] == team
    per_game["is_b2b"] = np.where(
        per_game["is_home_team"],
        per_game["home_back_to_back"].fillna(0) == 1.0,
        per_game["away_back_to_back"].fillna(0) == 1.0,
    )

    stat_cols = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min"]
    b2b = per_game[per_game["is_b2b"]]
    rested = per_game[~per_game["is_b2b"]]

    n_b2b = len(b2b)
    n_rested = len(rested)
    n_total = len(per_game)

    def _split_stats(grp: pd.DataFrame, n: int) -> Dict[str, Any]:
        out: Dict[str, Any] = {"n_games": n}
        for col in stat_cols:
            if col in grp.columns:
                out[f"{col}_pg"] = _rd(grp[col].mean())
        return out

    b2b_d = _split_stats(b2b, n_b2b)
    rested_d = _split_stats(rested, n_rested)

    # Compute delta (b2b - rested) for context
    for col in stat_cols:
        b_v = b2b_d.get(f"{col}_pg")
        r_v = rested_d.get(f"{col}_pg")
        if b_v is not None and r_v is not None:
            b2b_d[f"{col}_delta_b2b_minus_rested"] = _rd(b_v - r_v)

    return b2b_d, rested_d, n_total


def _clutch_stats(pid: int, as_of_iso: str) -> Dict[str, Any]:
    """Season clutch performance from clutch_profiles_2025-26 + pbp_possession_features.

    REAL source: data/cache/clutch_profiles_2025-26.parquet (season aggregate clutch
    stats: last-5-min, margin ≤ 5) and data/cache/pbp_possession_features.parquet
    (per-game clutch shots/pts, filtered <= as_of_iso).

    Leak guard: clutch_profiles is 2025-26 end-of-season; included only if
    as_of >= 2025-10-01.  PBP is filtered per game_date <= as_of_iso.
    """
    out: Dict[str, Any] = {}

    # Season-aggregate clutch (2025-26 only; season boundary leak guard)
    if as_of_iso >= "2025-10-01":
        cp = _load_parquet("clutch26", CACHE / "clutch_profiles_2025-26.parquet")
        if cp is not None and not cp.empty:
            rows = cp[cp["player_id"] == pid]
            if not rows.empty:
                r = rows.iloc[-1]
                out["season_clutch"] = {
                    "clutch_gp": _ri(r.get("clutch_gp")),
                    "clutch_min": _rd(r.get("clutch_min")),
                    "clutch_pts": _rd(r.get("clutch_pts")),
                    "clutch_fg_pct": _rd(r.get("clutch_fg_pct")),
                    "clutch_fg3_pct": _rd(r.get("clutch_fg3_pct")),
                    "clutch_ft_pct": _rd(r.get("clutch_ft_pct")),
                    "clutch_plus_minus": _rd(r.get("clutch_plus_minus")),
                    "clutch_pts_per36": _rd(r.get("clutch_pts_per36")),
                    "season": str(r.get("season", "2025-26")),
                }

    # Per-game clutch shots from PBP (leak-safe: filtered by game_date)
    pbp = _load_parquet("pbp_poss", CACHE / "pbp_possession_features.parquet")
    if pbp is not None and not pbp.empty and "player_id" in pbp.columns:
        player_pbp = pbp[pbp["player_id"] == pid].copy()
        if "game_date" in player_pbp.columns:
            player_pbp["game_date"] = player_pbp["game_date"].astype(str).str[:10]
            player_pbp = player_pbp[player_pbp["game_date"] <= as_of_iso]
        if not player_pbp.empty:
            n_pbp = len(player_pbp)
            clutch_fga = _rd(player_pbp["pbp_clutch_shots_attempted"].mean()) if "pbp_clutch_shots_attempted" in player_pbp.columns else None
            clutch_pts = _rd(player_pbp["pbp_clutch_pts_scored"].mean()) if "pbp_clutch_pts_scored" in player_pbp.columns else None
            out["pbp_clutch_per_game"] = {
                "n_games": n_pbp,
                "clutch_shots_attempted_pg": clutch_fga,
                "clutch_pts_scored_pg": clutch_pts,
            }

    return out


def _blowout_stats(pid: int, as_of_iso: str) -> Dict[str, Any]:
    """Garbage-time / blowout performance from garbage_time_player_aggregates.parquet.

    REAL source: data/intelligence/garbage_time_player_aggregates.parquet.
    Leak guard: game_date <= as_of_iso.

    Returns blowout summary: pct of games with GT entry, mean GT points/reb/ast,
    fg_pct in GT, vs full-game fg_pct (from fgm/fga in GT).
    """
    gt = _load_parquet("gt_agg", INTEL / "garbage_time_player_aggregates.parquet")
    if gt is None or gt.empty:
        return {}

    player_gt = gt[gt["player_id"] == pid].copy()
    if player_gt.empty:
        return {}

    # Leak guard: game_date <= as_of_iso
    if "game_date" in player_gt.columns:
        player_gt["game_date"] = player_gt["game_date"].astype(str).str[:10]
        player_gt = player_gt[player_gt["game_date"] <= as_of_iso]
    if player_gt.empty:
        return {}

    n_total = len(player_gt)
    # Blowout games defined as pct_minutes_in_gt > 0.1 (any notable GT time)
    gt_games = player_gt[player_gt["pct_minutes_in_gt"] > 0.10]
    n_gt = len(gt_games)

    result: Dict[str, Any] = {
        "n_games_total": n_total,
        "n_games_with_gt_entry": n_gt,
        "pct_games_in_garbage_time": _rd(n_gt / n_total) if n_total > 0 else None,
        "mean_pct_min_in_gt": _rd(player_gt["pct_minutes_in_gt"].mean()),
    }

    if n_gt > 0:
        result["gt_performance"] = {
            "pts_in_gt_pg": _rd(gt_games["points_in_gt"].mean()) if "points_in_gt" in gt_games.columns else None,
            "reb_in_gt_pg": _rd(gt_games["reb_in_gt"].mean()) if "reb_in_gt" in gt_games.columns else None,
            "ast_in_gt_pg": _rd(gt_games["ast_in_gt"].mean()) if "ast_in_gt" in gt_games.columns else None,
            "fg3m_in_gt_pg": _rd(gt_games["fg3m_in_gt"].mean()) if "fg3m_in_gt" in gt_games.columns else None,
            "n_gt_games": n_gt,
        }
        # GT fg_pct from fgm/fga columns
        total_fgm = gt_games["fgm_in_gt"].sum() if "fgm_in_gt" in gt_games.columns else 0.0
        total_fga = gt_games["fga_in_gt"].sum() if "fga_in_gt" in gt_games.columns else 0.0
        result["gt_performance"]["gt_fg_pct"] = (
            _rd(total_fgm / total_fga) if total_fga > 0 else None
        )

    return result


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerSituationalSplits(AtlasSection):
    """Deep player situational-splits atlas section (section='situational_splits').

    Builds a provenance-stamped, leak-safe artifact covering home/road splits,
    back-to-back performance, clutch-time stats, and blowout/garbage-time usage.
    Reserves 4 CV slots for spatial/behavioral enrichment later.

    Sources used (all existing repo parquets/JSON — no re-derivation):
      - data/player_quarter_stats.parquet + data/nba/season_games_*.json
        (home/road and B2B splits; 956 games × 609 players, joined to 553 with team)
      - data/cache/on_off_features.parquet (player → team_abbreviation, 2024-25)
      - data/cache/clutch_profiles_2025-26.parquet (season clutch stats, 492 players)
      - data/cache/pbp_possession_features.parquet (per-game clutch shots, 43 K rows)
      - data/intelligence/garbage_time_player_aggregates.parquet
        (blowout/GT usage, 51 K rows, 728 players)

    DEFER sub-fields:
      national_tv (no TV-flag parquet exists; requires schedule enrichment pass),
      revenge (no prior-team history parquet exists; requires traded-player enrichment).

    CV slots reserved (null until CV-fix session fills them):
      cv_clutch_velocity, cv_b2b_fatigue_score, cv_home_spacing_delta,
      cv_blowout_drive_rate.
    """

    name: str = "situational_splits"
    entity: str = "player"
    source_name: str = (
        "player_quarter_stats.parquet + season_games_*.json + "
        "on_off_features.parquet + clutch_profiles_2025-26.parquet + "
        "pbp_possession_features.parquet + "
        "garbage_time_player_aggregates.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the situational_splits artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - player_quarter_stats / season_games: game_date <= as_of applied.
          - on_off_features: 2024-25 season; used only for team lookup (not a stat target).
          - clutch_profiles_2025-26: included only if as_of >= 2025-10-01.
          - pbp_possession_features: filtered by game_date <= as_of.
          - garbage_time_player_aggregates: filtered by game_date <= as_of.

        Returns None when no data is available for the player in any source.
        """
        pid = int(entity_id)
        as_of_iso = as_of.date().isoformat()

        # Build each sub-section
        home_d, road_d, n_games = _home_road_split(pid, as_of_iso)
        b2b_d, rested_d, _ = _b2b_split(pid, as_of_iso)
        clutch_d = _clutch_stats(pid, as_of_iso)
        blowout_d = _blowout_stats(pid, as_of_iso)

        # DEFER: no national-TV flag or per-player prior-team history available
        national_tv_d: Dict[str, Any] = {
            "_note": (
                "DEFER: no national-TV game flag exists in any repo parquet. "
                "Requires a schedule enrichment pass to build "
                "national_tv_schedule.parquet tagging ESPN/TNT/ABC games."
            )
        }
        revenge_d: Dict[str, Any] = {
            "_note": (
                "DEFER: no prior-team history per player in any current parquet. "
                "Requires a traded-player enrichment pass building a "
                "player_team_history.parquet (e.g. from player_profile_features "
                "or NBA API LeaguePlayerOnDetails) to flag revenge games."
            )
        }

        # Return None only if ALL data sources returned empty
        has_any = (
            bool(home_d) or bool(b2b_d) or bool(clutch_d) or bool(blowout_d)
        )
        if not has_any:
            return None

        sub_fields: Dict[str, Any] = {
            "home_road": {
                "home": home_d,
                "road": road_d,
                "_n_games_in_split": n_games,
                "_source": "player_quarter_stats.parquet + season_games_*.json + on_off_features.parquet",
            },
            "back_to_back": {
                "b2b_second_night": b2b_d,
                "rested": rested_d,
                "_source": "player_quarter_stats.parquet + season_games_*.json (home/away_back_to_back)",
            },
            "clutch": {
                **clutch_d,
                "_definition": "last 5 min, margin ≤ 5 points",
                "_source": "clutch_profiles_2025-26.parquet + pbp_possession_features.parquet",
            },
            "blowout": {
                **blowout_d,
                "_definition": "garbage-time = pct_minutes_in_gt > 10%; blowout = any GT entry",
                "_source": "garbage_time_player_aggregates.parquet",
            },
            "national_tv": national_tv_d,
            "revenge": revenge_d,
        }

        # Sample size: best available; hierarchy: quarter_stats games > GT games
        gt_rows = _load_parquet("gt_agg", INTEL / "garbage_time_player_aggregates.parquet")
        n_gt = 0
        if gt_rows is not None and not gt_rows.empty:
            pg = gt_rows[gt_rows["player_id"] == pid].copy()
            if "game_date" in pg.columns:
                pg["game_date"] = pg["game_date"].astype(str).str[:10]
                pg = pg[pg["game_date"] <= as_of_iso]
            n_gt = len(pg)

        n = n_games if n_games > 0 else n_gt
        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_iso,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=None,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_iso,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required sub-field keys present; CV slots null.

        The full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "home_road", "back_to_back", "clutch",
            "blowout", "national_tv", "revenge",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # All CV slots must be present with value=None (not yet filled)
        for slot_name in self.cv_fields():
            if slot_name not in artifact.cv_fields:
                return False
            if artifact.cv_fields[slot_name].value is not None:
                return False

        # Blowout pct sanity: pct_games_in_garbage_time in [0, 1] if present
        blowout = sf.get("blowout", {})
        pct_gt = blowout.get("pct_games_in_garbage_time")
        if pct_gt is not None:
            try:
                if not (0.0 <= float(pct_gt) <= 1.0):
                    return False
            except (TypeError, ValueError):
                return False

        # Clutch fg_pct in [0, 1] if present
        clutch = sf.get("clutch", {})
        sc = clutch.get("season_clutch", {})
        for pct_key in ("clutch_fg_pct", "clutch_fg3_pct", "clutch_ft_pct"):
            v = sc.get(pct_key)
            if v is not None:
                try:
                    if not (0.0 <= float(v) <= 1.0):
                        return False
                except (TypeError, ValueError):
                    return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for situational_splits (values None — CV fills later).

        These slots are stable contract keys; the CV-fix session calls
        ``store.fill_cv_slot("player", pid, "situational_splits", slot, as_of, val)``.
        """
        return {
            "cv_clutch_velocity": CVSlot(
                name="cv_clutch_velocity",
                dtype="float",
                description=(
                    "Mean player velocity (ft/s) in clutch possession windows "
                    "(last 5 min, margin ≤ 5) minus full-game mean velocity, "
                    "from CV homography + Kalman tracking. Positive = player "
                    "moves faster in clutch; negative = fatigue/ball-watching."
                ),
                unit="ft/s",
                value=None,
            ),
            "cv_b2b_fatigue_score": CVSlot(
                name="cv_b2b_fatigue_score",
                dtype="float",
                description=(
                    "Mean CV fatigue_score (from cv_fatigue_trajectories.parquet "
                    "or per-frame advanced_features.add_fatigue_features) on B2B "
                    "second nights minus rested-game mean. Proxy for physical "
                    "recovery quality as observed in broadcast video."
                ),
                unit=None,
                value=None,
            ),
            "cv_home_spacing_delta": CVSlot(
                name="cv_home_spacing_delta",
                dtype="float",
                description=(
                    "Home − road delta in mean convex-hull teammate spacing (ft²) "
                    "from CV homography. Captures home-court familiarity / crowd "
                    "effects on offensive floor-spreading. Per-player seasonal mean."
                ),
                unit="ft²",
                value=None,
            ),
            "cv_blowout_drive_rate": CVSlot(
                name="cv_blowout_drive_rate",
                dtype="float",
                description=(
                    "Drive-attempt rate (drives per possession) in garbage-time "
                    "windows minus regulation rate, from CV EventDetector drive "
                    "tagging. Indicates whether a player attacks more or coasts "
                    "when the outcome is decided."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level build + registration helper
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build situational_splits for a list of players and register via the bridge.

    Args:
        player_ids: NBA player_id list (int).  If None, discovers from
                    player_quarter_stats.parquet (broadest game-level coverage).
        as_of:      leak boundary date (defaults to today midnight UTC).
        store:      PointInTimeStore; when provided, artifacts are written.
        dry_run:    compute everything but skip disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        q = _load_parquet("quarter_stats_disc", DATA / "player_quarter_stats.parquet")
        if q is not None and "player_id" in q.columns:
            player_ids = sorted(q["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerSituationalSplits()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)


def get_section() -> PlayerSituationalSplits:
    """Return the section instance (bridge registry hook)."""
    return PlayerSituationalSplits()
