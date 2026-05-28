"""Tests for the arb.detected SSE topic + arb_emitter_daemon dedupe logic."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# --------------------------------------------------------------------------- #
# Topic registration.                                                         #
# --------------------------------------------------------------------------- #
def test_arb_topic_in_topics():
    """arb.detected must be in api._courtvision_live._TOPICS so SSE subscribers receive it."""
    from api._courtvision_live import _TOPICS
    assert "arb.detected" in _TOPICS, (
        f"arb.detected missing from _TOPICS: {_TOPICS!r}"
    )


# --------------------------------------------------------------------------- #
# Dedupe key.                                                                 #
# --------------------------------------------------------------------------- #
def _fake_arb(line: float = 9.5, player: str = "Luka Doncic",
              stat: str = "pts", over_book: str = "fanduel",
              under_book: str = "draftkings") -> Dict[str, Any]:
    return {
        "player": player,
        "stat": stat,
        "line": line,
        "best_over_book": over_book,
        "best_under_book": under_book,
        "best_over_price": -110,
        "best_under_price": +105,
        "is_arb": True,
        "arb_quality": "tight",
        "arb_sum_pct": 97.5,
        "books": [
            {"book": over_book, "over_price": -110, "under_price": -130},
            {"book": under_book, "over_price": -135, "under_price": +105},
        ],
    }


def test_dedup_key_stable():
    from scripts.arb_emitter_daemon import make_dedup_key
    arb = _fake_arb()
    k1 = make_dedup_key(arb)
    k2 = make_dedup_key(dict(arb))  # same data, fresh dict
    assert k1 == k2, f"dedup key not stable: {k1!r} vs {k2!r}"


def test_dedup_key_distinguishes():
    """Changing the line should produce a different dedup key."""
    from scripts.arb_emitter_daemon import make_dedup_key
    a = _fake_arb(line=9.5)
    b = _fake_arb(line=10.5)
    assert make_dedup_key(a) != make_dedup_key(b)


# --------------------------------------------------------------------------- #
# Daemon import.                                                              #
# --------------------------------------------------------------------------- #
def test_emitter_imports():
    """Module must import cleanly so the watchdog can restart it."""
    mod = importlib.import_module("scripts.arb_emitter_daemon")
    assert hasattr(mod, "_tick")
    assert hasattr(mod, "run_main")
    assert hasattr(mod, "make_dedup_key")
    assert hasattr(mod, "build_payload")


# --------------------------------------------------------------------------- #
# Smoke test — _tick + dedupe.                                                #
# --------------------------------------------------------------------------- #
class _StubBus:
    """Async-bus stub that records every published event."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    async def publish(self, topic: str, event: Dict[str, Any]) -> None:
        self.events.append({"topic": topic, "event": event})


def test_emitter_smoke():
    """_tick should publish 2 events on first call, 0 on the second (dedup)."""
    from scripts.arb_emitter_daemon import _tick

    bus = _StubBus()
    dedup: Dict[str, float] = {}

    arbs = [
        _fake_arb(line=9.5, player="Luka Doncic", stat="pts"),
        _fake_arb(line=4.5, player="Nikola Jokic", stat="ast",
                  over_book="betmgm", under_book="pinnacle"),
    ]

    def fetcher(date, min_spread_pp, max_age_sec):
        # Return fresh copies each call so the daemon can mutate without affecting us.
        return [dict(a) for a in arbs]

    # First tick — both arbs are new, both should publish.
    new1, total1 = _tick(dedup, bus, fetcher=fetcher, in_process=True)
    assert total1 == 2, f"expected 2 total arbs seen, got {total1}"
    assert len(new1) == 2, f"expected 2 new payloads, got {len(new1)}"
    assert len(bus.events) == 2, f"expected 2 bus events, got {len(bus.events)}"
    for evt in bus.events:
        assert evt["topic"] == "arb.detected"
        assert evt["event"]["topic"] == "arb.detected"
        assert evt["event"].get("detected_at")

    # Second tick — both arbs are duplicates, nothing should publish.
    bus.events.clear()
    new2, total2 = _tick(dedup, bus, fetcher=fetcher, in_process=True)
    assert total2 == 2, f"still see both arbs but expected 0 new; got total={total2}"
    assert len(new2) == 0, f"expected 0 new payloads on rerun, got {len(new2)}"
    assert len(bus.events) == 0, f"expected 0 bus events on rerun, got {len(bus.events)}"


def test_emitter_skips_stale_quality():
    """Arbs with arb_quality='stale' must NOT be published."""
    from scripts.arb_emitter_daemon import _tick

    bus = _StubBus()
    dedup: Dict[str, float] = {}

    stale = _fake_arb()
    stale["arb_quality"] = "stale"

    def fetcher(date, min_spread_pp, max_age_sec):
        return [stale]

    new, total = _tick(dedup, bus, fetcher=fetcher, in_process=True)
    assert total == 0, f"stale arb should be filtered, got total={total}"
    assert len(new) == 0
    assert len(bus.events) == 0


def test_dedup_ttl_prune():
    """Entries older than DEDUP_TTL_SEC should be evicted by prune_dedup."""
    from scripts.arb_emitter_daemon import prune_dedup, DEDUP_TTL_SEC

    now = 10_000.0
    dedup = {
        "fresh": now - 10,
        "old":   now - DEDUP_TTL_SEC - 1,
    }
    prune_dedup(dedup, DEDUP_TTL_SEC, now)
    assert "fresh" in dedup
    assert "old" not in dedup
