"""tests/test_game_tip_detector.py — covers tip-time resolution from
schedule JSON, the scoreboard fallback, the default fallback, the
quarter_box detection short-circuit, and the ``is_pregame`` grace
period."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import game_tip_detector as gtd  # noqa: E402


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Redirect all on-disk paths to a tmp_path sandbox."""
    sched = tmp_path / "season_games.json"
    qbox = tmp_path / "quarter_box"
    cache_tpl = str(tmp_path / "tip_times_{date}.json")
    qbox.mkdir()
    monkeypatch.setattr(gtd, "SEASON_SCHEDULE", str(sched))
    monkeypatch.setattr(gtd, "QBOX_DIR", str(qbox))
    monkeypatch.setattr(gtd, "TIP_CACHE_TEMPLATE", cache_tpl)
    return {"sched": sched, "qbox": qbox, "tmp": tmp_path}


# ---------- tip time resolution ----------
def test_tip_time_resolved_from_season_json(isolated_paths):
    sched = isolated_paths["sched"]
    sched.write_text(json.dumps({
        "rows": [{
            "game_id": "0042400317",
            "game_date": "2026-05-26",
            "home_team": "OKC",
            "away_team": "SAS",
            "tip_time": "8:30 pm ET",
        }],
    }))
    tip = gtd.get_tip_time("0042400317")
    assert tip is not None
    # 8:30 PM EDT on 2026-05-26 = 00:30 UTC on 2026-05-27
    assert tip.tzinfo is not None
    assert tip.year == 2026 and tip.month == 5 and tip.day == 27
    assert tip.hour == 0 and tip.minute == 30


def test_tip_time_iso_format_in_schedule(isolated_paths):
    sched = isolated_paths["sched"]
    sched.write_text(json.dumps({
        "rows": [{
            "game_id": "0042400317",
            "game_date": "2026-05-26",
            "tip_time_utc": "2026-05-27T00:30:00+00:00",
        }],
    }))
    tip = gtd.get_tip_time("0042400317")
    assert tip == datetime(2026, 5, 27, 0, 30, tzinfo=timezone.utc)


def test_tip_time_falls_back_to_scoreboard(isolated_paths):
    """When the schedule row has no tip_time, scoreboardv2 fills it in."""
    sched = isolated_paths["sched"]
    sched.write_text(json.dumps({
        "rows": [{
            "game_id": "0042400317",
            "game_date": "2026-05-26",
            "home_team": "OKC",
            "away_team": "SAS",
        }],
    }))
    with mock.patch.object(gtd, "_tip_from_scoreboard") as mock_sb:
        mock_sb.return_value = datetime(2026, 5, 27, 0, 30,
                                          tzinfo=timezone.utc)
        tip = gtd.get_tip_time("0042400317", game_date="2026-05-26")
    assert tip == datetime(2026, 5, 27, 0, 30, tzinfo=timezone.utc)
    mock_sb.assert_called_once_with("0042400317", "2026-05-26")


def test_tip_time_default_for_unknown_game(isolated_paths):
    """No schedule row, no scoreboard hit -> default 8:30 PM ET."""
    with mock.patch.object(gtd, "_tip_from_scoreboard", return_value=None):
        tip = gtd.get_tip_time("9999999999", game_date="2026-05-26")
    assert tip is not None
    assert tip.year == 2026 and tip.month == 5 and tip.day == 27
    assert tip.hour == 0 and tip.minute == 30


def test_parse_et_clock_handles_am_pm():
    """The ET clock parser must handle both AM and PM correctly."""
    morning = gtd._parse_et_clock("11:00 am ET", "2026-05-26")
    assert morning is not None
    # 11 AM EDT = 15:00 UTC
    assert morning.hour == 15
    afternoon = gtd._parse_et_clock("2:30 pm ET", "2026-05-26")
    assert afternoon is not None
    # 2:30 PM EDT = 18:30 UTC
    assert afternoon.hour == 18 and afternoon.minute == 30


