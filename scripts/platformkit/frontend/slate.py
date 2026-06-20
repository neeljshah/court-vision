"""scripts.platformkit.frontend.slate -- honest slate-shaping for the bettor front end.

Reshapes domain-predictor output into flat rows for the table UI. No math here.

HONEST: markets are efficient -- NO model edge claimed. The "edge" field is the
raw prob-vs-line gap (decision support only). Human places every bet manually.

RECENCY + DEAD-MARKET GATE (QA iter 9/10 P1+P2): build_slate drops rows where:
  tipoff > 6 h past | matchup is 'Yes vs No' binary | market_prob < 0.001 (dead
  market) | best_odds > 50 (no liquid market). Tipoff 0-6 h past -> stamped
  stale=True + hours_old=N + status='stale'. Predicates live in board_sanitizer.

INVARIANTS: never edit src/ or kernel/; reuse domain predictors; <=300 LOC.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit import odds_shop
from scripts.platformkit import predict_matchup as pm
from scripts.platformkit.bestbets.board_sanitizer import (
    _is_non_sports_binary,
    _market_dead,
    _odds_too_extreme,
)
from scripts.platformkit.frontend.slate_recency_gate import (
    STALE_DROP_HOURS,
    _recency_verdict,
)

logger = logging.getLogger(__name__)

SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis")

HONEST_NOTE = (
    "Pregame MATCHES the devigged close (calibration/sharpness, not a money edge); "
    "in-game ADDS the realized state. Markets are efficient -- NO $ edge is claimed. "
    "Decision-support only: YOU place every bet manually on your own book."
)

_DEFAULT_MATCHUPS: Dict[str, List[Dict[str, str]]] = {
    "nba": [{"home": "BOS", "away": "LAL"}, {"home": "DEN", "away": "GSW"}],
    "mlb": [{"home": "CIN", "away": "NYM"}, {"home": "BOS", "away": "TOR"},
            {"home": "HOU", "away": "DET"}, {"home": "NYY", "away": "CWS"},
            {"home": "SEA", "away": "BAL"}],
    "soccer": [{"home": "Arsenal", "away": "Man City"}, {"home": "Liverpool", "away": "Chelsea"}],
    "soccer_intl": [{"home": "England", "away": "Croatia"}, {"home": "Portugal", "away": "DR Congo"},
                    {"home": "Uzbekistan", "away": "Colombia"}, {"home": "Ghana", "away": "Panama"}],
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
    """Calibration verdict tag from predictor's own honest_note (never invented)."""
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
    """Compact sport-appropriate model-output string from the REAL pregame block."""
    p = pregame.get("p_home_win")
    p_txt = f"P(home)={p:.1%}" if isinstance(p, (int, float)) else "P(home)=n/a"
    s = sport.lower()
    extra = ""
    if s == "nba" and pregame.get("total_mean") is not None:
        extra = f", total~{pregame['total_mean']:.1f}"
    elif s == "mlb" and pregame.get("expected_total") is not None:
        extra = f", total~{pregame['expected_total']:.1f}"
    elif s in ("soccer", "soccer_intl"):
        for label, key in (("P(draw)", "p_draw"), ("O2.5", "over_2.5"), ("BTTS", "btts_yes")):
            v = pregame.get(key)
            if isinstance(v, (int, float)):
                extra += f", {label}={v:.1%}"
    elif s == "tennis" and pregame.get("total_games_mean") is not None:
        extra = f", games~{pregame['total_games_mean']:.1f}"
    return p_txt + extra


def _edge(pregame: Dict[str, Any], market: Optional[Dict[str, Any]]) -> Optional[float]:
    """Prob-vs-line gap (decision support only, NOT a money edge); None if no market."""
    if not market:
        return None
    p = pregame.get("p_home_win")
    mk = market.get("p_home_implied")
    if isinstance(p, (int, float)) and isinstance(mk, (int, float)):
        return round(float(p) - float(mk), 4)
    return None


# Null multi-book block: stable UI shape when no odds supplied (never fabricated).
_NULL_BOOK_FIELDS: Dict[str, Any] = {
    "best_home_book": None, "best_home_price": None,
    "best_away_book": None, "best_away_price": None,
    "arb_pct": None, "model_ev_best": None,
    "pm_home_book": None, "pm_home_price": None,
    "pm_away_book": None, "pm_away_price": None,
}


# Three-way markets: HOME/AWAY-only arb is invalid (phantom arb without draw leg).
_THREE_WAY = {"soccer", "soccer_intl"}


