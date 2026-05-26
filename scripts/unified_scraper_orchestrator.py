"""unified_scraper_orchestrator.py - R16_E6 single-process scraper orchestrator.

Replaces 3 standalone daemons (FD / Bov / Pin) with one asyncio event loop.

Why
---
* Previously: 3 separate Python processes, 3 separate PIDs, 3 separate log
  streams, 3 separate dedup memories, 3x the conda env load.
* Now: 1 process, 1 PID, 1 log stream, unified health endpoint, shared HTTP
  connection pool. Scales cleanly to 5-10 books without a process per book.

Design
------
* Single asyncio event loop.
* Each book is an async coroutine driving its own interval:
    fd   60s   (FanDuel,  curl_cffi chrome120 impersonate)
    bov  60s   (Bovada,   requests + urllib fallback)
    pin  30s   (Pinnacle, curl_cffi chrome120 impersonate) -- match R16_E1 tier
* curl_cffi calls are sync -> wrapped in asyncio.to_thread() for parallelism.
* Each book still writes to its own canonical CSV (data/lines/<date>_<book>.csv).
* Per-scraper exception handling: if one book crashes (e.g. Bov 403s), the
  others keep running. Failures are logged but the coroutine continues.
* Aiohttp health server on localhost:8765/health returns JSON status.

Output (probe artifact)
-----------------------
data/cache/probe_R16_E6_unified_scraper_results.json with shape:
    {
      "orchestrator_pid": <int>,
      "books_alive": ["fd", "bov", "pin"],
      "ticks_per_book_30min": {"fd": N, "bov": N, "pin": N},
      "p99_tick_latency_ms": {"fd": N, "bov": N, "pin": N},
    }

CLI
---
    python scripts/unified_scraper_orchestrator.py                # default
    python scripts/unified_scraper_orchestrator.py --health-port 8765
    python scripts/unified_scraper_orchestrator.py --duration-sec 1800  # stop after 30min
    python scripts/unified_scraper_orchestrator.py --books fd,pin       # subset
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from collections import deque
from datetime import datetime
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Import the existing scrapers' tick functions. We reuse their normalize +
# write logic so the CSV schemas stay exactly the same as the standalone
# daemons -- this is the "unified output" contract.
from scripts.probe_R15_curl_cffi_fanduel import one_snapshot as _fd_one_snapshot
from scripts.bov_scraper_daemon import fetch_cycle as _bov_fetch_cycle
from scripts.pinnacle_scraper import run_once as _pin_run_once

# ── logging ─────────────────────────────────────────────────────────────────

log = logging.getLogger("unified_scraper")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

# ── constants ───────────────────────────────────────────────────────────────

CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
PROBE_RESULTS_PATH = os.path.join(
    CACHE_DIR, "probe_R16_E6_unified_scraper_results.json")
PIDS_PATH = os.path.join(CACHE_DIR, "scraper_daemon_pids.json")

# Match R16_E1's per-book scrape cadence.
DEFAULT_INTERVALS_SEC: Dict[str, int] = {
    "fd":  60,
    "bov": 60,
    "pin": 30,
}

# Latency ring buffer size per book (large enough for 30+ min of ticks).
_LATENCY_BUF_SIZE = 200


# ── per-book sync tick wrappers (returned dict goes into health state) ──────

def _tick_fd_sync() -> Dict[str, Any]:
    """One FanDuel tick. Calls existing one_snapshot(); returns its status."""
    s = _fd_one_snapshot()
    return {
        "rows": int(s.get("rows", 0)),
        "ok": bool(s.get("ok", False)),
        "events": int(s.get("events", 0)),
        "csv": s.get("csv"),
        "ran_at": s.get("ran_at"),
    }


def _tick_bov_sync() -> Dict[str, Any]:
    """One Bovada tick. Uses fetch_cycle directly -- bypasses run_daemon's
    5-min floor since the orchestrator owns the scheduler now.
    """
    summary = _bov_fetch_cycle(["nba", "wnba", "mlb"])
    return {
        "rows_new": int(summary.get("rows_new", 0)),
        "rows_total_after": int(summary.get("rows_total_after", 0)),
        "out_path": summary.get("out_path"),
        "blocked_sports": summary.get("blocked_sports", []),
        "sports_with_data": summary.get("sports_with_data", []),
    }


def _tick_pin_sync() -> Dict[str, Any]:
    """One Pinnacle tick."""
    s = _pin_run_once(fetch_props=True)
    return {
        "n_matchups": int(s.get("n_matchups", 0)),
        "n_player_props": int(s.get("n_player_props", 0)),
        "n_prop_rows_written": int(s.get("n_prop_rows_written", 0)),
        "n_mainline_rows_written": int(s.get("n_mainline_rows_written", 0)),
        "endpoints_tried": len(s.get("endpoints_tried", [])),
    }


# Default registry. Tests can override by passing a custom mapping.
DEFAULT_TICK_FNS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "fd":  _tick_fd_sync,
    "bov": _tick_bov_sync,
    "pin": _tick_pin_sync,
}


# ── per-book health state ───────────────────────────────────────────────────

class BookState:
    """Mutable rolling-window state for one scraper. Pure data, no I/O."""

    __slots__ = (
        "name", "interval_sec", "total_ticks", "total_errors",
        "last_tick_epoch", "last_status_code", "last_payload",
        "last_error", "latencies_ms", "started_epoch", "alive",
    )

    def __init__(self, name: str, interval_sec: int) -> None:
        self.name = name
        self.interval_sec = interval_sec
        self.total_ticks: int = 0
        self.total_errors: int = 0
        self.last_tick_epoch: Optional[float] = None
        self.last_status_code: str = "init"  # "ok" | "err" | "init"
        self.last_payload: Dict[str, Any] = {}
        self.last_error: Optional[str] = None
        self.latencies_ms: Deque[float] = deque(maxlen=_LATENCY_BUF_SIZE)
        self.started_epoch: float = time.time()
        self.alive: bool = True

    def to_health_dict(self) -> Dict[str, Any]:
        now = time.time()
        last_ago: Optional[float] = None
        if self.last_tick_epoch is not None:
            last_ago = round(now - self.last_tick_epoch, 1)
        p99 = _percentile(list(self.latencies_ms), 99) if self.latencies_ms else None
        p50 = _percentile(list(self.latencies_ms), 50) if self.latencies_ms else None
        return {
            "alive": self.alive,
            "interval_sec": self.interval_sec,
            "total_ticks": self.total_ticks,
            "total_errors": self.total_errors,
            "last_tick_ago_sec": last_ago,
            "last_status_code": self.last_status_code,
            "last_error": self.last_error,
            "last_payload": self.last_payload,
            "p50_tick_latency_ms": p50,
            "p99_tick_latency_ms": p99,
            "uptime_sec": round(now - self.started_epoch, 1),
        }


def _percentile(values: List[float], p: int) -> Optional[float]:
    """Simple percentile without numpy dependency. Returns None on empty."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 2)
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return round(s[lo] + (s[hi] - s[lo]) * frac, 2)


