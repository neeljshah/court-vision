"""L12_prophet_client.py — Prophet Exchange Client (PAPER / LIVE).

Prophet is a sports-prediction exchange where player props trade as
decimal-priced contracts (1.01 – 100.0 inclusive exclusive of bounds).

Mode gating
-----------
- PROPHET_LIVE_ENABLED=1  AND  PROPHET_API_KEY set  → LIVE (HTTP calls)
- Default (env vars absent / empty)                  → PAPER (seed JSON files)
- PROPHET_LIVE_ENABLED=1 without API key             → PermissionError on any call

Paper-vs-live mode delegated to L44_paper_mode.is_live_for_layer('prophet');
see L44 for the canonical list of env vars.

Public API
----------
    ProphetQuote     dataclass (frozen)
    ProphetPosition  dataclass
    find_nba_prop_markets(date)                          -> list[dict]
    get_orderbook(market_id)                             -> dict {bids, asks, ts}
    get_positions()                                      -> list[ProphetPosition]
    post_order(market_id, side, qty, price_decimal,
               idempotency_key)                          -> dict
    cancel_order(order_id)                               -> bool

CLI
---
    python L12_prophet_client.py markets [--date YYYY-MM-DD]
    python L12_prophet_client.py orderbook --market_id nba_lebron_pts_25_5
    python L12_prophet_client.py positions
    python L12_prophet_client.py post --market_id X --side over --qty 10
                                      --price_decimal 1.90 [--live]

Environment Variables
---------------------
    PROPHET_LIVE_ENABLED  — set to "1" to activate live (HTTP) mode; default paper.
                            Canonical flag read via L44_paper_mode.is_live_for_layer('prophet').
    PROPHET_API_KEY       — bearer token for live REST calls; required when
                            PROPHET_LIVE_ENABLED=1.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
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
# Configurable path roots (overridable in tests via monkeypatch)
# ---------------------------------------------------------------------------
_SEED_DIR: Path = PROJECT_DIR / "data" / "exchange_seed" / "prophet"
_LEDGER_DIR: Path = PROJECT_DIR / "data" / "ledger"
_PAPER_ORDERS_FILE_NAME = "paper_prophet_orders.json"

_LIVE_REST_BASE = "https://api.prophetexchange.com/v1"

# ---------------------------------------------------------------------------
# In-process idempotency cache (capped at 512 keys)
# ---------------------------------------------------------------------------
_IDEMPOTENCY_CACHE: dict[str, dict] = {}
_IDEMPOTENCY_MAX = 512

# ---------------------------------------------------------------------------
# Valid stat set
# ---------------------------------------------------------------------------
_VALID_STATS = {"PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV"}
_VALID_SIDES = {"over", "under"}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProphetQuote:
    market_id: str
    market_type: str      # "player_prop"
    player: str
    stat: str             # PTS | REB | AST | FG3M | STL | BLK | TOV
    line: float
    side: str             # "over" | "under"
    price_decimal: float  # 1.01 – 100.0 exclusive
    liquidity: float
    ts: float


@dataclass
class ProphetPosition:
    market_id: str
    side: str
    qty: float
    avg_price: float      # decimal VWAP
    unrealized_pnl: float


# ---------------------------------------------------------------------------
# Mode detection helpers
# ---------------------------------------------------------------------------

def _is_live_enabled() -> bool:
    if _L44 is not None:
        return _L44.is_live_for_layer("prophet")
    # fallback to inline env read (preserves backward compat if L44 absent)
    return os.environ.get("PROPHET_LIVE_ENABLED", "0").lower() in ("1", "true")


def _api_key() -> Optional[str]:
    return os.environ.get("PROPHET_API_KEY", "").strip() or None


def _check_live_auth() -> None:
    """Raise PermissionError if LIVE_ENABLED but no API key."""
    if _is_live_enabled() and not _api_key():
        raise PermissionError(
            "PROPHET_LIVE_ENABLED=1 but PROPHET_API_KEY is not set. "
            "Set the key or unset PROPHET_LIVE_ENABLED to use paper mode."
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

def _paper_markets_path(date: str) -> Path:
    return _seed_dir() / f"markets_{date}.json"


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


def _save_paper_orders(orders: list[dict]) -> None:
    p = _paper_orders_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp.json")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(orders, fh, indent=2)
    tmp.replace(p)


# ---------------------------------------------------------------------------
# LIVE helpers (lazy-import requests; never called in paper)
# ---------------------------------------------------------------------------

def _live_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _live_get(path: str) -> dict:
    import requests  # lazy — never imported in paper
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

def _validate_order(market_id: str, side: str, qty: float, price_decimal: float) -> None:
    if not market_id:
        raise ValueError("market_id must be a non-empty string.")
    if side not in _VALID_SIDES:
        raise ValueError(f"side must be one of {_VALID_SIDES}; got {side!r}")
    if qty <= 0:
        raise ValueError(f"qty must be > 0; got {qty}")
    if price_decimal <= 1.0 or price_decimal > 100.0:
        raise ValueError(
            f"price_decimal must be in (1.0, 100.0] exclusive of lower bound; got {price_decimal}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_nba_prop_markets(date: Optional[str] = None) -> list[dict]:
    """Return NBA player-prop markets for *date* (YYYY-MM-DD; default today UTC).

    Paper: reads data/exchange_seed/prophet/markets_<date>.json.
    Live:  GET /v1/markets?sport=nba&type=player_prop&date=<date>
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    mode = _mode()
    log.debug("[%s] find_nba_prop_markets date=%s", mode, date)

    if mode == "paper":
        path = _paper_markets_path(date)
        markets = _read_json(path)
        if not isinstance(markets, list):
            raise ValueError(f"Expected list in {path}; got {type(markets)}")
        return markets

    # LIVE
    data = _live_get(f"/markets?sport=nba&type=player_prop&date={date}")
    return data.get("markets", data) if isinstance(data, dict) else data


