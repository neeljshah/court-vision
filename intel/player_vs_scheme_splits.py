"""ARM-B atlas section: ``vs_scheme_splits`` — per-player stats vs opponent defensive schemes.

Implements :class:`AtlasSection` for the ``"vs_scheme_splits"`` section of a player's
persistent profile.  Groups per-game box-score stats by the *opponent team's dominant
defensive scheme tag* (DROP COVERAGE / SWITCH HEAVY / PAINT-FIRST DEFENSE / PACE CONTROL
/ ISO FORCE / HELP DEFENSE / BALANCED) to reveal how a player's production shifts when
facing each defensive archetype.

**Sub-field coverage:**

REAL (populated from existing parquets):
  by_scheme.<tag>.n_games           — game count vs this scheme type.
  by_scheme.<tag>.ts_pct            — mean true-shooting % in those games.
  by_scheme.<tag>.efg_pct           — mean effective FG % (<=1.6 ceil).
  by_scheme.<tag>.usage_pct         — mean usage % (<=1.0).
  by_scheme.<tag>.pts_pg            — mean points per game.
  by_scheme.<tag>.reb_pg            — mean rebounds per game.
  by_scheme.<tag>.ast_pg            — mean assists per game.
  by_scheme.<tag>.fg3m_pg           — mean 3-pointers made per game.
  by_scheme.<tag>.stl_pg            — mean steals per game.
  by_scheme.<tag>.blk_pg            — mean blocks per game.
  by_scheme.<tag>.tov_pg            — mean turnovers per game.
  best_scheme                       — tag with the highest ts_pct (at least 3 games).
  worst_scheme                      — tag with the lowest ts_pct (at least 3 games).
  scheme_ts_spread                  — best minus worst ts_pct (signed, ends in _minus_).
  n_games_total                     — total games used (sum of all scheme counts with data).

  Sources:
    - data/cache/adv_stats_splits.parquet       — player_id + game_id + game_date + opp_team
    - data/player_adv_stats.parquet             — ts_pct / efg_pct / usage / minutes per game
    - data/cache/pregame_oof.parquet            — actual pts/reb/ast/fg3m/stl/blk/tov per game
    - data/intelligence/defensive_schemes.parquet — team -> dominant_tag mapping (30 teams)

DEFER (data gap — not available in current parquets):
  by_scheme.<tag>.drop_rate         — DEFER: no possession-level coverage-type parquet; needs
                                      PBP screen-action annotation.
  by_scheme.<tag>.switch_pct        — DEFER: same; no per-possession switch tagging.
  by_scheme.<tag>.blitz_pct         — DEFER: no PKR defensive-assignment parquet.
  by_scheme.<tag>.zone_pct          — DEFER: no zone vs man annotation.

RESERVED CV SLOTS (value=None, CV branch fills later):
  contest_vs_scheme — distribution of contest-level (defender distance at shot release)
                      split by opponent dominant scheme tag; filled from CV EventDetector.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INTEL = DATA / "intelligence"
CACHE = DATA / "cache"

# ---------------------------------------------------------------------------
# Module-level lazy data cache (one load per process per path)
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


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
    """Clean integer scalar: NaN/inf -> None, numpy -> python int."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _safe_pct(v: Optional[float], ceil: float = 1.0) -> Optional[float]:
    """Return v only if it is in [0, ceil]; otherwise None (face-validity guard)."""
    if v is None:
        return None
    if 0.0 <= v <= ceil:
        return v
    return None


# ---------------------------------------------------------------------------
# Per-source helpers
# ---------------------------------------------------------------------------

def _dominant_tag_map() -> Dict[str, str]:
    """Return {team_tricode: dominant_tag} from defensive_schemes.parquet.

    The map is built at module level and cached; it covers all 30 NBA teams.
    """
    df = _load("def_schemes", INTEL / "defensive_schemes.parquet")
    if df is None or df.empty:
        return {}
    if "team" not in df.columns or "dominant_tag" not in df.columns:
        return {}
    return df.set_index("team")["dominant_tag"].to_dict()


