"""L14_order_manager.py — Order Manager (execute_loop layer 14).

Tracks live orders across Kalshi / Polymarket / SportTrade, detects fills,
triggers repricing when model probability drifts, and cancels stale orders.

Storage: data/ledger/open_orders.json   (list of OrderState dicts)
         Written atomically via .tmp + os.replace

Public API
----------
    track_order(order_id, exchange, market_id, side, qty, price, model_p) -> OrderState
    get_open_orders() -> list[OrderState]
    update_from_exchange_fills() -> int
    check_for_reprice(model_predictions: dict) -> list[OrderState]
    cancel_stale(max_age_seconds: int = 1800) -> int
    reprice_order(order: OrderState, new_price: int) -> bool

CLI
---
    python L14_order_manager.py list
    python L14_order_manager.py update
    python L14_order_manager.py reprice --order-id X --new-price 60
    python L14_order_manager.py cancel-stale [--max-age-sec 1800]

Paper vs Live Mode (MODE GATING)
---------------------------------
This module is paper/live-mode-agnostic. It composes lower layers (L9-L12)
which control paper-vs-live behaviour individually. This module makes no
live API calls of its own — order tracking, fill detection, repricing, and
cancellation all delegate to the exchange clients in L9-L12, which each
carry their own paper/live gate.

Live mode for downstream calls is enabled only when the per-exchange env var
(e.g. KALSHI_LIVE_ENABLED=1) is set on the underlying client; this module
defers to those defaults.

Environment Variables
---------------------
None. This module reads no environment variables directly. All paper/live
gating is delegated to the L9-L12 exchange clients it composes.

Event Publication (L46 EventBus)
---------------------------------
L14 publishes two event types through the L46 EventBus singleton so that
downstream layers (L7 ledger, L22 alerts) can subscribe without L14 needing
direct knowledge of them.  L46 is soft-imported; if unavailable, all
existing direct-call paths continue to function unchanged.

    "fill.received"  — emitted on every successful _apply_fill call
        payload keys: order_id, exchange, market_id, side,
                      matched_qty, qty_filled_now, status

    "order.filled"   — emitted when an order transitions to FILLED status
                       (qty_filled >= qty); fired once per fill event,
                       immediately after "fill.received"
        payload keys: order_id, exchange, market_id, side,
                      qty_filled, qty, price, model_p
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
_LEDGER_DIR = _PROJECT_DIR / "data" / "ledger"
_ORDERS_FILE = _LEDGER_DIR / "open_orders.json"

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exchange registry
# ---------------------------------------------------------------------------
ALL_EXCHANGES: Tuple[str, ...] = ("kalshi", "polymarket", "sporttrade", "prophet")
_VALID_EXCHANGES = {"kalshi", "polymarket", "sporttrade", "prophet"}

# ---------------------------------------------------------------------------
# NormalizedFill dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NormalizedFill:
    exchange: str
    market_id: str
    side: str          # always lowercase
    qty: float
    exchange_order_id: str


# ---------------------------------------------------------------------------
# OrderState dataclass
# ---------------------------------------------------------------------------

@dataclass
class OrderState:
    order_id: str
    exchange: str           # kalshi|polymarket|sporttrade
    market_id: str
    side: str
    qty: int
    qty_filled: int
    price: int              # cents 1-99
    status: str             # OPEN|PARTIAL|FILLED|CANCELLED|REJECTED
    model_p: float          # original model probability 0-1
    current_model_p: float  # latest model probability (updated by check_for_reprice callers)
    last_repriced_at: float # unix ts (0.0 if never repriced)
    placed_at: float        # unix ts


# ---------------------------------------------------------------------------
# In-memory state (module-level; tests can replace these directly)
# ---------------------------------------------------------------------------
_open_orders: List[OrderState] = []
_processed_fills: Dict[str, int] = {}         # order_id -> last known qty_filled (idempotency)
_processed_fills_by_oid: Dict[str, float] = {}  # exchange_order_id -> cumulative qty applied

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _ensure_ledger_dir() -> None:
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)


def _load_orders() -> List[OrderState]:
    """Load open_orders.json from disk. Returns [] if missing or corrupt."""
    if not _ORDERS_FILE.exists():
        return []
    try:
        raw = json.loads(_ORDERS_FILE.read_text(encoding="utf-8"))
        return [OrderState(**d) for d in raw]
    except Exception as exc:
        log.warning("L14: failed to load %s — %s; starting empty", _ORDERS_FILE, exc)
        return []


def _save_orders(orders: List[OrderState]) -> None:
    """Atomically write orders list to disk."""
    _ensure_ledger_dir()
    tmp = _ORDERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(o) for o in orders], indent=2), encoding="utf-8")
    os.replace(str(tmp), str(_ORDERS_FILE))


def _init_from_disk() -> None:
    """Populate module-level _open_orders from disk on first use."""
    global _open_orders
    if not _open_orders:
        _open_orders = _load_orders()


# ---------------------------------------------------------------------------
# Soft-import exchange clients
# ---------------------------------------------------------------------------

def _get_exchange_client(exchange: str):
    """Return exchange client module or None on import failure."""
    module_map = {
        "kalshi":      "L09_kalshi_client",
        "polymarket":  "L10_polymarket_client",
        "sporttrade":  "L11_sporttrade_client",
        "prophet":     "L12_prophet_client",
    }
    mod_name = module_map.get(exchange)
    if mod_name is None:
        log.warning("L14: unknown exchange %r — no client available", exchange)
        return None
    # Allow sys.modules injection for testing
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    try:
        import importlib
        return importlib.import_module(mod_name)
    except ImportError:
        log.warning("L14: exchange client %r not available (ImportError) — skipping", mod_name)
        return None


def _get_l07():
    """Soft-import L07 pnl_ledger."""
    if "L07_pnl_ledger" in sys.modules:
        return sys.modules["L07_pnl_ledger"]
    try:
        import importlib
        return importlib.import_module("L07_pnl_ledger")
    except ImportError:
        log.warning("L14: L07_pnl_ledger not available — fill event skipped")
        return None


def _get_l22():
    """Soft-import L22 alerting."""
    if "L22_alerting" in sys.modules:
        return sys.modules["L22_alerting"]
    try:
        import importlib
        return importlib.import_module("L22_alerting")
    except ImportError:
        log.warning("L14: L22_alerting not available — fill alert skipped")
        return None


# ---------------------------------------------------------------------------
# Soft-import L46 EventBus — lazy helper (avoids dual-singleton on sys.path)
# ---------------------------------------------------------------------------

def _get_l46():
    """Return L46_event_bus module or None.

    Uses a lazy lookup via sys.modules so that tests can inject a module under
    either canonical name ('L46_event_bus' or 'scripts.execute_loop.L46_event_bus')
    and L14 will always resolve to the same object — avoiding the dual-singleton
    problem that arises when pytest adds 'scripts/execute_loop' to sys.path
    after the package-form import has already been cached.
    """
    for _name in ("L46_event_bus", "scripts.execute_loop.L46_event_bus"):
        _mod = sys.modules.get(_name)
        if _mod is not None:
            return _mod
    # Not yet imported — attempt to load
    import importlib as _il
    try:
        return _il.import_module("L46_event_bus")
    except ImportError:
        pass
    try:
        return _il.import_module("scripts.execute_loop.L46_event_bus")
    except ImportError:
        pass
    return None


# Module-level alias kept for monkeypatching in tests (test_publish_failure_does_not_break_fill_apply)
_L46 = None  # resolved lazily via _get_l46() in _apply_fill


# ---------------------------------------------------------------------------
# Per-exchange adapters: raw position -> NormalizedFill
# ---------------------------------------------------------------------------

def _adapt_kalshi(pos: object, exchange: str) -> NormalizedFill:
    """Kalshi: KalshiPosition — market_ticker, side, qty."""
    market_id = getattr(pos, "market_ticker", None)
    if market_id is None and isinstance(pos, dict):
        market_id = pos.get("market_ticker", "")
    side = getattr(pos, "side", None)
    if side is None and isinstance(pos, dict):
        side = pos.get("side", "")
    qty = getattr(pos, "qty", None)
    if qty is None and isinstance(pos, dict):
        qty = pos.get("qty", 0)
    oid = f"{exchange}:{market_id}:{side}"
    return NormalizedFill(
        exchange=exchange,
        market_id=str(market_id or ""),
        side=str(side or "").lower(),
        qty=float(qty or 0),
        exchange_order_id=oid,
    )


def _adapt_polymarket(pos: object, exchange: str) -> NormalizedFill:
    """Polymarket: PolyPosition — condition_id, outcome (maps to side), qty."""
    market_id = getattr(pos, "condition_id", None)
    if market_id is None and isinstance(pos, dict):
        market_id = pos.get("condition_id", "")
    # outcome acts as side for Polymarket
    side = getattr(pos, "outcome", None)
    if side is None and isinstance(pos, dict):
        side = pos.get("outcome", "")
    qty = getattr(pos, "qty", None)
    if qty is None and isinstance(pos, dict):
        qty = pos.get("qty", 0)
    oid = f"{exchange}:{market_id}:{side}"
    return NormalizedFill(
        exchange=exchange,
        market_id=str(market_id or ""),
        side=str(side or "").lower(),
        qty=float(qty or 0),
        exchange_order_id=oid,
    )


def _adapt_sporttrade(pos: object, exchange: str) -> NormalizedFill:
    """Sporttrade: SporttradePosition — market_id, side, qty."""
    market_id = getattr(pos, "market_id", None)
    if market_id is None and isinstance(pos, dict):
        market_id = pos.get("market_id", "")
    side = getattr(pos, "side", None)
    if side is None and isinstance(pos, dict):
        side = pos.get("side", "")
    qty = getattr(pos, "qty", None)
    if qty is None and isinstance(pos, dict):
        qty = pos.get("qty", 0)
    oid = f"{exchange}:{market_id}:{side}"
    return NormalizedFill(
        exchange=exchange,
        market_id=str(market_id or ""),
        side=str(side or "").lower(),
        qty=float(qty or 0),
        exchange_order_id=oid,
    )


def _adapt_prophet(pos: object, exchange: str) -> NormalizedFill:
    """Prophet: ProphetPosition — market_id, side, qty."""
    market_id = getattr(pos, "market_id", None)
    if market_id is None and isinstance(pos, dict):
        market_id = pos.get("market_id", "")
    side = getattr(pos, "side", None)
    if side is None and isinstance(pos, dict):
        side = pos.get("side", "")
    qty = getattr(pos, "qty", None)
    if qty is None and isinstance(pos, dict):
        qty = pos.get("qty", 0)
    oid = f"{exchange}:{market_id}:{side}"
    return NormalizedFill(
        exchange=exchange,
        market_id=str(market_id or ""),
        side=str(side or "").lower(),
        qty=float(qty or 0),
        exchange_order_id=oid,
    )


_ADAPTERS = {
    "kalshi":      _adapt_kalshi,
    "polymarket":  _adapt_polymarket,
    "sporttrade":  _adapt_sporttrade,
    "prophet":     _adapt_prophet,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def track_order(
    order_id: str,
    exchange: str,
    market_id: str,
    side: str,
    qty: int,
    price: int,
    model_p: float,
) -> OrderState:
    """Create and persist a new tracked order.

    Raises ValueError for unknown exchange or qty == 0.
    """
    if exchange not in _VALID_EXCHANGES:
        raise ValueError(
            f"Unknown exchange {exchange!r}. Valid: {sorted(_VALID_EXCHANGES)}"
        )
    if qty == 0:
        log.warning("L14: track_order called with qty=0 for order_id=%s — ignored", order_id)
        raise ValueError(f"qty must be > 0, got {qty}")

    _init_from_disk()

    order = OrderState(
        order_id=order_id,
        exchange=exchange,
        market_id=market_id,
        side=side,
        qty=qty,
        qty_filled=0,
        price=price,
        status="OPEN",
        model_p=model_p,
        current_model_p=model_p,
        last_repriced_at=0.0,
        placed_at=time.time(),
    )
    _open_orders.append(order)
    _save_orders(_open_orders)
    log.info(
        "L14: tracked order_id=%s exchange=%s market=%s side=%s qty=%d price=%d",
        order_id, exchange, market_id, side, qty, price,
    )
    return order


def get_open_orders() -> List[OrderState]:
    """Return all currently tracked open/partial orders."""
    _init_from_disk()
    return list(_open_orders)


def _apply_fill(order: OrderState, matched_qty: int) -> bool:
    """Apply a fill quantity to an order, updating status and emitting events.

    Uses _processed_fills for idempotency. Returns True if qty_filled changed.
    Caller is responsible for appending order.order_id to a to_remove list
    when order.status == "FILLED".

    Publishes via L46 EventBus (non-fatal if unavailable):
        "fill.received" — always, when qty_filled advances
        "order.filled"  — additionally, when status transitions to FILLED
    """
    prior_fill = _processed_fills.get(order.order_id, 0)
    new_fill = max(prior_fill, matched_qty)

    if new_fill <= order.qty_filled:
        return False

    order.qty_filled = new_fill

    if order.qty_filled >= order.qty:
        order.status = "FILLED"
        if prior_fill < order.qty:
            _emit_fill_events(order)
        _processed_fills[order.order_id] = new_fill
    else:
        order.status = "PARTIAL"
        _processed_fills[order.order_id] = new_fill

    # --- L46 EventBus: resolve module (monkeypatch-aware for tests) ---
    _l46 = _L46 if _L46 is not None else _get_l46()

    # --- L46 EventBus: publish fill.received ---
    if _l46 is not None:
        try:
            _l46.publish("fill.received", source="L14", payload={
                "order_id": order.order_id,
                "exchange": order.exchange,
                "market_id": order.market_id,
                "side": order.side,
                "matched_qty": matched_qty,
                "qty_filled_now": order.qty_filled,
                "status": order.status,
            })
        except Exception:
            log.debug("L46 publish fill.received failed (non-fatal)", exc_info=True)

    # --- L46 EventBus: publish order.filled on FILLED transition ---
    if order.status == "FILLED" and _l46 is not None:
        try:
            _l46.publish("order.filled", source="L14", payload={
                "order_id": order.order_id,
                "exchange": order.exchange,
                "market_id": order.market_id,
                "side": order.side,
                "qty_filled": order.qty_filled,
                "qty": order.qty,
                "price": order.price,
                "model_p": order.model_p,
            })
        except Exception:
            log.debug("L46 publish order.filled failed (non-fatal)", exc_info=True)

    return True


def update_from_exchange_fills() -> int:
    """Poll each exchange and update fill state.

    Returns the number of orders whose fill count changed.
    """
    _init_from_disk()
    updated = 0
    to_remove: List[str] = []

    for order in list(_open_orders):
        if order.status in ("FILLED", "CANCELLED", "REJECTED"):
            continue

        client = _get_exchange_client(order.exchange)
        if client is None:
            continue

        try:
            positions = client.get_positions()
        except Exception as exc:
            log.warning("L14: get_positions failed for %s — %s", order.exchange, exc)
            continue

        # Match position by market_id and side
        matched_qty_filled: Optional[int] = None
        order_found = False
        for pos in positions:
            # Support both attribute and dict access
            pos_ticker = getattr(pos, "market_ticker", None) or (
                pos.get("market_ticker") if isinstance(pos, dict) else None
            )
            pos_side = getattr(pos, "side", None) or (
                pos.get("side") if isinstance(pos, dict) else None
            )
            pos_qty = getattr(pos, "qty", None)
            if pos_qty is None and isinstance(pos, dict):
                pos_qty = pos.get("qty")

            if pos_ticker == order.market_id and pos_side == order.side:
                order_found = True
                matched_qty_filled = int(pos_qty) if pos_qty is not None else 0
                break

        if not order_found:
            # Order not found at exchange — treat as cancelled
            log.warning(
                "L14: order_id=%s not found at exchange %s — marking CANCELLED",
                order.order_id, order.exchange,
            )
            order.status = "CANCELLED"
            to_remove.append(order.order_id)
            updated += 1
            continue

        if matched_qty_filled is None:
            continue

        changed = _apply_fill(order, matched_qty_filled)
        if changed:
            updated += 1
            if order.status == "FILLED":
                to_remove.append(order.order_id)

    # Remove fully settled orders from open list
    if to_remove:
        _open_orders[:] = [o for o in _open_orders if o.order_id not in to_remove]
        _save_orders(_open_orders)

    return updated


def sync_all_exchanges(
    positions: Optional[Dict[str, list]] = None,
    exchanges: Optional[List[str]] = None,
) -> List[OrderState]:
    """Poll all 4 paper exchange clients and reconcile positions.

    Parameters
    ----------
    positions:  Optional pre-fetched positions dict {exchange: [raw_pos, ...]}.
                When None, calls client.get_positions() for each exchange.
    exchanges:  Exchanges to poll. Defaults to list(ALL_EXCHANGES).

    Returns
    -------
    List of OrderState objects whose qty_filled changed during this call.
    """
    if exchanges is None:
        exchanges = list(ALL_EXCHANGES)

    _init_from_disk()
    changed_orders: List[OrderState] = []
    to_remove: List[str] = []

    for exchange in exchanges:
        # Fetch raw positions
        if positions is not None:
            raw_positions = positions.get(exchange) or []
        else:
            client = _get_exchange_client(exchange)
            if client is None:
                continue
            try:
                raw_positions = client.get_positions()
            except Exception as exc:
                log.warning(
                    "L14: sync_all_exchanges: get_positions failed for %s — %s",
                    exchange, exc,
                )
                continue

        adapter = _ADAPTERS.get(exchange)
        if adapter is None:
            log.warning("L14: no adapter for exchange %r — skipping", exchange)
            continue

        # Normalize each raw position into NormalizedFill
        normalized: List[NormalizedFill] = []
        for raw_pos in raw_positions:
            try:
                nf = adapter(raw_pos, exchange)
                normalized.append(nf)
            except Exception as exc:
                log.warning(
                    "L14: adapter %s failed on position %r — %s", exchange, raw_pos, exc
                )

        # Match NormalizedFills to open OrderStates
        for nf in normalized:
            # Dedup: only apply delta beyond what we've already processed for this oid
            prior_oid_qty = _processed_fills_by_oid.get(nf.exchange_order_id, 0.0)
            delta = nf.qty - prior_oid_qty
            if delta <= 0:
                continue

            # Find matching order(s) by (exchange, market_id, side)
            for order in list(_open_orders):
                if order.status in ("FILLED", "CANCELLED", "REJECTED"):
                    continue
                if (
                    order.exchange == nf.exchange
                    and order.market_id == nf.market_id
                    and order.side == nf.side
                ):
                    matched_qty = int(nf.qty)
                    changed = _apply_fill(order, matched_qty)
                    if changed:
                        changed_orders.append(order)
                        if order.status == "FILLED":
                            to_remove.append(order.order_id)
                    # Update oid tracking regardless
                    _processed_fills_by_oid[nf.exchange_order_id] = max(
                        prior_oid_qty, nf.qty
                    )
                    break

    # Remove FILLED orders from open list
    if to_remove:
        _open_orders[:] = [o for o in _open_orders if o.order_id not in to_remove]
        _save_orders(_open_orders)

    return changed_orders


def _emit_fill_events(order: OrderState) -> None:
    """Fire L07 place_bet + L22 send_fill_alert for a newly FILLED order."""
    l07 = _get_l07()
    if l07 is not None:
        try:
            BetRow = l07.BetRow
            row = BetRow(
                bet_id=order.order_id,
                book=order.exchange,
                market=order.market_id,
                side=order.side,
                stake=float(order.qty_filled),
                odds=int(order.price),
                model_p_side=order.model_p,
            )
            l07.place_bet(row)
            log.info("L14: L07.place_bet called for order_id=%s", order.order_id)
        except Exception as exc:
            log.warning("L14: L07.place_bet failed for order_id=%s — %s", order.order_id, exc)

    l22 = _get_l22()
    if l22 is not None:
        try:
            l22.send_fill_alert(
                bet_id=order.order_id,
                book=order.exchange,
                stake=float(order.qty_filled),
                status="FILLED",
            )
            log.info("L14: L22.send_fill_alert called for order_id=%s", order.order_id)
        except Exception as exc:
            log.warning("L14: L22.send_fill_alert failed for order_id=%s — %s", order.order_id, exc)


def check_for_reprice(model_predictions: dict) -> List[OrderState]:
    """Return orders where |current_model_p - model_predictions[market_id]| > 0.05.

    Also updates current_model_p on each order from model_predictions.
    model_predictions: {market_id: float probability}
    """
    _init_from_disk()
    needs_reprice: List[OrderState] = []

    for order in _open_orders:
        if order.status not in ("OPEN", "PARTIAL"):
            continue
        new_p = model_predictions.get(order.market_id)
        if new_p is None:
            continue
        # Update current model probability
        order.current_model_p = float(new_p)
        drift = abs(order.current_model_p - order.model_p)
        if drift > 0.05:
            needs_reprice.append(order)

    if needs_reprice:
        _save_orders(_open_orders)

    return needs_reprice


def cancel_stale(max_age_seconds: int = 1800) -> int:
    """Cancel orders older than max_age_seconds via exchange.cancel_order.

    Returns count of orders cancelled.
    """
    _init_from_disk()
    now = time.time()
    cancelled = 0
    to_remove: List[str] = []

    for order in list(_open_orders):
        if order.status not in ("OPEN", "PARTIAL"):
            continue
        age = now - order.placed_at
        if age <= max_age_seconds:
            continue

        client = _get_exchange_client(order.exchange)
        if client is None:
            continue

        try:
            ok = client.cancel_order(order.order_id)
        except Exception as exc:
            log.warning(
                "L14: cancel_order failed for order_id=%s — %s", order.order_id, exc
            )
            ok = False

        order.status = "CANCELLED"
        to_remove.append(order.order_id)
        cancelled += 1
        log.info(
            "L14: cancelled stale order_id=%s age=%.0fs exchange_ack=%s",
            order.order_id, age, ok,
        )

    if to_remove:
        _open_orders[:] = [o for o in _open_orders if o.order_id not in to_remove]
        _save_orders(_open_orders)

    return cancelled


def reprice_order(order: OrderState, new_price: int) -> bool:
    """Cancel existing order and post a new one at new_price.

    Removes old order from tracking and creates a new tracked order.
    Returns True on success, False if cancel or re-post fails.
    """
    _init_from_disk()

    client = _get_exchange_client(order.exchange)
    if client is None:
        log.warning("L14: reprice_order: exchange client unavailable for %s", order.exchange)
        return False

    # Cancel old order
    try:
        client.cancel_order(order.order_id)
    except Exception as exc:
        log.warning("L14: reprice cancel failed for order_id=%s — %s", order.order_id, exc)
        return False

    # Remove old from open list
    _open_orders[:] = [o for o in _open_orders if o.order_id != order.order_id]

    # Post new order at new_price
    import uuid
    new_order_id = f"repriced_{order.order_id}_{uuid.uuid4().hex[:6]}"
    try:
        client.post_order(
            market_ticker=order.market_id,
            side=order.side,
            qty=order.qty - order.qty_filled,
            price=new_price,
            idempotency_key=new_order_id,
        )
    except Exception as exc:
        log.warning("L14: reprice post_order failed for %s — %s", new_order_id, exc)
        _save_orders(_open_orders)
        return False

    # Track new order
    new_order = OrderState(
        order_id=new_order_id,
        exchange=order.exchange,
        market_id=order.market_id,
        side=order.side,
        qty=order.qty - order.qty_filled,
        qty_filled=0,
        price=new_price,
        status="OPEN",
        model_p=order.model_p,
        current_model_p=order.current_model_p,
        last_repriced_at=time.time(),
        placed_at=time.time(),
    )
    _open_orders.append(new_order)
    _save_orders(_open_orders)
    log.info(
        "L14: repriced order_id=%s → %s new_price=%d",
        order.order_id, new_order_id, new_price,
    )
    return True


# ---------------------------------------------------------------------------
# Module reset helper (used by tests)
# ---------------------------------------------------------------------------

def _reset_state() -> None:
    """Clear in-memory state — intended for test isolation only."""
    global _open_orders, _processed_fills, _processed_fills_by_oid
    _open_orders = []
    _processed_fills = {}
    _processed_fills_by_oid = {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="L14 Order Manager")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="Print all open orders")
    sub.add_parser("update", help="Poll exchanges for fills")

    rp = sub.add_parser("reprice", help="Cancel + repost order at new price")
    rp.add_argument("--order-id", required=True)
    rp.add_argument("--new-price", required=True, type=int)

    cs = sub.add_parser("cancel-stale", help="Cancel orders older than max_age_sec")
    cs.add_argument("--max-age-sec", type=int, default=1800)

    args = parser.parse_args()

    if args.cmd == "list":
        orders = get_open_orders()
        if not orders:
            print("No open orders.")
        for o in orders:
            print(
                f"  {o.order_id:32s}  {o.exchange:12s}  {o.market_id:20s}"
                f"  {o.side:4s}  qty={o.qty}/{o.qty_filled}"
                f"  price={o.price}  status={o.status}"
            )

    elif args.cmd == "update":
        n = update_from_exchange_fills()
        print(f"Updated {n} orders from exchange fills.")

    elif args.cmd == "reprice":
        orders = {o.order_id: o for o in get_open_orders()}
        order = orders.get(args.order_id)
        if order is None:
            print(f"Order {args.order_id!r} not found in open orders.")
            sys.exit(1)
        ok = reprice_order(order, args.new_price)
        print("Reprice", "succeeded" if ok else "FAILED")

    elif args.cmd == "cancel-stale":
        n = cancel_stale(max_age_seconds=args.max_age_sec)
        print(f"Cancelled {n} stale orders.")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