def get_orderbook(market_id: str) -> dict:
    """Return orderbook for *market_id* as {bids, asks, ts}.

    Paper: reads data/exchange_seed/prophet/<market_id>.json; missing → KeyError.
    Live:  GET /v1/markets/<market_id>/orderbook
    """
    if not market_id:
        raise ValueError("market_id must be a non-empty string.")

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


def get_positions() -> list[ProphetPosition]:
    """Return current open positions.

    Paper:
        Aggregates paper ledger by (market_id, side).
        avg_price = VWAP of fill prices (decimal).
        unrealized_pnl = (orderbook mid - avg_price) * qty.
        If orderbook file missing, unrealized_pnl defaults to 0.0.

    Live:
        GET /v1/positions
    """
    mode = _mode()
    log.debug("[%s] get_positions", mode)

    if mode == "paper":
        orders = _load_paper_orders()
        # Aggregate: {(market_id, side): {"qty": float, "cost": float}}
        agg: dict[tuple, dict] = {}
        for o in orders:
            key = (o["market_id"], o["side"])
            if key not in agg:
                agg[key] = {"qty": 0.0, "cost": 0.0}
            agg[key]["qty"] += o["qty"]
            agg[key]["cost"] += o["qty"] * o["price_decimal"]

        positions: list[ProphetPosition] = []
        for (market_id, side), bucket in agg.items():
            total_qty = bucket["qty"]
            avg_price = bucket["cost"] / total_qty if total_qty else 0.0
            # Attempt mid from orderbook seed
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
            positions.append(ProphetPosition(
                market_id=market_id,
                side=side,
                qty=total_qty,
                avg_price=round(avg_price, 6),
                unrealized_pnl=round(pnl, 6),
            ))
        return positions

    # LIVE
    data = _live_get("/positions")
    raw = data.get("positions", data) if isinstance(data, dict) else data
    return [
        ProphetPosition(
            market_id=p["market_id"],
            side=p["side"],
            qty=float(p["qty"]),
            avg_price=float(p["avg_price"]),
            unrealized_pnl=float(p.get("unrealized_pnl", 0.0)),
        )
        for p in raw
    ]


def post_order(
    market_id: str,
    side: str,
    qty: float,
    price_decimal: float,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Submit an order.

    Validation (both modes):
        price_decimal <= 1.0 or > 100.0 → ValueError
        qty <= 0                          → ValueError
        side not in {"over","under"}      → ValueError
        market_id empty/None              → ValueError

    Paper:
        Returns {"order_id": "paper-<12hex>", "status": "filled"}.
        Appends the order record to data/ledger/paper_prophet_orders.json.
        Idempotency: if *idempotency_key* already seen this process,
                     returns cached result without ledger duplication.

    Live:
        POST /v1/orders  with Idempotency-Key header.
    """
    _validate_order(market_id, side, qty, price_decimal)

    # In-process idempotency check (both modes share the cache)
    if idempotency_key and idempotency_key in _IDEMPOTENCY_CACHE:
        log.debug("Idempotency hit for key=%s", idempotency_key)
        return _IDEMPOTENCY_CACHE[idempotency_key]

    mode = _mode()
    log.debug(
        "[%s] post_order market=%s side=%s qty=%s price=%.4f ikey=%s",
        mode, market_id, side, qty, price_decimal, idempotency_key,
    )

    if mode == "paper":
        order_id = f"paper-{uuid4().hex[:12]}"
        result: dict = {"order_id": order_id, "status": "filled"}
        record = {
            "order_id": order_id,
            "market_id": market_id,
            "side": side,
            "qty": qty,
            "price_decimal": price_decimal,
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
            "price_decimal": price_decimal,
        }
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        result = _live_post("/orders", payload)

    # Cache for in-process idempotency
    if idempotency_key:
        if len(_IDEMPOTENCY_CACHE) >= _IDEMPOTENCY_MAX:
            oldest = next(iter(_IDEMPOTENCY_CACHE))
            del _IDEMPOTENCY_CACHE[oldest]
        _IDEMPOTENCY_CACHE[idempotency_key] = result

    return result


def cancel_order(order_id: str) -> bool:
    """Cancel an open order by *order_id*.

    Paper: always returns True (no open orders to manage in paper mode).
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_markets(args: argparse.Namespace) -> None:
    markets = find_nba_prop_markets(args.date)
    print(json.dumps(markets, indent=2))


def _cli_orderbook(args: argparse.Namespace) -> None:
    book = get_orderbook(args.market_id)
    print(json.dumps(book, indent=2))


def _cli_positions(args: argparse.Namespace) -> None:
    positions = get_positions()
    print(json.dumps([asdict(p) for p in positions], indent=2))


def _cli_post(args: argparse.Namespace) -> None:
    if args.live:
        os.environ["PROPHET_LIVE_ENABLED"] = "1"
    result = post_order(
        market_id=args.market_id,
        side=args.side,
        qty=args.qty,
        price_decimal=args.price_decimal,
    )
    print(json.dumps(result, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prophet exchange client (paper/live)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # markets
    p_markets = sub.add_parser("markets", help="List NBA prop markets")
    p_markets.add_argument("--date", default=None, help="YYYY-MM-DD (default today UTC)")
    p_markets.set_defaults(func=_cli_markets)

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
    p_post.add_argument("--side", required=True, choices=list(_VALID_SIDES))
    p_post.add_argument("--qty", type=float, required=True)
    p_post.add_argument("--price_decimal", type=float, required=True)
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
