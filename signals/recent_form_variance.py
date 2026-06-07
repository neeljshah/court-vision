"""signals/recent_form_variance.py — Recent-form CV predicts residual variance (ARM-A).

Basketball hypothesis
---------------------
A player's computer-vision behavioral consistency score predicts the WIDTH of their
stat distribution (abs(residual) = how far the actual stat deviates from the model
prediction), NOT the point estimate.  Highly consistent CV behaviour (low CV
coefficient-of-variation across tracked games) signals a "narrow" player whose
interval should be tight and Kelly stake should be full; volatile CV behaviour
signals a "wide" player where the interval should be inflated and Kelly should be
reduced.

Per memory/MEMORY.md feedback note [Consistency-CV = orthogonal interval signal]:
  - player CV prior predicts |residual| (rel-err corr +0.41, 3.4x across quartiles,
    survives usage tiers) — VALIDATED.
  - Wire prop_confidence into CI width + Kelly, NOT the point model.
  - This signal has target="sigma", scope="both".

Signal contract
---------------
  name    = "recent_form_variance"
  target  = "sigma"
  scope   = "both"
  emits   = ["sigma_mult", "cv_consistency_z", "coverage_weight"]

Sub-features:

  sigma_mult       float >= 0.5.  Multiplier on the base prediction interval
                   sigma.  Values >1 widen the CI; <1 narrow it.  Derived from
                   per_player_confidence.parquet ``<stat>_confidence_mult`` (or
                   ``overall_confidence_mult`` when stat is unknown).  Shrunk
                   toward 1.0 when CV coverage is low.

  cv_consistency_z float.  Standardised CV consistency z-score from
                   cv_consistency_kelly.parquet ``cv_consistency_z``.  Positive
                   z = more consistent than league average (narrow interval OK);
                   negative z = more volatile (widen interval).  Returns 0.0
                   (neutral) when coverage is absent.

  coverage_weight  float in [0, 1].  Fraction of evidence weight placed on CV
                   (vs league prior).  Derived from ``n_cv_games_in_window``
                   (n=1 → 0.2, n=3 → 0.5, n>=7 → 1.0).  Gate uses this to
                   discount the signal when CV games are sparse.

Data sources (leak-safe)
------------------------
PRIMARY (REAL):
  ``data/intelligence/per_player_confidence.parquet``
  Grain: (player_id) — season-level.  Cols: player_id, n_cv_games, pts_cv,
  pts_confidence_mult, reb_cv, reb_confidence_mult, ast_cv, ast_confidence_mult,
  fg3m_cv, fg3m_confidence_mult, stl_cv, stl_confidence_mult, blk_cv,
  blk_confidence_mult, tov_cv, tov_confidence_mult, overall_confidence_mult.
  Source: 112 rows as of 2026-05-30.
  Leak guard: no game_date column (season-level atlas); treated as pregame prior.

SECONDARY (REAL):
  ``data/intelligence/cv_consistency_kelly.parquet``
  Grain: (player_id, asof_date).  Cols: player_id, asof_date,
  n_cv_games_in_window, cv_consistency_z, cv_consistency_mult, plus per-dim CVs.
  Source: 145 rows.
  Leak guard: filtered to asof_date < ctx.decision_time (strict <).

TERTIARY — atlas store (REAL):
  Reads ``prop_calibration`` atlas section via self.read_atlas for per-stat MAE and
  interval_coverage, enabling the multiplier to correct for per-player interval
  under-coverage (spec_intel_memory 1.5 / MEMORY.md feedback on sigma too tight).

DEFER conditions
----------------
  DEFER-1: per_player_confidence.parquet has only 112 players (CV-coverage-bound).
           The signal degrades gracefully to sigma_mult=1.0, cv_consistency_z=0.0
           (neutral) for uncovered players — they are still valid training rows;
           the gate should evaluate whether this sparse coverage is sufficient.

  DEFER-2: cv_consistency_kelly.parquet is sparse (145 rows, 3+ game window).
           Players with fewer CV games than the window size will return z=0.0
           and coverage_weight will be low (<=0.5).

  DEFER-3: The signal does not yet attempt to predict per-STAT interval widths
           separately for pts/reb/ast from first principles.  It uses the
           <stat>_confidence_mult from per_player_confidence if available; otherwise
           falls back to overall_confidence_mult.  A per-stat decomposition (using
           count_distributions.dispersion + interval_sigma_recommendation.json)
           is a natural follow-on and should be queued as a SHIP upgrade.

Gate expectations
-----------------
  VARIANCE_ONLY (expected).  The hypothesis is explicitly that CV consistency
  predicts |residual| but NOT the point estimate; the gate should confirm that
  adding sigma_mult to the CI path improves calibration (interval_coverage closer
  to 0.90 nominal) without improving MAE.  If sigma_mult also improves MAE,
  upgrade to SHIP (unlikely given the validated orthogonality).

  Calibration gate: interval_coverage should move from ~0.76–0.85 observed
  (prop_calibration_history shows several players significantly below 0.90 nominal)
  toward nominal for high-CV players widened and low-CV players narrowed.
"""
from __future__ import annotations

