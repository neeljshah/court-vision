"""Tests for scripts/live_inplay_daemon.py — cycle 93e (loop 5).

All tests run offline. We monkey-patch ``discover_games_for_today`` and
``fetch_live_boxscore`` so no NBA endpoint is ever touched.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import List
from unittest.mock import MagicMock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.live_inplay_daemon as lid  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _payload(game_id: str = "0022400123", status: int = 2,
              period: int = 2, clock: str = "PT05M42.00S",
              home_score: int = 56, away_score: int = 48) -> dict:
    """A minimal cdn.nba.com payload with one LIVE-LAL + one starter."""
    return {
        "game": {
            "gameId":     game_id,
            "gameStatus": status,
            "period":     period,
            "gameClock":  clock,
            "homeTeam": {
                "teamTricode": "LAL",
                "score":       home_score,
                "players": [
                    {
                        "personId":  2544,
                        "name":      "LeBron James",
                        "starter":   True,
                        "statistics": {
                            "minutes": "PT14M30.00S",
                            "points": 12, "reboundsTotal": 4,
                            "assists": 6, "threePointersMade": 2,
                            "steals": 1, "blocks": 0, "turnovers": 1,
                            "foulsPersonal": 2,
                        },
                    }
                ],
            },
            "awayTeam": {
                "teamTricode": "DEN",
                "score":       away_score,
                "players": [
                    {
                        "personId":  203999,
                        "name":      "Nikola Jokic",
                        "starter":   True,
                        "statistics": {
                            "minutes": "PT15M00.00S",
                            "points": 14, "reboundsTotal": 7,
                            "assists": 5, "threePointersMade": 1,
                            "steals": 0, "blocks": 1, "turnovers": 2,
                            "foulsPersonal": 1,
                        },
                    }
                ],
            },
        }
    }


@pytest.fixture
def silent_logger():
    """A logger that just collects records — no stdout/file noise."""
    log = logging.getLogger("live_inplay_daemon_test")
    log.handlers.clear()
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.NullHandler())
    return log


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_single_iteration_writes_snapshot_and_inplay_rows(
        monkeypatch, tmp_path, silent_logger):
    """One iteration with one LIVE game: 1 snapshot + N in-play rows."""
    live_dir = tmp_path / "live"
    pred_dir = tmp_path / "predictions"
    live_dir.mkdir()
    pred_dir.mkdir()

    monkeypatch.setattr(lid.lgp, "discover_games_for_today",
                         lambda date=None: ["0022400123"])
    monkeypatch.setattr(lid.lgp, "fetch_live_boxscore",
                         lambda gid, **kw: _payload(game_id=gid))

    result = lid.run_one_iteration(
        date_str="2026-05-24",
        live_dir=str(live_dir),
        pred_dir=str(pred_dir),
        sleep_fn=lambda _s: None,
        logger=silent_logger,
    )

    assert result.active_count == 1
    assert result.snapshots_written == 1
    # 2 players * 7 stats = 14 in-play rows
    assert result.inplay_rows == 14
    assert not result.had_error

    # Snapshot json exists
    snaps = list(live_dir.iterdir())
    assert len(snaps) == 1
    assert snaps[0].name.startswith("0022400123_")

    # Ledger has the right path + a header + 14 rows
    ledger = pred_dir / "2026-05-24_inplay.csv"
    assert ledger.exists()
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 15  # 1 header + 14 rows
    assert lines[0].startswith("date,game_id,player_id")


def test_no_active_games_no_writes_no_crash(monkeypatch, tmp_path, silent_logger):
    """Offseason / no slate must be a clean no-op."""
    live_dir = tmp_path / "live"
    pred_dir = tmp_path / "predictions"
    live_dir.mkdir()
    pred_dir.mkdir()

    monkeypatch.setattr(lid.lgp, "discover_games_for_today",
                         lambda date=None: [])

    result = lid.run_one_iteration(
        date_str="2026-05-24",
        live_dir=str(live_dir),
        pred_dir=str(pred_dir),
        sleep_fn=lambda _s: None,
        logger=silent_logger,
    )
    assert result.active_count == 0
    assert result.snapshots_written == 0
    assert result.inplay_rows == 0
    assert not result.had_error
    assert list(live_dir.iterdir()) == []
    assert list(pred_dir.iterdir()) == []


def test_transient_api_error_retries_then_succeeds(
        monkeypatch, tmp_path, silent_logger):
    """First discover_fn call raises; second call returns a slate. Daemon recovers."""
    live_dir = tmp_path / "live"
    pred_dir = tmp_path / "predictions"
    live_dir.mkdir()
    pred_dir.mkdir()

    calls = {"n": 0}

    def flaky_discover(date=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated 503")
        return ["0022400123"]

    monkeypatch.setattr(lid.lgp, "discover_games_for_today", flaky_discover)
    monkeypatch.setattr(lid.lgp, "fetch_live_boxscore",
                         lambda gid, **kw: _payload(game_id=gid))

    sleep_mock = MagicMock()
    result = lid.run_one_iteration(
        date_str="2026-05-24",
        live_dir=str(live_dir),
        pred_dir=str(pred_dir),
        sleep_fn=sleep_mock,
        logger=silent_logger,
    )

    assert calls["n"] == 2
    assert result.active_count == 1
    assert result.snapshots_written == 1
    assert result.inplay_rows == 14
    assert not result.had_error
    # Retry sleep must have been invoked once with RETRY_SLEEP_S.
    assert sleep_mock.call_args_list[0].args == (lid.RETRY_SLEEP_S,)


def test_dry_run_writes_nothing(monkeypatch, tmp_path, silent_logger):
    """--dry-run discovers the slate but never persists."""
    live_dir = tmp_path / "live"
    pred_dir = tmp_path / "predictions"
    live_dir.mkdir()
    pred_dir.mkdir()

    monkeypatch.setattr(lid.lgp, "discover_games_for_today",
                         lambda date=None: ["0022400123"])
    # If something hits the network in dry-run, fail loudly.
    monkeypatch.setattr(lid.lgp, "fetch_live_boxscore",
                         lambda gid, **kw: pytest.fail("fetch in dry-run"))

    result = lid.run_one_iteration(
        date_str="2026-05-24",
        live_dir=str(live_dir),
        pred_dir=str(pred_dir),
        dry_run=True,
        sleep_fn=lambda _s: None,
        logger=silent_logger,
    )
    assert result.snapshots_written == 0
    assert result.inplay_rows == 0
    assert list(live_dir.iterdir()) == []
    assert list(pred_dir.iterdir()) == []


def test_max_iterations_one_exits_cleanly(
        monkeypatch, tmp_path, silent_logger):
    """--max-iterations 1 must run exactly one iteration and write a sentinel."""
    live_dir = tmp_path / "live"
    pred_dir = tmp_path / "predictions"
    live_dir.mkdir()
    pred_dir.mkdir()
    sentinel = tmp_path / "live_daemon.stopped"

    monkeypatch.setattr(lid, "STOPPED_SENTINEL", str(sentinel))
    monkeypatch.setattr(lid.lgp, "discover_games_for_today",
                         lambda date=None: [])

    sleep_mock = MagicMock()
    iters = lid.run_daemon(
        interval_min=0.0,
        max_iterations=1,
        auto_stop_iters=0,       # disable so it doesn't trip first
        date_str="2026-05-24",
        live_dir=str(live_dir),
        pred_dir=str(pred_dir),
        sleep_fn=sleep_mock,
        logger=silent_logger,
    )
    assert iters == 1
    assert sentinel.exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
