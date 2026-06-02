"""betrivers_ws.py — KAMBI/BetRivers CometD/Bayeux WebSocket subscriber.

Connects to wss://eu.offering-api.kambicdn.com/push/cometd (KAMBI's standard
CometD endpoint), performs the CometD/Bayeux handshake, subscribes to
/offering/v2018/rsiusia/betoffer/event/{id} for every live NBA event, and
writes canonical rows to data/lines/<date>_betrivers.csv on each push message.
Also publishes TOPIC_LINES_REFRESHED on the event bus.

Push host notes
---------------
The BetRivers HTML config sets pushApiUrl = "wss://push-us.offering-api.kambicdn.com"
(no path suffix).  The path is appended by the KAMBI sportsbook JS bundle after
fetching runtime config from settings-api.kambicdn.com.  Two confirmed endpoints:

  wss://eu.offering-api.kambicdn.com/push/cometd   — CloudFront 429 from non-browser
                                                      IPs during off-hours; during game
                                                      windows the rate limit relaxes.
  wss://push-us.offering-api.kambicdn.com/push     — CloudFront 404 (path not yet
                                                      reverse-engineered).

Override via BR_WS_URL env var once the correct path is confirmed from browser
DevTools during a live game.  The WS subscriber degrades gracefully to no-op
on connection failure (HTTP scraper in betrivers_scraper.py remains the fallback).

Reconnects on drop with exponential backoff (2/4/8/16/32→60s cap).
Refreshes event subscription list every 5 minutes.

Gate with env var:  BR_WS_ENABLED=1
Wire-in:            asyncio.create_task(start_br_ws(), name="br_ws_subscriber")
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, date as _date, timezone
from typing import Any, Dict, List, Optional, Set

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import websockets  # noqa: E402 — websockets>=12.0 pinned

# Reuse all parsing + CSV logic from the HTTP scraper — zero duplication.
from scripts.betrivers_scraper import (  # noqa: E402
    LINES_DIR,
    fetch_event_ids,
    parse_offers,
    write_csv,
)

try:
    from src.live.event_bus import TOPIC_LINES_REFRESHED, get_bus
    _BUS_AVAILABLE = True
except Exception:  # noqa: BLE001
    _BUS_AVAILABLE = False

try:
    from src.monitor.daemon_heartbeat import write_heartbeat as _hb
except Exception:  # noqa: BLE001
    def _hb(_name: str) -> bool:  # type: ignore[misc]
        return False

log = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────
# Override with BR_WS_URL env var once the exact path is confirmed from browser
# DevTools during a live game session.  The eu host/push/cometd path is the
# standard KAMBI CometD endpoint and is confirmed to exist (returns 429 from
# CloudFront on non-browser IPs during off-hours; relaxes during game windows).
_WS_URL        = os.environ.get("BR_WS_URL",
                                "wss://eu.offering-api.kambicdn.com/push/cometd")
_OP_KEY        = "rsiusia"
_CHANNEL_BASE  = f"/offering/v2018/{_OP_KEY}/betoffer/event"
_HEARTBEAT_KEY = "br_ws"
_HB_INTERVAL   = 30          # seconds between heartbeat writes
_REFRESH_INTERVAL = 300      # seconds between event-list refreshes
_BACKOFF_CAP   = 60          # maximum reconnect delay (seconds)
_CONNECT_TIMEOUT = 20        # WS connect + handshake timeout (seconds)
_MSG_TIMEOUT   = 90          # inactivity timeout before treating as dead (seconds)

# CometD message IDs (incrementing per-session; simple counter is fine).
_msg_id = 0


def _next_id() -> str:
    global _msg_id
    _msg_id += 1
    return str(_msg_id)


def _encode(payload: Any) -> str:
    """KAMBI expects the top-level frame to be a JSON *list*."""
    msg = payload if isinstance(payload, list) else [payload]
    return json.dumps(msg)


def _decode(raw: str) -> List[Dict[str, Any]]:
    """Parse a CometD frame; always returns a list of message dicts."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return [obj]
    return []


# ── CometD helpers ───────────────────────────────────────────────────────────

