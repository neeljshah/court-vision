"""Unit tests for execution engine. No network."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from venues.base import Book, Level
from execution import walk_book, route_order


def _book(venue: str, asks: list[tuple[float, float]]) -> Book:
    return Book(venue=venue, market_id="m", asks=[Level(p, s) for p, s in asks])


def test_walk_book_single_level():
    b = _book("polymarket", [(0.55, 500)])
    q = walk_book(b, 100)
    assert q.fillable_usd == 100
    assert q.avg_fill_price == 0.55
    assert q.slippage_bps == 0
    assert q.levels_consumed == 1


def test_walk_book_consumes_multiple_levels():
    b = _book("polymarket", [(0.55, 50), (0.57, 100), (0.60, 100)])
    q = walk_book(b, 200)
    # 50 @ 0.55, 100 @ 0.57, 50 @ 0.60 = 27.5 + 57 + 30 = 114.5 over 200 = 0.5725
    assert q.fillable_usd == 200
    assert round(q.avg_fill_price, 4) == 0.5725
    assert q.levels_consumed == 3
    assert q.slippage_bps > 0


def test_route_splits_across_venues_when_one_is_thin():
    poly = _book("polymarket", [(0.55, 40)])           # cheap but only 40 USD depth
    sx = _book("sx_bet", [(0.58, 500)])                # deeper but worse price
    out = route_order([poly, sx], target_usd=300, cv_prob=0.65, min_edge=0.02)
    assert out["status"] == "full"
    venues_hit = {a["venue"] for a in out["allocations"]}
    assert venues_hit == {"polymarket", "sx_bet"}
    # cheapest venue fills first
    assert out["allocations"][0]["venue"] == "polymarket"


def test_route_skips_venue_below_edge_threshold():
    # CV = 0.60, both venues priced above 0.59 → edge < 0.02 → no route
    poly = _book("polymarket", [(0.595, 1000)])
    sx = _book("sx_bet", [(0.59, 1000)])
    out = route_order([poly, sx], target_usd=100, cv_prob=0.60, min_edge=0.02)
    assert out["status"] == "none"
    assert out["allocations"] == []


def test_route_partial_when_insufficient_depth():
    poly = _book("polymarket", [(0.55, 30)])
    sx = _book("sx_bet", [(0.56, 40)])
    out = route_order([poly, sx], target_usd=500, cv_prob=0.65, min_edge=0.02)
    assert out["status"] == "partial"
    assert out["unrouted_usd"] > 0
