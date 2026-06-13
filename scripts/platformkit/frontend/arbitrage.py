"""scripts.platformkit.frontend.arbitrage — honest cross-book arb/middle/devig.

HONEST: markets are efficient and NO model edge is ever claimed here. The only
value surfaced is cross-book line-shopping / arbitrage / devig — which exists
ONLY when >=2 distinct books quote the same outcome. With a single book (as
on-disk corpora carry) every detector degrades gracefully to an empty result
plus an explicit insufficient-books note.

PURE module: stdlib only (math, typing). No numpy. No codebase package imports
(devig math is reproduced here); a frontend caller may import THIS module
one-directionally; never the reverse.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

# --- honest labels (every output carries one; NOT model alpha) ---------------
ARB_VALUE_LABEL = (
    "cross-book arbitrage value (NOT model alpha) — risk-free return % from "
    "line-shopping across books; markets are efficient, no model edge claimed"
)
MIDDLE_VALUE_LABEL = (
    "cross-book middle value (NOT model alpha) — window where both legs may "
    "win from line-shopping across books; not a model edge"
)
DEVIG_LABEL = (
    "fair (no-vig) probabilities from a single book's prices (NOT model alpha) "
    "— diagnostic devig only, not a model edge"
)
INSUFFICIENT_BOOKS_NOTE = (
    "Fewer than 2 distinct books available — cross-book arbitrage/middle value "
    "cannot exist with a single book. Showing none (this is line-shop/arb value "
    "only, NOT model alpha)."
)


# --- odds conversions (stdlib) ----------------------------------------------
def american_to_decimal(odds: Any) -> Optional[float]:
    """American odds -> decimal odds. None/0/non-numeric -> None."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0.0:
        return None
    return 1.0 + o / 100.0 if o > 0 else 1.0 + 100.0 / abs(o)


def decimal_to_implied(d: Any) -> Optional[float]:
    """Decimal odds -> raw (vigged) implied probability = 1/d."""
    try:
        dv = float(d)
    except (TypeError, ValueError):
        return None
    return 1.0 / dv if dv > 0.0 else None


def implied_to_decimal(p: Any) -> Optional[float]:
    """Implied probability -> decimal odds = 1/p."""
    try:
        pv = float(p)
    except (TypeError, ValueError):
        return None
    return 1.0 / pv if pv > 0.0 else None


# --- devig (pure reproduction; codebase devig module is NOT loaded) ----------
def devig_proportional(implied: Sequence[float]) -> List[float]:
    """p_i = pi_i / sum(pi). Falls back to uniform if total <= 0."""
    pi = [float(p) for p in implied]
    total = sum(pi)
    if total <= 0.0:
        n = len(pi) or 1
        return [1.0 / n] * len(pi)
    return [p / total for p in pi]


def devig_multiplicative(implied: Sequence[float], *, max_iter: int = 200,
                         tol: float = 1e-12) -> List[float]:
    """Find k with sum(pi_i^k)=1 by bisection, return pi_i^k normalized."""
    pi = [float(p) for p in implied]
    if any(p <= 0.0 for p in pi) or sum(pi) <= 1.0 + 1e-12:
        return devig_proportional(pi)
    total = lambda k: sum(p ** k for p in pi)  # noqa: E731
    lo, hi = 0.5, 8.0
    if total(lo) < 1.0:
        lo = 0.01
    if total(hi) > 1.0:
        hi = 32.0
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if total(mid) > 1.0 else (lo, mid)
        if hi - lo < tol:
            break
    out = [p ** (0.5 * (lo + hi)) for p in pi]
    z = sum(out)
    return [x / z for x in out] if z > 0 else devig_proportional(pi)


def devig_power(implied: Sequence[float], n: Optional[int] = None) -> List[float]:
    """pi_i^(1/n) / Z, default n = len(implied)."""
    pi = [float(p) for p in implied]
    if any(p <= 0.0 for p in pi):
        return devig_proportional(pi)
    n = len(pi) if n is None else n
    if n <= 0:
        return devig_proportional(pi)
    out = [p ** (1.0 / float(n)) for p in pi]
    z = sum(out)
    return [x / z for x in out] if z > 0 else devig_proportional(pi)


