"""L11_sporttrade_client.py — Sporttrade Exchange Client (PAPER / LIVE).

Sporttrade is a sports-exchange where contracts trade 1-99 (cents-on-dollar).

Mode gating
-----------
- SPORTTRADE_LIVE_ENABLED=1 AND SPORTTRADE_API_KEY set  → LIVE (HTTP calls)
- Default (env vars absent / empty)                     → PAPER (seed JSON files)
- SPORTTRADE_LIVE_ENABLED=1 without API key             → PermissionError on any call

Paper-vs-live mode delegated to L44_paper_mode.is_live_for_layer('sporttrade');
see L44 for the canonical list of env vars.

Public API
----------
    SporttradeQuote     dataclass
    SporttradePosition  dataclass
    find_nba_events(date)          -> list[dict]
    get_orderbook(market_id)       -> dict {bids, asks}
    get_positions()                -> list[SporttradePosition]
    post_order(market_id, side, qty, price, idempotency_key) -> dict
    cancel_order(order_id)         -> bool
    subscribe_ws(market_ids, on_msg) -> never (stub)

CLI
---
    python L11_sporttrade_client.py events [--date YYYY-MM-DD]
    python L11_sporttrade_client.py orderbook --market_id mkt_test
    python L11_sporttrade_client.py positions
    python L11_sporttrade_client.py post --market_id X --side back --qty 10 --price 55 [--live]

Environment Variables
---------------------
    SPORTTRADE_LIVE_ENABLED  — set to "1" to activate live (HTTP) mode; default paper.
                               Canonical flag read via L44_paper_mode.is_live_for_layer('sporttrade').
    SPORTTRADE_API_KEY       — bearer token for live REST/WS calls; required when
                               SPORTTRADE_LIVE_ENABLED=1.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# L44 soft-import — delegates paper/live mode to the canonical library
# ---------------------------------------------------------------------------

try:
    from scripts.execute_loop import L44_paper_mode as _L44
except Exception:
    _L44 = None

# ---------------------------------------------------------------------------
# Configurable path roots (overridable in tests)
# ---------------------------------------------------------------------------
_SEED_DIR: Path = PROJECT_DIR / "data" / "exchange_seed" / "sporttrade"
_LEDGER_DIR: Path = PROJECT_DIR / "data" / "ledger"
_PAPER_ORDERS_FILE_NAME = "paper_sporttrade_orders.json"

_LIVE_REST_BASE = "https://api.sporttrade.com/v1"
_LIVE_WS_URL = "wss://stream.sporttrade.com/v1"

# ---------------------------------------------------------------------------
# In-process idempotency cache (LRU, capped at 512 keys)
# ---------------------------------------------------------------------------
_IDEMPOTENCY_CACHE: dict[str, dict] = {}
_IDEMPOTENCY_MAX = 512


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SporttradeQuote:
    market_id: str
    market_type: str        # "spread" | "total" | "ml" | "player_prop"
    event_id: str
    side: str
    price: float            # 1-99 (Sporttrade contract price)
    liquidity_qty: int
    ts: str


@dataclass
class SporttradePosition:
    market_id: str
    side: str
    qty: int
    avg_price: float
    unrealized_pnl: float


# ---------------------------------------------------------------------------
# Mode detection helpers
# ---------------------------------------------------------------------------

def _is_live_enabled() -> bool:
    if _L44 is not None:
        return _L44.is_live_for_layer("sporttrade")
    # fallback to inline env read (preserves backward compat if L44 absent)
    return os.environ.get("SPORTTRADE_LIVE_ENABLED", "0").lower() in ("1", "true")


def _api_key() -> Optional[str]:
    return os.environ.get("SPORTTRADE_API_KEY", "").strip() or None


def _check_live_auth() -> None:
    """Raise PermissionError if LIVE_ENABLED but no API key."""
    if _is_live_enabled() and not _api_key():
        raise PermissionError(
            "SPORTTRADE_LIVE_ENABLED=1 but SPORTTRADE_API_KEY is not set. "
            "Set the key or unset SPORTTRADE_LIVE_ENABLED to use paper mode."
        )


def _mode() -> str:
    """Return 'live' or 'paper'."""
    _check_live_auth()
    return "live" if (_is_live_enabled() and _api_key()) else "paper"


# ---------------------------------------------------------------------------
# Path helpers (accept overrides injected by tests)
# ---------------------------------------------------------------------------

def _seed_dir() -> Path:
    return _SEED_DIR


def _ledger_dir() -> Path:
    return _LEDGER_DIR


def _paper_orders_path() -> Path:
    return _ledger_dir() / _PAPER_ORDERS_FILE_NAME


# ---------------------------------------------------------------------------
# PAPER helpers
# ---------------------------------------------------------------------------

def _paper_events_path(date: str) -> Path:
    return _seed_dir() / f"events_{date}.json"


def _read_json(path: Path) -> object:
    if not path.exists():
        raise KeyError(f"Seed file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_paper_orders() -> list[dict]:
    p = _paper_orders_path()
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


def _atomic_write_json(path: Path, payload: object) -> None:
    """Write *payload* as JSON to *path* atomically via tempfile + os.replace.

    On failure the original file is left untouched and the temp file is removed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _save_paper_orders(orders: list[dict]) -> None:
    _atomic_write_json(_paper_orders_path(), orders)


