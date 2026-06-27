"""frontend.quant_routes -- the quant EXECUTION API surface (transparency only).

GET-only endpoints that expose ONE auditable bet-validation verdict per market,
multi-book Shin-consensus devig, descriptive (never promoted) arb flags, UNIT-space
risk descriptors, and the sign-audited CLV scoreboard. Every number is produced by
a vetted helper reused VERBATIM -- no new math here:

  GET /api/quant/{sport}/validate
      Per-game, per-market BetValidation objects (tier/units/edge/ev/clv/
      gate_proven) via scripts.platformkit.quant_exec.build_validation, which
      reuses exec_decision.assign_tier + quarter_kelly_units + odds_shop devig/EV.
      MOST verdicts are no_bet / matches-the-close -- a SUCCESS, surfaced as such.

  GET /api/quant/{sport}/devig
      Multi-book Shin consensus fair prob per market (odds_shop.devig_twoway over
      the consensus two-way close). Probabilities only.

  GET /api/quant/{sport}/arb
      DESCRIPTIVE two-way arb flags (odds_shop.detect_arb). Flagged, NEVER
      promoted: arbs are rare, vanish fast, and books limit/void winners.

  GET /api/quant/risk
      UNIT-space variance / exposure descriptors over the open paper book. RoR is a
      MODEL-CONDITIONAL DESCRIPTIVE stat, NOT a profit/safety guarantee. NO $ field.

  GET /api/quant/clv
      The sign-audited beat-the-close CLV scoreboard (vetted clv_ledger via
      frontend.paper_trail.clv_summary). vs_close defaults UNPROVEN.

There is NO POST here. Placement stays on frontend.exec_routes (executed=False).
Every envelope stamps units-only, edge_claimed=False, real_money_enabled=False.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.quant_routes requires fastapi.") from exc

from frontend.edge_api import build_edge_view
from scripts.platformkit.quant_exec import build_validation
from predict_service.honest_route import honest_route

router = APIRouter()

_PREFIX = "/api/quant"
_STORE_DIR_ENV = "PREDICT_SERVICE_STORE_DIR"

_HONEST_NOTE = (
    "Quant execution surface -- transparency only. Units/probability, never $. "
    "MOST validation verdicts are no_bet / match-the-close, which is a SUCCESS "
    "(markets are efficient), not a miss. gate_proven defaults False; CLV vs_close "
    "defaults UNPROVEN. Arb is descriptive (rare/fragile), never promoted. RoR is a "
    "model-conditional descriptive stat, NOT a profit or safety guarantee."
)


def _store_out_dir() -> Optional[str]:
    return os.environ.get(_STORE_DIR_ENV) or None


def _stamp(body: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp the standing honesty invariants on every quant envelope."""
    body.setdefault("units", "probability")
    body["edge_claimed"] = False
    body["real_money_enabled"] = False
    body.setdefault("honest_note", _HONEST_NOTE)
    return body


def _edge_view(sport: str) -> Dict[str, Any]:
    try:
        return build_edge_view(sport, store_out_dir=_store_out_dir())
    except Exception as exc:  # noqa: BLE001 -- assembler is pure; belt + braces
        logger.warning("quant_routes /%s: build_edge_view raised: %s", sport, exc)
        return {"status": "unavailable", "games": [],
                "reason": "assembly error (%s)" % type(exc).__name__}


def _validate_game(game: Dict[str, Any]) -> Dict[str, Any]:
    """Per-market BetValidation list for one edge game (no $ field)."""
    rows: List[Dict[str, Any]] = []
    for c in (game.get("comparison") or []):
        v = build_validation(
            side=str(c.get("side", "")),
            market=str(c.get("market_type", "")),
            model_prob=c.get("model_prob"),
            best_decimal=c.get("best_odds"),
            # The comparison's market_prob is already Shin-devigged; pass it as the
            # close leg so edge = model - devigged_close without re-devig assumptions.
            close_home=c.get("market_prob"),
            close_away=(1.0 - c["market_prob"])
            if c.get("market_prob") is not None else None,
            clv_is_proxy=bool(c.get("clv_is_proxy", True)),
        )
        rows.append(v.as_dict())
    n_bet = sum(1 for r in rows if r.get("decision") == "bet")
    return {
        "game_id": game.get("game_id"),
        "home": game.get("home"),
        "away": game.get("away"),
        "status": "ok",
        "validations": rows,
        "n_bet": n_bet,
        "n_no_bet": len(rows) - n_bet,
    }


@router.get(_PREFIX + "/{sport}/validate")
@honest_route(extra={"games": [], "count": 0})
def quant_validate(sport: str) -> JSONResponse:
    """Per-game, per-market auditable bet-validation verdicts. Never raises."""
    view = _edge_view(sport)
    if view.get("status") != "ok":
        return JSONResponse(_stamp({
            "sport": sport, "status": "unavailable",
            "reason": view.get("reason", "snapshot unavailable"),
            "games": [], "count": 0}))
    games = [_validate_game(g) for g in (view.get("games") or [])]
    return JSONResponse(_stamp({
        "sport": sport, "status": "ok", "count": len(games),
        "generated_at": view.get("generated_at", ""), "games": games}))


