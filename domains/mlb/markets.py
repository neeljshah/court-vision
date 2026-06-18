"""domains.mlb.markets — COMPLETE derivable MLB market surface from the run model.

A PURE pricing layer over the predictor's anchored run-rate lambdas + FITTED NegBinom
dispersion (domains/mlb/negbinom_engine). It adds NO new data and NO new modelling: it
re-reads the SAME independent-NegBinom joint matrix the predictor already builds and
projects it onto every standard MLB team/game market that is a deterministic function
of the run distribution:

  * MONEYLINE              -> tie-split home-win prob (already in predict(); echoed here)
  * RUN LINE -1.5 / +1.5   -> P(home wins by >=2) and complement
  * ALTERNATE RUN LINES    -> P(home margin >= k) for k in {-3..-1, +2, +3} (both sides)
  * GAME TOTAL O/U          -> any line / alternates from the marginal total distribution
  * TEAM TOTALS O/U         -> per-side NegBinom marginal (sum-coherent with game total)
  * FIRST-5-INNINGS (F5)    -> run model scaled by an EMPIRICAL F5 fraction (see below),
                               giving F5 ML + F5 O/U. CLEARLY LABELLED as a scaling
                               approximation (no inning-engine; same dispersion r).

WHY F5_FRACTION = 0.521 (NOT the naive 5/9 = 0.556): on the full 27,983-game corpus the
realized first-5-innings runs are 52.1% of the full-game total, not 55.6% -- MLB scoring
ACCELERATES late (bullpen fatigue, pinch hitters, no save-situation starters). We use the
measured fraction so F5 means are calibrated, and we expose it as a constant so it is
auditable. This is still an APPROXIMATION (it scales the whole-game lambda; it does not
model the actual inning-by-inning process), and every F5 key is labelled f5_*.

COHERENCE GUARANTEES (asserted in the per-file test):
  * run line at margin 0 == moneyline (P(home margin>=1)+0.5*P(tie) == ml_home).
  * home team-total + away team-total expected values == game expected total.
  * P(over) is monotonically NON-INCREASING as the total line rises.
  * over_N + under_N (+ push_N for integer lines) == 1.

HONEST: calibration/coherence only. Markets are efficient; NO $ edge is claimed. The run
distribution is the predictor's; this file only reprices it onto more market shapes.
INVARIANTS: never edit src/kernel; pure (no file I/O, no global state); <=300 LOC.
"""
from __future__ import annotations

import math
from typing import Dict, Sequence

import numpy as np

from domains.mlb.negbinom_engine import _negbinom_pmf, runs_matrix_nb

# Empirical first-5-innings run fraction, measured on data/domains/mlb/pitchers.parquet
# (sum of first 5 inning tokens / full-game total runs over all 27,983 games == 0.521).
F5_FRACTION = 0.521
_F5_MAX_RUNS = 14  # F5 lambdas are ~half the full-game lambdas; 14 covers the tail


# --- per-side marginal helpers ---------------------------------------------

def _margin_dist(P: np.ndarray) -> tuple[np.ndarray, int]:
    """Distribution of (home_runs - away_runs). Returns (probs, zero_index).

    probs[zero_index + m] == P(home_margin == m). m ranges -(n-1)..+(n-1).
    """
    n = P.shape[0]
    d = np.zeros(2 * n - 1, dtype=float)
    for i in range(n):
        for j in range(n):
            d[(i - j) + (n - 1)] += P[i, j]
    return d, n - 1


def _total_dist(P: np.ndarray) -> np.ndarray:
    """Marginal total-runs distribution from the joint matrix."""
    n = P.shape[0]
    d = np.zeros(2 * n - 1, dtype=float)
    for i in range(n):
        for j in range(n):
            d[i + j] += P[i, j]
    return d


