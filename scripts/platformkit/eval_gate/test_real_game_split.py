"""Per-file test for scripts.platformkit.eval_gate.real_game_split.

  python -m pytest scripts/platformkit/eval_gate/test_real_game_split.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.eval_gate import real_game_split as rgs


def _rows(specs):
    return pd.DataFrame([{"game_id": g, "ts": t, "state_summary": s} for g, t, s in specs])


def _state(inning, home=0, away=0):
    return "home_score=%s away_score=%s inning=%s half=top outs=0" % (home, away, inning)


def test_parse_state_and_missing():
    assert rgs.parse_state("home_score=3.0 away_score=5.0 inning=2 half=top") == (2, 3.0, 5.0)
    assert rgs.parse_state("") == (None, None, None)
    assert rgs.parse_state(None) == (None, None, None)
    assert rgs.parse_state("home_score=1 away_score=2") == (None, 1.0, 2.0)


def test_single_game_monotone_stays_one():
    frame = _rows([("T", "2026-07-05T00:00:00Z", _state(1)),
                   ("T", "2026-07-05T01:00:00Z", _state(4, 1, 0)),
                   ("T", "2026-07-05T03:30:00Z", _state(9, 2, 3))])
    out, summary = rgs.assign_real_game_seq(frame)
    assert list(out["real_game_seq"]) == [1, 1, 1]
    assert summary["n_real_games"] == 1 and summary["n_multi"] == 0
    assert summary["n_ticks_reassigned"] == 0


def test_inning_decrease_splits():
    frame = _rows([("T", "2026-07-05T00:00:00Z", _state(7, 2, 3)),
                   ("T", "2026-07-05T01:00:00Z", _state(2, 1, 1))])
    out, summary = rgs.assign_real_game_seq(frame)
    assert list(out["real_game_seq"]) == [1, 2]
    assert summary["boundary_reasons"] == {"inning_decrease": 1}


def test_return_to_inning_1_across_a_non_state_row_still_splits():
    """A blank state row must not hide the reset: 3 -> (no state) -> 1 splits."""
    frame = _rows([("T", "2026-07-05T00:00:00Z", _state(1)),
                   ("T", "2026-07-05T01:00:00Z", _state(3, 1, 0)),
                   ("T", "2026-07-05T02:00:00Z", ""),
                   ("T", "2026-07-05T03:00:00Z", _state(1))])
    out, summary = rgs.assign_real_game_seq(frame)
    assert list(out["real_game_seq"]) == [1, 1, 1, 2]
    assert summary["boundary_reasons"] == {"inning_decrease": 1}


def test_ts_gap_splits_even_when_innings_rise():
    frame = _rows([("T", "2026-07-05T00:00:00Z", _state(1)),
                   ("T", "2026-07-05T18:00:00Z", _state(2, 1, 1))])
    out, summary = rgs.assign_real_game_seq(frame)
    assert list(out["real_game_seq"]) == [1, 2]
    assert summary["boundary_reasons"] == {"ts_gap": 1}


def test_score_reset_splits_without_an_inning_reset():
    frame = _rows([("T", "2026-07-05T00:00:00Z", _state(5, 4, 2)),
                   ("T", "2026-07-05T00:30:00Z", _state(5, 0, 0))])
    out, summary = rgs.assign_real_game_seq(frame)
    assert list(out["real_game_seq"]) == [1, 2]
    assert summary["boundary_reasons"] == {"score_reset": 1}


def test_no_state_rows_inherit_and_never_split():
    frame = _rows([("T", "2026-07-05T00:00:00Z", ""),
                   ("T", "2026-07-05T01:00:00Z", _state(1)),
                   ("T", "2026-07-09T22:00:00Z", "")])
    out, summary = rgs.assign_real_game_seq(frame)
    assert list(out["real_game_seq"]) == [1, 1, 1]
    assert summary["n_real_games"] == 1


def test_seq_is_per_game_id_and_row_order_preserved():
    frame = _rows([("A", "2026-07-05T02:00:00Z", _state(5, 1, 1)),
                   ("B", "2026-07-05T00:00:00Z", _state(1)),
                   ("A", "2026-07-05T00:00:00Z", _state(1)),
                   ("A", "2026-07-05T03:00:00Z", _state(1))])
    out, summary = rgs.assign_real_game_seq(frame)
    # row order unchanged; A's tick order is 00:00 -> 02:00 -> 03:00
    assert list(out["ts"]) == list(frame["ts"])
    assert list(out["real_game_seq"]) == [1, 1, 1, 2]
    assert summary["n_game_ids"] == 2 and summary["n_real_games"] == 3
    assert summary["n_multi"] == 1


def test_cluster_ids_and_missing_column():
    frame = _rows([("T", "2026-07-05T00:00:00Z", _state(1))])
    out, _ = rgs.assign_real_game_seq(frame)
    assert list(rgs.cluster_ids(out)) == ["T#1"]
    with pytest.raises(ValueError):
        rgs.assign_real_game_seq(frame.drop(columns=["state_summary"]))


def test_gap_hours_is_a_knob_not_a_constant():
    frame = _rows([("T", "2026-07-05T00:00:00Z", _state(1)),
                   ("T", "2026-07-05T07:00:00Z", _state(2, 1, 0))])
    assert list(rgs.assign_real_game_seq(frame)[0]["real_game_seq"]) == [1, 2]
    out, _ = rgs.assign_real_game_seq(frame, gap_hours=12.0)
    assert list(out["real_game_seq"]) == [1, 1]
