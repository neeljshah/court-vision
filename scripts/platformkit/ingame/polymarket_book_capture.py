"""Dense, measurement-only Polymarket public order-book capture LOOP for the POD.

Twin of kalshi_book_capture.py, split the same way: discovery + classification
live in polymarket_scope.py; the snapshot-ROW shape + archive I/O live in
polymarket_book_row.py; this file owns only the per-tick capture LOOP
(GovernedClient, discovery cache, orchestration). NO CLI: local authoring
cannot accidentally start a live loop.

READ-ONLY BY CONSTRUCTION: this module + polymarket_scope.py + polymarket_book_row.py
import ONLY stdlib + kalshi_book_row (generic iso/append/write_json_atomic, no
HTTP) + kalshi_series_scope.cap_due_markets (pure list function). Nothing here
can place, cancel, or modify an order -- the venue's order-placement surface
(scripts/execute_loop/L10_polymarket_client.py's order-posting function and its
CLOB order-submission route) is never imported, never referenced. Enforced by a
grep-guard test
(tests/platformkit/test_polymarket_book_capture.py) that scans every
scripts/platformkit/ingame/polymarket_* module for the forbidden path
fragments, assembled at runtime so the guard itself never contains a literal
match to trip on.

RATE DISCIPLINE: a simple in-process token bucket (RATE_LIMIT_RPS=4 sustained)
paces every request; ThreadPoolExecutor caps concurrency at MAX_FETCH_CONCURRENCY
(4). Intentionally NOT the cross-process kalshi_rate_governor -- that module is
keyed to Kalshi caller shares and a Kalshi-only shared-pressure file; a single
Polymarket capture process needs only its own local budget (ponytail: upgrade
to a shared governor if a second Polymarket-capturing process is ever added).
On HTTP 429, GovernedClient retries with backoff_seconds() (1s, 2s, 4s, ...
capped at BACKOFF_CAP_SEC) up to RATE_LIMIT_MAX_RETRIES times, then gives up
and returns None -- never raises, never blocks the tick forever.

POD LAUNCH (mirrors docs/operations/runpod-runbook.md's mlb_book_capture line;
NOT executed):
  cd /workspace/nba-ai-system && CV_CAPTURE_POD=1 CV_POLYMARKET_BOOK_ARCHIVE_LIVE=1 \\
    nohup setsid python -c \\
    "from scripts.platformkit.ingame.polymarket_book_capture import run_pod_capture; \\
     run_pod_capture(stop=lambda: False)" </dev/null >/workspace/polymarket_book_capture.log 2>&1 &

NOT VERIFIED: no live pod run of this module yet; field names (clobTokenIds,
outcomes, startDate/endDate, the event "live" flag, volume24hr, liquidity) are
taken from Polymarket's public gamma docs and ingame_book_depth_poly.py's own
2026-07-04 live probe of /book, not re-confirmed here; the /midpoint response
shape ({"mid": <price>}) is assumed, not confirmed live; gamma /events and clob
/ok returned 200 from a US PC on 2026-09-14, but a SUSTAINED capture loop from a
US IP is not confirmed to be permitted by Polymarket's terms -- the pod is the
intended runner, not this PC; the sport-from-title keyword heuristic
(polymarket_scope.classify_sport) is a documented guess, not a venue field;
clobTokenIds/outcomes JSON-string parsing is defensive but untested against a
real malformed payload from the live venue.

Sources: https://docs.polymarket.com/ , https://clob.polymarket.com (unauthed
/book, /midpoint probed 2026-09-14).
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_polymarket_book_capture.py -q
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.ingame import polymarket_book_row as row
from scripts.platformkit.ingame import polymarket_scope as scope

logger = logging.getLogger(__name__)

RATE_LIMIT_RPS = 4.0  # sustained -- well under Polymarket's documented public limits
MAX_FETCH_CONCURRENCY = 4
BACKOFF_BASE_SEC = 1.0
BACKOFF_CAP_SEC = 30.0
RATE_LIMIT_MAX_RETRIES = 5
DISCOVERY_REFRESH_SEC = 600.0  # 10 minutes, per ROW Q03 spec

# Re-exported for callers/tests that only need the capture surface (row shape
# and archive helpers live in polymarket_book_row.py).
CAPTURE_VERSION = row.CAPTURE_VERSION
LIVE_ARCHIVE_ROOT = row.LIVE_ARCHIVE_ROOT
SCRATCH_ARCHIVE_ROOT = row.SCRATCH_ARCHIVE_ROOT
live_archive_enabled = row.live_archive_enabled
archive_path = row.archive_path
heartbeat_path = row.heartbeat_path
book_row = row.book_row


def backoff_seconds(attempt: int, base: float = BACKOFF_BASE_SEC, cap: float = BACKOFF_CAP_SEC) -> float:
    """Pure exponential schedule: attempt 1 -> base, 2 -> 2*base, 3 -> 4*base,
    ..., capped at *cap*. attempt <= 0 -> 0.0 (no backoff)."""
    if attempt <= 0:
        return 0.0
    return min(cap, base * (2 ** (attempt - 1)))


class _TokenBucket:
    """ponytail: minimal in-process limiter (rung 7 -- fewest lines that hold
    the invariant), not a cross-process governor; see module docstring."""

    def __init__(self, rate: float = RATE_LIMIT_RPS, capacity: float = RATE_LIMIT_RPS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.rate, self.capacity, self.clock = rate, capacity, clock
        self.tokens = capacity
        self.last = clock()
        self._lock = Lock()

    def acquire(self, sleep_fn: Callable[[float], None] = time.sleep) -> None:
        with self._lock:
            now = self.clock()
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
            self.last = now
            wait = 0.0 if self.tokens >= 1.0 else (1.0 - self.tokens) / self.rate
            self.tokens = max(0.0, self.tokens - 1.0)
        if wait > 0.0:
            sleep_fn(wait)


class GovernedClient:
    """The only HTTP path: token-bucket-paced GET with 429 backoff. Never
    raises -- returns (None, ts_ms) on any failure or after exhausting
    retries. ts_ms is stamped immediately before each HTTP send."""

    def __init__(self, opener: Callable[..., Any] = urllib.request.urlopen,
                 sleep_fn: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 max_retries: int = RATE_LIMIT_MAX_RETRIES) -> None:
        self.bucket = _TokenBucket(clock=clock)
        self.opener = opener
        self.sleep_fn = sleep_fn
        self.max_retries = max_retries
        self.n_429 = 0
        self.n_errors = 0
        self._lock = Lock()

    def get(self, url: str) -> Tuple[Optional[Any], int]:
        attempt = 0
        while True:
            self.bucket.acquire(self.sleep_fn)
            ts_ms = int(time.time() * 1000)
            try:
                with self.opener(urllib.request.Request(url), timeout=15.0) as response:
                    return json.loads(response.read().decode("utf-8")), ts_ms
            except urllib.error.HTTPError as exc:
                with self._lock:
                    self.n_errors += 1
                    if exc.code == 429:
                        self.n_429 += 1
                if exc.code == 429 and attempt < self.max_retries:
                    attempt += 1
                    self.sleep_fn(backoff_seconds(attempt))
                    continue
                return None, ts_ms
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                with self._lock:
                    self.n_errors += 1
                return None, ts_ms


def discover_cached(client: "GovernedClient", state: Dict[str, Any], now: datetime,
                     clock: Callable[[], float] = time.monotonic) -> List[Dict[str, Any]]:
    """Every sports market across all discovery pages, refreshed at most every
    DISCOVERY_REFRESH_SEC. One bucket (not per-sport, unlike Kalshi): gamma's
    tag_slug=sports discovery query returns every sport in one paginated pass."""
    cache = state.setdefault("discovery_cache", {})
    nowc = clock()
    if cache and nowc - cache.get("ts", -1e18) < DISCOVERY_REFRESH_SEC:
        return cache["markets"]
    events = scope.fetch_events(lambda url: client.get(url)[0])
    markets = scope.extract_markets(events, now)
    cache["ts"], cache["markets"] = nowc, markets
    return markets


def capture_once(*, client: Optional["GovernedClient"] = None, now: Optional[datetime] = None,
                  state: Optional[Dict[str, Any]] = None, clock: Callable[[], float] = time.monotonic,
                  output_root: Optional[Path] = None,
                  max_concurrency: int = MAX_FETCH_CONCURRENCY) -> Dict[str, Any]:
    """One pass: refresh discovery (cached), re-classify every cached market's
    state, poll the due ones (priority-capped at scope.MAX_DUE_PER_TICK, live
    first), append per-token rows, write one heartbeat per sport seen."""
    client = client or GovernedClient()
    state = state if state is not None else {}
    now = now or datetime.now(timezone.utc)
    last_polled = state.setdefault("last_polled", {})
    nowc = clock()

    markets = discover_cached(client, state, now, clock)
    for m in markets:
        m["state"], m["cadence_sec"] = scope.classify_event_state(m, now)

    due = [m for m in markets if m.get("condition_id")
           and nowc - last_polled.get(m["condition_id"], 0.0) >= m["cadence_sec"]]
    n_due_before_cap = len(due)
    due, offset, bound = scope.cap_due_markets(due, state.get("due_rotation", 0), scope.MAX_DUE_PER_TICK)
    state["due_rotation"] = offset
    if bound:
        logger.warning("polymarket_book_capture due-cap bound: %d due markets, capped to %d this tick",
                        n_due_before_cap, len(due))
    current_ids = {m["condition_id"] for m in markets if m.get("condition_id")}
    for stale in [k for k in last_polled if k not in current_ids]:
        del last_polled[stale]

    def fetch_one(task: Tuple[Dict[str, Any], int, str]) -> Any:
        market, idx, token_id = task
        enqueue_ts_ms = int(time.time() * 1000)
        try:
            book_body, ts_ms = client.get(scope.book_url(token_id))
            mid_body, _ = client.get(scope.midpoint_url(token_id))
            return market, idx, token_id, book_body, mid_body, ts_ms, enqueue_ts_ms, None
        except Exception as exc:  # noqa: BLE001 -- one bad token must never kill the pass
            return market, idx, token_id, None, None, enqueue_ts_ms, enqueue_ts_ms, "%s: %s" % (type(exc).__name__, exc)

    tasks = [(m, idx, tid) for m in due for idx, tid in enumerate(m.get("token_ids", []))]
    with ThreadPoolExecutor(max_workers=max(1, min(int(max_concurrency), MAX_FETCH_CONCURRENCY))) as executor:
        fetched = list(executor.map(fetch_one, tasks))

    capture_ts = row.iso(now)
    rows_by_sport: Dict[str, List[Dict[str, Any]]] = {}
    polled: set = set()
    for market, idx, token_id, book_body, mid_body, ts_ms, enqueue_ts_ms, reason in fetched:
        polled.add(market["condition_id"])
        one_row = row.book_row(market, token_id, idx, book_body, mid_body, ts_ms, capture_ts, enqueue_ts_ms) \
            if book_body is not None else \
            row.fetch_error_row(market, token_id, idx, ts_ms, enqueue_ts_ms, capture_ts, reason)
        rows_by_sport.setdefault(market["sport"], []).append(one_row)
    for cid in polled:
        last_polled[cid] = nowc

    hb_state = state.setdefault("hb", {})
    by_sport: Dict[str, Any] = {}
    present_sports = sorted({m["sport"] for m in markets}) or sorted(rows_by_sport)
    for sport in present_sports:
        rows = rows_by_sport.get(sport, [])
        path = (output_root / sport / (now.strftime("%Y-%m-%d") + ".jsonl")) if output_root \
            else row.archive_path(sport, now)
        for one_row in rows:
            row.append(path, one_row)
        n_snap = sum(1 for r in rows if r.get("record_type") == "snapshot")
        counts = {"live": 0, "pregame": 0, "idle": 0}
        for m in markets:
            if m["sport"] == sport:
                counts[m["state"]] = counts.get(m["state"], 0) + 1
        prior = hb_state.get(sport, {})
        heartbeat = {"sport": sport, "venue": "polymarket", "updated_ts": capture_ts,
                     "last_snapshot_ts": capture_ts if n_snap else prior.get("last_snapshot_ts"),
                     "n_snapshot_rows_tick": n_snap, "n_markets_live": counts["live"],
                     "n_markets_pregame": counts["pregame"], "n_markets_idle": counts["idle"],
                     "n_429_total": client.n_429, "n_errors_total": client.n_errors}
        hb_state[sport] = heartbeat
        hb_path = (output_root / sport / "_heartbeat.json") if output_root else row.heartbeat_path(sport)
        row.write_json_atomic(hb_path, heartbeat)
        by_sport[sport] = {"path": str(path), "n_rows": len(rows), "n_snapshot_rows": n_snap,
                            "heartbeat_path": str(hb_path)}
    return {"n_discovered": len(markets), "n_due": len(due), "due_cap_bound": bound,
            "n_429": client.n_429, "n_errors": client.n_errors, "by_sport": by_sport}


def run_pod_capture(*, stop: Callable[[], bool], sleep: Callable[[float], None] = time.sleep,
                     clock: Callable[[], float] = time.monotonic,
                     output_root: Optional[Path] = None) -> Dict[str, Any]:
    """POD-only loop; refuses to start unless the POD owns the live archive.
    DEADLINE PACING (mirrors kalshi_book_capture.run_pod_capture): each tick
    sleeps only the residual to its own start+period, so an overrunning tick
    never piles up drift."""
    if not row.live_archive_enabled():
        raise RuntimeError("live Polymarket book archive requires CV_CAPTURE_POD=1 "
                            "and CV_POLYMARKET_BOOK_ARCHIVE_LIVE=1")
    client = GovernedClient()
    state: Dict[str, Any] = {}
    result: Dict[str, Any] = {}
    while not stop():
        started = clock()
        result = capture_once(client=client, state=state, clock=clock, output_root=output_root)
        states_seen = {m["state"] for m in state.get("discovery_cache", {}).get("markets", [])}
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


__all__ = ["GovernedClient", "CAPTURE_VERSION", "MAX_FETCH_CONCURRENCY", "RATE_LIMIT_RPS",
           "RATE_LIMIT_MAX_RETRIES", "BACKOFF_BASE_SEC", "BACKOFF_CAP_SEC", "DISCOVERY_REFRESH_SEC",
           "LIVE_ARCHIVE_ROOT", "SCRATCH_ARCHIVE_ROOT", "backoff_seconds", "live_archive_enabled",
           "archive_path", "heartbeat_path", "book_row", "discover_cached", "capture_once",
           "run_pod_capture"]
