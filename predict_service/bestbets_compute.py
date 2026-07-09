"""predict_service.bestbets_compute -- quant best-bets selection (W3).

Ranked calibrated divergence cards (props + game markets) across sports.
BestBetCard fields: game_id, matchup, sport, market_type, side, model_prob,
  market_prob, best_book, best_odds, edge_vs_market (prob diff NOT $),
  units (UNITS not $), tier, confidence, clv, status, honest_note.
W-DEGEN-GATE: flat-prior sports forced to decision=no_bet, tier/ev/stake_units
  nulled, excluded from ranked board. No $ field. ASCII. <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from predict_service.bestbets_model_only import model_only_cards as _model_only_cards
from predict_service.bestbets_props import cards_from_props as _props_cards

logger = logging.getLogger(__name__)

# BB-Q5 hooks (CLV-aware rank, honest confidence, stale-line gate) live in one
# small bridge module so this file stays under the LOC cap; see
# scripts/platformkit/bestbets/compute_wiring.py. Each hook degrades to the
# prior byte-identical behavior when its underlying module is unavailable.
from scripts.platformkit.bestbets.compute_wiring import (  # noqa: E402
    confidence_for as _confidence_for,
    select_best_odds as _select_best_odds,
    rank_cards as _rank_cards,
)

_HONEST_NOTE = (
    "Calibrated decision-support only. Markets are efficient; no $ edge claimed. "
    "edge_vs_market = model_prob - market_prob (prob diff, NOT $). "
    "clv=INSUFFICIENT_DATA when no liquid in-play prices (offseason). "
    "units = flat_unit from policy (1.0 per bet, UNITS not $)."
)

VALID_TIERS = frozenset({"A", "B", "C"})
VALID_STATUSES = frozenset({"live", "pregame", "done"})
_TIER_RANK = {"A": 0, "B": 1, "C": 2}
_CLV_EMPTY: Dict[str, Any] = {
    "clv_pct": None, "beat_close": None,
    "clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True,
}


# -- Thin wrappers (patchable in tests) ----------------------------------------

def _get_edge_view(sport: str) -> Dict[str, Any]:
    from frontend.edge_api import build_edge_view  # noqa: PLC0415
    return build_edge_view(sport)


def _do_decide_game(game: Dict[str, Any]) -> Dict[str, Any]:
    from frontend.exec_decision import decide_game  # noqa: PLC0415
    return decide_game(game)


def _clv_for(game_id: str, market_type: str, side: str) -> Dict[str, Any]:
    """Best-effort CLV from clv_ledger; returns INSUFFICIENT_DATA on any miss."""
    try:
        from scripts.platformkit.clv_ledger import load_rows  # noqa: PLC0415
        rows = load_rows()
    except Exception:  # noqa: BLE001
        return dict(_CLV_EMPTY)
    best = dict(_CLV_EMPTY)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("game_id", "")) != str(game_id):
            continue
        mt = str(row.get("market_type") or row.get("side", ""))
        if market_type and mt and mt != market_type:
            continue
        s = str(row.get("side", ""))
        if side and s and s != side:
            continue
        if not row.get("graded"):
            continue
        if row.get("clv_pct") is not None:
            best.update({
                "clv_pct": row["clv_pct"],
                "beat_close": row.get("beat_close"),
                "clv_status": str(row.get("clv_status", "proxy")),
                "clv_is_proxy": bool(row.get("clv_is_proxy", True)),
            })
            break
    return best


def _game_status(live_block: Any) -> str:
    if not isinstance(live_block, dict):
        return "pregame"
    state = str(live_block.get("state", "")).lower()
    if state in ("final", "complete", "post"):
        return "done"
    if state in ("in_game", "ingame", "live", "in progress"):
        return "live"
    return "pregame"


def _cards_from_game(game: Dict[str, Any], sport: str) -> List[Dict[str, Any]]:
    """Extract BestBetCards from decide_game output; decision=='bet' only."""
    cards: List[Dict[str, Any]] = []
    game_id = str(game.get("game_id", ""))
    home, away = str(game.get("home", "")), str(game.get("away", ""))
    matchup = f"{home} vs {away}" if home and away else game_id
    status = _game_status(game.get("live") or {})
    tipoff_utc = game.get("tipoff")  # ISO-8601 UTC; suppressor uses this

    cand_lookup: Dict[tuple, Dict[str, Any]] = {
        (str(c.get("market_type", "")), str(c.get("side", ""))): c
        for c in (game.get("candidates") or []) if isinstance(c, dict)
    }

    for bet in game.get("best_bets") or []:
        if not isinstance(bet, dict) or str(bet.get("decision", "")) != "bet":
            continue
        mt, side = str(bet.get("market_type", "")), str(bet.get("side", ""))
        tier = str(bet.get("tier") or "")
        if tier not in VALID_TIERS:
            continue
        cand = cand_lookup.get((mt, side)) or {}
        mp = float(cand.get("model_prob") or bet.get("model_prob") or 0.0)
        mkt = float(cand.get("market_prob") or bet.get("market_prob") or 0.0)
        all_books = list(cand.get("all_books") or [])
        legacy_bo = cand.get("best_odds") or bet.get("best_odds")
        legacy_book = str(cand.get("best_book") or bet.get("book") or "")
        bo, best_book = _select_best_odds(all_books, legacy_bo, legacy_book)
        clv = _clv_for(game_id, mt, side)
        card = {
            "game_id": game_id, "matchup": matchup, "sport": sport,
            "market_type": mt, "prop_player": None, "prop_stat": None,
            "side": side, "line": cand.get("line") or bet.get("line"),
            "model_prob": round(mp, 6), "market_prob": round(mkt, 6),
            "best_book": best_book,
            "best_odds": (round(float(bo), 6) if bo is not None else None),
            "all_books": all_books,
            "edge_vs_market": round(mp - mkt, 6) if mkt else 0.0,
            "units": float(bet.get("flat_unit") or cand.get("flat_unit") or 0.0),
            "tier": tier, "confidence": round(mp, 6),
            "decision": "bet",
            "clv": clv, "clv_is_proxy": bool(clv.get("clv_is_proxy", True)),
            "status": status, "honest_note": _HONEST_NOTE,
            "tipoff_utc": tipoff_utc,
        }
        card["confidence"] = _confidence_for(card)  # BBQ5-2: sharpness, not raw prob
        cards.append(card)

    # MODEL-ONLY / LINE-ONLY cards: a fresh book line the model does not price
    # (e.g. total / run-line). Surfaced honestly by bestbets_model_only -- the line
    # + best book are shown, but NO model_prob/tier/units/edge is fabricated.
    cards.extend(_model_only_cards(
        game, sport, cand_lookup, game_id=game_id, matchup=matchup,
        status=status, tipoff_utc=tipoff_utc, clv_empty=_CLV_EMPTY))
    return cards


def _cards_from_props(sport: str, status_filter: Optional[str]) -> List[Dict[str, Any]]:
    """BestBetCards from W2 prop_surface rows (delegated). Never raises."""
    return _props_cards(sport, status_filter, honest_note=_HONEST_NOTE,
                        clv_empty=_CLV_EMPTY)


def _mark_degenerate_sports(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Label cards from a flat-prior sport (degenerate_model=True). Never raises."""
    try:
        from scripts.platformkit.bestbets.degenerate_guard import (  # noqa: PLC0415
            mark_degenerate_sports as _mark,
        )
        return _mark(cards)
    except Exception:  # noqa: BLE001
        return cards