# ── per-book scheduler coroutine ────────────────────────────────────────────

async def _run_book_loop(
    state: BookState,
    tick_fn: Callable[[], Dict[str, Any]],
    stop_event: asyncio.Event,
) -> None:
    """Drive one book at its own interval. Per-tick exception isolation:
    one bad tick logs + marks last_status_code='err' but the loop keeps
    running. The book is only marked alive=False if asyncio.CancelledError
    propagates (orchestrator shutdown).
    """
    log.info("[%s] book loop start interval=%ds", state.name, state.interval_sec)
    try:
        while not stop_event.is_set():
            t0 = time.monotonic()
            try:
                # Run the sync scraper tick in a worker thread so the event
                # loop stays responsive (curl_cffi is blocking).
                payload = await asyncio.to_thread(tick_fn)
                latency_ms = (time.monotonic() - t0) * 1000.0
                state.latencies_ms.append(latency_ms)
                state.total_ticks += 1
                state.last_tick_epoch = time.time()
                state.last_status_code = "ok"
                state.last_payload = payload
                state.last_error = None
                log.info("[%s] tick #%d ok latency=%.0fms payload=%s",
                         state.name, state.total_ticks, latency_ms,
                         _compact(payload))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- per-book isolation
                latency_ms = (time.monotonic() - t0) * 1000.0
                state.latencies_ms.append(latency_ms)
                state.total_errors += 1
                state.last_status_code = "err"
                state.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("[%s] tick FAILED (#err %d): %s",
                            state.name, state.total_errors, state.last_error)
            # Wait either interval_sec or until stop_event fires.
            try:
                await asyncio.wait_for(stop_event.wait(),
                                       timeout=state.interval_sec)
            except asyncio.TimeoutError:
                pass  # normal -- interval elapsed, run next tick
    except asyncio.CancelledError:
        log.info("[%s] book loop cancelled", state.name)
        raise
    finally:
        state.alive = False
        log.info("[%s] book loop exit (ticks=%d errors=%d)",
                 state.name, state.total_ticks, state.total_errors)


