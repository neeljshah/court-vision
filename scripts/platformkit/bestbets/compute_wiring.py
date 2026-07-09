"""scripts.platformkit.bestbets.compute_wiring -- BB-Q5 hooks for bestbets_compute.

Bridges 3 built-but-never-wired bestbets modules into predict_service.bestbets_compute
without growing that file past its LOC cap:
  - confidence_score.score_card   -> composite sharpness confidence (BBQ5-2)
  - fresh_best_line.best_fresh_line -> stale-never-wins price gate (BBQ5-3)
  - clv_rank.rank_cards_clv        -> CLV-aware ranking tiebreak (BB-Q5-1)

Each hook is import-guarded: if the underlying module is unavailable, or it raises,
behavior degrades to the ORIGINAL bestbets_compute logic (raw model_prob confidence,
legacy best_odds/best_book fields, tier+confidence sort) -- byte-identical to before
this wire for any caller that never sees the new modules. Additive/superset-safe:
no existing card field changes type or is removed.

ASCII; <=300 LOC; ships no $/roi/pnl field.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    from scripts.platformkit.bestbets.confidence_score import score_card as _score_confidence
    _CONFIDENCE_SCORER_AVAILABLE = True
except Exception:  # noqa: BLE001 -- absent module -> raw-prob fallback, unchanged behavior
    _CONFIDENCE_SCORER_AVAILABLE = False

try:
    from scripts.platformkit.bestbets.fresh_best_line import best_fresh_line as _best_fresh_line
    _FRESH_LINE_AVAILABLE = True
except Exception:  # noqa: BLE001 -- absent module -> legacy selection, unchanged behavior
    _FRESH_LINE_AVAILABLE = False

try:
    from scripts.platformkit.bestbets.clv_rank import rank_cards_clv as _rank_cards_clv
    _CLV_RANK_AVAILABLE = True
except Exception:  # noqa: BLE001 -- absent module -> legacy sort, unchanged behavior
    _CLV_RANK_AVAILABLE = False


def confidence_for(card: Dict[str, Any]) -> float:
    """Composite sharpness score in [0,1] (BBQ5-2); falls back to raw model_prob
    if the scorer module is unavailable or errors (never raises)."""
    if _CONFIDENCE_SCORER_AVAILABLE:
        try:
            score, _label = _score_confidence(card)
            return round(float(score), 6)
        except Exception:  # noqa: BLE001 -- never sink a card on a scoring failure
            pass
    return round(float(card.get("model_prob") or 0.0), 6)


def select_best_odds(all_books: List[Any], fallback_odds: Any, fallback_book: str
                     ) -> Tuple[Any, str]:
    """(best_odds, best_book) from FRESH bettable books only (BBQ5-3); a stale
    higher price never wins. Falls back to the legacy cand/bet fields (unchanged
    behavior) when the gate is unavailable, errors, or finds no fresh book."""
    if _FRESH_LINE_AVAILABLE and all_books:
        try:
            result = _best_fresh_line(all_books)
            if result.get("status") == "ok":
                return result.get("best_decimal"), str(result.get("best_book") or "")
        except Exception:  # noqa: BLE001 -- gate failure -> legacy fallback
            pass
    return fallback_odds, fallback_book


def rank_cards(cards: List[Dict[str, Any]], *, tier_rank: Dict[str, int]
              ) -> List[Dict[str, Any]]:
    """Sort *cards* by the CLV-aware ranker (BB-Q5-1) when available, else the
    original (tier, -confidence) sort. Never raises."""
    if _CLV_RANK_AVAILABLE:
        try:
            return _rank_cards_clv(cards)
        except Exception:  # noqa: BLE001 -- ranker failure -> legacy sort, unchanged
            pass
    cards.sort(key=lambda c: (tier_rank.get(str(c.get("tier", "C")), 99),
                              -float(c.get("confidence") or 0.0)))
    return cards


__all__ = ["confidence_for", "select_best_odds", "rank_cards"]
