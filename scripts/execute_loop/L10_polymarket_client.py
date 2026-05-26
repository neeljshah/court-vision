"""L10_polymarket_client.py — Polymarket CLOB client (PAPER MODE default).

Reads NBA prediction markets from Polymarket's Gamma + CLOB APIs.
Default mode is PAPER — never touches private keys or real funds.
LIVE mode requires explicit env vars AND --live flag from caller.

Paper-vs-live mode delegated to L44_paper_mode.is_live_for_layer('polymarket');
see L44 for the canonical list of env vars.

Public API
----------
    PolyMarket           dataclass
    PolyOrderbook        dataclass
    PolyPosition         dataclass
    find_nba_markets(date)          -> list[PolyMarket]
    get_orderbook(condition_id)     -> PolyOrderbook | None
    get_positions(wallet)           -> list[PolyPosition]
    post_order(...)                 -> dict
    cancel_order(order_id)          -> bool

CLI
---
    python L10_polymarket_client.py markets [--date YYYY-MM-DD]
    python L10_polymarket_client.py orderbook --condition_id X
    python L10_polymarket_client.py post --condition_id X --outcome yes --qty 100 --price 0.55 [--live]
    python L10_polymarket_client.py cancel --order_id X

Environment Variables:
    POLYMARKET_LIVE_ENABLED  Set to "1" to activate live (HTTP) mode; default paper.
                             Canonical flag read via L44_paper_mode.is_live_for_layer('polymarket').
    POLYMARKET_PRIVATE_KEY   EIP-712 signing key for the funded Polymarket wallet.
                             Required to enable live order submission and cancellation.
                             Default: absent (paper mode only; live calls raise PermissionError).
    POLYMARKET_USDC_FUNDED   Confirmation flag that the wallet holds sufficient USDC.
                             Must be set to exactly "true" (lowercase) to permit live trading.
                             Default: absent / any other value (live calls raise PermissionError).

Paper vs Live Mode:
    Default is PAPER.  All write operations (post_order, cancel_order) record to a local
    JSON ledger at data/ledger/paper_polymarket_orders.json and never contact the CLOB.
    Live mode is gated by _is_live_permitted(): BOTH POLYMARKET_PRIVATE_KEY (non-empty)
    AND POLYMARKET_USDC_FUNDED == "true" must be set, AND the caller must explicitly pass
    live=True to post_order() / cancel_order().  Missing either env var raises PermissionError
    before any network call is attempted.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# L44 soft-import — delegates paper/live mode to the canonical library
# ---------------------------------------------------------------------------

try:
    from scripts.execute_loop import L44_paper_mode as _L44
except Exception:
    _L44 = None


def _is_live_mode() -> bool:
    if _L44 is not None:
        return _L44.is_live_for_layer("polymarket")
    # fallback to inline env read (preserves backward compat if L44 absent)
    return os.environ.get("POLYMARKET_LIVE_ENABLED", "0").lower() in ("1", "true")


# ---------------------------------------------------------------------------
# Repo-root resolution
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent  # scripts/execute_loop -> scripts -> repo root

_SEED_DIR = _REPO / "data" / "exchange_seed" / "polymarket"
_OB_DIR = _SEED_DIR / "orderbooks"
_LEDGER_DIR = _REPO / "data" / "ledger"
_LEDGER_FILE = _LEDGER_DIR / "paper_polymarket_orders.json"

# ---------------------------------------------------------------------------
# Live API endpoints (stubs — never called in PAPER mode)
# ---------------------------------------------------------------------------

_GAMMA_URL = "https://gamma-api.polymarket.com/query"
_CLOB_BOOK_URL = "https://clob.polymarket.com/book"
_CLOB_ORDER_URL = "https://clob.polymarket.com/order"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PolyMarket:
    """A single Polymarket prediction market."""

    condition_id: str
    question: str
    slug: str
    end_date: str
    outcome_prices: list[dict]  # [{"outcome": str, "price": float}]
    volume_24h: float


@dataclass
class PolyOrderbook:
    """Level-2 orderbook for one Polymarket market."""

    condition_id: str
    asks: list[dict]   # [{"price": float, "size": float}], sorted asc by price
    bids: list[dict]   # [{"price": float, "size": float}], sorted desc by price


@dataclass
class PolyPosition:
    """Aggregated paper or live position for one (condition_id, outcome) pair."""

    condition_id: str
    outcome: str
    qty: float
    avg_price: float
    unrealized_pnl: float


# ---------------------------------------------------------------------------
# Mode gating helpers
# ---------------------------------------------------------------------------


def _is_live_permitted() -> bool:
    """Return True only when BOTH env vars are set correctly."""
    pk = os.environ.get("POLYMARKET_PRIVATE_KEY", "")
    funded = os.environ.get("POLYMARKET_USDC_FUNDED", "")
    return bool(pk) and funded == "true"


def _check_live_or_raise() -> None:
    """Raise PermissionError with a descriptive message if live mode is blocked."""
    pk = os.environ.get("POLYMARKET_PRIVATE_KEY", "")
    if not pk:
        raise PermissionError("Live mode requires POLYMARKET_PRIVATE_KEY")
    funded = os.environ.get("POLYMARKET_USDC_FUNDED", "")
    if funded != "true":
        raise PermissionError("Wallet not confirmed funded — set POLYMARKET_USDC_FUNDED=true")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_order(price_usdc: float, qty: float) -> None:
    if price_usdc <= 0 or price_usdc >= 1.0:
        raise ValueError("Polymarket price must be in (0, 1)")
    if qty <= 0:
        raise ValueError(f"qty must be > 0, got {qty}")


# ---------------------------------------------------------------------------
# NBA market detection
# ---------------------------------------------------------------------------

_NBA_SLUG_RE = re.compile(r"(nba|basketball)", re.I)


def _is_nba_market(slug: str) -> bool:
    return bool(_NBA_SLUG_RE.search(slug))


# ---------------------------------------------------------------------------
# Ledger helpers (atomic writes via .tmp + os.replace)
# ---------------------------------------------------------------------------


def _read_ledger() -> dict:
    """Read existing ledger or return empty structure."""
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if not _LEDGER_FILE.exists():
        return {"orders": []}
    try:
        return json.loads(_LEDGER_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Ledger read error — treating as empty: %s", exc)
        return {"orders": []}


def _write_ledger(data: dict) -> None:
    """Atomically write ledger using a temp file + os.replace."""
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _LEDGER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, _LEDGER_FILE)


def _find_idempotent(ledger: dict, key: str) -> Optional[dict]:
    """Return cached order dict if idempotency_key already exists in ledger."""
    for order in ledger.get("orders", []):
        if order.get("idempotency_key") == key:
            return order
    return None


# ---------------------------------------------------------------------------
# Seed file helpers
# ---------------------------------------------------------------------------


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_seed_markets(date: str) -> list[dict]:
    path = _SEED_DIR / f"markets_{date}.json"
    if not path.exists():
        log.debug("Seed markets file not found: %s", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw.get("data", [])
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load seed markets %s: %s", path, exc)
        return []


def _load_seed_orderbook(condition_id: str) -> Optional[dict]:
    path = _OB_DIR / f"{condition_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load orderbook %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Orderbook mid-price helper (used for unrealized PnL)
# ---------------------------------------------------------------------------


def _orderbook_mid(condition_id: str) -> Optional[float]:
    raw = _load_seed_orderbook(condition_id)
    if raw is None:
        return None
    asks = raw.get("asks", [])
    bids = raw.get("bids", [])
    best_ask = min((a["price"] for a in asks), default=None)
    best_bid = max((b["price"] for b in bids), default=None)
    if best_ask is not None and best_bid is not None:
        return (best_ask + best_bid) / 2.0
    return best_ask or best_bid


# ---------------------------------------------------------------------------
# Public API — PAPER implementations
# ---------------------------------------------------------------------------


def find_nba_markets(date: Optional[str] = None) -> list[PolyMarket]:
    """Return NBA prediction markets from the seed file for *date* (default today UTC).

    In live mode this would query the Gamma GraphQL endpoint and filter by slug.
    """
    effective_date = date or _today_utc()
    raw_markets = _load_seed_markets(effective_date)
    result: list[PolyMarket] = []
    for m in raw_markets:
        slug = m.get("slug", "")
        if not _is_nba_market(slug):
            log.debug("Skipping non-NBA slug: %s", slug)
            continue
        result.append(PolyMarket(
            condition_id=m["condition_id"],
            question=m.get("question", ""),
            slug=slug,
            end_date=m.get("end_date", ""),
            outcome_prices=m.get("outcome_prices", []),
            volume_24h=float(m.get("volume_24h", 0.0)),
        ))
    log.info("find_nba_markets(%s) → %d market(s)", effective_date, len(result))
    return result


def get_orderbook(condition_id: str) -> Optional[PolyOrderbook]:
    """Return the L2 orderbook for *condition_id* from seed, or None if missing.

    In live mode this would call GET /book?market=<condition_id> on the CLOB.
    Asks are sorted ascending by price; bids descending by price.
    """
    raw = _load_seed_orderbook(condition_id)
    if raw is None:
        log.debug("No orderbook seed for %s", condition_id)
        return None
    asks = sorted(raw.get("asks", []), key=lambda x: x["price"])
    bids = sorted(raw.get("bids", []), key=lambda x: x["price"], reverse=True)
    return PolyOrderbook(condition_id=condition_id, asks=asks, bids=bids)


def get_positions(wallet: Optional[str] = None) -> list[PolyPosition]:
    """Aggregate open paper positions from the ledger.

    Groups filled BUY orders by (condition_id, outcome); uses orderbook mid
    to estimate unrealized PnL.  SELL orders reduce qty.
    """
    ledger = _read_ledger()
    # key → {"qty": float, "cost": float}
    agg: dict[tuple[str, str], dict] = {}
    for order in ledger.get("orders", []):
        if order.get("status") != "filled":
            continue
        key = (order["condition_id"], order["outcome"])
        side = order.get("side", "buy").lower()
        qty = float(order["qty"])
        price = float(order["price_usdc"])
        if key not in agg:
            agg[key] = {"qty": 0.0, "cost": 0.0}
        if side == "buy":
            agg[key]["qty"] += qty
            agg[key]["cost"] += qty * price
        elif side == "sell":
            agg[key]["qty"] -= qty
            agg[key]["cost"] -= qty * price

    positions: list[PolyPosition] = []
    for (cid, outcome), bucket in agg.items():
        net_qty = bucket["qty"]
        if net_qty <= 0:
            continue
        avg_price = bucket["cost"] / net_qty if net_qty > 0 else 0.0
        mid = _orderbook_mid(cid)
        unrealized = (mid - avg_price) * net_qty if mid is not None else 0.0
        positions.append(PolyPosition(
            condition_id=cid,
            outcome=outcome,
            qty=net_qty,
            avg_price=avg_price,
            unrealized_pnl=unrealized,
        ))
    return positions


def post_order(
    condition_id: str,
    outcome: str,
    side: str,
    qty: float,
    price_usdc: float,
    idempotency_key: Optional[str] = None,
    *,
    live: bool = False,
) -> dict:
    """Submit a paper order; in live mode signs EIP-712 and hits the CLOB.

    Parameters
    ----------
    condition_id:     Polymarket condition identifier.
    outcome:          "yes" | "no" (or market-specific outcome string).
    side:             "buy" | "sell".
    qty:              Number of shares (USDC notional = qty * price_usdc).
    price_usdc:       Limit price in USDC per share — must be in (0, 1).
    idempotency_key:  If provided, repeated calls with the same key return
                      the cached result without creating a duplicate order.
    live:             Caller must explicitly pass True AND env vars must be set.
    """
    _validate_order(price_usdc, qty)

    if live:
        _check_live_or_raise()
        # LIVE stub — EIP-712 signing omitted; would call _CLOB_ORDER_URL
        raise NotImplementedError("Live order submission not implemented in this stub")

    # --- PAPER path ---
    ledger = _read_ledger()

    if idempotency_key is not None:
        cached = _find_idempotent(ledger, idempotency_key)
        if cached is not None:
            log.debug("Idempotency hit for key=%s → %s", idempotency_key, cached["order_id"])
            return {"order_id": cached["order_id"], "status": cached["status"]}

    order_id = f"poly_paper_{uuid.uuid4().hex[:12]}"
    ts = datetime.now(timezone.utc).isoformat()
    record: dict = {
        "order_id": order_id,
        "ts": ts,
        "condition_id": condition_id,
        "outcome": outcome,
        "side": side.lower(),
        "qty": qty,
        "price_usdc": price_usdc,
        "status": "filled",
        "idempotency_key": idempotency_key,
    }
    ledger["orders"].append(record)
    _write_ledger(ledger)
    log.info("Paper order placed: %s qty=%.2f price=%.4f", order_id, qty, price_usdc)
    return {"order_id": order_id, "status": "filled"}


def cancel_order(order_id: str, *, live: bool = False) -> bool:
    """Cancel an open order by ID.  In paper mode marks it cancelled in the ledger.

    Returns True if the order was found and cancelled, False otherwise.
    """
    if live:
        _check_live_or_raise()
        raise NotImplementedError("Live cancel not implemented in this stub")

    ledger = _read_ledger()
    found = False
    for order in ledger.get("orders", []):
        if order["order_id"] == order_id:
            order["status"] = "cancelled"
            found = True
            log.info("Paper order cancelled: %s", order_id)
            break
    if found:
        _write_ledger(ledger)
    else:
        log.warning("cancel_order: order_id not found: %s", order_id)
    return found


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_markets(args: argparse.Namespace) -> None:
    markets = find_nba_markets(args.date)
    if not markets:
        print(f"No NBA markets found for date={args.date or _today_utc()}")
        return
    for m in markets:
        prices_str = ", ".join(
            f"{p['outcome']}={p['price']:.3f}" for p in m.outcome_prices
        )
        print(f"[{m.condition_id}] {m.question}  |  {prices_str}  |  vol24h={m.volume_24h:.0f}")


def _cli_orderbook(args: argparse.Namespace) -> None:
    ob = get_orderbook(args.condition_id)
    if ob is None:
        print(f"No orderbook for condition_id={args.condition_id}")
        return
    print(f"Orderbook: {ob.condition_id}")
    print(f"  Asks: {ob.asks}")
    print(f"  Bids: {ob.bids}")


def _cli_post(args: argparse.Namespace) -> None:
    result = post_order(
        condition_id=args.condition_id,
        outcome=args.outcome,
        side=args.side,
        qty=args.qty,
        price_usdc=args.price,
        live=args.live,
    )
    print(json.dumps(result, indent=2))


def _cli_cancel(args: argparse.Namespace) -> None:
    ok = cancel_order(args.order_id, live=getattr(args, "live", False))
    print("cancelled" if ok else "not found")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="L10 Polymarket client (paper mode default)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # markets
    p_markets = sub.add_parser("markets", help="List NBA markets")
    p_markets.add_argument("--date", default=None, help="YYYY-MM-DD (default today UTC)")
    p_markets.set_defaults(func=_cli_markets)

    # orderbook
    p_ob = sub.add_parser("orderbook", help="Show orderbook for a market")
    p_ob.add_argument("--condition_id", required=True)
    p_ob.set_defaults(func=_cli_orderbook)

    # post
    p_post = sub.add_parser("post", help="Submit a paper order")
    p_post.add_argument("--condition_id", required=True)
    p_post.add_argument("--outcome", required=True)
    p_post.add_argument("--side", default="buy", choices=["buy", "sell"])
    p_post.add_argument("--qty", type=float, required=True)
    p_post.add_argument("--price", type=float, required=True)
    p_post.add_argument("--live", action="store_true", default=False)
    p_post.set_defaults(func=_cli_post)

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel a paper order")
    p_cancel.add_argument("--order_id", required=True)
    p_cancel.set_defaults(func=_cli_cancel)

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
