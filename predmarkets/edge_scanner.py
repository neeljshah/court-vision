"""Edge scanner for Polymarket + Kalshi.

Pipeline:
    snapshot -> Forecaster -> EdgeScanner -> ranked_edges + Kelly sizing

A Forecaster takes a market dict (from snapshot or live) and returns a
probability estimate for the YES outcome plus a confidence score. The scanner
compares each Forecaster's `prob_yes` against the market-implied `yes_ask`
(buying YES) or `1 - yes_bid` (selling YES, i.e. buying NO at the matching
price), and keeps any edge whose absolute size exceeds `edge_threshold`.

Sizing:
    - Per-bet kelly fraction f* = (b*p - q) / b  with b = decimal odds - 1.
    - Capped per-bet at 1% of bankroll (configurable).
    - Per-category cap (default 5% of bankroll across all bets in one category).
    - Total open exposure cap (default 20% of bankroll).

Slippage guard:
    - Reject any bet whose required stake would walk the book more than
      `max_slip_pp` past `yes_ask` (or `1 - yes_bid` for NO).
    - Requires an orderbook fetched via the venue client.

Output is a list of ranked edge dicts, ordered by `expected_value_dollars`
descending. Pipe into `predmarkets.dry_run_placer` (TIER 5) for execution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd


PER_BET_CAP_DEFAULT = 0.01
PER_CATEGORY_CAP_DEFAULT = 0.05
TOTAL_EXPOSURE_CAP_DEFAULT = 0.20
EDGE_THRESHOLD_DEFAULT = 0.05
MAX_SLIP_PP_DEFAULT = 0.02


@dataclass
class Forecast:
    """A single forecaster's probability estimate for a market's YES outcome."""

    market_id: str
    prob_yes: float
    confidence: float
    model_name: str
    reasoning: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.prob_yes <= 1.0:
            raise ValueError(
                f"prob_yes must be in [0, 1], got {self.prob_yes} for {self.market_id}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0, 1], got {self.confidence}"
            )


class Forecaster:
    """Base class for category-specific forecasters.

    Subclasses override `forecast(market)` to return a `Forecast` or None.
    `applies_to(market)` returns True if this forecaster can score the market.
    """

    name: str = "base"

    def applies_to(self, market: Dict[str, Any]) -> bool:
        return False

    def forecast(self, market: Dict[str, Any]) -> Optional[Forecast]:
        raise NotImplementedError


class ManualForecaster(Forecaster):
    """Forecaster backed by a hand-supplied {market_id: prob_yes} mapping.

    Useful for testing edge-scanner plumbing without a real model wired up,
    or for one-off overrides when a manual analyst price is available.
    """

    name = "manual"

    def __init__(self, probs: Dict[str, float], confidence: float = 0.5) -> None:
        self._probs = dict(probs)
        self._confidence = confidence

    def applies_to(self, market: Dict[str, Any]) -> bool:
        return str(market.get("market_id") or market.get("id") or "") in self._probs

    def forecast(self, market: Dict[str, Any]) -> Optional[Forecast]:
        mid = str(market.get("market_id") or market.get("id") or "")
        if mid not in self._probs:
            return None
        return Forecast(
            market_id=mid,
            prob_yes=float(self._probs[mid]),
            confidence=self._confidence,
            model_name=self.name,
            reasoning="manual override",
        )


def market_implied_yes_prob(market: Dict[str, Any]) -> Optional[float]:
    """Mid-of-book YES probability if both sides quoted, else best available."""
    yb = market.get("yes_bid")
    ya = market.get("yes_ask")
    if yb is not None and ya is not None:
        return (float(yb) + float(ya)) / 2.0
    if yb is not None:
        return float(yb)
    if ya is not None:
        return float(ya)
    lp = market.get("last_price")
    if lp is not None:
        return float(lp)
    return None


def _kelly_fraction(p: float, price: float) -> float:
    """Optimal Kelly fraction for a binary bet at decimal probability p, buying
    at price `price`. Returns 0 if no positive edge."""
    if price <= 0 or price >= 1:
        return 0.0
    b = (1.0 - price) / price  # net odds: $1 bet pays $b on win
    q = 1.0 - p
    f_star = (b * p - q) / b
    return max(0.0, f_star)


def _walk_book(side_ladder: Sequence[Sequence[float]], best_price: float, max_slip_pp: float, bankroll_dollars: float, stake_dollars: float) -> Dict[str, Any]:
    """Estimate effective fill price walking a book ladder.

    `side_ladder` is the side we're buying from — a list of (price, contracts)
    sorted with best-price-first. For buying YES, that's ascending price on
    the ASK side; we approximate using the same `yes` ladder semantics
    (Polymarket asks descending, Kalshi orderbook_fp yes_dollars ascending).

    Returns {effective_price, contracts_fillable, capped_by_slippage}.
    """
    if not side_ladder or best_price is None:
        return {"effective_price": None, "contracts_fillable": 0.0, "capped_by_slippage": True}
    cap_price = float(best_price) + float(max_slip_pp)
    filled = 0.0
    cost = 0.0
    remaining = stake_dollars
    capped = False
    for entry in side_ladder:
        if len(entry) < 2:
            continue
        try:
            price = float(entry[0])
            qty = float(entry[1])
        except (TypeError, ValueError):
            continue
        if price > cap_price:
            capped = True
            break
        level_cost = price * qty
        if level_cost >= remaining:
            level_qty = remaining / price if price > 0 else 0.0
            filled += level_qty
            cost += level_qty * price
            remaining = 0.0
            break
        filled += qty
        cost += level_cost
        remaining -= level_cost
    if filled == 0.0:
        return {"effective_price": None, "contracts_fillable": 0.0, "capped_by_slippage": True}
    return {
        "effective_price": cost / filled,
        "contracts_fillable": filled,
        "capped_by_slippage": capped or remaining > 0,
    }


@dataclass
class EdgeScannerConfig:
    bankroll: float = 1000.0
    per_bet_cap: float = PER_BET_CAP_DEFAULT
    per_category_cap: float = PER_CATEGORY_CAP_DEFAULT
    total_exposure_cap: float = TOTAL_EXPOSURE_CAP_DEFAULT
    edge_threshold: float = EDGE_THRESHOLD_DEFAULT
    max_slip_pp: float = MAX_SLIP_PP_DEFAULT
    kelly_fraction_of_full: float = 0.25
    min_market_volume: float = 0.0
    require_orderbook_check: bool = False


class EdgeScanner:
    """Scan a snapshot of markets, pick edges, size with Kelly + caps."""

    def __init__(self, forecasters: Sequence[Forecaster], config: Optional[EdgeScannerConfig] = None,
                 orderbook_loader: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None) -> None:
        self.forecasters = list(forecasters)
        self.cfg = config or EdgeScannerConfig()
        self._orderbook_loader = orderbook_loader

    def _pick_forecaster(self, market: Dict[str, Any]) -> Optional[Forecaster]:
        for fc in self.forecasters:
            try:
                if fc.applies_to(market):
                    return fc
            except Exception:
                continue
        return None

    def _edge_for(self, market: Dict[str, Any], fc: Forecaster) -> Optional[Dict[str, Any]]:
        forecast = fc.forecast(market)
        if forecast is None:
            return None
        vol = market.get("volume")
        if vol is not None and vol < self.cfg.min_market_volume:
            return None
        implied = market_implied_yes_prob(market)
        if implied is None:
            return None
        yb = market.get("yes_bid")
        ya = market.get("yes_ask")
        # YES edge: model says YES likelier than the price you'd PAY (yes_ask).
        # NO  edge: model says NO  likelier than 1 - yes_bid (the price you'd
        # pay buying NO, since sell-YES at yb == buy-NO at 1-yb).
        yes_price = float(ya) if ya is not None else float(implied)
        no_price = (1.0 - float(yb)) if yb is not None else float(1.0 - implied)
        yes_edge = forecast.prob_yes - yes_price
        no_edge = (1.0 - forecast.prob_yes) - no_price
        if max(yes_edge, no_edge) < self.cfg.edge_threshold:
            return None
        if yes_edge >= no_edge:
            side = "YES"
            price = yes_price
            prob_win = forecast.prob_yes
            edge_pp = yes_edge
        else:
            side = "NO"
            price = no_price
            prob_win = 1.0 - forecast.prob_yes
            edge_pp = no_edge
        kelly_full = _kelly_fraction(prob_win, price)
        kelly_used = kelly_full * self.cfg.kelly_fraction_of_full
        stake_uncapped = kelly_used * self.cfg.bankroll
        stake = min(stake_uncapped, self.cfg.per_bet_cap * self.cfg.bankroll)
        ev_per_dollar = prob_win * (1.0 - price) / price - (1.0 - prob_win)
        return {
            "venue": market.get("venue", ""),
            "market_id": market.get("market_id") or market.get("id"),
            "question": market.get("question_or_title") or market.get("question"),
            "category": market.get("category", ""),
            "side": side,
            "price": round(price, 4),
            "model_prob": round(prob_win, 4),
            "edge_pp": round(edge_pp, 4),
            "kelly_full": round(kelly_full, 4),
            "kelly_used": round(kelly_used, 4),
            "stake_dollars": round(stake, 2),
            "expected_value_dollars": round(stake * ev_per_dollar, 2),
            "confidence": forecast.confidence,
            "model_name": forecast.model_name,
            "reasoning": forecast.reasoning,
            "yes_bid": yb,
            "yes_ask": ya,
            "volume": market.get("volume"),
        }

    def _apply_orderbook_guard(self, edge: Dict[str, Any], market: Dict[str, Any]) -> Dict[str, Any]:
        if self._orderbook_loader is None:
            edge["slippage_check"] = "skipped"
            return edge
        try:
            ob = self._orderbook_loader(market)
        except Exception as exc:
            edge["slippage_check"] = f"failed: {exc}"
            if self.cfg.require_orderbook_check:
                edge["stake_dollars"] = 0.0
                edge["expected_value_dollars"] = 0.0
            return edge
        side_ladder = ob.get("asks") if edge["side"] == "YES" else ob.get("no") or ob.get("bids")
        if not side_ladder:
            edge["slippage_check"] = "no_book"
            if self.cfg.require_orderbook_check:
                edge["stake_dollars"] = 0.0
                edge["expected_value_dollars"] = 0.0
            return edge
        walk = _walk_book(side_ladder, edge["price"], self.cfg.max_slip_pp, self.cfg.bankroll, edge["stake_dollars"])
        edge["effective_price"] = walk["effective_price"]
        edge["contracts_fillable"] = walk["contracts_fillable"]
        if walk["capped_by_slippage"]:
            edge["slippage_check"] = "capped"
            if walk["effective_price"] is None:
                edge["stake_dollars"] = 0.0
                edge["expected_value_dollars"] = 0.0
            else:
                fillable_dollars = walk["contracts_fillable"] * walk["effective_price"]
                edge["stake_dollars"] = round(min(edge["stake_dollars"], fillable_dollars), 2)
                price_used = walk["effective_price"]
                ev_per_dollar = edge["model_prob"] * (1.0 - price_used) / price_used - (1.0 - edge["model_prob"])
                edge["expected_value_dollars"] = round(edge["stake_dollars"] * ev_per_dollar, 2)
        else:
            edge["slippage_check"] = "ok"
        return edge

    def _apply_caps(self, edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cat_cap_dollars = self.cfg.per_category_cap * self.cfg.bankroll
        tot_cap_dollars = self.cfg.total_exposure_cap * self.cfg.bankroll
        edges.sort(key=lambda e: -float(e.get("expected_value_dollars") or 0.0))
        cat_used: Dict[str, float] = {}
        total_used = 0.0
        for e in edges:
            cat = e.get("category") or "uncategorized"
            stake = float(e.get("stake_dollars") or 0.0)
            cat_remaining = max(0.0, cat_cap_dollars - cat_used.get(cat, 0.0))
            tot_remaining = max(0.0, tot_cap_dollars - total_used)
            allowed = min(stake, cat_remaining, tot_remaining)
            if allowed < stake:
                price_used = e.get("effective_price") or e.get("price")
                if price_used and price_used > 0:
                    ev_per_dollar = e["model_prob"] * (1.0 - price_used) / price_used - (1.0 - e["model_prob"])
                    e["expected_value_dollars"] = round(allowed * ev_per_dollar, 2)
                e["stake_dollars"] = round(allowed, 2)
                e["cap_applied"] = True
            else:
                e["cap_applied"] = False
            cat_used[cat] = cat_used.get(cat, 0.0) + allowed
            total_used += allowed
        edges.sort(key=lambda e: -float(e.get("expected_value_dollars") or 0.0))
        return edges

    def scan(self, markets: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Scan a list of market dicts; return {"edges": [...], "scanned_at": iso, ...}."""
        edges: List[Dict[str, Any]] = []
        skipped_no_forecaster = 0
        skipped_below_threshold = 0
        for m in markets:
            if m.get("status") and m["status"] != "open":
                continue
            fc = self._pick_forecaster(m)
            if fc is None:
                skipped_no_forecaster += 1
                continue
            edge = self._edge_for(m, fc)
            if edge is None:
                skipped_below_threshold += 1
                continue
            edge = self._apply_orderbook_guard(edge, m)
            edges.append(edge)
        edges = self._apply_caps(edges)
        return {
            "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_markets": len(markets),
            "n_edges": len(edges),
            "n_skipped_no_forecaster": skipped_no_forecaster,
            "n_skipped_below_threshold": skipped_below_threshold,
            "config": self.cfg.__dict__,
            "edges": edges,
        }


