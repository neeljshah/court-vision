"""Per-file tests: MLB moneyline uniformity wire in bestbets_compute (REVIEW iter2 P0).

Acceptance criteria:
  U1. _mark_mlb_uniformity wrapper exists and is importable from bestbets_compute.
  U2. 16-card MLB moneyline board with 2 distinct model_prob values ->
        every card gets degenerate_model=True after _mark_mlb_uniformity.
  U3. After the full compute_best_bets pipeline those same cards are NOT on the
        ranked board (decision=no_bet, tier=None, in suppressed_degenerate).
  U4. Non-degenerate (varied probs) MLB cards are left untouched by the wrapper.
  U5. Non-MLB cards (NBA, soccer) are never touched by _mark_mlb_uniformity.
  U6. _mark_mlb_uniformity never raises -- returns cards unchanged on any error.
  U7. No $ / pnl / roi / profit field introduced by the uniformity wire.
  U8. degenerate_guard MIN_CARDS=4 floor alone would NOT catch a 16-card board
        that already has > 4 cards (verify wrapper provides ADDITIONAL coverage
        by patching degenerate_guard to a no-op so only _mark_mlb_uniformity acts).

Run (per-file only -- never run the full suite):
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/bestbets/test_bestbets_mlb_uniformity_wire.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.bestbets_compute import (  # noqa: E402
    _mark_mlb_uniformity,
    compute_best_bets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mlb_ml_card(
    gid: str,
    prob: float,
    market_type: str = "moneyline",
    tier: str = "A",
) -> Dict[str, Any]:
    """Minimal MLB moneyline card dict."""
    mkt = prob - 0.03
    return {
        "game_id": gid,
        "matchup": f"TeamA vs TeamB ({gid})",
        "sport": "mlb",
        "market_type": market_type,
        "side": "home",
        "model_prob": prob,
        "market_prob": mkt,
        "best_book": "draftkings",
        "best_odds": -110,
        "all_books": [],
        "edge_vs_market": round(prob - mkt, 6),
        "units": 1.0,
        "tier": tier,
        "ev": 0.04,
        "stake_units": 1.0,
        "confidence": prob,
        "clv": {"clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
        "clv_is_proxy": True,
        "status": "pregame",
        "honest_note": "original note",
        "tipoff_utc": None,
    }


def _nba_card(gid: str, prob: float, tier: str = "A") -> Dict[str, Any]:
    """Minimal NBA card dict."""
    c = _mlb_ml_card(gid, prob, tier=tier)
    c["sport"] = "nba"
    return c


def _make_flat_mlb_board(n: int = 16) -> List[Dict[str, Any]]:
    """n MLB moneyline cards collapsing to exactly 2 distinct probs (0.5345 / 0.4655)."""
    cards = []
    for i in range(n):
        prob = 0.5345 if i % 2 == 0 else 0.4655
        cards.append(_mlb_ml_card(f"mlb_{i}", prob))
    return cards


def _make_varied_mlb_board(n: int = 10) -> List[Dict[str, Any]]:
    """n MLB moneyline cards with diverse probs (healthy board)."""
    return [_mlb_ml_card(f"mlb_v{i}", round(0.45 + i * 0.012, 6)) for i in range(n)]


_FORBIDDEN_KEYS = frozenset({
    "dollar", "pnl", "roi", "profit", "bankroll", "usd",
})


def _has_forbidden(obj: object) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in _FORBIDDEN_KEYS:
                return True
            if _has_forbidden(v):
                return True
    elif isinstance(obj, list):
        return any(_has_forbidden(i) for i in obj)
    return False


# ---------------------------------------------------------------------------
# U1: importability
# ---------------------------------------------------------------------------

class TestImportability:

    def test_u1_wrapper_importable(self):
        """_mark_mlb_uniformity must be importable from bestbets_compute."""
        assert callable(_mark_mlb_uniformity), "U1: _mark_mlb_uniformity must be callable"


# ---------------------------------------------------------------------------
# U2: 16-card MLB board with 2 distinct probs -> degenerate_model=True on all
# ---------------------------------------------------------------------------

class TestFlatPriorDemotion:

    def test_u2_16_card_two_prob_board_all_flagged(self):
        """16 MLB cards, 2 distinct probs -> all get degenerate_model=True."""
        cards = _make_flat_mlb_board(16)
        result = _mark_mlb_uniformity(cards)
        assert result is cards, "U2: must return same list object"
        flagged = [c for c in result if c.get("degenerate_model") is True]
        assert len(flagged) == 16, (
            "U2: all 16 cards must be flagged; got %d flagged" % len(flagged)
        )

    def test_u2_exact_qa_symptom_11_cards_two_probs(self):
        """QA iter1/8 exact symptom: 11 cards at 0.5345 / 0.4655 -> all flagged."""
        cards = _make_flat_mlb_board(11)
        result = _mark_mlb_uniformity(cards)
        assert all(c.get("degenerate_model") is True for c in result), (
            "U2: all 11 QA-symptom cards must be degenerate"
        )


# ---------------------------------------------------------------------------
# U3: full pipeline -> suppressed, not on board
# ---------------------------------------------------------------------------

class TestFullPipelineSuppression:

    def _run_compute(self, injected_cards: List[Dict[str, Any]]):
        """Run compute_best_bets with IO patched out; inject cards via _cards_from_props."""
        with (
            patch("predict_service.bestbets_compute._get_edge_view",
                  return_value={"status": "unavailable"}),
            patch("predict_service.bestbets_compute._cards_from_props",
                  return_value=injected_cards),
            patch("predict_service.bestbets_compute._apply_stale_suppression",
                  side_effect=lambda c: c),
        ):
            return compute_best_bets("mlb", include_props=True)

    def test_u3_16_card_flat_board_not_on_ranked_board(self):
        """16-card flat MLB board -> zero cards on ranked board."""
        result = self._run_compute(_make_flat_mlb_board(16))
        mlb_on_board = [c for c in result["cards"] if c.get("sport") == "mlb"]
        assert len(mlb_on_board) == 0, (
            "U3: flat MLB cards must not appear on ranked board; got %d" % len(mlb_on_board)
        )

    def test_u3_16_card_flat_board_in_suppressed(self):
        """16-card flat MLB board -> all 16 in suppressed_degenerate."""
        result = self._run_compute(_make_flat_mlb_board(16))
        suppressed = result["suppressed_degenerate"]
        assert len(suppressed) == 16, (
            "U3: all 16 cards must be in suppressed_degenerate; got %d" % len(suppressed)
        )

    def test_u3_suppressed_cards_have_no_bet_and_null_tier(self):
        """Each suppressed MLB card must have decision=no_bet and tier=None."""
        result = self._run_compute(_make_flat_mlb_board(16))
        for c in result["suppressed_degenerate"]:
            assert c.get("decision") == "no_bet", (
                "U3: suppressed card decision must be no_bet; got %r" % c.get("decision")
            )
            assert c.get("tier") is None, (
                "U3: suppressed card tier must be None; got %r" % c.get("tier")
            )


# ---------------------------------------------------------------------------
# U4: varied MLB board untouched
# ---------------------------------------------------------------------------

class TestVariedBoardUntouched:

    def test_u4_varied_mlb_not_flagged(self):
        """MLB board with diverse probs -> no card flagged by _mark_mlb_uniformity."""
        cards = _make_varied_mlb_board(10)
        result = _mark_mlb_uniformity(cards)
        flagged = [c for c in result if c.get("degenerate_model")]
        assert flagged == [], (
            "U4: varied MLB board must not be flagged; got %d flagged" % len(flagged)
        )

    def test_u4_varied_tiers_preserved(self):
        """Varied MLB board tiers are not touched."""
        cards = _make_varied_mlb_board(10)
        tiers_before = [c["tier"] for c in cards]
        _mark_mlb_uniformity(cards)
        tiers_after = [c["tier"] for c in cards]
        assert tiers_before == tiers_after, "U4: tiers must not change on healthy board"


# ---------------------------------------------------------------------------
# U5: non-MLB cards never touched
# ---------------------------------------------------------------------------

class TestNonMlbUntouched:

    def test_u5_nba_cards_not_flagged(self):
        """NBA cards on a mixed board are never touched by _mark_mlb_uniformity."""
        nba_cards = [_nba_card(f"nba_{i}", 0.60 + i * 0.01) for i in range(5)]
        flat_mlb = _make_flat_mlb_board(8)
        combined = flat_mlb + nba_cards
        _mark_mlb_uniformity(combined)
        for c in combined:
            if c["sport"] == "nba":
                assert not c.get("degenerate_model"), (
                    "U5: NBA card must not be flagged; card=%r" % c
                )

    def test_u5_nba_tiers_preserved(self):
        """NBA card tiers are unchanged after _mark_mlb_uniformity."""
        nba_cards = [_nba_card(f"nba_{i}", 0.58 + i * 0.01, tier="B") for i in range(4)]
        _mark_mlb_uniformity(nba_cards)
        assert all(c["tier"] == "B" for c in nba_cards), "U5: NBA tiers must be preserved"

    def test_u5_empty_board_returns_empty(self):
        """Empty card list returns empty list without error."""
        result = _mark_mlb_uniformity([])
        assert result == [], "U5: empty input -> empty output"


# ---------------------------------------------------------------------------
# U6: never raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("inp", [
    [],
    [None, None],
    [42, "not_a_card"],
    [{"sport": "mlb"}],            # missing model_prob
    [{"model_prob": "bad_type"}],  # bad model_prob type
])
def test_u6_never_raises(inp):
    """_mark_mlb_uniformity must never raise on garbage input."""
    try:
        result = _mark_mlb_uniformity(inp)
        # Must return something list-like (or same object)
        assert result is not None
    except Exception as exc:
        pytest.fail("U6: _mark_mlb_uniformity raised on input %r: %s" % (inp, exc))


# ---------------------------------------------------------------------------
# U7: no $ / pnl / roi fields introduced
# ---------------------------------------------------------------------------

def test_u7_no_forbidden_fields():
    """No $ / pnl / roi / profit field introduced by the uniformity wire."""
    cards = _make_flat_mlb_board(16)
    _mark_mlb_uniformity(cards)
    assert not _has_forbidden(cards), "U7: forbidden $ field found after _mark_mlb_uniformity"


# ---------------------------------------------------------------------------
# U8: degenerate_guard alone (MIN_CARDS=4) does NOT cover; wrapper adds coverage
# ---------------------------------------------------------------------------

class TestWrapperAdditionalCoverage:

    def test_u8_wrapper_acts_even_when_degen_guard_is_no_op(self):
        """With _mark_degenerate_sports patched to a no-op, _mark_mlb_uniformity
        still flags a 16-card MLB board with 2 distinct probs."""
        cards = _make_flat_mlb_board(16)
        # Confirm no flags before wrapper
        assert not any(c.get("degenerate_model") for c in cards)
        # Run wrapper standalone (degenerate_guard not involved)
        result = _mark_mlb_uniformity(cards)
        flagged = [c for c in result if c.get("degenerate_model") is True]
        assert len(flagged) == 16, (
            "U8: wrapper must flag 16 cards independently of degenerate_guard; "
            "got %d flagged" % len(flagged)
        )

    def test_u8_full_pipeline_with_degen_guard_no_op(self):
        """Full compute_best_bets with degenerate_guard bypassed: mlb uniformity
        wrapper still demotes the 16-card flat board to suppressed_degenerate."""
        flat_cards = _make_flat_mlb_board(16)
        with (
            patch("predict_service.bestbets_compute._get_edge_view",
                  return_value={"status": "unavailable"}),
            patch("predict_service.bestbets_compute._cards_from_props",
                  return_value=flat_cards),
            patch("predict_service.bestbets_compute._apply_stale_suppression",
                  side_effect=lambda c: c),
            # Patch degenerate_guard to a no-op so only mlb_uniformity acts
            patch("predict_service.bestbets_compute._mark_degenerate_sports",
                  side_effect=lambda c: c),
        ):
            result = compute_best_bets("mlb", include_props=True)

        suppressed = result["suppressed_degenerate"]
        board = result["cards"]
        mlb_on_board = [c for c in board if c.get("sport") == "mlb"]
        assert len(mlb_on_board) == 0, (
            "U8: no MLB flat-prior cards on board even with degen_guard no-op; "
            "got %d" % len(mlb_on_board)
        )
        assert len(suppressed) == 16, (
            "U8: all 16 cards suppressed via mlb_uniformity wrapper alone; "
            "got %d" % len(suppressed)
        )
