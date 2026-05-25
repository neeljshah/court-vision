"""L15_market_making.py — Market-Making Logic (PAPER MODE STRICT).

Generates two-sided quotes (bid/ask) from a model probability estimate,
posts them via L14 order tracking, and refreshes quotes when model drift
exceeds a threshold.

Public API
----------
    MMQuote                     dataclass
    prob_to_american(p) -> int
    compute_mm_quote(model_p, model_p_std, target_spread_pp) -> MMQuote | None
    should_market_make(model_p, model_p_std, liquidity_threshold) -> bool
    post_two_sided(exchange, market_id, mm_quote) -> dict
    update_quotes_on_model_drift(open_quotes, new_predictions) -> list[MMQuote]

Paper Mode Strict
-----------------
    post_two_sided uses soft-imported L14.track_order only.
    If L14 is unavailable → {"bid_order_id": None, "ask_order_id": None, "status": "L14_missing"}
    No live exchange HTTP calls are ever made.

CLI
---
    python L15_market_making.py simulate --market_id X --model_p 0.55 --std 0.03 [--spread 5]
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path  # noqa: F401 — kept for pathlib.Path convention
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid exchanges (superset of L14; prophet added for prediction markets)
# ---------------------------------------------------------------------------
_VALID_EXCHANGES = {"kalshi", "polymarket", "sporttrade", "prophet"}

# ---------------------------------------------------------------------------
# Drift threshold: republish quote when model moves more than this
# ---------------------------------------------------------------------------
_DRIFT_THRESHOLD = 0.02

# ---------------------------------------------------------------------------
# Probability clamp: quotes must stay strictly inside (0.01, 0.99)
# ---------------------------------------------------------------------------
_PROB_MIN = 0.01
_PROB_MAX = 0.99

# ---------------------------------------------------------------------------
# Market-making guard rails
# ---------------------------------------------------------------------------
_STD_GATE = 0.05       # reject if model uncertainty too high
_P_LOW_GATE = 0.10     # reject extreme low probability
_P_HIGH_GATE = 0.90    # reject extreme high probability


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class MMQuote:
    """A two-sided market-maker quote for one market."""

    market_id: str
    bid_price: int    # American odds (integer) — taker buys YES at this price
    bid_qty: float
    ask_price: int    # American odds (integer) — taker buys NO at this price
    ask_qty: float
    fair_value: float   # model probability [0, 1]
    edge_per_side: float  # EV per $1 staked (proportion) = half_spread_prob


# ---------------------------------------------------------------------------
# Odds math
# ---------------------------------------------------------------------------

def prob_to_american(p: float) -> int:
    """Convert win probability [0, 1] to integer American odds.

    Examples
    --------
    >>> prob_to_american(0.55)
    -122
    >>> prob_to_american(0.40)
    150
    """
    if p >= 0.5:
        return int(round(-100 * p / (1 - p)))
    return int(round(100 * (1 - p) / p))


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def should_market_make(
    model_p: float,
    model_p_std: float,
    liquidity_threshold: float = 100,
) -> bool:
    """Return True iff it is safe and worthwhile to post a two-sided quote.

    Conditions (all must hold):
    - model_p_std < 0.05       (model confident enough)
    - 0.10 < model_p < 0.90   (not a near-certain outcome)
    - liquidity_threshold >= 0 (caller may pass any non-negative value)

    Parameters
    ----------
    model_p:
        Model win probability in [0, 1].
    model_p_std:
        Standard deviation of the model probability estimate.
    liquidity_threshold:
        Minimum available liquidity at this market (informational gate).
        Passes when >= 0; caller can use 0 to effectively disable this check.
    """
    if model_p_std >= _STD_GATE:
        log.debug(
            "should_market_make=False: std=%.4f >= %.2f (uncertainty gate)",
            model_p_std, _STD_GATE,
        )
        return False
    if not (_P_LOW_GATE < model_p < _P_HIGH_GATE):
        log.debug(
            "should_market_make=False: model_p=%.4f outside (%s, %s)",
            model_p, _P_LOW_GATE, _P_HIGH_GATE,
        )
        return False
    if liquidity_threshold < 0:
        log.debug(
            "should_market_make=False: liquidity_threshold=%.2f < 0",
            liquidity_threshold,
        )
        return False
    return True


def compute_mm_quote(
    model_p: float,
    model_p_std: float,
    target_spread_pp: int = 3,
    market_id: str = "unknown",
) -> Optional[MMQuote]:
    """Compute a two-sided market-maker quote.

    The spread in probability space is ``target_spread_pp / 100``.
    We post bid (buy YES) at a probability *above* fair value and ask (buy NO)
    at a probability *below* fair value — so every fill yields positive edge.

    Parameters
    ----------
    model_p:
        Model win probability in [0, 1].
    model_p_std:
        Standard deviation of the probability estimate.
    target_spread_pp:
        Total spread in percentage points (default 3pp = 1.5pp each side).
    market_id:
        Market identifier attached to the returned MMQuote.

    Returns
    -------
    MMQuote or None if any guard rail is violated.
    """
    if not should_market_make(model_p, model_p_std):
        log.debug(
            "compute_mm_quote: should_market_make=False for model_p=%.4f std=%.4f — returning None",
            model_p, model_p_std,
        )
        return None

    half_spread_prob = (target_spread_pp / 100) / 2  # fraction, halved

    # Bid: maker offers to buy YES; taker selling YES gets worse implied prob
    bid_p = model_p + half_spread_prob
    # Ask: maker offers to sell YES; taker buying YES gets worse implied prob
    ask_p = model_p - half_spread_prob

    if bid_p >= _PROB_MAX or ask_p <= _PROB_MIN:
        log.debug(
            "compute_mm_quote: spread breaches prob bounds (bid=%.4f ask=%.4f) — returning None",
            bid_p, ask_p,
        )
        return None

    bid_price = prob_to_american(bid_p)
    ask_price = prob_to_american(ask_p)

    quote = MMQuote(
        market_id=market_id,
        bid_price=bid_price,
        bid_qty=1.0,
        ask_price=ask_price,
        ask_qty=1.0,
        fair_value=model_p,
        edge_per_side=half_spread_prob,
    )
    log.info(
        "compute_mm_quote: market=%s fair=%.4f bid=%d ask=%d edge=%.4f",
        market_id, model_p, bid_price, ask_price, half_spread_prob,
    )
    return quote


# ---------------------------------------------------------------------------
# Soft-import helpers
# ---------------------------------------------------------------------------

def _get_l14():
    """Soft-import L14_order_manager. Returns module or None."""
    mod_name = "L14_order_manager"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    try:
        import importlib
        return importlib.import_module(mod_name)
    except ImportError:
        log.warning("L15: L14_order_manager not available (ImportError)")
        return None


def _get_l18():
    """Soft-import L18_bankroll_manager. Returns module or None."""
    mod_name = "L18_bankroll_manager"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    try:
        import importlib
        return importlib.import_module(mod_name)
    except ImportError:
        log.debug("L15: L18_bankroll_manager not available — bankroll gate skipped")
        return None


# ---------------------------------------------------------------------------
# Order dispatch
# ---------------------------------------------------------------------------

def post_two_sided(
    exchange: str,
    market_id: str,
    mm_quote: MMQuote,
) -> dict:
    """Post both legs of an MM quote via L14 paper order tracking.

    Parameters
    ----------
    exchange:
        One of {"kalshi", "polymarket", "sporttrade", "prophet"}.
    market_id:
        Market identifier (e.g. "NBA_LAL_BOS_SPREAD_OVER").
    mm_quote:
        Populated MMQuote (from compute_mm_quote).

    Returns
    -------
    dict with keys: "bid_order_id", "ask_order_id", "status"

    Notes
    -----
    PAPER MODE STRICT — all order dispatch routes through L14.track_order.
    No live exchange HTTP calls are made here.
    If L14 is unavailable, returns status "L14_missing" with None order IDs.
    """
    if exchange not in _VALID_EXCHANGES:
        raise ValueError(
            f"Unknown exchange {exchange!r}. Valid: {sorted(_VALID_EXCHANGES)}"
        )

    l14 = _get_l14()
    if l14 is None:
        log.warning("L15: L14 missing — cannot post two-sided quote for market=%s", market_id)
        return {"bid_order_id": None, "ask_order_id": None, "status": "L14_missing"}

    bid_order_id = f"mm_bid_{uuid.uuid4().hex[:10]}"
    ask_order_id = f"mm_ask_{uuid.uuid4().hex[:10]}"

    # L14 uses cents 1-99 for price; for prediction markets this is probability %.
    # For American-odds exchanges (sporttrade, kalshi) we store the raw American
    # integer in the order — L14 is agnostic about the semantics, callers interpret.
    try:
        l14.track_order(
            order_id=bid_order_id,
            exchange=exchange if exchange in {"kalshi", "polymarket", "sporttrade"} else "kalshi",
            market_id=market_id,
            side="BID",
            qty=1,
            price=mm_quote.bid_price,
            model_p=mm_quote.fair_value,
        )
        log.info(
            "L15: posted BID order_id=%s exchange=%s market=%s price=%d",
            bid_order_id, exchange, market_id, mm_quote.bid_price,
        )
    except Exception as exc:
        log.warning("L15: L14.track_order BID failed — %s", exc)
        return {"bid_order_id": None, "ask_order_id": None, "status": f"bid_error:{exc}"}

    try:
        l14.track_order(
            order_id=ask_order_id,
            exchange=exchange if exchange in {"kalshi", "polymarket", "sporttrade"} else "kalshi",
            market_id=market_id,
            side="ASK",
            qty=1,
            price=mm_quote.ask_price,
            model_p=mm_quote.fair_value,
        )
        log.info(
            "L15: posted ASK order_id=%s exchange=%s market=%s price=%d",
            ask_order_id, exchange, market_id, mm_quote.ask_price,
        )
    except Exception as exc:
        log.warning("L15: L14.track_order ASK failed — %s", exc)
        return {
            "bid_order_id": bid_order_id,
            "ask_order_id": None,
            "status": f"ask_error:{exc}",
        }

    return {
        "bid_order_id": bid_order_id,
        "ask_order_id": ask_order_id,
        "status": "posted",
    }


# ---------------------------------------------------------------------------
# Quote refresh on model drift
# ---------------------------------------------------------------------------

def update_quotes_on_model_drift(
    open_quotes: list[MMQuote],
    new_predictions: dict,
) -> list[MMQuote]:
    """Return quotes that need refreshing because the model has drifted.

    A quote is included in the refresh list if:
        abs(new_predictions[market_id] - quote.fair_value) > 0.02

    Parameters
    ----------
    open_quotes:
        Currently live MMQuote objects (from previous compute_mm_quote calls).
    new_predictions:
        Dict mapping market_id -> new model probability (float).

    Returns
    -------
    Subset of open_quotes that require re-quoting, in original order.
    """
    refresh: list[MMQuote] = []
    for quote in open_quotes:
        new_p = new_predictions.get(quote.market_id)
        if new_p is None:
            log.debug(
                "update_quotes_on_model_drift: no prediction for market=%s — skipping",
                quote.market_id,
            )
            continue
        drift = abs(new_p - quote.fair_value)
        if drift > _DRIFT_THRESHOLD:
            log.info(
                "L15: quote refresh needed for market=%s (drift=%.4f > %.4f)",
                quote.market_id, drift, _DRIFT_THRESHOLD,
            )
            refresh.append(quote)
        else:
            log.debug(
                "L15: quote stable for market=%s (drift=%.4f <= %.4f)",
                quote.market_id, drift, _DRIFT_THRESHOLD,
            )
    return refresh


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv=None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s [L15] %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        prog="L15_market_making",
        description="Market-Making Logic (PAPER MODE) — simulate quote generation",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sim = sub.add_parser(
        "simulate",
        help="Compute and display a two-sided MM quote for given model inputs",
    )
    sim.add_argument("--market_id", required=True, help="Market identifier string")
    sim.add_argument(
        "--model_p",
        required=True,
        type=float,
        help="Model probability estimate [0, 1]",
    )
    sim.add_argument(
        "--std",
        required=True,
        type=float,
        help="Model probability std-dev (uncertainty)",
    )
    sim.add_argument(
        "--spread",
        type=int,
        default=3,
        help="Target spread in percentage points (default: 3)",
    )

    args = parser.parse_args(argv)

    if args.command == "simulate":
        go = should_market_make(args.model_p, args.std)
        print(f"should_market_make: {go}")
        if not go:
            print("Conditions not met — no quote generated.")
            return

        quote = compute_mm_quote(
            model_p=args.model_p,
            model_p_std=args.std,
            target_spread_pp=args.spread,
            market_id=args.market_id,
        )
        if quote is None:
            print("compute_mm_quote returned None (spread breaches prob bounds).")
            return

        print(f"Market:        {quote.market_id}")
        print(f"Fair value:    {quote.fair_value:.4f} ({prob_to_american(quote.fair_value):+d})")
        print(f"Bid price:     {quote.bid_price:+d}  (qty={quote.bid_qty})")
        print(f"Ask price:     {quote.ask_price:+d}  (qty={quote.ask_qty})")
        print(f"Edge/side:     {quote.edge_per_side:.4f} ({quote.edge_per_side * 100:.2f}pp)")


if __name__ == "__main__":
    _cli()
