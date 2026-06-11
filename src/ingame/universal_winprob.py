"""src/ingame/universal_winprob.py — P3.4: win% from the PROJECTED FINAL + time remaining.

ROADMAP: D04 §1 bullet 3, resolved by RED-B Attacks 5/6/7. This is the INTERFACE (the input
representation), NOT the router:

  - Win% is computed from the PROJECTED FINAL margin + time, NEVER from the raw live margin
    (the raw live margin is the median-of-conditional; using it is the shrink artifact).
  - Uncertainty about the actual final margin shrinks as the game proceeds:
    sigma = sigma_full * sqrt(remaining_frac). As remaining_frac -> 0, sigma -> 0 and win% -> a hard
    step on the (now-certain) projected margin.
  - The ROUTING stays measured per game-time. ``universal_eligible`` encodes the only promotion rule
    we keep: NO sim/projection win-prob before endQ3 (the sigmoid heads win Q1-Q2 — RED-B Attack 6),
    and FAIL CLOSED to the existing league-trained ``inplay_winprob`` stack for matchups the sim cannot
    cover (coverage_class != mc_full — RED-B Attack 7). This module does NOT call inplay_winprob; the
    router does, when ``universal_eligible`` is False.
  - There is NO "Brier <= 0.183" bar anywhere (RED-B Attack 5: it is satisfiable by a 40% regression vs
    the 0.126 sim / 0.135 v6_hp the system already ships). The only promotion bar is no-Brier-regression
    vs production routing at every game-time, enforced by the grader, not by a magic constant here.

DEFAULT-OFF: reached only under CV_INGAME_UNIVERSAL_WP. stdlib math only.
"""
from __future__ import annotations

import math
from typing import Optional

# Full-game final-margin SD (NBA ~13-14 pts). Used to scale the shrinking uncertainty band.
SIGMA_FULL_DEFAULT: float = 13.5
# Floor so sigma never hits 0 exactly at the buzzer (avoids a divide-by-zero; keeps a hair of noise).
SIGMA_FLOOR: float = 0.5
# Only the sim/projection win-prob is gated here; promotion starts at Q4 (strictly after endQ3),
# matching production routing (the sim loses Brier to the sigmoid in Q1-Q2).
MIN_PERIOD_FOR_UNIVERSAL: int = 4
MC_COVERAGE_CLASSES = ("mc_full",)


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def win_prob_from_projection(proj_margin: float, remaining_frac: float,
                             sigma_full: float = SIGMA_FULL_DEFAULT) -> float:
    """P(home wins) from the PROJECTED FINAL margin (home - away) + fraction of game remaining.

    Never takes the raw live margin. As ``remaining_frac`` -> 0 the band collapses and the win
    probability approaches a hard step on the sign of ``proj_margin``.
    """
    rf = min(1.0, max(0.0, float(remaining_frac)))
    sigma = max(float(sigma_full) * math.sqrt(rf), SIGMA_FLOOR)
    return _phi(float(proj_margin) / sigma)


def universal_eligible(period: int, coverage_class: str,
                       min_period: int = MIN_PERIOD_FOR_UNIVERSAL) -> bool:
    """True iff the projected-final win-prob may be used (else the router FAILS CLOSED to inplay_winprob).

    Two conditions: (1) game-time is at/after Q4 (no sim-WP before endQ3 — RED-B Attack 6); (2) the
    matchup is sim-coverable (coverage_class == mc_full — RED-B Attack 7). Both must hold.
    """
    return int(period) >= int(min_period) and str(coverage_class) in MC_COVERAGE_CLASSES


def win_prob_routed(period: int, coverage_class: str, proj_margin: Optional[float],
                    remaining_frac: float, sigma_full: float = SIGMA_FULL_DEFAULT) -> Optional[float]:
    """Return the projected-final win-prob ONLY when eligible, else None (router falls back).

    A None return is the explicit signal to the caller: "use the existing inplay_winprob stack here."
    """
    if proj_margin is None or not universal_eligible(period, coverage_class):
        return None
    return win_prob_from_projection(proj_margin, remaining_frac, sigma_full)
