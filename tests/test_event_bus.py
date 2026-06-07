"""tests/test_event_bus.py — Phase A event bus regression set."""
from __future__ import annotations

import asyncio
import pytest

from src.live.event_bus import (
    EventBus,
    TOPIC_PBP_FOUL,
    TOPIC_PBP_MADE_SHOT,
    get_bus,
    reset_bus_for_tests,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_bus_for_tests()
    yield
    reset_bus_for_tests()


def test_singleton_identity():
    a = get_bus()
    b = get_bus()
    assert a is b


def test_subscribe_publish_async_callback():
    bus = EventBus()
    seen = []

    async def sub(topic, ev):
        seen.append((topic, ev["x"]))

    bus.subscribe(TOPIC_PBP_FOUL, sub)

    async def run():
        await bus.publish(TOPIC_PBP_FOUL, {"x": 1})
        await asyncio.sleep(0)   # let dispatched task complete

    asyncio.run(run())
    assert seen == [(TOPIC_PBP_FOUL, 1)]


def test_subscribe_rejects_sync_callback():
    bus = EventBus()
    with pytest.raises(TypeError):
        bus.subscribe(TOPIC_PBP_FOUL, lambda t, e: None)  # sync — must reject


def test_wildcard_subscribe_matches_multiple():
    bus = EventBus()
    seen = []

    async def sub(topic, ev):
        seen.append(topic)

    bus.subscribe("pbp.*", sub)

    async def run():
        await bus.publish(TOPIC_PBP_FOUL, {})
        await bus.publish(TOPIC_PBP_MADE_SHOT, {})
        await bus.publish("snapshot.updated", {})  # should NOT match pbp.*
        await asyncio.sleep(0)

    asyncio.run(run())
    assert TOPIC_PBP_FOUL in seen
    assert TOPIC_PBP_MADE_SHOT in seen
    assert "snapshot.updated" not in seen


def test_unsubscribe_removes_callback():
    bus = EventBus()
    seen = []

    async def sub(topic, ev):
        seen.append(1)

    bus.subscribe(TOPIC_PBP_FOUL, sub)
    assert bus.unsubscribe(TOPIC_PBP_FOUL, sub) is True
    assert bus.unsubscribe(TOPIC_PBP_FOUL, sub) is False  # already gone

    async def run():
        await bus.publish(TOPIC_PBP_FOUL, {})
        await asyncio.sleep(0)

    asyncio.run(run())
    assert seen == []


def test_subscriber_exception_does_not_break_others():
    bus = EventBus()
    seen = []

    async def bad(topic, ev):
        raise RuntimeError("boom")

    async def good(topic, ev):
        seen.append(ev)

    bus.subscribe(TOPIC_PBP_FOUL, bad)
    bus.subscribe(TOPIC_PBP_FOUL, good)

    async def run():
        await bus.publish(TOPIC_PBP_FOUL, {"ok": True})
        await asyncio.sleep(0)

    asyncio.run(run())
    assert seen == [{"ok": True}]


def test_stats_counts_publishes_per_topic():
    bus = EventBus()

    async def noop(t, e):
        pass

    bus.subscribe(TOPIC_PBP_FOUL, noop)

    async def run():
        await bus.publish(TOPIC_PBP_FOUL, {})
        await bus.publish(TOPIC_PBP_FOUL, {})
        await bus.publish(TOPIC_PBP_MADE_SHOT, {})
        await asyncio.sleep(0)

    asyncio.run(run())
    s = bus.stats()
    assert s["published_total"] == 3
    assert s["per_topic_counts"][TOPIC_PBP_FOUL] == 2
    assert s["per_topic_counts"][TOPIC_PBP_MADE_SHOT] == 1
    assert s["subscriber_count"] == 1
