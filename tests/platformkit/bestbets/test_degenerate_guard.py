"""Per-file tests for scripts/platformkit/bestbets/degenerate_guard.py.

QA-ISSUE-2 acceptance criteria:
  * A sport whose model_probs collapse to <=2 distinct values across many games
    (the MLB symptom: 11 cards all 0.5345 / 0.4655) is DEMOTED:
      - tier -> 'C' (never Tier-A/B)
      - edge_claimed -> False
      - honest_note labels it model-unavailable / base-rate-only
  * A genuine sport with varied per-game probs is left UNTOUCHED.
  * A small slate (< MIN_CARDS) is not demoted on uniformity alone.
  * No $ / roi / pnl field is ever introduced.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/bestbets/test_degenerate_guard.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List

from scripts.platformkit.bestbets.degenerate_guard import (
    DEGENERATE_NOTE,
    MIN_CARDS,
    mark_degenerate_sports,
)


def _card(sport: str, gid: str, prob: float, tier: str = "A") -> Dict[str, Any]:
    return {
        "game_id": gid, "matchup": f"{gid} home vs away", "sport": sport,
        "market_type": "moneyline", "side": "home",
        "model_prob": prob, "market_prob": prob - 0.03,
        "edge_vs_market": 0.03, "units": 1.0, "tier": tier,
        "confidence": prob, "status": "pregame", "honest_note": "orig",
    }


def _mlb_flat_slate(n: int = 11) -> List[Dict[str, Any]]:
    """The exact QA symptom: n MLB cards collapsing to two probs (0.5345/0.4655)."""
    cards = []
    for i in range(n):
        prob = 0.5345 if i % 2 == 0 else 0.4655
        cards.append(_card("mlb", f"mlb_{i}", prob, tier="A"))
    return cards


def _nba_varied_slate(n: int = 6) -> List[Dict[str, Any]]:
    """A genuine NBA slate with distinct per-game probs."""
    return [_card("nba", f"nba_{i}", 0.50 + i * 0.013, tier="A") for i in range(n)]


# ---------------------------------------------------------------------------
# Core acceptance: degenerate MLB slate demoted
# ---------------------------------------------------------------------------

class TestDegenerateDemotion:

    def test_flat_mlb_slate_demoted_to_tier_c(self):
        cards = _mlb_flat_slate(11)
        mark_degenerate_sports(cards)
        assert all(c["tier"] == "C" for c in cards)

    def test_flat_mlb_slate_edge_claimed_false(self):
        cards = _mlb_flat_slate(11)
        mark_degenerate_sports(cards)
        assert all(c["edge_claimed"] is False for c in cards)

    def test_flat_mlb_slate_honest_note_set(self):
        cards = _mlb_flat_slate(11)
        mark_degenerate_sports(cards)
        assert all(c["honest_note"] == DEGENERATE_NOTE for c in cards)
        assert all(c["degenerate_model"] is True for c in cards)

    def test_single_value_collapse_also_demoted(self):
        """All cards sharing ONE prob is the strongest degeneracy signal."""
        cards = [_card("mlb", f"m_{i}", 0.5, tier="B") for i in range(5)]
        mark_degenerate_sports(cards)
        assert all(c["tier"] == "C" and c["edge_claimed"] is False for c in cards)


# ---------------------------------------------------------------------------
# Genuine sports are untouched
# ---------------------------------------------------------------------------

class TestGenuineSportUntouched:

    def test_varied_nba_slate_not_demoted(self):
        cards = _nba_varied_slate(6)
        mark_degenerate_sports(cards)
        assert all(c["tier"] == "A" for c in cards)
        assert all("degenerate_model" not in c for c in cards)
        assert all(c["honest_note"] == "orig" for c in cards)

    def test_mixed_board_only_degenerate_sport_demoted(self):
        """A board with a flat MLB slate + a varied NBA slate: only MLB demoted."""
        cards = _mlb_flat_slate(11) + _nba_varied_slate(6)
        mark_degenerate_sports(cards)
        mlb = [c for c in cards if c["sport"] == "mlb"]
        nba = [c for c in cards if c["sport"] == "nba"]
        assert all(c["tier"] == "C" for c in mlb)
        assert all(c["tier"] == "A" for c in nba)


# ---------------------------------------------------------------------------
# Small slate / robustness
# ---------------------------------------------------------------------------

class TestRobustness:

    def test_small_slate_not_demoted_on_uniformity_alone(self):
        """Fewer than MIN_CARDS sharing a prob is not a flat-prior verdict."""
        cards = [_card("mlb", f"m_{i}", 0.5) for i in range(MIN_CARDS - 1)]
        mark_degenerate_sports(cards)
        assert all(c["tier"] == "A" for c in cards)

    def test_empty_list_returns_empty(self):
        assert mark_degenerate_sports([]) == []

    def test_never_introduces_dollar_field(self):
        cards = _mlb_flat_slate(11)
        mark_degenerate_sports(cards)
        forbidden = {"dollar", "pnl", "roi", "profit", "bankroll", "usd"}
        for c in cards:
            assert not ({k.lower() for k in c} & forbidden)

    def test_degenerate_card_never_ranked_tier_a_or_b(self):
        """Hard invariant: a flat-prior card must never carry tier A or B."""
        cards = _mlb_flat_slate(11)
        mark_degenerate_sports(cards)
        assert not any(c["tier"] in ("A", "B") for c in cards)
