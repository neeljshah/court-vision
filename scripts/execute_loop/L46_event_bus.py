"""L46_event_bus.py — Cross-layer EventBus for the autonomous NBA execution loop.

Purpose
-------
Formalises the inter-layer notification pattern used across the execute_loop
stack.  Instead of each layer soft-importing its target layer directly (creating
an implicit, hard-to-audit dependency graph), publishers emit named Events and
subscribers register handlers against name patterns.  This makes the dependency
graph explicit, observable, and testable without changing existing direct-call
code paths (backward compatible — both approaches work simultaneously).

Environment Variables
---------------------
None required.  The EventBus is configuration-free by design: callers pass a
``persistence_path`` at construction time when durable replay is needed.

Paper vs Live Mode (MODE GATING)
---------------------------------
L46 is mode-agnostic — it routes events but has no live-mode behaviour itself.
The ``live`` tokens that appear in payload examples (e.g. event names such as
``"bet.live"``) are arbitrary publisher-defined strings, not mode gates.
L46 neither reads nor writes any SUBMISSION_MODE / LIVE_MODE environment
variable and carries no conditional logic that differs between paper and live
deployments.  Mode enforcement is the responsibility of the publishing layer
(e.g. L44 asserts paper mode before any submission layer publishes).

Persistence Policy
------------------
When a ``persistence_path`` (Path) is supplied to EventBus.__init__, every
published Event is appended as a single JSONL line to that file.  We use plain
``open(path, "a")`` (append mode) rather than the atomic rename-replace pattern
used for snapshot files.  This is safe because:

  1. Each line is a self-contained JSON object terminated by ``\\n``.
  2. On POSIX, writes ≤ PIPE_BUF (≥4 096 bytes) to ``O_APPEND`` files are
     atomic at the kernel level.  A single serialised Event is always well under
     this limit in practice.
  3. On Windows (where PIPE_BUF guarantees do not apply), the EventBus is
     single-threaded in the common deploy scenario (one process per layer), so
     interleaving is not a concern.  For multi-process scenarios on Windows,
     callers should use a dedicated persistence_path per process.

The atomic rename-replace pattern (_atomic_write_text) is reserved for cases
where the *entire* file must be consistent (snapshots, config dumps).  For an
append-only log it would require reading the full file on every publish, which
is prohibitively expensive.
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Event:
    """An immutable event record emitted by a layer."""

    name: str        # e.g. "bet.settled", "fill.received", "incident.opened"
    source: str      # producing layer, e.g. "L7", "L14"
    payload: dict    # JSON-serialisable arbitrary data
    ts: str          # ISO 8601 UTC timestamp
    event_id: str    # UUID4 string


@dataclass
class Subscription:
    """A registered handler bound to a name_pattern on a specific layer."""

    name_pattern: str               # glob-style: "bet.*", "*.settled", "*"
    handler: Callable[[Event], None]
    layer: str                      # subscribing layer name, e.g. "L22"


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class EventBus:
    """Pub/sub event bus with optional JSONL persistence and replay.

    Parameters
    ----------
    persistence_path:
        When supplied, each published Event is appended as a JSONL line to
        this file.  The file is created (including parent directories) on
        first write.  Pass ``None`` (default) to disable persistence.
    """

    def __init__(self, persistence_path: Optional[Path] = None) -> None:
        self._persistence_path: Optional[Path] = persistence_path
        self._subscriptions: List[Subscription] = []
        # Stats counters
        self._events_published: int = 0
        self._events_dispatched: int = 0
        self._handler_errors: int = 0
        self._by_event_name: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def publish(self, name: str, source: str, payload: dict) -> Event:
        """Create an Event, dispatch to matching subscribers, and persist.

        Handler exceptions are caught and counted; they never interrupt the
        dispatch loop so that all matching subscribers always receive the event.

        Parameters
        ----------
        name:
            Dot-separated event name, e.g. ``"bet.settled"``.
        source:
            Identifier of the emitting layer, e.g. ``"L7"``.
        payload:
            JSON-serialisable dict carrying event data.

        Returns
        -------
        Event
            The fully-constructed, immutable Event record.
        """
        event = Event(
            name=name,
            source=source,
            payload=payload,
            ts=datetime.now(timezone.utc).isoformat(),
            event_id=str(uuid.uuid4()),
        )

        self._events_published += 1
        self._by_event_name[name] = self._by_event_name.get(name, 0) + 1

        # Dispatch to matching subscribers
        for sub in list(self._subscriptions):
            if fnmatch.fnmatch(name, sub.name_pattern):
                try:
                    sub.handler(event)
                    self._events_dispatched += 1
                except Exception as exc:  # noqa: BLE001
                    self._handler_errors += 1
                    logger.warning(
                        "EventBus: handler error in layer %s for event %r: %s",
                        sub.layer, name, exc,
                    )

        # Persist if configured
        if self._persistence_path is not None:
            self._append_event(event)

        return event

    def subscribe(
        self,
        name_pattern: str,
        handler: Callable[[Event], None],
        layer: str,
    ) -> Subscription:
        """Register a handler for events whose name matches *name_pattern*.

        Parameters
        ----------
        name_pattern:
            Glob-style pattern evaluated via ``fnmatch.fnmatch``.  Supports
            ``*`` (any substring) and ``?`` (any single character).
            Examples: ``"bet.*"``, ``"*.settled"``, ``"*"``.
        handler:
            Callable accepting a single :class:`Event` argument.
        layer:
            Human-readable name of the subscribing layer, e.g. ``"L22"``.

        Returns
        -------
        Subscription
            The created subscription object; pass to :meth:`unsubscribe` to
            deregister.
        """
        sub = Subscription(name_pattern=name_pattern, handler=handler, layer=layer)
        self._subscriptions.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> bool:
        """Remove *sub* from the active subscription list.

        Returns
        -------
        bool
            ``True`` if the subscription was found and removed, ``False`` if
            it was not present (already removed or never registered).
        """
        try:
            self._subscriptions.remove(sub)
            return True
        except ValueError:
            return False

    def replay(self, since: Optional[str] = None) -> List[Event]:
        """Read persisted events from the JSONL file; no dispatch occurs.

        Parameters
        ----------
        since:
            Optional ISO 8601 UTC timestamp string.  When supplied, only
            events whose ``ts`` field is *greater than or equal to* this
            value are returned.  Comparison is lexicographic, which is
            correct for ISO 8601 strings in the same timezone.

        Returns
        -------
        list[Event]
            Events in chronological order as recorded in the persistence file.
            Returns an empty list if no persistence path was configured or the
            file does not yet exist.
        """
        if self._persistence_path is None or not self._persistence_path.exists():
            return []

        events: List[Event] = []
        with open(self._persistence_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    evt = Event(**data)
                    if since is None or evt.ts >= since:
                        events.append(evt)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("EventBus.replay: skipping malformed line: %s", exc)

        return events

    def stats(self) -> dict:
        """Return a snapshot of bus activity counters.

        Returns
        -------
        dict
            Keys: ``events_published``, ``events_dispatched``, ``subscribers``,
            ``errors``, ``by_event_name`` (dict mapping name → count).
        """
        return {
            "events_published": self._events_published,
            "events_dispatched": self._events_dispatched,
            "subscribers": len(self._subscriptions),
            "errors": self._handler_errors,
            "by_event_name": dict(self._by_event_name),
        }

    def clear_subscribers(self) -> None:
        """Remove all registered subscriptions.

        Intended for test isolation — call at the start or end of each test
        that interacts with the module-level singleton so handler state does
        not leak between tests.
        """
        self._subscriptions.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_event(self, event: Event) -> None:
        """Append *event* as a single JSONL line to the persistence file.

        Uses a read-append-write-replace pattern (temp file + os.replace) to
        ensure the JSONL file is never left in a partially-written state.
        Each published Event is appended as a self-contained JSON object
        terminated by ``\\n``; on crash the previous content is preserved.
        """
        if self._persistence_path is None:
            return
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(event)) + "\n"
        # Read existing content, append new line, atomically replace the file.
        existing = b""
        if self._persistence_path.exists():
            existing = self._persistence_path.read_bytes()
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._persistence_path.parent,
            prefix=".tmp_L46_",
            suffix=".jsonl",
        )
        try:
            with os.fdopen(tmp_fd, "wb") as fh:
                fh.write(existing + line.encode("utf-8"))
            os.replace(tmp_path, self._persistence_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_DEFAULT_BUS: Optional[EventBus] = None


def get_default_bus() -> EventBus:
    """Return the module-level EventBus singleton (created on first call).

    The singleton has no persistence path by default.  For persistence,
    create an :class:`EventBus` instance directly and share it explicitly.
    """
    global _DEFAULT_BUS  # noqa: PLW0603
    if _DEFAULT_BUS is None:
        _DEFAULT_BUS = EventBus()
    return _DEFAULT_BUS


def publish(name: str, source: str, payload: dict) -> Event:
    """Convenience wrapper: publish via the default bus singleton."""
    return get_default_bus().publish(name, source, payload)


def subscribe(
    name_pattern: str,
    handler: Callable[[Event], None],
    layer: str,
) -> Subscription:
    """Convenience wrapper: subscribe via the default bus singleton."""
    return get_default_bus().subscribe(name_pattern, handler, layer)
