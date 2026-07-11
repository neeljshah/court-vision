"""scripts.platformkit.grade_paper_dates -- MLB ticker date extraction + the
bet_expected_dates settle-time date guard, split out of grade_paper_asof.py
(LOC-rail extraction, 2026-07-10) to keep both grade_paper.py and
grade_paper_asof.py under the platform's <=300 LOC/file rail. Pure move: bodies
are byte-identical to their prior home in grade_paper_asof.py, no behavior change.

Per-file test (covered indirectly via the importers' own suites):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_grade_paper_asof.py -q
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from scripts.platformkit.ingame.hist_mlb_outcome_resolver import (
    parse_mlb_ticker as _parse_mlb_ticker,
)

_ET = ZoneInfo("America/New_York")


def today_et_iso(now: Optional[_dt.datetime] = None) -> str:
    """Today's calendar date in America/New_York (ET), ISO -- the settle-time
    board_date label checked against bet_expected_dates (26c16bf6 guard).

    MLB Kalshi tickets embed the ET game date. A UTC-derived label instead
    flips to TOMORROW for any late ET game that goes final after 00:00 UTC
    (~8-9pm ET) -- the guard then wrongly REJECTs that night's own final
    until the next as-of pass (LANE C2, 2026-07-10).
    """
    dt = now if now is not None else _dt.datetime.now(_dt.timezone.utc)
    return dt.astimezone(_ET).date().isoformat()

# MLB team-alias gap (gap ledger row: 36-row backlog, 2026-07): Kalshi in-play
# rows carry a Kalshi-house shorthand matchup label ("A's", "Chicago WS", "New
# York Y") that grade_paper._team_match's full-name token match cannot
# resolve. bet_id embeds the ORIGINAL Kalshi ticker though -- reused (not
# re-derived) via hist_mlb_outcome_resolver's proven parser/split, same module
# that already solves this exact Kalshi-shorthand-vs-ESPN-abbr gap for the
# offline hist_mlb_forward_gate corpus.
_MLB_TICKER_RE = re.compile(r"KXMLBGAME-[A-Z0-9]+")


def _mlb_ticker(bet: Dict[str, Any]) -> Optional[str]:
    """The raw KXMLBGAME-... ticker embedded in *bet*'s bet_id, or None."""
    m = _MLB_TICKER_RE.search(str(bet.get("bet_id") or ""))
    return m.group(0) if m else None


def _mlb_ticker_date(bet: Dict[str, Any]) -> Optional[str]:
    """The exact game date (ISO) embedded in *bet*'s KXMLBGAME ticker, or None.

    A hard fact straight from the ticker -- preferred over the ts-based guess
    in _candidate_dates below, since a Kalshi in-play row's ts (when our own
    system recorded/discovered the market) can trail the game's own calendar
    date by several days, well outside the ts/ts+1 heuristic window.
    """
    ticker = _mlb_ticker(bet)
    if ticker is None:
        return None
    parsed = _parse_mlb_ticker(ticker)
    return parsed[0].isoformat() if parsed else None


_MLB_TICKER_HHMM_RE = re.compile(r"KXMLBGAME-\d{2}[A-Z]{3}\d{2}(\d{2})(\d{2})")


def _mlb_ticker_start_et(bet: Dict[str, Any]) -> Optional[_dt.datetime]:
    """*bet*'s own KXMLBGAME ticker's full scheduled (date, ET time) as one
    tz-aware datetime, or None if the ticker/date/hh:mm is missing or malformed.

    The DATE-only guard (bet_expected_dates / _find_final_game's board_date
    check, 26c16bf6) cannot catch a same-CALENDAR-DATE ticker whose scheduled
    TIME is still hours in the future (2026-07-11 AZLAD wrong-settle: a ticket
    for the 21:10 ET game settled at 01:27 ET the SAME date -- date-equal,
    ~20h before first pitch). This combines the existing date parse with the
    ticker's own HHMM field (present in the raw ticker, previously discarded
    by parse_mlb_ticker's caller) to support a TIME-aware guard."""
    ticker = _mlb_ticker(bet)
    if ticker is None:
        return None
    parsed = _parse_mlb_ticker(ticker)
    if parsed is None:
        return None
    game_date = parsed[0]
    m = _MLB_TICKER_HHMM_RE.match(ticker)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None
    return _dt.datetime(game_date.year, game_date.month, game_date.day, hh, mm, tzinfo=_ET)


def bet_not_yet_started(bet: Dict[str, Any], now_dt: Optional[_dt.datetime] = None) -> bool:
    """True iff *bet*'s own MLB ticker embeds a scheduled ET start strictly AFTER
    *now_dt* -- a game cannot be FINAL before it has even started. MLB only (the
    only ticker shape carrying an embedded HHMM here); missing/unparseable ticker
    or time degrades to False (old behavior, never a false-positive reject),
    mirroring bet_expected_dates' own honesty contract."""
    if str(bet.get("sport", "")).lower() != "mlb":
        return False
    start = _mlb_ticker_start_et(bet)
    if start is None:
        return False
    now = now_dt if now_dt is not None else _dt.datetime.now(_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    return start > now.astimezone(_ET)


def bet_expected_dates(bet: Dict[str, Any]) -> List[str]:
    """Every calendar date *bet*'s own game could plausibly be on, INCLUDING today
    (_candidate_dates below excludes today, for its own bounded-backlog purpose).
    Used by grade_paper._find_final_game's settle-time date guard: a board queried
    for a date outside this list cannot hold *bet*'s real game. Unparseable/absent
    date info returns [] (honest "no info", never a guess) so the guard degrades to
    a no-op instead of false-positive-rejecting a legitimate match.
    """
    if str(bet.get("sport", "")).lower() == "mlb":
        tdate = _mlb_ticker_date(bet)
        if tdate is not None:
            return [tdate]
    gd = str(bet.get("game_date") or "").strip()[:10]
    if gd:
        return [gd]
    ts = str(bet.get("ts") or "")[:10]
    if not ts:
        return []
    try:
        d = _dt.date.fromisoformat(ts)
    except ValueError:
        return []
    return [ts, (d + _dt.timedelta(days=1)).isoformat()]


__all__ = ["bet_expected_dates", "today_et_iso", "_mlb_ticker", "_mlb_ticker_date",
          "bet_not_yet_started", "_mlb_ticker_start_et"]
