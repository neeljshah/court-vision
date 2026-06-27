"""scripts.platformkit.pm_trading.kalshi_edge_finder -- price the LIQUID Kalshi surface
across market types and emit paper best-bet candidates where we have a model.

Kalshi quotes a real, LOW-VIG two-way (~1c spread) on game-winners, team totals, player
props and spreads. This framework processes every liquid market, DEVIGS the Kalshi
two-way to a fair YES prob, and -- for the market types we actually have a calibrated
model for -- compares our number to the fair price and emits an edge candidate. Types we
cannot honestly model (season futures, MVP, Ballon d'Or, ...) are SKIPPED and counted,
never priced from thin air. "Bet all of them best as it can" = price what we can model at
Kalshi's low vig; skip what we can't, transparently.

HONEST RAILS: PAPER candidates only (executed=False, edge_claimed=False) -- this emits
edge candidates for a placer to stake in UNITS; it never places real money, claims a $
edge, flips a flag, or writes data/registry/. A pricer that returns None -> no candidate
(never fabricated). edge = our model prob - the DEVIGGED fair prob (a probability gap, NOT
a $). Pricers are injected so the core is offline-testable and extensible per type.

INVARIANTS: scripts/platformkit only; ASCII; <=300 LOC.
Per-file test: scripts/platformkit/pm_trading/test_kalshi_edge_finder.py
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("kalshi_edge_finder")

# A pricer maps a liquid market dict -> our model P(YES), or None when we can't price it.
Pricer = Callable[[Dict[str, Any]], Optional[float]]

# Minimum edge over the devigged fair to emit a candidate (probability points). A real
# in-game edge must clear sampling noise + the (small) Kalshi spread cost.
DEFAULT_EDGE_FLOOR = 0.03


def _num(m: Dict[str, Any], key: str) -> Optional[float]:
    v = m.get(key)
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def devig_yes(yes_bid_dollars: Any, yes_ask_dollars: Any) -> Optional[float]:
    """Devig a Kalshi YES two-way to a fair YES probability (the no-vig mid).

    Kalshi prices are dollars in [0,1] = P(YES). The bid/ask straddle fair; the mid
    (yes_bid+yes_ask)/2 is the vig-free fair YES prob. Returns None on a bad/one-sided
    quote. (YES + NO straddle to ~1 by construction, so the mid is already ~devigged.)"""
    try:
        yb, ya = float(yes_bid_dollars), float(yes_ask_dollars)
    except (TypeError, ValueError):
        return None
    if not (0.0 < yb <= 1.0) or not (0.0 < ya <= 1.0) or ya < yb:
        return None
    mid = (yb + ya) / 2.0
    return mid if 0.0 < mid < 1.0 else None


def _market_type(m: Dict[str, Any]) -> str:
    """Reuse the scanner's classifier on the market's series ticker."""
    from scripts.platformkit.pm_trading.kalshi_market_scan import classify_market_type
    ser = str(m.get("ticker") or "").split("-")[0]
    return classify_market_type(ser, m.get("title"))


def find_edges(
    liquid_markets: List[Dict[str, Any]],
    pricers: Dict[str, Pricer],
    *,
    edge_floor: float = DEFAULT_EDGE_FLOOR,
) -> Dict[str, Any]:
    """Price each liquid market with the pricer for its type; emit edge candidates.

    For every market: devig the Kalshi two-way -> fair YES prob; look up
    pricers[market_type]; if a pricer returns a model prob, edge = model - fair, and we
    emit a candidate when |edge| >= edge_floor (taking the YES side on a positive edge,
    NO on a negative one). Types with no pricer are SKIPPED + counted (honest 'no model').
    Never raises. Returns {candidates, by_type, n_no_model, n_no_price, n_no_edge}."""
    candidates: List[Dict[str, Any]] = []
    by_type: Dict[str, Dict[str, int]] = {}
    n_no_model = n_no_price = n_no_edge = 0

    for m in liquid_markets:
        mt = _market_type(m)
        bucket = by_type.setdefault(mt, {"seen": 0, "priced": 0, "candidates": 0})
        bucket["seen"] += 1
        pricer = pricers.get(mt)
        if pricer is None:
            n_no_model += 1                       # we cannot honestly model this type
            continue
        fair = devig_yes(m.get("yes_bid_dollars"), m.get("yes_ask_dollars"))
        if fair is None:
            n_no_price += 1
            continue
        try:
            model_p = pricer(m)
        except Exception as exc:  # noqa: BLE001 -- a pricer must never crash the sweep
            logger.debug("kalshi_edge_finder pricer raised for %s: %s",
                         m.get("ticker"), exc)
            model_p = None
        if model_p is None or not (0.0 <= model_p <= 1.0):
            n_no_price += 1
            continue
        bucket["priced"] += 1
        edge = model_p - fair
        if abs(edge) < edge_floor:
            n_no_edge += 1
            continue
        side = "yes" if edge > 0 else "no"
        candidates.append({
            "ticker": m.get("ticker"), "market_type": mt, "venue": "kalshi",
            "side": side, "model_prob": round(model_p, 6),
            "fair_prob": round(fair, 6), "edge": round(edge, 6),
            "title": str(m.get("title") or "")[:80],
            "executed": False, "edge_claimed": False,
        })
        bucket["candidates"] += 1

    candidates.sort(key=lambda c: abs(c["edge"]), reverse=True)
    return {
        "candidates": candidates,
        "n_candidates": len(candidates),
        "by_type": by_type,
        "n_no_model": n_no_model,         # liquid markets we have no model for (skipped)
        "n_no_price": n_no_price,         # pricer returned None / bad two-way
        "n_no_edge": n_no_edge,           # priced but inside the edge floor (no bet)
        "edge_floor": edge_floor,
        "executed": False, "edge_claimed": False,
        "honest_note": ("PAPER edge candidates only (UNITS via a placer). edge = our model "
                        "prob - the DEVIGGED Kalshi fair; types we cannot model are SKIPPED, "
                        "never priced from thin air. No placement, no $ field, no edge claim."),
    }


__all__ = ["devig_yes", "find_edges", "Pricer", "DEFAULT_EDGE_FLOOR"]
