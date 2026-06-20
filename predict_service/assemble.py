"""predict_service.assemble -- pure builders that turn the engine's raw outputs
into the FROZEN contract shapes (MarketRow / EdgeRow / PredictionRecord).

NO network, NO predictor build, NO store I/O here -- everything is a pure
function of values already pulled by predict_service.produce. That keeps the
producer thin and lets the test exercise the assembly with plain dicts.

HONESTY (enforced by shape): EdgeRow carries model_prob / market_prob / ev only
(ev = probability ratio per 1 unit, NOT dollars). Devigging reuses the vetted
Shin N-outcome solver (shin_devig_decimal) for 3-way markets (soccer home/draw/away)
and devig_twoway for 2-way markets; EV reuses odds_shop.ev_vs_price. We never
fabricate a $ edge and never reimplement CLV (clv_ledger owns that downstream).

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from predict_service.contracts import EdgeRow, MarketRow

# Reuse the vetted devig + EV helpers verbatim -- never reimplement these.
from scripts.platformkit.odds_shop import devig_twoway, ev_vs_price
from scripts.platformkit.eval_gate.shin import shin_devig_decimal

_ML = "moneyline"
# Sides in the order passed to the Shin N-way solver for 3-way markets.
_THREE_WAY_SIDES = ("home", "draw", "away")


def _decimal(value: Any) -> Optional[float]:
    """Coerce a decimal-odds value to float > 1.0, else None (never fabricates)."""
    try:
        d = float(value)
    except (TypeError, ValueError):
        return None
    return d if d > 1.0 else None


def _devig_threeway(
    home_dec: float, draw_dec: float, away_dec: float
) -> Tuple[float, float, float]:
    """No-vig fair probs for a 3-way market via the vetted Shin N-outcome solver.

    The Shin solver handles any number of legs -- this is identical to devig_twoway
    but passes all three legs so the draw is fairly devigged within the full market
    overround, not discarded. Returns (fair_home, fair_draw, fair_away) summing ~1.
    """
    probs, _z = shin_devig_decimal([home_dec, draw_dec, away_dec])
    return float(probs[0]), float(probs[1]), float(probs[2])


def market_rows(sport: str, game_id: str,
                prices: Dict[str, Dict[str, Optional[float]]],
                captured_at: Optional[str] = None) -> List[MarketRow]:
    """One MarketRow per (book, side) moneyline quote, devigged within the book.

    *prices* is the OddsEvent.prices shape: {venue: {"home": dec, "away": dec,
    "draw": dec|None}}. For books quoting all three legs (home + draw + away) we
    use the Shin N-way solver so every leg gets an honest devigged_prob and the
    draw leg is not dropped. Books quoting only home + away fall through to the
    two-way path (devig_twoway). A side a book does not quote is simply skipped
    (never a guessed number).
    """
    rows: List[MarketRow] = []
    for book, quote in (prices or {}).items():
        if not isinstance(quote, dict):
            continue
        home_dec = _decimal(quote.get("home"))
        draw_dec = _decimal(quote.get("draw"))
        away_dec = _decimal(quote.get("away"))

        # --- 3-way path (soccer): home + draw + away all present. ---
        if home_dec is not None and draw_dec is not None and away_dec is not None:
            fair_home = fair_draw = fair_away = None
            try:
                fair_home, fair_draw, fair_away = _devig_threeway(
                    home_dec, draw_dec, away_dec
                )
            except Exception:  # noqa: BLE001 -- devig must never sink the row
                pass
            for side, dec, fair in (
                ("home", home_dec, fair_home),
                ("draw", draw_dec, fair_draw),
                ("away", away_dec, fair_away),
            ):
                rows.append(MarketRow(
                    sport=sport, game_id=game_id, market_type=_ML, side=side,
                    line=None, odds=round(dec, 6), book=str(book),
                    devigged_prob=(round(float(fair), 6) if fair is not None else None),
                    captured_at=captured_at, is_close=False, clv_is_proxy=True))
            continue

        # --- 2-way path (NBA, MLB, tennis): home + away only. ---
        fair_home = fair_away = None
        if home_dec is not None and away_dec is not None:
            try:
                fair_home, fair_away = devig_twoway(home_dec, away_dec)
            except Exception:  # noqa: BLE001 -- devig must never sink the row
                fair_home = fair_away = None
        for side, dec, fair in (("home", home_dec, fair_home),
                                ("away", away_dec, fair_away)):
            if dec is None:
                continue
            rows.append(MarketRow(
                sport=sport, game_id=game_id, market_type=_ML, side=side,
                line=None, odds=round(dec, 6), book=str(book),
                devigged_prob=(round(float(fair), 6) if fair is not None else None),
                captured_at=captured_at, is_close=False, clv_is_proxy=True))
    return rows


def _market_consensus(rows: List[MarketRow]) -> Dict[str, Tuple[float, str, float]]:
    """Per side: (best devigged market_prob, that book, that book's decimal odds).

    "Best" = the book whose devigged fair prob for the side is LOWEST (longest
    price the bettor can take), so the EdgeRow is computed against the most
    bettor-favourable real quote, not a fabricated average. Skips rows with no
    devigged_prob. Returns {side: (market_prob, book, odds)}.
    """
    best: Dict[str, Tuple[float, str, float]] = {}
    for r in rows:
        if r.devigged_prob is None or r.odds is None:
            continue
        cur = best.get(r.side)
        if cur is None or r.devigged_prob < cur[0]:
            best[r.side] = (float(r.devigged_prob), r.book, float(r.odds))
    return best


def edge_rows(game_id: str, model_probs: Dict[str, Optional[float]],
              rows: List[MarketRow]) -> List[EdgeRow]:
    """EdgeRow per side where we have BOTH a model prob and a devigged market prob.

    model_probs maps side -> model probability ("home"/"away"[/"draw"]). ev is the
    expected value per 1 unit at the book's decimal price (odds_shop.ev_vs_price),
    a pure probability ratio -- never dollars. clv_is_proxy is True (the close we
    settle against later is a pre-tip proxy, surfaced honestly). tier is left None
    here -- evidence tiering is a downstream, measured concern, not invented here.
    """
    consensus = _market_consensus(rows)
    out: List[EdgeRow] = []
    for side, mp in (model_probs or {}).items():
        if mp is None:
            continue
        slot = consensus.get(side)
        if slot is None:
            continue
        market_prob, book, dec = slot
        try:
            ev = ev_vs_price(float(mp), dec)
        except Exception:  # noqa: BLE001 -- a bad price never fabricates an edge
            continue
        out.append(EdgeRow(
            game_id=game_id, market_type=_ML, side=side,
            model_prob=round(float(mp), 6), market_prob=round(market_prob, 6),
            ev=round(float(ev), 6), tier=None, book=book,
            line=None, clv_is_proxy=True))
    return out


def model_probs_from_pregame(pregame: Dict[str, Any]) -> Dict[str, float]:
    """Map a build_result pregame block to {side: model_prob} for ML edges.

    p_home_win -> home, p_away_win (or 1 - p_home - p_draw) -> away, p_draw ->
    draw when present. Values are copied VERBATIM from the engine block -- the
    producer asserts they round-trip equal to the source, so no transform here
    invents a number.
    """
    out: Dict[str, float] = {}
    p_home = pregame.get("p_home_win")
    if p_home is not None:
        out["home"] = float(p_home)
    p_draw = pregame.get("p_draw")
    if p_draw is not None:
        out["draw"] = float(p_draw)
    p_away = pregame.get("p_away_win")
    if p_away is not None:
        out["away"] = float(p_away)
    elif p_home is not None:
        # Two-way market with no explicit away: away = 1 - home - draw.
        out["away"] = round(1.0 - float(p_home) - float(p_draw or 0.0), 6)
    return out


def pregame_probs_record(pregame: Dict[str, Any]) -> Dict[str, float]:
    """The pregame_probs dict stored on a PredictionRecord (home_ml/away_ml/draw).

    Keyed by market name so a consumer reads model probabilities without guessing
    the side convention. Values copied verbatim from *pregame* (no transform).
    """
    probs = model_probs_from_pregame(pregame)
    record: Dict[str, float] = {}
    if "home" in probs:
        record["home_ml"] = probs["home"]
    if "away" in probs:
        record["away_ml"] = probs["away"]
    if "draw" in probs:
        record["draw"] = probs["draw"]
    return record


__all__ = [
    "market_rows",
    "edge_rows",
    "model_probs_from_pregame",
    "pregame_probs_record",
]
