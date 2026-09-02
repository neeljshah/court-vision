"""scripts.platformkit.ingame.ticker_date -- ticker first pitch vs a live game's start.

WHY (S107, from S106). `inplay_capture_loop._scan_live_by_legs` bridges a Kalshi
ticker to a live ESPN game by TEAM PAIR. A series plays the SAME two teams on
consecutive days, so the team test alone binds the wrong night's game to a ticker
and files it under that ticker's key (S106: 122 of 227 scored MLB tickers hold more
than one real game). The guard that already lives in that function is day-granular
and compares the TICKER to TODAY -- it never looks at the matched game at all, and
it deliberately allows an ET-yesterday ticker, which is exactly the direction that
parks a series' NEXT game under the PREVIOUS day's ticker.

This module supplies the missing predicate: the ticker's OWN encoded first pitch
(ET, e.g. KXMLBGAME-26JUL061915NYMATL -> 2026-07-06 19:15 ET) against the matched
live game's start time. The caller keeps the nearest candidate inside
BRIDGE_WINDOW_H and skips the rest.

HONESTY: pure date arithmetic; no I/O, no fabrication. A ticker with no parseable
date+time, or a state with no start time, is honest NO INFO (None) -- the caller
then behaves exactly as it did before (missing != bad, verifier contract B3).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.

Per-file test: scripts/platformkit/ingame/test_inplay_capture_bridge.py
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

# A live game bound to a ticker whose first pitch is further away than this is a
# DIFFERENT game of the same series (or the other half of a doubleheader). 12 h is
# deliberately loose: it clears any single game's length plus a rain delay, and is
# still less than half the 24 h that separates consecutive games of a series.
BRIDGE_WINDOW_H = 12.0

# "-26JUL061915" -> (26, JUL, 06, 19, 15). A ticker with no HHMM (e.g.
# KXWCGAME-26JUN22USAMEX) simply does not match -> None -> no info.
_TICKER_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})")
_MONTHS = {m: i + 1 for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}

try:  # stdlib on 3.9+; absent only if the tz database is missing
    from zoneinfo import ZoneInfo  # type: ignore
    _ET: Any = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001 -- fixed EDT fallback (same call as close_join_mlb)
    # ponytail: the MLB/NBA in-play slate this bridge serves is EDT for all but a
    # handful of March/November dates, and a 1 h offset error cannot move a 12 h
    # window or reorder two candidates a full game apart. Add a tz table only if
    # zoneinfo is genuinely unavailable AND a winter slate ever runs through here.
    _ET = timezone(timedelta(hours=-4))


def ticker_first_pitch_utc(ref: Any) -> Optional[datetime]:
    """Scheduled first pitch encoded in a Kalshi ticker, as an aware UTC datetime.

    'KXMLBGAME-26JUL061915NYMATL' -> 2026-07-06 19:15 ET -> 2026-07-06T23:15Z.
    None when the ticker carries no parseable date+time. Pure; never raises."""
    try:
        m = _TICKER_RE.search(str(ref or "").upper())
        if m is None:
            return None
        mo = _MONTHS.get(m.group(2))
        hh, mi = int(m.group(4)), int(m.group(5))
        if mo is None or hh > 23 or mi > 59:
            return None
        local = datetime(2000 + int(m.group(1)), mo, int(m.group(3)), hh, mi,
                         tzinfo=_ET)
        return local.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def state_start_utc(state: Any) -> Optional[datetime]:
    """A live state's scheduled start as an aware UTC datetime, or None if absent.

    Reads the ADDITIVE `start_time` key ingame_live_state._extract copies straight
    off the ESPN event (ISO 8601, UTC). A state without it (npb/kbo, or any older
    cached shape) is honest no-info. Pure; never raises."""
    if not isinstance(state, dict):
        return None
    raw = str(state.get("start_time") or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def bridge_gap_hours(gid: Any, state: Any) -> Optional[float]:
    """|ticker first pitch - live game start| in hours, or None when either is absent.

    None is NO INFO, never "far": the caller must treat it as unchanged behavior."""
    tdt, sdt = ticker_first_pitch_utc(gid), state_start_utc(state)
    if tdt is None or sdt is None:
        return None
    return abs((sdt - tdt).total_seconds()) / 3600.0


def bridge_date_ok(gid: Any, state: Any,
                   window_h: float = BRIDGE_WINDOW_H) -> bool:
    """True iff this live game may be bridged onto this ticker (no info -> True)."""
    gap = bridge_gap_hours(gid, state)
    return gap is None or gap <= window_h


def _demo() -> None:
    """Self-check: python -m scripts.platformkit.ingame.ticker_date"""
    d1 = "KXMLBGAME-26JUL061915NYMATL"
    assert ticker_first_pitch_utc(d1) == datetime(2026, 7, 6, 23, 15, tzinfo=timezone.utc)
    assert ticker_first_pitch_utc("KXWCGAME-26JUN22USAMEX") is None
    same = {"start_time": "2026-07-06T23:15Z"}
    nextday = {"start_time": "2026-07-07T23:15Z"}
    assert bridge_gap_hours(d1, same) == 0.0
    assert bridge_gap_hours(d1, nextday) == 24.0
    assert bridge_date_ok(d1, same) and not bridge_date_ok(d1, nextday)
    assert bridge_gap_hours(d1, {}) is None and bridge_date_ok(d1, {})
    print("ticker_date self-check OK")


__all__ = ["BRIDGE_WINDOW_H", "ticker_first_pitch_utc", "state_start_utc",
           "bridge_gap_hours", "bridge_date_ok"]


if __name__ == "__main__":
    _demo()
