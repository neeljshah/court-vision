"""test_L46_event_bus.py — Tests for the L46 EventBus (execute_loop layer 46).

Run with:
    conda run -n basketball_ai python -m pytest scripts/execute_loop/tests/test_L46_event_bus.py -v
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import target module
# ---------------------------------------------------------------------------

import importlib
import scripts.execute_loop.L46_event_bus as _mod

from scripts.execute_loop.L46_event_bus import (
    Event,
    EventBus,
    Subscription,
    get_default_bus,
    publish as bus_publish,
    subscribe as bus_subscribe,
)


# ---------------------------------------------------------------------------
# Isolation helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level singleton before and after every test."""
    _mod._DEFAULT_BUS = None
    yield
    _mod._DEFAULT_BUS = None


@pytest.fixture()
def fresh_bus() -> EventBus:
    """Return a brand-new EventBus instance (no persistence, no subscribers)."""
    return EventBus()


@pytest.fixture()
def persisted_bus(tmp_path: Path) -> EventBus:
    """Return an EventBus backed by a temp JSONL file."""
    return EventBus(persistence_path=tmp_path / "events.jsonl")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPublish:
    def test_publish_creates_event_with_id_and_ts(self, fresh_bus: EventBus):
        """publish() returns an Event with a non-empty event_id and valid ISO ts."""
        evt = fresh_bus.publish("bet.settled", "L7", {"amount": 100})

        assert isinstance(evt, Event)
        # event_id must be a non-empty UUID-shaped string
        assert evt.event_id and len(evt.event_id) == 36
        assert "-" in evt.event_id
        # ts must be parseable ISO UTC
        parsed = datetime.fromisoformat(evt.ts.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        # name, source, payload preserved
        assert evt.name == "bet.settled"
        assert evt.source == "L7"
        assert evt.payload == {"amount": 100}


class TestSubscribe:
    def test_subscribe_handler_receives_published_event(self, fresh_bus: EventBus):
        """A subscribed handler is called with the published event."""
        received: list[Event] = []

        fresh_bus.subscribe("bet.settled", received.append, layer="L22")
        evt = fresh_bus.publish("bet.settled", "L7", {"stake": 50})

        assert len(received) == 1
        assert received[0] is evt

    def test_glob_pattern_matching_prefix_wildcard(self, fresh_bus: EventBus):
        """'bet.*' matches 'bet.settled' and 'bet.placed' but not 'fill.received'."""
        hits: list[str] = []

        fresh_bus.subscribe("bet.*", lambda e: hits.append(e.name), layer="L22")

        fresh_bus.publish("bet.settled", "L7", {})
        fresh_bus.publish("bet.placed", "L16", {})
        fresh_bus.publish("fill.received", "L14", {})

        assert hits == ["bet.settled", "bet.placed"]

    def test_glob_pattern_matching_suffix_wildcard(self, fresh_bus: EventBus):
        """'*.opened' matches 'incident.opened' but not 'incident.closed'."""
        hits: list[str] = []

        fresh_bus.subscribe("*.opened", lambda e: hits.append(e.name), layer="L22")

        fresh_bus.publish("incident.opened", "L38", {})
        fresh_bus.publish("incident.closed", "L38", {})

        assert hits == ["incident.opened"]

    def test_glob_star_matches_all(self, fresh_bus: EventBus):
        """Pattern '*' receives every event."""
        hits: list[str] = []

        fresh_bus.subscribe("*", lambda e: hits.append(e.name), layer="L23")

        fresh_bus.publish("bet.settled", "L7", {})
        fresh_bus.publish("fill.received", "L14", {})
        fresh_bus.publish("incident.opened", "L38", {})

        assert len(hits) == 3


class TestErrorHandling:
    def test_handler_error_does_not_break_publish(self, fresh_bus: EventBus):
        """If one handler raises, the bus catches it and subsequent subs still fire."""
        second_received: list[Event] = []

        def bad_handler(evt: Event) -> None:
            raise RuntimeError("intentional test error")

        fresh_bus.subscribe("bet.*", bad_handler, layer="L_bad")
        fresh_bus.subscribe("bet.*", second_received.append, layer="L_good")

        # Should not raise despite bad_handler blowing up
        evt = fresh_bus.publish("bet.settled", "L7", {})

        assert len(second_received) == 1
        assert second_received[0] is evt
        # Error should be counted in stats
        assert fresh_bus.stats()["errors"] == 1


class TestUnsubscribe:
    def test_unsubscribe_removes_handler(self, fresh_bus: EventBus):
        """After unsubscribe, the handler is no longer called."""
        hits: list[Event] = []

        sub = fresh_bus.subscribe("bet.*", hits.append, layer="L22")
        fresh_bus.publish("bet.placed", "L16", {})   # should arrive
        result = fresh_bus.unsubscribe(sub)
        fresh_bus.publish("bet.settled", "L7", {})   # should NOT arrive

        assert result is True
        assert len(hits) == 1

    def test_unsubscribe_returns_false_when_not_found(self, fresh_bus: EventBus):
        """unsubscribe on an already-removed sub returns False."""
        sub = fresh_bus.subscribe("*", lambda e: None, layer="L22")
        fresh_bus.unsubscribe(sub)
        assert fresh_bus.unsubscribe(sub) is False


class TestPersistenceAndReplay:
    def test_replay_yields_persisted_events(self, persisted_bus: EventBus):
        """After publishing 3 events, replay() returns all 3 in order."""
        persisted_bus.publish("bet.placed", "L16", {"stake": 10})
        persisted_bus.publish("fill.received", "L14", {"fill_id": "abc"})
        persisted_bus.publish("bet.settled", "L7", {"pnl": 5.0})

        replayed = persisted_bus.replay()

        assert len(replayed) == 3
        assert replayed[0].name == "bet.placed"
        assert replayed[1].name == "fill.received"
        assert replayed[2].name == "bet.settled"
        # Each is a proper Event with an event_id
        for evt in replayed:
            assert isinstance(evt, Event)
            assert evt.event_id

    def test_replay_filtered_by_since(self, persisted_bus: EventBus):
        """replay(since=middle_ts) returns only events strictly after that timestamp."""
        import time
        # Publish first event
        e1 = persisted_bus.publish("bet.placed", "L16", {})

        # Sleep to guarantee ts ordering on fast Windows clocks
        # (datetime.now() resolution can be 15.6ms on Windows; sub-ms publishes
        # can share an ISO string otherwise).
        time.sleep(0.02)
        middle_ts = datetime.now(timezone.utc).isoformat()
        time.sleep(0.02)

        e2 = persisted_bus.publish("fill.received", "L14", {})
        e3 = persisted_bus.publish("bet.settled", "L7", {})

        # Replay from just before e2 and e3 were published
        replayed = persisted_bus.replay(since=middle_ts)

        # e1 was before middle_ts; e2/e3 are at or after
        names = [e.name for e in replayed]
        assert "bet.placed" not in names
        assert "fill.received" in names
        assert "bet.settled" in names

    def test_replay_returns_empty_without_persistence_path(self, fresh_bus: EventBus):
        """replay() on a bus with no persistence_path returns []."""
        fresh_bus.publish("bet.placed", "L16", {})
        assert fresh_bus.replay() == []

    def test_replay_returns_empty_when_file_not_yet_created(self, tmp_path: Path):
        """replay() on a configured bus with no writes yet returns []."""
        bus = EventBus(persistence_path=tmp_path / "never_written.jsonl")
        assert bus.replay() == []


class TestStats:
    def test_stats_counts(self, fresh_bus: EventBus):
        """With 5 published events and 2 subscribers each → dispatched=10, published=5."""
        log: list = []

        fresh_bus.subscribe("*", log.append, layer="L22")
        fresh_bus.subscribe("*", log.append, layer="L23")

        for i in range(5):
            fresh_bus.publish("bet.placed", "L16", {"i": i})

        s = fresh_bus.stats()
        assert s["events_published"] == 5
        assert s["events_dispatched"] == 10
        assert s["subscribers"] == 2
        assert s["errors"] == 0
        assert s["by_event_name"]["bet.placed"] == 5

    def test_stats_by_event_name_multiple_types(self, fresh_bus: EventBus):
        """by_event_name tracks each distinct event name independently."""
        fresh_bus.publish("bet.settled", "L7", {})
        fresh_bus.publish("bet.settled", "L7", {})
        fresh_bus.publish("fill.received", "L14", {})

        s = fresh_bus.stats()
        assert s["by_event_name"]["bet.settled"] == 2
        assert s["by_event_name"]["fill.received"] == 1


class TestSingleton:
    def test_default_bus_singleton(self):
        """Two calls to get_default_bus() return the same object."""
        bus_a = get_default_bus()
        bus_b = get_default_bus()
        assert bus_a is bus_b

    def test_module_level_publish_uses_singleton(self):
        """Module-level publish() routes through the default bus."""
        hits: list[Event] = []
        get_default_bus().subscribe("test.event", hits.append, layer="L99")
        bus_publish("test.event", "L_test", {"x": 1})
        assert len(hits) == 1

    def test_module_level_subscribe_uses_singleton(self):
        """Module-level subscribe() registers on the default bus."""
        hits: list[Event] = []
        bus_subscribe("test.event", hits.append, layer="L99")
        get_default_bus().publish("test.event", "L_test", {})
        assert len(hits) == 1


class TestClearSubscribers:
    def test_clear_subscribers_for_test_isolation(self, fresh_bus: EventBus):
        """clear_subscribers() removes all handlers; subsequent publishes dispatch to none."""
        hits: list[Event] = []
        fresh_bus.subscribe("*", hits.append, layer="L22")
        fresh_bus.subscribe("bet.*", hits.append, layer="L7")

        assert fresh_bus.stats()["subscribers"] == 2

        fresh_bus.clear_subscribers()

        assert fresh_bus.stats()["subscribers"] == 0

        # Publish after clear — nothing should be received
        fresh_bus.publish("bet.settled", "L7", {})
        assert len(hits) == 0
