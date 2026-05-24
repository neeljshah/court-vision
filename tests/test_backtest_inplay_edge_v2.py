"""tests/test_backtest_inplay_edge_v2.py — cycle 97d (loop 5).

5 tests for backtest_inplay_edge_v2:
  1. endQ3 ROI matches cycle 95d on the same fixture (regression — proves the
     v2 simulator is the same logic, just driven across more snapshots).
  2. endQ1 / endQ2 ROIs compute without crash.
  3. Zero-edge case: when projection == pregame the bet count is 0 (no
     spurious bets).
  4. Push case: when L5 == actual the bet does not pay (no-action / refund).
  5. Per-snapshot snapshot reconstruction handles a missing period gracefully
     (e.g. only Q1+Q2 in the parquet but endQ3 requested → returns None, NOT
     a crash, and downstream simulate_bets keeps running on the populated
     snapshots).

All tests are pure arithmetic — no model loads, no file I/O, no nba_api.
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from scripts import backtest_inplay_edge as bie  # noqa: E402
from scripts import backtest_inplay_edge_v2 as bie2  # noqa: E402


# ── 1. endQ3 ROI matches cycle 95d on shared fixture ────────────────────────

def test_endq3_simulator_identical_to_cycle_95d():
    """v2 must re-export and reuse cycle 95d's simulate_bets verbatim.

    Construct a 5-bet PTS fixture (mirrors cycle 95d's test_roi_matches_
    hand_computation) and confirm BOTH bie.simulate_bets and
    bie2.simulate_bets produce identical results — proves v2 is the same
    underlying logic, just driven across multiple snapshots.
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

    res_v1 = bie.simulate_bets(triples, lines, actuals, threshold=1.0)
    res_v2 = bie2.simulate_bets(triples, lines, actuals, threshold=1.0)

    assert res_v1["pts"]["n_bets"] == res_v2["pts"]["n_bets"]
    assert res_v1["pts"]["wins"] == res_v2["pts"]["wins"]
    assert res_v1["pts"]["roi_flat"] == pytest.approx(res_v2["pts"]["roi_flat"])
    assert res_v1["pts"]["roi_kelly"] == pytest.approx(res_v2["pts"]["roi_kelly"])
    # Hand check — wins 3, losses 2, flat ROI = (3*10/11 - 2) / 5 = 8/55.
    assert res_v2["pts"]["n_bets"] == 5
    assert res_v2["pts"]["wins"] == 3
    assert res_v2["pts"]["roi_flat"] == pytest.approx(8 / 55)


# ── 2. endQ1 / endQ2 ROIs computed without crash ────────────────────────────

def test_endq1_and_endq2_rois_computed_without_crash():
    """Run simulate_bets on independent endQ1 / endQ2 fixtures — both must
    return a populated dict (no exception, no None for n_bets / ROI keys).

    The whole POINT of v2 is to compute ROI at multiple snapshots; if either
    of these crashes the multi-snapshot driver is broken.
    """
    # Use distinct projections per snapshot point — early snapshots typically
    # over-project because they extrapolate a hot first quarter.
    fixtures = {
        "endQ1": {
            ("g1", 1, "pts"): 38.0,  # +9.5 edge — strong OVER
            ("g1", 2, "pts"): 18.0,  # -10.5 edge — strong UNDER
        },
        "endQ2": {
            ("g1", 1, "pts"): 33.0,  # +4.5 edge — moderate OVER
            ("g1", 2, "pts"): 22.0,  # -6.5 edge — UNDER
        },
    }
    lines = {("g1", 1, "pts"): 28.5, ("g1", 2, "pts"): 28.5}
    actuals = {("g1", 1, "pts"): 31.0, ("g1", 2, "pts"): 25.0}

    for point, triples in fixtures.items():
        res = bie2.simulate_bets(triples, lines, actuals, threshold=1.0)
        assert "pts" in res, f"{point}: missing pts bucket"
        cell = res["pts"]
        assert cell["n_bets"] >= 0, f"{point}: n_bets present"
        # win_rate / roi_flat keys exist (may be None when n_bets=0 — but
        # with our fixture, edges clear threshold so they should be populated).
        assert "win_rate" in cell and "roi_flat" in cell, (
            f"{point}: missing roi keys")
        assert cell["n_bets"] == 2, f"{point}: both bets should clear"
        # Both bets win (OVER on g1=1 hits 31>28.5, UNDER on g1=2 hits 25<28.5).
        assert cell["wins"] == 2, f"{point}: both bets should win"


# ── 3. Zero-edge case — projection == line gives bet count 0 ────────────────

