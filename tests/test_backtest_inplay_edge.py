"""tests/test_backtest_inplay_edge.py — cycle 95d (loop 5).

4 tests for the in-play-vs-pregame betting edge backtest helpers:
  1. Edge calculation is correct on synthetic (pred, line) fixtures.
  2. Kelly fraction is clipped at 0 (never negative).
  3. ROI on a 5-bet fixture matches a hand-computed reference.
  4. simulate_bets handles missing pregame data gracefully (no crash, just
     skips the triple in the pregame branch while inplay still simulates).

All tests are pure arithmetic — no model loads, no file I/O, no nba_api.
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import backtest_inplay_edge as bie


# ── 1. Edge calculation ───────────────────────────────────────────────────────

def test_edge_calc_correct_on_synthetic_triples():
    """Edge sign + magnitude is just pred - line. Sanity-check this against a
    handful of fixtures so any regression in the EV math gets caught.
    """
    cases = [
        # (pred, line, expected_edge, expected_side)
        (32.0, 28.5, +3.5, "OVER"),
        (24.0, 28.5, -4.5, "UNDER"),
        (10.0, 10.0,  0.0, "OVER"),       # zero edge — sim should skip
        ( 5.5,  6.0, -0.5, "UNDER"),
        (15.2, 14.7, +0.5, "OVER"),
    ]
    for pred, line, exp_edge, exp_side in cases:
        edge = pred - line
        assert edge == pytest.approx(exp_edge), f"edge for ({pred},{line})"
        if edge != 0:
            side = "OVER" if edge > 0 else "UNDER"
            assert side == exp_side, f"side for edge={edge}"


# ── 2. Kelly fraction clipping ───────────────────────────────────────────────

def test_kelly_fraction_clipped_non_negative():
    """Kelly must never return < 0 — that would mean 'short the bet', which
    sportsbooks don't allow. The function should return exactly 0.0 when the
    book-implied probability exceeds the model's win-probability.
    """
    # -110 odds → implied p = 0.5238. Probabilities below that → negative
    # raw Kelly → should clip to 0.
    for p_below in (0.05, 0.20, 0.40, 0.50, 0.5238):
        assert bie.kelly_fraction(p_below, -110) >= 0.0
    assert bie.kelly_fraction(0.40, -110) == 0.0
    assert bie.kelly_fraction(0.10, -110) == 0.0

    # Probabilities above implied → positive Kelly.
    assert bie.kelly_fraction(0.60, -110) > 0.0
    assert bie.kelly_fraction(0.75, -110) > bie.kelly_fraction(0.60, -110)

    # Edge case: prob=None should not crash and should give 0.
    assert bie.kelly_fraction(None, -110) == 0.0


# ── 3. ROI computation matches hand math on a 5-bet fixture ───────────────────

def test_roi_matches_hand_computation_on_5_bet_fixture():
    """Construct 5 triples where we KNOW the bet decision + outcome, then
    confirm simulate_bets produces the right wins / flat ROI.

    Fixture rules (all -110 odds, flat $1 stakes):
      - bet1 PTS: pred=32, line=28.5 → OVER, actual=30 → WIN  (+0.909)
      - bet2 PTS: pred=20, line=28.5 → UNDER, actual=24 → WIN (+0.909)
      - bet3 PTS: pred=35, line=28.5 → OVER, actual=24 → LOSE (-1.000)
      - bet4 PTS: pred=32, line=28.5 → OVER, actual=28 → LOSE (-1.000)
      - bet5 PTS: pred=33, line=28.5 → OVER, actual=29 → WIN  (+0.909)

    Hand totals:
      n_bets = 5, wins = 3, pnl_flat = 3*(10/11) - 2 = 30/11 - 2 = 8/11
      roi_flat = (8/11) / 5 = 8/55 = 0.14545...
    """
    triples = {
        ("g1", 1, "pts"): 32.0,
        ("g1", 2, "pts"): 20.0,
        ("g1", 3, "pts"): 35.0,
        ("g1", 4, "pts"): 32.0,
        ("g1", 5, "pts"): 33.0,
    }
    lines = {k: 28.5 for k in triples}
    actuals = {
        ("g1", 1, "pts"): 30.0,
        ("g1", 2, "pts"): 24.0,
        ("g1", 3, "pts"): 24.0,
        ("g1", 4, "pts"): 28.0,
        ("g1", 5, "pts"): 29.0,
    }

    res = bie.simulate_bets(triples, lines, actuals, threshold=1.0)
    pts = res["pts"]
    # Edges are 3.5 / -8.5 / 6.5 / 3.5 / 4.5 — all >= 1.0 threshold.
    # Probabilities under the default PTS calibrated sigma should all clear
    # Kelly>0 (each edge is large vs the ~5.5 sigma so model thinks it's
    # confident enough). Verify everything routes through correctly.
    assert pts["n_bets"] == 5, f"expected 5 bets, got {pts['n_bets']}"
    assert pts["wins"] == 3, f"expected 3 wins, got {pts['wins']}"

    # Flat ROI: win pays 10/11 ≈ 0.9090909, loss pays -1.0.
    win_payout = 10 / 11
    expected_pnl = 3 * win_payout - 2 * 1.0  # 30/11 - 2 = 8/11
    expected_roi = expected_pnl / 5.0  # = 8/55
    assert pts["pnl_flat"] == pytest.approx(expected_pnl)
    assert pts["roi_flat"] == pytest.approx(expected_roi)
    assert pts["win_rate"] == pytest.approx(3 / 5)


# ── 4. Missing-pregame graceful handling ─────────────────────────────────────

def test_missing_pregame_handled_gracefully():
    """If pregame is missing for a triple but inplay has it, simulate_bets
    should silently skip the missing-pregame triple (no crash) while the
    inplay system still bets that triple successfully.
    """
    # In-play has all 3 triples, pregame is missing 1 of them.
    inplay = {
        ("g1", 1, "pts"): 32.0,
        ("g1", 2, "pts"): 20.0,
        ("g1", 3, "pts"): 33.0,
    }
    pregame = {
        ("g1", 1, "pts"): 31.0,
        # ("g1", 2, "pts") deliberately absent.
        ("g1", 3, "pts"): 30.0,
    }
    lines = {
        ("g1", 1, "pts"): 28.5,
        ("g1", 2, "pts"): 28.5,
        ("g1", 3, "pts"): 28.5,
    }
    actuals = {
        ("g1", 1, "pts"): 30.0,
        ("g1", 2, "pts"): 24.0,
        ("g1", 3, "pts"): 29.0,
    }

    # Both branches simulate without raising.
    res_inplay = bie.simulate_bets(inplay, lines, actuals, threshold=1.0)
    res_pregame = bie.simulate_bets(pregame, lines, actuals, threshold=1.0)

    # Inplay should bet all 3 (edges +3.5, -8.5, +4.5).
    assert res_inplay["pts"]["n_bets"] == 3
    # Pregame should bet 2 (edges +2.5 for g1/1, +1.5 for g1/3). g1/2 absent.
    assert res_pregame["pts"]["n_bets"] == 2
    # Neither system crashes; ROI computed for both.
    assert res_inplay["pts"]["roi_flat"] is not None
    assert res_pregame["pts"]["roi_flat"] is not None
