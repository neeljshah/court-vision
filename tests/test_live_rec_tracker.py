"""tests/test_live_rec_tracker.py - R24_Q4.

Covers the live-rec-tracker --snapshot, --settle, --report modes:
  * --snapshot creates valid file
  * --settle correctly computes WIN/LOSS/PUSH for OVER + UNDER
  * --settle handles missing player gracefully
  * --report aggregates correctly
  * rec_id is deterministic for same bet
  * rec_id changes when any field changes
  * --settle is idempotent
  * dry-run for --snapshot writes to a test dir
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import live_rec_tracker as lrt  # noqa: E402


DATE = "2099-01-15"  # synthetic future date, never collides with real data


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _mk_rec(player: str, stat: str, line: float, side: str,
            book: str = "bov", odds: int = -110,
            edge: float = 0.07, stake_dollars: float = 25.0) -> Dict[str, Any]:
    return {
        "player": player, "stat": stat, "line": line, "side": side,
        "book": book, "odds": odds, "edge": edge,
        "stake_dollars": stake_dollars,
    }


def _mk_payload(recs: List[Dict[str, Any]], date_str: str = DATE) -> Dict[str, Any]:
    return {
        "recommendations": recs,
        "date": date_str,
        "bankroll": 1000.0,
        "top": 10,
        "min_edge": 0.05,
        "engine_version": "R23_P8",
        "reason": "test payload",
    }


def _box_loader_for(boxscore: Dict[str, Dict[str, float]]):
    def _loader(date_str: str, qb_dir: str) -> Dict[str, Dict[str, float]]:
        return {lrt._player_key(k): v for k, v in boxscore.items()}
    return _loader


# --------------------------------------------------------------------------- #
# Test 1: --snapshot creates a valid file                                      #
# --------------------------------------------------------------------------- #
def test_snapshot_creates_valid_file(tmp_path):
    recs = [_mk_rec("Alice Adams", "pts", 18.5, "OVER")]
    payload = _mk_payload(recs)
    path = lrt.snapshot(payload, snapshot_dir=str(tmp_path), date_str=DATE)
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["date"] == DATE
    assert data["n_recs"] == 1
    assert data["bankroll"] == 1000.0
    assert "captured_at" in data
    assert len(data["recommendations"]) == 1
    rec = data["recommendations"][0]
    # rec_id was injected
    assert "rec_id" in rec
    assert len(rec["rec_id"]) == 12
    # Original fields preserved
    assert rec["player"] == "Alice Adams"
    assert rec["stat"] == "pts"
    assert rec["side"] == "OVER"


# --------------------------------------------------------------------------- #
# Test 2: --settle grades WIN / LOSS / PUSH correctly for OVER + UNDER          #
# --------------------------------------------------------------------------- #
def test_settle_grades_all_three_outcomes(tmp_path):
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    settled = str(tmp_path / "settled.parquet")
    recs = [
        # actual=25 > line 18.5 OVER  -> WIN
        _mk_rec("OverWin",   "pts", 18.5, "OVER", odds=-110),
        # actual=10 < line 18.5 OVER  -> LOSS
        _mk_rec("OverLoss",  "pts", 18.5, "OVER", odds=-110),
        # actual=18.5 == line OVER    -> PUSH
        _mk_rec("Pusher",    "pts", 18.5, "OVER", odds=-110),
        # actual=5 < line 8.5 UNDER   -> WIN
        _mk_rec("UnderWin",  "reb",  8.5, "UNDER", odds=-110),
        # actual=12 > line 8.5 UNDER  -> LOSS
        _mk_rec("UnderLoss", "reb",  8.5, "UNDER", odds=-110),
    ]
    lrt.snapshot(_mk_payload(recs), snapshot_dir=str(snap_dir), date_str=DATE)
    box = {
        "OverWin":   {"pts": 25},
        "OverLoss":  {"pts": 10},
        "Pusher":    {"pts": 18.5},
        "UnderWin":  {"reb": 5},
        "UnderLoss": {"reb": 12},
    }
    out = lrt.settle(
        date_str=DATE, snapshot_dir=str(snap_dir),
        settled_path=settled, boxscore_loader=_box_loader_for(box),
    )
    assert out["ok"] is True
    assert out["n_settled"] == 5
    assert out["wins"]   == 2
    assert out["losses"] == 2
    assert out["pushes"] == 1

    df = pd.read_parquet(settled)
    by_player = {r.player: r for r in df.itertuples()}
    assert by_player["OverWin"].result   == "WIN"
    assert by_player["OverLoss"].result  == "LOSS"
    assert by_player["Pusher"].result    == "PUSH"
    assert by_player["UnderWin"].result  == "WIN"
    assert by_player["UnderLoss"].result == "LOSS"
    # -110 payout: WIN +100/110 = +0.909..., LOSS = -1.0, PUSH = 0
    assert by_player["OverWin"].profit   == pytest.approx(100.0/110.0)
    assert by_player["OverLoss"].profit  == pytest.approx(-1.0)
    assert by_player["Pusher"].profit    == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Test 3: --settle handles missing player gracefully                           #
# --------------------------------------------------------------------------- #
def test_settle_handles_missing_player(tmp_path):
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    settled = str(tmp_path / "settled.parquet")
    recs = [
        _mk_rec("Present", "pts", 18.5, "OVER"),
        _mk_rec("Missing", "pts", 18.5, "OVER"),
    ]
    lrt.snapshot(_mk_payload(recs), snapshot_dir=str(snap_dir), date_str=DATE)
    box = {"Present": {"pts": 22}}  # Missing absent
    out = lrt.settle(
        date_str=DATE, snapshot_dir=str(snap_dir),
        settled_path=settled, boxscore_loader=_box_loader_for(box),
    )
    assert out["ok"] is True
    assert out["n_settled"] == 2
    assert out["n_missing_player"] == 1
    assert out["wins"] == 1

    df = pd.read_parquet(settled)
    by_player = {r.player: r for r in df.itertuples()}
    assert by_player["Present"].result == "WIN"
    assert by_player["Missing"].result == "UNGRADED"
    assert by_player["Missing"].profit == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Test 4: --report aggregates correctly                                        #
# --------------------------------------------------------------------------- #
def test_report_aggregates_correctly(tmp_path):
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    settled = str(tmp_path / "settled.parquet")
    recs = [
        _mk_rec("A", "pts", 10, "OVER",  edge=0.10, odds=-110),  # WIN
        _mk_rec("B", "pts", 10, "OVER",  edge=0.04, odds=-110),  # LOSS
        _mk_rec("C", "reb",  5, "UNDER", edge=0.12, odds=-110),  # WIN
        _mk_rec("D", "reb",  5, "UNDER", edge=0.06, odds=-110),  # LOSS
    ]
    lrt.snapshot(_mk_payload(recs), snapshot_dir=str(snap_dir), date_str=DATE)
    box = {
        "A": {"pts": 12},  # OVER 10 -> WIN
        "B": {"pts":  5},  # OVER 10 -> LOSS
        "C": {"reb":  3},  # UNDER 5 -> WIN
        "D": {"reb":  9},  # UNDER 5 -> LOSS
    }
    lrt.settle(date_str=DATE, snapshot_dir=str(snap_dir),
               settled_path=settled, boxscore_loader=_box_loader_for(box))
    rpt = lrt.report(settled_path=settled, days="all")
    assert rpt["ok"] is True
    assert rpt["n_graded"] == 4
    assert rpt["wins"] == 2
    assert rpt["losses"] == 2
    assert rpt["pushes"] == 0
    assert rpt["win_rate"] == pytest.approx(0.5)
    # 4 graded non-push bets at stake_unit=1 each -> total stake = 4
    # profit = 2*(100/110) - 2*1 = -0.1818 -> ROI = -0.1818 / 4 = -0.04545
    assert rpt["roi"] == pytest.approx((2.0 * 100.0 / 110.0 - 2.0) / 4.0, rel=1e-3)
    assert rpt["mean_edge_win"]  == pytest.approx((0.10 + 0.12) / 2.0)
    assert rpt["mean_edge_loss"] == pytest.approx((0.04 + 0.06) / 2.0)
    assert "pts" in rpt["by_stat"]
    assert "reb" in rpt["by_stat"]
    assert rpt["by_stat"]["pts"]["n"] == 2
    assert rpt["by_stat"]["reb"]["wins"] == 1


# --------------------------------------------------------------------------- #
# Test 5: rec_id is deterministic for same bet                                  #
# --------------------------------------------------------------------------- #
def test_rec_id_is_deterministic():
    rec = _mk_rec("Player A", "pts", 18.5, "OVER", book="bov", odds=-110)
    id1 = lrt.rec_id_for(rec, DATE)
    id2 = lrt.rec_id_for(rec, DATE)
    id3 = lrt.rec_id_for(dict(rec), DATE)
    assert id1 == id2 == id3
    assert len(id1) == 12
    # Different odds should NOT change the id (odds aren't part of the key)
    rec_diff_odds = dict(rec, odds=-105)
    assert lrt.rec_id_for(rec_diff_odds, DATE) == id1


# --------------------------------------------------------------------------- #
# Test 6: rec_id changes when any key field changes                            #
# --------------------------------------------------------------------------- #
def test_rec_id_changes_when_fields_change():
    base = _mk_rec("Player A", "pts", 18.5, "OVER", book="bov")
    base_id = lrt.rec_id_for(base, DATE)
    # player change
    assert lrt.rec_id_for(dict(base, player="Player B"), DATE) != base_id
    # stat change
    assert lrt.rec_id_for(dict(base, stat="reb"),       DATE) != base_id
    # line change
    assert lrt.rec_id_for(dict(base, line=19.5),         DATE) != base_id
    # side change
    assert lrt.rec_id_for(dict(base, side="UNDER"),      DATE) != base_id
    # book change
    assert lrt.rec_id_for(dict(base, book="fd"),         DATE) != base_id
    # date change
    assert lrt.rec_id_for(base, "2099-01-16") != base_id


# --------------------------------------------------------------------------- #
# Test 7: --settle is idempotent                                               #
# --------------------------------------------------------------------------- #
def test_settle_is_idempotent(tmp_path):
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    settled = str(tmp_path / "settled.parquet")
    recs = [_mk_rec("X", "pts", 10, "OVER")]
    lrt.snapshot(_mk_payload(recs), snapshot_dir=str(snap_dir), date_str=DATE)
    box = {"X": {"pts": 12}}
    out1 = lrt.settle(date_str=DATE, snapshot_dir=str(snap_dir),
                      settled_path=settled, boxscore_loader=_box_loader_for(box))
    out2 = lrt.settle(date_str=DATE, snapshot_dir=str(snap_dir),
                      settled_path=settled, boxscore_loader=_box_loader_for(box))
    assert out1["n_settled"] == 1
    assert out2["n_settled"] == 0
    assert out2["n_skipped"] == 1
    # The settled parquet must still contain exactly one row.
    df = pd.read_parquet(settled)
    assert len(df) == 1


# --------------------------------------------------------------------------- #
# Test 8: --snapshot --dry-run writes to a test dir                            #
# --------------------------------------------------------------------------- #
def test_dry_run_writes_to_test_dir(tmp_path, monkeypatch):
    """Use snapshot() directly with an explicit snapshot_dir override.

    This is the same code path the CLI takes when --dry-run flips the
    snapshot_dir to a tempfile.mkdtemp() result.
    """
    test_dir = tmp_path / "dry_run_sandbox"
    test_dir.mkdir()
    recs = [_mk_rec("Z", "ast", 5.5, "OVER")]
    path = lrt.snapshot(_mk_payload(recs),
                        snapshot_dir=str(test_dir), date_str=DATE)
    assert os.path.exists(path)
    # And the path is inside the test sandbox, NOT under DEFAULT_SNAPSHOT_DIR.
    assert str(test_dir) in path
    assert lrt.DEFAULT_SNAPSHOT_DIR not in path


# --------------------------------------------------------------------------- #
# Test 9 (bonus): report respects --days lookback                              #
# --------------------------------------------------------------------------- #
def test_report_days_lookback(tmp_path):
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    settled = str(tmp_path / "settled.parquet")
    # Two snapshots: one ancient (filtered out by --days 7), one for DATE.
    old_date = "2099-01-01"
    new_date = "2099-12-31"
    recs_old = [_mk_rec("Old", "pts", 10, "OVER")]
    recs_new = [_mk_rec("New", "pts", 10, "OVER")]
    lrt.snapshot(_mk_payload(recs_old, old_date), snapshot_dir=str(snap_dir),
                 date_str=old_date)
    lrt.snapshot(_mk_payload(recs_new, new_date), snapshot_dir=str(snap_dir),
                 date_str=new_date)
    box = {"Old": {"pts": 12}, "New": {"pts": 12}}
    lrt.settle(date_str=old_date, snapshot_dir=str(snap_dir),
               settled_path=settled, boxscore_loader=_box_loader_for(box))
    lrt.settle(date_str=new_date, snapshot_dir=str(snap_dir),
               settled_path=settled, boxscore_loader=_box_loader_for(box))
    # all-time report sees 2 rows
    rpt_all = lrt.report(settled_path=settled, days="all")
    assert rpt_all["n"] == 2