def _compact(d: Dict[str, Any]) -> str:
    """One-line compact repr for log readability."""
    items = []
    for k, v in d.items():
        if isinstance(v, list):
            items.append(f"{k}={len(v)}")
        elif isinstance(v, dict):
            items.append(f"{k}={{...{len(v)}}}")
        else:
            items.append(f"{k}={v}")
    return " ".join(items)


# ── health HTTP server (aiohttp) ────────────────────────────────────────────

async def _start_health_server(
    states: Dict[str, BookState],
    port: int,
) -> Any:
    """Start a minimal aiohttp server. /health returns JSON status.

    Returns the runner object so the caller can shut it down cleanly.
    """
    from aiohttp import web  # noqa: PLC0415 -- defer import until called

    async def health_handler(request: "web.Request") -> "web.Response":
        body = {
            "ok": all(s.alive for s in states.values()),
            "now": datetime.utcnow().isoformat(),
            "books": {name: s.to_health_dict() for name, s in states.items()},
        }
        return web.json_response(body)

    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    log.info("health server listening on http://127.0.0.1:%d/health", port)
    return runner


# ── PID file management ─────────────────────────────────────────────────────

def _write_pid_file(books: List[str]) -> None:
    """Write the single orchestrator PID to data/cache/scraper_daemon_pids.json.
    Old 3-daemon code wrote one entry per daemon; we collapse to one.
    """
    pid = os.getpid()
    payload = {
        "orchestrator_pid": pid,
        "books": books,
        "started_at": datetime.utcnow().isoformat(),
    }
    try:
        with open(PIDS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        log.info("wrote PID file %s pid=%d", PIDS_PATH, pid)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not write PID file: %s", exc)


def _remove_pid_file() -> None:
    try:
        if os.path.exists(PIDS_PATH):
            os.remove(PIDS_PATH)
            log.info("removed PID file %s", PIDS_PATH)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not remove PID file: %s", exc)


# ── probe artifact writer ───────────────────────────────────────────────────

def write_probe_results(
    states: Dict[str, BookState],
    path: str = PROBE_RESULTS_PATH,
    elapsed_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Snapshot current state to the R16_E6 probe-results JSON."""
    books_alive = [n for n, s in states.items() if s.alive]
    ticks = {n: s.total_ticks for n, s in states.items()}
    p99 = {
        n: (_percentile(list(s.latencies_ms), 99) if s.latencies_ms else None)
        for n, s in states.items()
    }
    payload = {
        "orchestrator_pid": os.getpid(),
        "books_alive": books_alive,
        "ticks_per_book_30min": ticks,  # raw tick counts; caller chooses window
        "p99_tick_latency_ms": p99,
        "elapsed_sec": elapsed_sec,
        "captured_at": datetime.utcnow().isoformat(),
        "per_book_detail": {n: s.to_health_dict() for n, s in states.items()},
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return payload


# ── orchestrator main ───────────────────────────────────────────────────────

async def run_orchestrator(
    books: List[str],
    intervals: Dict[str, int],
    duration_sec: Optional[float] = None,
    health_port: int = 8765,
    tick_fns: Optional[Dict[str, Callable[[], Dict[str, Any]]]] = None,
    enable_health: bool = True,
) -> Dict[str, BookState]:
    """Top-level async entry. Runs all book loops + the health server until
    duration_sec elapses or a signal arrives.
    """
    tick_fns = tick_fns or DEFAULT_TICK_FNS
    states: Dict[str, BookState] = {
        name: BookState(name, intervals.get(name, DEFAULT_INTERVALS_SEC.get(name, 60)))
        for name in books
    }

    stop_event = asyncio.Event()

    # SIGINT / SIGTERM -> graceful stop
    loop = asyncio.get_running_loop()
    def _signal_stop() -> None:
        log.info("signal received -> stopping orchestrator")
        stop_event.set()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_stop)
        except (NotImplementedError, RuntimeError):
            # Windows / restricted envs: signal handlers may not be available.
            pass

    # Start per-book tasks
    book_tasks: List[asyncio.Task] = []
    for name in books:
        fn = tick_fns.get(name)
        if fn is None:
            log.warning("no tick fn registered for book %r, skipping", name)
            continue
        book_tasks.append(asyncio.create_task(
            _run_book_loop(states[name], fn, stop_event), name=f"book-{name}"))

    # Start health server
    runner = None
    if enable_health:
        try:
            runner = await _start_health_server(states, health_port)
        except Exception as exc:  # noqa: BLE001
            log.warning("health server failed to start on :%d: %s",
                        health_port, exc)

    # Write probe results periodically while running.
    started = time.time()
    try:
        if duration_sec is not None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=duration_sec)
            except asyncio.TimeoutError:
                log.info("duration_sec=%s elapsed -> stopping", duration_sec)
                stop_event.set()
        else:
            await stop_event.wait()
    finally:
        # Snapshot probe artifact regardless of how we exited.
        elapsed = time.time() - started
        write_probe_results(states, elapsed_sec=elapsed)

        stop_event.set()
        for t in book_tasks:
            t.cancel()
        # Wait for tasks to finish cancelling.
        await asyncio.gather(*book_tasks, return_exceptions=True)

        if runner is not None:
            try:
                await runner.cleanup()
            except Exception:  # noqa: BLE001
                pass

    return states


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--books", default="fd,bov,pin",
                    help="Comma-sep book codes (default: fd,bov,pin).")
    ap.add_argument("--fd-interval-sec",  type=int, default=DEFAULT_INTERVALS_SEC["fd"])
    ap.add_argument("--bov-interval-sec", type=int, default=DEFAULT_INTERVALS_SEC["bov"])
    ap.add_argument("--pin-interval-sec", type=int, default=DEFAULT_INTERVALS_SEC["pin"])
    ap.add_argument("--health-port", type=int, default=8765)
    ap.add_argument("--duration-sec", type=float, default=None,
                    help="Stop after this many seconds (default: run forever).")
    ap.add_argument("--no-health", action="store_true",
                    help="Disable the health HTTP server (testing).")
    args = ap.parse_args(argv)

    books = [b.strip().lower() for b in args.books.split(",") if b.strip()]
    intervals = {
        "fd":  args.fd_interval_sec,
        "bov": args.bov_interval_sec,
        "pin": args.pin_interval_sec,
    }

    _write_pid_file(books)
    try:
        asyncio.run(run_orchestrator(
            books=books,
            intervals=intervals,
            duration_sec=args.duration_sec,
            health_port=args.health_port,
            enable_health=not args.no_health,
        ))
    finally:
        _remove_pid_file()
    return 0


if __name__ == "__main__":
    sys.exit(main())
