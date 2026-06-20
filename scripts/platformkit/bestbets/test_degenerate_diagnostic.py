"""test_degenerate_diagnostic.py -- per-file test for degenerate_diagnostic.

Per-file test only (full pytest freezes the box).
Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/bestbets/test_degenerate_diagnostic.py -q

Acceptance criteria (R6-6-mlb-degenerate-emitter):
  A) 11 cards / 2 distinct model_prob -> {degenerate:True, n_distinct:2,
     model_status:'unavailable -- base rate only', edge_claimed:False}
  B) 11 well-spread probs -> {degenerate:False}
  C) < min_cards -> model_status INSUFFICIENT_DATA, edge_claimed False
  D) No $ / roi / pnl field anywhere.
  E) assess_board() groups by sport correctly.
  F) Bad/None input handled gracefully.
"""
from __future__ import annotations

import pytest

from scripts.platformkit.bestbets.degenerate_diagnostic import (
    INSUFFICIENT_DATA_STATUS,
    MAX_DISTINCT_PROBS,
    MIN_CARDS,
    MODEL_STATUS_UNAVAILABLE,
    MODEL_STATUS_OK,
    assess_board,
    assess_sport,
)

_BANNED_KEYS = {"dollar", "usd", "roi", "pnl", "profit", "bankroll", "stake"}


def _assert_no_money_keys(d: dict) -> None:
    for k in d:
        assert k.lower() not in _BANNED_KEYS, f"Banned money key found: {k!r}"


def _make_cards(probs, sport="mlb"):
    return [{"sport": sport, "model_prob": p, "edge_claimed": True} for p in probs]


def _mlb_degenerate(n=11):
    """6 cards at 0.5345 + 5 at 0.4655 -- exactly 2 distinct values."""
    return _make_cards([0.5345] * 6 + [0.4655] * 5, sport="mlb")


def _nba_healthy(n=11):
    """11 unique probs, each well-spread."""
    probs = [round(0.40 + i * 0.02, 4) for i in range(n)]
    assert len(set(probs)) == n
    return _make_cards(probs, sport="nba")


# ---------------------------------------------------------------------------
# A) 11 cards / 2 distinct -> degenerate
# ---------------------------------------------------------------------------

class TestDegenerateBoard:
    def test_degenerate_true(self):
        r = assess_sport(_mlb_degenerate(), sport="mlb")
        assert r["degenerate"] is True, r

    def test_n_distinct_is_2(self):
        r = assess_sport(_mlb_degenerate(), sport="mlb")
        assert r["n_distinct"] == 2

    def test_model_status_unavailable(self):
        r = assess_sport(_mlb_degenerate(), sport="mlb")
        assert r["model_status"] == MODEL_STATUS_UNAVAILABLE, r["model_status"]

    def test_edge_claimed_false(self):
        r = assess_sport(_mlb_degenerate(), sport="mlb")
        assert r["edge_claimed"] is False

    def test_n_cards_matches(self):
        r = assess_sport(_mlb_degenerate(), sport="mlb")
        assert r["n_cards"] == 11

    def test_no_money_keys(self):
        _assert_no_money_keys(assess_sport(_mlb_degenerate(), sport="mlb"))

    def test_ascii_only_model_status(self):
        r = assess_sport(_mlb_degenerate(), sport="mlb")
        assert r["model_status"].isascii()

    def test_ascii_only_reason(self):
        r = assess_sport(_mlb_degenerate(), sport="mlb")
        assert r["reason"].isascii()

    def test_single_distinct_is_degenerate(self):
        """All 11 at same prob -> 1 distinct <= MAX_DISTINCT_PROBS -> degenerate."""
        cards = _make_cards([0.5] * 11, sport="mlb")
        r = assess_sport(cards, sport="mlb")
        assert r["degenerate"] is True
        assert r["n_distinct"] == 1
        assert r["edge_claimed"] is False


# ---------------------------------------------------------------------------
# B) 11 well-spread probs -> NOT degenerate
# ---------------------------------------------------------------------------

class TestHealthyBoard:
    def test_degenerate_false(self):
        r = assess_sport(_nba_healthy(), sport="nba")
        assert r["degenerate"] is False, r

    def test_model_status_ok(self):
        r = assess_sport(_nba_healthy(), sport="nba")
        assert r["model_status"] == MODEL_STATUS_OK

    def test_n_distinct_is_11(self):
        r = assess_sport(_nba_healthy(), sport="nba")
        assert r["n_distinct"] == 11

    def test_no_money_keys(self):
        _assert_no_money_keys(assess_sport(_nba_healthy(), sport="nba"))

    def test_edge_claimed_true(self):
        r = assess_sport(_nba_healthy(), sport="nba")
        assert r["edge_claimed"] is True