# ---------- is_pregame ----------
def test_is_pregame_true_one_hour_before_tip(isolated_paths):
    sched = isolated_paths["sched"]
    sched.write_text(json.dumps({
        "rows": [{
            "game_id": "0042400317",
            "game_date": "2026-05-26",
            "tip_time_utc": "2026-05-27T00:30:00+00:00",
        }],
    }))
    one_hour_before = datetime(2026, 5, 26, 23, 30, tzinfo=timezone.utc)
    assert gtd.is_pregame("0042400317", now=one_hour_before) is True


def test_is_pregame_false_after_tip_plus_grace(isolated_paths):
    """5 minutes after tip + grace -> in-play."""
    sched = isolated_paths["sched"]
    sched.write_text(json.dumps({
        "rows": [{
            "game_id": "0042400317",
            "game_date": "2026-05-26",
            "tip_time_utc": "2026-05-27T00:30:00+00:00",
        }],
    }))
    # tip + 6 min > tip + GRACE_MINUTES (5)
    after = datetime(2026, 5, 27, 0, 30, tzinfo=timezone.utc) \
        + timedelta(minutes=gtd.GRACE_MINUTES + 1)
    assert gtd.is_pregame("0042400317", now=after) is False


def test_is_pregame_within_grace_period(isolated_paths):
    """Right at tip + 3 min should still be pregame (within 5 min grace)."""
    sched = isolated_paths["sched"]
    sched.write_text(json.dumps({
        "rows": [{
            "game_id": "0042400317",
            "game_date": "2026-05-26",
            "tip_time_utc": "2026-05-27T00:30:00+00:00",
        }],
    }))
    within = datetime(2026, 5, 27, 0, 33, tzinfo=timezone.utc)
    assert gtd.is_pregame("0042400317", now=within) is True


def test_quarter_box_short_circuits_pregame(isolated_paths):
    """If the q1 box file already exists, is_pregame returns False even
    if we're 'before' the scheduled tip — the game has actually started."""
    qbox = isolated_paths["qbox"]
    (qbox / "0042400317_q1.json").write_text("{}")
    # Even an hour before the scheduled tip, we're now in-play.
    one_hour_before = datetime(2026, 5, 26, 23, 30, tzinfo=timezone.utc)
    assert gtd.is_pregame(
        "0042400317",
        game_date="2026-05-26",
        now=one_hour_before,
    ) is False


def test_quarter_box_exists_detects_any_match(isolated_paths):
    qbox = isolated_paths["qbox"]
    assert gtd.quarter_box_exists("0042400317") is False
    (qbox / "0042400317_q1.json").write_text("{}")
    assert gtd.quarter_box_exists("0042400317") is True


def test_in_play_quarter_returns_latest(isolated_paths):
    qbox = isolated_paths["qbox"]
    assert gtd.in_play_quarter("0042400317") is None
    (qbox / "0042400317_q1.json").write_text("{}")
    (qbox / "0042400317_q2.json").write_text("{}")
    assert gtd.in_play_quarter("0042400317") == "q2"


def test_write_today_tip_cache_roundtrip(isolated_paths):
    sched = isolated_paths["sched"]
    sched.write_text(json.dumps({
        "rows": [{
            "game_id": "0042400317",
            "game_date": "2026-05-26",
            "tip_time_utc": "2026-05-27T00:30:00+00:00",
        }],
    }))
    path = gtd.write_today_tip_cache("2026-05-26", ["0042400317"])
    assert os.path.exists(path)
    payload = json.loads(open(path).read())
    assert "0042400317" in payload
    # Cached tip should still round-trip into get_tip_time.
    tip = gtd.get_tip_time("0042400317", game_date="2026-05-26")
    assert tip == datetime(2026, 5, 27, 0, 30, tzinfo=timezone.utc)
