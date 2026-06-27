"""Per-file tests for scripts.platformkit.bestbets.prop_sides.

BB-Q3: Surface the under side of player props.

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/bestbets/test_prop_sides.py -q

Acceptance criteria (from BACKLOG BB-Q3-prop-sides):
  * p_over=0.40 with positive under edge -> card with side='under'.
  * p_over=0.55 with edge -> card with side='over'.
  * p_over=0.50 flat (no surplus) -> no card (returns None).
  * No $ field, units=1.0 flat on every card.
  * Missing/None probabilities -> None (safe degradation).
  * edge_vs_market sign-flipped correctly for the under side.
"""
from __future__ import annotations

import sys
import pathlib

# Ensure the scripts tree is importable from the repo root.
_REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from scripts.platformkit.bestbets.prop_sides import (
    EDGE_MIN,
    emit_side_card,
    emit_side_cards,
)

# ---------------------------------------------------------------------------
# Helper: build a minimal PlayerPropRow-shaped dict
# ---------------------------------------------------------------------------

def _row(
    p_over: float,
    p_under: float,
    edge_vs_market: float | None = None,
    player: str = "Test Player",
    stat: str = "pts",
    line: float = 22.5,
    book: str = "testbook",
    sport: str = "nba",
    date: str = "2026-06-19",
) -> dict:
    return {
        "player": player,
        "stat": stat,
        "line": line,
        "book": book,
        "p_over": p_over,
        "p_under": p_under,
        "proj_mean": None,
        "proj_sigma": None,
        "edge_vs_market": edge_vs_market,
        "tier": None,
        "confidence": "recency_gaussian",
        "clv_is_proxy": True,
        "date": date,
        "sport": sport,
        "honest_note": "test",
    }


# ---------------------------------------------------------------------------
# Core acceptance tests
# ---------------------------------------------------------------------------

def test_under_card_when_p_over_low():
    """p_over=0.40 -> p_under=0.60 -> card with side='under'."""
    card = emit_side_card(_row(p_over=0.40, p_under=0.60, edge_vs_market=-0.10))
    assert card is not None, "Expected an under card but got None"
    assert card["side"] == "under"
    assert card["side_prob"] == 0.60


def test_over_card_when_p_over_high():
    """p_over=0.55 (surplus=0.05 > EDGE_MIN=0.02) -> card with side='over'."""
    card = emit_side_card(_row(p_over=0.55, p_under=0.45, edge_vs_market=0.05))
    assert card is not None, "Expected an over card but got None"
    assert card["side"] == "over"
    assert card["side_prob"] == 0.55


def test_no_card_when_flat():
    """p_over=0.50 -> neither side clears threshold -> None."""
    card = emit_side_card(_row(p_over=0.50, p_under=0.50))
    assert card is None, "Expected None for flat p_over=0.50 but got a card"


def test_no_card_when_lean_below_edge_min():
    """p_over=0.51 (surplus=0.01 < EDGE_MIN=0.02) -> no card."""
    card = emit_side_card(_row(p_over=0.51, p_under=0.49))
    assert card is None


# ---------------------------------------------------------------------------
# UNITS not $ -- no dollar field anywhere
# ---------------------------------------------------------------------------

def test_units_flat_over():
    """units=1.0 on an over card; no $ / pnl / roi key."""
    card = emit_side_card(_row(p_over=0.60, p_under=0.40))
    assert card is not None
    assert card["units"] == 1.0
    for forbidden in ("dollar", "pnl", "roi", "profit"):
        assert forbidden not in card, f"Forbidden key '{forbidden}' found in card"


def test_units_flat_under():
    """units=1.0 on an under card; no $ / pnl / roi key."""
    card = emit_side_card(_row(p_over=0.35, p_under=0.65))
    assert card is not None
    assert card["units"] == 1.0
    for forbidden in ("dollar", "pnl", "roi", "profit"):
        assert forbidden not in card, f"Forbidden key '{forbidden}' found in card"


# ---------------------------------------------------------------------------
# edge_vs_market sign convention
# ---------------------------------------------------------------------------

def test_under_edge_sign_flipped():
    """For the under side, edge_vs_market is sign-flipped vs the row value."""
    # edge_vs_market in the row is (p_over - market_prob): negative means under-edge.
    card = emit_side_card(_row(p_over=0.40, p_under=0.60, edge_vs_market=-0.10))
    assert card is not None
    assert card["side"] == "under"
    # Flipped: -(-0.10) = +0.10
    assert abs(card["edge_vs_market"] - 0.10) < 1e-9


def test_over_edge_forwarded_unchanged():
    """For the over side, edge_vs_market is forwarded without sign flip."""
    card = emit_side_card(_row(p_over=0.60, p_under=0.40, edge_vs_market=0.08))
    assert card is not None
    assert card["side"] == "over"
    assert abs(card["edge_vs_market"] - 0.08) < 1e-9


# ---------------------------------------------------------------------------
# Safe degradation
# ---------------------------------------------------------------------------

def test_none_p_over_returns_none():
    """Missing p_over -> None (safe degradation)."""
    row = _row(p_over=0.60, p_under=0.40)
    row["p_over"] = None
    assert emit_side_card(row) is None


def test_none_p_under_returns_none():
    """Missing p_under -> None (safe degradation)."""
    row = _row(p_over=0.40, p_under=0.60)
    row["p_under"] = None
    assert emit_side_card(row) is None


def test_missing_edge_vs_market_is_none_not_raised():
    """Missing edge_vs_market is allowed; card is still emitted."""
    card = emit_side_card(_row(p_over=0.60, p_under=0.40, edge_vs_market=None))
    assert card is not None
    assert card["edge_vs_market"] is None


# ---------------------------------------------------------------------------
# clv_is_proxy always forwarded
# ---------------------------------------------------------------------------

def test_clv_is_proxy_forwarded():
    """clv_is_proxy from the row is always forwarded to the card."""
    card = emit_side_card(_row(p_over=0.60, p_under=0.40))
    assert card is not None
    assert card["clv_is_proxy"] is True


# ---------------------------------------------------------------------------
# custom edge_threshold
# ---------------------------------------------------------------------------

def test_custom_threshold_tighter():
    """With threshold=0.10, p_over=0.55 (surplus=0.05) -> no card."""
    card = emit_side_card(_row(p_over=0.55, p_under=0.45), edge_threshold=0.10)
    assert card is None


def test_custom_threshold_zero_accepts_any_lean():
    """With threshold=0.0, p_over=0.51 (lean=0.01) -> over card."""
    card = emit_side_card(_row(p_over=0.51, p_under=0.49), edge_threshold=0.0)
    assert card is not None
    assert card["side"] == "over"


# ---------------------------------------------------------------------------
# emit_side_cards (batch helper)
# ---------------------------------------------------------------------------

def test_emit_side_cards_filters_nones():
    """Batch helper drops rows that produce no card."""
    rows = [
        _row(p_over=0.60, p_under=0.40),   # over card
        _row(p_over=0.50, p_under=0.50),   # no card (flat)
        _row(p_over=0.35, p_under=0.65),   # under card
    ]
    cards = emit_side_cards(rows)
    assert len(cards) == 2
    sides = {c["side"] for c in cards}
    assert sides == {"over", "under"}


def test_emit_side_cards_empty_input():
    """Empty input returns empty list."""
    assert emit_side_cards([]) == []