def _ou_from_dist(d: np.ndarray, line: float) -> Dict[str, float]:
    """Over/under/push for a single total line from a 1-D count distribution.

    Half-integer lines have no push (over+under==1). Integer lines push on total==line.
    """
    is_half = (line != math.floor(line))
    if is_half:
        cutoff = int(math.ceil(line))
        po = float(d[cutoff:].sum()) if cutoff < len(d) else 0.0
        push = 0.0
    else:
        # Integer line: over is STRICTLY above the line; total==line is the push.
        li = int(round(line))
        push = float(d[li]) if li < len(d) else 0.0
        po = float(d[li + 1:].sum()) if (li + 1) < len(d) else 0.0
    out = {"over": round(po, 4), "under": round(1.0 - po - push, 4)}
    if not is_half:
        out["push"] = round(push, 4)
    return out


# --- public surface ---------------------------------------------------------

def run_line_surface(P: np.ndarray, alt_margins: Sequence[int] = (1, 2, 3)) -> Dict:
    """Run line + alternate run lines from the joint matrix.

    Standard MLB run line is +/-1.5 (margin>=2). alt_margins are the absolute margins
    k for which we price P(home wins by >=k) (home -k.5) and P(away wins by >=k)
    (away -k.5), plus the generous side (+k.5) as the complement.
    """
    md, z = _margin_dist(P)
    n = len(md)

    def p_home_by_at_least(k: int) -> float:
        lo = z + k
        return float(md[lo:].sum()) if lo < n else 0.0

    def p_away_by_at_least(k: int) -> float:
        hi = z - k
        return float(md[: hi + 1].sum()) if hi >= 0 else 0.0

    standard = {
        "home_minus_1.5": round(p_home_by_at_least(2), 4),   # home wins by >=2
        "away_plus_1.5": round(1.0 - p_home_by_at_least(2), 4),
        "away_minus_1.5": round(p_away_by_at_least(2), 4),   # away wins by >=2
        "home_plus_1.5": round(1.0 - p_away_by_at_least(2), 4),
    }
    alts = []
    for k in alt_margins:
        ph = p_home_by_at_least(k)
        pa = p_away_by_at_least(k)
        alts.append({
            "abs_margin": k,
            "line": k - 0.5,                       # the -(k-.5) / +(k-.5) run line
            "p_home_cover_minus": round(ph, 4),   # home wins by >= k  (home -(k-.5))
            "p_home_cover_plus": round(1.0 - pa, 4),  # home +(k-.5): not(away by>=k)
            "p_away_cover_minus": round(pa, 4),   # away wins by >= k
            "p_away_cover_plus": round(1.0 - ph, 4),
        })
    return {"standard": standard, "alternates": alts}


def game_total_surface(P: np.ndarray, lines: Sequence[float]) -> list:
    """Game total O/U for every requested line (half-integer or integer)."""
    d = _total_dist(P)
    return [dict(line=ln, **_ou_from_dist(d, ln)) for ln in lines]


def team_total_surface(lam_home: float, lam_away: float, r_home: float, r_away: float,
                       lines: Sequence[float], *, max_runs: int = 25) -> Dict:
    """Per-team total O/U from the SAME NegBinom marginals used in the joint matrix.

    Sum-coherent: E[home_team_total] + E[away_team_total] == lam_home + lam_away ==
    the game expected total (the marginals share the joint's means by construction).
    """
    ph = _negbinom_pmf(lam_home, r_home, max_runs)
    pa = _negbinom_pmf(lam_away, r_away, max_runs)
    return {
        "home": {"expected": round(float((np.arange(max_runs + 1) * ph).sum()), 3),
                 "lines": [dict(line=ln, **_ou_from_dist(ph, ln)) for ln in lines]},
        "away": {"expected": round(float((np.arange(max_runs + 1) * pa).sum()), 3),
                 "lines": [dict(line=ln, **_ou_from_dist(pa, ln)) for ln in lines]},
    }