# ---------------------------------------------------------------------------
# C) Below min_cards -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestInsufficientData:
    def test_zero_cards(self):
        r = assess_sport([], sport="mlb")
        assert r["model_status"] == INSUFFICIENT_DATA_STATUS
        assert r["edge_claimed"] is False
        assert r["degenerate"] is False

    def test_one_card(self):
        r = assess_sport(_make_cards([0.5345], sport="mlb"), sport="mlb")
        assert r["model_status"] == INSUFFICIENT_DATA_STATUS
        assert r["edge_claimed"] is False

    def test_min_cards_minus_one(self):
        cards = _make_cards([0.5345] * (MIN_CARDS - 1), sport="mlb")
        r = assess_sport(cards, sport="mlb")
        assert r["model_status"] == INSUFFICIENT_DATA_STATUS
        assert r["edge_claimed"] is False

    def test_no_money_keys(self):
        _assert_no_money_keys(assess_sport(_make_cards([0.5] * 2, sport="mlb"), sport="mlb"))


# ---------------------------------------------------------------------------
# D) No $ field -- parametrized across all code paths
# ---------------------------------------------------------------------------

class TestNoMoneyFields:
    @pytest.mark.parametrize("n_probs,sport", [
        (11, "mlb"), (11, "nba"), (2, "mlb"),
    ])
    def test_no_money_key(self, n_probs, sport):
        if sport == "mlb" and n_probs == 11:
            probs = [0.5345] * 6 + [0.4655] * 5
        elif sport == "nba" and n_probs == 11:
            probs = [round(0.40 + i * 0.02, 4) for i in range(11)]
        else:
            probs = [0.5] * n_probs
        _assert_no_money_keys(assess_sport(_make_cards(probs, sport=sport), sport=sport))


# ---------------------------------------------------------------------------
# E) assess_board() groups by sport
# ---------------------------------------------------------------------------

class TestAssessBoard:
    def test_two_sports_independent(self):
        mlb_cards = _mlb_degenerate()
        nba_cards = _nba_healthy()
        result = assess_board(mlb_cards + nba_cards)
        assert result["mlb"]["degenerate"] is True
        assert result["nba"]["degenerate"] is False

    def test_empty_board(self):
        assert assess_board([]) == {}

    def test_single_sport(self):
        result = assess_board(_mlb_degenerate())
        assert list(result.keys()) == ["mlb"]

    def test_board_no_money_keys(self):
        for payload in assess_board(_mlb_degenerate()).values():
            _assert_no_money_keys(payload)


# ---------------------------------------------------------------------------
# F) Graceful degradation + boundary conditions
# ---------------------------------------------------------------------------

class TestGracefulAndBoundary:
    def test_non_dict_cards_skipped(self):
        cards = [None, "bad", 42, {"sport": "mlb", "model_prob": 0.5345}]
        r = assess_sport(cards, sport="mlb")
        assert r["n_cards"] == 1
        assert r["model_status"] == INSUFFICIENT_DATA_STATUS

    def test_missing_model_prob_skipped(self):
        cards = [{"sport": "mlb"}] * 10 + [{"sport": "mlb", "model_prob": 0.5345}]
        r = assess_sport(cards, sport="mlb")
        assert r["n_cards"] == 1
        assert r["model_status"] == INSUFFICIENT_DATA_STATUS

    def test_nan_model_prob_skipped(self):
        cards = _make_cards([float("nan")] * 11, sport="mlb")
        r = assess_sport(cards, sport="mlb")
        assert r["n_cards"] == 0
        assert r["model_status"] == INSUFFICIENT_DATA_STATUS

    def test_exactly_max_distinct_is_degenerate(self):
        """Exactly MAX_DISTINCT_PROBS distinct values -> degenerate."""
        probs = [0.5345] * 6 + [0.4655] * 5
        r = assess_sport(_make_cards(probs, sport="mlb"), sport="mlb")
        assert r["degenerate"] is True
        assert r["n_distinct"] == MAX_DISTINCT_PROBS

    def test_11_unique_probs_not_degenerate(self):
        """11 unique probs well-separated -> not degenerate."""
        probs = [round(0.40 + i * 0.04, 4) for i in range(11)]
        r = assess_sport(_make_cards(probs, sport="mlb"), sport="mlb")
        assert r["degenerate"] is False
        assert r["n_distinct"] == 11

    def test_exactly_min_cards_at_boundary(self):
        """Exactly MIN_CARDS cards with 2 distinct probs -> degenerate."""
        half = MIN_CARDS // 2
        probs = [0.5345] * half + [0.4655] * (MIN_CARDS - half)
        assert len(probs) == MIN_CARDS
        r = assess_sport(_make_cards(probs, sport="mlb"), sport="mlb")
        assert r["degenerate"] is True
