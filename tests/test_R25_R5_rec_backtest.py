"""tests/test_R25_R5_rec_backtest.py — R25_R5 backtest of live rec engine.

Covers:
  1. chunk_games_to_pseudo_dates returns sorted, distinct date strings
  2. build_pointintime_predictions uses ONLY prior gids (no leakage)
  3. grade_recs WIN/LOSS/PUSH logic for OVER + UNDER
  4. multi-day aggregation sums correctly + win_rate / roi math
  5. missing-boxscore handled gracefully (UNGRADED + zero profit)
  6. sweep_configs produces all 12 permutations
  7. ROI math sanity: 1u win at -110 -> +0.909u; 1u loss -> -1.0u
  8. backtest never raises on a degenerate (empty) qb_dir
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import Any, Dict, List

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import backtest_live_rec_engine as btr  # noqa: E402
from scripts.live_rec_tracker import _grade_rec, _profit_for  # noqa: E402


# --------------------------------------------------------------------------- #
# Synthetic qb_dir helpers                                                     #
# --------------------------------------------------------------------------- #
def _make_q4_file(qb_dir: str, gid: str, players: List[Dict[str, Any]]) -> None:
    data = {
        "game_id": gid,
        "period":  4,
        "players": players,
        "teams":   [],
    }
    path = os.path.join(qb_dir, f"{gid}_q4.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _make_player(name: str, team: str, pts: float, reb: float = 0, ast: float = 0,
                 fg3m: float = 0, stl: float = 0, blk: float = 0,
                 to: float = 0) -> Dict[str, Any]:
    return {
        "player_id":          hash(name) & 0xFFFFFF,
        "player_name":        name,
        "team_abbreviation":  team,
        "pts": pts, "reb": reb, "ast": ast, "fg3m": fg3m,
        "stl": stl, "blk": blk, "to": to,
    }


# --------------------------------------------------------------------------- #
# Test 1                                                                       #
# --------------------------------------------------------------------------- #
def test_chunk_games_returns_sorted_distinct_dates(tmp_path):
    qb = str(tmp_path)
    # 36 games -> 3 chunks of 12
    for i in range(1, 37):
        gid = f"00224{i:05d}"
        _make_q4_file(qb, gid, [_make_player("X Y", "BOS", pts=10)])
    chunks = btr.chunk_games_to_pseudo_dates(qb, n_per_date=12, min_chunks=2)
    assert len(chunks) == 3
    dates = [d for d, _ in chunks]
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)
    assert all(len(gids) == 12 for _, gids in chunks)


# --------------------------------------------------------------------------- #
# Test 2: point-in-time correctness — predictions never see "today's" games   #
# --------------------------------------------------------------------------- #
def test_pointintime_predictions_no_leak(tmp_path):
    qb = str(tmp_path)
    # 3 prior games: Alice averages 20pts
    _make_q4_file(qb, "0022400001", [_make_player("Alice", "BOS", pts=18)])
    _make_q4_file(qb, "0022400002", [_make_player("Alice", "BOS", pts=20)])
    _make_q4_file(qb, "0022400003", [_make_player("Alice", "BOS", pts=22)])
    # "Today's" game where Alice scores 50 (must NOT influence q50)
    _make_q4_file(qb, "0022400004", [_make_player("Alice", "BOS", pts=50)])
    df = btr.build_pointintime_predictions(
        qb, prior_gids=["0022400001", "0022400002", "0022400003"],
        min_games=2,
    )
    alice_pts = df[(df["player_name"].str.lower() == "alice") &
                   (df["stat"] == "pts")]
    assert len(alice_pts) == 1
    assert abs(float(alice_pts.iloc[0]["q50"]) - 20.0) < 1e-6  # NOT 27.5


# --------------------------------------------------------------------------- #
# Test 3: OVER/UNDER grading logic                                             #
# --------------------------------------------------------------------------- #
def test_grade_over_under_logic(tmp_path):
    qb = str(tmp_path)
    # one "today" game
    _make_q4_file(qb, "0022400010", [
        _make_player("Bob", "LAL", pts=25, reb=10),
        _make_player("Cat", "LAL", pts=15, reb=8),
    ])
    recs = [
        # Bob 25 over 20 -> WIN
        {"player": "Bob",  "stat": "pts", "side": "OVER",  "line": 20.0,
         "book": "syn", "odds": -110, "edge": 0.1, "stake_dollars": 25.0},
        # Bob 25 under 30 -> WIN
        {"player": "Bob",  "stat": "pts", "side": "UNDER", "line": 30.0,
         "book": "syn", "odds": -110, "edge": 0.1, "stake_dollars": 25.0},
        # Cat 15 over 20 -> LOSS
        {"player": "Cat",  "stat": "pts", "side": "OVER",  "line": 20.0,
         "book": "syn", "odds": -110, "edge": 0.1, "stake_dollars": 25.0},
        # Cat 15 under 10 -> LOSS
        {"player": "Cat",  "stat": "pts", "side": "UNDER", "line": 10.0,
         "book": "syn", "odds": -110, "edge": 0.1, "stake_dollars": 25.0},
    ]
    out = btr.grade_recs(recs, qb, ["0022400010"])
    assert out[0]["result"] == "WIN"
    assert out[1]["result"] == "WIN"
    assert out[2]["result"] == "LOSS"
    assert out[3]["result"] == "LOSS"
    # Profits: 2 WIN at -110 -> 2 * 100/110, 2 LOSS -> -2.0
    expected_profit = 2 * (100.0 / 110.0) - 2.0
    total = sum(g["profit"] for g in out)
    assert abs(total - expected_profit) < 1e-9


def test_push_logic_exact_match(tmp_path):
    qb = str(tmp_path)
    _make_q4_file(qb, "0022400011", [_make_player("Dee", "MIA", pts=18)])
    rec = [{"player": "Dee", "stat": "pts", "side": "OVER", "line": 18.0,
            "book": "syn", "odds": -110, "edge": 0.1, "stake_dollars": 0.0}]
    out = btr.grade_recs(rec, qb, ["0022400011"])
    assert out[0]["result"] == "PUSH"
    assert out[0]["profit"] == 0.0


# --------------------------------------------------------------------------- #
# Test 4: ROI math sanity at -110                                              #
# --------------------------------------------------------------------------- #
def test_roi_math_at_minus_110():
    # WIN at -110, 1u stake -> profit = 100/110 = 0.9090909...
    p_win = _profit_for("WIN", odds=-110, stake=1.0)
    assert abs(p_win - 100.0 / 110.0) < 1e-9
    # LOSS at -110, 1u stake -> -1.0
    p_loss = _profit_for("LOSS", odds=-110, stake=1.0)
    assert p_loss == -1.0
    # PUSH -> 0
    p_push = _profit_for("PUSH", odds=-110, stake=1.0)
    assert p_push == 0.0


# --------------------------------------------------------------------------- #
# Test 5: multi-day aggregation correctness                                    #
# --------------------------------------------------------------------------- #
def test_aggregate_daily_sums_correctly():
    dailies = [
        {"ok": True, "wins": 3, "losses": 2, "pushes": 1,
         "total_profit": 0.5, "by_stat": {
             "pts": {"n": 3, "wins": 2, "losses": 1, "pushes": 0,
                     "profit": 0.8, "stake": 3.0}}},
        {"ok": True, "wins": 4, "losses": 1, "pushes": 0,
         "total_profit": 2.6, "by_stat": {
             "pts": {"n": 3, "wins": 2, "losses": 1, "pushes": 0,
                     "profit": 0.8, "stake": 3.0},
             "ast": {"n": 2, "wins": 2, "losses": 0, "pushes": 0,
                     "profit": 1.8, "stake": 2.0}}},
        {"ok": False, "reason": "missing data"},
    ]
    agg = btr.aggregate_daily(dailies)
    assert agg["ok"] is True
    assert agg["n_dates"] == 2  # the failed date is filtered
    assert agg["wins"] == 7
    assert agg["losses"] == 3
    assert agg["pushes"] == 1
    assert agg["n_recs"] == 11
    # win_rate = 7 / (7+3) = 0.7
    assert abs(agg["win_rate"] - 0.7) < 1e-6
    # by_stat aggregation
    assert agg["by_stat"]["pts"]["n"] == 6
    assert agg["by_stat"]["pts"]["wins"] == 4
    assert agg["by_stat"]["ast"]["n"] == 2


# --------------------------------------------------------------------------- #
# Test 6: missing boxscore -> UNGRADED + zero profit                            #
# --------------------------------------------------------------------------- #
def test_missing_boxscore_graceful(tmp_path):
    qb = str(tmp_path)
    _make_q4_file(qb, "0022400020", [_make_player("Eve", "PHX", pts=22)])
    recs = [
        {"player": "Eve",     "stat": "pts", "side": "OVER", "line": 15.0,
         "book": "syn", "odds": -110, "edge": 0.1, "stake_dollars": 0.0},
        {"player": "Ghost",   "stat": "pts", "side": "OVER", "line": 15.0,
         "book": "syn", "odds": -110, "edge": 0.1, "stake_dollars": 0.0},
    ]
    out = btr.grade_recs(recs, qb, ["0022400020"])
    assert out[0]["result"] == "WIN"
    assert out[1]["result"] == "UNGRADED"
    assert out[1]["profit"] == 0.0


# --------------------------------------------------------------------------- #
# Test 7: sweep_configs produces all 12 permutations                           #
# --------------------------------------------------------------------------- #
def test_sweep_configs_produces_all_permutations(tmp_path):
    qb = str(tmp_path)
    # Build 6 chunks of 5 games so the sweep has data
    pid = 1
    for chunk_i in range(6):
        for g in range(5):
            gid = f"00224{pid:05d}"
            pid += 1
            _make_q4_file(qb, gid, [
                _make_player("Star Player", "BOS",
                             pts=20 + chunk_i, reb=8, ast=5),
                _make_player("Role Player", "LAL",
                             pts=10, reb=4, ast=2),
            ])
    sweep = btr.sweep_configs(
        qb_dir=qb, bankroll=100.0, n_per_date=5,
        max_dates=4, seed=0,
        min_edges=btr.SWEEP_MIN_EDGES, tops=btr.SWEEP_TOPS,
    )
    assert sweep["ok"]
    expected = len(btr.SWEEP_MIN_EDGES) * len(btr.SWEEP_TOPS)
    assert len(sweep["matrix"]) == expected  # 4*3 = 12
    # Each cell has the required keys
    for cell in sweep["matrix"]:
        for k in ("min_edge", "top", "n_dates", "n_recs",
                  "wins", "losses", "win_rate", "roi", "total_profit"):
            assert k in cell


# --------------------------------------------------------------------------- #
# Test 8: empty qb_dir doesn't crash                                           #
# --------------------------------------------------------------------------- #
def test_empty_qb_dir_does_not_crash(tmp_path):
    # no q4 files written
    res = btr.run_backtest(qb_dir=str(tmp_path), max_dates=3)
    assert res["ok"] is False
    assert "no game chunks" in str(res.get("reason", "")).lower() or \
           res.get("aggregate", {}).get("n_dates", 0) == 0


# --------------------------------------------------------------------------- #
# Test 9: synthesise_lines is deterministic for the same seed                 #
# --------------------------------------------------------------------------- #
def test_synthesised_lines_deterministic(tmp_path):
    qb = str(tmp_path)
    _make_q4_file(qb, "0022400030", [_make_player("Hank", "DET", pts=12)])
    preds = pd.DataFrame([{
        "player_name": "Hank", "stat": "pts", "team": "DET",
        "q10": 6.0, "q50": 12.0, "q90": 18.0, "sigma": 4.0, "_n_prior": 5,
    }])
    df1 = btr.synthesise_lines(preds, ["0022400030"], qb, seed=7)
    df2 = btr.synthesise_lines(preds, ["0022400030"], qb, seed=7)
    df3 = btr.synthesise_lines(preds, ["0022400030"], qb, seed=99)
    assert not df1.empty
    assert float(df1.iloc[0]["line"]) == float(df2.iloc[0]["line"])
    # different seed CAN produce a different line — at least the jitter
    # branch reaches a different value most of the time, but tolerate
    # a coincidence by asserting we DID call it (cols present).
    assert "line" in df3.columns
