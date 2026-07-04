"""domains.basketball_wnba.ingame_blend -- WNBA-local in-game win-prob blend.

LANE 4 (this wave) SETTLEMENT: wave 2 shipped the FIXED-constant blend below
(now `blend_prob_fixed_legacy`, K_SCORE=3.0, never fit on data) as the adapter
default. The honest wave-2 check (data/domains/wnba/ingame_blend_check.json v1)
showed a naive score-diff sigmoid beats it decisively at half (.1915 vs .2316)
and end_q3 (.1606 vs .2318) on 150 2026 games. domains.basketball_wnba.
ingame_blend_families.py then fit 4 pre-declared candidate families on 2024,
validated on 2025, and OOS-checked on 2026 (see that module's docstring for the
full method + data/domains/wnba/ingame_blend_check.json v2 for the tables).
RESULT: the "anchored" family --

    p_live = sigmoid( logit(p0) * w0 * (1 - t)  +  k * score_diff / sqrt(minutes_remaining) )

-- won EVERY checkpoint (end_q1/half/end_q3) on BOTH 2025 (validate) and 2026
(OOS) independently vs fixed, naive, and time_scaled -- a clean cross-corpus
win, not a tie. Fit on 2024 only: k=0.63, w0=1.0 (frozen constants below,
ANCHORED_K / ANCHORED_W0 -- NOT refit on 2025/2026, per the no-leak contract).
`blend_prob` below is now this anchored family; the OLD fixed-constant formula
is kept importable, unchanged, as `blend_prob_fixed_legacy` for comparison
(ingame_blend_families.predict_fixed calls it directly).

WNBA in-game live blend, deferred from Wave 1 (see adapter.py docstring): NBA's
domains/basketball_nba/ingame_blend_plive.py hardcodes _REG_SEC=2880.0 (4x12min)
and consumes a live PBP foul-state feed (players dict -> per-player personal
fouls) that WNBA has no ingest for. Rather than faking that feed or silently
reusing the NBA clock constant, this module RE-DERIVES the time-scale-dependent
constant (regulation = 2400s, 4x10min) and DEGRADES the foul-state term out
cleanly (it is simply absent from the feature set here -- not zero-filled, not
approximated).

CURRENT DEFAULT FAMILY (anchored, adopted this wave):

    p_live = sigmoid( logit(p0) * w_prior(t)  +  ANCHORED_K * score_diff / sqrt(minutes_remaining(t)) )

  - w_prior(t) = ANCHORED_W0 * (1 - fraction_elapsed(t)): weight kept on the
    pregame prior as time elapses. ANCHORED_W0=1.0 (fit) makes this identical
    in SHAPE to the legacy family's w_prior(t) = 1 - fraction_elapsed(t) --
    the fit independently recovered a pure linear prior-decay as optimal.
  - score_diff / sqrt(minutes_remaining(t)): the realized-state term, scaled by
    inverse SQRT time remaining in MINUTES (not linear inverse seconds, as the
    legacy family used) -- this shape, with a properly fit k, is what wins
    cross-corpus (see ingame_blend_families.py docstring for the full family
    comparison). minutes_remaining floor-clamped at 25/60 min so the term never
    diverges near the buzzer (same 25s floor the legacy ramp used).
  - AT t=0 (tipoff): score_diff/... term uses whatever score_diff is at tipoff
    (0 by construction in the adapter's real call path) and w_prior(0)=ANCHORED_W0
    -> with ANCHORED_W0=1.0, p_live == p0 exactly (recovers the pregame Elo
    probability, the p0-recovery invariant tested below).
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

# Points-to-logits scale for the LEGACY fixed blend's realized-score term. Kept
# a fixed, documented constant (not fit on a live corpus at the time it was
# shipped) chosen so a 10-point lead with ~1 quarter (600s) remaining moves the
# blended probability sharply away from 0.5 without swamping the pregame prior
# at tip-off-adjacent states. Retained ONLY for blend_prob_fixed_legacy.
K_SCORE: float = 3.0

# Floor on sec_remaining used only inside the legacy ramp's inverse-time term,
# so the realized-score contribution never diverges as sec_remaining -> 0
# (mirrors NBA's build_state_features time_pressure 30s floor, scaled here to
# WNBA's shorter period length: 30 * (PERIOD_SEC/720) = 25s).
_TIME_FLOOR_SEC: float = 25.0

# ---------------------------------------------------------------------------
# Current default family (anchored) -- fit ONLY on 2024, frozen thereafter.
# See ingame_blend_families.py + data/domains/wnba/ingame_blend_check.json (v2)
# for the fit method and full cross-corpus Brier tables.
# ---------------------------------------------------------------------------
ANCHORED_K: float = 0.63
ANCHORED_W0: float = 1.0
_MIN_REMAIN_FLOOR: float = 25.0 / 60.0  # same 25s floor, expressed in minutes


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


def minutes_remaining(period: int, clock_s: float) -> float:
    """Minutes left in regulation/OT, floor-clamped at _MIN_REMAIN_FLOOR (25s
    expressed in minutes) so 1/sqrt(minutes_remaining) never diverges near the
    buzzer. Thin unit-conversion wrapper around sec_remaining."""
    sr = sec_remaining(period, clock_s)
    return max(sr / 60.0, _MIN_REMAIN_FLOOR)


def blend_prob(p0: float, state: LiveState) -> float:
    """CURRENT DEFAULT (anchored family, adopted this wave -- see module
    docstring): p_live = sigmoid(logit(p0) * w_prior(t) + ANCHORED_K *
    score_diff / sqrt(minutes_remaining(t))), with w_prior(t) = ANCHORED_W0 *
    (1 - fraction_elapsed(t)).

    Pure function of (p0, state); no I/O, no fitting (ANCHORED_K/ANCHORED_W0
    are frozen constants fit once on 2024 -- see ingame_blend_families.py).
    p0 is the pregame P(home win) (WNBA Elo, the SAME prior
    WNBAAdapter.baseline_probability reports). Monotone increasing in
    score_diff for fixed t (larger home lead -> higher p_live); converges to a
    determined 0/1 outcome as t->T when score_diff!=0 (see predict_live's exact
    buzzer clamp -- this function alone asymptotes toward but does not force
    0/1, by design a pure continuous blend). At tipoff (t=0, score_diff=0 in
    the adapter's real call path) p_live == p0 exactly with ANCHORED_W0=1.0
    (p0-recovery invariant tested below)."""
    t = fraction_elapsed(state.period, state.clock_s)
    w_prior = ANCHORED_W0 * (1.0 - t)
    score_diff = float(state.home_score) - float(state.away_score)
    mr = minutes_remaining(state.period, state.clock_s)
    z = _logit(p0) * w_prior + ANCHORED_K * score_diff / math.sqrt(mr)
    return _sigmoid(z)


def blend_prob_fixed_legacy(p0: float, state: LiveState) -> float:
    """LEGACY (wave-2) fixed-constant blend, UNCHANGED:
    p_live = sigmoid(logit(p0) * w_prior(t) + K_SCORE * score_diff * ramp(t)).

    Kept importable for comparison (ingame_blend_families.predict_fixed calls
    this directly) and as the wave-2 incumbent baseline in the cross-family
    check. No longer the adapter default -- see module docstring for why."""
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
    "REG_SEC", "PERIOD_SEC", "OT_SEC", "K_SCORE", "ANCHORED_K", "ANCHORED_W0",
    "LiveState", "sec_remaining", "fraction_elapsed", "minutes_remaining",
    "blend_prob", "blend_prob_fixed_legacy", "is_buzzer",
]
