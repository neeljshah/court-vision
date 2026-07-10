"""Per-file test for compute_wiring. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/bestbets/test_compute_wiring.py -q
"""
from __future__ import annotations

from scripts.platformkit.bestbets import compute_wiring as cw


def test_confidence_for_falls_back_to_model_prob_when_scorer_unavailable(monkeypatch):
    monkeypatch.setattr(cw, "_CONFIDENCE_SCORER_AVAILABLE", False)
    assert cw.confidence_for({"model_prob": 0.62}) == 0.62
    assert cw.confidence_for({}) == 0.0


def test_confidence_for_scorer_exception_falls_back_not_raises(monkeypatch):
    """Failure mode: a raising confidence scorer must never sink a card --
    it should degrade to the legacy raw model_prob, not blow up bestbets_compute."""
    monkeypatch.setattr(cw, "_CONFIDENCE_SCORER_AVAILABLE", True)
    monkeypatch.setattr(cw, "_score_confidence", lambda card: (_ for _ in ()).throw(RuntimeError("boom")))
    assert cw.confidence_for({"model_prob": 0.55}) == 0.55


def test_select_best_odds_falls_back_when_gate_unavailable(monkeypatch):
    monkeypatch.setattr(cw, "_FRESH_LINE_AVAILABLE", False)
    odds, book = cw.select_best_odds([{"decimal": 2.1, "book": "x"}], 1.91, "legacy_book")
    assert (odds, book) == (1.91, "legacy_book")


def test_select_best_odds_uses_gate_result_when_ok(monkeypatch):
    monkeypatch.setattr(cw, "_FRESH_LINE_AVAILABLE", True)
    monkeypatch.setattr(cw, "_best_fresh_line",
                        lambda books: {"status": "ok", "best_decimal": 2.05, "best_book": "fresh_book"})
    odds, book = cw.select_best_odds([{"decimal": 2.05}], 1.91, "legacy_book")
    assert (odds, book) == (2.05, "fresh_book")


def test_rank_cards_falls_back_to_legacy_sort_on_ranker_failure(monkeypatch):
    """Failure mode: if the CLV ranker raises, cards must still come back
    sorted by the legacy (tier, -confidence) rule rather than an unsorted/
    partially-mutated list silently reaching the served bestbets page."""
    monkeypatch.setattr(cw, "_CLV_RANK_AVAILABLE", True)
    monkeypatch.setattr(cw, "_rank_cards_clv", lambda cards: (_ for _ in ()).throw(RuntimeError("boom")))
    cards = [{"tier": "B", "confidence": 0.9}, {"tier": "A", "confidence": 0.1}]
    out = cw.rank_cards(cards, tier_rank={"A": 0, "B": 1, "C": 2})
    assert [c["tier"] for c in out] == ["A", "B"]