def devig_shin(implied: Sequence[float], *, max_iter: int = 64,
               tol: float = 1e-12) -> List[float]:
    """Shin (1992) bisection on z in [0,1). Fallback proportional if degenerate."""
    pi = [float(p) for p in implied]
    s = sum(pi)
    if s <= 1.0 or any(p <= 0.0 for p in pi):
        return devig_proportional(pi)
    p_of_z = lambda z, q: (  # noqa: E731
        math.sqrt(z * z + 4.0 * (1.0 - z) * q * q / s) - z) / (2.0 * (1.0 - z))
    lo, hi = 0.0, 1.0 - 1e-9
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if sum(p_of_z(mid, q) for q in pi) > 1.0 else (lo, mid)
        if hi - lo < tol:
            break
    z = 0.5 * (lo + hi)
    out = [p_of_z(z, q) for q in pi]
    total = sum(out)
    return [p / total for p in out] if total > 0 else devig_proportional(pi)


_DEVIG_METHODS = {"proportional": devig_proportional,
                  "multiplicative": devig_multiplicative,
                  "power": devig_power, "shin": devig_shin}


def devig_fair_probs(outcomes: Sequence[Dict[str, Any]],
                     method: str = "multiplicative") -> Optional[Dict[str, Any]]:
    """outcomes=[{"side","decimal_odds"},...] -> fair (no-vig) probs + overround."""
    sides: List[str] = []
    implied: List[float] = []
    for o in outcomes:
        p = decimal_to_implied(o.get("decimal_odds"))
        if p is None:
            return None
        sides.append(o.get("side"))
        implied.append(p)
    if not implied:
        return None
    fn = _DEVIG_METHODS.get((method or "multiplicative").lower(), devig_multiplicative)
    fair = fn(implied)
    return {
        "method": (method or "multiplicative").lower(),
        "fair_probs": {s: fp for s, fp in zip(sides, fair)},
        "overround": sum(implied) - 1.0, "label": DEVIG_LABEL,
    }


