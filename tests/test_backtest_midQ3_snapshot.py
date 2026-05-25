"""tests/test_backtest_midQ3_snapshot.py — cycle 99d (loop 5).

4 tests for backtest_midQ3_snapshot:
  1. Synthetic snapshot construction halves Q3 stats correctly (fraction=0.5).
  2. Sensitivity sweep emits 3 separate ROI tables, one per fraction.
  3. Empty-Q3 case — player with no Q3 row → zero Q3 contribution and no crash.
  4. Result schema matches cycle 97d's simulate_bets cell format
     (n_bets/wins/roi_flat/roi_kelly/win_rate keys).

All tests are pure data-driven — they avoid loading the real parquet and
build small synthetic DataFrames so the suite runs in <1 sec without nba_api.
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from scripts import backtest_midQ3_snapshot as midq3  # noqa: E402


# ── shared fixture ───────────────────────────────────────────────────────────

def _make_qstats_df(include_q3: bool = True):
    """3-quarter parquet for one game / two players. Q1+Q2 identical to give
    a clean baseline; Q3 numbers chosen to make the fraction-scaling math
    arithmetically obvious in test assertions.
    """
    import pandas as pd

    rows = []
    # Player 1: 10 pts each Q (30 pre-Q3, 10 in Q3 if Q3 present)
    # Player 2: 4 pts each Q (12 pre-Q3, 4 in Q3 if Q3 present)
    for period in (1, 2):
        rows.append({
            "game_id": "G1", "period": period, "player_id": 1,
            "min": 10.0, "pts": 10.0, "reb": 4.0, "ast": 2.0,
            "fg3m": 1.0, "stl": 0.0, "blk": 0.0, "tov": 1.0, "pf": 0.0,
        })
        rows.append({
            "game_id": "G1", "period": period, "player_id": 2,
            "min": 8.0, "pts": 4.0, "reb": 2.0, "ast": 1.0,
            "fg3m": 0.0, "stl": 1.0, "blk": 0.0, "tov": 0.0, "pf": 1.0,
        })
    if include_q3:
        rows.append({
            "game_id": "G1", "period": 3, "player_id": 1,
            "min": 8.0, "pts": 10.0, "reb": 2.0, "ast": 4.0,
            "fg3m": 2.0, "stl": 0.0, "blk": 0.0, "tov": 0.0, "pf": 1.0,
        })
        # Player 2 sits Q3 → row OMITTED entirely (proxies "no Q3 minutes").
    return pd.DataFrame(rows)


# Stub out load_team_map so the test doesn't require the file fixtures
# under data/cache/quarter_box / data/nba/. Replaces the v1 helper for the
# duration of these tests.

@pytest.fixture(autouse=True)
def _stub_team_map(monkeypatch):
    monkeypatch.setattr(
        midq3.v1, "load_team_map",
        lambda gid: ({1: "AAA", 2: "BBB"}, "AAA", "BBB"),
    )


# ── 1. Synthetic snapshot halves Q3 stats correctly ─────────────────────────

def test_synthetic_snapshot_halves_q3_stats():
    """fraction=0.5 should give each player Q1+Q2 + half of their Q3 row.

    Player 1 pts: 10 + 10 (Q1+Q2) + 10*0.5 = 25 pts.
    Player 1 ast: 2 + 2 + 4*0.5             = 6 ast.
    Player 1 reb: 4 + 4 + 2*0.5             = 9 reb.
    Player 1 min: 10 + 10 + 8*0.5           = 24 min.
    Player 2 (no Q3 row): 4 + 4 + 0 = 8 pts (zero Q3 contribution).
    Snapshot period=3 (Q3 IN PROGRESS), clock="6:00".
    """
    df = _make_qstats_df(include_q3=True)
    snap = midq3.build_midq3_synthetic_snapshot("G1", df, fraction=0.5)
    assert snap is not None, "snapshot should build with all 3 periods present"
    assert snap["period"] == 3
    assert snap["clock"] == "6:00"

    by_pid = {p["player_id"]: p for p in snap["players"]}
    p1 = by_pid[1]
    assert p1["pts"] == pytest.approx(25.0)
    assert p1["reb"] == pytest.approx(9.0)
    assert p1["ast"] == pytest.approx(6.0)
    assert p1["min"] == pytest.approx(24.0)
    assert p1["fg3m"] == pytest.approx(3.0)  # 1+1 + 2*0.5 = 3.0

    # min_q1 / min_q2 unchanged (full quarters elapsed); min_q3 = half.
    assert p1["min_q1"] == pytest.approx(10.0)
    assert p1["min_q2"] == pytest.approx(10.0)
    assert p1["min_q3"] == pytest.approx(4.0)
    assert p1["min_q4"] == pytest.approx(0.0)


# ── 2. Sensitivity sweep produces 3 separate ROI tables ─────────────────────

def test_sensitivity_sweep_produces_three_tables(monkeypatch):
    """compute_roi_table over fractions (0.25, 0.5, 0.75) must return a dict
    with all three keys, and EACH key maps to a per-stat simulate_bets dict.

    With the fixture (only 2 players, 1 game), no live model is actually
    invoked — we monkey-patch project_midq3_via_live_engine to return a
    deterministic projection that scales with fraction so the test can
    assert the structure WITHOUT depending on the real cycle-88 projector.
    """
    df = _make_qstats_df(include_q3=True)

    # Deterministic stub projector: project_final = current_pts * 1.6 (a
    # fixed "remaining" multiplier). Other stats simply 0 to keep the math
    # transparent.
    def _stub_projector(snap):
        out = {}
        for p in snap["players"]:
            out[(int(p["player_id"]), "pts")] = p["pts"] * 1.6
            for s in ("reb", "ast", "fg3m", "stl", "blk", "tov"):
                out[(int(p["player_id"]), s)] = 0.0
        return out
    monkeypatch.setattr(midq3, "project_midq3_via_live_engine", _stub_projector)

    # Line + actuals — make pts edges clear threshold so we see actual ROI cells.
    lines = {("G1", 1, "pts"): 25.0, ("G1", 2, "pts"): 8.0}
    actuals = {("G1", 1, "pts"): 50.0, ("G1", 2, "pts"): 14.0}

    out = midq3.compute_roi_table(
        midq3.SENSITIVITY_FRACTIONS, ["G1"], df, lines, actuals, threshold=1.0)
    assert set(out.keys()) == set(midq3.SENSITIVITY_FRACTIONS)
    for frac in midq3.SENSITIVITY_FRACTIONS:
        cells = out[frac]
        assert "pts" in cells, f"fraction={frac}: pts cell present"
        # Each cell carries the canonical simulate_bets schema.
        for k in ("n_bets", "wins", "roi_flat", "roi_kelly", "win_rate"):
            assert k in cells["pts"], f"fraction={frac}: missing key {k}"


# ── 3. Empty Q3 — player with no Q3 row contributes zero, no crash ──────────

def test_empty_q3_player_contributes_zero():
    """Player who did not appear in Q3 must show Q1+Q2 only (zero Q3 stat)
    in the synthetic snapshot, and the snapshot builder must NOT crash on
    that row absence.

    Also exercises the all-Q3-missing case: when nobody has a Q3 row at
    all, build_midq3_synthetic_snapshot returns None (Q1+Q2+Q3 subset
    requirement fails).
    """
    df = _make_qstats_df(include_q3=True)
    snap = midq3.build_midq3_synthetic_snapshot("G1", df, fraction=0.5)
    assert snap is not None
    by_pid = {p["player_id"]: p for p in snap["players"]}
    # Player 2 has no Q3 row → Q3 contribution is 0 across all stats.
    p2 = by_pid[2]
    assert p2["pts"] == pytest.approx(8.0)   # 4 + 4 + 0
    assert p2["reb"] == pytest.approx(4.0)
    assert p2["ast"] == pytest.approx(2.0)
    assert p2["stl"] == pytest.approx(2.0)
    assert p2["fg3m"] == pytest.approx(0.0)
    assert p2["min_q3"] == pytest.approx(0.0)

    # When the parquet has NO Q3 rows at all → snapshot returns None
    # (Q1+Q2+Q3 subset requirement isn't satisfied).
    df_no_q3 = _make_qstats_df(include_q3=False)
    assert midq3.build_midq3_synthetic_snapshot(
        "G1", df_no_q3, fraction=0.5) is None


# ── 4. Result schema matches cycle 97d format ────────────────────────────────

def test_result_schema_matches_cycle_97d(monkeypatch):
    """compute_roi_table's per-fraction cells must use the SAME key set that
    cycle 97d's simulate_bets emits, so the cycle 99d report can pivot
    midQ3 vs endQ2 vs endQ3 on the exact same column names.

    The keys we expect (per cycle 95d simulate_bets contract):
        n_bets, wins, roi_flat, roi_kelly, win_rate,
        stake_flat, pnl_flat, stake_kelly, pnl_kelly.
    """
    df = _make_qstats_df(include_q3=True)
    # Stub projector with deterministic edges that fire bets in pts only.
    def _stub_projector(snap):
        out = {}
        for p in snap["players"]:
            out[(int(p["player_id"]), "pts")] = p["pts"] * 1.6
            for s in ("reb", "ast", "fg3m", "stl", "blk", "tov"):
                out[(int(p["player_id"]), s)] = 0.0
        return out
    monkeypatch.setattr(midq3, "project_midq3_via_live_engine", _stub_projector)

    lines = {("G1", 1, "pts"): 25.0, ("G1", 2, "pts"): 8.0}
    actuals = {("G1", 1, "pts"): 50.0, ("G1", 2, "pts"): 14.0}

    out = midq3.compute_roi_table(
        (0.5,), ["G1"], df, lines, actuals, threshold=1.0)
    pts_cell = out[0.5]["pts"]
    expected_keys = {
        "n_bets", "wins", "roi_flat", "roi_kelly", "win_rate",
        "stake_flat", "pnl_flat", "stake_kelly", "pnl_kelly",
    }
    assert expected_keys.issubset(pts_cell.keys()), (
        f"midQ3 cell missing schema keys: {expected_keys - set(pts_cell)}")

    # Cross-check the exact schema against cycle 95d's simulate_bets output
    # on the same inputs — ensures no key drift.
    from scripts import backtest_inplay_edge as bie
    direct = bie.simulate_bets(
        {("G1", 1, "pts"): 25.0 * 1.6, ("G1", 2, "pts"): 8.0 * 1.6},
        lines, actuals, threshold=1.0,
    )
    assert set(direct["pts"].keys()) == set(pts_cell.keys())