async def _handshake(ws) -> Optional[str]:
    """Perform CometD /meta/handshake.  Returns clientId or None on failure."""
    msg = {
        "channel": "/meta/handshake",
        "version": "1.0",
        "supportedConnectionTypes": ["websocket"],
        "minimumVersion": "1.0",
        "id": _next_id(),
        "advice": {"timeout": 60000, "interval": 0},
    }
    await ws.send(_encode(msg))
    raw = await asyncio.wait_for(ws.recv(), timeout=_CONNECT_TIMEOUT)
    frames = _decode(raw)
    for frame in frames:
        if frame.get("channel") == "/meta/handshake":
            if frame.get("successful"):
                cid = frame.get("clientId")
                log.info("[br-ws] handshake OK clientId=%s...", str(cid)[:12])
                return cid
            err = frame.get("error", "unknown error")
            log.error("[br-ws] handshake FAILED: %s", err)
            return None
    log.error("[br-ws] handshake: no /meta/handshake in response: %s", raw[:200])
    return None


async def _connect(ws, client_id: str) -> bool:
    """Send /meta/connect.  Returns True if the server ACKs."""
    msg = {
        "channel": "/meta/connect",
        "clientId": client_id,
        "connectionType": "websocket",
        "id": _next_id(),
    }
    await ws.send(_encode(msg))
    # The connect response may arrive together with subscription confirmations;
    # we don't block hard here — return True optimistically after send.
    return True


async def _subscribe(ws, client_id: str, event_ids: List[int]) -> List[str]:
    """Subscribe to betoffer channels for all given event IDs.

    Returns the list of subscribed channel names.
    """
    channels: List[str] = []
    for eid in event_ids:
        channel = f"{_CHANNEL_BASE}/{eid}"
        msg = {
            "channel": "/meta/subscribe",
            "clientId": client_id,
            "subscription": channel,
            "id": _next_id(),
        }
        await ws.send(_encode(msg))
        channels.append(channel)
        log.debug("[br-ws] subscribed channel=%s", channel)
    return channels


# ── Push message handling ────────────────────────────────────────────────────

def _process_push_frame(frame: Dict[str, Any], captured_at: str) -> int:
    """Parse one CometD push frame; write rows to CSV; return row count."""
    channel = frame.get("channel", "")
    if not channel.startswith(_CHANNEL_BASE + "/"):
        return 0
    # Extract event_id from channel tail.
    try:
        event_id = channel.rsplit("/", 1)[-1]
    except Exception:  # noqa: BLE001
        return 0

    data = frame.get("data") or {}
    # KAMBI push wraps the betoffer snapshot in data.betOffers or data directly.
    if "betOffers" not in data:
        return 0

    seen_labels: set = set()
    rows = parse_offers(data, event_id, start_time="", captured_at=captured_at,
                        seen_labels=seen_labels)
    if not rows:
        return 0

    today = _date.today().isoformat()
    # Write to a _ws-suffixed file to avoid dual-writer race with the HTTP
    # scraper (betrivers_scraper.py --daemon -> <date>_betrivers.csv).  The
    # row's `book` column stays "betrivers" (canonical); no "_ws" key leaks.
    csv_path = os.path.join(LINES_DIR, f"{today}_betrivers_ws.csv")
    write_csv(rows, csv_path)

    if _BUS_AVAILABLE:
        bus = get_bus()
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(
                bus.publish(TOPIC_LINES_REFRESHED, {
                    "source": "betrivers_ws",
                    "book": "betrivers",
                    "event_id": event_id,
                    "rows": len(rows),
                    "captured_at": captured_at,
                })
            )
        except RuntimeError:
            pass  # no event loop yet (rare edge case at startup)

    log.info("[br-ws] push event_id=%s rows=%d", event_id, len(rows))
    return len(rows)


# ── Main loop ────────────────────────────────────────────────────────────────

async def _fetch_event_ids_async() -> List[int]:
    """Run the blocking HTTP event-list fetch in a thread pool.

    fetch_event_ids() returns a 2-tuple (List[Dict], operator_str).
    We unpack it so the list comprehension iterates the dicts, not the tuple.
    """
    loop = asyncio.get_event_loop()
    stubs, _op = await loop.run_in_executor(None, fetch_event_ids)
    return [int(s["id"]) for s in stubs if s.get("id")]


