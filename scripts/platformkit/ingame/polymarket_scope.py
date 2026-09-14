"""scripts.platformkit.ingame.polymarket_scope -- Polymarket sports-event discovery.

Mirrors kalshi_series_scope.py's split: this module owns DISCOVERY (paginated
gamma /events) and CLASSIFICATION (live/pregame/idle + cadence); the capture
LOOP, snapshot-row shape, and archive I/O live in polymarket_book_capture.py.
No HTTP happens here beyond the injected *get* callable -- safe to unit test
with fixture bodies only (no network in tests, per invariant).

DISCOVERY: GET gamma-api.polymarket.com/events?limit=100&active=true&
closed=false&tag_slug=sports&order=volume24hr&ascending=false&offset=<n>,
paginated by bumping offset by DISCOVERY_LIMIT until the response returns
FEWER than DISCOVERY_LIMIT events (gamma has no cursor field, unlike Kalshi).
Each event's markets carry clobTokenIds as a JSON-ENCODED STRING of a two-
element token-id list (one per outcome) -- parse_token_ids() decodes it,
never guessing on a malformed/short list.

CLASSIFICATION: live when now is within [startDate, endDate] OR the event
carries a truthy "live" flag; pregame when startDate is within 24h of now;
idle otherwise (includes any event whose startDate cannot be parsed -- same
fail-safe-to-idle convention as kalshi_series_scope). Cadence: live 10s,
pregame 120s, idle 600s (see ROW Q03 spec, distinct from Kalshi's 5/60/300).

SPORT HEURISTIC (documented, NOT venue-provided): gamma has no per-event sport
field on this discovery query, so classify_sport() keyword-matches the event
title into soccer/tennis/nfl/mlb/nba/nhl/esports/other. A title with no match
falls to "other" -- never guessed further.

cap_due_markets is reused UNCHANGED from kalshi_series_scope (venue-agnostic: it
operates on a plain "due" list of dicts with a "state" key -- no Kalshi-specific
logic lives in it).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_polymarket_book_capture.py -q
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

# Re-exported so callers need only import this module for the generic due-cap
# helper -- see module docstring "reused UNCHANGED" note. (prune_stale_state is
# NOT reused: its per-sport discovery_cache shape assumption does not match
# this module's single all-sports discovery bucket -- polymarket_book_capture.py
# prunes last_polled itself instead.)
from scripts.platformkit.ingame.kalshi_series_scope import cap_due_markets  # noqa: F401

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

HttpGet = Callable[[str], Any]

DISCOVERY_LIMIT = 100
DISCOVERY_TAG_SLUG = "sports"

LIVE_CADENCE_SEC = 10.0
PREGAME_CADENCE_SEC = 120.0
IDLE_CADENCE_SEC = 600.0
PREGAME_WINDOW = timedelta(hours=24)
MAX_DUE_PER_TICK = 40  # markets, live first -- see kalshi_series_scope.cap_due_markets

_SPORT_KEYWORDS: Tuple[Tuple[str, str], ...] = (
    ("soccer", "soccer"), ("epl", "soccer"), ("la liga", "soccer"), ("bundesliga", "soccer"),
    ("serie a", "soccer"), ("ligue 1", "soccer"), ("champions league", "soccer"), ("uefa", "soccer"),
    ("mls", "soccer"), ("fifa", "soccer"), ("world cup", "soccer"),
    ("tennis", "tennis"), ("atp", "tennis"), ("wta", "tennis"), ("open", "tennis"),
    ("nfl", "nfl"), ("nhl", "nhl"),
    ("mlb", "mlb"), ("baseball", "mlb"),
    ("nba", "nba"), ("wnba", "nba"), ("basketball", "nba"),
    ("esports", "esports"), ("csgo", "esports"), ("cs2", "esports"), ("dota", "esports"),
    ("league of legends", "esports"), ("valorant", "esports"),
)


def discovery_url(offset: int = 0) -> str:
    params = {"limit": DISCOVERY_LIMIT, "active": "true", "closed": "false",
              "tag_slug": DISCOVERY_TAG_SLUG, "order": "volume24hr",
              "ascending": "false", "offset": offset}
    return GAMMA_BASE + "/events?" + urllib.parse.urlencode(params)


def book_url(token_id: str) -> str:
    return CLOB_BASE + "/book?token_id=" + urllib.parse.quote(str(token_id), safe="")


def midpoint_url(token_id: str) -> str:
    return CLOB_BASE + "/midpoint?token_id=" + urllib.parse.quote(str(token_id), safe="")


def fetch_events(get: HttpGet, *, max_pages: int = 50) -> List[Dict[str, Any]]:
    """Every sports event across all discovery pages. Best-effort: a missing/
    malformed page (incl. a fetch failure the caller's *get* turned into None)
    simply ends pagination rather than raising."""
    out: List[Dict[str, Any]] = []
    for page in range(max_pages):
        body = get(discovery_url(page * DISCOVERY_LIMIT))
        events = body if isinstance(body, list) else (body.get("events") if isinstance(body, dict) else None)
        if not isinstance(events, list):
            break
        out.extend(e for e in events if isinstance(e, dict))
        if len(events) < DISCOVERY_LIMIT:
            break
    return out


def parse_token_ids(market: Dict[str, Any]) -> List[str]:
    """clobTokenIds is a JSON-ENCODED STRING of a token-id list on the wire
    (same convention as ingame_book_depth_poly.resolve_token). Never raises;
    a missing/malformed field -> []."""
    raw = market.get("clobTokenIds")
    try:
        tokens = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    if not isinstance(tokens, list):
        return []
    return [str(t) for t in tokens if t is not None]


def parse_outcomes(market: Dict[str, Any]) -> List[str]:
    """outcomes is the same JSON-encoded-string convention as clobTokenIds."""
    raw = market.get("outcomes")
    try:
        outcomes = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    return [str(o) for o in outcomes] if isinstance(outcomes, list) else []


def classify_sport(title: Any) -> str:
    """Keyword heuristic over the event title -- documented gap, not a venue
    field (see module docstring SPORT HEURISTIC)."""
    text = (title or "").lower() if isinstance(title, str) else ""
    for needle, sport in _SPORT_KEYWORDS:
        if needle in text:
            return sport
    return "other"


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


def classify_event_state(event: Dict[str, Any], now: datetime) -> Tuple[str, float]:
    """(state, cadence_sec) for one event -- see module docstring CLASSIFICATION.
    Unparseable/absent startDate -> "idle" (slow poll, best-effort, mirrors
    kalshi_series_scope's own fallback)."""
    start = _parse_ts(event.get("startDate"))
    end = _parse_ts(event.get("endDate"))
    live_flag = bool(event.get("live"))
    if live_flag or (start is not None and end is not None and start <= now <= end):
        return "live", LIVE_CADENCE_SEC
    if start is not None and timedelta(0) <= (start - now) <= PREGAME_WINDOW:
        return "pregame", PREGAME_CADENCE_SEC
    return "idle", IDLE_CADENCE_SEC


def extract_markets(events: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """Flatten events -> one dict per MARKET (a market may carry 2 token ids,
    handled together as one capture unit -- see polymarket_book_capture.py),
    tagged with its event's classification + the sport heuristic."""
    out: List[Dict[str, Any]] = []
    for event in events:
        markets = event.get("markets")
        if not isinstance(markets, list):
            continue
        state, cadence_sec = classify_event_state(event, now)
        sport = classify_sport(event.get("title"))
        for market in markets:
            if not isinstance(market, dict):
                continue
            token_ids = parse_token_ids(market)
            if not token_ids:
                continue  # nothing to poll for this market -- never fabricated
            out.append({
                "event_id": event.get("id"), "event_slug": event.get("slug"),
                "event_title": event.get("title"), "condition_id": market.get("conditionId"),
                "question": market.get("question"), "outcomes": parse_outcomes(market),
                "token_ids": token_ids, "volume24hr": market.get("volume24hr"),
                "liquidity": market.get("liquidity"), "sport": sport,
                "state": state, "cadence_sec": cadence_sec,
                # ADDITIVE: the event's own endDate, threaded through under the
                # same field name Kalshi's raw payload already uses (close_time)
                # so both capture modules can read market.get("close_time")
                # identically -- see polymarket_book_row.book_row.
                "close_time": event.get("endDate"),
            })
    return out


__all__ = ["GAMMA_BASE", "CLOB_BASE", "DISCOVERY_LIMIT", "LIVE_CADENCE_SEC",
           "PREGAME_CADENCE_SEC", "IDLE_CADENCE_SEC", "PREGAME_WINDOW", "MAX_DUE_PER_TICK",
           "discovery_url", "book_url", "midpoint_url", "fetch_events", "parse_token_ids",
           "parse_outcomes", "classify_sport", "classify_event_state", "extract_markets",
           "cap_due_markets"]