def f5_surface(lam_home: float, lam_away: float, r_home: float, r_away: float,
               *, total_lines: Sequence[float] = (4.5, 5.5),
               fraction: float = F5_FRACTION) -> Dict:
    """First-5-innings ML + O/U by scaling the full-game lambdas by the empirical fraction.

    APPROXIMATION (labelled): scales the whole-game run rate to 5 innings using the
    measured F5 share of full-game runs (NOT the naive 5/9). It does NOT model the real
    inning process and reuses the full-game dispersion r, so the F5 tail shape is
    approximate. ML is the tie-split home-win prob of the scaled NegBinom matrix.
    """
    lh5, la5 = max(lam_home * fraction, 0.05), max(lam_away * fraction, 0.05)
    P5 = runs_matrix_nb(lh5, la5, r_home, r_away, max_runs=_F5_MAX_RUNS)
    n = P5.shape[0]
    ri, ci = np.arange(n)[:, None], np.arange(n)[None, :]
    ph = float(P5[ri > ci].sum()); pa = float(P5[ri < ci].sum()); pt = float(P5[ri == ci].sum())
    d = _total_dist(P5)
    return {
        "approximation": (f"full-game lambdas x F5_FRACTION={fraction:g} (empirical, "
                          "NOT 5/9); same dispersion r; F5 tail shape approximate"),
        "f5_lam_home": round(lh5, 3), "f5_lam_away": round(la5, 3),
        "f5_expected_total": round(lh5 + la5, 3),
        # F5 ties are common (5-inning games end level often) -> a real 3-way market.
        # f5_ml_home/away/tie are RAW probabilities that sum to 1. f5_ml_home_2way is the
        # tie-split (draw-no-bet) home prob for books that offer F5 as a 2-way line.
        "f5_ml_home": round(ph, 4),
        "f5_ml_away": round(pa, 4),
        "f5_tie": round(pt, 4),
        "f5_ml_home_2way": round(ph + 0.5 * pt, 4),
        "f5_ml_away_2way": round(pa + 0.5 * pt, 4),
        "f5_totals": [dict(line=ln, **_ou_from_dist(d, ln)) for ln in total_lines],
    }


def full_market_surface(lam_home: float, lam_away: float, r_home: float, r_away: float,
                        *, total_lines: Sequence[float] = (6.5, 7.5, 8.5, 9.5, 10.5),
                        team_total_lines: Sequence[float] = (3.5, 4.5, 5.5),
                        alt_run_margins: Sequence[int] = (1, 2, 3),
                        f5_total_lines: Sequence[float] = (4.5, 5.5),
                        max_runs: int = 25) -> Dict:
    """One call -> the complete derivable MLB market surface for one matchup.

    Inputs are the predictor's ANCHORED lambdas (tilted so the matrix ML == the Elo
    win-prob, sum-preserved) and the FITTED dispersion r. Everything below is a pure
    read-off of the resulting NegBinom joint, so every market shares ONE win-prob and
    ONE expected total. NO new data; NO edge claimed.
    """
    P = runs_matrix_nb(lam_home, lam_away, r_home, r_away, max_runs=max_runs)
    n = P.shape[0]
    ri, ci = np.arange(n)[:, None], np.arange(n)[None, :]
    pt = float(P[ri == ci].sum())
    ml_home = float(P[ri > ci].sum()) + 0.5 * pt
    return {
        "moneyline": {"home": round(ml_home, 4), "away": round(1.0 - ml_home, 4)},
        "run_line": run_line_surface(P, alt_run_margins),
        "game_total": game_total_surface(P, total_lines),
        "team_totals": team_total_surface(lam_home, lam_away, r_home, r_away,
                                          team_total_lines, max_runs=max_runs),
        "first_5_innings": f5_surface(lam_home, lam_away, r_home, r_away,
                                      total_lines=f5_total_lines),
        "expected_runs_home": round(lam_home, 3),
        "expected_runs_away": round(lam_away, 3),
        "expected_total": round(lam_home + lam_away, 3),
        "honest_note": ("Complete derivable MLB market surface from ONE NegBinom run "
                        "distribution (predictor's anchored lambdas + fitted r). Every "
                        "market shares one win-prob and one expected total. F5 is a "
                        "labelled empirical scaling. Markets efficient; NO $ edge."),
    }
