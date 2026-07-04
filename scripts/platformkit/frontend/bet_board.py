"""scripts.platformkit.frontend.bet_board -- the per-game multi-sport BET BOARD.

The advanced successor to the old NBA bet card: for ONE game it lists EVERY bet
available (moneyline, spread/run-line/handicap ladders, totals, team totals,
periods, derived props) with the model's probability, the model's fair odds, the
best available BOOK price where one exists, the EV at that price, and a ranked
"best bets" list -- all in ONE uniform schema the front end renders generically.

Honesty contract (binding):
  * The model's PROB and FAIR ODDS come straight off the calibrated predictor
    surface (predict_matchup.build_result). They are a model VIEW, not a claimed
    edge. fair_odds = 1 / model_prob (decimal).
  * EV is shown ONLY where a real BOOK price exists (attached from odds_lookup --
    mainly moneyline, and totals/spreads when the feed quotes them). ev_pct =
    model_prob * best_price - 1. A +EV vs a soft book is a line-shopping execution
    opportunity, NOT a beat-the-close edge -- the model does not beat the sharp
    close. Where no book price exists, best_*/ev are null and only fair_odds shows.
  * best_bets ranks by ev_pct when prices exist (only +/-near-zero-EV shown), else
    by model confidence |p-0.5| with an explicit "model view, not a priced edge"
    note. Never a fabricated price, never a fabricated edge.

INVARIANTS: never edit src/ or kernel/; reuse the domain predictors; <=300 LOC;
no secrets; no $ edge claimed.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit import odds_shop
from scripts.platformkit import predict_matchup as pm
from scripts.platformkit.frontend import bet_board_flat as flat

logger = logging.getLogger(__name__)

SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis", "wnba", "npb", "kbo")

HONEST_NOTE = (
    "Model prob + fair odds are a calibrated model VIEW, not a claimed edge. EV is "
    "shown ONLY where a real book price exists (line-shopping, an execution edge -- "
    "the model does not beat the sharp close). Derived markets with no book price "
    "show fair odds only. YOU place every bet manually. No $ edge is claimed."
)

# Best bets considers a bet 'priced' (rank by EV) only above this EV; below it the
# row is still shown but is not promoted as a priced opportunity.
_EV_FLOOR = -0.02
_BEST_CAP = 8


def _ns(sport: str, home: str, away: str, surface: str,
        live: Optional[Dict[str, Any]] = None) -> argparse.Namespace:
    """Build the predict_matchup-shaped namespace. When *live* is supplied, map its
    generic fields onto the sport-appropriate flags so build_result emits an in-game
    block (predict_matchup.live_kwargs ignores partial/inapplicable states)."""
    ns = argparse.Namespace(
        sport=sport, home=home, away=away, surface=surface,
        elapsed=None, inning=None, half=None, home_score=None, away_score=None,
        sets_home=None, sets_away=None, games_home=None, games_away=None)
    if isinstance(live, dict):
        ns._live = True
        ns.elapsed = live.get("elapsed", live.get("minute"))
        ns.inning = live.get("inning")
        ns.half = live.get("half")
        ns.home_score = live.get("home_score")
        ns.away_score = live.get("away_score")
        ns.sets_home = live.get("sets_home")
        ns.sets_away = live.get("sets_away")
        ns.games_home = live.get("games_home")
        ns.games_away = live.get("games_away")
    return ns


def _fair_odds(prob: Optional[float]) -> Optional[float]:
    """Decimal fair odds = 1 / prob. None / non-positive prob -> None."""
    if not isinstance(prob, (int, float)) or prob <= 0.0 or prob >= 1.0:
        return None
    return round(1.0 / float(prob), 4)


# Group names that carry the head-to-head / match-winner market across sports.
# NBA/MLB/WNBA/NPB/KBO emit "Moneyline"; soccer/soccer_intl emit "1X2" (a 3-way
# market -- Home/Draw/Away -- per bet_board_flat.flatten_soccer). Both are the
# same conceptual seam (the reliably shoppable market via our keyless feed);
# book prices attach to selections in EITHER group, never elsewhere.
_H2H_GROUPS = ("Moneyline", "1X2")


def _moneyline_prices(book_prices: Optional[Dict[str, Dict[str, float]]],
                      home: str, away: str) -> Dict[str, Optional[Dict[str, Any]]]:
    """Best book+price per side from the multi-book head-to-head dict (keyed by
    team name or "Draw", per to_odds_lookup). Absent -> None entries (never
    fabricated). Keeps every side the feed quotes (not just home/away) so a
    soccer "Draw" price -- when a book quotes one -- can still attach."""
    if not book_prices:
        return {home: None, away: None}
    try:
        best = odds_shop.best_line(book_prices)
    except Exception as exc:  # noqa: BLE001 -- shopping never sinks the board
        logger.warning("best_line failed: %s", exc)
        return {home: None, away: None}
    out = dict(best)
    out.setdefault(home, None)
    out.setdefault(away, None)
    return out


def _enrich(rows: List[Dict[str, Any]], home: str, away: str,
            book_prices: Optional[Dict[str, Dict[str, float]]]) -> List[Dict[str, Any]]:
    """Attach fair_odds to every row + best_book/best_price/ev_pct/verdict.

    Book price is attached ONLY to head-to-head rows (Moneyline for nba/mlb/
    wnba/npb/kbo, 1X2 for soccer/soccer_intl -- the reliably shoppable market
    via our keyless feed): the selection string equals the team name (or
    "Draw" for soccer, when a book quotes one). All other rows get fair_odds +
    a model-view verdict, best_*/ev null.
    """
    ml_best = _moneyline_prices(book_prices, home, away)
    out: List[Dict[str, Any]] = []
    for r in rows:
        prob = r.get("model_prob")
        fair = _fair_odds(prob)
        best = ml_best.get(r.get("selection")) if r.get("group") in _H2H_GROUPS else None
        price = best["price"] if best else None
        book = best["book"] if best else None
        ev = None
        verdict = "MODEL_VIEW"
        note = "model view (no book price); fair odds shown"
        if price is not None and isinstance(prob, (int, float)):
            ev = round(odds_shop.ev_vs_price(prob, price), 4)
            verdict = "PRICED+EV" if ev > 0 else "PRICED"
            note = ("EV vs best book price (line-shopping, not a beat-the-close edge)"
                    if ev > 0 else "priced; model EV non-positive at this price")
        out.append({
            "group": r["group"], "selection": r["selection"],
            "model_prob": prob, "line": r.get("line"),
            "fair_odds": fair, "best_book": book, "best_price": price,
            "ev_pct": (round(ev * 100.0, 2) if ev is not None else None),
            "verdict": verdict, "note": note,
        })
    return out


def _rank_best(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Top ~8 best bets. Priced rows (ev_pct not None) rank by EV desc and must
    clear the EV floor; if none are priced, fall back to model confidence |p-0.5|
    (labelled a model view, not a priced edge)."""
    priced = [r for r in rows if r.get("ev_pct") is not None
              and r["ev_pct"] / 100.0 >= _EV_FLOOR]
    if priced:
        priced.sort(key=lambda r: r["ev_pct"], reverse=True)
        return priced[:_BEST_CAP]
    # No book prices: we cannot rank by edge. Surface the model's highest-CONVICTION
    # FAVORED selections (p >= 0.5), ranked by |p-0.5|, and labelled a model view --
    # NOT a priced edge. We exclude the dominated under-0.5 side of each pair so the
    # list is confident picks, not mirror longshots.
    conf = [r for r in rows if isinstance(r.get("model_prob"), (int, float))
            and r["model_prob"] >= 0.5]
    conf.sort(key=lambda r: r["model_prob"], reverse=True)
    top = conf[:_BEST_CAP]
    for r in top:
        if r.get("note", "").startswith("model view"):
            r["note"] = ("ranked by model confidence -- a model VIEW, NOT a priced "
                         "edge (no book price available for this market)")
    return top


