"""predict_service.tests.test_bestbets_compute -- W-DEGEN-GATE unit tests.

Acceptance criteria (W-DEGEN-GATE):
  D1. A card on a degenerate-flagged sport returns decision=no_bet.
  D2. Degenerate card: tier is None (never 'A', 'B', or 'C').
  D3. Degenerate card: ev is None.
  D4. Degenerate card: stake_units is None.
  D5. Degenerate card: edge_vs_market == 0.0 (not a calibrated divergence).
  D6. Degenerate card does NOT appear in compute_best_bets cards list.
  D7. Degenerate card appears in suppressed_degenerate list.
  D8. A flat prior (model_prob==0.5345 across >= 4 cards) triggers suppression.
  D9. Non-degenerate sport cards keep ranked divergence (tier preserved).
  D10. No $ field anywhere in output.
  D11. edge_vs_market is labeled as prob-diff, not $-field.
  D12. _suppress_degenerate never raises on garbage input.

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/tests/test_bestbets_compute.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.bestbets_compute import (  # noqa: E402
    _suppress_degenerate,
    compute_best_bets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card(
    sport: str = "mlb",
    tier: str = "A",
    model_prob: float = 0.62,
    market_prob: float = 0.50,
    degenerate: bool = False,
) -> Dict[str, Any]:
    """Minimal valid BestBetCard dict."""
    c: Dict[str, Any] = {
        "game_id": "g1",
        "matchup": "TeamA vs TeamB",
        "sport": sport,
        "market_type": "moneyline",
        "side": "home",
        "model_prob": model_prob,
        "market_prob": market_prob,
        "best_book": "book1",
        "best_odds": -110,
        "all_books": [],
        "edge_vs_market": round(model_prob - market_prob, 6),
        "units": 1.0,
        "tier": tier,
        "ev": 0.08,
        "stake_units": 1.0,
        "confidence": model_prob,
        "clv": {"clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
        "clv_is_proxy": True,
        "status": "pregame",
        "honest_note": "Calibrated; no $ edge claimed.",
        "tipoff_utc": None,
    }
    if degenerate:
        c["degenerate_model"] = True
    return c


def _degen_card(**kw) -> Dict[str, Any]:
    return _card(degenerate=True, **kw)


def _has_dollar_key(obj: object) -> bool:
    if isinstance(obj, dict):
        return any("$" in str(k) or _has_dollar_key(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_has_dollar_key(i) for i in obj)
    return False


# ---------------------------------------------------------------------------
# D1-D5: _suppress_degenerate field contracts on a single flagged card
# ---------------------------------------------------------------------------

class TestSuppressDegenerate:
    """Direct unit tests for _suppress_degenerate."""

    def test_d1_decision_is_no_bet(self):
        cards = [_degen_card(tier="A")]
        tradable, suppressed = _suppress_degenerate(cards)
        assert suppressed[0]["decision"] == "no_bet", "D1: decision must be no_bet"

    def test_d2_tier_is_none(self):
        cards = [_degen_card(tier="A")]
        _, suppressed = _suppress_degenerate(cards)
        assert suppressed[0]["tier"] is None, "D2: tier must be None, not Tier-A"

    def test_d3_ev_is_none(self):
        cards = [_degen_card(tier="B")]
        _, suppressed = _suppress_degenerate(cards)
        assert suppressed[0]["ev"] is None, "D3: ev must be None"

    def test_d4_stake_units_is_none(self):
        cards = [_degen_card(tier="C")]
        _, suppressed = _suppress_degenerate(cards)
        assert suppressed[0]["stake_units"] is None, "D4: stake_units must be None"

    def test_d5_edge_vs_market_zeroed(self):
        cards = [_degen_card(tier="A", model_prob=0.5345, market_prob=0.4655)]
        _, suppressed = _suppress_degenerate(cards)
        assert suppressed[0]["edge_vs_market"] == 0.0, (
            "D5: edge_vs_market must be 0.0 on degenerate card"
        )

    def test_d6_not_in_tradable(self):
        cards = [_degen_card(tier="A"), _card(sport="nba", tier="B")]
        tradable, _ = _suppress_degenerate(cards)
        sports_tradable = [c["sport"] for c in tradable]
        assert "mlb" not in sports_tradable, "D6: degenerate card must not be in tradable"

    def test_d7_in_suppressed(self):
        cards = [_degen_card(tier="A"), _card(sport="nba", tier="B")]
        _, suppressed = _suppress_degenerate(cards)
        assert len(suppressed) == 1, "D7: exactly one suppressed card"
        assert suppressed[0]["sport"] == "mlb"

    def test_non_degen_keeps_tier(self):
        cards = [_card(sport="nba", tier="A", degenerate=False)]
        tradable, suppressed = _suppress_degenerate(cards)
        assert len(suppressed) == 0, "D9: non-degen card must not be suppressed"
        assert tradable[0]["tier"] == "A", "D9: non-degen tier must be preserved"

    def test_mixed_slate_splits_correctly(self):
        cards = [
            _degen_card(sport="mlb", tier="A"),
            _card(sport="nba", tier="B"),
            _degen_card(sport="mlb", tier="A"),
        ]
        tradable, suppressed = _suppress_degenerate(cards)
        assert len(tradable) == 1, "Mixed: 1 tradable (nba)"
        assert len(suppressed) == 2, "Mixed: 2 suppressed (mlb degen)"
        assert all(c["tier"] is None for c in suppressed), "All suppressed: tier None"
        assert all(c["decision"] == "no_bet" for c in suppressed)


# ---------------------------------------------------------------------------
# D8: Flat-prior (MLB 0.5345) cards -> flagged by degenerate_guard -> suppressed
# ---------------------------------------------------------------------------

class TestFlatPriorSuppression:
    """D8: verify the degenerate_guard integration path via compute_best_bets."""

    def _make_flat_prior_cards(self, n: int = 6) -> List[Dict[str, Any]]:
        """MLB slate where all model_probs are 0.5345 (the real QA-2 bug value)."""
        cards = []
        for i in range(n):
            c = _card(sport="mlb", tier="A", model_prob=0.5345, market_prob=0.4655)
            c["game_id"] = f"mlb_{i}"
            cards.append(c)
        return cards

    def test_d8_flat_prior_not_on_board(self):
        """compute_best_bets must not emit tier=A cards for a flat-prior sport."""
        flat_cards = self._make_flat_prior_cards(6)
        # Patch away all IO; inject flat cards directly into the pipeline.
        with (
            patch("predict_service.bestbets_compute._get_edge_view",
                  return_value={"status": "unavailable"}),
            patch("predict_service.bestbets_compute._cards_from_props",
                  return_value=flat_cards),
            patch("predict_service.bestbets_compute._apply_stale_suppression",
                  side_effect=lambda c: c),
        ):
            result = compute_best_bets("mlb", include_props=True)

        board_cards = result["cards"]
        suppressed = result["suppressed_degenerate"]
        # No MLB flat-prior card may appear on the ranked board.
        mlb_on_board = [c for c in board_cards if c.get("sport") == "mlb"]
        assert not mlb_on_board, (
            "D8: flat-prior MLB cards must NOT appear on board; "
            "got %d cards with tiers %s" % (
                len(mlb_on_board), [c.get("tier") for c in mlb_on_board])
        )
        assert len(suppressed) > 0, "D8: suppressed_degenerate must be non-empty"
        for c in suppressed:
            assert c.get("tier") is None, "D8: suppressed tier must be None"
            assert c.get("decision") == "no_bet", "D8: suppressed decision must be no_bet"


# ---------------------------------------------------------------------------
# D9: Non-degenerate sport keeps ranked divergence cards
# ---------------------------------------------------------------------------

class TestNonDegenerateKept:
    """D9: non-degenerate sport cards are not suppressed."""

    def test_d9_nba_cards_kept(self):
        nba_cards = [
            _card(sport="nba", tier="A", model_prob=0.62),
            _card(sport="nba", tier="B", model_prob=0.58),
        ]
        with (
            patch("predict_service.bestbets_compute._get_edge_view",
                  return_value={"status": "unavailable"}),
            patch("predict_service.bestbets_compute._cards_from_props",
                  return_value=nba_cards),
            patch("predict_service.bestbets_compute._apply_stale_suppression",
                  side_effect=lambda c: c),
        ):
            result = compute_best_bets("nba", include_props=True)

        board = result["cards"]
        assert len(board) == 2, "D9: both non-degen NBA cards must be on board"
        tiers = {c["tier"] for c in board}
        assert "A" in tiers and "B" in tiers, "D9: tier A and B preserved"
        assert result["suppressed_degenerate"] == [], "D9: no suppressed for non-degen"


# ---------------------------------------------------------------------------
# D10: No $ field in any output
# ---------------------------------------------------------------------------

def test_d10_no_dollar_field():
    cards = [_card(sport="nba", tier="A")]
    with (
        patch("predict_service.bestbets_compute._get_edge_view",
              return_value={"status": "unavailable"}),
        patch("predict_service.bestbets_compute._cards_from_props",
              return_value=cards),
        patch("predict_service.bestbets_compute._apply_stale_suppression",
              side_effect=lambda c: c),
    ):
        result = compute_best_bets("nba")
    assert not _has_dollar_key(result), "D10: no $ key in compute_best_bets output"
    assert result.get("edge_claimed") is False, "D10: edge_claimed must be False"


# ---------------------------------------------------------------------------
# D11: edge_vs_market is a prob diff, not a $ field
# ---------------------------------------------------------------------------

def test_d11_edge_vs_market_is_prob_diff():
    mp, mkt = 0.62, 0.50
    card = _card(sport="nba", tier="A", model_prob=mp, market_prob=mkt)
    card["edge_vs_market"] = round(mp - mkt, 6)
    tradable, _ = _suppress_degenerate([card])
    ev = tradable[0]["edge_vs_market"]
    assert 0.0 < ev < 1.0, "D11: edge_vs_market must be a prob diff in (0, 1)"
    assert abs(ev - (mp - mkt)) < 1e-6, "D11: edge_vs_market == model_prob - market_prob"


# ---------------------------------------------------------------------------
# D12: _suppress_degenerate never raises on garbage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("inp", [
    [],
    [None, None],
    [{"degenerate_model": True}],
    [{"degenerate_model": "yes", "tier": object()}],
    [42, "string", {}],
])
def test_d12_never_raises(inp):
    try:
        tradable, suppressed = _suppress_degenerate(inp)
        assert isinstance(tradable, list)
        assert isinstance(suppressed, list)
    except Exception as exc:
        pytest.fail("D12: _suppress_degenerate raised on garbage input: %s" % exc)
