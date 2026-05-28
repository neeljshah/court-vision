"""latency_optimizer.py — caching + coalescing primitives for Live Engine v2.

Three small helpers shared across pollers + reactive components:

* ``lru_ttl_cache`` — functools.lru_cache wrapper with per-entry TTL.
* ``EventCoalescer`` — drops duplicate events within a sliding window
  so a flurry of identical PBP events doesn't trigger N redundant
  reprojections.
* ``is_game_live`` — fast schedule-aware check so pollers can skip
  RPC calls when the game hasn't tipped or is already final.

Design rule: zero external dependencies, no I/O in the hot path.
"""
from __future__ import annotations

import functools
import logging
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Hashable, Optional, Tuple

log = logging.getLogger(__name__)


# ── 1. TTL-aware LRU cache decorator ─────────────────────────────────────
def lru_ttl_cache(maxsize: int = 128, ttl_seconds: float = 30.0) -> Callable:
    """Decorator: LRU cache with per-entry TTL.

    Stores up to ``maxsize`` distinct call signatures. Entries older
    than ``ttl_seconds`` are recomputed transparently. Useful for
    rate-limited NBA endpoints where a 30-second cache eliminates
    almost all duplicate fetches at <1 ms overhead.

    Caveat: cache key is built from positional + keyword args (so all
    must be hashable). Mirrors functools.lru_cache constraints.
    """
    def decorator(fn: Callable) -> Callable:
        cache: "OrderedDict[Tuple, Tuple[float, Any]]" = OrderedDict()

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            hit = cache.get(key)
            if hit is not None:
                ts, value = hit
                if now - ts < ttl_seconds:
                    cache.move_to_end(key)
                    return value
                # expired — fall through and recompute
            value = fn(*args, **kwargs)
            cache[key] = (now, value)
            cache.move_to_end(key)
            while len(cache) > maxsize:
                cache.popitem(last=False)
            return value

        def cache_clear() -> None:
            cache.clear()

        def cache_info() -> Dict[str, Any]:
            return {"entries": len(cache), "maxsize": maxsize,
                    "ttl_seconds": ttl_seconds}

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info    # type: ignore[attr-defined]
        return wrapper

    return decorator


# ── 2. Event coalescer ──────────────────────────────────────────────────
class EventCoalescer:
    """Drop duplicate events within a sliding window.

    Use case: a PBP poll sees the same play twice because we polled
    just as the API was updating; without coalescing the reactive
    projector reprojects the same player twice. ``should_emit(key)``
    returns False on the second call within ``window_seconds``.

    Thread-safe? No — designed for single asyncio loop use.
    """

    def __init__(self, window_seconds: float = 2.0,
                 maxsize: int = 1024) -> None:
        self.window = window_seconds
        self.maxsize = maxsize
        # OrderedDict so we can evict oldest cheaply.
        self._seen: "OrderedDict[Hashable, float]" = OrderedDict()

    def should_emit(self, key: Hashable) -> bool:
        """Return True iff ``key`` hasn't been seen in the last window."""
        now = time.time()
        # Garbage-collect expired entries opportunistically.
        cutoff = now - self.window
        # Cheap forward sweep — OrderedDict iteration is in insertion order
        # but timestamps may not be monotonic if the clock jumps. Keep the
        # sweep bounded.
        evictions = 0
        for k, ts in list(self._seen.items()):
            if ts < cutoff:
                self._seen.pop(k, None)
                evictions += 1
                if evictions > 32:  # bounded per call
                    break
            else:
                break  # rest are newer

        last_seen = self._seen.get(key)
        if last_seen is not None and (now - last_seen) < self.window:
            return False

        self._seen[key] = now
        self._seen.move_to_end(key)
        # Hard cap so a misbehaving caller can't OOM us.
        while len(self._seen) > self.maxsize:
            self._seen.popitem(last=False)
        return True

    def reset(self) -> None:
        self._seen.clear()


# ── 3. is_game_live ─────────────────────────────────────────────────────
def is_game_live(snapshot: Optional[Dict[str, Any]]) -> bool:
    """True iff ``snapshot`` represents an in-progress NBA game.

    Accepts the canonical schema used by ``src/data/live.py``:
    ``snapshot["game_status"]`` ∈ {"PREGAME", "LIVE", "FINAL", ...}.

    Also tolerates the raw cdn.nba.com shape where the live indicator
    is ``gameStatus`` ∈ {1: pregame, 2: live, 3: final}.

    None / empty snapshot → False (treat as "not live yet").
    """
    if not snapshot:
        return False
    # Canonical schema first.
    status = snapshot.get("game_status")
    if status is not None:
        return str(status).upper() == "LIVE"
    # Raw cdn.nba.com fallback.
    raw = snapshot.get("gameStatus")
    if raw is not None:
        try:
            return int(raw) == 2
        except (TypeError, ValueError):
            return False
    return False


# ── 4. small profiler helper ─────────────────────────────────────────────
class LatencyProbe:
    """Lightweight wall-time profiler for end-to-end latency tests.

    Usage:
        probe = LatencyProbe()
        probe.mark("pbp_received")
        ...
        probe.mark("dashboard_rendered")
        elapsed_ms = probe.elapsed_ms("pbp_received", "dashboard_rendered")
    """

    def __init__(self) -> None:
        self._marks: Dict[str, float] = {}

    def mark(self, name: str) -> float:
        ts = time.time()
        self._marks[name] = ts
        return ts

    def elapsed_ms(self, start: str, end: str) -> float:
        a = self._marks.get(start)
        b = self._marks.get(end)
        if a is None or b is None:
            raise KeyError(f"missing mark(s): {start!r}, {end!r}")
        return (b - a) * 1000.0

    def marks(self) -> Dict[str, float]:
        return dict(self._marks)
