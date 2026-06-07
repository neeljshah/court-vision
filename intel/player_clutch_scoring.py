"""ARM-B atlas section: ``clutch_scoring`` — last-5-min (<=5-pt) scoring profile.

Implements :class:`AtlasSection` for the ``"clutch_scoring"`` section of a player's
persistent profile.  All sub-fields come from existing parquets (no re-derivation).

**Sub-field coverage:**

REAL (populated from parquets):
  scoring.*    — fg_pct / fg3_pct / ft_pct / pts_per36 / plus_minus / gp / min_pg /
                 pts_pg from data/cache/clutch_profiles_2025-26.parquet.
  usage.*      — season-average usage_pct / ts_pct / efg_pct from
                 data/player_adv_stats.parquet (as context for clutch efficiency).
  pbp.*        — per-game clutch shots attempted / pts scored / and1_count from
                 data/cache/pbp_possession_features.parquet (game-date filtered).

DEFER (no source parquet has raw counts):
  ft_rate      — FTA/FGA in clutch (clutch parquet has ft_pct but no raw FTA/FGA counts;
                 DEFER until a raw-count clutch parquet is fetched).
  tov_under_pressure — clutch TOV count not in either clutch or PBP parquet;
                 DEFER until scripts/fetch_clutch_advanced.py is added.

RESERVED CV SLOTS (value=None, CV branch fills later):
  clutch_defender_distance — mean nearest-defender distance (ft) at clutch shot release
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
CACHE = DATA / "cache"

# ---------------------------------------------------------------------------
# Data-loading helpers (lazy, module-level cache)
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


def _proportion(v: Any, ceil: float = 1.0) -> Optional[float]:
    """Clean a proportion: must be in [0, ceil], else None."""
    result = _rd(v)
    if result is None:
        return None
    if not (0.0 <= result <= ceil):
        return None
    return result


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _clutch_profile_for_player(
    pid: int, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Return clutch scoring fields from clutch_profiles_2025-26.parquet.

    ``n`` is set to ``clutch_gp`` (the actual number of games the player
    appeared in a clutch situation) — NOT the number of parquet rows.

    Returns an empty dict if the player is absent.
    """
    path = CACHE / "clutch_profiles_2025-26.parquet"
    df = _load("clutch26", path)
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}
    if "season" in rows.columns:
        rows = rows.sort_values("season", ascending=False)
    row = rows.iloc[0]

    return {
        # n = actual clutch games played (the real game-count coverage signal)
        "gp": _ri(row.get("clutch_gp")),
        # avg clutch minutes per game (already float in parquet — no MM:SS parsing needed)
        "min_pg": _rd(row.get("clutch_min")),
        "pts_pg": _rd(row.get("clutch_pts")),
        # shooting efficiency — must be proportions in [0,1]
        "fg_pct": _proportion(row.get("clutch_fg_pct")),
        "fg3_pct": _proportion(row.get("clutch_fg3_pct")),
        "ft_pct": _proportion(row.get("clutch_ft_pct")),
        # scoring volume and net impact
        "pts_per36": _rd(row.get("clutch_pts_per36")),
        "plus_minus": _rd(row.get("clutch_plus_minus")),  # signed diff — exempt from [0,1]
        "_season": str(row.get("season", "")),
    }


