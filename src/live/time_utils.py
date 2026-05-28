"""time_utils.py — shared time helpers for the live-betting system.

Why a dedicated module: Railway/Fly/most cloud runtimes ship containers in UTC,
but NBA slate dates, scraping windows, and CSV filenames are anchored to ET.
A naive ``date.today()`` rolls past the slate ~5 hours before midnight ET, so
both the producer (parallel_scraper writing CSVs) and the consumer (pregame
EV engine reading them) must agree on the same ET-based date.
"""
from __future__ import annotations

from datetime import date as _date, datetime as _datetime, timedelta, timezone


def slate_date() -> _date:
    """Today's NBA slate date in America/New_York."""
    try:
        from zoneinfo import ZoneInfo
        return _datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        # tzdata pkg in requirements-web.txt makes the path above always work;
        # this fallback (UTC-5h, EST) is only for absent-tzdata environments.
        return (_datetime.now(timezone.utc) - timedelta(hours=5)).date()
