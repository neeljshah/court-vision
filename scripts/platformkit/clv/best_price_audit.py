"""best_price_audit -- "where is the +CLV on today's real slate?" (the money signal).

Runs best_price.value_bets over the LIVE aggregated odds for each sport: for every
game it takes the BEST sportsbook price on each side and compares it to the SHARP
fair (Pinnacle / cross-book median). A row appears ONLY where the best price we can
actually take beats fair -- i.e. a positive expected-CLV bet exists right now. This
is the honest, model-free edge: take a better-than-fair number, get +CLV, make money
over time. Empty output is the honest, common answer on an efficient slate.

Network: aggregates each sport once (no per-row fetch). Never fabricates a price.
No dollar-edge claim -- CLV is the yardstick.

Run:  python -m scripts.platformkit.clv.best_price_audit [--min-clv 0.5] [--sport mlb]
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv.best_price import value_bets

_DEFAULT_SPORTS = ("mlb", "soccer_intl")


def _games_for_sport(sport: str) -> List[Dict[str, Any]]:
    """Aggregate the live slate -> [{matchup, side_a, side_b, book_prices, n_books}].

    aggregate() returns an ENVELOPE dict {sport,status,sources,events:[...]}; each
    event dict carries home/away/prices {venue:{home,away,...}}. Never raises."""
    try:
        from scripts.platformkit.odds_provider.aggregate import aggregate
        env = aggregate(sport) or {}
    except Exception:  # noqa: BLE001 -- a dead source yields no games, not a crash
        return []
    games: List[Dict[str, Any]] = []
    for e in (env.get("events") or []):
        prices = e.get("prices") or {}
        home, away = e.get("home"), e.get("away")
        if not prices or not home or not away:
            continue
        # Count venues that actually quote a two-way moneyline (home & away).
        n_books = sum(1 for v in prices.values()
                      if isinstance(v, dict)
                      and v.get("home") is not None and v.get("away") is not None)
        games.append({"matchup": "%s@%s" % (away, home), "side_a": "home",
                      "side_b": "away", "book_prices": prices, "n_books": n_books})
    return games


def audit(sports: Sequence[str] = _DEFAULT_SPORTS, *, min_clv_pct: float = 0.5
          ) -> Dict[str, Any]:
    by_sport: Dict[str, Any] = {}
    total = 0
    for s in sports:
        games = _games_for_sport(s)
        vb = value_bets(games, min_clv_pct=min_clv_pct)
        nbooks = [g.get("n_books", 0) for g in games]
        # Line-shopping is only POSSIBLE where >= 2 books quote the same game.
        shoppable = sum(1 for n in nbooks if n >= 2)
        by_sport[s] = {"games_scanned": len(games), "value_bets": vb,
                       "shoppable_games": shoppable,
                       "max_books": max(nbooks) if nbooks else 0}
        total += len(vb)
    return {"min_clv_pct": min_clv_pct, "total_value_bets": total,
            "by_sport": by_sport}


def render(res: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("=" * 78)
    L.append("BEST-PRICE +CLV AUDIT -- where the best book price beats sharp fair")
    L.append("(min expected CLV >= %.2f%%; the only honest, model-free edge)"
             % res["min_clv_pct"])
    L.append("=" * 78)
    for sport, b in res["by_sport"].items():
        L.append("%-12s scanned %d games (%d shoppable >=2 books, max %d books) "
                 "-> %d +CLV bet(s)"
                 % (sport, b["games_scanned"], b["shoppable_games"],
                    b["max_books"], len(b["value_bets"])))
        for v in b["value_bets"]:
            L.append("   %-22s %-5s best %.2f @%-12s vs fair %.3f (%s)  +CLV %.2f%%"
                     % (v["matchup"], v["side"], v["best_price"], v["best_book"],
                        v["fair_prob"], v["fair_source"], v["expected_clv_pct"]))
    L.append("-" * 78)
    shoppable = sum(b["shoppable_games"] for b in res["by_sport"].values())
    if shoppable == 0:
        L.append("BINDING CONSTRAINT: 0 games have >=2 books quoting -- line-shopping "
                 "is IMPOSSIBLE with one book (you just pay its vig -> the -3.18%% CLV). "
                 "The money lever here is DATA: add more book feeds (Pinnacle auth / "
                 "FanDuel / MGM), not a smarter model.")
    elif res["total_value_bets"] == 0:
        L.append("No +CLV opportunity right now -- the slate is efficient. Honest "
                 "empty > a fabricated edge. (Lower --min-clv to widen the scan.)")
    else:
        L.append("%d +CLV bet(s): take the BEST price shown; that is the realized "
                 "edge. CLV settles the verdict." % res["total_value_bets"])
    L.append("=" * 78)
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="best-price +CLV audit")
    p.add_argument("--min-clv", type=float, default=0.5, help="min expected CLV %%")
    p.add_argument("--sport", default=None, help="one sport (default: all live)")
    a = p.parse_args(argv)
    sports = (a.sport,) if a.sport else _DEFAULT_SPORTS
    print(render(audit(sports, min_clv_pct=a.min_clv)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