# --- arbitrage --------------------------------------------------------------
def _best_per_side(market: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """For each side, the book with the max decimal_odds."""
    best: Dict[str, Dict[str, Any]] = {}
    for b in market.get("books", []):
        side, d = b.get("side"), b.get("decimal_odds")
        if side is None or d is None:
            continue
        try:
            dv = float(d)
        except (TypeError, ValueError):
            continue
        cur = best.get(side)
        if cur is None or dv > cur["decimal_odds"]:
            best[side] = {"side": side, "book": b.get("book"), "decimal_odds": dv}
    return best


def _distinct_books(market: Dict[str, Any]) -> int:
    return len({b.get("book") for b in market.get("books", []) if b.get("book") is not None})


def detect_arbitrage(game: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best decimal per side across books; arb iff sum(1/d_i) < 1.

    None if any market lacks all outcomes or <2 distinct books contribute;
    returns the first arbitrage found across the game's markets.
    """
    for mkt_name, market in game.get("markets", {}).items():
        outcomes = market.get("outcomes", [])
        best = _best_per_side(market)
        if not outcomes or any(side not in best for side in outcomes):
            continue
        if len({best[side]["book"] for side in outcomes}) < 2:
            continue
        legs = [best[side] for side in outcomes]
        s = sum(1.0 / leg["decimal_odds"] for leg in legs)
        if s >= 1.0:
            continue
        return {
            "type": "arbitrage", "event_id": game.get("event_id"),
            "sport": game.get("sport"), "market": mkt_name, "inverse_sum": s,
            "return_pct": (1.0 / s - 1.0) * 100.0,
            "legs": [{"side": leg["side"], "book": leg["book"],
                      "decimal_odds": leg["decimal_odds"],
                      "stake_fraction": (1.0 / leg["decimal_odds"]) / s} for leg in legs],
            "label": ARB_VALUE_LABEL,
        }
    return None


# --- middles ----------------------------------------------------------------
def _line_book_entries(market: Dict[str, Any], side: str) -> List[Dict[str, Any]]:
    out = []
    for b in market.get("books", []):
        if b.get("side") != side or b.get("line") is None or b.get("decimal_odds") is None:
            continue
        try:
            out.append({"book": b.get("book"), "line": float(b["line"]),
                        "decimal": float(b["decimal_odds"])})
        except (TypeError, ValueError):
            continue
    return out


def detect_middles(game: Dict[str, Any], *, min_width: float = 0.5,
                   max_width: float = 10.0) -> List[Dict[str, Any]]:
    """Pair a low-side line@bookA with an opposing high-side line@bookB.

    Spread/total markets: width = high_line - low_line in [min_width, max_width];
    worst = min(decimals); is_free_arb when both decimals > 2.0; arb_return_pct
    via inverse-sum when < 1 else None.
    """
    results: List[Dict[str, Any]] = []
    markets = game.get("markets", {})
    for mkt_name in ("total", "spread"):
        market = markets.get(mkt_name)
        if not market or len(market.get("outcomes", [])) != 2:
            continue
        low_side, high_side = market["outcomes"][0], market["outcomes"][1]
        lows = _line_book_entries(market, low_side)
        highs = _line_book_entries(market, high_side)
        for lo in lows:
            for hi in highs:
                width = hi["line"] - lo["line"]
                if lo["book"] == hi["book"] or width < min_width or width > max_width:
                    continue
                s = 1.0 / lo["decimal"] + 1.0 / hi["decimal"]
                results.append({
                    "type": "middle", "event_id": game.get("event_id"),
                    "sport": game.get("sport"), "market": mkt_name, "width": width,
                    "low_leg": {"side": low_side, "book": lo["book"],
                                "line": lo["line"], "decimal_odds": lo["decimal"]},
                    "high_leg": {"side": high_side, "book": hi["book"],
                                 "line": hi["line"], "decimal_odds": hi["decimal"]},
                    "worst": min(lo["decimal"], hi["decimal"]),
                    "is_free_arb": lo["decimal"] > 2.0 and hi["decimal"] > 2.0,
                    "arb_return_pct": (1.0 / s - 1.0) * 100.0 if s < 1.0 else None,
                    "label": MIDDLE_VALUE_LABEL,
                })
    results.sort(key=lambda r: (r["is_free_arb"], r["width"], r["worst"]), reverse=True)
    return results


# --- top-level slate scan ---------------------------------------------------
def scan_slate(slate: Sequence[Dict[str, Any]], *, devig_method: str = "multiplicative",
               min_middle_width: float = 0.5) -> Dict[str, Any]:
    """Scan a normalized slate; graceful degrade per game when <2 books."""
    arbitrage: List[Dict[str, Any]] = []
    middles: List[Dict[str, Any]] = []
    devig: List[Dict[str, Any]] = []
    n_multibook = 0
    for game in slate:
        markets = game.get("markets", {})
        if any(_distinct_books(m) >= 2 for m in markets.values()):
            n_multibook += 1
        arb = detect_arbitrage(game)
        if arb is not None:
            arbitrage.append(arb)
        middles.extend(detect_middles(game, min_width=min_middle_width))
        for mkt_name, market in markets.items():
            best = _best_per_side(market)
            outcomes = market.get("outcomes", [])
            if not outcomes or any(s not in best for s in outcomes):
                continue
            fair = devig_fair_probs(
                [{"side": s, "decimal_odds": best[s]["decimal_odds"]} for s in outcomes],
                method=devig_method)
            if fair is not None:
                fair["event_id"] = game.get("event_id")
                fair["market"] = mkt_name
                devig.append(fair)
    note = ("Cross-book line-shop / arbitrage / devig scan (NOT model alpha)."
            if n_multibook else INSUFFICIENT_BOOKS_NOTE)
    return {
        "arbitrage": arbitrage, "middles": middles, "devig": devig,
        "n_games": len(slate), "n_multibook_games": n_multibook, "note": note,
        "value_class": "line-shop/arb only — NOT model alpha",
    }
