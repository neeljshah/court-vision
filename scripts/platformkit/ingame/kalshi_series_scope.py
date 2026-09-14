"""scripts.platformkit.ingame.kalshi_series_scope -- Kalshi sports-series discovery.

Multi-sport OPEN-market discovery for kalshi_book_capture.py: a series allowlist per
sport (measured 2026-09-14 from GET /trade-api/v2/series?category=Sports, keyless,
no auth) plus the pure classify_market_state() rule that turns one market's
close_time into a live/pregame/idle capture-cadence bucket. No HTTP happens in this
module beyond the injected *get* callable -- it never opens a socket itself, so it
is safe to unit test with fixture bodies only (no network in tests, per invariant).

DISCOVERY: GET /events?series_ticker=<S>&status=open&with_nested_markets=true,
paginated by the response's own "cursor" field until absent/empty. Only markets
whose own status == "open" are kept (a nested market can be non-open even while its
event is still returned). Prop/derivative series (KXNBAPTS etc.) are best-effort:
an unlisted or renamed ticker simply 404s per-page (the injected *get* turns any
HTTP error into None per its own contract) and that series yields zero rows --
never an exception, never a crash.

CADENCE RULE (documented, NOT independently verified against a live game-start
field -- the public events/markets payload exposes no such field): a market's
ESTIMATED game start = close_time - TYPICAL_DURATION_SEC[sport], a fixed, coarse
per-sport game-length guess. now >= estimated_start -> "live"; within 24h before
estimated_start -> "pregame"; otherwise -> "idle". This is a proxy, not a schedule
feed -- overtime/rain delays push the true start earlier than close_time implies,
so the live window can under-run at the margins (documented LIMIT, not corrected
here; NOT VERIFIED against real game clocks).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_kalshi_book_capture.py -q
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

HttpGet = Callable[[str], Any]

# Measured 2026-09-14 from /trade-api/v2/series?category=Sports (public, no auth).
# Prop/derivative series inside each sport are best-effort -- see module docstring.
SERIES_BY_SPORT: Dict[str, Tuple[str, ...]] = {
    "nba": ("KXNBAGAME", "KXNBASPREAD", "KXNBA1QWINNER", "KXNBA1HWINNER",
            "KXNBA3QWINNER", "KXNBA4QWINNER", "KXNBA1QSPREAD", "KXNBA1HSPREAD",
            "KXNBA1QTOTAL", "KXNBA1HTOTAL", "KXNBA30COMEBACK", "KXNBA1STTEAM",
            "KXNBAPTS", "KXNBAREB", "KXNBAAST", "KXNBA3PT"),
    "mlb": ("KXMLBGAME", "KXMLBF5", "KXMLBF5SPREAD", "KXMLBF5TOTAL", "KXMLBF3",
            "KXMLBF7", "KXMLBEXTRAS", "KXMLBPITCH"),
    "tennis": ("KXATPMATCH", "KXATPCHALLENGERMATCH", "KXATPGAMESPREAD",
               "KXATPGAMETOTAL", "KXATPSETWINNER", "KXATPEXACTSETS", "KXWTAMATCH"),
    "soccer": ("KXEPLGAME", "KXBUNDESLIGAGAME", "KXLALIGAGAME", "KXSERIEAGAME",
               "KXLIGUE1GAME", "KXUCLGAME", "KXEPLBTTS", "KXBUNDESLIGABTTS",
               "KXEPL1HSPREAD", "KXEPL1HTOTAL"),
    "wnba": ("KXWNBAGAME",),
    "ncaab": ("KXNCAAMBGAME", "KXNCAABBGAME"),
}

# Coarse per-sport typical game length, used only to back out an ESTIMATED start
# time from a market's close_time -- see module docstring CADENCE RULE.
TYPICAL_DURATION_SEC: Dict[str, float] = {
    "nba": 150 * 60.0, "wnba": 130 * 60.0, "ncaab": 130 * 60.0,
    "mlb": 210 * 60.0, "tennis": 150 * 60.0, "soccer": 125 * 60.0,
}
DEFAULT_TYPICAL_DURATION_SEC = 150 * 60.0

LIVE_CADENCE_SEC = 5.0
PREGAME_CADENCE_SEC = 60.0
IDLE_CADENCE_SEC = 300.0
PREGAME_WINDOW = timedelta(hours=24)


def discovery_url(series_ticker: str, cursor: Optional[str] = None) -> str:
    params = {"series_ticker": series_ticker, "status": "open",
              "with_nested_markets": "true"}
    if cursor:
        params["cursor"] = cursor
    return KALSHI_BASE + "/events?" + urllib.parse.urlencode(params)


def fetch_open_markets(get: HttpGet, series_ticker: str, *, max_pages: int = 20
                        ) -> List[Dict[str, Any]]:
    """One series' open markets, flattened out of the nested events payload.
    A missing/malformed page (incl. a 404 the caller's *get* turned into None)
    simply ends pagination -- best-effort, never raises. A repeated cursor (an
    immediate repeat or a longer A->B->A cycle) also ends pagination rather than
    re-fetching the same page(s) up to max_pages."""
    out: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    seen_cursors = {None}
    for _ in range(max_pages):
        body = get(discovery_url(series_ticker, cursor))
        if not isinstance(body, dict) or not isinstance(body.get("events"), list):
            break
        for event in body["events"]:
            if not isinstance(event, dict) or not isinstance(event.get("markets"), list):
                continue
            for market in event["markets"]:
                if isinstance(market, dict) and market.get("status") == "open":
                    out.append({**market, "series_ticker": series_ticker,
                                "event_ticker": event.get("event_ticker", market.get("event_ticker")),
                                "event_title": event.get("title")})
        cursor = body.get("cursor") or None
        if not cursor or cursor in seen_cursors:
            break
        seen_cursors.add(cursor)
    return out


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def classify_market_state(market: Dict[str, Any], sport: str, now: datetime
                           ) -> Tuple[str, float]:
    """(state, cadence_sec) for one market -- see module docstring CADENCE RULE.
    No parseable close_time on the payload -> "idle" (slow poll, best-effort)."""
    close_time = _parse_ts(market.get("close_time"))
    if close_time is None:
        return "idle", IDLE_CADENCE_SEC
    duration = TYPICAL_DURATION_SEC.get(sport, DEFAULT_TYPICAL_DURATION_SEC)
    estimated_start = close_time - timedelta(seconds=duration)
    if now >= estimated_start:
        return "live", LIVE_CADENCE_SEC
    if estimated_start - now <= PREGAME_WINDOW:
        return "pregame", PREGAME_CADENCE_SEC
    return "idle", IDLE_CADENCE_SEC


def discover_sport(get: HttpGet, sport: str, now: datetime, *,
                    series_by_sport: Dict[str, Tuple[str, ...]] = SERIES_BY_SPORT
                    ) -> List[Dict[str, Any]]:
    """Every open market across *sport*'s allowlisted series, each tagged with a
    discovery state/cadence. Best-effort per series -- one bad series never blocks
    the rest."""
    out: List[Dict[str, Any]] = []
    for series_ticker in series_by_sport.get(sport, ()):
        for market in fetch_open_markets(get, series_ticker):
            state, cadence_sec = classify_market_state(market, sport, now)
            out.append({**market, "sport": sport, "state": state, "cadence_sec": cadence_sec})
    return out


def cap_due_markets(due: List[Dict[str, Any]], rotation_offset: int, cap: int
                     ) -> Tuple[List[Dict[str, Any]], int, bool]:
    """Priority cap for one capture tick: every "live" market first, then a
    round-robin slice of the rest -- a rotating start offset so a long idle/
    pregame tail is serviced fairly across ticks instead of always landing past
    the cap. Returns (selected, next_rotation_offset, bound)."""
    if len(due) <= cap:
        return due, rotation_offset, False
    live = [m for m in due if m.get("state") == "live"]
    rest = [m for m in due if m.get("state") != "live"]
    room = max(0, cap - len(live))
    if not rest or room <= 0:
        return live[:cap], rotation_offset, True
    offset = rotation_offset % len(rest)
    rotated = rest[offset:] + rest[:offset]
    return live + rotated[:room], offset + room, True


def prune_stale_state(state: Dict[str, Any], sports: List[str], current_tickers: Any) -> None:
    """Drop last_polled/heartbeat/discovery-cache bookkeeping for tickers or
    sports no longer in scope, so a long-running process's state dicts do not
    grow without bound as markets settle or a caller narrows *sports*."""
    last_polled = state.get("last_polled", {})
    for ticker in [t for t in last_polled if t not in current_tickers]:
        del last_polled[ticker]
    for key in ("hb", "discovery_cache"):
        bucket = state.get(key, {})
        for stale in [s for s in bucket if s not in sports]:
            del bucket[stale]


__all__ = ["SERIES_BY_SPORT", "TYPICAL_DURATION_SEC", "DEFAULT_TYPICAL_DURATION_SEC",
           "LIVE_CADENCE_SEC", "PREGAME_CADENCE_SEC", "IDLE_CADENCE_SEC", "PREGAME_WINDOW",
           "KALSHI_BASE", "discovery_url", "fetch_open_markets",
           "classify_market_state", "discover_sport", "cap_due_markets", "prune_stale_state"]
