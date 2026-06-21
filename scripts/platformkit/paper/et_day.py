"""scripts.platformkit.paper.et_day -- the SHARED Eastern-Time day-boundary helper.

The paper slate is an ET slate. "Today" and the daily-P&L bucket MUST be cut on the
America/New_York calendar day, NOT UTC: at 8pm ET the UTC clock has already rolled to
00:00 of the next date, so a UTC day-label rolls the daily bankroll a full ET-day early
and blends the late-evening slate into the wrong day (confirmed live: paper_bankroll.json
showed day=2026-06-21 while ET was still the 20th).

This one module is imported by paper_today, bankroll_daemon and pnl_series so the curve,
today.json and the bankroll all agree on the same ET day. Prefers stdlib zoneinfo; if the
tz database is unavailable it falls back to a fixed ET offset (EST -5 / EDT -4 via a
simple US DST rule) so the boundary is still ET, never UTC.

HONESTY: pure date arithmetic only; nothing fabricated, no I/O, no secrets.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.

Per-file test: covered by scripts/platformkit/paper/test_paper_today.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

_ET_NAME = "America/New_York"

try:  # stdlib on 3.9+; absent only if the tz database is missing
    from zoneinfo import ZoneInfo  # type: ignore
    _ET = ZoneInfo(_ET_NAME)
except Exception:  # noqa: BLE001 -- fall back to a fixed-offset ET below
    _ET = None


def _second_sunday_march(year: int) -> datetime:
    d = datetime(year, 3, 8, tzinfo=timezone.utc)  # earliest possible 2nd Sunday
    while d.weekday() != 6:
        d += timedelta(days=1)
    return d


def _first_sunday_november(year: int) -> datetime:
    d = datetime(year, 11, 1, tzinfo=timezone.utc)
    while d.weekday() != 6:
        d += timedelta(days=1)
    return d


def _fixed_et_offset(dt_utc: datetime) -> timezone:
    """ET offset (EDT -4 / EST -5) for *dt_utc* via the US DST rule (zoneinfo fallback).

    DST runs 2nd Sunday of March 07:00 UTC -> 1st Sunday of November 06:00 UTC. This is
    only used when zoneinfo is unavailable; it keeps the boundary ET, never UTC.
    """
    start = _second_sunday_march(dt_utc.year).replace(hour=7)
    end = _first_sunday_november(dt_utc.year).replace(hour=6)
    is_dst = start <= dt_utc < end
    return timezone(timedelta(hours=-4 if is_dst else -5))


def to_et(dt_utc: datetime) -> datetime:
    """Convert an aware UTC datetime to ET (zoneinfo if present, else fixed offset)."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    if _ET is not None:
        return dt_utc.astimezone(_ET)
    return dt_utc.astimezone(_fixed_et_offset(dt_utc))


def now_et_day(now_utc: Optional[datetime] = None) -> str:
    """The current ET calendar date as YYYY-MM-DD (the betting 'today')."""
    base = now_utc if now_utc is not None else datetime.now(timezone.utc)
    return to_et(base).strftime("%Y-%m-%d")


def et_day_of(ts: str) -> str:
    """The ET calendar date (YYYY-MM-DD) of an ISO timestamp string.

    Parses common ISO forms (with or without a trailing 'Z' / offset). A naive
    timestamp is read as UTC. A value that cannot be parsed falls back to its first
    10 chars (date prefix) so a malformed row never raises -- never fabricated.
    """
    raw = str(ts or "").strip()
    if not raw:
        return "unknown"
    # A bare calendar date (YYYY-MM-DD, no time component) is ALREADY an ET day:
    # parsing it as naive-UTC-midnight then shifting to ET wrongly rolls it back a
    # full day (00:00 UTC == 20:00 prev-day ET). A date has no time to convert.
    if (len(raw) == 10 and raw[4] == "-" and raw[7] == "-"
            and raw[:4].isdigit() and raw[5:7].isdigit() and raw[8:10].isdigit()):
        return raw
    parsed = _parse_iso(raw)
    if parsed is None:
        return raw[:10] if len(raw) >= 10 else "unknown"
    return to_et(parsed).strftime("%Y-%m-%d")


def _parse_iso(raw: str) -> Optional[datetime]:
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


__all__ = ["now_et_day", "et_day_of", "to_et"]
