"""predict_service.bestbets_props -- player-prop BestBetCards for the board.

Split out of bestbets_compute to keep that file <=300 LOC. Builds prop cards from
the W2 prop_surface rows of the canonical snapshot. NBA offseason / no snapshot ->
[]. Never raises. No $ key; edge_vs_market is a prob diff, not a dollar amount.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no $ key.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def cards_from_props(
    sport: str,
    status_filter: Optional[str],
    *,
    honest_note: str,
    clv_empty: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """BestBetCards from W2 prop_surface rows; NBA offseason -> []. Never raises."""
    prop_status = "pregame"
    if status_filter and prop_status != status_filter:
        return []
    try:
        from predict_service import store as _store  # noqa: PLC0415
        env = _store.read_latest(sport)
    except Exception:  # noqa: BLE001
        return []
    if not env or getattr(env, "status", "unavailable") != "ok":
        return []
    try:
        from predict_service.frontend.props_routes import (  # noqa: PLC0415
            _prop_lines_from_markets,
        )
        from predict_service.prop_surface import build_prop_rows  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    from datetime import datetime, timezone
    prop_date = datetime.now(tz=timezone.utc).date().isoformat()
    cards: List[Dict[str, Any]] = []
    for pred in getattr(env, "predictions", []) or []:
        lines = _prop_lines_from_markets(getattr(pred, "markets", []) or [])
        for row in build_prop_rows(sport, prop_date, lines):
            if not isinstance(row, dict):
                continue
            try:
                p_over = float(row["p_over"])
                edge_f = float(row["edge_vs_market"])
            except (TypeError, ValueError, KeyError):
                continue
            if not (0.0 <= p_over <= 1.0) or edge_f <= 0:
                continue
            cards.append({
                "game_id": str(getattr(pred, "game_id", "")),
                "matchup": (f"{getattr(pred,'home','')} vs "
                            f"{getattr(pred,'away','')}"),
                "sport": sport, "market_type": "player_prop",
                "prop_player": str(row.get("player", "")),
                "prop_stat": str(row.get("stat", "")),
                "side": "over",
                "model_prob": round(p_over, 6),
                "market_prob": round(p_over - edge_f, 6),
                "best_book": str(row.get("book", "")),
                "best_odds": None, "all_books": [],
                "edge_vs_market": round(edge_f, 6),
                "units": 1.0, "tier": "C",
                "confidence": round(p_over, 6),
                "clv": dict(clv_empty), "clv_is_proxy": True,
                "status": prop_status, "honest_note": honest_note,
            })
    return cards


__all__ = ["cards_from_props"]
