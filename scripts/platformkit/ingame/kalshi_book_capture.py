"""Dense, measurement-only Kalshi MULTI-SPORT order-book capture LOOP for the POD.

Extends mlb_book_capture.py's pattern (GovernedClient, get_governor('depth_capture'),
before_request/report_429, the two-env-flag live-write gate) to every sport in
kalshi_series_scope.SERIES_BY_SPORT in ONE module. Discovery
(GET /events?series_ticker=...&status=open) lives in kalshi_series_scope.py
(allowlist, cadence rule, due-cap/prune helpers); the snapshot row shape and
archive/heartbeat paths live in kalshi_book_row.py (both split out to stay under
the 300 LOC cap). This file owns only the per-tick orchestration LOOP. NO CLI:
local authoring cannot accidentally start a live loop.

ARCHIVE OWNERSHIP: kalshi_book_row's LIVE_ARCHIVE_ROOT is its OWN root,
data/cache/ingame_books/kalshi_multi/<sport>/, NOT ingame_books/mlb/ -- the landed
mlb_book_capture.py already owns MLB GAME books (its own pod process, its own
archive, already relaunched by the runbook); a second writer at that path would
collide. Default *sports* (kalshi_book_row.default_sports) therefore EXCLUDES mlb;
set CV_KALSHI_MULTI_INCLUDE_MLB=1 to also poll MLB DERIVATIVE series
(F5/F5SPREAD/F5TOTAL/F3/F7/EXTRAS/PITCH) -- never KXMLBGAME -- alongside the rest.
GOVERNOR NOTE: get_governor() is a per-PROCESS singleton -- this module and
mlb_book_capture.py run as two pod processes each taking the FULL 'depth_capture'
share independently (not split); fold both into one process in a later row if the
combined rate matters.

POD LAUNCH (mirrors docs/operations/runpod-runbook.md's mlb_book_capture line):
  cd /workspace/nba-ai-system && CV_CAPTURE_POD=1 CV_KALSHI_BOOK_ARCHIVE_LIVE=1 \\
    nohup setsid python -c \\
    "from scripts.platformkit.ingame.kalshi_book_capture import run_pod_capture; \\
     run_pod_capture(stop=lambda: False)" </dev/null >/workspace/kalshi_book_capture.log 2>&1 &

NOT VERIFIED: no live pod run of this module yet; api_ts (kalshi_book_row.book_row)
is a best-effort body.get("ts") read (ingame_book_depth_kalshi.py documents the
orderbook_fp ladder shape only, no response-level timestamp -- expect None until
checked live); the nested-markets shape for prop/derivative series (KXNBAPTS,
KXMLBPITCH, ...) is assumed from the ROW Q02 spec text, not confirmed live; the
POD LAUNCH block above is written by analogy to the runbook, not executed.

Sources: https://docs.kalshi.com/getting_started/rate_limits ,
         https://help.kalshi.com/en/articles/13823805-fees
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_kalshi_book_capture.py -q
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.ingame import kalshi_book_row as row
from scripts.platformkit.ingame import kalshi_series_scope as scope
from scripts.platformkit.odds_provider.kalshi_rate_governor import (
    before_request, get_governor, report_429,
)

logger = logging.getLogger(__name__)

MAX_FETCH_CONCURRENCY = 4  # ponytail: mirrors mlb_book_capture's MAX_FETCH_CONCURRENCY
MAX_DUE_PER_TICK = 40  # priority-capped; see kalshi_series_scope.cap_due_markets

# Re-exported for callers/tests that only need the capture surface (row shape and
# archive helpers live in kalshi_book_row.py).
CAPTURE_VERSION = row.CAPTURE_VERSION
LIVE_ARCHIVE_ROOT = row.LIVE_ARCHIVE_ROOT
SCRATCH_ARCHIVE_ROOT = row.SCRATCH_ARCHIVE_ROOT
DISCOVERY_REFRESH_SEC = 600.0  # re-list open markets per sport at most this often
live_archive_enabled = row.live_archive_enabled
archive_path = row.archive_path
heartbeat_path = row.heartbeat_path
book_row = row.book_row


class GovernedClient:
    """The only HTTP path: existing governor before every request, 429 reported.
    One shared token bucket across every sport this process captures (caller
    'depth_capture', same registered share depth_capture.py already uses)."""

    def __init__(self, opener: Callable[..., Any] = urllib.request.urlopen) -> None:
        self.governor = get_governor("depth_capture")
        self.opener = opener
        self.n_429 = 0
        self.n_errors = 0
        self._lock = Lock()

    def get(self, url: str, sport: str, *, n_active_sports: int = 1) -> Tuple[Optional[Any], int]:
        """Returns (body_or_None, ts_ms) -- ts_ms is stamped AFTER before_request
        returns (excludes any governor wait) and immediately before the HTTP
        send, so it approximates wire time, not enqueue time."""
        with self._lock:
            before_request(self.governor, sport, n_active_sports=n_active_sports)
        ts_ms = int(time.time() * 1000)
        try:
            with self.opener(urllib.request.Request(url), timeout=15.0) as response:
                return json.loads(response.read().decode("utf-8")), ts_ms
        except urllib.error.HTTPError as exc:
            with self._lock:
                self.n_errors += 1
                if exc.code == 429:
                    self.n_429 += 1
                    report_429(self.governor)
            return None, ts_ms
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            with self._lock:
                self.n_errors += 1
            return None, ts_ms


def discover_cached(client: "GovernedClient", sport: str, state: Dict[str, Any],
                     now: datetime, clock: Callable[[], float] = time.monotonic
                     ) -> List[Dict[str, Any]]:
    """Open markets for *sport*, refreshed at most every DISCOVERY_REFRESH_SEC.
    Every cached market's state/cadence is re-classified by the CALLER each tick
    (a pure, cheap call) so a market crossing its estimated start switches cadence
    within one tick rather than waiting for the next discovery refresh."""
    cache = state.setdefault("discovery_cache", {})
    entry = cache.get(sport)
    nowc = clock()
    if entry is not None and nowc - entry["ts"] < DISCOVERY_REFRESH_SEC:
        return entry["markets"]
    markets = scope.discover_sport(lambda url: client.get(url, sport)[0], sport, now)
    cache[sport] = {"ts": nowc, "markets": markets}
    return markets


def capture_once(*, client: Optional["GovernedClient"] = None, sports: Optional[List[str]] = None,
                  now: Optional[datetime] = None, state: Optional[Dict[str, Any]] = None,
                  clock: Callable[[], float] = time.monotonic,
                  output_root: Optional[Path] = None,
                  max_concurrency: int = MAX_FETCH_CONCURRENCY) -> Dict[str, Any]:
    """One pass: refresh discovery per sport (cached), re-classify every cached
    market's state, poll the due ones (priority-capped), append rows, write one
    heartbeat per sport, and prune stale per-ticker/per-sport bookkeeping."""
    client = client or GovernedClient()
    state = state if state is not None else {}
    now = now or datetime.now(timezone.utc)
    sports = list(sports) if sports else row.default_sports()
    last_polled = state.setdefault("last_polled", {})
    nowc = clock()
    all_markets: List[Dict[str, Any]] = []
    due: List[Dict[str, Any]] = []
    for sport in sports:
        markets = discover_cached(client, sport, state, now, clock)
        for market in markets:
            market["state"], market["cadence_sec"] = scope.classify_market_state(market, sport, now)
        all_markets.extend(markets)
        for market in markets:
            ticker = market.get("ticker")
            if ticker and nowc - last_polled.get(ticker, 0.0) >= market["cadence_sec"]:
                due.append(market)

    n_due_before_cap = len(due)
    due, offset, bound = scope.cap_due_markets(due, state.get("due_rotation", 0), MAX_DUE_PER_TICK)
    state["due_rotation"] = offset
    if bound:
        logger.warning("kalshi_book_capture due-cap bound: %d due markets, capped to %d this tick",
                        n_due_before_cap, len(due))
    scope.prune_stale_state(state, sports, {m["ticker"] for m in all_markets if m.get("ticker")})

    def fetch(market: Dict[str, Any]) -> Any:
        enqueue_ts_ms = int(time.time() * 1000)
        try:
            url = scope.KALSHI_BASE + "/markets/" + urllib.parse.quote(str(market["ticker"]), safe="") + "/orderbook"
            body, ts_ms = client.get(url, market["sport"], n_active_sports=max(1, len(sports)))
            return market, body, ts_ms, enqueue_ts_ms, None
        except Exception as exc:  # noqa: BLE001 -- one bad market must never kill the pass
            return market, None, enqueue_ts_ms, enqueue_ts_ms, "%s: %s" % (type(exc).__name__, exc)

    with ThreadPoolExecutor(max_workers=max(1, int(max_concurrency))) as executor:
        fetched = list(executor.map(fetch, due))

    capture_ts = row.iso(now)
    rows_by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for market, body, ts_ms, enqueue_ts_ms, reason in fetched:
        last_polled[market["ticker"]] = nowc
        # close_time: prefer the market's own close_time, else expected_expiration_time
        # (both raw Kalshi payload fields, preserved verbatim by kalshi_series_scope).
        close_time = market.get("close_time") or market.get("expected_expiration_time")
        one_row = row.book_row(market, body, ts_ms, capture_ts, enqueue_ts_ms, close_time=close_time) \
            if body is not None else row.fetch_error_row(market, ts_ms, enqueue_ts_ms, capture_ts, reason)
        rows_by_sport.setdefault(market["sport"], []).append(one_row)

    hb_state = state.setdefault("hb", {})
    by_sport: Dict[str, Any] = {}
    for sport in sports:
        rows = rows_by_sport.get(sport, [])
        path = (output_root / sport / (now.strftime("%Y-%m-%d") + ".jsonl")) if output_root \
            else row.archive_path(sport, now)
        for one_row in rows:
            row.append(path, one_row)
        n_snap = sum(1 for r in rows if r.get("record_type") == "snapshot")
        counts = {"live": 0, "pregame": 0, "idle": 0}
        for m in all_markets:
            if m["sport"] == sport:
                counts[m["state"]] = counts.get(m["state"], 0) + 1
        prior = hb_state.get(sport, {})
        heartbeat = {"sport": sport, "updated_ts": capture_ts,
                     "last_snapshot_ts": capture_ts if n_snap else prior.get("last_snapshot_ts"),
                     "n_snapshot_rows_tick": n_snap, "n_markets_live": counts["live"],
                     "n_markets_pregame": counts["pregame"], "n_markets_idle": counts["idle"],
                     "n_429_total": client.n_429, "n_errors_total": client.n_errors}
        hb_state[sport] = heartbeat
        hb_path = (output_root / sport / "_heartbeat.json") if output_root else row.heartbeat_path(sport)
        row.write_json_atomic(hb_path, heartbeat)
        by_sport[sport] = {"path": str(path), "n_rows": len(rows), "n_snapshot_rows": n_snap,
                            "heartbeat_path": str(hb_path)}
    return {"n_discovered": len(all_markets), "n_due": len(due), "due_cap_bound": bound,
            "n_429": client.n_429, "n_errors": client.n_errors, "by_sport": by_sport}


def run_pod_capture(*, stop: Callable[[], bool], sports: Optional[List[str]] = None,
                     sleep: Callable[[float], None] = time.sleep,
                     clock: Callable[[], float] = time.monotonic,
                     output_root: Optional[Path] = None) -> Dict[str, Any]:
    """POD-only loop; refuses to start unless the POD owns the live archive. A
    single market's fetch failure NEVER escapes capture_once (fetch() there is
    fully try/except-guarded), so this loop only stops on *stop*.

    DEADLINE PACING (mirrors mlb_book_capture.run_pod_capture): each tick sleeps
    only the residual to its OWN start+period, so an overrunning tick never piles
    up drift. period = the fastest cadence among markets discovered this tick
    (live 5s > pregame 60s > idle 300s), or DISCOVERY_REFRESH_SEC when nothing has
    been discovered yet. Liveness evidence is the per-sport heartbeat file
    capture_once already writes every tick -- no separate metrics stream."""
    if not row.live_archive_enabled():
        raise RuntimeError("live Kalshi book archive requires CV_CAPTURE_POD=1 "
                            "and CV_KALSHI_BOOK_ARCHIVE_LIVE=1")
    client = GovernedClient()
    state: Dict[str, Any] = {}
    sports = list(sports) if sports else row.default_sports()
    result: Dict[str, Any] = {}
    while not stop():
        started = clock()
        result = capture_once(client=client, sports=sports, state=state, clock=clock,
                               output_root=output_root)
        states_seen = {m["state"] for sport in sports
                        for m in state.get("discovery_cache", {}).get(sport, {}).get("markets", [])}
        if "live" in states_seen:
            period = scope.LIVE_CADENCE_SEC
        elif "pregame" in states_seen:
            period = scope.PREGAME_CADENCE_SEC
        elif states_seen:
            period = scope.IDLE_CADENCE_SEC
        else:
            period = DISCOVERY_REFRESH_SEC
        sleep(max(0.0, started + period - clock()))
    return result


__all__ = ["GovernedClient", "CAPTURE_VERSION", "MAX_FETCH_CONCURRENCY", "MAX_DUE_PER_TICK",
           "DISCOVERY_REFRESH_SEC", "LIVE_ARCHIVE_ROOT", "SCRATCH_ARCHIVE_ROOT",
           "archive_path", "heartbeat_path", "book_row", "capture_once", "discover_cached",
           "live_archive_enabled", "run_pod_capture"]
