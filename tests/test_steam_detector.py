"""
test_steam_detector.py -- Tests for the Pinnacle steam detector (16.7-02).

Acceptance criterion: the steam detector reads pinnacle line history, fires a
STEAM event for a qualifying move (>0.5 pt in <5 min), and emits an event
dict with direction and velocity.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data.line_timing import detect_steam  # noqa: E402
from src.data.pinnacle_monitor import get_line_history, record_line_snapshot  # noqa: E402


def _series(base: datetime, points) -> list:
    """Build a snapshot series from (minute_offset, line) pairs."""
    return [
        {"timestamp": (base + timedelta(minutes=m)).isoformat(), "line": ln}
        for m, ln in points
    ]


def test_qualifying_up_move_fires_over_steam():
    """A +0.8 pt move in 3 min fires a STEAM event in the 'over' direction."""
    base = datetime(2026, 5, 21, 23, 0, tzinfo=timezone.utc)
    history = _series(base, [(0, 25.0), (3, 25.8)])
    event = detect_steam(history)
    assert event is not None
    assert event["event"] == "STEAM"
    assert event["direction"] == "over"
    assert event["magnitude"] == 0.8
    assert event["velocity"] > 0


def test_qualifying_down_move_fires_under_steam():
    """A -0.7 pt move fires a STEAM event in the 'under' direction."""
    base = datetime(2026, 5, 21, 23, 0, tzinfo=timezone.utc)
    history = _series(base, [(0, 18.0), (2, 17.3)])
    event = detect_steam(history)
    assert event is not None
    assert event["direction"] == "under"
    assert event["velocity"] < 0


def test_slow_move_does_not_fire():
    """A 0.8 pt move spread over 12 min (> 5 min window) does NOT qualify."""
    base = datetime(2026, 5, 21, 23, 0, tzinfo=timezone.utc)
    history = _series(base, [(0, 25.0), (12, 25.8)])
    assert detect_steam(history) is None


def test_small_move_does_not_fire():
    """A 0.3 pt move (below the 0.5 pt threshold) does NOT qualify."""
    base = datetime(2026, 5, 21, 23, 0, tzinfo=timezone.utc)
    history = _series(base, [(0, 25.0), (2, 25.3)])
    assert detect_steam(history) is None


def test_detects_steam_within_window_of_noisy_series():
    """A qualifying burst inside a longer noisy series is still detected."""
    base = datetime(2026, 5, 21, 22, 0, tzinfo=timezone.utc)
    history = _series(base, [
        (0, 25.0), (10, 25.1), (20, 25.0), (21, 25.1),
        (22, 25.9),   # +0.8 in 1 min -> steam
        (35, 26.0),
    ])
    event = detect_steam(history)
    assert event is not None
    assert event["direction"] == "over"
    # detected at the snapshot completing the burst
    assert event["detected_at"].startswith(
        (base + timedelta(minutes=22)).isoformat()[:16]
    )


def test_replay_through_pinnacle_history_store(tmp_path):
    """End-to-end: snapshots recorded to the pinnacle history store replay
    into a STEAM event."""
    hist_path = str(tmp_path / "pinnacle_line_history.json")
    base = datetime(2026, 5, 21, 23, 0, tzinfo=timezone.utc)
    for m, ln in [(0, 30.0), (2, 30.4), (4, 31.0)]:
        record_line_snapshot(
            "Jayson Tatum", "pts", ln,
            ts=(base + timedelta(minutes=m)).isoformat(),
            history_path=hist_path,
        )
    history = get_line_history("Jayson Tatum", "pts", history_path=hist_path)
    assert len(history) == 3
    event = detect_steam(history)
    assert event is not None
    assert event["event"] == "STEAM"
    assert event["direction"] == "over"


def test_empty_history_returns_none():
    """An empty or single-snapshot history yields no event."""
    assert detect_steam([]) is None
    assert detect_steam([{"timestamp": "2026-05-21T23:00:00+00:00", "line": 25.0}]) is None


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
