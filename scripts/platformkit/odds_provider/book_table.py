"""scripts.platformkit.odds_provider.book_table -- line-shopping table per card.

For ONE merged aggregate event, build a per-market / per-side table listing EVERY
contributing book, its price, and its freshness, and mark the single best FRESH
BETTABLE (sportsbook, not prediction-market) price per side. This is the field a
UI renders to show "each bet shown with its line + best book" line-shopping.

Input
-----
event       : one aggregate() event dict (OddsEvent.to_dict() shape) carrying
              prices = {venue: {"home","away","draw"?, "spread"?, "total"?}}.
venue_as_of : {venue: ISO-8601 captured_at | None} -- per-book timestamps. A book
              absent from this map, or with a None/unparseable value, is treated as
              STALE (stale-never-green: unknown timestamps are never trusted fresh).
              When omitted, the event's own as_of is used as a conservative fallback
              for EVERY book (so all books share one honest slate timestamp).

Output (book_table_for_event)
-----------------------------
{ (market_type, side): {
    "books": [ {"book","price","line"?,"as_of","fresh","is_pm"} , ... ],
    "best":  {"book","price","line"?} | None   # best FRESH SPORTSBOOK price; PM
                                               # books and stale books never win;
                                               # None when no fresh bettable book.
} }

Honesty rails (binding, mirror best_line_fresh + fresh_best_line):
  * Prediction-market venues (Kalshi/Polymarket) are listed (is_pm=True) but NEVER
    selected as best -- they are not bettable sportsbook lines.
  * A STALE (or unknown-timestamp) book NEVER beats a fresh lower price.
  * Best = highest decimal odds (bettor-favourable) among fresh sportsbooks only.
  * Prices <= 1.0 are invalid and excluded. Never fabricates a price or a line.
  * Pure: no network, time injectable via now=. Never raises.

build_on: base.venue_type/VENUE_SPORTSBOOK (read-only), freshness.freshness_status
          (pure), MARKET_MAX_AGE per-market SLAs.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .base import VENUE_SPORTSBOOK, venue_type
from .freshness import DEFAULT_MAX_AGE_SEC, freshness_status

# Market identifiers (mirror markets.MONEYLINE/SPREAD/TOTAL without importing it).
MONEYLINE = "moneyline"
SPREAD = "spread"
TOTAL = "total"

# (market_type, side, line) extraction per venue side-dict.
_ML_SIDES = ("home", "away", "draw")
_SPREAD_SIDES = ("home", "away")
_TOTAL_SIDES = ("over", "under")


def _decimal(value: Any) -> Optional[float]:
    """A usable decimal price (> 1.0) or None. Never fabricates."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 1.0 else None


