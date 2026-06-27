"""predict_service.bestbets_model_only -- honest MODEL-ONLY (line-only) cards.

Split out of bestbets_compute to keep that file <=300 LOC. A MODEL-ONLY card is a
market the SNAPSHOT/model never priced (e.g. total / run-line) but for which a
FRESH BOOK LINE was captured. We surface the line + best book for transparency and
NEVER fabricate a model_prob, tier, edge, EV, or stake. The card's market_prob is
the real devigged book prob (so the board sanitizer keeps it); edge_vs_market is
forced to 0.0; tier/confidence are None; units are 0.0. This mirrors how props
show an unpriced projection -- no $ edge claimed, nothing invented.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no $ key.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

MODEL_ONLY_NOTE = (
    "LINE-ONLY: a fresh book line for this market exists but the model does not "
    "price it (e.g. total / run-line we do not project). The line + best book are "
    "shown for transparency; there is NO model_prob, tier, edge, or stake. No $ "
    "edge claimed; nothing fabricated."
)


def model_only_cards(
    game: Dict[str, Any],
    sport: str,
    cand_lookup: Dict[Tuple[str, str], Dict[str, Any]],
    *,
    game_id: str,
    matchup: str,
    status: str,
    tipoff_utc: Any,
    clv_empty: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build the honest model-only/line-only cards for one decided game.

    Reads game['info_bets'] (decision=='model_only' rows from decide_game). A row
    with NO real devigged market_prob is omitted (nothing honest to show -- never
    fabricated). Never raises on a malformed row.
    """
    cards: List[Dict[str, Any]] = []
    for info in game.get("info_bets") or []:
        if not isinstance(info, dict):
            continue
        if str(info.get("decision", "")) != "model_only":
            continue
        mt = str(info.get("market_type", ""))
        side = str(info.get("side", ""))
        cand = cand_lookup.get((mt, side)) or {}
        mkt_raw = cand.get("market_prob")
        if mkt_raw is None:
            mkt_raw = info.get("market_prob")
        if mkt_raw is None:
            continue  # no real devigged book prob -> nothing honest to show
        try:
            mkt = float(mkt_raw)
        except (TypeError, ValueError):
            continue
        bo = cand.get("best_odds") or info.get("best_odds")
        best_odds: Optional[float]
        try:
            best_odds = round(float(bo), 6) if bo is not None else None
        except (TypeError, ValueError):
            best_odds = None
        cards.append({
            "game_id": game_id, "matchup": matchup, "sport": sport,
            "market_type": mt, "prop_player": None, "prop_stat": None,
            "side": side, "line": cand.get("line") or info.get("line"),
            "model_prob": None, "market_prob": round(mkt, 6),
            "best_book": str(cand.get("best_book") or info.get("best_book") or ""),
            "best_odds": best_odds,
            "all_books": list(cand.get("all_books") or []),
            "edge_vs_market": 0.0,
            "units": 0.0, "tier": None, "confidence": None,
            "decision": "model_only",
            "clv": dict(clv_empty), "clv_is_proxy": True,
            "status": status, "honest_note": MODEL_ONLY_NOTE,
            "tipoff_utc": tipoff_utc,
        })
    return cards


__all__ = ["model_only_cards", "MODEL_ONLY_NOTE"]
