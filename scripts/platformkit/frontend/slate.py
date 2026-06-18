"""scripts.platformkit.frontend.slate -- honest slate-shaping for the bettor front end.

Reuses the REAL predictor end to end: builds each matchup via
scripts.platformkit.predict_matchup.build_result on a predictor from
predictor_jd._build_predictor. NO prediction math is reimplemented here -- this
module only RESHAPES the predictor's output into a flat row for the table UI and
derives an HONEST calibration verdict string from the predictor's own honest_note.

If a sport's corpus is unavailable (fresh clone, gitignored data), the row carries
status="unavailable" with a clear note and NO fabricated numbers. Market lines, when
present, come from the on-disk OddsFeed corpus; absent -> market=None (never faked).

HONEST: markets are efficient -- NO model edge is claimed. Pregame MATCHES the
devigged close (calibration/sharpness); the "edge" shown is the raw prob-vs-line
gap for decision support only, NOT a claimed money edge. The human places bets
manually -- there is no auto-execution anywhere.

INVARIANTS: never edit src/ or kernel/; reuse the domain predictors; <=300 LOC; no secrets.
"""
from __future__ import annotations

import argparse
import logging
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit import odds_shop
from scripts.platformkit import predict_matchup as pm

logger = logging.getLogger(__name__)

SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis")

HONEST_NOTE = (
    "Pregame MATCHES the devigged close (calibration/sharpness, not a money edge); "
    "in-game ADDS the realized state. Markets are efficient -- NO $ edge is claimed. "
    "Decision-support only: YOU place every bet manually on your own book."
)

# Default demo matchups per sport, sourced from the real predictor's demo registry so the
# slate always references matchups the corpus actually contains.
_DEFAULT_MATCHUPS: Dict[str, List[Dict[str, str]]] = {
    "nba": [{"home": "BOS", "away": "LAL"}, {"home": "DEN", "away": "GSW"}],
    # today's real MLB slate (home = host; refreshed-to-2026 ratings serve these)
    "mlb": [{"home": "CIN", "away": "NYM"}, {"home": "BOS", "away": "TOR"},
            {"home": "HOU", "away": "DET"}, {"home": "NYY", "away": "CWS"},
            {"home": "SEA", "away": "BAL"}],
    "soccer": [{"home": "Arsenal", "away": "Man City"},
               {"home": "Liverpool", "away": "Chelsea"}],
    # today's real 2026 World Cup slate (neutral-site national teams)
    "soccer_intl": [{"home": "England", "away": "Croatia"},
                    {"home": "Portugal", "away": "DR Congo"},
                    {"home": "Uzbekistan", "away": "Colombia"},
                    {"home": "Ghana", "away": "Panama"}],
    "tennis": [{"home": "Novak Djokovic", "away": "Carlos Alcaraz"}],
}


def default_matchups(sport: str) -> List[Dict[str, str]]:
    """Honest default matchup list for *sport* (empty for an unknown sport)."""
    return list(_DEFAULT_MATCHUPS.get(sport.lower(), []))


def _ns(sport: str, home: str, away: str, surface: str = "Hard") -> argparse.Namespace:
    """A minimal Namespace shaped like predict_matchup's parsed args (pregame only)."""
    return argparse.Namespace(
        sport=sport, home=home, away=away, surface=surface,
        elapsed=None, inning=None, half=None, home_score=None, away_score=None,
        sets_home=None, sets_away=None, games_home=None, games_away=None,
    )


def _verdict(honest_note: Optional[str]) -> str:
    """Derive an HONEST calibration verdict tag from the predictor's own honest_note.

    The predictors describe their standing vs the market in plain English; we read it,
    never invent it. Unknown -> "UNKNOWN" (we do not guess).
    """
    if not honest_note:
        return "UNKNOWN"
    low = honest_note.lower()
    if "behind" in low:
        return "BEHIND"
    if "match" in low:
        return "MATCH"
    if "ahead" in low or "beat" in low:
        return "AHEAD"
    return "CALIBRATED"