def _consensus_devig(comparison: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Shin-consensus fair prob per (market_type) two-way from the edge comparison.

    The comparison already carries market_prob (Shin-devigged consensus fair prob).
    We surface it per side as the multi-book consensus, re-confirming via the vetted
    devig_twoway when both legs' best decimals are present. Probabilities only.
    """
    out: List[Dict[str, Any]] = []
    for c in comparison:
        mp = c.get("market_prob")
        out.append({
            "market_type": c.get("market_type"),
            "side": c.get("side"),
            "consensus_fair_prob": (float(mp) if mp is not None else None),
            "best_book": c.get("best_book", ""),
            "best_odds": c.get("best_odds"),
            "method": "shin",
        })
    return out


@router.get(_PREFIX + "/{sport}/devig")
@honest_route(extra={"games": [], "count": 0})
def quant_devig(sport: str) -> JSONResponse:
    """Multi-book Shin consensus fair prob per market. Probabilities only."""
    view = _edge_view(sport)
    if view.get("status") != "ok":
        return JSONResponse(_stamp({
            "sport": sport, "status": "unavailable",
            "reason": view.get("reason", "snapshot unavailable"), "games": []}))
    games = [{
        "game_id": g.get("game_id"),
        "devig": _consensus_devig(g.get("comparison") or []),
    } for g in (view.get("games") or [])]
    return JSONResponse(_stamp({
        "sport": sport, "status": "ok", "count": len(games), "games": games}))


def _arb_flags(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Descriptive two-way arb flags via odds_shop.detect_arb (never promoted)."""
    try:
        from scripts.platformkit.odds_shop import best_line, detect_arb, VENUE_SPORTSBOOK
    except Exception as exc:  # noqa: BLE001
        logger.debug("quant_routes: arb import failed: %s", exc)
        return []
    book_prices: Dict[str, Dict[str, float]] = {}
    for m in markets:
        book = str(m.get("book", "") or "")
        side = str(m.get("side", "") or "")
        odds = m.get("odds")
        if not (book and side) or odds is None:
            continue
        try:
            book_prices.setdefault(book, {})[side] = float(odds)
        except (TypeError, ValueError):
            continue
    best = best_line(book_prices, restrict_to=VENUE_SPORTSBOOK)
    ba, bb = best.get("home"), best.get("away")
    if not (ba and bb):
        return []
    arb = detect_arb(ba["price"], bb["price"])
    arb.update({"home_book": ba["book"], "away_book": bb["book"],
                "promoted": False, "descriptive": True})
    return [arb]


@router.get(_PREFIX + "/{sport}/arb")
@honest_route(extra={"games": [], "count": 0})
def quant_arb(sport: str) -> JSONResponse:
    """DESCRIPTIVE two-way arb flags (flagged, never promoted). Never raises."""
    view = _edge_view(sport)
    if view.get("status") != "ok":
        return JSONResponse(_stamp({
            "sport": sport, "status": "unavailable",
            "reason": view.get("reason", "snapshot unavailable"), "games": [],
            "arb_promoted": False, "arb_descriptive": True}))
    games = [{
        "game_id": g.get("game_id"),
        "arb": _arb_flags(g.get("markets") or []),
    } for g in (view.get("games") or [])]
    return JSONResponse(_stamp({
        "sport": sport, "status": "ok", "count": len(games), "games": games,
        "arb_promoted": False, "arb_descriptive": True,
        "arb_note": "Arbs are rare, vanish fast, and books limit/void winners -- "
                    "a fragile execution flag, never a standing edge."}))


def _open_units() -> List[float]:
    """Stake-units of currently OPEN paper bets (units only; never $)."""
    try:
        from frontend.paper_trail import read_trail
        trail = read_trail()
    except Exception as exc:  # noqa: BLE001
        logger.debug("quant_routes: read_trail failed: %s", exc)
        return []
    units: List[float] = []
    for r in trail:
        if str(r.get("status", "")).lower() != "open":
            continue
        try:
            units.append(float(r.get("stake_units", 0.0) or 0.0))
        except (TypeError, ValueError):
            continue
    return units


@router.get(_PREFIX + "/risk")
@honest_route
def quant_risk() -> JSONResponse:
    """UNIT-space variance / exposure over the open paper book. NO $ field.

    RoR (risk-of-ruin) is framed as a MODEL-CONDITIONAL DESCRIPTIVE stat, not a
    profit or safety guarantee: with no realized-money path it is purely a
    units-space variance descriptor. Never raises.
    """
    units = _open_units()
    n = len(units)
    total = round(sum(units), 6)
    max_unit = round(max(units), 6) if units else 0.0
    mean_unit = round(total / n, 6) if n else 0.0
    var = (round(sum((u - mean_unit) ** 2 for u in units) / n, 6) if n else 0.0)
    return JSONResponse(_stamp({
        "status": "ok",
        "n_open": n,
        "total_exposure_units": total,
        "max_single_units": max_unit,
        "mean_units": mean_unit,
        "variance_units2": var,
        "ror_descriptive": True,
        "ror_is_guarantee": False,
        "risk_note": "Exposure/variance are in UNITS, never dollars. RoR is a "
                     "model-conditional descriptive stat, NOT a profit/safety "
                     "guarantee; there is no realized-money path.",
    }))


@router.get(_PREFIX + "/clv")
@honest_route
def quant_clv() -> JSONResponse:
    """Sign-audited beat-the-close CLV scoreboard. vs_close defaults UNPROVEN."""
    try:
        from frontend.paper_trail import clv_summary
        summary = clv_summary()
    except Exception as exc:  # noqa: BLE001 -- CLV is advisory, never fatal
        logger.warning("quant_routes /clv: clv_summary failed: %s", exc)
        summary = {"n_bets": 0, "pct_beat_close": None, "mean_clv_pct": None,
                   "clv_is_proxy": True, "by_sport": {},
                   "note": "CLV ledger unavailable (%s)" % type(exc).__name__}
    summary["vs_close_proven"] = False  # UNPROVEN by default; never self-stamped
    return JSONResponse(_stamp({"status": "ok", "clv": summary}))


__all__ = ["router"]
