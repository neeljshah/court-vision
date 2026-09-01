"""scripts.platformkit.execution_model -- execution-cost modeling for PAPER
prediction-market fills. Probability units and size UNITS only, never currency.

Paper decisions in this repo are priced at the MID today, and the mid flatters
every result because it is a price nobody actually trades at. Crossing the
spread, sweeping past top-of-book depth, and ordinary slippage are real,
one-directional costs that only ever move a fill against you. State it plainly:
a strategy that only survives at mid fills is not a strategy.

This module makes no edge, ROI, or profit claim. effective_edge() is a
CALIBRATION diagnostic in probability units -- a modelled probability minus the
price actually paid -- reported so a candidate can be checked for survival once
realistic fills are charged. It is not a return and carries no currency.

Relationship to scripts/platformkit/pm_trading/fill_sim.py: that module VWAPs a
full CAPTURED depth ladder for one archived Kalshi book row and fails closed on
a stale snapshot. This one takes scalar top-of-book (bid, ask, depth) handed in
by the caller, so it can re-price decision rows that have no archived ladder.
Different input contract, so it is deliberately not a wrapper of that.

INVARIANTS: <=300 LOC; ASCII; stdlib only; reads nothing, writes nothing.
Test: python -m pytest scripts/platformkit/test_execution_model.py -q
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

BUY = "buy"
SELL = "sell"
DEFAULT_TICK = 0.01  # Kalshi-style cent tick, in probability units

# The three scenarios replay_costs() prices side by side.
MID = "mid"
CROSSING = "crossing"
CROSSING_SLIPPAGE = "crossing_slippage"
SCENARIOS = (MID, CROSSING, CROSSING_SLIPPAGE)


def _side(side: Any) -> str:
    """Normalize a side to BUY/SELL. No yes/no aliases on purpose: buying NO is
    a buy of the complementary contract, not a sell of YES, and silently
    conflating the two would misprice the book."""
    s = str(side).strip().lower()
    if s not in (BUY, SELL):
        raise ValueError("side must be 'buy' or 'sell', got %r" % (side,))
    return s


def _price(value: Any, name: str) -> float:
    v = float(value)
    if not 0.0 <= v <= 1.0:
        raise ValueError("%s must be a probability in [0, 1], got %r" % (name, value))
    return v


def _clamp(p: float) -> float:
    return min(1.0, max(0.0, p))


@dataclass(frozen=True)
class SpreadModel:
    """Prices an immediate (taker) fill against a scalar top-of-book quote.

    tick            -- price increment, in probability units.
    slippage_ticks  -- extra adverse ticks charged on every fill, standing in
                       for the queue position / latency / quote fade this model
                       cannot see. A calibration knob: set it from measured
                       fills, not from whatever makes a candidate look good.
    """

    tick: float = DEFAULT_TICK
    slippage_ticks: float = 0.0

    def __post_init__(self) -> None:
        if not self.tick > 0.0:
            raise ValueError("tick must be > 0, got %r" % (self.tick,))
        if self.slippage_ticks < 0.0:
            raise ValueError("slippage_ticks must be >= 0, got %r" % (self.slippage_ticks,))

    @staticmethod
    def mid_price(bid: Any, ask: Any) -> float:
        """The flattering baseline: the midpoint, charging no execution cost."""
        b = _price(bid, "bid")
        a = _price(ask, "ask")
        if a < b:
            raise ValueError("crossed book: ask %r < bid %r" % (ask, bid))
        return (b + a) / 2.0

    def fill_price(self, side: Any, bid: Any, ask: Any, size_units: Any,
                   depth_units: Optional[Any] = None) -> float:
        """Size-weighted fill price for taking *size_units* immediately.

        A buy lifts the ask, a sell hits the bid (crossing the spread). Any size
        beyond *depth_units* at top of book fills one tick worse -- ASSUMING
        unlimited depth at that next tick, which stays optimistic for a large
        order. depth_units=None means top of book covers the whole order;
        depth_units=0 puts the entire order at the next tick. slippage_ticks is
        charged on top. The result is clamped to [0, 1].
        """
        model_side = _side(side)
        b = _price(bid, "bid")
        a = _price(ask, "ask")
        if a < b:
            raise ValueError("crossed book: ask %r < bid %r" % (ask, bid))
        size = float(size_units)
        if not size > 0.0:
            raise ValueError("size_units must be > 0, got %r" % (size_units,))
        # Crossing the spread, and each tick past it, is always adverse.
        top = a if model_side == BUY else b
        step = self.tick if model_side == BUY else -self.tick
        if depth_units is None:
            at_top = size
        else:
            at_top = min(size, max(float(depth_units), 0.0))
        remainder = size - at_top
        vwap = (at_top * top + remainder * (top + step)) / size
        return _clamp(vwap + step * self.slippage_ticks)


def effective_edge(prob: Any, fill_price: Any, side: Any = BUY) -> float:
    """Modelled probability minus the price actually paid, in PROBABILITY units.

    Buy: prob - fill. Sell: fill - prob. Positive means the fill landed on the
    right side of the model's number; it is a calibration diagnostic, not a
    return, and it says nothing about whether that number is any good.
    """
    p = _price(prob, "prob")
    f = _price(fill_price, "fill_price")
    return p - f if _side(side) == BUY else f - p


def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    k = (len(sorted_vals) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _summary(values: List[float]) -> Dict[str, Any]:
    """Distribution of effective edges. Empty input -> n=0 and null stats."""
    if not values:
        return {"n": 0, "mean": None, "median": None, "p10": None, "p90": None,
                "min": None, "max": None, "share_positive": None}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p10": _quantile(ordered, 0.10),
        "p90": _quantile(ordered, 0.90),
        "min": ordered[0],
        "max": ordered[-1],
        "share_positive": sum(1 for v in ordered if v > 0.0) / len(ordered),
    }


def _row_edges(row: Dict[str, Any], crossing: SpreadModel,
               slipped: SpreadModel) -> Dict[str, float]:
    """Effective edge for one decision row under each of the three scenarios."""
    side = _side(row.get("side"))
    bid, ask, prob = row.get("bid"), row.get("ask"), row.get("prob")
    size = row.get("size_units", 1.0)
    depth = row.get("depth_units")
    fills = {
        MID: SpreadModel.mid_price(bid, ask),
        CROSSING: crossing.fill_price(side, bid, ask, size, depth),
        CROSSING_SLIPPAGE: slipped.fill_price(side, bid, ask, size, depth),
    }
    return {name: effective_edge(prob, price, side) for name, price in fills.items()}


def replay_costs(decision_rows: Iterable[Dict[str, Any]], *,
                 tick: float = DEFAULT_TICK,
                 slippage_ticks: float = 1.0) -> Dict[str, Any]:
    """Re-price paper decisions under (a) mid, (b) spread-crossing, (c) spread
    plus slippage, and return the three effective-edge distributions side by
    side. Any candidate that survives only in column (a) is an artifact of
    pricing at a price nobody trades at.

    Each row: {"side": "buy"|"sell", "bid", "ask", "prob", "size_units"
    (default 1.0), "depth_units" (optional), "id" (optional)}. Rows that cannot
    be priced are SKIPPED and counted with a reason, never silently defaulted.
    """
    crossing = SpreadModel(tick=tick, slippage_ticks=0.0)
    slipped = SpreadModel(tick=tick, slippage_ticks=slippage_ticks)
    edges: Dict[str, List[float]] = {name: [] for name in SCENARIOS}
    per_row: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    n_rows = 0
    for i, row in enumerate(decision_rows):
        n_rows += 1
        try:
            if not isinstance(row, dict):
                raise ValueError("row is not a dict")
            row_edges = _row_edges(row, crossing, slipped)
        except (ValueError, TypeError) as exc:
            row_id = row.get("id") if isinstance(row, dict) else None
            skipped.append({"index": i, "id": row_id, "reason": str(exc)})
            continue
        for name in SCENARIOS:
            edges[name].append(row_edges[name])
        entry: Dict[str, Any] = {"index": i, "id": row.get("id")}
        entry.update(row_edges)
        per_row.append(entry)
    return {
        "units": "probability",
        "tick": float(tick),
        "slippage_ticks": float(slippage_ticks),
        "n_rows": n_rows,
        "n_priced": len(per_row),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "scenarios": {name: _summary(edges[name]) for name in SCENARIOS},
        "per_row": per_row,
    }
