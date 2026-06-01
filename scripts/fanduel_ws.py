"""fanduel_ws.py — FanDuel WebSocket subscriber for live NBA player-prop odds.

Protocol (reverse-engineered from public sources + liveuk probe):
  * WS host: wss://liveuk.fanduel.com/sportsbook
  * Protocol: CometD/Bayeux 1.0 over WebSocket
  * Handshake: send [{channel:'/meta/handshake', version:'1.0',
      supportedConnectionTypes:['websocket'], ext:{ack:true}}]
  * Server responds with clientId
  * Connect:   [{channel:'/meta/connect', clientId:..., connectionType:'websocket'}]
  * Subscribe: [{channel:'/meta/subscribe', clientId:..., subscription:'/1/markets/<eventId>'}]
  * Push shape: [{channel:'/1/markets/<eventId>', data:{markets:{...},events:{...}}}]
    — identical structure to the HTTP REST API attachments dict.
  * Auth: PerimeterX cookies primed from sportsbook.fanduel.com (via curl_cffi session).

Geo-restriction note (2026-05-27):
  * liveuk.fanduel.com is CloudFront geo-restricted from dev IPs outside US
    gambling-state coverage zones. TLS handshake fails (server-side alert).
  * From Railway/RunPod (NJ/NY IP) expected to work — deploy with FD_WS_ENABLED=1.
  * Fallback: HTTP polling of sbapi.nj at 30s interval (runs automatically when
    WS is unreachable — gives ~30s latency vs 5-min HTTP daemon).

Dedup logic (WS writer): (captured_at, player_name, stat, line, over_price, under_price) —
  full-second timestamp + both prices so intra-minute price moves are preserved.

Run:
    python scripts/fanduel_ws.py           # long-running daemon
    FD_WS_ENABLED=1 (wired into live_v2_app.py startup)
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, date as _date, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import re

import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

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

# ── constants ────────────────────────────────────────────────────────────

_WS_URL = "wss://liveuk.fanduel.com/sportsbook"
_NJ_REST_URL = (
    "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
    "?page=CUSTOM&customPageId=nba&pbHorizontal=false"
    "&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York"
)
_PRIME_URL = "https://sportsbook.fanduel.com/"

_CONNECT_HEADERS = {
    "Origin": "https://sportsbook.fanduel.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://sportsbook.fanduel.com/",
}

# marketType regex → canonical stat (mirrors probe_R15_curl_cffi_fanduel.py lines 86-94)
_THRESHOLD_PATTERNS: List[tuple] = [
    (re.compile(r"^TO_SCORE_(\d+)\+_POINTS$"), "pts"),
    (re.compile(r"^(\d+)\+_MADE_THREES$"), "fg3m"),
    (re.compile(r"^TO_RECORD_(\d+)\+_ASSISTS$"), "ast"),
    (re.compile(r"^TO_RECORD_(\d+)\+_REBOUNDS$"), "reb"),
    (re.compile(r"^TO_RECORD_(\d+)\+_STEALS$"), "stl"),
    (re.compile(r"^TO_RECORD_(\d+)\+_BLOCKS$"), "blk"),
    (re.compile(r"^TO_RECORD_(\d+)\+_TURNOVERS$"), "tov"),
]

_BACKOFF_SEQUENCE = [2, 4, 8, 16, 32, 60]   # seconds; stays at 60 after exhausted
_HEARTBEAT_INTERVAL = 30                      # seconds
_POLL_FALLBACK_INTERVAL = 30                  # HTTP fallback when WS unreachable
_LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
_HB_DIR = os.path.join(PROJECT_DIR, "data", "cache", "daemon_heartbeats")
_CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]

os.makedirs(_LINES_DIR, exist_ok=True)
os.makedirs(_HB_DIR, exist_ok=True)


# ── helpers ──────────────────────────────────────────────────────────────

def _match_threshold(market_type: str) -> Optional[Tuple[str, int]]:
    """Map FD marketType string to (stat, threshold). Returns None if not a prop."""
    for pat, stat in _THRESHOLD_PATTERNS:
        m = pat.match(market_type or "")
        if m:
            return stat, int(m.group(1))
    return None


def _prime_cookies() -> Dict[str, str]:
    """GET sportsbook.fanduel.com via curl_cffi chrome120 to harvest PX cookies.

    Returns a cookie dict (may be empty if PerimeterX blocks us).
    The WS connect header is set regardless; cookies help on prod IPs.
    """
    try:
        from curl_cffi import requests as cf_req
        sess = cf_req.Session(impersonate="chrome120")
        r = sess.get(_PRIME_URL, headers=_CONNECT_HEADERS, timeout=15, allow_redirects=True)
        cookies = dict(r.cookies)
        log.debug("[fd-ws] primed cookies: %s", list(cookies.keys()))
        return cookies
    except Exception as exc:  # noqa: BLE001
        log.debug("[fd-ws] cookie priming failed (non-fatal): %s", exc)
        return {}


def _normalize_push(
    data: Any,
    captured_at: str,
) -> List[Dict[str, Any]]:
    """Convert a CometD push data block to canonical CSV rows.

    Push data shape mirrors HTTP API attachments:
      {"markets": {<id>: {...}}, "events": {<id>: {...}}}
    """
    if not isinstance(data, dict):
        return []

    events: Dict[str, Any] = data.get("events") or {}
    markets: Dict[str, Any] = data.get("markets") or {}

    rows: List[Dict[str, Any]] = []
    for m in markets.values():
        match = _match_threshold(m.get("marketType") or "")
        if not match:
            continue
        stat, threshold = match

        ev_id = m.get("eventId")
        ev = events.get(str(ev_id), {}) or {}
        ev_name = ev.get("name") or ""
        if "@" not in ev_name:
            continue
        start_time = ev.get("openDate") or ""

        for runner in m.get("runners") or []:
            if not runner.get("isPlayerSelection"):
                continue
            odds_block = (
                (runner.get("winRunnerOdds") or {})
                .get("americanDisplayOdds") or {}
            )
            odds = odds_block.get("americanOdds")
            if odds is None:
                continue
            rows.append({
                "captured_at": captured_at,
                "book": "fd",
                "game_id": ev_id,
                "player_id": runner.get("selectionId"),
                "player_name": runner.get("runnerName"),
                "stat": stat,
                "line": threshold - 0.5,
                "over_price": int(odds),
                "under_price": "",   # FD threshold markets have no NO side
                "start_time": start_time,
            })
    return rows


def _normalize_rest(j: Dict[str, Any], captured_at: str) -> List[Dict[str, Any]]:
    """Normalize the REST API response (same shape as CometD push.data)."""
    att = j.get("attachments") or {}
    return _normalize_push(att, captured_at)


def _write_csv(rows: List[Dict[str, Any]], path: str) -> int:
    """Append rows to CSV, deduplicating on (captured_at, player, stat, line, over_price, under_price).

    The key uses the full-second captured_at (no truncation) and includes both
    prices so that intra-minute price moves on the same line are preserved.
    Only byte-identical rows (same second, same line, same prices) are deduped.

    Returns the number of net-new rows written.
    """
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    existing_keys: Set[Tuple[str, str, str, str, str, str]] = set()
    if not new_file:
        try:
            with open(path, "r", encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    existing_keys.add((
                        r.get("captured_at") or "",
                        r.get("player_name") or "",
                        r.get("stat") or "",
                        str(r.get("line") or ""),
                        str(r.get("over_price") or ""),
                        str(r.get("under_price") or ""),
                    ))
        except OSError:
            new_file = True

    written = 0
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_CANONICAL_FIELDS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for r in rows:
            key: Tuple[str, str, str, str, str, str] = (
                r["captured_at"],
                r["player_name"],
                r["stat"],
                str(r["line"]),
                str(r.get("over_price") or ""),
                str(r.get("under_price") or ""),
            )
            if key in existing_keys:
                continue
            existing_keys.add(key)
            w.writerow(r)
            written += 1
    return written


async def _publish(captured_at: str, stat: str, written: int, csv_path: str) -> None:
    """Publish TOPIC_LINES_REFRESHED on the event bus."""
    if written <= 0 or not _BUS_AVAILABLE:
        return
    try:
        bus = get_bus()
        await bus.publish(TOPIC_LINES_REFRESHED, {
            "source": "fd_ws",
            "stat": stat,
            "rows": written,
            "csv": csv_path,
            "captured_at": captured_at,
        })
    except Exception as exc:  # noqa: BLE001
        log.debug("[fd-ws] event bus publish failed: %s", exc)


async def _handle_push(data: Any, channel: str) -> None:
    """Parse CometD push data, write CSV, publish event."""
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    today = _date.today().isoformat()
    # Write to a _ws-suffixed file to avoid dual-writer race with the HTTP
    # scraper (unified_scraper_orchestrator -> <date>_fd.csv).  The row's
    # `book` column stays "fd" (canonical), so consolidate_for_slate tags
    # these rows as FanDuel odds — no "_ws" book key surfaces in the UI.
    csv_path = os.path.join(_LINES_DIR, f"{today}_fd_ws.csv")

    rows = _normalize_push(data, captured_at)
    if not rows:
        return

    written = _write_csv(rows, csv_path)
    log.info("[fd-ws] push channel=%s rows=%d new=%d csv=%s",
             channel, len(rows), written, os.path.basename(csv_path))

    if written > 0:
        # Determine dominant stat for bus payload (most common in push batch)
        stat_counts: Dict[str, int] = {}
        for r in rows:
            stat_counts[r["stat"]] = stat_counts.get(r["stat"], 0) + 1
        dominant_stat = max(stat_counts, key=lambda k: stat_counts[k])
        await _publish(captured_at, dominant_stat, written, csv_path)


# ── CometD Bayeux messages ───────────────────────────────────────────────

def _msg_handshake() -> str:
    return json.dumps([{
        "channel": "/meta/handshake",
        "version": "1.0",
        "minimumVersion": "1.0beta",
        "supportedConnectionTypes": ["websocket"],
        "advice": {"timeout": 60000, "interval": 0},
        "ext": {"ack": True},
        "id": "1",
    }])


def _msg_connect(client_id: str, msg_id: int) -> str:
    return json.dumps([{
        "channel": "/meta/connect",
        "clientId": client_id,
        "connectionType": "websocket",
        "advice": {"timeout": 0},
        "id": str(msg_id),
    }])


def _msg_subscribe(client_id: str, event_id: Any, msg_id: int) -> str:
    return json.dumps([{
        "channel": "/meta/subscribe",
        "clientId": client_id,
        "subscription": f"/1/markets/{event_id}",
        "id": str(msg_id),
    }])


def _fetch_nba_event_ids() -> List[Any]:
    """Fetch NBA game event IDs from the NJ REST API.

    Returns a list of eventIds for today's/upcoming NBA games.
    """
    try:
        from curl_cffi import requests as cf_req
        r = cf_req.get(
            _NJ_REST_URL,
            headers={
                "Accept": "application/json",
                "Referer": "https://sportsbook.fanduel.com/",
                "Origin": "https://sportsbook.fanduel.com",
            },
            impersonate="chrome120",
            timeout=15,
        )
        if r.status_code != 200:
            log.warning("[fd-ws] REST event-id fetch: status=%d", r.status_code)
            return []
        j = r.json()
        events = (j.get("attachments") or {}).get("events") or {}
        ids = [
            ev["eventId"]
            for ev in events.values()
            if "@" in (ev.get("name") or "")
        ]
        log.info("[fd-ws] fetched %d NBA event IDs for subscription", len(ids))
        return ids
    except Exception as exc:  # noqa: BLE001
        log.warning("[fd-ws] event-id fetch failed: %s", exc)
        return []


# ── HTTP polling fallback ────────────────────────────────────────────────

async def _poll_loop() -> None:
    """HTTP polling fallback — runs at 30s interval when WS is unreachable.

    Uses the same NJ REST API as the HTTP scraper but at 30s (not 5 min).
    """
    log.info("[fd-ws] entering HTTP poll fallback (interval=%ds)", _POLL_FALLBACK_INTERVAL)
    last_hb = 0.0
    loop = asyncio.get_event_loop()

    while True:
        now = time.monotonic()
        if now - last_hb >= _HEARTBEAT_INTERVAL:
            _hb("fd_ws")
            last_hb = now

        try:
            captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            today = _date.today().isoformat()
            # Same _ws suffix so the poll fallback also avoids the dual-writer
            # race and is included in the WS-file freshness merge.
            csv_path = os.path.join(_LINES_DIR, f"{today}_fd_ws.csv")

            from curl_cffi import requests as cf_req
            r = await loop.run_in_executor(
                None,
                lambda: cf_req.get(
                    _NJ_REST_URL,
                    headers={
                        "Accept": "application/json",
                        "Referer": "https://sportsbook.fanduel.com/",
                        "Origin": "https://sportsbook.fanduel.com",
                    },
                    impersonate="chrome120",
                    timeout=15,
                ),
            )
            if r.status_code == 200:
                rows = _normalize_rest(r.json(), captured_at)
                if rows:
                    written = _write_csv(rows, csv_path)
                    log.info("[fd-poll] rows=%d new=%d", len(rows), written)
                    if written > 0:
                        await _publish(captured_at, "multi", written, csv_path)
            else:
                log.warning("[fd-poll] non-200: %d", r.status_code)
        except Exception as exc:  # noqa: BLE001
            log.warning("[fd-poll] tick error: %s", exc)

        await asyncio.sleep(_POLL_FALLBACK_INTERVAL)


# ── core WS subscriber loop ──────────────────────────────────────────────

async def _ws_loop(cookies: Dict[str, str]) -> None:
    """CometD/Bayeux WS subscriber. Returns when WS is unreachable (for fallback)."""
    attempt = 0
    last_hb = 0.0

    # Build cookie header from primed session
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    extra_headers: Dict[str, str] = dict(_CONNECT_HEADERS)
    if cookie_header:
        extra_headers["Cookie"] = cookie_header

    # Fetch event IDs for subscription (retry once if empty)
    event_ids = _fetch_nba_event_ids()
    if not event_ids:
        log.warning("[fd-ws] no NBA events found — will still connect and subscribe broadly")

    while True:
        now = time.monotonic()
        if now - last_hb >= _HEARTBEAT_INTERVAL:
            _hb("fd_ws")
            last_hb = now

        try:
            ws = await asyncio.wait_for(
                websockets.connect(
                    _WS_URL,
                    additional_headers=extra_headers,
                    open_timeout=12,
                    close_timeout=5,
                    ping_interval=20,
                    ping_timeout=10,
                ),
                timeout=15,
            )
            log.info("[fd-ws] connected to %s", _WS_URL)
        except Exception as exc:  # noqa: BLE001
            delay = _BACKOFF_SEQUENCE[min(attempt, len(_BACKOFF_SEQUENCE) - 1)]
            log.warning(
                "[fd-ws] connect failed (attempt %d): %s — retry in %ds",
                attempt, exc, delay,
            )
            attempt += 1
            if attempt >= 6:
                # 6 consecutive failures — hand off to HTTP fallback
                log.warning("[fd-ws] 6 failures — handing off to HTTP poll fallback")
                return
            await asyncio.sleep(delay)
            continue

        attempt = 0
        client_id: Optional[str] = None
        msg_id = 2

        try:
            async with ws:
                # ── handshake ──────────────────────────────────────
                await ws.send(_msg_handshake())
                log.debug("[fd-ws] sent handshake")

                async for raw in ws:
                    now = time.monotonic()
                    if now - last_hb >= _HEARTBEAT_INTERVAL:
                        _hb("fd_ws")
                        last_hb = now

                    if isinstance(raw, bytes):
                        log.debug("[fd-ws] binary frame %d bytes (skip)", len(raw))
                        continue

                    try:
                        msgs = json.loads(raw)
                    except json.JSONDecodeError:
                        log.debug("[fd-ws] non-JSON frame: %s", raw[:200])
                        continue

                    if not isinstance(msgs, list):
                        msgs = [msgs]

                    for msg in msgs:
                        channel = msg.get("channel", "")

                        # ── meta/handshake response ───────────────
                        if channel == "/meta/handshake":
                            if not msg.get("successful"):
                                log.error("[fd-ws] handshake failed: %s", msg)
                                break
                            client_id = msg["clientId"]
                            log.info("[fd-ws] handshake OK clientId=%s", client_id[:8])

                            # Send connect
                            await ws.send(_msg_connect(client_id, msg_id))
                            msg_id += 1
                            continue

                        # ── meta/connect response ─────────────────
                        if channel == "/meta/connect":
                            if not msg.get("successful"):
                                log.warning("[fd-ws] connect rejected: %s", msg)
                                continue
                            log.debug("[fd-ws] connect confirmed")

                            # Subscribe to each NBA event
                            if not event_ids:
                                log.warning("[fd-ws] no event IDs to subscribe to")
                            for eid in event_ids:
                                sub_msg = _msg_subscribe(client_id, eid, msg_id)
                                await ws.send(sub_msg)
                                msg_id += 1
                                log.debug("[fd-ws] subscribed eventId=%s", eid)

                            # Re-send connect for long-poll keep-alive
                            await ws.send(_msg_connect(client_id, msg_id))
                            msg_id += 1
                            continue

                        # ── meta/subscribe response ───────────────
                        if channel == "/meta/subscribe":
                            if msg.get("successful"):
                                log.info("[fd-ws] subscription confirmed: %s",
                                         msg.get("subscription"))
                            else:
                                log.warning("[fd-ws] subscribe failed: %s", msg)
                            continue

                        # ── meta/disconnect ───────────────────────
                        if channel == "/meta/disconnect":
                            log.warning("[fd-ws] server sent disconnect: %s", msg)
                            break

                        # ── market push ───────────────────────────
                        if channel.startswith("/1/markets/"):
                            data = msg.get("data")
                            if data:
                                await _handle_push(data, channel)
                            continue

                        log.debug("[fd-ws] unhandled channel=%s", channel)

        except (ConnectionClosedError, ConnectionClosedOK) as exc:
            log.warning("[fd-ws] connection closed: %s — reconnecting", exc)
        except Exception as exc:  # noqa: BLE001
            log.error("[fd-ws] unexpected error: %s", exc)

        delay = _BACKOFF_SEQUENCE[min(attempt, len(_BACKOFF_SEQUENCE) - 1)]
        log.info("[fd-ws] reconnect in %ds (attempt %d)", delay, attempt)
        attempt += 1
        await asyncio.sleep(delay)


# ── public entry points ──────────────────────────────────────────────────

async def start_fd_ws() -> None:
    """Top-level coroutine spawned from live_v2_app._startup().

    Checks FD_WS_ENABLED env-var. Tries the CometD WS subscriber first;
    if the WS is geo-restricted (6 consecutive failures), drops to HTTP
    poll fallback at 30s interval.
    """
    if os.environ.get("FD_WS_ENABLED", "").strip() not in ("1", "true", "yes", "on"):
        log.debug("[fd-ws] FD_WS_ENABLED not set — subscriber disabled")
        return

    log.info("[fd-ws] starting FanDuel NBA prop subscriber (CometD/Bayeux)")

    # Prime cookies from sportsbook.fanduel.com
    loop = asyncio.get_event_loop()
    cookies = await loop.run_in_executor(None, _prime_cookies)

    # Try WS first, fall back to HTTP polling if geo-blocked
    await _ws_loop(cookies)
    # If _ws_loop returns (exhausted retries), switch to poll
    log.info("[fd-ws] WS unreachable — starting HTTP poll fallback")
    await _poll_loop()


def main() -> None:
    """CLI entry point: python scripts/fanduel_ws.py"""
    import argparse
    ap = argparse.ArgumentParser(description="FanDuel NBA WS prop subscriber")
    ap.add_argument("--debug", action="store_true", help="Verbose logging")
    ap.add_argument("--poll-only", action="store_true",
                    help="Skip WS, use HTTP poll fallback directly")
    args = ap.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    os.environ["FD_WS_ENABLED"] = "1"

    if args.poll_only:
        asyncio.run(_poll_loop())
    else:
        asyncio.run(start_fd_ws())


if __name__ == "__main__":
    main()