def _build_per_game_frame(
    pid: int, as_of: _dt.datetime
) -> Optional[pd.DataFrame]:
    """Build a per-game DataFrame for the player with opp_team and scheme tag.

    Joins three sources on (player_id, game_id, game_date):
      1. adv_stats_splits   -> opp_team (leak-filtered to game_date <= as_of)
      2. player_adv_stats   -> ts_pct, efg_pct, usage, minutes
      3. pregame_oof pivoted -> actual pts/reb/ast/fg3m/stl/blk/tov

    Returns a DataFrame with one row per qualifying game and a ``dominant_tag``
    column, or None if the player has no qualifying rows.
    """
    as_of_ts = pd.Timestamp(as_of)

    # --- Source 1: opp_team per game ---
    sp = _load("adv_splits", CACHE / "adv_stats_splits.parquet")
    if sp is None or sp.empty:
        return None
    sp_p = sp[sp["player_id"] == pid].copy()
    if sp_p.empty:
        return None
    sp_p["game_date"] = pd.to_datetime(sp_p["game_date"])
    sp_p = sp_p[sp_p["game_date"] <= as_of_ts][
        ["player_id", "game_id", "game_date", "opp_team"]
    ]
    if sp_p.empty:
        return None

    # --- Source 2: ts_pct / efg_pct / usage / minutes per game ---
    adv = _load("adv_stats", DATA / "player_adv_stats.parquet")
    if adv is not None and not adv.empty:
        adv_p = adv[adv["player_id"] == pid].copy()
        adv_p["game_date"] = pd.to_datetime(adv_p["game_date"])
        adv_p = adv_p[adv_p["game_date"] <= as_of_ts][
            [
                "player_id", "game_id", "game_date",
                "usagepercentage", "trueshootingpercentage",
                "effectivefieldgoalpercentage", "minutes",
            ]
        ]
        base = sp_p.merge(adv_p, on=["player_id", "game_id", "game_date"], how="inner")
    else:
        base = sp_p

    if base.empty:
        return None

    # --- Source 3: actual per-game stats from pregame_oof (pivot) ---
    oof = _load("oof", CACHE / "pregame_oof.parquet")
    if oof is not None and not oof.empty:
        oof_p = oof[oof["player_id"] == pid].copy()
        oof_p["game_date"] = pd.to_datetime(oof_p["game_date"])
        oof_p = oof_p[oof_p["game_date"] <= as_of_ts]
        if not oof_p.empty:
            try:
                oof_wide = (
                    oof_p[["game_id", "stat", "actual"]]
                    .pivot(index="game_id", columns="stat", values="actual")
                    .reset_index()
                )
                oof_wide.columns.name = None
                base = base.merge(oof_wide, on="game_id", how="left")
            except Exception:
                pass  # if pivot fails, stat columns are absent -> show as None

    # --- Attach dominant_tag ---
    tag_map = _dominant_tag_map()
    if not tag_map:
        return None
    base["dominant_tag"] = base["opp_team"].map(tag_map)
    base = base[base["dominant_tag"].notna()]

    return base if not base.empty else None


# ---------------------------------------------------------------------------
# Scheme-level aggregation
# ---------------------------------------------------------------------------

_STAT_COLS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_ADV_COLS = [
    ("usagepercentage", "usage_pct"),
    ("trueshootingpercentage", "ts_pct"),
    ("effectivefieldgoalpercentage", "efg_pct"),
]
# ceil for pct-type adv columns (ts/efg allowed up to 1.6 per intel_validator)
_ADV_CEIL = {
    "ts_pct": 1.6,
    "efg_pct": 1.6,
    "usage_pct": 1.0,
}


