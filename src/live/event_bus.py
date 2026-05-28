"""event_bus.py — asyncio pub/sub for Live Engine v2.

Tiny, dependency-free message bus. Pollers `publish()` typed events;
the reactive projector and decision engine `subscribe()` to react.

Topics (string constants exported below)
----------------------------------------
pbp.made_shot, pbp.foul, pbp.sub, pbp.turnover, pbp.timeout,
pbp.period_end, lineup.defender_changed, snapshot.updated,
lines.refreshed, projection.updated, bet.recommended

Design
------
* In-process only — no IPC, no networking. Sub-ms publish latency.
* Subscribers receive events as dicts via async callbacks.
* Slow subscribers do NOT block fast ones (each call is dispatched
  as its own task).
* Publish is fire-and-forget; failures in one subscriber never
  break another (errors are logged + swallowed).
* Topics may be subscribed with wildcards: `pbp.*` matches all PBP.
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# ── topic constants ──────────────────────────────────────────────────
TOPIC_PBP_MADE_SHOT = "pbp.made_shot"
TOPIC_PBP_FOUL = "pbp.foul"
TOPIC_PBP_SUB = "pbp.sub"
TOPIC_PBP_TURNOVER = "pbp.turnover"
TOPIC_PBP_TIMEOUT = "pbp.timeout"
TOPIC_PBP_PERIOD_END = "pbp.period_end"
TOPIC_LINEUP_DEFENDER_CHANGED = "lineup.defender_changed"
TOPIC_SNAPSHOT_UPDATED = "snapshot.updated"
TOPIC_LINES_REFRESHED = "lines.refreshed"
TOPIC_PROJECTION_UPDATED = "projection.updated"
TOPIC_BET_RECOMMENDED = "bet.recommended"
TOPIC_PREGAME_INFO = "pregame.info"
TOPIC_BOOK_STALE = "book.stale"

ALL_TOPICS = (
    TOPIC_PBP_MADE_SHOT, TOPIC_PBP_FOUL, TOPIC_PBP_SUB,
    TOPIC_PBP_TURNOVER, TOPIC_PBP_TIMEOUT, TOPIC_PBP_PERIOD_END,
    TOPIC_LINEUP_DEFENDER_CHANGED, TOPIC_SNAPSHOT_UPDATED,
    TOPIC_LINES_REFRESHED, TOPIC_PROJECTION_UPDATED,
    TOPIC_BET_RECOMMENDED, TOPIC_PREGAME_INFO, TOPIC_BOOK_STALE,
)

# Type alias: a subscriber is an async function `(topic, event) -> None`.
Subscriber = Callable[[str, Dict[str, Any]], Awaitable[None]]


class EventBus:
    """In-process asyncio pub/sub.

    Subscribers register an async callback for one topic (or wildcard
    like ``pbp.*``). publish() dispatches the event to every matching
    subscriber as its own asyncio task — slow subscribers can't block
    the publisher or other subscribers.

    Stats
    -----
    `stats()` returns `{topic: count}` and `subscriber_count` for
    operator/dashboard visibility.
    """

    def __init__(self) -> None:
        # Map exact-topic OR wildcard-pattern → list of subscriber callables.
        self._subs: Dict[str, List[Subscriber]] = {}
        # Per-topic publish counter for ops visibility.
        self._counts: Dict[str, int] = {}
        # Total events published (across all topics).
        self._published_total: int = 0
        # Per-event timestamp circular buffer for latency probes.
        self._last_publish_ts: Optional[float] = None

    # ── subscribe / unsubscribe ─────────────────────────────────────
    def subscribe(self, topic: str, callback: Subscriber) -> Subscriber:
        """Register ``callback`` for ``topic``.

        Topic may be exact (``pbp.foul``) or a fnmatch pattern
        (``pbp.*``, ``*``). Returns the callback so callers can
        chain or unsubscribe by reference.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise TypeError(
                f"subscriber for {topic!r} must be `async def`; got {callback!r}")
        self._subs.setdefault(topic, []).append(callback)
        return callback

    def unsubscribe(self, topic: str, callback: Subscriber) -> bool:
        """Remove a single subscriber. Returns True if it was registered."""
        subs = self._subs.get(topic)
        if not subs:
            return False
        try:
            subs.remove(callback)
        except ValueError:
            return False
        if not subs:
            del self._subs[topic]
        return True

    # ── publish ─────────────────────────────────────────────────────
    async def publish(self, topic: str, event: Dict[str, Any]) -> int:
        """Fire ``event`` to every matching subscriber.

        Returns the number of subscriber tasks dispatched. Each
        subscriber runs in its own asyncio.Task — exceptions are
        logged and swallowed so one bad subscriber can't break the
        bus.
        """
        self._counts[topic] = self._counts.get(topic, 0) + 1
        self._published_total += 1
        self._last_publish_ts = time.time()

        dispatched = 0
        # Collect every callback whose registered topic matches.
        matches: List[Subscriber] = []
        for pattern, subs in list(self._subs.items()):
            if pattern == topic or fnmatch.fnmatchcase(topic, pattern):
                matches.extend(subs)

        for cb in matches:
            # Wrap in a task so a slow subscriber can't block others.
            asyncio.create_task(self._safe_dispatch(cb, topic, event))
            dispatched += 1
        return dispatched

    @staticmethod
    async def _safe_dispatch(cb: Subscriber, topic: str,
                             event: Dict[str, Any]) -> None:
        try:
            await cb(topic, event)
        except Exception as exc:  # noqa: BLE001
            log.warning("subscriber %s on %s raised: %s",
                        getattr(cb, "__name__", cb), topic, exc)

    # ── introspection ───────────────────────────────────────────────
    def subscriber_count(self, topic: Optional[str] = None) -> int:
        """Number of subscribers for a topic (exact match only).

        When ``topic is None`` returns the grand total across all
        registered patterns.
        """
        if topic is None:
            return sum(len(v) for v in self._subs.values())
        return len(self._subs.get(topic, []))

    def stats(self) -> Dict[str, Any]:
        """Diagnostic snapshot for ops dashboards / health probes."""
        return {
            "published_total": self._published_total,
            "per_topic_counts": dict(self._counts),
            "subscriber_count": self.subscriber_count(),
            "registered_topics": list(self._subs.keys()),
            "last_publish_ts": self._last_publish_ts,
        }


# Process-level singleton so pollers + reactive components share one bus.
_BUS_SINGLETON: Optional[EventBus] = None


def get_bus() -> EventBus:
    """Return the process-wide singleton EventBus (lazily constructed)."""
    global _BUS_SINGLETON
    if _BUS_SINGLETON is None:
        _BUS_SINGLETON = EventBus()
    return _BUS_SINGLETON


def reset_bus_for_tests() -> None:
    """Drop the singleton so tests start clean. Test-only helper."""
    global _BUS_SINGLETON
    _BUS_SINGLETON = None
