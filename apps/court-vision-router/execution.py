"""Execution engine: size-weighted cross-venue fills with slippage.

This is the "large syndicate order" layer. A $100 order fills on top-of-book.
A $50,000 order has to walk the book on each venue and often split across
venues to minimize average fill price. That's what the engine does here.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from venues.base import Book


@dataclass
class VenueQuote:
    venue: str
    chain: str
    fillable_usd: float          # how much of the requested size this venue can actually take
    avg_fill_price: float        # size-weighted implied prob of the fill
    top_of_book: float           # for reporting slippage
    slippage_bps: float          # (avg - top) in basis points
    levels_consumed: int


@dataclass
class Allocation:
    venue: str
    chain: str
    size_usd: float
    avg_fill_price: float
    edge_vs_cv_pct: float


def walk_book(book: Book, target_usd: float) -> VenueQuote | None:
    """Walk asks ascending until target_usd is filled. Returns size-weighted price."""
    if not book.asks:
        return None
    remaining = target_usd
    filled_usd = 0.0
    notional_cost = 0.0
    levels_used = 0
    top = book.asks[0].price
    for lvl in book.asks:
        take = min(remaining, lvl.size)
        if take <= 0:
            break
        notional_cost += take * lvl.price
        filled_usd += take
        remaining -= take
        levels_used += 1
        if remaining <= 0:
            break
    if filled_usd == 0:
        return None
    avg = notional_cost / filled_usd
    return VenueQuote(
        venue=book.venue,
        chain="polygon" if book.venue == "polymarket" else "sx",
        fillable_usd=filled_usd,
        avg_fill_price=avg,
        top_of_book=top,
        slippage_bps=round((avg - top) * 10_000, 2),
        levels_consumed=levels_used,
    )


def route_order(
    books: list[Book],
    target_usd: float,
    cv_prob: float,
    min_edge: float = 0.02,
) -> dict:
    """Split target_usd across venues to minimize average fill price.

    Strategy: quote each venue for the full target independently (cheapest
    price walking its own book), then greedily consume venues cheapest-first
    while filtering out any venue whose avg price leaves edge < min_edge.
    """
    quotes: list[VenueQuote] = []
    for b in books:
        q = walk_book(b, target_usd)
        if q and (cv_prob - q.avg_fill_price) >= min_edge:
            quotes.append(q)
    quotes.sort(key=lambda q: q.avg_fill_price)

    remaining = target_usd
    allocs: list[Allocation] = []
    for q in quotes:
        if remaining <= 0:
            break
        take = min(remaining, q.fillable_usd)
        if take <= 0:
            continue
        allocs.append(Allocation(
            venue=q.venue,
            chain=q.chain,
            size_usd=round(take, 2),
            avg_fill_price=round(q.avg_fill_price, 4),
            edge_vs_cv_pct=round((cv_prob - q.avg_fill_price) * 100, 2),
        ))
        remaining -= take

    status = "full" if remaining <= 0 else ("partial" if remaining < target_usd else "none")
    return {
        "target_usd": target_usd,
        "cv_prob": cv_prob,
        "min_edge": min_edge,
        "quotes": [asdict(q) for q in quotes],
        "allocations": [asdict(a) for a in allocs],
        "unrouted_usd": round(max(0.0, remaining), 2),
        "status": status,
    }