import datetime as _dt
import math
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.loop.signal import (
    SCOPES, TARGETS, AsOfContext, Hypothesis, Signal, SignalValue, Verdict,
)

# ---------------------------------------------------------------------------
# Paths (script-relative ROOT — portable to RunPod Linux)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_PER_PLAYER_CONF_PATH = _ROOT / "data" / "intelligence" / "per_player_confidence.parquet"
_CV_CONSISTENCY_PATH = _ROOT / "data" / "intelligence" / "cv_consistency_kelly.parquet"

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

# Shrinkage: coverage_weight controls how much we trust CV vs the league prior (1.0).
# Interpolated from n_cv_games_in_window: [1 -> 0.20, 3 -> 0.50, 7 -> 1.00].
_COV_ANCHORS = [(1, 0.20), (3, 0.50), (7, 1.00)]

# Minimum and maximum allowed sigma multiplier (safety clamp).
_SIGMA_MULT_MIN = 0.50
_SIGMA_MULT_MAX = 2.50

# Stat column name map: signal target stat -> per_player_confidence column prefix.
_STAT_CONF_COL: Dict[str, str] = {
    "pts":  "pts",
    "reb":  "reb",
    "ast":  "ast",
    "fg3m": "fg3m",
    "stl":  "stl",
    "blk":  "blk",
    "tov":  "tov",
}

# ---------------------------------------------------------------------------
# Module-level lazy caches (avoids re-reading parquets on every call)
# ---------------------------------------------------------------------------

_conf_cache: Optional[pd.DataFrame] = None
_consistency_cache: Optional[pd.DataFrame] = None


def _load_per_player_confidence() -> pd.DataFrame:
    """Lazy-load per_player_confidence.parquet (112 rows, season-level)."""
    global _conf_cache
    if _conf_cache is None:
        try:
            _conf_cache = pd.read_parquet(_PER_PLAYER_CONF_PATH)
        except Exception as exc:
            warnings.warn(
                f"recent_form_variance: cannot load per_player_confidence.parquet: {exc}"
            )
            _conf_cache = pd.DataFrame()
    return _conf_cache


def _load_cv_consistency() -> pd.DataFrame:
    """Lazy-load cv_consistency_kelly.parquet (145 rows, (player_id, asof_date))."""
    global _consistency_cache
    if _consistency_cache is None:
        try:
            df = pd.read_parquet(_CV_CONSISTENCY_PATH)
            df["asof_date"] = pd.to_datetime(df["asof_date"]).dt.date
            _consistency_cache = df
        except Exception as exc:
            warnings.warn(
                f"recent_form_variance: cannot load cv_consistency_kelly.parquet: {exc}"
            )
            _consistency_cache = pd.DataFrame()
    return _consistency_cache


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def _coverage_weight_from_n(n_cv_games: int) -> float:
    """Interpolate coverage weight in [0, 1] from n_cv_games_in_window.

    Uses piecewise-linear interpolation over _COV_ANCHORS.  Returns 0.0 when
    n_cv_games is 0.

    Args:
        n_cv_games: number of CV games in the rolling window.

    Returns:
        Weight in [0.0, 1.0].
    """
    if n_cv_games <= 0:
        return 0.0
    # Below first anchor: linear from 0 to anchor[0]
    x0, y0 = 0, 0.0
    for x1, y1 in _COV_ANCHORS:
        if n_cv_games <= x1:
            # Piecewise-linear interpolation
            frac = (n_cv_games - x0) / max(x1 - x0, 1)
            return float(y0 + frac * (y1 - y0))
        x0, y0 = x1, y1
    # Above last anchor: clamp to 1.0
    return 1.0


def _shrink_to_league_prior(mult: float, coverage_weight: float) -> float:
    """Shrink a per-player confidence multiplier toward 1.0 (league prior).

    Shrinkage = coverage_weight * mult + (1 - coverage_weight) * 1.0.
    At coverage_weight=0: returns 1.0 (pure prior).
    At coverage_weight=1: returns mult unchanged.

    Args:
        mult:             raw per-player sigma multiplier.
        coverage_weight:  fraction of weight on the player estimate.

    Returns:
        Shrunk multiplier, clamped to [_SIGMA_MULT_MIN, _SIGMA_MULT_MAX].
    """
    shrunk = coverage_weight * mult + (1.0 - coverage_weight) * 1.0
    return float(max(_SIGMA_MULT_MIN, min(_SIGMA_MULT_MAX, shrunk)))


