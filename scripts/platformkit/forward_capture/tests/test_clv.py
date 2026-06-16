"""Per-file test for forward_capture.clv. Run ONLY this file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/forward_capture/tests/test_clv.py -q

Asserts the load-bearing CLV honesty contract:
  - CLV is graded ONLY for a prediction whose pred_ts is strictly BEFORE the captured close;
  - a HINDSIGHT prediction (pred_ts at/after the close) is EXCLUDED, never graded;
  - the devigged close is the REAL captured 2-way price devigged via eval_gate/shin;
  - clv is reported in PROBABILITY space (= calibrated_prob - devig_close_prob), no $ field.

Hermetic: builds the archive in a tmp dir, then grades in-memory moves. No network/secret.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from scripts.platformkit.forward_capture.schema import OddsSnapshot  # noqa: E402
from scripts.platformkit.forward_capture import archive as A  # noqa: E402
from scripts.platformkit.forward_capture import clv as CLV  # noqa: E402
from scripts.platformkit.eval_gate.shin import shin_devig_decimal  # noqa: E402

_OPEN_TS = "2026-01-15T17:00:00+00:00"
_CLOSE_TS = "2026-01-15T23:00:00+00:00"


def _snap(side, price, ts):
    return OddsSnapshot("mock", "ml", "nba", "G1", side, price, ts)


def _moves(tmp_path):
    A.append_snapshots([
        _snap("home", 1.91, _OPEN_TS), _snap("away", 1.95, _OPEN_TS),
        _snap("home", 1.83, _CLOSE_TS), _snap("away", 2.05, _CLOSE_TS),
    ], base_dir=str(tmp_path))
    return A.build_all_line_moves("nba", base_dir=str(tmp_path))


def _pred(pred_id, pred_ts, prob=0.60):
    return {"pred_id": pred_id, "pred_ts": pred_ts, "calibrated_prob": prob,
            "game_id": "G1", "market": "ml", "book": "mock"}


def test_leak_free_prediction_is_graded(tmp_path):
    moves = _moves(tmp_path)
    res = CLV.grade_forward_clv([_pred("p1", "2026-01-15T18:00:00+00:00")], moves)
    assert len(res) == 1
    r = res[0]
    # devig is the REAL captured close (1.83/2.05) via shin, not invented
    expect, _z = shin_devig_decimal([1.83, 2.05])
    assert abs(r.devig_close_prob - expect[0]) < 1e-9
    assert abs(r.clv - (0.60 - expect[0])) < 1e-9      # probability space, no $


def test_hindsight_prediction_is_excluded(tmp_path):
    moves = _moves(tmp_path)
    # pred_ts AT the close -> hindsight -> excluded (strict pred_ts < close).
    at_close = CLV.grade_forward_clv([_pred("p_at", _CLOSE_TS)], moves)
    assert at_close == []
    # pred_ts AFTER the close -> hindsight -> excluded.
    after = CLV.grade_forward_clv([_pred("p_after", "2026-01-15T23:30:00+00:00")], moves)
    assert after == []


def test_mixed_batch_keeps_only_leak_free(tmp_path):
    moves = _moves(tmp_path)
    rows = [
        _pred("ok", "2026-01-15T18:00:00+00:00"),     # before close -> graded
        _pred("hindsight", "2026-01-16T00:00:00+00:00"),  # after close -> excluded
    ]
    res = CLV.grade_forward_clv(rows, moves)
    assert [r.pred_id for r in res] == ["ok"]


def test_compute_clv_returns_none_for_hindsight(tmp_path):
    moves = _moves(tmp_path)
    assert CLV.compute_clv(_pred("p", _CLOSE_TS), moves[0]) is None
    assert CLV.compute_clv(_pred("p", "2026-01-15T22:59:59+00:00"), moves[0]) is not None


def test_missing_devig_is_excluded(tmp_path):
    # a move with no two-way close legs cannot be devigged -> prediction excluded, never graded.
    move = {"game_id": "G1", "market": "ml", "book": "mock",
            "close_captured_at": _CLOSE_TS, "close_home_price": None,
            "close_away_price": None, "devig_close_prob": None}
    assert CLV.compute_clv(_pred("p", "2026-01-15T18:00:00+00:00"), move) is None


def test_no_dollar_field_on_result(tmp_path):
    moves = _moves(tmp_path)
    r = CLV.grade_forward_clv([_pred("p1", "2026-01-15T18:00:00+00:00")], moves)[0]
    rec = r.as_record()
    for banned in ("edge", "roi", "ev", "units", "stake", "kelly", "profit", "pnl"):
        assert banned not in rec
    assert "clv" in rec and "devig_close_prob" in rec       # calibration terms only


def test_to_grade_map_carries_real_close(tmp_path):
    moves = _moves(tmp_path)
    res = CLV.grade_forward_clv([_pred("p1", "2026-01-15T18:00:00+00:00")], moves)
    gmap = CLV.to_grade_map(res, outcomes={"p1": 1})
    assert "p1" in gmap
    assert gmap["p1"]["outcome"] == 1
    assert abs(gmap["p1"]["devig_close_prob"] - res[0].devig_close_prob) < 1e-12