async def _run_session() -> None:
    """One connected WS session: handshake → connect → subscribe → recv loop."""
    event_ids = await _fetch_event_ids_async()
    log.info("[br-ws] fetched %d NBA event(s) to subscribe", len(event_ids))

    async with websockets.connect(
        _WS_URL,
        additional_headers={
            "Origin": "https://www.betrivers.com",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
        open_timeout=_CONNECT_TIMEOUT,
        ping_interval=25,
        ping_timeout=15,
    ) as ws:
        # 1. Handshake
        client_id = await _handshake(ws)
        if client_id is None:
            raise RuntimeError("CometD handshake failed — will reconnect")

        # 2. Connect
        await _connect(ws, client_id)

        # 3. Subscribe to all current events
        subscribed: Set[int] = set()
        if event_ids:
            await _subscribe(ws, client_id, event_ids)
            subscribed.update(event_ids)
        else:
            log.warning("[br-ws] no NBA events right now — will recheck in %ds",
                        _REFRESH_INTERVAL)

        last_refresh   = asyncio.get_event_loop().time()
        last_heartbeat = asyncio.get_event_loop().time()
        total_rows     = 0

        # 4. Receive loop
        while True:
            now = asyncio.get_event_loop().time()

            # Heartbeat
            if now - last_heartbeat >= _HB_INTERVAL:
                _hb(_HEARTBEAT_KEY)
                last_heartbeat = now

            # Periodic event-list refresh (subscribe to any new events)
            if now - last_refresh >= _REFRESH_INTERVAL:
                fresh_ids = await _fetch_event_ids_async()
                new_ids = [eid for eid in fresh_ids if eid not in subscribed]
                if new_ids:
                    await _subscribe(ws, client_id, new_ids)
                    subscribed.update(new_ids)
                    log.info("[br-ws] refreshed event list — subscribed %d new event(s)",
                             len(new_ids))
                last_refresh = now

            # Receive with timeout so we can run heartbeat / refresh tasks.
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(_HB_INTERVAL, 20))
            except asyncio.TimeoutError:
                # No message yet — that's fine; loop again for HB/refresh checks.
                continue
            except websockets.exceptions.ConnectionClosed as exc:
                log.warning("[br-ws] connection closed: %s", exc)
                raise  # let the outer loop reconnect

            if not raw:
                continue

            captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            frames = _decode(raw)
            for frame in frames:
                ch = frame.get("channel", "")

                # Log subscription confirmations
                if ch == "/meta/subscribe":
                    ok  = frame.get("successful")
                    sub = frame.get("subscription", "")
                    if ok:
                        log.debug("[br-ws] subscribe confirmed: %s", sub)
                    else:
                        log.warning("[br-ws] subscribe failed: %s err=%s",
                                    sub, frame.get("error"))

                # Log connect acknowledgements
                elif ch == "/meta/connect":
                    if not frame.get("successful"):
                        log.warning("[br-ws] /meta/connect not successful: %s", frame)

                # Data push
                elif ch.startswith(_CHANNEL_BASE + "/"):
                    n = _process_push_frame(frame, captured_at)
                    total_rows += n

                # Unknown (advisory, disconnect, etc.) — just log at DEBUG
                else:
                    log.debug("[br-ws] unhandled channel=%s", ch)


async def start_br_ws() -> None:
    """Entry point for asyncio.create_task().

    Never returns — reconnects with exponential backoff on any error.
    """
    backoff = 2
    attempt = 0
    log.info("[br-ws] subscriber starting url=%s", _WS_URL)

    while True:
        attempt += 1
        try:
            await _run_session()
        except (websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException,
                OSError, RuntimeError, asyncio.TimeoutError) as exc:
            log.warning("[br-ws] session ended (attempt %d): %s — retry in %ds",
                        attempt, exc, backoff)
        except Exception as exc:  # noqa: BLE001
            log.exception("[br-ws] unexpected error (attempt %d): %s", attempt, exc)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, _BACKOFF_CAP)


# ── Standalone entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="BetRivers KAMBI WebSocket subscriber")
    ap.add_argument("--debug", action="store_true", help="verbose logging")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        asyncio.run(start_br_ws())
    except KeyboardInterrupt:
        print("\n[br-ws] stopped by user")