def _line(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iter_venue_quotes(
    venue: str, sides: Dict[str, Any],
) -> List[Tuple[str, str, Optional[float], float]]:
    """Flatten one venue's side-dict to (market_type, side, line, price) tuples.

    Handles the flat moneyline keys (home/away/draw) and the extended spread/total
    nodes ({side: {'line','odds'}}). A side missing a usable price (or, for
    spread/total, a line) is dropped -- never fabricated.
    """
    out: List[Tuple[str, str, Optional[float], float]] = []
    if not isinstance(sides, dict):
        return out
    # Moneyline: flat decimal under home/away/draw.
    for side in _ML_SIDES:
        price = _decimal(sides.get(side))
        if price is not None:
            out.append((MONEYLINE, side, None, price))
    # Spread / total: extended nodes.
    for market, side_names in ((SPREAD, _SPREAD_SIDES), (TOTAL, _TOTAL_SIDES)):
        node = sides.get(market)
        if not isinstance(node, dict):
            continue
        for side in side_names:
            leg = node.get(side)
            if not isinstance(leg, dict):
                continue
            price = _decimal(leg.get("odds"))
            line = _line(leg.get("line"))
            if price is not None and line is not None:
                out.append((market, side, line, price))
    return out


def _resolve_as_of(
    venue: str,
    venue_as_of: Optional[Dict[str, Optional[str]]],
    fallback_as_of: Optional[str],
) -> Optional[str]:
    """Per-venue timestamp: explicit map value, else the slate-level fallback.

    A venue PRESENT in the map with a None value keeps None (caller knows it is
    unknown -> stale). A venue ABSENT from the map falls back to the slate as_of
    (the conservative shared timestamp). When no map is given, every venue uses
    the fallback.
    """
    if venue_as_of is not None and venue in venue_as_of:
        return venue_as_of.get(venue)
    return fallback_as_of


def book_table_for_event(
    event: Dict[str, Any],
    venue_as_of: Optional[Dict[str, Optional[str]]] = None,
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    max_age_override: Optional[Dict[str, float]] = None,
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Build the line-shopping table for one merged aggregate event.

    Returns a dict keyed by (market_type, side) -> {"books": [...], "best": {...}|None}.
    Each book entry: {"book","price","line"|None,"as_of","fresh","is_pm"}. "best"
    is the highest-decimal FRESH SPORTSBOOK price (PM books and stale books never
    win); None when no fresh bettable book exists for that side.

    Pure + total: never raises (garbage event -> {}). market_type drives the
    per-market freshness SLA (moneyline/spread 15min, total 30min) via freshness.
    """
    try:
        return _build(event, venue_as_of, now, max_age_sec, max_age_override)
    except Exception:  # noqa: BLE001 -- table build must never sink a caller
        return {}


def _build(
    event: Dict[str, Any],
    venue_as_of: Optional[Dict[str, Optional[str]]],
    now: Optional[datetime],
    max_age_sec: float,
    max_age_override: Optional[Dict[str, float]],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    prices = event.get("prices") if isinstance(event, dict) else None
    if not isinstance(prices, dict):
        return {}
    fallback = str(event.get("as_of") or "").strip() or None
    table: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for venue, sides in prices.items():
        if not venue or not isinstance(sides, dict):
            continue
        is_pm = venue_type(str(venue)) != VENUE_SPORTSBOOK
        as_of = _resolve_as_of(str(venue), venue_as_of, fallback)
        for market, side, line, price in _iter_venue_quotes(str(venue), sides):
            fs = freshness_status(
                as_of, now=now, max_age_sec=max_age_sec,
                market_type=market, max_age_override=max_age_override)
            fresh = fs["status"] == "fresh"
            entry: Dict[str, Any] = {
                "book": str(venue), "price": price, "line": line,
                "as_of": as_of, "fresh": fresh, "is_pm": is_pm,
            }
            cell = table.setdefault((market, side), {"books": [], "best": None})
            cell["books"].append(entry)
            # Best = highest decimal among FRESH SPORTSBOOK books only.
            if fresh and not is_pm:
                best = cell["best"]
                if best is None or price > best["price"]:
                    cell["best"] = {"book": str(venue), "price": price,
                                    "line": line}
    return table


def book_table_to_jsonable(
    table: Dict[Tuple[str, str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Flatten the (market,side)-keyed table to a JSON-serialisable card list.

    Each row: {"market_type","side","books":[...],"best":{...}|None}. Tuple keys
    are not JSON-safe, so this is the shape a UI / API layer should serialise. The
    "books" list is sorted best-bettable-first: fresh sportsbooks by descending
    price, then stale/PM books after (so the line-shopping view leads with the
    actually-backable number).
    """
    rows: List[Dict[str, Any]] = []
    for (market, side), cell in table.items():
        books = list(cell.get("books") or [])
        books.sort(key=lambda b: (
            0 if (b.get("fresh") and not b.get("is_pm")) else 1,
            -float(b.get("price") or 0.0),
        ))
        rows.append({
            "market_type": market, "side": side,
            "books": books, "best": cell.get("best"),
        })
    rows.sort(key=lambda r: (r["market_type"], r["side"]))
    return rows


__all__ = [
    "book_table_for_event",
    "book_table_to_jsonable",
    "MONEYLINE",
    "SPREAD",
    "TOTAL",
]
