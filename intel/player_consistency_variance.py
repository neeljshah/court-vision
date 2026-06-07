"""ARM-B atlas section: ``consistency_variance`` — per-player stat consistency profiles.

Implements :class:`AtlasSection` for the ``"consistency_variance"`` section of a
player's persistent profile.  This section feeds the interval/uncertainty (CI width
and Kelly sizing) signal validated in memory note
``feedback_consistency_cv_orthogonal_interval_signal.md``.

**Sub-field coverage:**

REAL (populated from ``data/cache/pregame_oof.parquet`` — per-game actual stat values
filtered to ``game_date <= as_of``):
  per_stat.<stat>.n_games         — number of game observations used
  per_stat.<stat>.mean            — season-mean production
  per_stat.<stat>.std             — standard deviation across games
  per_stat.<stat>.cv              — coefficient of variation (std / mean); None if mean=0
  per_stat.<stat>.floor_p10       — 10th-percentile actual (worst-case floor)
  per_stat.<stat>.ceiling_p90     — 90th-percentile actual (best-case ceiling)
  per_stat.<stat>.floor_p25       — 25th-percentile (soft floor)
  per_stat.<stat>.ceiling_p75     — 75th-percentile (soft ceiling)
  per_stat.<stat>.boom_rate       — fraction of games >= 1.5 × mean (boom games)
  per_stat.<stat>.bust_rate       — fraction of games <= 0.5 × mean (bust games)
  per_stat.<stat>.iqr             — interquartile range (p75 - p25)
  per_stat.<stat>.median          — 50th-percentile actual
  headline.most_consistent_stat   — stat with lowest CV (most reliable bet)
  headline.least_consistent_stat  — stat with highest CV (most volatile)
  headline.composite_cv           — mean CV across all stats (overall consistency index)

REAL (populated from ``data/cache/prop_calibration_history.parquet`` — model
calibration per-stat; exists for players with >= 5 OOF games):
  calibration.<stat>.mae          — model MAE on this player/stat
  calibration.<stat>.bias         — mean(pred - actual); >0 means model over-predicts
  calibration.<stat>.interval_coverage — empirical 90% CI coverage rate
  calibration.<stat>.n            — calibration observations (same as oof n_games)

DEFER (data gap — not available without a separate join):
  consistency_trend.*             — DEFER: would require rolling L10 / L20 window CVs
                                    across a time axis; the per-game oof parquet has
                                    game_date but building rolling sub-windows per player
                                    is deferred to a dedicated script that streams the
                                    sorted games.
  opponent_adjusted_cv.*          — DEFER: per-opponent matchup CV (e.g. cv vs top-10
                                    defenses) would require merging opponent defensive
                                    ratings by game_id; the join logic is not yet
                                    pre-aggregated in any existing parquet.

RESERVED CV SLOTS (value=None, CV branch fills later):
  cv_shot_quality_cv   — CV of shot-quality-proxy scores across games (measures how
                         consistently the player generates good shots, not just makes)
  cv_velocity_cv       — CV of mean frame-velocity across games (fatigue/effort
                         consistency from the tracking layer)
  cv_spacing_cv        — CV of mean team spacing (floor-spread consistency, game-to-game)
  cv_paint_touches_cv  — CV of paint-touch rate per game (driving consistency indicator)
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

# Stats the section covers — must match pregame_oof 'stat' values
_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Boom/bust thresholds (relative to player mean)
_BOOM_MULT = 1.5  # >= 1.5 × mean → boom game
_BUST_MULT = 0.5  # <= 0.5 × mean → bust game


# ---------------------------------------------------------------------------
# Data-loading helpers (lazy, module-level cache — one read per process)
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
    """Clean integer."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _oof_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, pd.Series]:
    """Return per-stat Series of actual game values for player, filtered to <= as_of.

    Source: ``data/cache/pregame_oof.parquet`` (game_id, player_id, stat, actual,
    game_date, …).  Only rows with game_date <= as_of are returned — LEAK-SAFE.

    Returns:
        Dict mapping stat name → pd.Series of actual values (float).
        Empty dict if player absent or no rows before as_of.
    """
    df = _load("oof", CACHE / "pregame_oof.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Leak filter: only use games that were played before as_of
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    result: Dict[str, pd.Series] = {}
    for stat in _STATS:
        stat_rows = rows[rows["stat"] == stat]["actual"].dropna()
        if not stat_rows.empty:
            result[stat] = stat_rows.reset_index(drop=True)
    return result


def _propcal_for_player(pid: int) -> Dict[str, Any]:
    """Return per-stat calibration dict from prop_calibration_history.parquet.

    Source: ``data/cache/prop_calibration_history.parquet``.
    This parquet contains season-aggregate metrics (not per-game dates), so no
    as_of filter is needed — it reflects OOF metrics up to when it was built,
    which is always <= the build date.

    Returns:
        Dict mapping stat -> {mae, bias, interval_coverage, n}
    """
    df = _load("propcal", CACHE / "prop_calibration_history.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}

    result: Dict[str, Any] = {}
    for _, row in rows.iterrows():
        stat = str(row.get("stat", "")).strip()
        if not stat:
            continue
        result[stat] = {
            "mae": _rd(row.get("mae")),
            "bias": _rd(row.get("bias")),
            "interval_coverage": _rd(row.get("interval_coverage")),
            "n": _ri(row.get("n")),
        }
    return result


def _compute_per_stat_metrics(series: pd.Series) -> Dict[str, Any]:
    """Compute the full consistency/variance profile for one stat's game series.

    Args:
        series: float series of per-game actual values (already as_of-filtered).

    Returns:
        Dict with n_games, mean, std, cv, floor_p10, ceiling_p90, floor_p25,
        ceiling_p75, boom_rate, bust_rate, iqr, median.
    """
    n = len(series)
    if n == 0:
        return {}

    mean = float(series.mean())
    std = float(series.std(ddof=1)) if n > 1 else 0.0
    median = float(series.median())
    p10 = float(series.quantile(0.10))
    p25 = float(series.quantile(0.25))
    p75 = float(series.quantile(0.75))
    p90 = float(series.quantile(0.90))
    iqr = p75 - p25

    # Coefficient of variation: std / mean (dimensionless consistency measure)
    cv = (std / mean) if mean > 0 else None

    # Boom/bust rates (fraction of games at the extremes relative to mean)
    boom_rate = float((series >= _BOOM_MULT * mean).mean()) if mean > 0 else None
    bust_rate = float((series <= _BUST_MULT * mean).mean()) if mean > 0 else None

    return {
        "n_games": n,
        "mean": _rd(mean),
        "std": _rd(std),
        "cv": _rd(cv),
        "floor_p10": _rd(p10),
        "floor_p25": _rd(p25),
        "median": _rd(median),
        "ceiling_p75": _rd(p75),
        "ceiling_p90": _rd(p90),
        "iqr": _rd(iqr),
        "boom_rate": _rd(boom_rate),
        "bust_rate": _rd(bust_rate),
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerConsistencyVariance(AtlasSection):
    """Deep player consistency/variance atlas section (section='consistency_variance').

    Builds a provenance-stamped, leak-safe artifact covering per-stat coefficient
    of variation, floor/ceiling percentiles, and boom/bust rates for all 7 prop
    stats.  This section feeds the interval-width signal (VARIANCE_ONLY validated
    finding: prop_confidence CV prior predicts |residual| with +0.41 correlation,
    3.4x across quartiles — see memory note feedback_consistency_cv_orthogonal_interval_signal).

    Sources used (ALL filtered to game_date <= as_of for leak-safety):
      - data/cache/pregame_oof.parquet — per-game actual stat values (primary)
      - data/cache/prop_calibration_history.parquet — model MAE/bias/interval coverage

    DEFER sections:
      - consistency_trend.*   — rolling L10/L20 CV trend not pre-aggregated
      - opponent_adjusted_cv.* — per-opponent matchup CV requires game_id join

    CV slots reserved (value=None until CV branch fills):
      - cv_shot_quality_cv    — CV of per-game shot-quality-proxy scores
      - cv_velocity_cv        — CV of mean frame-velocity per game
      - cv_spacing_cv         — CV of mean team spacing per game
      - cv_paint_touches_cv   — CV of paint-touch rate per game
    """

    name: str = "consistency_variance"
    entity: str = "player"
    source_name: str = (
        "pregame_oof.parquet + prop_calibration_history.parquet"
    )
    conf_cap: Optional[str] = None  # no hard cap; CV slots capped "med" separately

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the consistency_variance artifact for player ``entity_id``.

        Leak guarantee: ``pregame_oof.parquet`` is filtered to game_date <= as_of;
        ``prop_calibration_history.parquet`` is season-aggregate (no future data).

        Returns None when the player has no OOF data before as_of.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        # --- Primary source: per-game OOF actuals (filtered to <= as_of) ---
        stat_series = _oof_for_player(pid, as_of)
        if not stat_series:
            return None  # player absent or no games before as_of

        # --- Calibration metrics (secondary, not leak-filtered by date) ---
        calibration_raw = _propcal_for_player(pid)

        # --- Compute per-stat consistency metrics ---
        per_stat: Dict[str, Any] = {}
        cv_values: List[float] = []

        for stat in _STATS:
            series = stat_series.get(stat)
            if series is None or len(series) == 0:
                continue
            metrics = _compute_per_stat_metrics(series)
            per_stat[stat] = metrics
            cv = metrics.get("cv")
            if cv is not None:
                cv_values.append(cv)

        if not per_stat:
            return None  # nothing computed

        # --- Headline consistency summary ---
        # Find most/least consistent stats (by CV)
        stat_cvs = {
            s: v["cv"]
            for s, v in per_stat.items()
            if v.get("cv") is not None
        }
        most_consistent = min(stat_cvs, key=stat_cvs.get) if stat_cvs else None
        least_consistent = max(stat_cvs, key=stat_cvs.get) if stat_cvs else None
        composite_cv = _rd(float(np.mean(list(stat_cvs.values()))) if stat_cvs else None)

        headline: Dict[str, Any] = {
            "most_consistent_stat": most_consistent,
            "least_consistent_stat": least_consistent,
            "composite_cv": composite_cv,
        }

        # --- Calibration section (from prop_calibration_history) ---
        calibration: Dict[str, Any] = {}
        for stat in _STATS:
            cal = calibration_raw.get(stat)
            if cal:
                calibration[stat] = cal

        # --- DEFER sections (documented stubs) ---
        consistency_trend: Dict[str, Any] = {
            "_note": (
                "DEFER: rolling L10/L20 per-stat CV trends not pre-aggregated. "
                "Requires sorting games by date per player and computing windowed std/mean. "
                "Will be added via scripts/build_consistency_trend.py."
            )
        }
        opponent_adjusted_cv: Dict[str, Any] = {
            "_note": (
                "DEFER: per-opponent matchup CV (e.g. cv vs top-10 defenses) requires "
                "game_id → opponent defensive_rating join not pre-aggregated in any parquet."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "per_stat": per_stat,
            "headline": headline,
            "calibration": calibration,
            "consistency_trend": consistency_trend,
            "opponent_adjusted_cv": opponent_adjusted_cv,
        }

        # --- Sample size: max n_games across any stat ---
        n = max(
            (v.get("n_games", 0) for v in per_stat.values()),
            default=0,
        )
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
            value=composite_cv,  # headline scalar: overall consistency index
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required sub-field keys present; CV values in range.

        Full leak/coverage/dedup gate lives in ``src.loop.intel_validator``.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "per_stat", "headline", "calibration",
            "consistency_trend", "opponent_adjusted_cv",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Must have at least one stat with real data
        per_stat = sf.get("per_stat", {})
        if not per_stat:
            return False

        # Sanity-check per-stat values
        for stat, metrics in per_stat.items():
            # CV must be non-negative when present
            cv = metrics.get("cv")
            if cv is not None and cv < 0.0:
                return False
            # n_games must be positive
            n = metrics.get("n_games", 0)
            if n < 1:
                return False
            # Floor <= median <= ceiling
            floor_p10 = metrics.get("floor_p10")
            median = metrics.get("median")
            ceiling_p90 = metrics.get("ceiling_p90")
            if all(v is not None for v in [floor_p10, median, ceiling_p90]):
                if not (floor_p10 <= median <= ceiling_p90):
                    return False
            # boom/bust rates in [0, 1]
            for rate_key in ("boom_rate", "bust_rate"):
                r = metrics.get(rate_key)
                if r is not None and not (0.0 <= r <= 1.0):
                    return False

        # Headline composite_cv must be non-negative when present
        composite_cv = sf.get("headline", {}).get("composite_cv")
        if composite_cv is not None and composite_cv < 0.0:
            return False

        # CV fields schema must be present; all values must be None (CV not yet filled)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for consistency_variance (values None until CV fills).

        These four slots capture the behavioral-consistency dimensions that CV tracking
        provides: shot quality, movement effort, spacing, and paint activity — all as
        game-to-game CVs.  The CV branch fills them via
        ``store.fill_cv_slot("player", pid, "consistency_variance", slot, as_of, value)``.
        """
        return {
            "cv_shot_quality_cv": CVSlot(
                name="cv_shot_quality_cv",
                dtype="float",
                description=(
                    "Coefficient of variation of the CV shot-quality-proxy score "
                    "(shot_quality_proxy from feature_engineering.py) across games — "
                    "measures whether the player consistently generates high-quality shots "
                    "or swings wildly based on defensive matchup."
                ),
                unit=None,
                value=None,
            ),
            "cv_velocity_cv": CVSlot(
                name="cv_velocity_cv",
                dtype="float",
                description=(
                    "Coefficient of variation of mean per-frame velocity (ft/s from "
                    "Kalman tracking) across games — proxy for effort/fatigue consistency; "
                    "high CV suggests some games the player coasts, others he runs hard."
                ),
                unit=None,
                value=None,
            ),
            "cv_spacing_cv": CVSlot(
                name="cv_spacing_cv",
                dtype="float",
                description=(
                    "Coefficient of variation of mean team spacing (convex-hull ft² from "
                    "homography coordinates) across games — captures whether the player's "
                    "spacing role is consistent or fluctuates with lineup composition."
                ),
                unit=None,
                value=None,
            ),
            "cv_paint_touches_cv": CVSlot(
                name="cv_paint_touches_cv",
                dtype="float",
                description=(
                    "Coefficient of variation of paint-touch rate (paint_count_own from "
                    "CV possession features) across games — measures how consistently the "
                    "player attacks the paint; high CV = situational paint attacker."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level build-and-register helper (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build consistency_variance for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from pregame_oof.
        as_of:      leak boundary date (defaults to today UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        df = _load("oof_disc", CACHE / "pregame_oof.parquet")
        if df is not None and not df.empty and "player_id" in df.columns:
            player_ids = sorted(df["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerConsistencyVariance()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
