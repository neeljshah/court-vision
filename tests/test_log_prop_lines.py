"""
test_log_prop_lines.py -- Tests for the prop-line history collector (PRED-18).

The collector accumulates real market lines per slate day so the per-game
models can eventually add a market-line feature (the move that breaks the
~0.48 R² ceiling).
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

from log_prop_lines import (  # noqa: E402
    get_market_line,
    load_line_history,
    snapshot_prop_lines,
)


def _source(rows):
    return lambda: list(rows)


def test_snapshot_appends_lines(tmp_path):
    """A day's lines are written to the history store."""
    hist = str(tmp_path / "prop_line_history.json")
    src = _source([
        {"player": "lebron james", "stat": "pts", "line": 25.5, "source": "pinnacle"},
        {"player": "lebron james", "stat": "reb", "line": 7.5, "source": "pinnacle"},
    ])
    added = snapshot_prop_lines("2026-05-21", hist, src)
    assert added == 2
    assert len(load_line_history(hist)) == 2


def test_snapshot_is_idempotent_per_day(tmp_path):
    """Re-running on the same date does not duplicate rows."""
    hist = str(tmp_path / "h.json")
    src = _source([{"player": "a", "stat": "pts", "line": 20.5, "source": "pinnacle"}])
    assert snapshot_prop_lines("2026-05-21", hist, src) == 1
    assert snapshot_prop_lines("2026-05-21", hist, src) == 0   # no dupes
    assert len(load_line_history(hist)) == 1


def test_snapshot_accumulates_across_days(tmp_path):
    """Lines from different dates accumulate into one growing history."""
    hist = str(tmp_path / "h.json")
    src = _source([{"player": "a", "stat": "pts", "line": 20.5, "source": "pinnacle"}])
    snapshot_prop_lines("2026-05-21", hist, src)
    snapshot_prop_lines("2026-05-22", hist, src)
    assert len(load_line_history(hist)) == 2


def test_get_market_line_returns_latest(tmp_path):
    """get_market_line returns the most recent line on or before a date."""
    hist = str(tmp_path / "h.json")
    snapshot_prop_lines("2026-05-21", hist,
                        _source([{"player": "Star", "stat": "pts", "line": 24.5,
                                  "source": "pinnacle"}]))
    snapshot_prop_lines("2026-05-23", hist,
                        _source([{"player": "Star", "stat": "pts", "line": 26.5,
                                  "source": "pinnacle"}]))
    assert get_market_line("Star", "pts", "2026-05-22", hist) == 24.5   # before update
    assert get_market_line("Star", "pts", "2026-05-24", hist) == 26.5   # after update
    assert get_market_line("Star", "pts", history_path=hist) == 26.5    # latest


def test_get_market_line_missing_returns_none(tmp_path):
    """No logged line for a player+stat -> None (feature treated as missing)."""
    hist = str(tmp_path / "h.json")
    snapshot_prop_lines("2026-05-21", hist,
                        _source([{"player": "a", "stat": "pts", "line": 20.5,
                                  "source": "pinnacle"}]))
    assert get_market_line("nobody", "pts", history_path=hist) is None
    assert get_market_line("a", "blk", history_path=hist) is None


def test_load_history_missing_file_is_empty():
    """An absent history file is an empty dataset, not an error."""
    assert load_line_history("/nonexistent/path/h.json") == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
