"""_courtvision_live.py — SSE stream of live bet.recommended events.

Subscribes to the in-process EventBus and yields each event as a
Server-Sent-Event to the connected browser. Adds a heartbeat every 25s
so proxies + browsers don't close the connection. Sends a `:hello` line
on connect with the most recent ring-buffer payload.

Public API:
    await live_edge_stream(request) -> StreamingResponse
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import time
import urllib.request
from typing import Optional

from fastapi import Request
from fastapi.responses import StreamingResponse

log = logging.getLogger(__name__)

_TOPICS = ("bet.recommended", "snapshot.updated", "pregame.info", "arb.detected")
_RING_SIZE = 25
_HEARTBEAT_SEC = 10.0
_DEFAULT_MAX_SECONDS = 60.0  # browser EventSource auto-reconnects
_ring: collections.deque = collections.deque(maxlen=_RING_SIZE)
_ring_seq = 0
_bus_subscribed = False


def _format_sse(event: dict, ev_id: Optional[int] = None,
                event_type: str = "edge") -> bytes:
    parts = []
    if ev_id is not None:
        parts.append(f"id: {ev_id}")
    parts.append(f"event: {event_type}")
    parts.append(f"data: {json.dumps(event, separators=(',', ':'))}")
    parts.append("")
    parts.append("")
    return ("\n".join(parts)).encode("utf-8")


_WEBHOOK_COOLDOWN_SEC = 300
_WEBHOOK_THRESHOLD = 0.10  # 10pp
_last_webhook_at: dict = {}  # bet identity -> ts


def _maybe_fire_webhook(event: dict) -> None:
    """Fire LIVE_ALERT_WEBHOOK_URL on +10pp edges, deduped 5min per bet."""
    url = os.environ.get("LIVE_ALERT_WEBHOOK_URL")
    if not url:
        return
    ev = event.get("ev")
    if not isinstance(ev, (int, float)) or ev < _WEBHOOK_THRESHOLD:
        return
    key = (event.get("player_id"), event.get("stat"),
           event.get("side"), event.get("line"), event.get("book"))
    now = time.time()
    if now - _last_webhook_at.get(key, 0) < _WEBHOOK_COOLDOWN_SEC:
        return
    _last_webhook_at[key] = now
    payload = {
        "text": (f"🚨 +EV alert: {event.get('name','?')} "
                 f"{(event.get('stat') or '').upper()} "
                 f"{event.get('side','').upper()} {event.get('line','?')} "
                 f"@ {event.get('book','?')} {event.get('odds','?')} — "
                 f"EV {ev*100:+.1f}%, model {(event.get('p_hit',0)*100):.1f}%"),
        "event": event,
    }
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "User-Agent": "courtvision-alerts/1.0"})
        urllib.request.urlopen(req, timeout=3.0).close()
    except Exception as exc:
        log.warning("webhook alert failed: %s", exc)


async def _bus_handler(topic: str, event: dict) -> None:
    global _ring_seq
    _ring_seq += 1
    _ring.append({"seq": _ring_seq, "topic": topic,
                  "event": event, "ts": time.time()})
    if topic == "bet.recommended":
        # Fire webhook on a fresh async task to avoid contending for the request
        # thread pool. The webhook helper is sync but uses urllib's own timeout.
        try:
            asyncio.create_task(asyncio.to_thread(_maybe_fire_webhook, event))
        except Exception as exc:
            log.debug("webhook task spawn failed: %s", exc)


def _ensure_bus_subscription() -> None:
    """Subscribe once per process to the relevant bus topics.

    The bus is an in-process async pubsub — no external connections or DB load.
    Gate removed: subscription is always attempted so /sse/live_edges emits real
    events without requiring COURTVISION_SSE_BUS=1 on the Railway service.
    The original env-var gate can be restored by setting COURTVISION_SSE_BUS=0
    explicitly if the subscription ever needs to be disabled.
    """
    import os as _os
    global _bus_subscribed
    if _bus_subscribed:
        return
    # Allow explicit opt-out via COURTVISION_SSE_BUS=0 (default is now enabled).
    if _os.environ.get("COURTVISION_SSE_BUS", "1") == "0":
        return
    try:
        from src.live.event_bus import get_bus
        bus = get_bus()
        for t in _TOPICS:
            bus.subscribe(t, _bus_handler)
        _bus_subscribed = True
        log.info("courtvision SSE: subscribed to %s", ", ".join(_TOPICS))
    except Exception as exc:
        log.warning("courtvision SSE: event bus unavailable (%s)", exc)


async def _generator(request: Request, max_seconds: float = _DEFAULT_MAX_SECONDS):
    """Stream SSE events for at most `max_seconds`. Browser EventSource auto-reconnects."""
    last_seen = _ring[-1]["seq"] if _ring else 0
    for entry in list(_ring):
        yield _format_sse(entry, ev_id=entry["seq"])
    start = time.time()
    last_hb = start
    while time.time() - start < max_seconds:
        try:
            if await request.is_disconnected():
                return
        except Exception:
            return
        delivered = 0
        for entry in list(_ring):
            if entry["seq"] > last_seen:
                last_seen = entry["seq"]
                yield _format_sse(entry, ev_id=entry["seq"])
                delivered += 1
        if delivered == 0 and time.time() - last_hb >= _HEARTBEAT_SEC:
            last_hb = time.time()
            yield b":heartbeat\n\n"
        await asyncio.sleep(1.0)


async def live_edge_stream(request: Request) -> StreamingResponse:
    _ensure_bus_subscription()
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(_generator(request),
                             media_type="text/event-stream",
                             headers=headers)
