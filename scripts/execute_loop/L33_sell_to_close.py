"""L33_sell_to_close.py — Sell-to-Close Optimizer for live prediction-market positions.

Given an open position and the current bid/ask quote, decides whether to HOLD,
SELL (full position), or SELL_PARTIAL (half the position) by comparing the
market's current value against the model's expected settlement value.

Public API
----------
    CloseDecision                 dataclass
    evaluate_close_decision(position, current_quote, model_p, time_to_settle_min,
                            *, model_p_var=None) -> CloseDecision
    score_market_value_now(position, current_quote) -> float
    score_hold_to_settle(position, model_p) -> float

CLI
---
    python L33_sell_to_close.py evaluate \\
        --position '{"position_id":"p1","qty":100,"entry_price":0.50,"side":"YES"}' \\
        --quote '{"bid_price":0.70,"ask_price":0.72,"bid_size":50}' \\
        --model-p 0.75 \\
        [--time 30] \\
        [--model-p-var 0.03]

Environment Variables
---------------------
L33_PAPER_MODE
    When set to "1", "true", or "yes" (case-insensitive), the module operates in
    paper mode.  Decisions are computed normally but the mode is logged on every
    SELL/SELL_PARTIAL action so callers can gate live order submission.  Defaults
    to paper mode when the variable is absent (safe default).

L33_EVENT_BUS_DISABLED
    When set to "1", "true", or "yes" (case-insensitive), event publication is
    skipped entirely even if L46 is available.  Useful for offline / unit-test
    environments where importing L46 is undesirable.

Paper vs Live Mode (MODE GATING)
---------------------------------
L33 reads L33_PAPER_MODE at module import time.  The resolved mode is available
as the module-level boolean ``PAPER_MODE`` (True = paper, False = live).

In paper mode:
  - All decision logic runs identically to live mode.
  - SELL and SELL_PARTIAL actions log a [PAPER] prefix so operators can
    distinguish simulated closes from real executions.
  - The "close.recommended" EventBus event is still published; downstream
    layers (e.g. L34, L44) are responsible for gating real order submission.

In live mode:
  - Behaviour is identical; L33 itself does not submit orders.  Live gating
    belongs to the submission layer (L44).

Event Publication
-----------------
When ``evaluate_close_decision`` returns action "SELL" or "SELL_PARTIAL", L33
publishes a "close.recommended" event to the L46 EventBus default bus:

    {
        "position_id":   str   — position identifier
        "player":        str   — player name (from position["player"], or "")
        "stat":          str   — stat label (from position["stat"], or "")
        "current_price": float — bid_price at decision time
        "entry_price":   float — original entry price
        "unrealized_pnl": float — expected_pnl_now at decision time
        "reason":        str   — decision_reason ("lock_gain" | "de_risk_marginal")
        "model_p_var":   float | None — variance signal passed to evaluate_close_decision
        "recommended_at": str  — ISO 8601 UTC timestamp
    }

HOLD decisions do not publish any event.  Publication failures are caught and
logged as warnings so that a broken bus never prevents the CloseDecision from
being returned to the caller.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Make imports work from both the loop dir and from the project root.
_LOOP_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _LOOP_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paper vs live mode — resolved once at import time
# ---------------------------------------------------------------------------
def _resolve_bool_env(var: str, default: bool = True) -> bool:
    """Return True if the env var is absent (default) or set to a truthy value."""
    val = os.environ.get(var, "").strip().lower()
    if val == "":
        return default
    return val in ("1", "true", "yes")

PAPER_MODE: bool = _resolve_bool_env("L33_PAPER_MODE", default=True)
_EVENT_BUS_DISABLED: bool = _resolve_bool_env("L33_EVENT_BUS_DISABLED", default=False)

# ---------------------------------------------------------------------------
# Soft-import L46 EventBus
# ---------------------------------------------------------------------------
_L46 = None
if not _EVENT_BUS_DISABLED:
    try:
        import L46_event_bus as _L46  # type: ignore[import]
    except ImportError:  # pragma: no cover
        log.debug("[L33] L46_event_bus not available; event publication disabled.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_HOLD_PREMIUM_DEFAULT = 1.05   # hold preferred if hold_value > now_value * this
_SELL_PREMIUM_DEFAULT = 1.05   # sell preferred if now_value > hold_value * this
_HOLD_PREMIUM_UNCERTAIN = 1.02  # tighter threshold when model_p variance is high
_HIGH_VAR_THRESHOLD = 0.05     # model_p_var above which we use tighter premiums
_SETTLEMENT_IMMINENT_MIN = 5   # minutes; below this skip trading to avoid timing risk

# Sides recognised as the "YES / OVER" direction (long)
_LONG_SIDES = {"YES", "OVER"}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class CloseDecision:
    position_id: str
    action: str                    # "HOLD" | "SELL" | "SELL_PARTIAL"
    sell_qty: float                # 0 if HOLD; full qty if SELL; qty/2 if SELL_PARTIAL
    sell_price: Optional[float]    # current bid_price, or None if no liquidity
    expected_pnl_now: float        # USD if we sell at bid right now
    expected_pnl_hold: float       # USD expected at settlement given model_p
    decision_reason: str
    # Internal book-keeping — not part of the core interface but useful for logs
    _value_now: float = field(default=0.0, repr=False)
    _value_hold: float = field(default=0.0, repr=False)


# ---------------------------------------------------------------------------
# Core scoring functions
# ---------------------------------------------------------------------------
def score_market_value_now(position: dict, current_quote: dict) -> float:
    """Return the USD value of selling the position at the current bid price.

    Parameters
    ----------
    position      : dict — must contain "qty" (float), "side" (str), "entry_price" (float)
    current_quote : dict — must contain "bid_price" (float | None), "bid_size" (float)

    Returns
    -------
    float — estimated USD proceeds from closing now; 0.0 if bid_price is None.

    Notes
    -----
    - YES / OVER (long): value = qty * bid_price
    - NO  / UNDER (short): value = qty * (1 - bid_price)
      because a NO share at bid_price implies the counterpart pays (1 - bid_price).
    """
    qty: float = float(position.get("qty", 0.0))
    side: str = str(position.get("side", "YES")).upper()
    bid_price = current_quote.get("bid_price")

    if bid_price is None:
        return 0.0

    bid_price = float(bid_price)

    if side in _LONG_SIDES:
        return qty * bid_price
    else:
        # NO / UNDER position: closing via YES bid means we receive (1 - bid)
        return qty * (1.0 - bid_price)


def score_hold_to_settle(position: dict, model_p: float) -> float:
    """Return the model-expected USD value at settlement.

    Parameters
    ----------
    position : dict — must contain "qty" (float) and "side" (str)
    model_p  : float — model probability that the YES/OVER outcome resolves True;
               must already be clamped to [0, 1] before calling (caller is evaluate_close_decision).

    Returns
    -------
    float — expected USD at settlement.

    Notes
    -----
    - YES / OVER: E[value] = qty * model_p
    - NO  / UNDER: E[value] = qty * (1 - model_p)
    """
    qty: float = float(position.get("qty", 0.0))
    side: str = str(position.get("side", "YES")).upper()

    if side in _LONG_SIDES:
        return qty * model_p
    else:
        return qty * (1.0 - model_p)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _publish_close_event(
    decision: CloseDecision,
    position: dict,
    model_p_var: Optional[float],
) -> None:
    """Publish 'close.recommended' to L46 EventBus.  Silently swallows errors."""
    if _L46 is None:
        return
    try:
        _L46.publish(
            "close.recommended",
            source="L33",
            payload={
                "position_id": decision.position_id,
                "player": position.get("player", ""),
                "stat": position.get("stat", ""),
                "current_price": decision.sell_price,
                "entry_price": float(position.get("entry_price", 0.0)),
                "unrealized_pnl": decision.expected_pnl_now,
                "reason": decision.decision_reason,
                "model_p_var": model_p_var,
                "recommended_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("[L33] EventBus publish failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Main decision function
# ---------------------------------------------------------------------------
def evaluate_close_decision(
    position: dict,
    current_quote: dict,
    model_p: float,
    time_to_settle_min: int,
    *,
    model_p_var: Optional[float] = None,
) -> CloseDecision:
    """Evaluate whether to close (sell) a position, hold it, or sell it partially.

    Parameters
    ----------
    position           : dict — {"position_id": str, "qty": float,
                                  "entry_price": float, "side": "YES"|"NO"|"OVER"|"UNDER",
                                  "player": str (optional), "stat": str (optional)}
    current_quote      : dict — {"bid_price": float | None, "ask_price": float | None,
                                  "bid_size": float, "venue": str}
    model_p            : float — model probability of YES/OVER resolving True (0-1)
    time_to_settle_min : int   — minutes until settlement / game end
    model_p_var        : float | None — model prediction variance; when > 0.05 the
                          hold/sell premium threshold tightens to 1.02 (more aggressive selling)

    Returns
    -------
    CloseDecision — dataclass with action, quantities, prices, and PnL estimates.

    Decision tree
    -------------
    1. Clamp model_p to [0, 1]; WARN if outside.
    2. qty <= 0                       → HOLD (reason="empty_position")
    3. time_to_settle_min < 5         → HOLD (reason="settlement_imminent")
    4. bid_price None or bid_size==0  → HOLD (reason="no_liquidity")
    5. Compute value_now, value_hold.
    6. value_hold > value_now * premium  → HOLD   (reason="hold_premium")
    7. value_now > value_hold * premium  → SELL    (reason="lock_gain")
    8. else                             → SELL_PARTIAL (reason="de_risk_marginal")

    Event Publication
    -----------------
    When action is SELL or SELL_PARTIAL, a "close.recommended" event is published
    to the L46 EventBus default bus (if L46 is importable and L33_EVENT_BUS_DISABLED
    is not set).  Publication errors are caught and logged as warnings; they never
    prevent the CloseDecision from being returned.
    """
    position_id: str = str(position.get("position_id", ""))
    qty: float = float(position.get("qty", 0.0))
    entry_price: float = float(position.get("entry_price", 0.0))

    # ------------------------------------------------------------------
    # Step 1: clamp model_p
    # ------------------------------------------------------------------
    raw_model_p = model_p
    model_p = max(0.0, min(1.0, model_p))
    if raw_model_p != model_p:
        log.warning(
            "[L33] position=%s model_p=%.4f is outside [0,1]; clamped to %.4f",
            position_id, raw_model_p, model_p,
        )

    # Determine premium threshold (tighten if high model uncertainty)
    if model_p_var is not None and float(model_p_var) > _HIGH_VAR_THRESHOLD:
        premium = _HOLD_PREMIUM_UNCERTAIN
        log.info(
            "[L33] position=%s model_p_var=%.4f > %.2f; using tighter premium %.2f",
            position_id, model_p_var, _HIGH_VAR_THRESHOLD, premium,
        )
    else:
        premium = _HOLD_PREMIUM_DEFAULT

    def _make(action: str, sell_qty: float, sell_price, reason: str,
              val_now: float = 0.0, val_hold: float = 0.0) -> CloseDecision:
        pnl_now = val_now - (sell_qty * entry_price) if sell_qty > 0 else 0.0
        pnl_hold = val_hold - (qty * entry_price)
        return CloseDecision(
            position_id=position_id,
            action=action,
            sell_qty=sell_qty,
            sell_price=sell_price,
            expected_pnl_now=round(pnl_now, 6),
            expected_pnl_hold=round(pnl_hold, 6),
            decision_reason=reason,
            _value_now=val_now,
            _value_hold=val_hold,
        )

    # ------------------------------------------------------------------
    # Step 2: empty position guard
    # ------------------------------------------------------------------
    if qty <= 0:
        log.warning("[L33] position=%s qty=%.4f <= 0; skipping.", position_id, qty)
        return _make("HOLD", 0.0, None, "empty_position")

    # ------------------------------------------------------------------
    # Step 3: settlement imminent — avoid execution risk near close
    # ------------------------------------------------------------------
    if time_to_settle_min < _SETTLEMENT_IMMINENT_MIN:
        log.info(
            "[L33] position=%s time_to_settle=%d < %d min; HOLD (settlement_imminent).",
            position_id, time_to_settle_min, _SETTLEMENT_IMMINENT_MIN,
        )
        return _make("HOLD", 0.0, None, "settlement_imminent")

    # ------------------------------------------------------------------
    # Step 4: liquidity check
    # ------------------------------------------------------------------
    bid_price = current_quote.get("bid_price")
    bid_size: float = float(current_quote.get("bid_size", 0.0))

    if bid_price is None or bid_size == 0:
        log.info(
            "[L33] position=%s bid_price=%s bid_size=%.2f; HOLD (no_liquidity).",
            position_id, bid_price, bid_size,
        )
        return _make("HOLD", 0.0, None, "no_liquidity")

    bid_price = float(bid_price)

    # ------------------------------------------------------------------
    # Step 5: compute values
    # ------------------------------------------------------------------
    value_now = score_market_value_now(position, current_quote)
    value_hold = score_hold_to_settle(position, model_p)

    log.debug(
        "[L33] position=%s value_now=%.4f value_hold=%.4f premium=%.2f",
        position_id, value_now, value_hold, premium,
    )

    # ------------------------------------------------------------------
    # Step 6: HOLD if model expects meaningfully more at settlement
    # ------------------------------------------------------------------
    if value_hold > value_now * premium:
        log.info(
            "[L33] position=%s HOLD — hold_value=%.4f > now*%.2f=%.4f (hold_premium)",
            position_id, value_hold, premium, value_now * premium,
        )
        return _make("HOLD", 0.0, bid_price, "hold_premium", value_now, value_hold)

    # ------------------------------------------------------------------
    # Step 7: SELL full if market bid is meaningfully better than model
    # ------------------------------------------------------------------
    if value_now > value_hold * premium:
        _mode_tag = "[PAPER] " if PAPER_MODE else ""
        log.info(
            "[L33] %sposition=%s SELL — now=%.4f > hold*%.2f=%.4f (lock_gain)",
            _mode_tag, position_id, value_now, premium, value_hold * premium,
        )
        decision = _make("SELL", qty, bid_price, "lock_gain", value_now, value_hold)
        _publish_close_event(decision, position, model_p_var)
        return decision

    # ------------------------------------------------------------------
    # Step 8: values are roughly equal — de-risk half the position
    # ------------------------------------------------------------------
    half_qty = qty / 2.0
    half_value_now = value_now / 2.0
    _mode_tag = "[PAPER] " if PAPER_MODE else ""
    log.info(
        "[L33] %sposition=%s SELL_PARTIAL qty=%.2f — marginal difference (de_risk_marginal)",
        _mode_tag, position_id, half_qty,
    )
    decision = CloseDecision(
        position_id=position_id,
        action="SELL_PARTIAL",
        sell_qty=half_qty,
        sell_price=bid_price,
        expected_pnl_now=round(half_value_now - (half_qty * entry_price), 6),
        expected_pnl_hold=round(value_hold - (qty * entry_price), 6),
        decision_reason="de_risk_marginal",
        _value_now=value_now,
        _value_hold=value_hold,
    )
    _publish_close_event(decision, position, model_p_var)
    return decision


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_evaluate(args: argparse.Namespace) -> None:
    try:
        position = json.loads(args.position)
    except json.JSONDecodeError as exc:
        print(f"[L33] ERROR parsing --position JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        quote = json.loads(args.quote)
    except json.JSONDecodeError as exc:
        print(f"[L33] ERROR parsing --quote JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    model_p: float = float(args.model_p)
    time_min: int = int(args.time)
    model_p_var: Optional[float] = float(args.model_p_var) if args.model_p_var is not None else None

    decision = evaluate_close_decision(
        position, quote, model_p, time_min, model_p_var=model_p_var
    )

    print(f"[L33] CloseDecision for position '{decision.position_id}'")
    print(f"  action         : {decision.action}")
    print(f"  sell_qty       : {decision.sell_qty:.4f}")
    print(f"  sell_price     : {decision.sell_price}")
    print(f"  pnl_now        : ${decision.expected_pnl_now:.4f}")
    print(f"  pnl_hold       : ${decision.expected_pnl_hold:.4f}")
    print(f"  reason         : {decision.decision_reason}")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="L33_sell_to_close")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_eval = sub.add_parser("evaluate", help="Evaluate whether to close a position")
    p_eval.add_argument("--position", required=True, help="JSON string for position dict")
    p_eval.add_argument("--quote", required=True, help="JSON string for current_quote dict")
    p_eval.add_argument("--model-p", required=True, type=float, help="Model probability (0-1)")
    p_eval.add_argument("--time", default=30, type=int,
                        help="Minutes to settlement (default: 30)")
    p_eval.add_argument("--model-p-var", default=None, type=float,
                        help="Model prediction variance (optional; >0.05 tightens premium)")
    p_eval.set_defaults(func=_cli_evaluate)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