def _aggregate_by_scheme(df: pd.DataFrame) -> Dict[str, Any]:
    """Return by_scheme dict: one entry per dominant_tag with per-game averages.

    Only tags with at least 1 qualifying game are included.  All proportion
    fields are validated to [0, ceil] before persisting.
    """
    by_scheme: Dict[str, Any] = {}

    for tag, grp in df.groupby("dominant_tag"):
        n = len(grp)
        entry: Dict[str, Any] = {"n_games": n}

        # Advanced stats averages (ts_pct / efg_pct / usage_pct)
        for src_col, dst_key in _ADV_COLS:
            if src_col in grp.columns:
                raw = _rd(grp[src_col].mean())
                entry[dst_key] = _safe_pct(raw, ceil=_ADV_CEIL.get(dst_key, 1.0))
            else:
                entry[dst_key] = None

        # Actual stat averages (pts_pg / reb_pg / ...)
        for stat in _STAT_COLS:
            if stat in grp.columns:
                raw = grp[stat].dropna()
                entry[f"{stat}_pg"] = _rd(raw.mean()) if not raw.empty else None
            else:
                entry[f"{stat}_pg"] = None

        # Deferred per-possession fields
        entry["drop_rate"] = None     # DEFER: no possession-level coverage annotation
        entry["switch_pct"] = None    # DEFER: no per-possession switch annotation
        entry["blitz_pct"] = None     # DEFER: no PKR defensive-assignment parquet
        entry["zone_pct"] = None      # DEFER: no zone vs man annotation

        # Normalise tag key to safe dict key (replace spaces with underscores, lower)
        tag_key = str(tag).lower().replace(" ", "_").replace("-", "_")
        by_scheme[tag_key] = {"tag": str(tag), **entry}

    return by_scheme


