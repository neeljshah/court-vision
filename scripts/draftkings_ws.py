"""draftkings_ws.py — DraftKings WebSocket subscriber for live NBA player-prop odds.

Protocol (reverse-engineered from dkDataLayer.js SDK v3.1.0):
  * WS host: wss://sportsbook-ws-us-{state}.draftkings.com/websocket
    Tried in order: ia → nj → pa (all accept connections; ia is our geo-detected state).
  * No auth required for prop reads — jwt field sent as empty string.
  * Subscribe message (JSON-RPC 2.0):
      {
        "jsonrpc": "2.0",
        "method": "subscribe",
        "params": {
          "entity": "markets",
          "queryParams": {
            "query": "$filter=leagueId eq '42648' and clientMetadata/subCategoryId eq '{sub_id}'
                       and tags/all(t: t ne 'SportcastBetBuilder')",
            "initialData": true,
            "projection": "betOffers",
            "locale": "en-US"
          },
          "forwardedHeaders": {},
          "clientMetadata": {"feature": "league", "subCategoryId": "{sub_id}"},
          "jwt": "",
          "siteName": "dk-sandbox"
        },
        "id": "sub-{stat}"
      }
  * Server → client push message (JSON):
      {
        "id": "sub-{stat}",
        "event": "data-updated",     ← or "subscribed" on handshake
        "data": {...},               ← same shape as HTTP API payload
        "websocketPublishTimestamp": "2026-05-27T..."
      }
  * Binary (msgpack) messages are possible when the server detects a
    msgpack-capable client — we do not set that flag so we stay on JSON.
  * Reconnect: use exponential backoff 2→4→8→16→32→60s (capped).

Dedup logic (WS writer): (captured_at, player_name, stat, line, over_price, under_price) —
full-second timestamp + both prices so intra-minute price moves are preserved.

Run:
    python scripts/draftkings_ws.py            # long-running daemon
    DK_WS_ENABLED=1 (also wired into live_v2_app.py startup)
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

# ── constants ───────────────────────────────────────────────────────────
_NBA_LEAGUE_ID = "42648"

# (categoryId, subcategoryId) per canonical stat — mirrors draftkings_scraper.py
_DK_STAT_SUBS: Dict[str, Tuple[str, str]] = {
    "pts":  ("1215", "12488"),
    "reb":  ("1216", "12492"),
    "ast":  ("1217", "12495"),
    "fg3m": ("1218", "12497"),
}

# State-specific WS hosts to try in order (ia = Iowa, nj = New Jersey, pa = Pennsylvania)
_WS_HOSTS = [
    "wss://sportsbook-ws-us-ia.draftkings.com/websocket",
    "wss://sportsbook-ws-us-nj.draftkings.com/websocket",
    "wss://sportsbook-ws-us-pa.draftkings.com/websocket",
]

_CONNECT_HEADERS = {
    "Origin": "https://sportsbook.draftkings.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

_BACKOFF_SEQUENCE = [2, 4, 8, 16, 32, 60]  # seconds; stays at 60 after exhausted
_HEARTBEAT_INTERVAL = 30  # seconds between daemon_heartbeat writes
_LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
_CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]

os.makedirs(_LINES_DIR, exist_ok=True)


# ── helpers ──────────────────────────────────────────────────────────────

def _parse_odds(american: Optional[str]) -> Optional[int]:
    """DK americanOdds may use U+2212 (−) instead of ASCII minus."""
    if not american:
        return None
    s = str(american).replace("−", "-").replace("+", "").strip()
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _build_subscribe_msg(stat: str, sub_id: str) -> str:
    """Return JSON-RPC 2.0 subscribe message for one stat subcategory."""
    return json.dumps({
        "jsonrpc": "2.0",
        "method": "subscribe",
        "params": {
            "entity": "markets",
            "queryParams": {
                "query": (
                    f"$filter=leagueId eq '{_NBA_LEAGUE_ID}' "
                    f"and clientMetadata/subCategoryId eq '{sub_id}' "
                    f"and tags/all(t: t ne 'SportcastBetBuilder')"
                ),
                "initialData": True,
                "projection": "betOffers",
                "locale": "en-US",
            },
            "forwardedHeaders": {},
            "clientMetadata": {
                "feature": "league",
                "subCategoryId": sub_id,
                "X-Client-Name": "web",
                "X-Client-Version": "2621.3.1.5",
            },
            "jwt": "",
            "siteName": "dk-sandbox",
        },
        "id": f"sub-{stat}",
    })


def _normalize_push(payload: Any, stat: str, captured_at: str) -> List[Dict[str, Any]]:
    """Convert a WS push payload to canonical CSV rows.

    The push data has the same shape as the HTTP subcategory API:
      { events: [...], markets: [...], selections: [...] }
    We replicate the normalization logic from draftkings_scraper.normalize().
    """
    if not isinstance(payload, dict):
        return []

    events: Dict[str, Any] = {
        e["id"]: e for e in (payload.get("events") or [])
    }
    markets: List[Dict[str, Any]] = payload.get("markets") or []
    selections: List[Dict[str, Any]] = payload.get("selections") or []

    sel_by_market: Dict[str, List[Dict[str, Any]]] = {}
    for s in selections:
        mid = s.get("marketId")
        if mid:
            sel_by_market.setdefault(mid, []).append(s)

    rows: List[Dict[str, Any]] = []
    for m in markets:
        mid = m.get("id")
        sels = sel_by_market.get(mid, [])
        if not sels:
            continue

        ev_id = m.get("eventId") or ""
        ev = events.get(ev_id) or {}
        start_time = ev.get("startEventDate") or ""

        player_name = ""
        player_id: Any = ""
        for s in sels:
            parts = [
                p for p in (s.get("participants") or [])
                if (p.get("type") == "Player")
            ]
            if len(parts) != 1:
                continue
            player_name = parts[0].get("name") or ""
            player_id = parts[0].get("id") or ""
            break
        if not player_name:
            continue

        line: Optional[float] = None
        over_price: Optional[int] = None
        under_price: Optional[int] = None
        for s in sels:
            label = (s.get("label") or "").strip().lower()
            pts = s.get("points")
            if pts is None:
                continue
            try:
                pts_f = float(pts)
            except (TypeError, ValueError):
                continue
            price = _parse_odds((s.get("displayOdds") or {}).get("american"))
            if label == "over":
                line = pts_f
                over_price = price
            elif label == "under":
                line = pts_f
                under_price = price

        if line is None or (over_price is None and under_price is None):
            continue

        rows.append({
            "captured_at": captured_at,
            "book": "dk",
            "game_id": ev_id,
            "player_id": player_id,
            "player_name": player_name,
            "stat": stat,
            "line": line,
            "over_price": over_price if over_price is not None else "",
            "under_price": under_price if under_price is not None else "",
            "start_time": start_time,
        })
    return rows


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


async def _connect_with_fallback(hosts: List[str]) -> websockets.WebSocketClientProtocol:
    """Try WS hosts in order; raise the last exception if all fail."""
    last_exc: Exception = RuntimeError("no hosts provided")
    for host in hosts:
        try:
            ws = await websockets.connect(
                host,
                additional_headers=_CONNECT_HEADERS,
                open_timeout=10,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10,
            )
            log.info("[dk-ws] connected to %s", host)
            return ws
        except Exception as exc:  # noqa: BLE001
            log.warning("[dk-ws] %s unreachable: %s", host, exc)
            last_exc = exc
    raise last_exc


# ── core subscriber loop ─────────────────────────────────────────────────

async def _subscriber_loop() -> None:
    """Persistent WS subscriber with reconnect backoff. Runs forever."""
    attempt = 0
    last_hb = 0.0

    while True:
        # ── heartbeat ────────────────────────────────────────────────
        now = time.monotonic()
        if now - last_hb >= _HEARTBEAT_INTERVAL:
            _hb("dk_ws")
            last_hb = now

        # ── connect ──────────────────────────────────────────────────
        try:
            ws = await _connect_with_fallback(_WS_HOSTS)
        except Exception as exc:  # noqa: BLE001
            delay = _BACKOFF_SEQUENCE[min(attempt, len(_BACKOFF_SEQUENCE) - 1)]
            log.error("[dk-ws] all hosts failed (attempt %d): %s — retry in %ds",
                      attempt, exc, delay)
            attempt += 1
            await asyncio.sleep(delay)
            continue

        attempt = 0  # reset on successful connect

        try:
            async with ws:
                # ── subscribe to all stat subcategories ──────────────
                for stat, (_cat, sub_id) in _DK_STAT_SUBS.items():
                    msg = _build_subscribe_msg(stat, sub_id)
                    await ws.send(msg)
                    log.debug("[dk-ws] subscribed stat=%s sub_id=%s", stat, sub_id)

                # ── message pump ─────────────────────────────────────
                async for raw in ws:
                    # heartbeat check (every 30s inside the pump too)
                    now = time.monotonic()
                    if now - last_hb >= _HEARTBEAT_INTERVAL:
                        _hb("dk_ws")
                        last_hb = now

                    if isinstance(raw, bytes):
                        # Binary msgpack — skip (we requested JSON-only)
                        log.debug("[dk-ws] binary msg %d bytes (skipped)", len(raw))
                        continue

                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        log.warning("[dk-ws] non-JSON message: %s", raw[:200])
                        continue

                    event = msg.get("event", "")
                    sub_id_resp = msg.get("id", "")

                    if event == "subscribed":
                        log.info("[dk-ws] subscription confirmed: id=%s", sub_id_resp)
                        # Check if initial data was included
                        data = msg.get("data")
                        if data and isinstance(data, dict):
                            await _handle_payload(data, sub_id_resp)
                        continue

                    if event in ("exception", "subscription-terminated"):
                        log.warning("[dk-ws] sub error id=%s: %s",
                                    sub_id_resp, msg.get("error"))
                        continue

                    # Live update message
                    data = msg.get("data")
                    if data and isinstance(data, dict):
                        await _handle_payload(data, sub_id_resp)

        except (ConnectionClosedError, ConnectionClosedOK) as exc:
            log.warning("[dk-ws] connection closed: %s — reconnecting", exc)
        except Exception as exc:  # noqa: BLE001
            log.error("[dk-ws] unexpected error: %s", exc)

        delay = _BACKOFF_SEQUENCE[min(attempt, len(_BACKOFF_SEQUENCE) - 1)]
        log.info("[dk-ws] reconnect in %ds (attempt %d)", delay, attempt)
        attempt += 1
        await asyncio.sleep(delay)


async def _handle_payload(data: Dict[str, Any], sub_id: str) -> None:
    """Parse a push payload, write CSV, publish to event bus."""
    # Resolve stat from sub_id e.g. "sub-pts" → "pts"
    stat = sub_id.replace("sub-", "") if sub_id.startswith("sub-") else "unknown"

    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    today = _date.today().isoformat()
    # Write to a _ws-suffixed file to avoid dual-writer race with the HTTP
    # scraper (draftkings_scraper.py -> <date>_dk.csv).  The row's `book`
    # column stays "dk" (canonical), so consolidate_for_slate tags these
    # rows as DraftKings odds — no "_ws" book key ever surfaces in the UI.
    csv_path = os.path.join(_LINES_DIR, f"{today}_dk_ws.csv")

    rows = _normalize_push(data, stat, captured_at)
    if not rows:
        return

    written = _write_csv(rows, csv_path)
    log.info("[dk-ws] stat=%s rows=%d new=%d csv=%s",
             stat, len(rows), written, os.path.basename(csv_path))

    if written > 0 and _BUS_AVAILABLE:
        try:
            bus = get_bus()
            await bus.publish(TOPIC_LINES_REFRESHED, {
                "source": "dk_ws",
                "book": "dk",
                "stat": stat,
                "rows": written,
                "csv": csv_path,
                "captured_at": captured_at,
            })
        except Exception as exc:  # noqa: BLE001
            log.debug("[dk-ws] event bus publish failed: %s", exc)


# ── public entry points ──────────────────────────────────────────────────

async def start_dk_ws() -> None:
    """Top-level coroutine to spawn from live_v2_app._startup().

    Checks DK_WS_ENABLED env-var before starting. Returns immediately if
    the flag is not set to avoid any resource usage.
    """
    if not os.environ.get("DK_WS_ENABLED", "").strip() in ("1", "true", "yes", "on"):
        log.debug("[dk-ws] DK_WS_ENABLED not set — subscriber disabled")
        return
    log.info("[dk-ws] starting persistent NBA prop subscriber")
    await _subscriber_loop()


def main() -> None:
    """CLI entry point: python scripts/draftkings_ws.py"""
    import argparse
    ap = argparse.ArgumentParser(description="DraftKings NBA WS prop subscriber")
    ap.add_argument("--debug", action="store_true", help="Verbose logging")
    args = ap.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Force-enable for CLI runs
    os.environ["DK_WS_ENABLED"] = "1"
    asyncio.run(_subscriber_loop())


if __name__ == "__main__":
    main()
