"""Leak-safety + correctness tests for src/ingest/prop_line_movement.py.

Uses a synthetic data/lines CSV in a tmp dir so the test does not depend on
the live slate. Verifies:
  1. movement is computed from pre-asof captures only;
  2. truncation-invariance: deleting captures at/after asof does not change the
     feature vector (the core leak guard);
  3. neutral vector with no asof and with <2 captures;
  4. feature_keys() matches the returned dict.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingest import prop_line_movement as plm  # noqa: E402


_ROWS = [
    # captured_at (UTC), book, game_id, player_id, player_name, stat, line, over, under, start_time
    ("2026-05-30T14:00+00:00", "dk", "G1", "", "Test Player", "pts", 25.5, -110, -110, "2026-05-31T00:00:00Z"),
    ("2026-05-30T16:00+00:00", "dk", "G1", "", "Test Player", "pts", 26.5, -115, -105, "2026-05-31T00:00:00Z"),
    ("2026-05-30T18:00+00:00", "dk", "G1", "", "Test Player", "pts", 27.5, -120, -100, "2026-05-31T00:00:00Z"),  # post-asof
]
_COLS = ["captured_at", "book", "game_id", "player_id", "player_name",
         "stat", "line", "over_price", "under_price", "start_time"]


@pytest.fixture()
def lines_dir(tmp_path, monkeypatch):
    d = tmp_path / "lines"
    d.mkdir()
    pd.DataFrame(_ROWS, columns=_COLS).to_csv(d / "2026-05-30_dk.csv", index=False)
    monkeypatch.setattr(plm, "_LINES_DIR", str(d))
    return d


def test_movement_from_pre_asof_only(lines_dir):
    # asof at 17:00 -> only the 14:00 and 16:00 captures count (25.5 -> 26.5)
    f = plm.get_prop_line_movement("Test Player", "pts", "2026-05-30",
                                   asof="2026-05-30T17:00+00:00")
    assert f["prop_n_captures"] == 2.0
    assert f["prop_line_open"] == 25.5
    assert f["prop_line_latest"] == 26.5
    assert f["prop_line_move"] == pytest.approx(1.0)
    assert f["prop_line_moved_flag"] == 1.0
    # over price moved -110 -> -115
    assert f["prop_over_price_move"] == pytest.approx(-5.0)


def test_truncation_invariance(lines_dir):
    """The leak guard: dropping the post-asof 18:00 capture must not change the
    feature vector computed at asof=17:00."""
    before = plm.get_prop_line_movement("Test Player", "pts", "2026-05-30",
                                        asof="2026-05-30T17:00+00:00")
    # rewrite the CSV without the future (18:00) row
    pd.DataFrame(_ROWS[:2], columns=_COLS).to_csv(
        lines_dir / "2026-05-30_dk.csv", index=False)
    after = plm.get_prop_line_movement("Test Player", "pts", "2026-05-30",
                                       asof="2026-05-30T17:00+00:00")
    assert before == after


def test_no_asof_is_neutral(lines_dir):
    f = plm.get_prop_line_movement("Test Player", "pts", "2026-05-30", asof=None)
    assert f == dict.fromkeys(plm.feature_keys(), 0.0)


def test_single_capture_no_movement(lines_dir):
    # asof at 15:00 -> only the 14:00 capture visible; no movement derivable
    f = plm.get_prop_line_movement("Test Player", "pts", "2026-05-30",
                                   asof="2026-05-30T15:00+00:00")
    assert f["prop_n_captures"] == 1.0
    assert f["prop_line_move"] == 0.0
    assert f["prop_line_open"] == 25.5


def test_unknown_player_is_neutral(lines_dir):
    f = plm.get_prop_line_movement("Nobody Here", "pts", "2026-05-30",
                                   asof="2026-05-30T17:00+00:00")
    assert f == dict.fromkeys(plm.feature_keys(), 0.0)


def test_feature_keys_match(lines_dir):
    f = plm.get_prop_line_movement("Test Player", "pts", "2026-05-30",
                                   asof="2026-05-30T17:00+00:00")
    assert set(f.keys()) == set(plm.feature_keys())
