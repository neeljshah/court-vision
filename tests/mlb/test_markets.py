"""tests.mlb.test_markets — coherence of the derivable MLB market surface.

Asserts the math invariants of domains/mlb/markets.py against the SAME NegBinom run
distribution the predictor uses:
  * run line at margin 0 == moneyline (P(home wins)+0.5*P(tie) == ml_home),
  * home team-total expected + away team-total expected == game expected total,
  * P(over) is monotonically non-increasing as the total line rises,
  * over_N + under_N (+ push for integer lines) == 1,
  * run-line complement pairs sum to 1,
  * F5 expected total == fraction * full expected total.
HONEST: pure math coherence; no edge claimed. Run ONLY this file (full suite freezes).
"""
from __future__ import annotations

import numpy as np

from domains.mlb.markets import (
    F5_FRACTION, full_market_surface, game_total_surface, run_line_surface,
    team_total_surface, f5_surface,
)
from domains.mlb.negbinom_engine import runs_matrix_nb

LAM_H, LAM_A, R_H, R_A = 4.8, 4.2, 4.0, 4.2
P = runs_matrix_nb(LAM_H, LAM_A, R_H, R_A)


def _ml_home(P):
    n = P.shape[0]
    ri, ci = np.arange(n)[:, None], np.arange(n)[None, :]
    pt = float(P[ri == ci].sum())
    return float(P[ri > ci].sum()) + 0.5 * pt


def test_run_line_at_zero_equals_moneyline():
    """P(home wins) + 0.5 P(tie) read off the margin distribution == ml_home."""
    rl = run_line_surface(P)
    # home win-by-1 ("margin 0" run line, i.e. straight win) is alt margin k=1
    k1 = [a for a in rl["alternates"] if a["abs_margin"] == 1][0]
    p_home_win = k1["p_home_cover_minus"]          # home wins by >=1
    p_away_win = k1["p_away_cover_minus"]           # away wins by >=1
    p_tie = 1.0 - p_home_win - p_away_win
    ml = _ml_home(P)
    # alt fields are rounded to 4 decimals -> compare at rounding tolerance
    assert abs((p_home_win + 0.5 * p_tie) - ml) < 5e-4


def test_runline_complements_sum_to_one():
    rl = run_line_surface(P)
    s = rl["standard"]
    assert abs(s["home_minus_1.5"] + s["away_plus_1.5"] - 1.0) < 1e-9
    assert abs(s["away_minus_1.5"] + s["home_plus_1.5"] - 1.0) < 1e-9
    for a in rl["alternates"]:
        assert abs(a["p_home_cover_minus"] + a["p_away_cover_plus"] - 1.0) < 1e-9
        assert abs(a["p_away_cover_minus"] + a["p_home_cover_plus"] - 1.0) < 1e-9


def test_team_totals_sum_to_game_total():
    tt = team_total_surface(LAM_H, LAM_A, R_H, R_A, (3.5, 4.5, 5.5))
    assert abs((tt["home"]["expected"] + tt["away"]["expected"]) - (LAM_H + LAM_A)) < 0.05


def test_game_total_over_monotonic_nonincreasing():
    lines = [4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
    gt = game_total_surface(P, lines)
    overs = [g["over"] for g in gt]
    for a, b in zip(overs, overs[1:]):
        assert b <= a + 1e-9, f"over not monotonic: {a} -> {b}"


def test_over_under_partition_to_one():
    # half-integer: over+under==1; integer: over+under+push==1
    for ln in (6.5, 7.0, 8.5, 9.0):
        g = game_total_surface(P, [ln])[0]
        s = g["over"] + g["under"] + g.get("push", 0.0)
        # values are rounded to 4 decimals; matrix is truncated+renormalized
        assert abs(s - 1.0) < 1e-3, f"line {ln} partition={s}"


def test_f5_expected_total_scales_by_fraction():
    f5 = f5_surface(LAM_H, LAM_A, R_H, R_A)
    expected = (LAM_H + LAM_A) * F5_FRACTION
    assert abs(f5["f5_expected_total"] - expected) < 0.06
    # F5 ML 3-way market (raw home/away/tie) sums to 1
    assert abs(f5["f5_ml_home"] + f5["f5_ml_away"] + f5["f5_tie"] - 1.0) < 1e-3
    # 2-way (draw-no-bet) line also sums to 1
    assert abs(f5["f5_ml_home_2way"] + f5["f5_ml_away_2way"] - 1.0) < 1e-3


def test_full_surface_one_winprob():
    """The moneyline in the full surface == the ml read straight off the matrix."""
    s = full_market_surface(LAM_H, LAM_A, R_H, R_A)
    assert abs(s["moneyline"]["home"] - _ml_home(P)) < 5e-4  # 4-decimal rounding
    assert abs(s["moneyline"]["home"] + s["moneyline"]["away"] - 1.0) < 1e-3
    # run line standard home -1.5 must equal P(home margin>=2) <= ml_home
    assert s["run_line"]["standard"]["home_minus_1.5"] <= s["moneyline"]["home"] + 1e-9
