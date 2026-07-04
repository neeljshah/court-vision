"""domains.basketball_wnba.ingame_blend -- WNBA-local in-game win-prob blend.

WNBA in-game live blend, deferred from Wave 1 (see adapter.py docstring): NBA's
domains/basketball_nba/ingame_blend_plive.py hardcodes _REG_SEC=2880.0 (4x12min)
and consumes a live PBP foul-state feed (players dict -> per-player personal
fouls) that WNBA has no ingest for. Rather than faking that feed or silently
reusing the NBA clock constant, this module RE-DERIVES the time-scale-dependent
constant (regulation = 2400s, 4x10min) and DEGRADES the foul-state term out
cleanly (it is simply absent from the feature set here -- not zero-filled, not
approximated).

FUNCTIONAL FAMILY (deliberately the SAME shape the NBA blend/repricer family
uses, ported at the transparent-formula level rather than reusing NBA's fitted
ML artifact, since fit_plive/predict_plive in ingame_blend_plive.py is trained
on the NBA foul/bonus feature row this domain does not have):

    p_live = sigmoid( logit(p0) * w_prior(t)  +  k * score_diff * ramp(t) )

  - w_prior(t) in [0, 1]: weight kept on the pregame prior as time elapses.
    w_prior(t) = 1 - fraction_elapsed(t) -- the prior's influence LINEARLY
    decays to 0 at the final buzzer (mirrors the "early trust prior, late trust
    score" freshness ramp documented in scripts/platformkit/ingame/mlb_live_model.py,
    re-derived here as a closed-form linear ramp rather than the MLB module's
    4-bucket step function, since WNBA has no per-file bucket calibration yet).
  - score_diff * ramp(t): the realized-state term. ramp(t) = fraction_elapsed(t)
    / max(sec_remaining, floor) -- same "time_pressure" shape as NBA's
    ingame_blend_plive.build_state_features (score_diff scaled by inverse time
    remaining, floor-clamped so it never blows up near the buzzer); k is a fixed
    points-to-logits scale (see K_SCORE below), NOT fit on a live corpus (no
    leak-free live corpus exists yet for WNBA -- see calibration check step 4).
  - AT t=0 (tipoff): ramp(0)=0, w_prior(0)=1 -> p_live == p0 exactly (recovers
    the pregame Elo probability, the p0-recovery invariant tested below).
  - AT t=T (buzzer): if the game is DECIDED (score_diff != 0), p_live snaps to
    the EXACT 0.0/1.0 (see predict_live's buzzer clamp -- same class of fix as
    domains/basketball_nba/test_nba_live_buzzer.py) rather than reporting a
    near-1 sigmoid value.

NO foul-state term: WNBA has no live per-player foul feed. The NBA feature
`foul_diff`/`bonus` terms are DROPPED (not zero-filled -- they never enter the
formula), which is the honest degrade requested rather than a silent fake.

EDGE_CLAIMED = False. Calibration/coherence only -- see ingame_blend_check.json
(built by run_ingame_blend_check.py) for the honest small-n calibration read.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

EDGE_CLAIMED = False

# WNBA regulation: 4 x 10-minute quarters (vs NBA's 4x12=2880s). OT periods are
# 5 minutes (300s) each, same convention NBA uses for its OT periods.
REG_SEC: float = 2400.0
PERIOD_SEC: float = 600.0
OT_SEC: float = 300.0

# Points-to-logits scale for the realized-score term. Kept a fixed, documented
# constant (not fit on a live corpus -- WNBA has none yet) chosen so a 10-point
# lead with ~1 quarter (600s) remaining moves the blended probability sharply
# away from 0.5 without swamping the pregame prior at tip-off-adjacent states.
K_SCORE: float = 3.0

# Floor on sec_remaining used only inside the ramp's inverse-time term, so the
# realized-score contribution never diverges as sec_remaining -> 0 (mirrors
# NBA's build_state_features time_pressure 30s floor, scaled here to WNBA's
# shorter period length: 30 * (PERIOD_SEC/720) = 25s).
_TIME_FLOOR_SEC: float = 25.0


def sec_remaining(period: int, clock_s: float) -> float:
    """Seconds left in regulation/OT. period is 1-based; clock_s = seconds left
    in the CURRENT period. Regulation periods 1-4 (WNBA quarters); period >= 5
    is OT and returns clock_s directly (matches NBA's ingame_blend_plive
    convention, OT-length-agnostic by design). Never negative."""
    period = int(period)
    clock_s = float(clock_s)
    if period >= 5:
        return max(0.0, clock_s)
    return max(0.0, PERIOD_SEC * (4 - period) + clock_s)


def fraction_elapsed(period: int, clock_s: float) -> float:
    """Fraction of REGULATION elapsed, clamped to [0, 1]. OT periods (period>=5)
    report 1.0 (regulation is fully elapsed once OT starts); this is the ramp
    input, not a literal game-clock fraction, so OT correctly maxes out the
    realized-score term's weight and fully decays the pregame prior."""
    if int(period) >= 5:
        return 1.0
    sr = sec_remaining(period, clock_s)
    return float(min(1.0, max(0.0, 1.0 - sr / REG_SEC)))


def _logit(p: float) -> float:
    pc = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(pc / (1.0 - pc))


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


@dataclass
class LiveState:
    """One normalized WNBA live snapshot. period 1-based (1-4 regulation, >=5
    OT); clock_s = seconds REMAINING in the current period. No foul/bonus
    fields -- WNBA has no live per-player foul-state feed (see module docstring)."""
    period: int
    clock_s: float
    home_score: float
    away_score: float


def blend_prob(p0: float, state: LiveState) -> float:
    """p_live = sigmoid(logit(p0) * w_prior(t) + K_SCORE * score_diff * ramp(t)).

    Pure function of (p0, state); no I/O, no fitting. p0 is the pregame P(home
    win) (WNBA Elo, the SAME prior WNBAAdapter.baseline_probability reports).
    Monotone increasing in score_diff for fixed t (larger home lead -> higher
    p_live); converges to a determined 0/1 outcome as t->T when score_diff!=0
    (see predict_live's exact buzzer clamp -- this function alone asymptotes
    toward but does not force 0/1, by design a pure continuous blend)."""
    t = fraction_elapsed(state.period, state.clock_s)
    w_prior = 1.0 - t
    score_diff = float(state.home_score) - float(state.away_score)
    sr = sec_remaining(state.period, state.clock_s)
    ramp = t / max(sr, _TIME_FLOOR_SEC)
    z = _logit(p0) * w_prior + K_SCORE * score_diff * ramp
    return _sigmoid(z)


def is_buzzer(state: LiveState) -> bool:
    """True at the exact final buzzer: regulation period (4) with 0s left, and
    NOT tied (a tie at 0s goes to OT -- period advances, so is_buzzer is False
    for a tied 4th-quarter 0:00 state; the caller's period feed handles that)."""
    return int(state.period) == 4 and float(state.clock_s) <= 0.0


__all__ = [
    "REG_SEC", "PERIOD_SEC", "OT_SEC", "K_SCORE",
    "LiveState", "sec_remaining", "fraction_elapsed", "blend_prob", "is_buzzer",
]