# ---------------------------------------------------------------------------
# Signal implementation
# ---------------------------------------------------------------------------

class RecentFormVariance(Signal):
    """CV-consistency as a predictor of residual variance (interval width signal).

    Reads:
      - per_player_confidence.parquet: per-player, per-stat sigma multipliers
        derived from CV coefficient-of-variation analysis.
      - cv_consistency_kelly.parquet: rolling CV consistency z-score per player,
        filtered leak-safe to asof_date < ctx.decision_time.
      - prop_calibration atlas section from the store: per-player interval
        under-coverage check (reinforcement loop feedback).

    Emits: sigma_mult, cv_consistency_z, coverage_weight.

    Returns None only when player_id is not provided — the signal is always
    evaluable pregame (uses season-level priors) and live (same priors; no live
    branch needed since the variance prior is pregame-only).
    """

    name: str = "recent_form_variance"
    target: str = "sigma"
    scope: str = "both"
    reads_atlas: List[str] = ["prop_calibration", "interval_calibration", "cv_bonus"]
    emits: List[str] = ["sigma_mult", "cv_consistency_z", "coverage_weight"]

    # ---- build ---------------------------------------------------------------

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute leak-safe CV-consistency variance features for one decision.

        All parquet reads are either season-level (no date column, treated as
        a pregame prior) or filtered to asof_date < ctx.decision_time.
        The atlas store read uses as_of=ctx.decision_time (enforced by the
        store's leak-safe read contract).

        Args:
            ctx: decision context.  player_id must be set; stat can be derived
                 from ctx.extra.get("stat") if available.

        Returns:
            Dict with keys sigma_mult, cv_consistency_z, coverage_weight; or
            None if player_id is missing.
        """
        if ctx.player_id is None:
            return None

        stat: Optional[str] = ctx.extra.get("stat") if ctx.extra else None

        # ---- 1. Per-player confidence multiplier (primary source) ------------
        sigma_mult_raw, n_cv_games_conf = self._confidence_mult_from_parquet(
            ctx.player_id, stat
        )

        # ---- 2. CV consistency z-score (secondary source, leak-safe) ---------
        cv_z, n_cv_games_consistency = self._consistency_z_from_parquet(
            ctx.player_id, ctx.decision_time
        )

        # ---- 3. Coverage weight (from the richer of the two sources) ---------
        n_cv_best = max(n_cv_games_conf, n_cv_games_consistency)
        coverage_weight = _coverage_weight_from_n(n_cv_best)

        # ---- 4. Reinforcement: adjust for per-player interval under-coverage --
        sigma_mult_raw = self._adjust_for_interval_coverage(
            ctx, stat, sigma_mult_raw
        )

        # ---- 5. Shrink toward league prior (1.0) by coverage weight ----------
        sigma_mult = _shrink_to_league_prior(sigma_mult_raw, coverage_weight)

        return {
            "sigma_mult": sigma_mult,
            "cv_consistency_z": cv_z,
            "coverage_weight": coverage_weight,
        }

    # ---- hypothesis ----------------------------------------------------------

    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "A player's CV behavioral consistency (coefficient-of-variation "
                "across tracked games) predicts the absolute residual |actual - pred| "
                "and therefore the appropriate CI width and Kelly stake — NOT the point "
                "estimate.  High CV consistency → narrow interval (full Kelly); "
                "low CV consistency → wide interval (reduced Kelly).  "
                "This is an orthogonal interval/variance signal, not a point-estimate "
                "signal, and should resolve VARIANCE_ONLY."
            ),
            rationale=(
                "Validated finding in memory (feedback_consistency_cv_orthogonal_interval_signal): "
                "player CV prior predicts |residual| (rel-err corr +0.41, 3.4x across "
                "quartiles, survives usage tiers) but NOT the point estimate.  "
                "prop_calibration_history.parquet confirms that several players have "
                "interval_coverage well below the 0.90 nominal (SGA: 0.85 pts, 0.77 reb), "
                "while highly consistent CV players over-cover.  Wiring sigma_mult into "
                "the CI path (not the point model) corrects per-player heteroscedasticity "
                "without touching the mean prediction, matching the validated orthogonality."
            ),
            source="seed",
            atlas_fields=["prop_calibration", "interval_calibration", "cv_bonus"],
            expected_verdict=Verdict.VARIANCE_ONLY,
            priority="P1",
        )

    # ---- private helpers -----------------------------------------------------

    def _confidence_mult_from_parquet(
        self, player_id: int, stat: Optional[str]
    ) -> tuple:
        """Read sigma multiplier from per_player_confidence.parquet.

        Returns (mult, n_cv_games).  Neutral (1.0, 0) when player absent.

        Args:
            player_id: NBA player id.
            stat:      stat name (pts/reb/ast/...) or None for overall.

        Returns:
            Tuple (sigma_mult_raw: float, n_cv_games: int).
        """
        df = _load_per_player_confidence()
        if df.empty:
            return 1.0, 0

        try:
            row_mask = df["player_id"] == player_id
            rows = df[row_mask]
            if rows.empty:
                return 1.0, 0

            row = rows.iloc[0]
            n_cv = int(row.get("n_cv_games", 0) or 0)

            # Prefer per-stat multiplier when stat is known and column exists
            mult_col = None
            if stat and stat in _STAT_CONF_COL:
                candidate = f"{_STAT_CONF_COL[stat]}_confidence_mult"
                if candidate in row.index:
                    mult_col = candidate

            if mult_col is None:
                mult_col = "overall_confidence_mult"

            raw = row.get(mult_col)
            if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                return 1.0, n_cv

            return float(raw), n_cv

        except Exception:
            return 1.0, 0

    def _consistency_z_from_parquet(
        self, player_id: int, decision_time: _dt.datetime
    ) -> tuple:
        """Read cv_consistency_z from cv_consistency_kelly.parquet (leak-safe).

        Filters rows to asof_date < decision_time (strictly before the decision
        date) and takes the most recent row.

        Returns (cv_consistency_z: float, n_cv_games: int).  Neutral (0.0, 0)
        when player absent or no rows predate decision_time.

        Args:
            player_id:     NBA player id.
            decision_time: as-of datetime (leak boundary).

        Returns:
            Tuple (z: float, n_cv_games: int).
        """
        df = _load_cv_consistency()
        if df.empty:
            return 0.0, 0

        try:
            cutoff = decision_time.date()  # strict < filter
            mask = (df["player_id"] == player_id) & (df["asof_date"] < cutoff)
            rows = df[mask].sort_values("asof_date")
            if rows.empty:
                return 0.0, 0

            latest = rows.iloc[-1]
            z_raw = latest.get("cv_consistency_z")
            n_cv = int(latest.get("n_cv_games_in_window", 0) or 0)

            if z_raw is None or (isinstance(z_raw, float) and math.isnan(z_raw)):
                # cv_consistency_z can be NaN for players with n_cv_games < 5
                # Fall back to cv_consistency_mult direction (>1 = more consistent)
                mult_raw = latest.get("cv_consistency_mult")
                if mult_raw is not None and not (isinstance(mult_raw, float) and math.isnan(mult_raw)):
                    # Translate mult to approximate z-score direction (mult~1 -> z~0)
                    z_raw = float(mult_raw) - 1.0
                else:
                    return 0.0, n_cv

            return float(z_raw), n_cv

        except Exception:
            return 0.0, 0

    def _adjust_for_interval_coverage(
        self,
        ctx: AsOfContext,
        stat: Optional[str],
        sigma_mult: float,
    ) -> float:
        """Adjust sigma_mult upward when the player chronically under-covers.

        Reads prop_calibration atlas section from the store to find
        interval_coverage vs interval_nominal.  If the player's coverage is
        materially below nominal (e.g. 0.77 vs 0.90), inflate sigma_mult
        by the coverage-deficit ratio.  This is the reinforcement path:
        the atlas carries prop_calibration_history data built into profiles.

        Args:
            ctx:        decision context.
            stat:       stat name or None.
            sigma_mult: current raw sigma_mult from CV source.

        Returns:
            Adjusted sigma_mult (same or higher; never lower via this path).
        """
        if self.store is None or ctx.player_id is None:
            return sigma_mult

        try:
            atlas = self.read_atlas(
                f"player:{ctx.player_id}", "prop_calibration", ctx.decision_time
            )
            if atlas is None or not isinstance(atlas, dict):
                return sigma_mult

            # stat-specific or first available
            stat_data: Optional[dict] = None
            if stat and stat in atlas:
                stat_data = atlas[stat]
            elif atlas:
                # Use the first stat with coverage data as a fallback
                for v in atlas.values():
                    if isinstance(v, dict) and "interval_coverage" in v:
                        stat_data = v
                        break

            if stat_data is None:
                return sigma_mult

            cov_obs = stat_data.get("interval_coverage")
            cov_nom = stat_data.get("interval_nominal", 0.90)

            if cov_obs is None or math.isnan(float(cov_obs)):
                return sigma_mult

            cov_obs = float(cov_obs)
            cov_nom = float(cov_nom)

            # Inflate proportionally: if coverage is 0.77 vs 0.90, multiply by
            # (0.90/0.77) ~ 1.17 to widen the interval enough to close the gap.
            # Only inflate (never deflate via this path — the CV multiplier handles that).
            if cov_obs < cov_nom * 0.97 and cov_obs > 0.0:
                inflation = cov_nom / cov_obs
                sigma_mult = max(sigma_mult, sigma_mult * inflation)

        except Exception:
            pass  # always degrade gracefully

        return sigma_mult
