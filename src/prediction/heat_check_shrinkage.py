"""heat_check_shrinkage.py -- cycle 96d (loop 5). Bayesian shrinkage for hot Q3.

Background
----------
Cycle 95b's endQ3 decomposition (scripts/_results/endQ3_decomposition_v1.md)
isolated **heat_check** (Q3 pts/min > 1.5x Q1-Q2 pts/min) as failure mode #2:

  * PTS MAE in stratum = 2.9818 vs 2.4469 global (+0.5349 delta)
  * PTS bias in stratum = +0.7411 (projector OVER-projects; Q3 hot streak gets
    linearly extrapolated to Q4 but mean-reverts instead).

The cycle-88b ``project_snapshot`` projects by per-clock pro-rata of the
cumulative-thru-Q3 totals; when Q3 was a true heat-check the per-clock rate
across Q1+Q2+Q3 is inflated, so the Q4 projection inherits that inflated
rate. Mean reversion is real (defensive adjustments, regression-to-mean of
make rate). This module ships a soft Bayesian shrinkage applied to the
**remaining-stats projection only** (we never alter the already-locked-in
current_stat).

API
---
``heat_check_factor(q3_ppm, q12_ppm, season_ppm, shrinkage_weight=0.20)``
    returns a multiplicative factor in [0.7, 1.0]. Multiply the projector's
    *remaining* projection by this factor; do NOT multiply current_stat.

Rules
-----
    ratio = q3_ppm / max(q12_ppm, 0.01)
    ratio < 1.5            -> 1.0 (no shrinkage; not a heat-check)
    1.5 <= ratio < 2.0     -> 1 - 0.5 * weight * (ratio - 1.5)  (mild)
    ratio >= 2.0           -> 1 - weight * (ratio - 1.5)        (stronger)
    factor floored at 0.7.

``season_ppm`` is accepted for API symmetry with future per-player priors but
is intentionally NOT consulted by the current formula -- the gate is purely
within-game (Q3 vs Q1-Q2). The current-game prior beats season noise for the
mean-reversion gate because heat-check is by definition a within-game burst.

Scope
-----
Only PTS / AST / FG3M are scoring stats that exhibit heat-check dynamics.
The wired-in caller (cycle 96d -- scripts/predict_in_game.project_snapshot)
applies this factor ONLY for those three stats; defensive/turnover stats
(STL / BLK / TOV / REB) pass through unchanged.

See ``tests/test_heat_check_shrinkage.py`` for the 4 boundary tests.
"""
from __future__ import annotations

# Stats that exhibit heat-check (scoring/shot-making bursts that mean-revert).
# Re-exported so the caller (predict_in_game) imports the canonical set.
HEAT_CHECK_STATS = frozenset({"pts", "ast", "fg3m"})

# Shrinkage floor: do not pull the projection below 70% of the unshunken value.
# Cap reflects the empirical bias (+0.74 PTS over-projection in cycle 95b) --
# anything more aggressive than 30% reduction would under-shoot in cases where
# the Q3 burst was genuinely real (high-usage scorer with shot-creation alpha).
_FACTOR_FLOOR = 0.7

# Ratio at which shrinkage starts (matches cycle 95b heat_check definition).
_RATIO_TRIGGER = 1.5

# Ratio at which the gradient steepens (mild->stronger transition).
_RATIO_BREAK = 2.0


def heat_check_factor(
    q3_ppm: float,
    q12_ppm: float,
    season_ppm: float,
    shrinkage_weight: float = 0.20,
) -> float:
    """Return multiplicative factor in [0.7, 1.0] for endQ3 projection.

    When ``q3_ppm >> q12_ppm`` (Q3 hot streak), the cycle-88 projector
    extrapolates the hot rate to Q4 -- but ``q3_ppm > 1.5x q12_ppm`` means
    mean-reversion is likely. Apply soft shrinkage toward the within-game
    pre-Q3 rate by scaling the remaining-stats projection.

    Parameters
    ----------
    q3_ppm : float
        Player's Q3 per-minute stat rate (e.g. PTS / Q3_minutes_played).
    q12_ppm : float
        Player's Q1+Q2 per-minute stat rate (the "non-heat" baseline).
    season_ppm : float
        Player's season-level per-minute prior. Accepted for API symmetry --
        the current formula does NOT consult it (the within-game ratio is
        the stronger signal for a within-game burst). Reserved for future
        per-player calibration.
    shrinkage_weight : float, default 0.20
        Controls the slope of the shrinkage. Selected via the cycle-96d
        probe sweep over {0.10, 0.15, 0.20, 0.25, 0.30}.

    Returns
    -------
    float
        Multiplicative factor in ``[0.7, 1.0]``. Multiply the projector's
        REMAINING-stats projection by this. ``1.0`` means no shrinkage.

    Rules
    -----
    * ``ratio = q3_ppm / max(q12_ppm, 0.01)`` (epsilon prevents div/0 when
      a player scored 0 in Q1+Q2).
    * ``ratio < 1.5``   -> ``1.0`` (no shrinkage; not in heat-check stratum).
    * ``1.5 <= ratio < 2.0`` -> mild: ``1 - 0.5 * weight * (ratio - 1.5)``.
    * ``ratio >= 2.0``  -> stronger: ``1 - weight * (ratio - 1.5)``.
    * Floored at ``0.7`` to cap the absolute shrinkage.

    The function is pure and side-effect free; safe to call in inner loops.
    """
    # Defensive coerce. None / NaN / non-numeric -> 0.0 (which propagates to
    # ratio=0 below threshold -> factor=1.0, i.e. safe no-op).
    try:
        q3 = float(q3_ppm) if q3_ppm is not None else 0.0
    except (TypeError, ValueError):
        q3 = 0.0
    try:
        q12 = float(q12_ppm) if q12_ppm is not None else 0.0
    except (TypeError, ValueError):
        q12 = 0.0
    # season_ppm intentionally read-but-ignored by the current rule -- callers
    # may pass any numeric / None without affecting output (API stability for
    # future per-player calibration).
    _ = season_ppm
    try:
        w = float(shrinkage_weight)
    except (TypeError, ValueError):
        w = 0.20

    # NaN guard (NaN != NaN).
    if q3 != q3:
        q3 = 0.0
    if q12 != q12:
        q12 = 0.0

    if q3 <= 0.0:
        return 1.0

    # Epsilon floor in denominator: a zero-Q12 baseline with positive Q3 yields
    # ratio = q3 / 0.01 = 100, which would hard-clamp to the floor. That is
    # intentional -- a player who scored 0 across all of Q1+Q2 then went off
    # in Q3 is the prototypical mean-reversion candidate.
    ratio = q3 / max(q12, 0.01)

    if ratio < _RATIO_TRIGGER:
        return 1.0

    if ratio < _RATIO_BREAK:
        # Mild slope in [1.5, 2.0): half the gradient of the harder branch.
        factor = 1.0 - 0.5 * w * (ratio - _RATIO_TRIGGER)
    else:
        # Stronger slope at ratio >= 2.0.
        factor = 1.0 - w * (ratio - _RATIO_TRIGGER)

    return max(_FACTOR_FLOOR, factor)


__all__ = ["heat_check_factor", "HEAT_CHECK_STATS"]