def _book_fields(book_prices: Optional[Dict[str, Dict[str, float]]],
                 home: str, away: str,
                 p_home: Optional[float],
                 sport: str = "") -> Dict[str, Any]:
    """Best-line + arb + model-EV fields; absent/unusable -> all-None (never fabricated)."""
    if not book_prices:
        return dict(_NULL_BOOK_FIELDS)
    try:
        s = odds_shop.summarise_twoway(  # SPORTSBOOK-restricted; PM prices come back pm_*
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
        "pm_home_book": s["pm_a_book"], "pm_home_price": s["pm_a_price"],
        "pm_away_book": s["pm_b_book"], "pm_away_price": s["pm_b_price"],
    }


def _apply_recency_gate(
    row: Dict[str, Any],
    matchup_meta: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    stale_drop_hours: float = STALE_DROP_HOURS,
) -> Dict[str, Any]:
    """Recency + dead-market gate. Returns NEW dict; caller drops on _drop=True."""
    if now is None:
        now = datetime.now(tz=timezone.utc)
    out = dict(row)

    # 1. Non-sports binary (both orderings: "Yes vs No" and "No vs Yes").
    matchup_str = out.get("matchup", "") or ""
    _hset = {str(matchup_meta.get(k, "") or "").strip().lower() for k in ("home", "away")}
    if _is_non_sports_binary(matchup_str) or _hset == {"yes", "no"}:
        out["_drop"] = True; out["_drop_reason"] = "non_sports_binary"; return out

    # 2. Dead-market / extreme-odds (board_sanitizer predicates; never duplicated).
    if _market_dead(matchup_meta.get("market_prob")):
        out["_drop"] = True; out["_drop_reason"] = "dead_market"; return out
    if _odds_too_extreme(matchup_meta.get("best_odds")):
        out["_drop"] = True; out["_drop_reason"] = "extreme_odds"; return out

    # 3. Recency: stamp (0-6 h) or drop (>6 h past tipoff).
    verdict, hours_old = _recency_verdict(matchup_meta, now, stale_drop_hours)
    _ho = round(hours_old, 2) if hours_old is not None else None
    if verdict == "drop":
        out["_drop"] = True; out["_drop_reason"] = "tipoff_too_old"; out["hours_old"] = _ho
        return out
    if verdict == "stamp":
        out["stale"] = True; out["hours_old"] = _ho; out["status"] = "stale"
    return out


def build_row(sport: str, home: str, away: str, *, predictor: Any,
              market: Optional[Dict[str, Any]] = None,
              surface: str = "Hard",
              book_prices: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """Shape ONE honest slate row from the REAL predictor (or mark it unavailable)."""
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
                now: Optional[datetime] = None,
                ) -> Dict[str, Any]:
    """Build the honest slate payload for *sport*. All factories are injectable (tests).

    *now* is injectable for deterministic recency-gate tests. Each built row passes
    through _apply_recency_gate (drop/stamp); gate_dropped count added when non-zero.
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
    _now = now if now is not None else datetime.now(tz=timezone.utc)
    rows: List[Dict[str, Any]] = []
    n_dropped = 0
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
        row = build_row(sport, home, away, predictor=predictor,
                        market=market, surface=g.get("surface", "Hard"),
                        book_prices=book_prices)
        _mp = (float(market["p_home_implied"])
               if market and isinstance(market.get("p_home_implied"), (int, float)) else None)
        meta: Dict[str, Any] = {
            "matchup": row.get("matchup", ""), "home": home, "away": away,
            "tipoff_utc": g.get("tipoff_utc"), "tipoff": g.get("tipoff"),
            "game_datetime": g.get("game_datetime"), "commence_time": g.get("commence_time"),
            "market_prob": _mp, "best_odds": row.get("best_home_price"),
        }
        gated = _apply_recency_gate(row, meta, now=_now)
        if gated.get("_drop"):
            n_dropped += 1
            logger.debug("gate dropped %s: %s", gated.get("matchup"), gated.get("_drop_reason"))
            continue
        gated.pop("_drop", None)
        gated.pop("_drop_reason", None)
        rows.append(gated)
    status = "ok" if predictor is not None else "unavailable"
    out: Dict[str, Any] = {"sport": sport, "status": status, "rows": rows,
                            "honest_note": HONEST_NOTE,
                            "predictor_available": predictor is not None}
    if n_dropped:
        out["gate_dropped"] = n_dropped
    return out