def _mark_mlb_uniformity(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-board MLB moneyline uniformity demote (REVIEW iter2 P0).

    Runs after _mark_degenerate_sports. Labels any MLB moneyline slate that
    collapses to <= 2 distinct model_prob values as degenerate_model=True so
    the subsequent _suppress_degenerate pass forces decision=no_bet + tier=None.
    Never raises; returns cards unchanged on any error.
    """
    try:
        from predict_service.mlb_board_uniformity_label import (  # noqa: PLC0415
            label_mlb_moneyline_cards as _label,
        )
        return _label(cards)
    except Exception:  # noqa: BLE001
        return cards


def _suppress_degenerate(cards: List[Dict[str, Any]]) -> tuple:
    """W-DEGEN-GATE: FORCE no_bet + null tier/ev/stake on degenerate cards.

    Returns (tradable_cards, suppressed_cards). Tradable is the ranked board;
    suppressed carries nulled-out degen cards for audit only. Never raises.
    """
    tradable: List[Dict[str, Any]] = []
    suppressed: List[Dict[str, Any]] = []
    for c in cards:
        if not isinstance(c, dict):
            tradable.append(c)
            continue
        if c.get("degenerate_model"):
            c["decision"] = "no_bet"
            c["tier"] = None
            c["ev"] = None
            c["stake_units"] = None
            c["edge_vs_market"] = 0.0
            suppressed.append(c)
        else:
            tradable.append(c)
    return tradable, suppressed


def _apply_stale_suppression(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Final filter: drop/demote completed or stale-tipoff cards. Never raises."""
    try:
        from scripts.platformkit.bestbets.stale_game_suppressor import (  # noqa: PLC0415
            apply_suppression as _supp,
        )
        state_map: Dict[str, Any] = {
            str(c["game_id"]): {
                "state": str(c.get("status") or ""),
                "completed": str(c.get("status") or "") in ("done", "final", "post"),
                "commence_time": c.get("tipoff_utc"),
            }
            for c in cards if isinstance(c, dict) and c.get("game_id")
        }
        return _supp(cards, state_map=state_map)
    except Exception:  # noqa: BLE001
        return cards


def compute_best_bets(
    sport: str, tier_filter: Optional[str] = None,
    status_filter: Optional[str] = None, include_props: bool = True,
) -> Dict[str, Any]:
    """Ranked calibrated divergence cards. Never raises; degrades to empty."""
    if tier_filter and tier_filter.upper() not in VALID_TIERS:
        tier_filter = None
    if status_filter and status_filter.lower() not in VALID_STATUSES:
        status_filter = None
    all_cards: List[Dict[str, Any]] = []
    try:
        view = _get_edge_view(sport)
        if isinstance(view, dict) and view.get("status") == "ok":
            for g in view.get("games") or []:
                try:
                    dec = _do_decide_game(g)
                    dec.setdefault("live", {})
                    all_cards.extend(_cards_from_game(dec, sport))
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    if include_props:
        try:
            all_cards.extend(_cards_from_props(sport, status_filter))
        except Exception:  # noqa: BLE001
            pass
    if tier_filter:
        all_cards = [c for c in all_cards if c.get("tier") == tier_filter.upper()]
    if status_filter:
        all_cards = [c for c in all_cards if c.get("status") == status_filter.lower()]
    # QA1: sanitize Yes/No binaries and stale format cards.
    try:
        from scripts.platformkit.bestbets.board_sanitizer import sanitize as _san  # noqa: PLC0415
        all_cards = _san(all_cards)
    except Exception:  # noqa: BLE001
        pass
    # QA2: label flat-prior sports; W-DEGEN-GATE: force no_bet + null fields.
    all_cards = _mark_degenerate_sports(all_cards)
    # QA2b (iter2 P0): per-board MLB moneyline uniformity demote.
    all_cards = _mark_mlb_uniformity(all_cards)
    all_cards, suppressed = _suppress_degenerate(all_cards)
    # QA-stale: drop completed games, stale tipoffs.
    all_cards = _apply_stale_suppression(all_cards)
    all_cards = _rank_cards(all_cards, tier_rank=_TIER_RANK)
    return {
        "status": "ok", "sport": sport, "cards": all_cards,
        "count": len(all_cards), "honest_note": _HONEST_NOTE,
        "edge_claimed": False, "suppressed_degenerate": suppressed,
    }


__all__ = ["compute_best_bets"]