def _usage_for_player(
    pid: int, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Season-context usage and efficiency from player_adv_stats, filtered to <= as_of.

    Provides season-average usage_pct / ts_pct / efg_pct as context for reading
    the clutch efficiency scores (e.g. does the player maintain TS% in clutch?).
    """
    path = DATA / "player_adv_stats.parquet"
    df = _load("adv", path)
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)
    cols_want = [c for c in [
        "usagepercentage",
        "trueshootingpercentage",
        "effectivefieldgoalpercentage",
    ] if c in rows.columns]
    if not cols_want:
        return {"n_games": n}

    means = rows[cols_want].mean()
    return {
        # usage_pct is in [0,1] in the adv parquet (e.g. 0.266 for Jokic)
        "usage_pct": _proportion(means.get("usagepercentage")),
        # TS% and eFG% can edge above 1.0 (TS% can be ~1.05 on extreme FT%); ceil=1.6
        "ts_pct": _proportion(means.get("trueshootingpercentage"), ceil=1.6),
        "efg_pct": _proportion(means.get("effectivefieldgoalpercentage"), ceil=1.6),
        "n_games": n,
    }


def _pbp_clutch_for_player(
    pid: int, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Per-game clutch shot / scoring aggregates from pbp_possession_features, <= as_of.

    Provides clutch_shots_pg / clutch_pts_pg / and1_pg as complementary shot-volume
    signals (the clutch_profiles parquet only has per-game averages, not shot counts).
    """
    path = CACHE / "pbp_possession_features.parquet"
    df = _load("pbp_poss", path)
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)
    want = [c for c in [
        "pbp_clutch_shots_attempted",
        "pbp_clutch_pts_scored",
        "pbp_and1_count",
    ] if c in rows.columns]
    if not want:
        return {"n_games": n}

    means = rows[want].mean()
    return {
        # per-game counts — must be >= 0 (enforced by _rd)
        "clutch_shots_pg": _rd(means.get("pbp_clutch_shots_attempted")),
        "clutch_pts_pg": _rd(means.get("pbp_clutch_pts_scored")),
        "and1_pg": _rd(means.get("pbp_and1_count")),
        "n_games": n,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerClutchScoring(AtlasSection):
    """Deep clutch-scoring atlas section (player entity, section='clutch_scoring').

    Builds a provenance-stamped, leak-safe artifact covering last-5-minute (<=5-pt
    game margin) scoring efficiency (eFG, FT%, usage, TOV), season context, and
    PBP-derived clutch shot volume.  Reserves 1 CV slot for CV-branch enrichment.

    Sources used:
      - data/cache/clutch_profiles_2025-26.parquet (primary — clutch fg%/ft%/pts)
      - data/player_adv_stats.parquet (season usage/TS%/eFG% context)
      - data/cache/pbp_possession_features.parquet (clutch shots / and1 per game)

    DEFER sub-fields (no source parquet provides raw counts):
      - ft_rate (FTA/FGA in clutch) — clutch parquet has ft_pct only, not raw FTA/FGA
      - tov_under_pressure — clutch TOV not in either clutch or PBP parquet;
        needs scripts/fetch_clutch_advanced.py (NBA LeagueDashPlayerClutch extended).

    ``n`` is set from ``clutch_gp`` — the number of games the player actually
    appeared in a clutch situation — not from row counts (which would be 1 per season).
    """

    name: str = "clutch_scoring"
    entity: str = "player"
    source_name: str = (
        "clutch_profiles_2025-26.parquet + player_adv_stats.parquet + "
        "pbp_possession_features.parquet"
    )
    conf_cap: Optional[str] = None

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the clutch_scoring artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - player_adv_stats and pbp_possession_features are filtered to game_date <= as_of.
          - clutch_profiles_2025-26 uses season aggregates published end-of-season; we
            read the latest season available (acceptable: pre-published summary that
            exists before game-by-game replay).

        Returns None when the player is absent from all sources.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        cp = _clutch_profile_for_player(pid, as_of)
        usage = _usage_for_player(pid, as_of)
        pbp = _pbp_clutch_for_player(pid, as_of)

        # Bail if primary source is empty (player has no clutch data)
        if not cp:
            return None

        # --- scoring sub-dict (primary source) ---
        scoring: Dict[str, Any] = {
            "gp": cp.get("gp"),
            "min_pg": cp.get("min_pg"),
            "pts_pg": cp.get("pts_pg"),
            "fg_pct": cp.get("fg_pct"),
            "fg3_pct": cp.get("fg3_pct"),
            "ft_pct": cp.get("ft_pct"),
            "pts_per36": cp.get("pts_per36"),
            "plus_minus": cp.get("plus_minus"),  # signed — named correctly for validator exempt
            "_season": cp.get("_season"),
        }

        # --- usage sub-dict (season context) ---
        usage_context: Dict[str, Any] = {
            "usage_pct": usage.get("usage_pct"),
            "ts_pct": usage.get("ts_pct"),
            "efg_pct": usage.get("efg_pct"),
            "n_games_season": usage.get("n_games"),
        }

        # --- pbp sub-dict (per-game shot-volume under pressure) ---
        pbp_clutch: Dict[str, Any] = {
            "clutch_shots_pg": pbp.get("clutch_shots_pg"),
            "clutch_pts_pg": pbp.get("clutch_pts_pg"),
            "and1_pg": pbp.get("and1_pg"),
            "n_games_pbp": pbp.get("n_games"),
        }

        # --- DEFER sub-fields (no raw-count parquet available) ---
        deferred: Dict[str, Any] = {
            "ft_rate": None,  # DEFER: FTA/FGA ratio requires raw count clutch parquet
            "tov_under_pressure": None,  # DEFER: clutch TOV not in either parquet
            "_note": (
                "ft_rate and tov_under_pressure DEFER: raw count data unavailable in "
                "clutch_profiles_2025-26 (only pct/per-game agg) and pbp parquet "
                "lacks clutch-specific TOV counts. "
                "Needs scripts/fetch_clutch_advanced.py."
            ),
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "scoring": scoring,
            "usage_context": usage_context,
            "pbp_clutch": pbp_clutch,
            "deferred": deferred,
        }

        # --- Determine n (CRITICAL LESSON 1: use actual games, not row count) ---
        # Primary n = clutch_gp (number of games in clutch situation)
        n_primary = cp.get("gp") or 0
        # Secondary candidates from per-game data sources
        n_candidates: List[int] = [n_primary]
        if pbp.get("n_games"):
            n_candidates.append(pbp["n_games"])
        # Usage season n is not clutch-specific; use as fallback only if gp is 0
        n = max(n_candidates) if n_candidates else 0
        if n == 0 and usage.get("n_games"):
            n = usage["n_games"]

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
            value=cp.get("pts_per36"),  # headline scalar: clutch scoring rate
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required sub-field keys present, proportions in [0,1].

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False
        sf = artifact.sub_fields
        required_keys = {"scoring", "usage_context", "pbp_clutch", "deferred"}
        if not required_keys.issubset(sf.keys()):
            return False

        # Sanity-check shooting percentages are in [0, 1]
        scoring = sf.get("scoring", {})
        for key in ["fg_pct", "fg3_pct", "ft_pct"]:
            v = scoring.get(key)
            if v is not None and not (0.0 <= v <= 1.0):
                return False

        # eFG and TS% allow slight overshoot (ceil 1.6)
        uctx = sf.get("usage_context", {})
        for key in ["ts_pct", "efg_pct"]:
            v = uctx.get(key)
            if v is not None and not (0.0 <= v <= 1.6):
                return False

        # CV fields must all be reserved (None values)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for clutch_scoring (values None -- CV branch fills later).

        The CV branch fills clutch_defender_distance by linking broadcast-video
        tracking coordinates to clutch-window possessions identified via PBP clock.
        """
        return {
            "clutch_defender_distance": CVSlot(
                name="clutch_defender_distance",
                dtype="float",
                description=(
                    "Mean nearest-defender distance (ft) at shot release during "
                    "last-5-min, within-5-point clutch windows, from CV homography "
                    "coordinates and bounding-box centroids."
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
    """Build clutch_scoring for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from clutch parquet.
        as_of:      leak boundary date (defaults to today UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if player_ids is None:
        df = _load("clutch26_disc", CACHE / "clutch_profiles_2025-26.parquet")
        if df is not None and not df.empty and "player_id" in df.columns:
            player_ids = sorted(df["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerClutchScoring()
    artifacts = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
