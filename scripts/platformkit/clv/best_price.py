"""best_price -- price-edge (CLV) detection: where the BEST available price beats fair.

The honest, model-free money lever. A sharp does not bet because a model disagrees
with a book (that is mostly model overconfidence on an efficient market); a sharp
bets when the BEST price they can actually take is better than the SHARP fair --
i.e. positive expected CLV at the moment of the bet. Do that systematically and CLV
is positive by construction; that is the only thing that reliably makes money.

This module is PURE (no network):
  * sharp_fair(book_prices)   -- no-vig fair from the sharp anchor (Pinnacle if
    present, else the cross-book median), INDEPENDENT of the book we would take.
  * best_price(book_prices)   -- highest (bettor-favourable) decimal per side + book
    (sportsbooks only by default, so a thin PM ask never wins a bettable best).
  * price_edge(...)           -- expected CLV% of taking the best price for a side
    vs the sharp fair. Positive = we are getting a better-than-fair number = value.
  * value_bets(...)           -- the +CLV opportunities on a slate at a min threshold.

Reuses the vetted Shin devig (odds_shop.devig_twoway / best_line). Never fabricates
a price; a side without a real two-way degrades to None, never an invented number.
No dollar-edge claim -- CLV is the measured yardstick. ASCII, <=300 LOC.

Per-file test: scripts/platformkit/clv/test_best_price.py
"""
from __future__ import annotations

import math
import os
import statistics
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.odds_shop import best_line, devig_twoway
from scripts.platformkit.odds_provider.base import VENUE_SPORTSBOOK

_SHARP_ANCHOR = "pinnacle"  # the reference sharp book when present


def _both(prices: Dict[str, float], a: str, b: str) -> Optional[Tuple[float, float]]:
    pa, pb = prices.get(a), prices.get(b)
    try:
        pa, pb = float(pa), float(pb)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(pa) and math.isfinite(pb)):
        return None
    if pa <= 1.0 or pb <= 1.0:
        return None
    return pa, pb


def _safe_devig(pa: float, pb: float) -> Optional[Tuple[float, float]]:
    """Shin devig that NEVER raises. None when the input cannot be devigged: a
    sub-1.0 booksum (stale/arb quote) must yield NO fair price here -- since
    634fdd1a devig_twoway normalizes instead of raising, the reject is explicit
    (opus judge 2026-07-12 BLOCKER 2: a synthesized fair from a broken sharp
    quote would mint phantom is_value/expected_clv_pct rows)."""
    try:
        if (1.0 / pa + 1.0 / pb) < 1.0 - 1e-9:
            return None  # strict arb only; booksum==1.0 is an honest vig-free fair
        fa, fb = devig_twoway(pa, pb)
        return float(fa), float(fb)
    except Exception:  # noqa: BLE001 -- a bad quote must not crash the scan
        return None


def sharp_fair(book_prices: Dict[str, Dict[str, float]], side_a: str, side_b: str
               ) -> Optional[Dict[str, Any]]:
    """No-vig fair probs for (side_a, side_b) from the SHARP anchor, independent of
    the book we would take. Pinnacle if it quotes both sides, else the cross-book
    median of each book's devigged fair. None if no book quotes a real two-way."""
    # Prefer the sharp anchor.
    for name, prices in book_prices.items():
        if str(name).lower() != _SHARP_ANCHOR:
            continue
        tw = _both(prices, side_a, side_b)
        if tw:
            dv = _safe_devig(*tw)
            if dv:
                return {"fair_a": round(dv[0], 6), "fair_b": round(dv[1], 6),
                        "source": _SHARP_ANCHOR}
    # Fallback: median of each book's own devigged fair.
    fas: List[float] = []
    fbs: List[float] = []
    for prices in book_prices.values():
        tw = _both(prices, side_a, side_b)
        if not tw:
            continue
        dv = _safe_devig(*tw)
        if not dv:
            continue
        fas.append(dv[0])
        fbs.append(dv[1])
    if not fas:
        return None
    ma, mb = statistics.median(fas), statistics.median(fbs)
    tot = ma + mb
    if tot <= 0:
        return None
    return {"fair_a": round(ma / tot, 6), "fair_b": round(mb / tot, 6),
            "source": "median(%d books)" % len(fas)}


def best_price(book_prices: Dict[str, Dict[str, float]], side: str,
               *, sportsbook_only: bool = True) -> Optional[Dict[str, Any]]:
    """Highest decimal + book for *side*, sportsbooks only by default."""
    restrict = VENUE_SPORTSBOOK if sportsbook_only else None
    best = best_line(book_prices, restrict_to=restrict)
    b = best.get(side)
    if not b:
        return None
    return {"book": b["book"], "price": round(float(b["price"]), 4)}


def price_edge(book_prices: Dict[str, Dict[str, float]], side_a: str, side_b: str,
               side: str, *, sportsbook_only: bool = True) -> Optional[Dict[str, Any]]:
    """Expected CLV% of taking the best price for *side* vs the sharp fair.

    Positive => the best number we can take is better than fair = value. None when
    the fair or the best price is unavailable (never fabricated)."""
    fair = sharp_fair(book_prices, side_a, side_b)
    bp = best_price(book_prices, side, sportsbook_only=sportsbook_only)
    if fair is None or bp is None:
        return None
    fair_side = fair["fair_a"] if side == side_a else fair["fair_b"]
    taken_implied = 1.0 / bp["price"]
    clv_pct = (fair_side - taken_implied) / taken_implied * 100.0
    return {
        "side": side, "best_book": bp["book"], "best_price": bp["price"],
        "taken_implied": round(taken_implied, 6),
        "fair_prob": round(fair_side, 6), "fair_source": fair["source"],
        "expected_clv_pct": round(clv_pct, 4),
        "is_value": clv_pct > 0.0,
    }


def value_bets(games: Sequence[Dict[str, Any]], *, min_clv_pct: float = 0.0,
               sportsbook_only: bool = True) -> List[Dict[str, Any]]:
    """Scan games for +CLV opportunities.

    Each game: {"matchup", "side_a", "side_b", "book_prices"}. Returns the side(s)
    whose best price clears *min_clv_pct* over fair, richest CLV first."""
    out: List[Dict[str, Any]] = []
    for g in games:
        bp = g.get("book_prices") or {}
        sa, sb = g.get("side_a"), g.get("side_b")
        if not sa or not sb:
            continue
        for side in (sa, sb):
            pe = price_edge(bp, sa, sb, side, sportsbook_only=sportsbook_only)
            if pe and pe["expected_clv_pct"] >= min_clv_pct and pe["is_value"]:
                out.append({"matchup": g.get("matchup"), **pe})
    out.sort(key=lambda r: -r["expected_clv_pct"])
    return out