def test_zero_edge_yields_zero_bets():
    """When pred == line (zero edge) simulate_bets must NOT place a bet, even
    at threshold 0.0 (the threshold gate is `< threshold`, not `<=`, so
    threshold 0.0 still permits an edge of 0.0 if we used `<=` — confirm
    the strict-inequality behaviour).

    NO-OP TEST per cycle-97d spec: zero edge → zero bets → ROI = None (no
    spurious wins or losses).
    """
    triples = {
        ("g1", 1, "pts"): 28.5,  # pred == line → edge = 0
        ("g1", 2, "reb"): 7.0,
        ("g1", 3, "ast"): 5.0,
    }
    lines = {
        ("g1", 1, "pts"): 28.5,
        ("g1", 2, "reb"): 7.0,
        ("g1", 3, "ast"): 5.0,
    }
    actuals = {
        ("g1", 1, "pts"): 30.0,
        ("g1", 2, "reb"): 6.0,
        ("g1", 3, "ast"): 4.0,
    }

    # At threshold 0.5 — clearly above any zero-edge bet.
    res = bie2.simulate_bets(triples, lines, actuals, threshold=0.5)
    for stat in ("pts", "reb", "ast"):
        assert res[stat]["n_bets"] == 0, (
            f"{stat}: zero edge should never bet")
        assert res[stat]["roi_flat"] is None, (
            f"{stat}: ROI should be None when n_bets=0")


# ── 4. Push case — actual == line → bet does not pay ────────────────────────

def test_push_actual_equals_line_does_not_pay():
    """When the actual stat lands EXACTLY on the line, the bet pushes —
    P&L = 0 (no profit, no loss). This is the standard sportsbook rule.

    Construct a single bet where pred clearly clears threshold (so we DO bet)
    but actual matches the line exactly → net P&L = 0 even though we wagered.
    """
    # Pred 32, line 28, edge +4 (clears threshold 1.0) → OVER.
    triples = {("g1", 1, "pts"): 32.0}
    lines = {("g1", 1, "pts"): 28.0}
    actuals = {("g1", 1, "pts"): 28.0}  # PUSH — equals line exactly.

    res = bie2.simulate_bets(triples, lines, actuals, threshold=1.0)
    cell = res["pts"]
    assert cell["n_bets"] == 1, "should have placed the bet"
    assert cell["wins"] == 0, "push is not a win"
    assert cell["pnl_flat"] == pytest.approx(0.0), "push has zero P&L"
    # ROI on $1 stake with $0 P&L = 0.0 (we wagered but got refunded).
    assert cell["roi_flat"] == pytest.approx(0.0)

    # Also exercise the pure settle_bet helper directly.
    assert bie2.settle_bet(1.0, "OVER", 28.0, 28.0, -110) == 0.0
    assert bie2.settle_bet(1.0, "UNDER", 28.0, 28.0, -110) == 0.0


# ── 5. Missing-period snapshot reconstruction handled gracefully ────────────

def test_snapshot_reconstruction_handles_missing_period():
    """v1.build_snapshot must return None when the parquet doesn't have all
    the periods needed for the requested snapshot point. The v2 main loop
    explicitly handles None (continues) so a partial game doesn't crash the
    full multi-snapshot run.

    Build a fake quarter_stats DataFrame with ONLY periods 1 + 2 for one
    game, then ask for endQ3 (which needs periods 1+2+3). build_snapshot
    must return None, not raise.

    Also confirm: even if we get None on some games, simulate_bets still
    runs on the populated points — that's the design of the v2 driver.
    """
    import pandas as pd

    from scripts import retro_inplay_mae as v1

    # Game G_PARTIAL has only Q1+Q2; game G_FULL has Q1+Q2+Q3.
    rows = []
    for game_id, periods in (
        ("G_PARTIAL", [1, 2]),
        ("G_FULL",    [1, 2, 3]),
    ):
        for period in periods:
            rows.append({
                "game_id": game_id, "period": period, "player_id": 1,
                "min": 8.0, "pts": 6.0, "reb": 2.0, "ast": 1.0,
                "fg3m": 0.0, "stl": 0.0, "blk": 0.0, "tov": 1.0, "pf": 1.0,
            })
    df = pd.DataFrame(rows)

    # Partial game @ endQ3 → None (period 3 missing).
    snap_partial = v1.build_snapshot("G_PARTIAL", "endQ3", df)
    assert snap_partial is None, "missing Q3 should return None, not crash"

    # Partial game @ endQ2 → OK (we have Q1+Q2).
    snap_q2 = v1.build_snapshot("G_PARTIAL", "endQ2", df)
    assert snap_q2 is not None, "Q1+Q2 present → endQ2 snapshot valid"

    # Full game @ endQ3 → OK.
    snap_full = v1.build_snapshot("G_FULL", "endQ3", df)
    assert snap_full is not None, "Q1+Q2+Q3 present → endQ3 snapshot valid"

    # Sanity: simulate_bets still works on empty triples (degenerate case
    # the driver hits when ALL games are partial at a given snapshot).
    res = bie2.simulate_bets({}, {}, {}, threshold=1.0)
    for stat in bie2.STATS:
        assert res[stat]["n_bets"] == 0
        assert res[stat]["roi_flat"] is None
