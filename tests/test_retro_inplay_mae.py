"""tests/test_retro_inplay_mae.py — cycle 93c (loop 5).

Unit tests for scripts/retro_inplay_mae.py. Each test is offline: it builds a
tiny in-memory pandas DataFrame mimicking ``data/player_quarter_stats.parquet``
plus an actuals/pregame dict, and validates each pure function in isolation.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as ri  # noqa: E402


# ── tiny fixture ──────────────────────────────────────────────────────────────

def _fake_qstats() -> pd.DataFrame:
    """4-period × 2-player tiny parquet, one game.

    Player A (HOME): 5/3/2/0 per Q on pts; Player B (AWAY): 8/4/4/4 per Q.
    """
    rows = []
    schema_keys = ("min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov",
                   "pf", "plus_minus")
    # Player A — home, played all 4 quarters.
    pa_pts = [5, 3, 2, 0]
    pa_reb = [2, 1, 1, 0]
    pa_ast = [1, 1, 1, 0]
    # Player B — away, played all 4 quarters.
    pb_pts = [8, 4, 4, 4]
    pb_reb = [3, 2, 1, 1]
    pb_ast = [2, 1, 1, 1]
    for q in (1, 2, 3, 4):
        rows.append({
            "game_id": "0099999999", "player_id": 1001, "period": q,
            "min": 10.0, "pts": pa_pts[q - 1], "reb": pa_reb[q - 1],
            "ast": pa_ast[q - 1], "fg3m": 0.0, "stl": 0.0, "blk": 0.0,
            "tov": 0.0, "pf": 1.0, "plus_minus": 0.0,
        })
        rows.append({
            "game_id": "0099999999", "player_id": 2002, "period": q,
            "min": 10.0, "pts": pb_pts[q - 1], "reb": pb_reb[q - 1],
            "ast": pb_ast[q - 1], "fg3m": 0.0, "stl": 0.0, "blk": 0.0,
            "tov": 0.0, "pf": 1.0, "plus_minus": 0.0,
        })
    df = pd.DataFrame(rows)
    return df


# ── 1. snapshot reconstruction produces valid live-schema dict ────────────────

def test_snapshot_endQ1_is_live_schema(monkeypatch):
    """end-of-Q1 snapshot has period=2, clock=12:00, top-level home/away keys."""
    df = _fake_qstats()

    # team_map lookup hits disk — stub it.
    def _stub_team_map(_gid):
        return ({1001: "HOM", 2002: "AWY"}, "HOM", "AWY")
    monkeypatch.setattr(ri, "load_team_map", _stub_team_map)

    snap = ri.build_snapshot("0099999999", "endQ1", df)
    assert snap is not None
    assert snap["period"] == 2
    assert snap["clock"] == "12:00"
    assert snap["home_team"] == "HOM"
    assert snap["away_team"] == "AWY"
    # Live schema demands top-level scores (no nested home={...}).
    assert "home_score" in snap and "away_score" in snap
    assert isinstance(snap["players"], list)
    assert len(snap["players"]) == 2
    # Every player has the canonical live.py keys.
    p0 = snap["players"][0]
    for k in ("player_id", "team", "min", "pts", "reb", "ast",
              "fg3m", "stl", "blk", "tov", "pf"):
        assert k in p0


# ── 2. quarter sums are correct (no double counting) ──────────────────────────

def test_q1_sums_no_double_count(monkeypatch):
    """endQ1 snapshot pts = Q1 only; endQ2 = Q1+Q2; endQ3 = Q1+Q2+Q3."""
    df = _fake_qstats()
    monkeypatch.setattr(
        ri, "load_team_map",
        lambda _gid: ({1001: "HOM", 2002: "AWY"}, "HOM", "AWY"))

    snap_q1 = ri.build_snapshot("0099999999", "endQ1", df)
    snap_q2 = ri.build_snapshot("0099999999", "endQ2", df)
    snap_q3 = ri.build_snapshot("0099999999", "endQ3", df)

    pa_q1 = next(p for p in snap_q1["players"] if p["player_id"] == 1001)
    pa_q2 = next(p for p in snap_q2["players"] if p["player_id"] == 1001)
    pa_q3 = next(p for p in snap_q3["players"] if p["player_id"] == 1001)

    # Player A pts/Q: [5, 3, 2, 0]
    assert pa_q1["pts"] == 5
    assert pa_q2["pts"] == 5 + 3
    assert pa_q3["pts"] == 5 + 3 + 2
    # Score totals = sum of team players' pts.
    pb_q3 = next(p for p in snap_q3["players"] if p["player_id"] == 2002)
    assert snap_q3["home_score"] == pa_q3["pts"]
    assert snap_q3["away_score"] == pb_q3["pts"]
    # min_q1..min_q4 are populated for bench-detection.
    assert pa_q3["min_q1"] == 10.0 and pa_q3["min_q4"] == 10.0


# ── 3. MAE calc handles missing actuals gracefully ────────────────────────────

def test_aggregate_mae_skips_missing_actuals():
    """A (pid, stat) with no actual must not crash or inflate counts."""
    snaps_per_game = {
        "G1": {
            "endQ1": {
                (1, "pts"): 20.0,         # actual present
                (1, "ast"): 8.0,          # actual missing — must be skipped
            },
        },
    }
    actuals = {"G1": {(1, "pts"): 24.0}}   # only pts known
    pregame = {("G1", 1, "pts"): 18.0}      # pregame for pts only

    table = ri.aggregate_mae(snaps_per_game, actuals, pregame)
    # pts: endQ1 has 1 entry (|20-24|=4); pregame has 1 (|18-24|=6).
    assert table["pts"]["endQ1"] == (1, 4.0)
    assert table["pts"]["pregame"] == (1, 6.0)
    # ast: no actuals → either absent or empty.
    assert "endQ1" not in table.get("ast", {})


# ── 4. end-to-end on fixture: per-stat MAE returned ───────────────────────────

def test_end_to_end_fixture_returns_per_stat_mae(monkeypatch):
    """Whole pipeline against the in-memory fixture: report has the right shape."""
    df = _fake_qstats()
    monkeypatch.setattr(
        ri, "load_team_map",
        lambda _gid: ({1001: "HOM", 2002: "AWY"}, "HOM", "AWY"))

    snaps_per_game = {"0099999999": {}}
    for point in ri.SNAPSHOT_POINTS:
        snap = ri.build_snapshot("0099999999", point, df)
        snaps_per_game["0099999999"][point] = ri.project_snapshot_to_finals(snap)

    actuals = {"0099999999": ri.actuals_for_game("0099999999", df)}
    # Player A full-game pts = 5+3+2+0 = 10; reb = 4; ast = 3.
    assert actuals["0099999999"][(1001, "pts")] == 10.0
    assert actuals["0099999999"][(1001, "reb")] == 4.0

    # A fake pregame baseline → constant 7.0 for every key.
    pregame = {("0099999999", pid, s): 7.0
                for pid in (1001, 2002) for s in ri.STATS}

    table = ri.aggregate_mae(snaps_per_game, actuals, pregame)
    # Every stat should have all three kinds plus pregame populated when n>0.
    assert "pts" in table
    assert "endQ1" in table["pts"] and "endQ3" in table["pts"]
    assert "pregame" in table["pts"]

    report = ri.build_report(table, n_games=1)
    assert "Verdict" in report
    assert "endQ3" in report
    # Header always contains the per-stat row for pts when n>0.
    assert "| pts |" in report