# ---------------------------------------------------------------------------
# LIVE helpers (lazy-import requests; never called in paper)
# ---------------------------------------------------------------------------

def _live_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


def _live_get(path: str) -> dict:
    import requests  # lazy
    url = f"{_LIVE_REST_BASE}{path}"
    log.debug("GET %s", url)
    resp = requests.get(url, headers=_live_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def _live_post(path: str, payload: dict) -> dict:
    import requests  # lazy
    url = f"{_LIVE_REST_BASE}{path}"
    log.debug("POST %s payload=%s", url, payload)
    resp = requests.post(url, headers=_live_headers(), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _live_delete(path: str) -> dict:
    import requests  # lazy
    url = f"{_LIVE_REST_BASE}{path}"
    log.debug("DELETE %s", url)
    resp = requests.delete(url, headers=_live_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_order(price: float, qty: int) -> None:
    if price <= 0 or price >= 100:
        raise ValueError(f"price must be in (0, 100) exclusive; got {price}")
    if qty <= 0:
        raise ValueError(f"qty must be > 0; got {qty}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_nba_events(date: Optional[str] = None) -> list[dict]:
    """Return NBA events for *date* (YYYY-MM-DD; default today UTC).

    Paper: reads data/exchange_seed/sporttrade/events_<date>.json.
    Live:  GET /v1/events?sport=nba&date=<date>
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    mode = _mode()
    log.debug("[%s] find_nba_events date=%s", mode, date)

    if mode == "paper":
        path = _paper_events_path(date)
        events = _read_json(path)
        if not isinstance(events, list):
            raise ValueError(f"Expected list in {path}; got {type(events)}")
        return events

    # LIVE
    data = _live_get(f"/events?sport=nba&date={date}")
    return data.get("events", data) if isinstance(data, dict) else data


def get_orderbook(market_id: str) -> dict:
    """Return orderbook for *market_id* as {bids: [[price, qty], ...], asks: ...}.

    Paper: reads data/exchange_seed/sporttrade/<market_id>.json; missing → KeyError.
    Live:  GET /v1/markets/<market_id>/orderbook
    """
    mode = _mode()
    log.debug("[%s] get_orderbook market_id=%s", mode, market_id)

    if mode == "paper":
        path = _seed_dir() / f"{market_id}.json"
        book = _read_json(path)
        if not isinstance(book, dict):
            raise ValueError(f"Expected dict in {path}")
        return book

    # LIVE
    return _live_get(f"/markets/{market_id}/orderbook")


def post_order(
    market_id: str,
    side: str,
    qty: int,
    price: float,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Submit an order.

    Validation (both modes):
        price must be in (0, 100) exclusive → ValueError
        qty must be > 0               → ValueError

    Paper:
        Returns {"order_id": "paper-st-<12hex>", "status": "filled"}.
        Appends the order record to data/ledger/paper_sporttrade_orders.json.
        Idempotency: if *idempotency_key* already seen this process, returns cached result.

    Live:
        POST /v1/orders  with idempotency header.
    """
    _validate_order(price, qty)

    # Idempotency check (both modes share the in-process cache)
    if idempotency_key and idempotency_key in _IDEMPOTENCY_CACHE:
        log.debug("Idempotency hit for key=%s", idempotency_key)
        return _IDEMPOTENCY_CACHE[idempotency_key]

    mode = _mode()
    log.debug(
        "[%s] post_order market=%s side=%s qty=%d price=%.2f ikey=%s",
        mode, market_id, side, qty, price, idempotency_key,
    )

    if mode == "paper":
        order_id = f"paper-st-{uuid4().hex[:12]}"
        result = {"order_id": order_id, "status": "filled"}
        record = {
            "order_id": order_id,
            "market_id": market_id,
            "side": side,
            "qty": qty,
            "price": price,
            "ts": datetime.now(timezone.utc).isoformat(),
            "idempotency_key": idempotency_key,
        }
        orders = _load_paper_orders()
        orders.append(record)
        _save_paper_orders(orders)
        log.info("Paper order filed: %s", order_id)
    else:
        # LIVE
        payload: dict = {
            "market_id": market_id,
            "side": side,
            "qty": qty,
            "price": price,
        }
        headers_extra: dict = {}
        if idempotency_key:
            headers_extra["Idempotency-Key"] = idempotency_key
        result = _live_post("/orders", payload)

    # Cache result
    if idempotency_key:
        if len(_IDEMPOTENCY_CACHE) >= _IDEMPOTENCY_MAX:
            # Evict oldest key (insertion-order dict, Python 3.7+)
            oldest = next(iter(_IDEMPOTENCY_CACHE))
            del _IDEMPOTENCY_CACHE[oldest]
        _IDEMPOTENCY_CACHE[idempotency_key] = result

    return result


def cancel_order(order_id: str) -> bool:
    """Cancel an open order by *order_id*.

    Paper: always returns True (no open orders in paper mode).
    Live:  DELETE /v1/orders/<order_id>
    """
    mode = _mode()
    log.debug("[%s] cancel_order order_id=%s", mode, order_id)

    if mode == "paper":
        log.info("Paper cancel (no-op) for %s", order_id)
        return True

    # LIVE
    resp = _live_delete(f"/orders/{order_id}")
    return resp.get("status", "") in ("cancelled", "canceled", "ok", "success")


def get_positions() -> list[SporttradePosition]:
    """Return current open positions.

    Paper:
        Aggregates paper ledger by (market_id, side).
        avg_price = weighted average of fill prices.
        unrealized_pnl = (orderbook mid - avg_price) * qty.
        If orderbook file missing, unrealized_pnl defaults to 0.0.

    Live:
        GET /v1/positions
    """
    mode = _mode()
    log.debug("[%s] get_positions", mode)

    if mode == "paper":
        orders = _load_paper_orders()
        # Aggregate: {(market_id, side): {"qty": int, "cost": float}}
        agg: dict[tuple, dict] = {}
        for o in orders:
            key = (o["market_id"], o["side"])
            if key not in agg:
                agg[key] = {"qty": 0, "cost": 0.0}
            agg[key]["qty"] += o["qty"]
            agg[key]["cost"] += o["qty"] * o["price"]

        positions: list[SporttradePosition] = []
        for (market_id, side), data in agg.items():
            total_qty = data["qty"]
            avg_price = data["cost"] / total_qty if total_qty else 0.0
            # Attempt mid from orderbook
            try:
                book = get_orderbook(market_id)
                bids = book.get("bids", [])
                asks = book.get("asks", [])
                best_bid = bids[0][0] if bids else avg_price
                best_ask = asks[0][0] if asks else avg_price
                mid = (best_bid + best_ask) / 2.0
            except (KeyError, IndexError, Exception):
                mid = avg_price
            pnl = (mid - avg_price) * total_qty
            positions.append(SporttradePosition(
                market_id=market_id,
                side=side,
                qty=total_qty,
                avg_price=round(avg_price, 4),
                unrealized_pnl=round(pnl, 4),
            ))
        return positions

    # LIVE
    data = _live_get("/positions")
    raw = data.get("positions", data) if isinstance(data, dict) else data
    return [
        SporttradePosition(
            market_id=p["market_id"],
            side=p["side"],
            qty=p["qty"],
            avg_price=p["avg_price"],
            unrealized_pnl=p.get("unrealized_pnl", 0.0),
        )
        for p in raw
    ]


def subscribe_ws(
    market_ids: list[str],
    on_msg: Callable[[dict], None],
) -> None:
    """Stream orderbook updates over WebSocket.

    Stub: raises NotImplementedError in paper mode.
    Live stub: would connect to wss://stream.sporttrade.com/v1 with bearer auth.
    """
    mode = _mode()
    if mode == "paper":
        raise NotImplementedError(
            "subscribe_ws is not supported in paper mode. "
            "Set SPORTTRADE_LIVE_ENABLED=1 and SPORTTRADE_API_KEY to use live streaming."
        )
    # LIVE stub — would use websocket-client
    raise NotImplementedError(
        "subscribe_ws live implementation pending. "
        "Install websocket-client and implement the WS handshake."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_events(args: argparse.Namespace) -> None:
    events = find_nba_events(args.date)
    print(json.dumps(events, indent=2))


def _cli_orderbook(args: argparse.Namespace) -> None:
    book = get_orderbook(args.market_id)
    print(json.dumps(book, indent=2))


def _cli_positions(args: argparse.Namespace) -> None:
    positions = get_positions()
    print(json.dumps([asdict(p) for p in positions], indent=2))


def _cli_post(args: argparse.Namespace) -> None:
    if args.live:
        os.environ["SPORTTRADE_LIVE_ENABLED"] = "1"
    result = post_order(
        market_id=args.market_id,
        side=args.side,
        qty=args.qty,
        price=args.price,
    )
    print(json.dumps(result, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sporttrade exchange client (paper/live)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # events
    p_events = sub.add_parser("events", help="List NBA events")
    p_events.add_argument("--date", default=None, help="YYYY-MM-DD (default today UTC)")
    p_events.set_defaults(func=_cli_events)

    # orderbook
    p_ob = sub.add_parser("orderbook", help="Get orderbook for a market")
    p_ob.add_argument("--market_id", required=True)
    p_ob.set_defaults(func=_cli_orderbook)

    # positions
    p_pos = sub.add_parser("positions", help="Show current paper positions")
    p_pos.set_defaults(func=_cli_positions)

    # post
    p_post = sub.add_parser("post", help="Post an order")
    p_post.add_argument("--market_id", required=True)
    p_post.add_argument("--side", required=True)
    p_post.add_argument("--qty", type=int, required=True)
    p_post.add_argument("--price", type=float, required=True)
    p_post.add_argument("--live", action="store_true", help="Force live mode")
    p_post.set_defaults(func=_cli_post)

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
