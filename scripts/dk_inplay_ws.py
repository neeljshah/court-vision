"""dk_inplay_ws.py — DraftKings IN-PLAY WebSocket subscriber for NBA player props.

Connects to the same DK sportsbook WS as draftkings_ws.py but subscribes to
IN-PLAY (live) player-prop subcategories.  The DK in-play market IDs differ
from pregame IDs; the pregame subCategoryIds (12488, 12492, ...) are SUSPENDED
once a game goes live.  Discovered live in-play IDs must be validated on the
owner's residential network — see _INPLAY_SUBCATEGORY_IDS below.

Output file: data/lines/<today>_dk_inplay_ws.csv
Book label  : "dk_inplay"  (matches draftkings_inplay_scraper.py / the HTTP
              in-play path so _load_inplay_line_history merges them as the same
              book)

The file is auto-consumed by api/courtvision_router.py::_load_inplay_line_history
which globs data/lines/<date>_*inplay*.csv — no consumer change needed.

Gate:
  Set env DK_INPLAY_WS_ENABLED=1 to activate. If _INPLAY_SUBCATEGORY_IDS is
  empty (not yet configured), the subscriber idles with a clear warning and
  does NOT write garbage rows.

Protocol:
  Mirrors draftkings_ws.py exactly — JSON-RPC 2.0 subscribe over wss with
  exponential backoff reconnect.  The WS host + handshake structure are
  identical for pre-game and in-play markets; only the subCategoryId differs.

Run standalone:
    python scripts/dk_inplay_ws.py
    python scripts/dk_inplay_ws.py --debug

IMPORTANT — OWNER MUST FILL:
    Open sportsbook.draftkings.com in Chrome during a live NBA game, open
    DevTools → Network → WS → filter by 'websocket', subscribe message has
    "subCategoryId" under clientMetadata.  Record those IDs for each stat and
    paste them into _INPLAY_SUBCATEGORY_IDS below.  The current values are
    PLACEHOLDERS — the connection attempt will be skipped until they are filled.
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

# ── NBA league ID (same for pregame + in-play) ───────────────────────────────
_NBA_LEAGUE_ID = "42648"

# ── IN-PLAY MARKET QUERY (OData filter sent in the subscribe message) ─────────
#
# FILL INSTRUCTION:
#   During a live game on sportsbook.draftkings.com, open Chrome DevTools →
#   Network → WS → look at the "subscribe" message payloads.  The in-play
#   markets use a different subCategoryId from pregame (the pregame IDs
#   12488/12492/12495/12497 are SUSPENDED once the game tips).
#   Replace the dict values below with the IDs you discover.  Remove the
#   placeholder comments once validated on your residential network.
#
# Example (unverified — these are the HTTP in-play IDs from
#   draftkings_inplay_scraper.py as a starting point; the WS may use different
#   subCategoryIds — VALIDATE via DevTools):
#   "pts":  ("1686", "16413")
#   "ast":  ("1687", "16414")
#   "reb":  ("1688", "16415")
#   "fg3m": ("1689", "16416")
#   "blk":  ("1691", "16418")
#   "stl":  ("1691", "16419")
#
# FORMAT: { "stat": ("categoryId", "subcategoryId") }
# Leave empty dict {} to idle gracefully without writing any rows.
# ─────────────────────────────────────────────────────────────────────────────
_INPLAY_SUBCATEGORY_IDS: Dict[str, Tuple[str, str]] = {
    # ↓ PLACEHOLDER — validate on residential network during a live NBA game ↓
    # "pts":  ("1686", "16413"),   # Points O/U  — UNVERIFIED WS subcategoryId
    # "ast":  ("1687", "16414"),   # Assists O/U — UNVERIFIED WS subcategoryId
    # "reb":  ("1688", "16415"),   # Rebounds O/U — UNVERIFIED WS subcategoryId
    # "fg3m": ("1689", "16416"),   # 3PM O/U     — UNVERIFIED WS subcategoryId
    # "blk":  ("1691", "16418"),   # Blocks O/U  — UNVERIFIED WS subcategoryId
    # "stl":  ("1691", "16419"),   # Steals O/U  — UNVERIFIED WS subcategoryId
    # ↑ Uncomment + fill with verified IDs discovered on residential network  ↑
}

# OData query injected into each subscribe message.
# The {sub_id} placeholder is replaced per stat in _build_subscribe_msg().
_INPLAY_MARKET_QUERY = (
    "$filter=leagueId eq '{league_id}' "
    "and clientMetadata/subCategoryId eq '{sub_id}' "
    "and tags/all(t: t ne 'SportcastBetBuilder')"
)

# ── WS connection (same hosts + headers as draftkings_ws.py) ─────────────────
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
os.makedirs(_LINES_DIR, exist_ok=True)

# ── CSV schema — EXACT match to what _load_inplay_line_history expects ────────
# Verified against: api/courtvision_router.py::_load_inplay_line_history ~L4281
# and draftkings_inplay_scraper.py::CANONICAL_FIELDS.
# book column MUST be "dk_inplay" so it merges with _dk_inplay.csv rows as the
# same in-play book in _load_inplay_line_history.
_CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]
_INPLAY_BOOK_LABEL = "dk_inplay"


# ── helpers ──────────────────────────────────────────────────────────────────

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
    """Return JSON-RPC 2.0 subscribe message for one in-play stat subcategory."""
    query = _INPLAY_MARKET_QUERY.format(
        league_id=_NBA_LEAGUE_ID,
        sub_id=sub_id,
    )
    return json.dumps({
        "jsonrpc": "2.0",
        "method": "subscribe",
        "params": {
            "entity": "markets",
            "queryParams": {
                "query": query,
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
        "id": f"inplay-{stat}",
    })


def _normalize_push(
    payload: Any,
    stat: str,
    captured_at: str,
) -> List[Dict[str, Any]]:
    """Convert a WS push payload to canonical in-play CSV rows.

    The push data has the same JSON shape as the HTTP subcategory API:
      { events: [...], markets: [...], selections: [...] }
    Supports both standard O/U markets (over + under selections) and
    one-sided milestone markets (over_price only, under_price="").
    book column is always "dk_inplay".
    """
    if not isinstance(payload, dict):
        return []

    events: Dict[str, Any] = {
        str(e["id"]): e for e in (payload.get("events") or [])
    }
    markets: List[Dict[str, Any]] = payload.get("markets") or []
    selections: List[Dict[str, Any]] = payload.get("selections") or []

    sel_by_market: Dict[str, List[Dict[str, Any]]] = {}
    for s in selections:
        mid = str(s.get("marketId") or "")
        if mid:
            sel_by_market.setdefault(mid, []).append(s)

    rows: List[Dict[str, Any]] = []
    for m in markets:
        mid = str(m.get("id") or "")
        sels = sel_by_market.get(mid, [])
        if not sels:
            continue

        ev_id = str(m.get("eventId") or "")
        ev = events.get(ev_id) or {}
        start_time = ev.get("startEventDate") or ""

        # Resolve player from any selection's participants list
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

        # Parse O/U lines — handles both standard two-sided markets and one-sided
        line: Optional[float] = None
        over_price: Optional[int] = None
        under_price: Optional[int] = None

        for s in sels:
            side = (
                s.get("outcomeType")
                or s.get("label")
                or ""
            ).strip().lower()
            pts = s.get("points")
            if pts is None:
                # Fallback: try "Over X.5" label parsing for milestone markets
                label = (s.get("label") or "").strip()
                if label.endswith("+"):
                    try:
                        threshold = float(label.rstrip("+"))
                        pts = threshold - 0.5
                        side = "over"
                    except (TypeError, ValueError):
                        continue
                else:
                    continue
            try:
                pts_f = float(pts)
            except (TypeError, ValueError):
                continue
            price = _parse_odds((s.get("displayOdds") or {}).get("american"))
            if side in ("over",):
                line = pts_f
                over_price = price
            elif side in ("under",):
                line = pts_f
                under_price = price

        if line is None or (over_price is None and under_price is None):
            continue

        rows.append({
            "captured_at": captured_at,
            "book": _INPLAY_BOOK_LABEL,
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
    """Append rows to CSV, deduplicating on (captured_at[:16], player, stat, line).

    Returns the number of net-new rows written.
    Mirrors draftkings_ws.py::_write_csv exactly.
    """
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    existing_keys: Set[Tuple[str, str, str, str]] = set()
    if not new_file:
        try:
            with open(path, "r", encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    existing_keys.add((
                        (r.get("captured_at") or "")[:16],
                        r.get("player_name") or "",
                        r.get("stat") or "",
                        str(r.get("line") or ""),
                    ))
        except OSError:
            new_file = True

    written = 0
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_CANONICAL_FIELDS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for r in rows:
            key: Tuple[str, str, str, str] = (
                r["captured_at"][:16],
                r["player_name"],
                r["stat"],
                str(r["line"]),
            )
            if key in existing_keys:
                continue
            existing_keys.add(key)
            w.writerow(r)
            written += 1
    return written


async def _connect_with_fallback(
    hosts: List[str],
) -> "websockets.WebSocketClientProtocol":
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
            log.info("[dk-inplay-ws] connected to %s", host)
            return ws
        except Exception as exc:  # noqa: BLE001
            log.warning("[dk-inplay-ws] %s unreachable: %s", host, exc)
            last_exc = exc
    raise last_exc


# ── core subscriber loop ──────────────────────────────────────────────────────

async def _subscriber_loop() -> None:
    """Persistent in-play WS subscriber with reconnect backoff. Runs forever."""
    attempt = 0
    last_hb = 0.0

    while True:
        # heartbeat
        now = time.monotonic()
        if now - last_hb >= _HEARTBEAT_INTERVAL:
            _hb("dk_inplay_ws")
            last_hb = now

        try:
            ws = await _connect_with_fallback(_WS_HOSTS)
        except Exception as exc:  # noqa: BLE001
            delay = _BACKOFF_SEQUENCE[min(attempt, len(_BACKOFF_SEQUENCE) - 1)]
            log.error(
                "[dk-inplay-ws] all hosts failed (attempt %d): %s — retry in %ds",
                attempt, exc, delay,
            )
            attempt += 1
            await asyncio.sleep(delay)
            continue

        attempt = 0  # reset on successful connect

        try:
            async with ws:
                # Subscribe to all configured in-play stat subcategories
                for stat, (_cat, sub_id) in _INPLAY_SUBCATEGORY_IDS.items():
                    msg = _build_subscribe_msg(stat, sub_id)
                    await ws.send(msg)
                    log.debug(
                        "[dk-inplay-ws] subscribed stat=%s sub_id=%s", stat, sub_id
                    )

                async for raw in ws:
                    now = time.monotonic()
                    if now - last_hb >= _HEARTBEAT_INTERVAL:
                        _hb("dk_inplay_ws")
                        last_hb = now

                    if isinstance(raw, bytes):
                        log.debug(
                            "[dk-inplay-ws] binary msg %d bytes (skipped)", len(raw)
                        )
                        continue

                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        log.warning(
                            "[dk-inplay-ws] non-JSON message: %s", raw[:200]
                        )
                        continue

                    event = msg.get("event", "")
                    sub_id_resp = msg.get("id", "")

                    if event == "subscribed":
                        log.info(
                            "[dk-inplay-ws] subscription confirmed: id=%s",
                            sub_id_resp,
                        )
                        data = msg.get("data")
                        if data and isinstance(data, dict):
                            await _handle_payload(data, sub_id_resp)
                        continue

                    if event in ("exception", "subscription-terminated"):
                        log.warning(
                            "[dk-inplay-ws] sub error id=%s: %s",
                            sub_id_resp, msg.get("error"),
                        )
                        continue

                    data = msg.get("data")
                    if data and isinstance(data, dict):
                        await _handle_payload(data, sub_id_resp)

        except (ConnectionClosedError, ConnectionClosedOK) as exc:
            log.warning("[dk-inplay-ws] connection closed: %s — reconnecting", exc)
        except Exception as exc:  # noqa: BLE001
            log.error("[dk-inplay-ws] unexpected error: %s", exc)

        delay = _BACKOFF_SEQUENCE[min(attempt, len(_BACKOFF_SEQUENCE) - 1)]
        log.info("[dk-inplay-ws] reconnect in %ds (attempt %d)", delay, attempt)
        attempt += 1
        await asyncio.sleep(delay)


async def _handle_payload(data: Dict[str, Any], sub_id: str) -> None:
    """Parse a push payload, write CSV, publish to event bus."""
    # "inplay-pts" → "pts"
    stat = (
        sub_id.replace("inplay-", "")
        if sub_id.startswith("inplay-")
        else sub_id.replace("sub-", "")
    )

    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    today = _date.today().isoformat()

    # File named <date>_dk_inplay_ws.csv — matches the glob pattern
    # data/lines/<date>_*inplay*.csv used by _load_inplay_line_history.
    # A separate _ws suffix avoids dual-writer race with the HTTP
    # draftkings_inplay_scraper.py which writes <date>_dk_inplay.csv.
    csv_path = os.path.join(_LINES_DIR, f"{today}_dk_inplay_ws.csv")

    rows = _normalize_push(data, stat, captured_at)
    if not rows:
        return

    written = _write_csv(rows, csv_path)
    log.info(
        "[dk-inplay-ws] stat=%s rows=%d new=%d csv=%s",
        stat, len(rows), written, os.path.basename(csv_path),
    )

    if written > 0 and _BUS_AVAILABLE:
        try:
            bus = get_bus()
            await bus.publish(TOPIC_LINES_REFRESHED, {
                "source": "dk_inplay_ws",
                "book": _INPLAY_BOOK_LABEL,
                "stat": stat,
                "rows": written,
                "csv": csv_path,
                "captured_at": captured_at,
            })
        except Exception as exc:  # noqa: BLE001
            log.debug("[dk-inplay-ws] event bus publish failed: %s", exc)


# ── public entry point ────────────────────────────────────────────────────────

async def start_dk_inplay_ws() -> None:
    """Top-level coroutine to spawn from api/main.py::_start_ws_subscribers().

    Checks DK_INPLAY_WS_ENABLED env-var before starting.
    If _INPLAY_SUBCATEGORY_IDS is empty (not yet configured), logs a clear
    warning and idles without writing any rows or crashing.
    """
    if os.environ.get("DK_INPLAY_WS_ENABLED", "").strip() not in (
        "1", "true", "yes", "on"
    ):
        log.debug("[dk-inplay-ws] DK_INPLAY_WS_ENABLED not set — subscriber disabled")
        return

    if not _INPLAY_SUBCATEGORY_IDS:
        log.warning(
            "[dk-inplay-ws] IN-PLAY WS NOT CONFIGURED: _INPLAY_SUBCATEGORY_IDS is "
            "empty in scripts/dk_inplay_ws.py. "
            "During a live game, open Chrome DevTools → Network → WS → "
            "capture the 'subCategoryId' values from subscribe messages and "
            "fill _INPLAY_SUBCATEGORY_IDS in that file. "
            "Idling — no rows will be written until IDs are provided."
        )
        # Idle loop: stay alive so the supervised task does not restart-loop
        while True:
            _hb("dk_inplay_ws")
            await asyncio.sleep(_HEARTBEAT_INTERVAL)

    log.info(
        "[dk-inplay-ws] starting DK in-play NBA prop subscriber (%d stats: %s)",
        len(_INPLAY_SUBCATEGORY_IDS),
        ", ".join(_INPLAY_SUBCATEGORY_IDS),
    )
    await _subscriber_loop()


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point: python scripts/dk_inplay_ws.py"""
    import argparse
    ap = argparse.ArgumentParser(
        description="DraftKings NBA in-play WS prop subscriber"
    )
    ap.add_argument("--debug", action="store_true", help="Verbose logging")
    args = ap.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    os.environ["DK_INPLAY_WS_ENABLED"] = "1"
    asyncio.run(start_dk_inplay_ws())


if __name__ == "__main__":
    main()
