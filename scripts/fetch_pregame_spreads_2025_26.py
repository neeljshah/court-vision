"""fetch_pregame_spreads_2025_26.py — cycle 91c (loop 5).

Why
---
Cycle 90a T1-A garbage-time haircut probe was crippled because the SRS-derived
implied-margin spread only covers 2023-24 + 2024-25 (last day 2025-04-13). The
canonical 80/20 holdout (all 2025-26 games) had ZERO spread data, so T1-A re-ran
on the in-coverage window only and saw a directional but tiny effect. With true
PRE-GAME sportsbook spreads for 2025-26, T1-A can be re-tested with real signal.

This fetcher pulls ESPN's public scoreboard JSON for every date in the 2025-26
NBA season window. Each game's `competitions[0].odds[0].details` field carries a
free pre-game spread string like "LAL -4.5" (or "EVEN"). We parse the favourite
team + magnitude into a signed `home_spread` (negative when home is favoured).

Pipeline per date
-----------------
  1. GET https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD
  2. Persist raw JSON -> data/cache/spreads/<YYYYMMDD>.json (idempotent, skip if exists).
  3. Done. Aggregation -> parquet lives in aggregate_spreads_to_parquet.py.

CLI
---
    python scripts/fetch_pregame_spreads_2025_26.py --since 2025-11-01 --until 2025-11-07
    python scripts/fetch_pregame_spreads_2025_26.py --season-full   # 2025-10-21..today
    python scripts/fetch_pregame_spreads_2025_26.py --date 20251105 --force

Rate-limited 1 req/sec, retries 2x on transient errors. Free, no auth.

Sandbox note
------------
When the sandbox can't reach ESPN, the cache simply doesn't grow — the downstream
aggregator + prop_pergame join both fail gracefully (parquet absent ⇒ no
home_spread feature). Tests inject a synthetic ESPN response via fetch_fn.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache", "spreads")
_ESPN_URL  = ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
              "scoreboard?dates={ymd}")
# ESPN scoreboard strips the `odds` block from completed games, so we pull
# per-event odds from the core API which retains open/close/current per
# provider (ESPN BET, Caesars, etc).
_ESPN_ODDS_URL = ("https://sports.core.api.espn.com/v2/sports/basketball/"
                   "leagues/nba/events/{event_id}/competitions/{event_id}/odds")
_UA        = "Mozilla/5.0 (NBA-AI/0.1 +pregame-spreads-fetcher)"

# 2025-26 NBA regular season opens Tue 2025-10-21.
_SEASON_OPEN = date(2025, 10, 21)


def _cache_path(ymd: str) -> str:
    return os.path.join(_CACHE_DIR, f"{ymd}.json")


def _http_json(url: str, *, timeout: float = 20.0,
                retries: int = 2) -> Optional[dict]:
    """GET url, decode JSON. Returns dict or None on any failure."""
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": _UA,
                                          "Accept": "application/json"})
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw)
        except (HTTPError, URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(0.5 + attempt)
                continue
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            break
    print(f"  [warn] GET failed {url[:90]}...: {last_err}")
    return None


def fetch_event_odds(event_id: str, *, timeout: float = 20.0,
                      retries: int = 1) -> Optional[list]:
    """GET the core-API odds items for a single event_id. Returns list or None.

    The scoreboard endpoint omits the `odds` block for completed games. The
    core API retains it. Returns the `items` array (one entry per book), e.g.
    [{"provider": ..., "details": "MIL -6.5", "spread": -6.5,
      "overUnder": 232.5, "homeTeamOdds": {...}, "awayTeamOdds": {...}}].
    """
    payload = _http_json(_ESPN_ODDS_URL.format(event_id=event_id),
                          timeout=timeout, retries=retries)
    if not payload:
        return None
    return payload.get("items") or []


def fetch_date(ymd: str, *, timeout: float = 20.0,
               retries: int = 2,
               include_odds: bool = True,
               odds_sleep: float = 0.3) -> Optional[dict]:
    """GET ESPN scoreboard for one YYYYMMDD date and (optionally) splice in
    per-event odds from the core API. Returns the augmented dict or None.

    `include_odds=False` matches the original lightweight path used by tests.
    """
    payload = _http_json(_ESPN_URL.format(ymd=ymd), timeout=timeout,
                          retries=retries)
    if payload is None:
        return None
    if not include_odds:
        return payload
    # Splice per-event odds in-place so the existing aggregator works unchanged.
    for ev in payload.get("events") or []:
        ev_id = ev.get("id")
        comps = ev.get("competitions") or []
        if not ev_id or not comps:
            continue
        if comps[0].get("odds"):
            continue  # scoreboard already had odds (rare — live games)
        items = fetch_event_odds(str(ev_id), timeout=timeout, retries=1)
        if items:
            comps[0]["odds"] = items
        time.sleep(odds_sleep)
    return payload


def fetch_and_cache(ymd: str, *, force: bool = False,
                    fetch_fn=fetch_date) -> Optional[str]:
    """Fetch ESPN scoreboard for ymd and persist raw JSON. Returns cache path or None.

    Idempotent: existing cache file is reused unless force=True. Returns None
    when the fetch failed AND no prior cache file exists.
    """
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = _cache_path(ymd)
    if os.path.exists(path) and not force:
        return path
    payload = fetch_fn(ymd)
    if payload is None:
        return path if os.path.exists(path) else None
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def run(since: date, until: date, *, sleep_sec: float = 1.0,
        force: bool = False, fetch_fn=fetch_date) -> int:
    """Iterate [since, until], fetch each date, sleep between. Returns files written."""
    n = 0
    for d in _daterange(since, until):
        ymd = d.strftime("%Y%m%d")
        path = fetch_and_cache(ymd, force=force, fetch_fn=fetch_fn)
        if path:
            n += 1
            print(f"[{ymd}] cached -> {os.path.relpath(path, PROJECT_DIR)}")
        time.sleep(sleep_sec)
    return n


def _parse_iso(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None,
                    help="ISO date (YYYY-MM-DD). Default: 2025-10-21 (season open).")
    ap.add_argument("--until", default=None,
                    help="ISO date (YYYY-MM-DD). Default: today.")
    ap.add_argument("--date", default=None,
                    help="Single YYYYMMDD date (overrides --since/--until).")
    ap.add_argument("--season-full", action="store_true",
                    help="Shortcut: since=2025-10-21, until=today.")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch even if a cache file already exists.")
    ap.add_argument("--sleep-sec", type=float, default=1.0,
                    help="Rate-limit between dates (default 1.0s).")
    args = ap.parse_args(argv)

    if args.date:
        path = fetch_and_cache(args.date, force=args.force)
        print(f"single-date fetch {args.date} -> {path}")
        return 0 if path else 1

    today = date.today()
    if args.season_full:
        since, until = _SEASON_OPEN, today
    else:
        since = _parse_iso(args.since) if args.since else _SEASON_OPEN
        until = _parse_iso(args.until) if args.until else today

    if until < since:
        print(f"[err] until {until} < since {since}")
        return 1

    print(f"[fetch_pregame_spreads] {since} -> {until} "
          f"({(until - since).days + 1} days, ~{args.sleep_sec:.1f}s/req)")
    n = run(since, until, sleep_sec=args.sleep_sec, force=args.force)
    print(f"[fetch_pregame_spreads] done. {n} dates cached under "
          f"{os.path.relpath(_CACHE_DIR, PROJECT_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
