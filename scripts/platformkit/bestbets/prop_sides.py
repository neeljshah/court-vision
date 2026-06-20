"""scripts.platformkit.bestbets.prop_sides -- emit the correct side card for a prop.

BB-Q3: Surface the under side of player props instead of silently dropping rows
whose p_over < 0.5.  Pure function with no I/O.

KEY FUNCTION
------------
emit_side_card(row) -> dict | None
    Given a PlayerPropRow (see predict_service.prop_surface for the full shape),
    choose which side has genuine calibrated edge and return a card for that side.
    Returns None when neither side clears the minimum threshold.

Decision logic
--------------
    Let e = edge_threshold (default EDGE_MIN = 0.02).
    * over card  when p_over  > 0.5 + e
    * under card when p_under > 0.5 + e  (i.e. p_over < 0.5 - e)
    * no card    otherwise (|p_over - 0.5| <= e, or probabilities missing)

edge_threshold is configurable so callers can tighten/relax the floor.

Card shape (returned dict)
--------------------------
  {
    "player":      str,
    "stat":        str,
    "line":        float,
    "book":        str,
    "side":        "over" | "under",
    "side_prob":   float,        # model prob for the chosen side (in [0,1])
    "edge_vs_market": float|None,  # sign-adjusted: + means model favours this side
    "units":       float,        # 1.0 flat (no Kelly / no $ sizing)
    "tier":        None,         # reserved; tier assignment is a separate concern
    "confidence":  str|None,     # forwarded from input row
    "clv_is_proxy": bool,        # forwarded (always True for props)
    "date":        str,
    "sport":       str,
    "honest_note": str,
  }

RAILS (binding)
---------------
  * UNITS not $: never includes a dollar / pnl / roi field.
  * CALIBRATION not edge: units=1.0 flat; no Kelly multiplier; no profit claim.
  * Pure function: no I/O, no network, no global state mutation.
  * Never raises: bad / missing inputs degrade to None.
  * ASCII only; <= 300 LOC.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Minimum probability surplus above 0.5 for a side to produce a card.
# Keeps p_over=0.50 (flat) from generating any card at all.
EDGE_MIN: float = 0.02

_HONEST_NOTE = (
    "Calibrated P(side) vs line: recency-weighted Gaussian projection. "
    "Side chosen by max(p_over, p_under) > 0.5+edge_threshold. "
    "units=1.0 flat -- no dollar edge or profit claim. "
    "clv_is_proxy=True: no true prop closing lines available."
)


def emit_side_card(
    row: Dict[str, Any],
    *,
    edge_threshold: float = EDGE_MIN,
) -> Optional[Dict[str, Any]]:
    """Return the best-side card for a PlayerPropRow, or None.

    Parameters
    ----------
    row:
        A PlayerPropRow dict as produced by predict_service.prop_surface.
        Must contain at least: p_over, p_under, and player/stat/line/book/sport.
    edge_threshold:
        Minimum surplus above 0.5 for a side to qualify.  Default EDGE_MIN=0.02.
        Pass 0.0 to accept any model lean.

    Returns
    -------
    dict with keys documented in the module docstring, or None when:
      * p_over or p_under is None / missing / non-finite
      * neither side exceeds 0.5 + edge_threshold
    """
    try:
        et = float(edge_threshold)
    except (TypeError, ValueError):
        et = EDGE_MIN

    # Extract and validate probabilities.
    p_over_raw = row.get("p_over")
    p_under_raw = row.get("p_under")

    if p_over_raw is None or p_under_raw is None:
        return None

    try:
        p_over = float(p_over_raw)
        p_under = float(p_under_raw)
    except (TypeError, ValueError):
        return None

    # Guard against non-finite values.
    import math
    if not math.isfinite(p_over) or not math.isfinite(p_under):
        return None

    # Determine side: the side whose probability exceeds 0.5 + threshold wins.
    # When both clear (unusual but possible with independent pricing), prefer the
    # side with the higher probability surplus.
    over_surplus = p_over - 0.5
    under_surplus = p_under - 0.5

    if over_surplus > et and over_surplus >= under_surplus:
        chosen_side = "over"
        side_prob = p_over
        # edge_vs_market from the row is already defined as (p_over - market_prob).
        # For the over side we forward it directly.
        raw_edge = row.get("edge_vs_market")
        edge_adj: Optional[float] = float(raw_edge) if raw_edge is not None else None
    elif under_surplus > et:
        chosen_side = "under"
        side_prob = p_under
        # For the under side the edge is -(edge_vs_market) because edge_vs_market
        # is defined as (p_over - market_prob): a negative value means the under
        # has the edge.  We expose it sign-flipped so the card reads positively.
        raw_edge = row.get("edge_vs_market")
        if raw_edge is not None:
            try:
                edge_adj = -float(raw_edge)
            except (TypeError, ValueError):
                edge_adj = None
        else:
            edge_adj = None
    else:
        # Neither side clears the threshold -> no card.
        return None

    return {
        "player": str(row.get("player", "")),
        "stat": str(row.get("stat", "")),
        "line": float(row["line"]) if row.get("line") is not None else None,
        "book": str(row.get("book", "")),
        "side": chosen_side,
        "side_prob": side_prob,
        "edge_vs_market": edge_adj,
        "units": 1.0,
        "tier": None,
        "confidence": row.get("confidence"),
        "clv_is_proxy": bool(row.get("clv_is_proxy", True)),
        "date": str(row.get("date", "")),
        "sport": str(row.get("sport", "")),
        "honest_note": _HONEST_NOTE,
    }


def emit_side_cards(
    rows: list,
    *,
    edge_threshold: float = EDGE_MIN,
) -> list:
    """Filter a list of PlayerPropRows through emit_side_card, dropping Nones.

    Parameters
    ----------
    rows:
        List of PlayerPropRow dicts.
    edge_threshold:
        Forwarded to emit_side_card for each row.

    Returns
    -------
    list of side-card dicts (only rows that produced a card).
    """
    cards = []
    for row in rows:
        card = emit_side_card(row, edge_threshold=edge_threshold)
        if card is not None:
            cards.append(card)
    return cards


__all__ = [
    "EDGE_MIN",
    "emit_side_card",
    "emit_side_cards",
]
