"""domains.soccer.markets — full soccer market surface from one scoreline matrix.

The Dixon-Coles bivariate-Poisson scoreline matrix P[i, j] = P(home=i, away=j) is
the joint distribution of the final score. EVERY standard soccer market is a linear
read-off of that single matrix, so they are COHERENT by construction (1X2 sums to 1,
double-chance = sum of its two 1X2 legs, Asian-0 == draw-no-bet, totals monotone in
the line, etc.). This module prices the whole catalog with NO new data:

  * 1X2 (home / draw / away moneyline)
  * Double chance (1X, 12, X2)
  * Draw-no-bet (DNB; stake refunded on a draw -> renormalise over the decisive mass)
  * Both-teams-to-score (BTTS yes / no)
  * Total goals over/under at ALL lines (0.5, 1.5, 2.5, 3.5, 4.5 ... any half-line)
  * Team totals over/under (home / away, any half-line)
  * Asian handicap at any line (.0 / .25 / .5 / .75 / 1.0 ...), push mass split correctly
  * European (3-way) handicap at integer lines (home-win / draw / away-win after handicap)
  * Correct score (top-N most-probable exact scorelines)
  * Odd / even total goals
  * Clean sheet (home / away keep a clean sheet)
  * Winning margin (home-by-1, home-by-2+, away-by-1, ... bucketed)

This module is reused by BOTH the club predictor (domains/soccer/predictor.py) and the
international predictor (domains/soccer_intl/predictor.py) so there is ONE implementation.

HONEST: every probability here is an algebraic read-off of the already-validated
scoreline matrix. It does NOT add any signal or edge over the base Poisson surface;
it just prices markets that the scalar baseline could not express. Pregame soccer
markets are efficient; calibration only, no $ edge claimed.

INVARIANTS: never edit src/ or kernel/; pure numpy; read-only on scoreline_engine; <=300 LOC.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

_DEFAULT_OU_LINES: Tuple[float, ...] = (0.5, 1.5, 2.5, 3.5, 4.5)
_DEFAULT_TEAM_OU_LINES: Tuple[float, ...] = (0.5, 1.5, 2.5)
_DEFAULT_AH_LINES: Tuple[float, ...] = (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5)


# ---------------------------------------------------------------------------
# Marginals / helpers
# ---------------------------------------------------------------------------

def _total_dist(P: np.ndarray) -> np.ndarray:
    """Total-goals marginal: out[t] = sum of P over all (i, j) with i + j == t."""
    n = P.shape[0]
    Pf = np.fliplr(P)
    return np.array([np.trace(Pf, offset=k) for k in range(n - 1, -n, -1)], dtype=float)


def _diff_probs(P: np.ndarray) -> Tuple[float, float, float]:
    """(P(home win), P(draw), P(away win)) from the scoreline matrix."""
    n = P.shape[0]
    r = np.arange(n)[:, None]
    c = np.arange(n)[None, :]
    return (float(P[r > c].sum()), float(P[r == c].sum()), float(P[r < c].sum()))


# ---------------------------------------------------------------------------
# Individual market pricers (each is a pure read-off of P)
# ---------------------------------------------------------------------------

def one_x_two(P: np.ndarray) -> Dict[str, float]:
    """1X2 moneyline. The three legs sum to 1.0 by construction."""
    ph, pd, pa = _diff_probs(P)
    return {"1X2_home": ph, "1X2_draw": pd, "1X2_away": pa}


def double_chance(P: np.ndarray) -> Dict[str, float]:
    """Double chance = sum of the two covered 1X2 legs."""
    ph, pd, pa = _diff_probs(P)
    return {"dc_1X": ph + pd, "dc_12": ph + pa, "dc_X2": pd + pa}


def draw_no_bet(P: np.ndarray) -> Dict[str, float]:
    """Draw-no-bet: stake refunded on a draw, so renormalise over the decisive mass."""
    ph, pd, pa = _diff_probs(P)
    decisive = ph + pa
    if decisive <= 0.0:
        return {"dnb_home": 0.5, "dnb_away": 0.5}
    return {"dnb_home": ph / decisive, "dnb_away": pa / decisive}


def btts(P: np.ndarray) -> Dict[str, float]:
    """Both-teams-to-score: P(h>=1, a>=1) = 1 - P(h=0) - P(a=0) + P(0,0)."""
    p_yes = max(0.0, float(1.0 - P[0, :].sum() - P[:, 0].sum() + P[0, 0]))
    return {"btts_yes": p_yes, "btts_no": 1.0 - p_yes}


def totals(P: np.ndarray, lines=_DEFAULT_OU_LINES) -> Dict[str, float]:
    """Total-goals over/under at every half-line. Over-prob is monotone decreasing in line."""
    td = _total_dist(P)
    out: Dict[str, float] = {}
    for line in lines:
        threshold = int(np.ceil(line))  # over means total >= ceil(line) for a half-line
        p_over = float(td[threshold:].sum())
        out[f"over_{line:g}"] = p_over
        out[f"under_{line:g}"] = 1.0 - p_over
    return out


def team_totals(P: np.ndarray, lines=_DEFAULT_TEAM_OU_LINES) -> Dict[str, float]:
    """Per-team goals over/under at every half-line, off the team-goal marginals."""
    home_marg = P.sum(axis=1)  # P(home = i)
    away_marg = P.sum(axis=0)  # P(away = j)
    out: Dict[str, float] = {}
    for marg, tag in ((home_marg, "home"), (away_marg, "away")):
        for line in lines:
            threshold = int(np.ceil(line))
            p_over = float(marg[threshold:].sum())
            out[f"team_{tag}_over_{line:g}"] = p_over
            out[f"team_{tag}_under_{line:g}"] = 1.0 - p_over
    return out


def asian_handicap(P: np.ndarray, lines=_DEFAULT_AH_LINES) -> Dict[str, float]:
    """Asian handicap for the HOME side at each line.

    The handicap is added to the home goals; the bet settles on margin = (home - away).
    On a whole-number line the stake is REFUNDED when the adjusted margin is exactly 0
    (a push), so the fair home-cover probability is the win mass renormalised over the
    resolved (non-push) mass -- this makes the line 0.0 case coincide EXACTLY with
    draw-no-bet.  Half lines (.5) cannot push.  Quarter lines (.25/.75) are the average
    of the two adjacent half/whole lines (half the stake on each).

    Returns keys 'ah_home_{line}' = P(home covers | not pushed).
    """
    n = P.shape[0]
    r = np.arange(n)[:, None]
    c = np.arange(n)[None, :]
    margin = r - c  # home - away, per cell
    out: Dict[str, float] = {}
    for line in lines:
        two = round(line * 2, 6)
        if float(two).is_integer() and int(two) % 2 == 0:
            # whole-number line -> push possible at adjusted margin == 0; refund -> renorm
            win = float(P[(margin + line) > 0].sum())
            push = float(P[(margin + line) == 0].sum())
            resolved = 1.0 - push
            out[f"ah_home_{line:g}"] = win / resolved if resolved > 0 else 0.5
        elif float(two).is_integer():
            # half line (.5) -> no push
            out[f"ah_home_{line:g}"] = float(P[(margin + line) > 0].sum())
        else:
            # quarter line -> average of the two adjacent (half + whole) lines
            lo = np.floor(line * 2) / 2.0
            hi = np.ceil(line * 2) / 2.0
            sub = asian_handicap(P, lines=(lo, hi))
            out[f"ah_home_{line:g}"] = 0.5 * (sub[f"ah_home_{lo:g}"] + sub[f"ah_home_{hi:g}"])
    return out


def european_handicap(P: np.ndarray, lines=(1, 2)) -> Dict[str, float]:
    """3-way (European) handicap at integer lines: home / draw / away after the handicap.

    Adds +line to the home score, then prices a coherent 1X2 on the adjusted margin.
    Emits 'eh_home_{+/-line}_{home,draw,away}'. The three legs sum to 1.0.
    """
    n = P.shape[0]
    r = np.arange(n)[:, None]
    c = np.arange(n)[None, :]
    margin = r - c
    out: Dict[str, float] = {}
    for line in lines:
        for sign, tag in ((line, f"home+{line}"), (-line, f"home-{line}")):
            adj = margin + sign
            out[f"eh_{tag}_home"] = float(P[adj > 0].sum())
            out[f"eh_{tag}_draw"] = float(P[adj == 0].sum())
            out[f"eh_{tag}_away"] = float(P[adj < 0].sum())
    return out


def odd_even(P: np.ndarray) -> Dict[str, float]:
    """Odd / even total goals."""
    td = _total_dist(P)
    p_odd = float(td[1::2].sum())
    return {"total_odd": p_odd, "total_even": 1.0 - p_odd}


def clean_sheet(P: np.ndarray) -> Dict[str, float]:
    """Clean sheet: P(away=0) for the home keeper, P(home=0) for the away keeper."""
    return {"cs_home_clean": float(P[:, 0].sum()), "cs_away_clean": float(P[0, :].sum())}


def winning_margin(P: np.ndarray, max_by: int = 3) -> Dict[str, float]:
    """Winning-margin buckets: home_by_1..(max_by), home_by_{max_by}+, away_by_*, draw."""
    n = P.shape[0]
    r = np.arange(n)[:, None]
    c = np.arange(n)[None, :]
    margin = r - c
    out: Dict[str, float] = {"wm_draw": float(P[margin == 0].sum())}
    for side, sgn in (("home", 1), ("away", -1)):
        for m in range(1, max_by):
            out[f"wm_{side}_by_{m}"] = float(P[margin == sgn * m].sum())
        out[f"wm_{side}_by_{max_by}plus"] = float(P[(sgn * margin) >= max_by].sum())
    return out


def correct_scores(P: np.ndarray, top_n: int = 8) -> Dict[str, float]:
    """Top-N most-probable exact scorelines, key 'cs_{home}_{away}'."""
    n = P.shape[0]
    out: Dict[str, float] = {}
    for flat_i in np.argsort(P.ravel())[::-1][:top_n]:
        hi, ai = divmod(int(flat_i), n)
        out[f"cs_{hi}_{ai}"] = float(P[hi, ai])
    return out


# ---------------------------------------------------------------------------
# Full surface
# ---------------------------------------------------------------------------

def full_surface(
    P: np.ndarray,
    *,
    top_n: int = 8,
    ou_lines=_DEFAULT_OU_LINES,
    team_ou_lines=_DEFAULT_TEAM_OU_LINES,
    ah_lines=_DEFAULT_AH_LINES,
    eh_lines=(1, 2),
) -> Dict[str, float]:
    """Price the ENTIRE standard soccer market catalog off one scoreline matrix P.

    All probabilities are coherent linear read-offs of P, so cross-market identities
    hold exactly (1X2 sums to 1, double-chance = the two legs, Asian-0 == DNB, etc.).
    """
    out: Dict[str, float] = {}
    out.update(one_x_two(P))
    out.update(double_chance(P))
    out.update(draw_no_bet(P))
    out.update(btts(P))
    out.update(totals(P, ou_lines))
    out.update(team_totals(P, team_ou_lines))
    out.update(asian_handicap(P, ah_lines))
    out.update(european_handicap(P, eh_lines))
    out.update(odd_even(P))
    out.update(clean_sheet(P))
    out.update(winning_margin(P))
    out.update(correct_scores(P, top_n))
    return out