def _model_summary(sport: str, pregame: Dict[str, Any]) -> str:
    """A compact, sport-appropriate model-output string off the REAL pregame block."""
    p = pregame.get("p_home_win")
    p_txt = f"P(home)={p:.1%}" if isinstance(p, (int, float)) else "P(home)=n/a"
    s = sport.lower()
    extra = ""
    if s == "nba" and pregame.get("total_mean") is not None:
        extra = f", total~{pregame['total_mean']:.1f}"
    elif s == "mlb" and pregame.get("expected_total") is not None:
        extra = f", total~{pregame['expected_total']:.1f}"
    elif s in ("soccer", "soccer_intl"):
        # Club soccer now carries a real 1X2 moneyline too -> show draw + O2.5 + BTTS.
        draw = pregame.get("p_draw")
        o25 = pregame.get("over_2.5")
        btts = pregame.get("btts_yes")
        if isinstance(draw, (int, float)):
            extra += f", P(draw)={draw:.1%}"
        if isinstance(o25, (int, float)):
            extra += f", O2.5={o25:.1%}"
        if isinstance(btts, (int, float)):
            extra += f", BTTS={btts:.1%}"
    elif s == "tennis" and pregame.get("total_games_mean") is not None:
        extra = f", games~{pregame['total_games_mean']:.1f}"
    return p_txt + extra


def _edge(pregame: Dict[str, Any], market: Optional[Dict[str, Any]]) -> Optional[float]:
    """prob-vs-line gap for decision support (NOT a claimed money edge); None if no market."""
    if not market:
        return None
    p = pregame.get("p_home_win")
    mk = market.get("p_home_implied")
    if isinstance(p, (int, float)) and isinstance(mk, (int, float)):
        return round(float(p) - float(mk), 4)
    return None


# Null multi-book block: present on every row so the UI shape is stable. When no
# multi-book odds are supplied the fields are None (NEVER fabricated) and the row
# still shows the model number.
_NULL_BOOK_FIELDS: Dict[str, Any] = {
    "best_home_book": None, "best_home_price": None,
    "best_away_book": None, "best_away_price": None,
    "arb_pct": None, "model_ev_best": None,
    "pm_home_book": None, "pm_home_price": None,
    "pm_away_book": None, "pm_away_price": None,
}


# Three-way markets (a draw exists): a HOME/AWAY-only arb calc is invalid here -- it
# ignores the draw's probability mass and reports phantom arbs. Suppress arb_pct for
# these sports (best-line + EV remain valid). A true 3-way arb needs best_draw too.
_THREE_WAY = {"soccer", "soccer_intl"}


def _book_fields(book_prices: Optional[Dict[str, Dict[str, float]]],
                 home: str, away: str,
                 p_home: Optional[float],
                 sport: str = "") -> Dict[str, Any]:
    """Best-line + arb + model-EV-vs-best-price fields from raw multi-book odds.

    *book_prices* maps book -> {home_label: decimal, away_label: decimal}. Absent
    or unusable -> the all-None block (no fabricated price). model_ev_best is the
    model's EV at the BEST available home price (decision support, NOT a claimed
    beat-the-close edge -- line-shopping is an execution edge only). arb_pct is
    suppressed for three-way markets (see _THREE_WAY) to avoid phantom arbs.
    """
    if not book_prices:
        return dict(_NULL_BOOK_FIELDS)
    try:
        # HONESTY: restrict the bettable best line + arb to SPORTSBOOK venues so a
        # thin prediction-market YES price is never surfaced as a bettable best /
        # arb leg. PM prices still come back separately (pm_*_*) as a divergence
        # signal -- a signal, never a bettable line.
        s = odds_shop.summarise_twoway(
            book_prices, home, away, model_prob_a=p_home,
            bettable_restrict=odds_shop.VENUE_SPORTSBOOK)
    except Exception as exc:  # noqa: BLE001 -- odds must never sink a row
        logger.warning("odds shop failed for %s vs %s: %s", home, away, exc)
        return dict(_NULL_BOOK_FIELDS)
    arb = None if sport.lower() in _THREE_WAY else s["arb_pct"]
    return {
        "best_home_book": s["best_a_book"], "best_home_price": s["best_a_price"],
        "best_away_book": s["best_b_book"], "best_away_price": s["best_b_price"],
        "arb_pct": arb,
        "model_ev_best": s["model_ev_a"],
        # PM line surfaced separately (divergence signal, NOT bettable).
        "pm_home_book": s["pm_a_book"], "pm_home_price": s["pm_a_price"],
        "pm_away_book": s["pm_b_book"], "pm_away_price": s["pm_b_price"],
    }


