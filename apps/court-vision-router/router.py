"""court-vision-router
--------------------
Cross-venue execution router for NBA prediction markets.

Pipeline:
  1. Court Vision model -> win probability for team_a
  2. For each configured Venue (Polymarket, SX Bet): find market, fetch full book
  3. Execution engine walks each book for target notional, splits across venues
     to minimize size-weighted fill price, enforces edge threshold
  4. Chain/wallet abstraction produces signed order payloads (DRY_RUN by default)

Read-only. Submission is stubbed to keep the tool capital-safe.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from dataclasses import asdict

from venues import Polymarket, SXBet
from venues.base import Book
from execution import route_order
from chain import wallet_for


def collect_books(venues, team_a: str, team_b: str) -> list[Book]:
    books: list[Book] = []
    for v in venues:
        mid = v.find_market(team_a, team_b)
        if not mid:
            books.append(Book(venue=v.name, market_id="", error="no active market found"))
            continue
        books.append(v.fetch_book(mid))
    return books


def build_payloads(venues_by_name: dict, allocations: list[dict]) -> list[dict]:
    """Turn routing allocations into signed (stub) order payloads via chain wallets."""
    payloads = []
    for a in allocations:
        v = venues_by_name[a["venue"]]
        wallet = wallet_for(v.chain)
        order = v.submit_order(
            market_id="",  # populated in live impl from book.market_id
            size_usd=a["size_usd"],
            limit_price=a["avg_fill_price"],
        )
        order["sig"] = wallet.sign_order({"size": a["size_usd"], "price": a["avg_fill_price"]})
        order["gas_usd"] = wallet.estimate_gas_usd(order)
        payloads.append(order)
    return payloads


def run(game: str, cv_prob: float, notional: float, min_edge: float, team_a: str, team_b: str) -> dict:
    venues = [Polymarket(), SXBet()]
    by_name = {v.name: v for v in venues}

    books = collect_books(venues, team_a, team_b)
    route = route_order(books, target_usd=notional, cv_prob=cv_prob, min_edge=min_edge)
    payloads = build_payloads(by_name, route["allocations"])

    return {
        "game": game,
        "court_vision_prob": cv_prob,
        "notional_usd": notional,
        "min_edge": min_edge,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "books": [
            {
                "venue": b.venue,
                "market_id": b.market_id,
                "error": b.error,
                "depth_usd": round(b.depth_usd, 2),
                "top_of_book": (b.best_ask.price if b.best_ask else None),
                "levels": len(b.asks),
            }
            for b in books
        ],
        "routing": route,
        "payloads": payloads,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-venue NBA order router")
    ap.add_argument("--game", default="Lakers vs Suns")
    ap.add_argument("--team-a", default="Lakers", help="team the CV prob is FOR")
    ap.add_argument("--team-b", default="Suns")
    ap.add_argument("--cv-prob", type=float, default=0.62)
    ap.add_argument("--notional", type=float, default=100.0)
    ap.add_argument("--min-edge", type=float, default=0.02)
    ap.add_argument("--out", default="example_output.json")
    args = ap.parse_args()

    result = run(args.game, args.cv_prob, args.notional, args.min_edge, args.team_a, args.team_b)
    print(json.dumps(result, indent=2))
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
