"""scripts.platformkit.venue_history.polymarket_game_slug_backfill -- LANE 3:
2024+ NBA/MLB per-game Polymarket backfill under the ALTERNATE (non-dailies)
slug family the venue relaunched under after the 2023 "dailies" pilot ended.

PROBE FINDING (2026-07-04, live gamma-api + clob probing, ~30 requests):
  - WC-2022 (Qatar): game markets exist on gamma (world-cup-2022-<day>-will-
    <team>-beat-<team>), CLOSED with clean settled outcomePrices, but
    clob.polymarket.com/prices-history is EMPTY (0 points) for every one of
    4 sampled tokens across 4 different games (explicit-ts fidelity=1 and
    wider windows). Consistent with the mid-2022 CLOB indexing cutoff named
    in the brief -- gamma kept the metadata, CLOB never indexed the ticks.
    CONCLUSION: no WC-2022 price paths exist via this API; nothing to
    backfill for that corpus (reported honestly, not silently skipped).
  - 2024/2025/2026 NBA and MLB: per-game markets exist under a NEW slug
    family, "<sport>-<away>-<home>-YYYY-MM-DD" (e.g. nba-sas-lal-2025-12-10,
    mlb-tor-nyy-2025-10-07), plus irregularly-named postseason variants
    (world-series-*, alcs-*, nba-playoffs-*) this module does NOT enumerate
    (regex-gated, out of scope). Each event has 1 base moneyline market
    (event slug == market slug) with POPULATED history (~1900-2400
    ticks/game sampled); dozens of aux markets (spreads/totals/1H/props)
    were EMPTY in every one of ~12 sampled -- likely illiquid. This module
    backfills ONLY the base moneyline market.
  - Earliest confirmed regular-season slug: nba-nyk-bos-2024-10-22 (the
    2024-25 opener). MLB per-game slugs appear from the 2024 postseason
    (irregular naming) with the regular "mlb-<away>-<home>-YYYY-MM-DD"
    pattern from the 2025 season on.

ENUMERATION RECIPE (differs from polymarket_intragame's day-walk): games
are NOT one-per-day, so we page the gamma tag-listing endpoint (ordered by
startDate ascending):
  GET /events?tag_slug=<sport>&closed=true&order=startDate&ascending=true
      &limit=100&start_date_min=<cursor>
Probe-confirmed: this endpoint 422s past an internal offset~2100 ceiling
regardless of limit/offset; start_date_min pages around that ceiling by
advancing the date window instead of the offset. Only slugs matching
"<sport>-<team>-<team>-YYYY-MM-DD" are treated as game events (postseason
irregular slugs are skipped, not guessed at).

PROVENANCE (binding): VALIDATION corpus, physically separate directory
(<sport>_2024plus) from both the 2023 "dailies" corpus and the forward
pre-registered tail gates. Never pooled with either.

Politeness: 1 req/s: 1 tag-listing page (~100 events) + 1 event-slug lookup
+ 1 prices-history call per confirmed game. Resumable via progress_sidecar.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; stdlib only; no $-edge
claims; no data/registry writes; no flag flips.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_polymarket_game_slug_backfill.py -q
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.odds_provider.http_cache import http_get_json
from scripts.platformkit.venue_history.polymarket_intragame import (
    GAMMA_BASE, CLOB_BASE, _as_list, _resolve_outcome, fetch_price_history,
)
from scripts.platformkit.venue_history.progress_sidecar import load_progress, save_progress

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "venue_history" / "polymarket"

HttpGet = Callable[[str], Any]

# Confirmed-live earliest regular-season windows (see module docstring).
DEFAULT_NBA_START = "2024-10-20"
DEFAULT_MLB_START = "2024-09-25"

_SLUG_RE_TMPL = r"^%s-[a-z]{2,4}-[a-z]{2,4}-\d{4}-\d{2}-\d{2}(-v\d+)?$"


def _get(http: HttpGet, url: str) -> Optional[Any]:
    try:
        return http(url)
    except Exception:  # noqa: BLE001 -- one bad page must not kill the whole run
        return None


def game_slug_pattern(sport: str) -> re.Pattern:
    return re.compile(_SLUG_RE_TMPL % re.escape(sport.lower()))


def list_game_events_page(sport: str, start_date_min: str, *, limit: int = 100,
                          http: HttpGet = http_get_json) -> List[Dict[str, Any]]:
    """One page of the tag-listing endpoint, ordered by startDate ascending,
    filtered to slugs matching the base "<sport>-<team>-<team>-YYYY-MM-DD"
    game pattern (postseason irregular slugs are skipped, not guessed at)."""
    url = "%s/events?%s" % (GAMMA_BASE, urllib.parse.urlencode({
        "tag_slug": sport.lower(), "closed": "true", "limit": limit,
        "order": "startDate", "ascending": "true", "start_date_min": start_date_min,
    }))
    body = _get(http, url)
    if not isinstance(body, list):
        return []
    pat = game_slug_pattern(sport)
    return [e for e in body if pat.match(str(e.get("slug") or ""))]


def fetch_game_event(sport: str, slug: str, *, http: HttpGet = http_get_json) -> Optional[Dict[str, Any]]:
    """Exact-slug lookup, same convention as polymarket_intragame.fetch_dailies_event."""
    url = "%s/events?slug=%s" % (GAMMA_BASE, urllib.parse.quote(slug))
    body = _get(http, url)
    if not isinstance(body, list) or not body:
        return None
    return body[0]


def _base_moneyline_market(event: Dict[str, Any], slug: str) -> Optional[Dict[str, Any]]:
    """The base moneyline market has market slug == event slug (confirmed in
    probe: exactly one such market per game event, with populated history;
    all other -spread-/-total-/-1h-/prop markets are out of scope here)."""
    for m in event.get("markets") or []:
        if str(m.get("slug") or "") == slug:
            return m
    return None


def _game_window(date_str: str) -> tuple:
    """[date-1d 00:00Z, date+2d 00:00Z) -- pad both sides for early tips / OT."""
    d0 = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int((d0 - timedelta(days=1)).timestamp()), int((d0 + timedelta(days=2)).timestamp())


def build_game_doc(sport: str, slug: str, event: Dict[str, Any], *,
                   http: HttpGet = http_get_json) -> Optional[Dict[str, Any]]:
    """One game event -> its per-game JSONL doc (base moneyline market only),
    or None if unparseable / no base market found."""
    m = _base_moneyline_market(event, slug)
    if m is None:
        return None
    outcomes = [str(o).strip() for o in _as_list(m.get("outcomes"))]
    tokens = [str(t) for t in _as_list(m.get("clobTokenIds"))]
    if len(outcomes) != 2 or len(tokens) != 2:
        return None
    # date parsed from the trailing YYYY-MM-DD in the slug, not startDate
    # (startDate is listing/creation time, not game date).
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})(?:-v\d+)?$", slug)
    date_str = date_match.group(1) if date_match else str(event.get("startDate", ""))[:10]
    start_ts, end_ts = _game_window(date_str)
    prices = fetch_price_history(tokens[0], start_ts, end_ts, http=http)
    return {
        "date": date_str, "event_slug": slug, "market_slug": str(m.get("slug") or ""),
        "sport": sport, "home": outcomes[0], "away": outcomes[1],
        "outcome_home_win": _resolve_outcome(m),
        "closed": bool(m.get("closed")),
        "token_home": tokens[0],
        "n_prices": len(prices), "prices": prices,
        "window": "2024plus",
    }


def run_backfill(
    sport: str,
    start_date: str,
    *,
    end_date: Optional[str] = None,
    out_dir: Optional[Path] = None,
    progress_path: Optional[Path] = None,
    max_requests: int = 1200,
    sleep_sec: float = 1.0,
    page_limit: int = 100,
    http: HttpGet = http_get_json,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Bounded, resumable tranche: page the tag-listing endpoint from
    *start_date* forward (resuming from the progress sidecar's last-seen
    startDate cursor if present), confirm+fetch each matched game slug's
    base moneyline market, write one JSONL per game-day (may append multiple
    games sharing a date). Stops at *end_date* if given, else at the request
    budget or first empty page (today's edge)."""
    out_base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR / ("%s_2024plus" % sport.lower())
    prog_path = Path(progress_path) if progress_path is not None else out_base / "_progress.json"
    progress = load_progress(prog_path)
    cursor = str(progress.get("cursor_start_date_min", "")) or start_date

    n_requests = 0
    n_game_days = int(progress.get("n_game_days", 0))
    n_games = int(progress.get("n_games", 0))
    n_prices = int(progress.get("n_prices", 0))
    seen_dates = set(progress.get("dates_seen") or [])
    earliest = progress.get("earliest_date_confirmed")
    latest = progress.get("latest_date_confirmed")
    budget_hit = False
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

    docs_by_date: Dict[str, List[Dict[str, Any]]] = {}
    last_cursor = cursor
    exhausted = False

    while n_requests < max_requests:
        page = list_game_events_page(sport, last_cursor, limit=page_limit, http=http)
        n_requests += 1
        sleep_fn(sleep_sec)
        if not page:
            exhausted = True
            break
        page_max_date = last_cursor
        for e in page:
            slug = str(e.get("slug") or "")
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})(?:-v\d+)?$", slug)
            date_str = date_match.group(1) if date_match else ""
            if not date_str:
                continue
            if end_dt is not None and datetime.strptime(date_str, "%Y-%m-%d").date() > end_dt:
                exhausted = True
                break
            if slug in seen_dates:
                continue
            if n_requests >= max_requests:
                budget_hit = True
                break
            event = fetch_game_event(sport, slug, http=http)
            n_requests += 1
            sleep_fn(sleep_sec)
            if event is None:
                continue
            doc = build_game_doc(sport, slug, event, http=http)
            n_requests += 1
            sleep_fn(sleep_sec)
            seen_dates.add(slug)
            if doc is not None:
                docs_by_date.setdefault(date_str, []).append(doc)
                n_games += 1
                n_prices += doc["n_prices"]
                if earliest is None or date_str < earliest:
                    earliest = date_str
                if latest is None or date_str > latest:
                    latest = date_str
            page_max_date = max(page_max_date, date_str + "T23:59:59Z")
        if budget_hit or exhausted:
            break
        # advance cursor to the day after the last date on this page (dedup
        # via seen_dates protects the boundary day from being dropped).
        last_seen_date = page_max_date[:10]
        next_cursor_date = (datetime.strptime(last_seen_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
        if next_cursor_date <= last_cursor[:10]:
            exhausted = True  # no forward progress -- stop rather than loop
            break
        last_cursor = next_cursor_date

    if docs_by_date:
        out_base.mkdir(parents=True, exist_ok=True)
        for date_str, docs in docs_by_date.items():
            out_path = out_base / ("%s_%s-games.jsonl" % (date_str, sport.lower()))
            with out_path.open("a", encoding="utf-8") as fh:
                for d in docs:
                    fh.write(json.dumps(d) + "\n")
        n_game_days = len({p.stem for p in out_base.glob("*-games.jsonl")})

    save_progress(prog_path, {
        "sport": sport, "cursor_start_date_min": last_cursor,
        "n_game_days": n_game_days, "n_games": n_games, "n_prices": n_prices,
        "dates_seen": sorted(seen_dates),
        "earliest_date_confirmed": earliest, "latest_date_confirmed": latest,
    })

    return {
        "sport": sport, "start_date": start_date, "end_date": end_date,
        "n_requests_this_run": n_requests,
        "n_game_days": n_game_days, "n_games": n_games, "n_prices": n_prices,
        "earliest_date_confirmed": earliest, "latest_date_confirmed": latest,
        "budget_hit": budget_hit, "exhausted": exhausted,
        "cursor_start_date_min": last_cursor, "out_dir": str(out_base),
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="polymarket_game_slug_backfill")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--max-requests", type=int, default=1200)
    ap.add_argument("--sleep-sec", type=float, default=1.0)
    a = ap.parse_args()
    start = a.start or (DEFAULT_NBA_START if a.sport.lower() == "nba" else DEFAULT_MLB_START)
    result = run_backfill(a.sport, start, end_date=a.end, max_requests=a.max_requests, sleep_sec=a.sleep_sec)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()


__all__ = [
    "game_slug_pattern", "list_game_events_page", "fetch_game_event", "build_game_doc",
    "run_backfill", "DEFAULT_NBA_START", "DEFAULT_MLB_START",
]