def load_snapshot(parquet_path: str, status: str = "open") -> List[Dict[str, Any]]:
    """Read a snapshot parquet and return rows of the given status as dicts."""
    df = pd.read_parquet(parquet_path)
    if status:
        df = df[df["status"] == status]
    return df.to_dict(orient="records")


__all__ = [
    "Forecast",
    "Forecaster",
    "ManualForecaster",
    "EdgeScanner",
    "EdgeScannerConfig",
    "market_implied_yes_prob",
    "load_snapshot",
]


def _print_edges(result: Dict[str, Any]) -> None:
    print(f"scanned {result['n_markets']} markets, {result['n_edges']} edges (skipped {result['n_skipped_no_forecaster']} no-forecaster, {result['n_skipped_below_threshold']} below-threshold)")
    print(f"{'venue':<11}{'side':<5}{'price':<8}{'model':<8}{'edge':<9}{'stake$':<10}{'EV$':<10} question")
    print("-" * 120)
    for e in result["edges"][:50]:
        q = (e.get("question") or "")[:55]
        print(f"{(e.get('venue') or '')[:10]:<11}{e['side']:<5}{e['price']:<8.4f}{e['model_prob']:<8.4f}{e['edge_pp']:<+9.4f}${e['stake_dollars']:<9.2f}${e['expected_value_dollars']:<9.2f}{q}")


def _cli(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    import os
    parser = argparse.ArgumentParser(description="Scan a snapshot parquet for edges with a manual probability overlay.")
    parser.add_argument("--snapshot", required=True, help="Path to snapshot parquet (data/pm/markets_*.parquet)")
    parser.add_argument("--overrides", default=None, help="Path to JSON {market_id: prob_yes} to drive ManualForecaster")
    parser.add_argument("--bankroll", type=float, default=1000.0)
    parser.add_argument("--threshold", type=float, default=EDGE_THRESHOLD_DEFAULT)
    parser.add_argument("--out", default=None, help="Optional path to write edges JSON")
    args = parser.parse_args(argv)
    markets = load_snapshot(args.snapshot, status="open")
    probs: Dict[str, float] = {}
    if args.overrides:
        with open(args.overrides, "r", encoding="utf-8") as fh:
            probs = {str(k): float(v) for k, v in json.load(fh).items()}
    forecaster = ManualForecaster(probs, confidence=0.4)
    cfg = EdgeScannerConfig(bankroll=args.bankroll, edge_threshold=args.threshold)
    scanner = EdgeScanner([forecaster], cfg)
    result = scanner.scan(markets)
    _print_edges(result)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli())
