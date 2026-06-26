"""scripts.platformkit.odds_provider.pinnacle_parse -- pure Pinnacle leg parsers.

Extracted from pinnacle.py to keep that module under the 300-LOC cap. These are
the pure, network-free parsers that turn a Pinnacle straight-market `prices` list
into the extended spread / total node shape that markets.quotes_from_aggregate
consumes:

  spread -> {"home": {"line","odds"}, "away": {"line","odds"}}
  total  -> {"over": {"line","odds"}, "under": {"line","odds"}}

A node is returned ONLY when BOTH legs carry a usable line AND a price; a partial
market is dropped (never fabricated). All prices convert American -> decimal (>1.0).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no I/O.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import american_to_decimal


def _safe_points(value: Any) -> Optional[float]:
    """Parse a Pinnacle `points` handicap/total line to float; None if absent."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _two_leg_node(
    prices: List[Dict[str, Any]],
    side_a: str,
    side_b: str,
) -> Optional[Dict[str, Any]]:
    """Build a {side_a, side_b} node from a Pinnacle two-leg market's prices.

    Each price leg may carry `designation`; when it is absent OR not one of the two
    expected sides, we fall back to index order (side_a=0, side_b=1) -- this is how
    Pinnacle totals (which omit `designation`) are paired (over=0, under=1) and is
    harmless for spreads (which DO carry designation). Each leg needs a usable
    `points` line AND an American `price`; the node is returned ONLY when BOTH legs
    are complete -- a partial market yields None (never fabricated). Pure.
    """
    legs: Dict[str, Dict[str, float]] = {}
    expected = (side_a, side_b)
    for idx, pr in enumerate(prices or []):
        if not isinstance(pr, dict):
            continue
        desig = (pr.get("designation") or "").lower()
        if desig not in expected:
            desig = side_a if idx == 0 else side_b if idx == 1 else ""
        if not desig:
            continue
        line = _safe_points(pr.get("points"))
        odds = american_to_decimal(pr.get("price"))
        if line is None or odds is None:
            continue
        legs[desig] = {"line": line, "odds": odds}
    if side_a in legs and side_b in legs:
        return {side_a: legs[side_a], side_b: legs[side_b]}
    return None


def spread_node(prices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pinnacle spread market prices -> {'home','away'} node (or None)."""
    return _two_leg_node(prices, "home", "away")


def total_node(prices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pinnacle total market prices -> {'over','under'} node (or None)."""
    return _two_leg_node(prices, "over", "under")


def moneyline_sides(prices: List[Dict[str, Any]]) -> Dict[str, float]:
    """Pinnacle moneyline market prices -> {'home'?, 'away'?} decimal dict.

    Uses `designation` to map legs; falls back to index order when both are absent.
    Only sides with a usable decimal price are included (never fabricated).
    """
    h_dec: Optional[float] = None
    a_dec: Optional[float] = None
    prs = prices or []
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        desig = (pr.get("designation") or "").lower()
        dec = american_to_decimal(pr.get("price"))
        if desig == "home":
            h_dec = dec
        elif desig == "away":
            a_dec = dec
    if h_dec is None and a_dec is None and isinstance(prs, (list, tuple)) and len(prs) >= 2:
        h_dec = american_to_decimal(prs[0].get("price") if isinstance(prs[0], dict) else None)
        a_dec = american_to_decimal(prs[1].get("price") if isinstance(prs[1], dict) else None)
    out: Dict[str, float] = {}
    if h_dec is not None:
        out["home"] = h_dec
    if a_dec is not None:
        out["away"] = a_dec
    return out


__all__ = ["spread_node", "total_node", "moneyline_sides"]
