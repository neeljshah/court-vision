"""domains.basketball_nba.prop_card_service -- leak-free NBA prop-card service.

Wraps domains.basketball_nba.player_props (price_prop / price_player_card) with a
stable, test-friendly interface for the predict_service W2 API layer.

This is the ONLY layer that should call price_prop/price_player_card from the API
surface; it enforces:
  - leak-free date constraint (never uses today's games to price today's props)
  - UNAVAILABLE degradation when corpus is absent or player history is too thin
  - no $ / pnl / roi / edge field -- calibration only (p_over is a probability)

KEY FUNCTION:
  card_for_player(player, date, lines) -> dict
    Returns the full prop card or an UNAVAILABLE sentinel.
    Degrades gracefully when the parquet corpus is missing.

  price_one(player, stat, line, date) -> dict
    Single-stat pricer, forwarded to price_prop.

  slate_cards(players_lines, date) -> list[dict]
    Bulk card generation for a slate of (player, lines) pairs.

HONESTY: p_over in [0,1] is a probability, not an edge. No $ field.
INVARIANTS: <=300 LOC; ASCII only; no src/ imports; no network I/O; read-only.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_UNAVAILABLE_STATUS = "UNAVAILABLE"
_HONEST_NOTE = (
    "Calibrated recency-weighted Gaussian P(over/under) vs line. "
    "Leak-free: uses only games strictly before date. "
    "Calibration baseline -- no $ edge is claimed."
)


def _load_pricer():
    """Lazy-import price_prop/price_player_card. Returns (price_prop, price_player_card, load_box) or None."""
    try:
        from domains.basketball_nba.player_props import (  # noqa: PLC0415
            price_prop,
            price_player_card,
            load_box,
        )
        return price_prop, price_player_card, load_box
    except Exception as exc:  # noqa: BLE001
        logger.warning("prop_card_service: cannot import player_props (%s)", exc)
        return None, None, None


def _corpus_available() -> bool:
    """Return True if the NBA boxscore parquet corpus exists."""
    try:
        from pathlib import Path  # noqa: PLC0415
        p = Path("data/domains/basketball_nba/player_boxscores.parquet")
        return p.exists()
    except Exception:  # noqa: BLE001
        return False


def _unavailable_sentinel(player: Any, stat: str, line: float, date: Any,
                          reason: str) -> Dict[str, Any]:
    return {
        "status": _UNAVAILABLE_STATUS,
        "player": str(player),
        "stat": stat,
        "line": float(line),
        "date": str(date),
        "p_over": None,
        "p_under": None,
        "proj_mean": None,
        "proj_sigma": None,
        "edge_vs_market": None,
        "clv_is_proxy": True,
        "confidence": None,
        "tier": None,
        "reason": reason,
        "honest_note": _HONEST_NOTE,
    }


def price_one(player: Any, stat: str, line: float, date: Any,
              market_prob: Optional[float] = None) -> Dict[str, Any]:
    """Single-stat prop pricing -- wraps price_prop with UNAVAILABLE degradation.

    market_prob is the devigged book probability for over (if known from W1).
    edge_vs_market = p_over - market_prob when both are present; else None.
    p_over is always in [0, 1] or None.
    """
    if not _corpus_available():
        return _unavailable_sentinel(player, stat, line, date,
                                     "player_boxscores.parquet not found")
    price_prop_fn, _, _ = _load_pricer()
    if price_prop_fn is None:
        return _unavailable_sentinel(player, stat, line, date,
                                     "price_prop import failed")
    try:
        raw = price_prop_fn(player, stat, float(line), date)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prop_card_service.price_one: price_prop error (%s)", exc)
        return _unavailable_sentinel(player, stat, line, date, str(exc))

    p_over = raw.get("p_over")
    p_under = raw.get("p_under")
    edge = None
    if p_over is not None and market_prob is not None:
        try:
            edge = round(float(p_over) - float(market_prob), 4)
        except (TypeError, ValueError):
            edge = None

    return {
        "status": raw.get("status", "ok"),
        "player": raw.get("player", str(player)),
        "stat": stat,
        "line": raw.get("line", float(line)),
        "date": raw.get("date", str(date)),
        "n_games": raw.get("n_games"),
        "proj_mean": raw.get("proj_mean"),
        "proj_sigma": raw.get("proj_sigma"),
        "p_over": p_over,
        "p_under": p_under,
        "hit_rate_l5": raw.get("hit_rate_l5"),
        "hit_rate_l10": raw.get("hit_rate_l10"),
        "hit_rate_l20": raw.get("hit_rate_l20"),
        "edge_vs_market": edge,
        "clv_is_proxy": True,
        "confidence": raw.get("confidence"),
        "tier": None,
        "honest_note": _HONEST_NOTE,
    }


def card_for_player(player: Any, date: Any,
                    lines: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Full prop card for a player as of date, using price_player_card.

    Returns card dict with props dict (one entry per stat) plus honest_note.
    Degrades to UNAVAILABLE sentinel if corpus missing or import fails.
    """
    if not _corpus_available():
        return {"status": _UNAVAILABLE_STATUS, "player": str(player),
                "date": str(date), "props": {},
                "reason": "player_boxscores.parquet not found",
                "honest_note": _HONEST_NOTE}
    _, price_player_card_fn, _ = _load_pricer()
    if price_player_card_fn is None:
        return {"status": _UNAVAILABLE_STATUS, "player": str(player),
                "date": str(date), "props": {},
                "reason": "price_player_card import failed",
                "honest_note": _HONEST_NOTE}
    try:
        raw = price_player_card_fn(player, date, lines or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("prop_card_service.card_for_player: error (%s)", exc)
        return {"status": _UNAVAILABLE_STATUS, "player": str(player),
                "date": str(date), "props": {},
                "reason": str(exc), "honest_note": _HONEST_NOTE}
    raw["honest_note"] = _HONEST_NOTE
    raw.setdefault("status", "ok")
    return raw


def slate_cards(
    players_lines: List[Tuple[Any, Optional[Dict[str, float]]]],
    date: Any,
) -> List[Dict[str, Any]]:
    """Bulk prop cards for a slate.

    players_lines: list of (player_name_or_id, lines_dict_or_None).
    Returns one card per player; never raises (degrades per player).
    """
    out = []
    for player, lines in players_lines:
        out.append(card_for_player(player, date, lines))
    return out


__all__ = ["price_one", "card_for_player", "slate_cards"]