def build_row(sport: str, home: str, away: str, *, predictor: Any,
              market: Optional[Dict[str, Any]] = None,
              surface: str = "Hard",
              book_prices: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """Shape ONE honest slate row from the REAL predictor (or mark it unavailable).

    *predictor* is the built domain predictor (or None). *market* is an optional dict
    with at least {"line": str, "p_home_implied": float}; absent -> market unavailable.
    Never raises and never fabricates a number.
    """
    sport = sport.lower()
    label = f"{home} vs {away}"
    if predictor is None:
        row = {"sport": sport, "matchup": label, "status": "unavailable",
               "model": None, "market": None, "edge": None, "verdict": "UNAVAILABLE",
               "note": pm._UNAVAILABLE}
        row.update(_book_fields(book_prices, home, away, None, sport))
        return row
    try:
        result = pm.build_result(sport, predictor, _ns(sport, home, away, surface))
    except Exception as exc:  # noqa: BLE001 -- one bad matchup must not sink the slate
        logger.warning("slate row failed for %s %s: %s", sport, label, exc)
        row = {"sport": sport, "matchup": label, "status": "error",
               "model": None, "market": None, "edge": None, "verdict": "UNKNOWN",
               "note": f"prediction error ({type(exc).__name__})"}
        row.update(_book_fields(book_prices, home, away, None, sport))
        return row
    pregame = result.get("pregame", {})
    p_home = pregame.get("p_home_win")
    row = {
        "sport": sport,
        "matchup": label,
        "status": "ok",
        "model": _model_summary(sport, pregame),
        "p_home_win": p_home,
        "market": (market.get("line") if market else None),
        "edge": _edge(pregame, market),
        "verdict": _verdict(pregame.get("honest_note")),
        "note": pregame.get("honest_note"),
    }
    row.update(_book_fields(
        book_prices, home, away,
        p_home if isinstance(p_home, (int, float)) else None, sport))
    return row


def build_slate(sport: str, *,
                matchups: Optional[List[Dict[str, str]]] = None,
                predictor_factory: Callable[[str], Any] = pm._build_predictor,
                market_lookup: Optional[Callable[[str, str, str], Optional[Dict[str, Any]]]] = None,
                odds_lookup: Optional[Callable[[str, str, str], Optional[Dict[str, Dict[str, float]]]]] = None,
                ) -> Dict[str, Any]:
    """Build the honest slate payload for *sport*.

    *predictor_factory*, *market_lookup*, and *odds_lookup* are injectable so tests
    can stub them with no live data. Real defaults: the cached domain-predictor
    factory, no single market (None), and no multi-book odds (None).

    *odds_lookup(sport, home, away)* returns a {book: {home_label: decimal,
    away_label: decimal}} dict (or None). When present, each row gains best_*_book/
    best_*_price, arb_pct, and model_ev_best; absent -> those fields are null and
    the row still shows the model number.
    """
    sport = sport.lower()
    if sport not in SPORTS:
        return {"sport": sport, "status": "unknown_sport", "rows": [],
                "honest_note": HONEST_NOTE,
                "note": f"unknown sport '{sport}'; choose one of {', '.join(SPORTS)}"}
    games = matchups if matchups is not None else default_matchups(sport)
    predictor = None
    try:
        predictor = predictor_factory(sport)
    except Exception as exc:  # noqa: BLE001
        logger.warning("predictor factory failed for %s: %s", sport, exc)
    rows: List[Dict[str, Any]] = []
    for g in games:
        home, away = g.get("home", ""), g.get("away", "")
        market = None
        if market_lookup is not None:
            try:
                market = market_lookup(sport, home, away)
            except Exception:  # noqa: BLE001 -- a market miss is never fatal
                market = None
        book_prices = None
        if odds_lookup is not None:
            try:
                book_prices = odds_lookup(sport, home, away)
            except Exception:  # noqa: BLE001 -- an odds miss is never fatal
                book_prices = None
        rows.append(build_row(sport, home, away, predictor=predictor,
                              market=market, surface=g.get("surface", "Hard"),
                              book_prices=book_prices))
    status = "ok" if predictor is not None else "unavailable"
    return {"sport": sport, "status": status, "rows": rows,
            "honest_note": HONEST_NOTE,
            "predictor_available": predictor is not None}