def _live_block(live: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(live, dict):
        return None
    return {
        "state": live.get("state", "live"),
        "home_score": live.get("home_score"),
        "away_score": live.get("away_score"),
        "clock": live.get("clock"),
    }


def _group_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Preserve first-seen group order; bucket rows under each group name."""
    order: List[str] = []
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        g = r["group"]
        if g not in buckets:
            buckets[g] = []
            order.append(g)
        buckets[g].append(r)
    return [{"name": g, "bets": buckets[g]} for g in order]


def _unavailable(sport: str, home: str, away: str, status: str,
                 note: str) -> Dict[str, Any]:
    return {
        "sport": sport, "home": home, "away": away, "status": status,
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "live": None, "best_bets": [], "groups": [], "honest_note": note,
    }


def game_bet_board(sport: str, home: str, away: str, *,
                   predictor: Any = None,
                   odds_lookup: Optional[Callable[..., Any]] = None,
                   live: Optional[Dict[str, Any]] = None,
                   surface: str = "Hard") -> Dict[str, Any]:
    """The uniform per-game bet board. Never raises; degrades to status fields.

    *predictor* is a built domain predictor (None -> built via the cached factory).
    *odds_lookup(sport, home, away)* returns {book: {home_label: dec, away_label:
    dec}} (or None) -- the same seam slate uses. *live* is an optional in-game
    state dict {state,home_score,away_score,clock,...}; when present the in-game
    block's updated numbers are folded in as live-labelled rows.
    """
    sport = sport.lower()
    if sport not in SPORTS:
        return _unavailable(sport, home, away, "unknown_sport",
                            f"unknown sport '{sport}'; choose {', '.join(SPORTS)}")
    if predictor is None:
        try:
            predictor = pm._build_predictor(sport)
        except Exception as exc:  # noqa: BLE001
            logger.warning("predictor factory failed for %s: %s", sport, exc)
            predictor = None
    if predictor is None:
        return _unavailable(sport, home, away, "unavailable", pm._UNAVAILABLE)
    try:
        result = pm.build_result(sport, predictor,
                                 _ns(sport, home, away, surface, live))
    except Exception as exc:  # noqa: BLE001 -- one bad game never 500s the board
        logger.warning("bet board build failed for %s %s vs %s: %s",
                       sport, home, away, exc)
        return _unavailable(sport, home, away, "error",
                            f"prediction error ({type(exc).__name__})")
    pregame = result.get("pregame", {})
    extra = {"top_correct_scores": pregame.get("top_correct_scores")}
    raw = flat.flatten(sport, pregame.get("markets"), home, away, extra=extra)

    book_prices = None
    if odds_lookup is not None:
        try:
            book_prices = odds_lookup(sport, home, away)
        except Exception:  # noqa: BLE001 -- an odds miss is never fatal
            book_prices = None

    rows = _enrich(raw, home, away, book_prices)

    if isinstance(live, dict):
        rows += _live_rows(result, sport, home, away)

    return {
        "sport": sport, "home": home, "away": away, "status": "ok",
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "live": _live_block(live),
        "best_bets": _rank_best(rows),
        "groups": _group_rows(rows),
        "honest_note": HONEST_NOTE,
    }


def _live_rows(result: Dict[str, Any], sport: str, home: str,
               away: str) -> List[Dict[str, Any]]:
    """In-game updated numbers as live-labelled rows (model view only -- no live
    book shopping). Absent in-game block -> []."""
    ig = result.get("ingame")
    if not isinstance(ig, dict):
        return []
    out: List[Dict[str, Any]] = []
    p = ig.get("p_home_win")
    if isinstance(p, (int, float)):
        out.append({"group": "LIVE Moneyline", "selection": f"{home} (live)",
                    "model_prob": p, "line": None, "fair_odds": _fair_odds(p),
                    "best_book": None, "best_price": None, "ev_pct": None,
                    "verdict": "LIVE", "note": "in-game re-priced model view"})
        out.append({"group": "LIVE Moneyline", "selection": f"{away} (live)",
                    "model_prob": 1.0 - p, "line": None,
                    "fair_odds": _fair_odds(1.0 - p), "best_book": None,
                    "best_price": None, "ev_pct": None, "verdict": "LIVE",
                    "note": "in-game re-priced model view"})
    return out
