"""
test_lineup_release_trigger.py -- Tests for the 30-min pre-tip lineup trigger.

Covers task 16-03 acceptance criterion: a scheduled trigger fires
run_daily_slate exactly 30 minutes before each game's tip-off, and logs
confirm reruns executed for all games in a simulated 3-game slate.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.lineup_release_trigger import (  # noqa: E402
    _PRE_TIP_MINUTES,
    _get_log_path,
    run_trigger,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_slate(base_utc: datetime, n: int = 3) -> list:
    """Build an n-game slate with staggered tip-off times."""
    games = []
    for i in range(n):
        games.append({
            "game_id":    f"002240{i:04d}",
            "home_team":  ["BOS", "LAL", "DEN"][i % 3],
            "away_team":  ["NYK", "GSW", "MIA"][i % 3],
            "tipoff_utc": base_utc + timedelta(hours=i),
        })
    return games


class _AdvancingClock:
    """Injectable clock that advances 5 minutes per call."""

    def __init__(self, start: datetime, step_minutes: int = 5):
        self.now = start
        self.step = timedelta(minutes=step_minutes)

    def __call__(self) -> datetime:
        current = self.now
        self.now += self.step
        return current


# ── tests ─────────────────────────────────────────────────────────────────────

def test_three_game_slate_fires_all(tmp_path, monkeypatch):
    """All 3 games in a simulated slate trigger exactly one rerun each."""
    monkeypatch.setattr(
        "scripts.lineup_release_trigger._OUTPUT_DIR", str(tmp_path)
    )

    base = datetime(2026, 5, 21, 23, 0, tzinfo=timezone.utc)
    games = _make_slate(base, n=3)

    fired: list = []

    def fake_slate(date_str: str, game_id: str) -> None:
        fired.append(game_id)

    # Start the clock 1h before the first trigger so it sweeps through all 3.
    clock = _AdvancingClock(base - timedelta(hours=1))

    count = run_trigger(
        date_str="2026-05-21",
        games=games,
        now_fn=clock,
        run_slate_fn=fake_slate,
        poll_interval=0,
    )

    assert count == 3
    assert sorted(fired) == sorted(g["game_id"] for g in games)


def test_log_records_every_rerun(tmp_path, monkeypatch):
    """The trigger log file contains one line per rerun."""
    monkeypatch.setattr(
        "scripts.lineup_release_trigger._OUTPUT_DIR", str(tmp_path)
    )

    base = datetime(2026, 5, 21, 23, 0, tzinfo=timezone.utc)
    games = _make_slate(base, n=3)
    clock = _AdvancingClock(base - timedelta(hours=1))

    run_trigger(
        date_str="2026-05-21",
        games=games,
        now_fn=clock,
        run_slate_fn=lambda date_str, game_id: None,
        poll_interval=0,
    )

    log_path = _get_log_path("2026-05-21")
    assert os.path.exists(log_path)
    with open(log_path, encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip()]
    assert len(lines) == 3
    for g in games:
        assert any(g["game_id"] in ln for ln in lines)


def test_fires_30_min_before_tipoff(tmp_path, monkeypatch):
    """A rerun does not fire before tipoff-30m and does fire at/after it."""
    monkeypatch.setattr(
        "scripts.lineup_release_trigger._OUTPUT_DIR", str(tmp_path)
    )

    tipoff = datetime(2026, 5, 21, 23, 0, tzinfo=timezone.utc)
    trigger_at = tipoff - timedelta(minutes=_PRE_TIP_MINUTES)
    games = [{
        "game_id": "0022400099", "home_team": "BOS",
        "away_team": "NYK", "tipoff_utc": tipoff,
    }]

    fire_times: list = []

    def fake_slate(date_str: str, game_id: str) -> None:
        fire_times.append(game_id)

    # Clock starts 7 min before the trigger, steps 5 min: first call is
    # before the window (no fire), second call is past it (fires).
    clock = _AdvancingClock(trigger_at - timedelta(minutes=7), step_minutes=5)

    count = run_trigger(
        date_str="2026-05-21",
        games=games,
        now_fn=clock,
        run_slate_fn=fake_slate,
        poll_interval=0,
    )

    assert count == 1
    assert fire_times == ["0022400099"]


def test_empty_slate_returns_zero(tmp_path, monkeypatch):
    """No games for the date -> zero reruns, no crash."""
    monkeypatch.setattr(
        "scripts.lineup_release_trigger._OUTPUT_DIR", str(tmp_path)
    )
    count = run_trigger(
        date_str="2026-05-21",
        games=[],
        now_fn=lambda: datetime(2026, 5, 21, tzinfo=timezone.utc),
        run_slate_fn=lambda date_str, game_id: None,
        poll_interval=0,
    )
    assert count == 0


def test_naive_tipoff_treated_as_utc(tmp_path, monkeypatch):
    """A tip-off datetime without tzinfo is coerced to UTC, not crashed on."""
    monkeypatch.setattr(
        "scripts.lineup_release_trigger._OUTPUT_DIR", str(tmp_path)
    )
    naive_tipoff = datetime(2026, 5, 21, 23, 0)  # no tzinfo
    games = [{
        "game_id": "0022400100", "home_team": "LAL",
        "away_team": "GSW", "tipoff_utc": naive_tipoff,
    }]
    clock = _AdvancingClock(
        datetime(2026, 5, 21, 22, 0, tzinfo=timezone.utc)
    )
    count = run_trigger(
        date_str="2026-05-21",
        games=games,
        now_fn=clock,
        run_slate_fn=lambda date_str, game_id: None,
        poll_interval=0,
    )
    assert count == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
