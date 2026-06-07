"""tests/test_time_utils.py — guard the ET slate-date helper.

Regression for the UTC-clock-on-Railway bug that froze the pregame EV scanner
when UTC rolled past midnight ET. The helper must return the calendar date in
America/New_York regardless of system clock zone.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from src.live.time_utils import slate_date


def test_slate_date_returns_et_when_utc_clock_is_next_day():
    """The classic Railway scenario: it's 1 AM UTC (= 8 PM ET previous day).
    slate_date() must return the ET date, not the UTC date."""
    # 2026-05-27 03:00 UTC = 2026-05-26 23:00 ET (still the same NBA slate)
    fake_utc = datetime(2026, 5, 27, 3, 0, tzinfo=timezone.utc)

    with patch("src.live.time_utils._datetime") as mock_dt:
        # ZoneInfo path: now(ZoneInfo("America/New_York")) returns ET local.
        mock_dt.now.return_value = fake_utc.astimezone(_et())
        assert slate_date().isoformat() == "2026-05-26"


def test_slate_date_handles_midnight_et_boundary():
    """Right after midnight ET, the slate date should advance even though
    UTC is still on the previous calendar day's slate."""
    # 2026-05-27 04:30 UTC = 2026-05-27 00:30 ET (new slate)
    fake_utc = datetime(2026, 5, 27, 4, 30, tzinfo=timezone.utc)
    with patch("src.live.time_utils._datetime") as mock_dt:
        mock_dt.now.return_value = fake_utc.astimezone(_et())
        assert slate_date().isoformat() == "2026-05-27"


def _et():
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/New_York")
