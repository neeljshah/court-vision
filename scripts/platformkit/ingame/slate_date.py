"""Shared MLB baseball-date resolution for live-slate callers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def slate_date(now: Optional[datetime] = None) -> str:
    """Return the MLB baseball date, per gumbo_mlb_poller.py lines 107-116."""
    current = now or datetime.now(timezone.utc)
    return (current.astimezone(timezone.utc) - timedelta(hours=10)).strftime("%Y-%m-%d")
