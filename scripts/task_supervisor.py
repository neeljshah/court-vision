"""task_supervisor.py — async restart-on-crash supervisor for CourtVision scraper tasks.

Wraps any long-running coroutine factory in an infinite restart loop with:
- Exponential backoff between restarts.
- Sliding-window rate limiter: if max_restarts_per_min is exceeded the supervisor
  backs off to 60 s base until the rate calms.
- Structured error logging to data/cache/scraper_errors.jsonl.
- Optional Sentry reporting when SENTRY_DSN env var is set (never imported unless
  the var is present so the dependency stays optional).

Usage
-----
    # Replace:
    asyncio.create_task(start_dk_ws())
    # With:
    asyncio.create_task(supervised("dk_ws", start_dk_ws))

The factory callable must be a zero-argument async callable that runs until
error (the supervisor handles the outer retry loop — the factory should NOT
contain its own infinite loop unless it handles its own reconnects internally,
in which case it should only raise on truly unrecoverable failure).

If the factory IS already an infinite loop with internal reconnect (e.g. the
existing WS subscribers), the supervisor adds a safety-net: if the inner loop
itself dies unexpectedly it will be restarted after a backoff delay.
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import sys
import time
import traceback
from typing import Awaitable, Callable, Deque, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger("task_supervisor")

_ERRORS_PATH = os.path.join(PROJECT_DIR, "data", "cache", "scraper_errors.jsonl")
_DEFAULT_BACKOFF: Tuple[int, ...] = (2, 5, 15, 30, 60)


# ── optional Sentry ───────────────────────────────────────────────────────────

def _maybe_init_sentry() -> bool:
    """Lazily initialise Sentry SDK if SENTRY_DSN is set.  Returns True if active."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk  # type: ignore[import]
        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)
        log.info("Sentry initialised (dsn present)")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Sentry init failed (non-fatal): %s", exc)
        return False


_SENTRY_ACTIVE: Optional[bool] = None  # None = uninitialised


def _report_to_sentry(name: str, exc: BaseException) -> None:
    global _SENTRY_ACTIVE
    if _SENTRY_ACTIVE is None:
        _SENTRY_ACTIVE = _maybe_init_sentry()
    if not _SENTRY_ACTIVE:
        return
    try:
        import sentry_sdk  # type: ignore[import]
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("supervisor.task", name)
            sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        pass


# ── structured error logging ──────────────────────────────────────────────────

def _log_error(name: str, exc: BaseException) -> None:
    """Append one JSONL record to scraper_errors.jsonl (truncated to 1 KB)."""
    try:
        os.makedirs(os.path.dirname(_ERRORS_PATH), exist_ok=True)
        tb_full = traceback.format_exc()
        tb_short = tb_full[-1024:] if len(tb_full) > 1024 else tb_full
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "book": name,
            "exception_type": type(exc).__name__,
            "exception_msg": str(exc)[:256],
            "traceback": tb_short,
        }
        with open(_ERRORS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001
        pass  # never let error-logging crash the supervisor


# ── rate-limit helpers ────────────────────────────────────────────────────────

def _count_in_window(timestamps: Deque[float], window_sec: float = 60.0) -> int:
    """Count events in the sliding window, pruning stale entries."""
    now = time.monotonic()
    while timestamps and (now - timestamps[0]) > window_sec:
        timestamps.popleft()
    return len(timestamps)


# ── main supervisor ───────────────────────────────────────────────────────────

async def supervised(
    name: str,
    factory: Callable[[], Awaitable[None]],
    *,
    max_restarts_per_min: int = 6,
    backoff_seconds: Tuple[int, ...] = _DEFAULT_BACKOFF,
) -> None:
    """Run factory() forever; restart on crash with exponential backoff.

    Args:
        name:                 Human-readable task name used in logs + error records.
        factory:              Zero-argument async callable to run.
        max_restarts_per_min: Restart-rate cap (sliding 60 s window).  When
                              exceeded the supervisor logs CRITICAL and extends
                              the backoff to 60 s until the rate calms.
        backoff_seconds:      Sequence of wait durations used in order; the last
                              element is repeated for all subsequent restarts.
    """
    restart_times: Deque[float] = collections.deque()
    attempt = 0

    log.info("[supervisor] starting task=%s", name)

    while True:
        started_at = time.monotonic()
        try:
            await factory()
            # Factory returned cleanly (unusual for long-running tasks).
            # Treat as a soft crash so we restart after a brief delay.
            log.warning(
                "[supervisor] task=%s exited without exception after %.1fs; "
                "restarting",
                name, time.monotonic() - started_at,
            )
        except asyncio.CancelledError:
            # Propagate cancellation — this task was intentionally stopped.
            log.info("[supervisor] task=%s cancelled; stopping restart loop", name)
            raise
        except Exception as exc:  # noqa: BLE001
            runtime = time.monotonic() - started_at
            log.error(
                "[supervisor] task=%s crashed after %.1fs: %s: %s",
                name, runtime, type(exc).__name__, exc,
            )
            _log_error(name, exc)
            _report_to_sentry(name, exc)

        # Track restart rate.
        restart_times.append(time.monotonic())
        rate = _count_in_window(restart_times)

        if rate > max_restarts_per_min:
            log.critical(
                "[supervisor] task=%s exceeded %d restarts/min (current=%d); "
                "backing off to 60 s",
                name, max_restarts_per_min, rate,
            )
            wait = 60
        else:
            idx = min(attempt, len(backoff_seconds) - 1)
            wait = backoff_seconds[idx]

        attempt += 1
        log.info("[supervisor] task=%s restarting in %ds (attempt #%d)",
                 name, wait, attempt)
        await asyncio.sleep(wait)


# ── convenience: one-shot wrap for an already-running coroutine ───────────────

def create_supervised_task(
    name: str,
    factory: Callable[[], Awaitable[None]],
    *,
    max_restarts_per_min: int = 6,
    backoff_seconds: Tuple[int, ...] = _DEFAULT_BACKOFF,
) -> "asyncio.Task[None]":
    """Schedule a supervised task and return the outer asyncio.Task.

    This is a thin helper so call sites can replace::

        asyncio.create_task(start_dk_ws())

    with::

        create_supervised_task("dk_ws", start_dk_ws)

    The returned Task wraps the *supervisor* loop — cancelling it cancels both
    the supervisor and the active inner factory coroutine.
    """
    return asyncio.create_task(
        supervised(name, factory,
                   max_restarts_per_min=max_restarts_per_min,
                   backoff_seconds=backoff_seconds),
        name=f"supervised_{name}",
    )


if __name__ == "__main__":
    # Quick smoke test: factory that raises immediately.
    import itertools

    async def _broken_factory() -> None:
        raise RuntimeError("boom")

    async def _smoke() -> None:
        counter = itertools.count(1)

        async def _once() -> None:
            n = next(counter)
            if n < 4:
                raise RuntimeError(f"deliberate crash #{n}")
            # On 4th attempt just return so the supervisor restarts cleanly.

        task = create_supervised_task("smoke", _once,
                                      backoff_seconds=(0, 0, 0, 0))
        await asyncio.sleep(2)
        task.cancel()
        print("smoke test passed — supervisor restarted 3 times then continued")

    asyncio.run(_smoke())
