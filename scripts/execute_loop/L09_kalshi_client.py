"""L09_kalshi_client.py — Kalshi Exchange Client (PAPER MODE by default).

MODE GATING
-----------
  KALSHI_LIVE_ENABLED=1  AND  KALSHI_API_KEY  AND  KALSHI_API_KEY_ID  → LIVE
  Else → PAPER (default)

  Paper-vs-live mode delegated to L44_paper_mode.is_live_for_layer('kalshi');
  see L44 for the canonical list of env vars.

PAPER BEHAVIOUR
---------------
  Orderbook:   read data/exchange_seed/kalshi/<ticker>.json
               missing ticker → KeyError("unknown market_ticker: <ticker>")
  post_order:  append to data/ledger/paper_kalshi_orders.json;
               return {"order_id": "paper_kalshi_<12-hex>", "status": "filled"}
  Idempotency: same key twice → return cached response, ledger unchanged
  get_positions: aggregate paper ledger by (ticker, side); avg_price + PnL

PUBLIC API
----------
    get_orderbook(market_ticker)   -> dict
    get_positions()                -> list[KalshiPosition]
    post_order(market_ticker, side, qty, price, idempotency_key) -> dict
    cancel_order(order_id)         -> bool

CLI
---
    python L09_kalshi_client.py orderbook --ticker NBA-TEST
    python L09_kalshi_client.py positions
    python L09_kalshi_client.py post --ticker X --side yes --qty 10 --price 60 [--live]

Environment Variables
---------------------
    KALSHI_LIVE_ENABLED   Set to "1" to activate live (HTTP) mode; default paper.
    KALSHI_API_KEY        API key for live REST calls; required when KALSHI_LIVE_ENABLED=1.
    KALSHI_API_KEY_ID     API key ID for live REST calls; required when KALSHI_LIVE_ENABLED=1.
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
# Paths (module-level so tests can monkeypatch)
# ---------------------------------------------------------------------------
_SEED_DIR = PROJECT_DIR / "data" / "exchange_seed" / "kalshi"
_LEDGER_DIR = PROJECT_DIR / "data" / "ledger"
_PAPER_ORDERS_FILE = _LEDGER_DIR / "paper_kalshi_orders.json"

# ---------------------------------------------------------------------------
# REST constants (never called in paper mode)
# ---------------------------------------------------------------------------
_KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"
_EP_ORDERBOOK = "/markets/{ticker}/orderbook"
_EP_ORDERS = "/portfolio/orders"
_EP_ORDER_DELETE = "/portfolio/orders/{order_id}"

# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class KalshiQuote:
    market_ticker: str
    side: str        # "yes" | "no"
    price: int       # cents 1-99
    liquidity: int
    ts: str          # ISO-8601


@dataclass
class KalshiPosition:
    market_ticker: str
    side: str
    qty: int
    avg_price: float
    unrealized_pnl: float


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------

def _is_live_mode() -> bool:
    if _L44 is not None:
        return _L44.is_live_for_layer("kalshi")
    # fallback to inline env read (preserves backward compat if L44 absent)
    return os.environ.get("KALSHI_LIVE_ENABLED", "0").lower() in ("1", "true")


def _live_credentials_present() -> bool:
    return bool(
        os.environ.get("KALSHI_API_KEY", "").strip()
        and os.environ.get("KALSHI_API_KEY_ID", "").strip()
    )


def _check_live_permissions() -> None:
    """Raise PermissionError if LIVE requested but credentials absent."""
    if _is_live_mode() and not _live_credentials_present():
        raise PermissionError(
            "KALSHI_LIVE_ENABLED=1 but KALSHI_API_KEY / KALSHI_API_KEY_ID not set. "
            "Provide credentials or unset KALSHI_LIVE_ENABLED to use paper mode."
        )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_order(side: str, qty: int, price: int) -> None:
    if side not in {"yes", "no"}:
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
    if qty <= 0:
        raise ValueError(f"qty must be > 0, got {qty}")
    if price not in range(1, 100):
        raise ValueError(f"price must be 1-99 cents, got {price}")


# ---------------------------------------------------------------------------
# HTTP stub (raises immediately; never called in paper mode)
# ---------------------------------------------------------------------------

def _http_get(path: str, **params) -> dict:  # pragma: no cover
    raise RuntimeError(
        "_http_get called in paper mode — this is a programming error. "
        "Wire a real requests.Session for live mode."
    )


def _http_post(path: str, body: dict, idempotency_key: str | None = None) -> dict:  # pragma: no cover
    raise RuntimeError("_http_post called in paper mode.")


def _http_delete(path: str) -> bool:  # pragma: no cover
    raise RuntimeError("_http_delete called in paper mode.")


# ---------------------------------------------------------------------------
# Paper ledger helpers
# ---------------------------------------------------------------------------

def _load_paper_ledger() -> list[dict]:
    """Load paper orders from JSON ledger; return [] if missing."""
    if _PAPER_ORDERS_FILE.exists():
        with _PAPER_ORDERS_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return []


def _save_paper_ledger(orders: list[dict]) -> None:
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _PAPER_ORDERS_FILE.with_suffix(".tmp.json")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(orders, fh, indent=2)
    tmp.replace(_PAPER_ORDERS_FILE)


def _paper_mid_price(market_ticker: str) -> float:
    """Return mid-price from seed JSON; fall back to 50 if unavailable."""
    seed_path = _SEED_DIR / f"{market_ticker}.json"
    if not seed_path.exists():
        return 50.0
    with seed_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    yes_bids = data.get("yes_bids", [])
    yes_asks = data.get("yes_asks", [])
    if yes_bids and yes_asks:
        best_bid = yes_bids[0][0] if yes_bids else 50
        best_ask = yes_asks[0][0] if yes_asks else 50
        return (best_bid + best_ask) / 2.0
    return 50.0


# ---------------------------------------------------------------------------
# L07 soft-import for paper bet write-through
# ---------------------------------------------------------------------------

def _write_l07_bet(market_ticker: str, side: str, qty: int, price: int) -> None:
    """Soft-import L07 place_bet and record a paper BetRow for the fill."""
    try:
        import scripts.execute_loop.L07_pnl_ledger as L07  # type: ignore
    except Exception:
        log.debug("L07 import unavailable — skipping paper bet write-through")
        return

    try:
        # Approximate American odds from centavos price
        # p_implied = price / 100
        # American = -100 * p / (1 - p)  for p >= 0.5 else 100 * (1-p)/p
        p = price / 100.0
        if p <= 0 or p >= 1:
            american_odds = 0
        elif p >= 0.5:
            american_odds = int(round(-100.0 * p / (1.0 - p)))
        else:
            american_odds = int(round(100.0 * (1.0 - p) / p))

        stake = qty * (price / 100.0)

        row = L07.BetRow(
            book="kalshi",
            market=f"kalshi_{market_ticker}",
            player="",
            stat="binary",
            line=0.0,
            side=side,
            stake=stake,
            odds=american_odds,
            test_mode=True,
            status="OPEN",
        )
        L07.place_bet(row)
        log.debug("L07 write-through: market=%s side=%s stake=%.2f odds=%d",
                  market_ticker, side, stake, american_odds)
    except Exception as exc:  # never crash the caller
        log.warning("L07 write-through failed: %s", exc)


# ---------------------------------------------------------------------------
# Core public API — PAPER implementations
# ---------------------------------------------------------------------------

def get_orderbook(market_ticker: str) -> dict:
    """Return orderbook dict with yes_bids/yes_asks/no_bids/no_asks.

    Paper mode: reads data/exchange_seed/kalshi/<ticker>.json.
    Live mode:  GET /markets/{ticker}/orderbook.

    Raises
    ------
    KeyError if market_ticker seed file is absent (paper) or market unknown (live).
    PermissionError if live mode requested without credentials.
    """
    _check_live_permissions()

    if _is_live_mode():  # pragma: no cover
        raw = _http_get(_EP_ORDERBOOK.format(ticker=market_ticker))
        return raw

    # Paper: read seed JSON
    seed_path = _SEED_DIR / f"{market_ticker}.json"
    if not seed_path.exists():
        raise KeyError(f"unknown market_ticker: {market_ticker}")

    with seed_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    return {
        "yes_bids": data.get("yes_bids", []),
        "yes_asks": data.get("yes_asks", []),
        "no_bids": data.get("no_bids", []),
        "no_asks": data.get("no_asks", []),
    }


def get_positions() -> list[KalshiPosition]:
    """Aggregate paper ledger into per-(ticker, side) KalshiPosition objects.

    Live mode: GET /portfolio/positions (stub — not implemented here).
    """
    _check_live_permissions()

    if _is_live_mode():  # pragma: no cover
        raise NotImplementedError("Live get_positions not yet wired; implement HTTP layer.")

    orders = _load_paper_ledger()
    if not orders:
        return []

    # Group by (ticker, side)
    groups: dict[tuple[str, str], list[dict]] = {}
    for o in orders:
        key = (o["market_ticker"], o["side"])
        groups.setdefault(key, []).append(o)

    positions: list[KalshiPosition] = []
    for (ticker, side), fills in groups.items():
        total_qty = sum(f["qty"] for f in fills)
        if total_qty <= 0:
            continue
        avg_price = sum(f["qty"] * f["price"] for f in fills) / total_qty
        mid = _paper_mid_price(ticker)
        # PnL per contract: (mid - avg_price) for yes, (100-mid - (100-avg_price)) for no
        if side == "yes":
            unrealized_pnl = (mid - avg_price) * total_qty
        else:
            unrealized_pnl = ((100.0 - mid) - (100.0 - avg_price)) * total_qty

        positions.append(
            KalshiPosition(
                market_ticker=ticker,
                side=side,
                qty=total_qty,
                avg_price=avg_price,
                unrealized_pnl=unrealized_pnl,
            )
        )

    return positions


def post_order(
    market_ticker: str,
    side: str,
    qty: int,
    price: int,
    idempotency_key: str | None = None,
) -> dict:
    """Place an order.

    Paper mode: appends to data/ledger/paper_kalshi_orders.json.
                Returns {"order_id": "paper_kalshi_<12hex>", "status": "filled"}.
    Live mode:  POST /portfolio/orders.

    Raises
    ------
    ValueError for invalid side / qty / price.
    PermissionError if live requested without credentials.
    """
    _check_live_permissions()
    _validate_order(side, qty, price)

    if _is_live_mode():  # pragma: no cover
        body = {
            "ticker": market_ticker,
            "side": side,
            "count": qty,
            "yes_price" if side == "yes" else "no_price": price,
            "type": "limit",
            "action": "buy",
        }
        headers: dict = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return _http_post(_EP_ORDERS, body, idempotency_key=idempotency_key)

    # Paper mode
    orders = _load_paper_ledger()

    # Idempotency check
    if idempotency_key:
        for existing in orders:
            if existing.get("idempotency_key") == idempotency_key:
                log.debug("post_order: idempotency hit key=%s", idempotency_key)
                return {
                    "order_id": existing["order_id"],
                    "status": existing["status"],
                }

    order_id = f"paper_kalshi_{uuid4().hex[:12]}"
    ts = datetime.now(timezone.utc).isoformat()

    record = {
        "order_id": order_id,
        "market_ticker": market_ticker,
        "side": side,
        "qty": qty,
        "price": price,
        "status": "filled",
        "placed_at": ts,
        "idempotency_key": idempotency_key,
    }
    orders.append(record)
    _save_paper_ledger(orders)

    log.info(
        "post_order [PAPER]: ticker=%s side=%s qty=%d price=%d order_id=%s",
        market_ticker, side, qty, price, order_id,
    )

    # L07 write-through (soft)
    _write_l07_bet(market_ticker, side, qty, price)

    return {"order_id": order_id, "status": "filled"}


def cancel_order(order_id: str) -> bool:
    """Cancel an open order.

    Paper mode: mark matching order as 'cancelled' in ledger.
                Returns True if found, False if not found.
    Live mode:  DELETE /portfolio/orders/{order_id}.
    """
    _check_live_permissions()

    if _is_live_mode():  # pragma: no cover
        return _http_delete(_EP_ORDER_DELETE.format(order_id=order_id))

    orders = _load_paper_ledger()
    found = False
    for o in orders:
        if o["order_id"] == order_id:
            o["status"] = "cancelled"
            found = True
            log.info("cancel_order [PAPER]: order_id=%s marked cancelled", order_id)
            break

    if found:
        _save_paper_ledger(orders)
    else:
        log.warning("cancel_order [PAPER]: order_id=%s not found", order_id)

    return found


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="L09_kalshi_client",
        description="Kalshi exchange client (paper/live).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ob = sub.add_parser("orderbook", help="Fetch orderbook for a market.")
    ob.add_argument("--ticker", required=True, help="Market ticker, e.g. NBA-TEST")

    sub.add_parser("positions", help="Show open positions (paper ledger).")

    po = sub.add_parser("post", help="Post a limit order.")
    po.add_argument("--ticker", required=True)
    po.add_argument("--side", required=True, choices=["yes", "no"])
    po.add_argument("--qty", type=int, required=True)
    po.add_argument("--price", type=int, required=True, help="Cents 1-99")
    po.add_argument("--idempotency-key", default=None)
    po.add_argument("--live", action="store_true", help="Require live mode (sets env flag)")

    return p


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "orderbook":
        ob = get_orderbook(args.ticker)
        print(json.dumps(ob, indent=2))

    elif args.cmd == "positions":
        positions = get_positions()
        if not positions:
            print("No open positions.")
        for pos in positions:
            print(json.dumps(asdict(pos), indent=2))

    elif args.cmd == "post":
        if args.live:
            os.environ["KALSHI_LIVE_ENABLED"] = "1"
        result = post_order(
            market_ticker=args.ticker,
            side=args.side,
            qty=args.qty,
            price=args.price,
            idempotency_key=args.idempotency_key,
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