def _best_worst_scheme(
    by_scheme: Dict[str, Any]
) -> tuple:
    """Return (best_tag, worst_tag, ts_spread) among tags with n_games >= 3.

    Uses ts_pct as the ranking criterion.  Returns (None, None, None) if fewer
    than 2 qualifying tags exist.  ts_spread is named with '_minus_' to signal
    it is a signed difference and exempt from the [0,1] proportion rule.
    """
    qualified = [
        (info["tag"], info.get("ts_pct"))
        for info in by_scheme.values()
        if info.get("n_games", 0) >= 3 and info.get("ts_pct") is not None
    ]
    if len(qualified) < 2:
        return None, None, None

    qualified.sort(key=lambda x: x[1], reverse=True)
    best_tag, best_ts = qualified[0]
    worst_tag, worst_ts = qualified[-1]
    spread = _rd(best_ts - worst_ts) if (best_ts is not None and worst_ts is not None) else None
    return best_tag, worst_tag, spread


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerVsSchemeSplits(AtlasSection):
    """Player stats split by opponent defensive scheme type (entity='player').

    Section key: ``vs_scheme_splits``.

    Groups each player's per-game box-score stats by the opponent team's dominant
    defensive scheme tag from the team_defensive_scheme atlas, producing per-scheme
    averages for ts_pct, efg_pct, usage, pts/reb/ast/fg3m/stl/blk/tov.

    REAL sub-fields:
      by_scheme.<tag>.*   — per-scheme averages (n_games, ts_pct, efg_pct,
                            usage_pct, pts_pg, reb_pg, ast_pg, fg3m_pg,
                            stl_pg, blk_pg, tov_pg) from adv_stats_splits +
                            player_adv_stats + pregame_oof actual column.
      best_scheme         — tag with highest ts_pct (>= 3 games).
      worst_scheme        — tag with lowest ts_pct (>= 3 games).
      scheme_ts_spread    — best_ts_pct minus worst_ts_pct (signed; _minus_ exempt).
      n_games_total       — total qualifying games.

    DEFER sub-fields (no possession-level defense-type annotation available):
      drop_rate / switch_pct / blitz_pct / zone_pct within each scheme entry.

    RESERVED CV SLOT:
      contest_vs_scheme   — CV-measured contest level (defender distance at shot
                            release) split by opponent scheme tag; CV branch fills.

    Sources:
      data/cache/adv_stats_splits.parquet      (opp_team per game, leak-filtered)
      data/player_adv_stats.parquet            (ts_pct, efg_pct, usage, minutes)
      data/cache/pregame_oof.parquet           (actual pts/reb/ast/fg3m/stl/blk/tov)
      data/intelligence/defensive_schemes.parquet (dominant_tag map, 30 teams)
    """

    name: str = "vs_scheme_splits"
    entity: str = "player"
    source_name: str = (
        "adv_stats_splits.parquet + player_adv_stats.parquet + "
        "pregame_oof.parquet + defensive_schemes.parquet"
    )
    conf_cap: Optional[str] = None  # no hard cap; CV slots capped separately

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the vs_scheme_splits artifact for ``entity_id`` as-of ``as_of``.

        Leak guarantee: adv_stats_splits, player_adv_stats, and pregame_oof are all
        filtered to game_date <= as_of before any aggregation.
        defensive_schemes.parquet is a season-level summary without game_date; treated
        as a pre-published aggregate (same convention as playtypes in shot_profile).

        Args:
            entity_id: NBA player_id (int).
            as_of:     datetime representing the decision boundary (leak cutoff).

        Returns:
            AtlasArtifact with by_scheme split stats + reserved CV slot, or None
            if the player has no qualifying games in any source.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        # Build the per-game base frame (leak-filtered, with opp_team + dominant_tag)
        df = _build_per_game_frame(pid, as_of)
        if df is None or df.empty:
            return None

        # Per-scheme aggregation
        by_scheme = _aggregate_by_scheme(df)
        if not by_scheme:
            return None

        # Summary fields
        best, worst, spread = _best_worst_scheme(by_scheme)
        n_games_total = _ri(len(df))

        sub_fields: Dict[str, Any] = {
            "by_scheme": by_scheme,
            "best_scheme": best,
            "worst_scheme": worst,
            # _minus_ suffix marks this as a signed difference (exempt from [0,1] rule)
            "scheme_ts_pct_best_minus_worst": spread,
            "n_games_total": n_games_total,
        }

        # n = total games (actual game-count, satisfies CRITICAL LESSON 1)
        n = n_games_total or 0
        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=best,  # headline: scheme where this player performs best
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, pct values in safe ranges.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False
        sf = artifact.sub_fields
        required_keys = {
            "by_scheme", "best_scheme", "worst_scheme",
            "scheme_ts_pct_best_minus_worst", "n_games_total",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Validate pct fields within each scheme entry
        by_scheme = sf.get("by_scheme", {})
        for tag_key, entry in by_scheme.items():
            if not isinstance(entry, dict):
                return False
            ts = entry.get("ts_pct")
            if ts is not None and not (0.0 <= ts <= 1.6):
                return False
            efg = entry.get("efg_pct")
            if efg is not None and not (0.0 <= efg <= 1.6):
                return False
            usage = entry.get("usage_pct")
            if usage is not None and not (0.0 <= usage <= 1.0):
                return False
            # Per-game stats must be non-negative
            for stat_key in ["pts_pg", "reb_pg", "ast_pg", "fg3m_pg",
                             "stl_pg", "blk_pg", "tov_pg"]:
                v = entry.get(stat_key)
                if v is not None and v < 0.0:
                    return False

        # CV fields: all values must be None (CV branch has not run yet)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema (values None — CV branch fills later).

        Slot: contest_vs_scheme — CV-measured contest level distribution at shot
        release, keyed by the opponent team's dominant scheme tag.  The CV branch
        populates this by grouping CV EventDetector contest readings per game
        by the opponent's scheme tag (same join as the build() pipeline above).
        """
        return {
            "contest_vs_scheme": CVSlot(
                name="contest_vs_scheme",
                dtype="dist",
                description=(
                    "Distribution (mean contest level per scheme tag) of nearest-defender "
                    "distance at shot release — from CV EventDetector + homography — grouped "
                    "by the opponent team's dominant defensive scheme tag "
                    "(DROP COVERAGE / SWITCH HEAVY / PAINT-FIRST / etc.). "
                    "Enables quantifying whether a scheme type generates more open looks."
                ),
                unit="ft",
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration helper (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build vs_scheme_splits for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from
                    adv_stats_splits.parquet (all players with game rows).
        as_of:      leak boundary date (defaults to today midnight UTC).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        df = _load("adv_splits_disc", CACHE / "adv_stats_splits.parquet")
        if df is not None and not df.empty and "player_id" in df.columns:
            player_ids = sorted(df["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerVsSchemeSplits()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
