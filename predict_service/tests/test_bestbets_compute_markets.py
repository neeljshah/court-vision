"""predict_service.tests.test_bestbets_compute_markets -- per-market cards.

The board must show EACH bettable market as its OWN card, not collapse a game to
one moneyline card. A game with moneyline (model-priced) + total + spread (fresh
book line, model-only) must yield THREE distinct cards:

  M1. exactly 3 cards for the game, one per market_type (moneyline/total/spread).
  M2. each card carries the correct market_type, side, line, and best_book.
  M3. the moneyline card is a real bet (tier in A/B/C, decision='bet').
  M4. the total + spread cards are honest MODEL-ONLY: model_prob None, tier None,
      units 0.0, edge_vs_market 0.0, decision='model_only', a real market_prob +
      line + best_book preserved (nothing fabricated).
  M5. a market with NO fresh line and no model prob is OMITTED (never fabricated).
  M6. stale-never-green still holds: a past-tipoff game emits 0 cards.
  M7. no $ key anywhere; edge_claimed False.

Run (per-file only)::
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest predict_service/tests/test_bestbets_compute_markets.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import predict_service.bestbets_compute as bc  # noqa: E402
from predict_service.bestbets_compute import compute_best_bets  # noqa: E402


def _future(hours: float = 6.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _past(hours: float = 6.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _game(tipoff: str) -> Dict[str, Any]:
    """An edge-view game with ML (priced) + total + spread (fresh-line-only)."""
    return {
        "status": "ok", "game_id": "G1", "home": "Home", "away": "Away",
        "tipoff": tipoff,
        "comparison": [
            {"market_type": "moneyline", "side": "home", "model_prob": 0.60,
             "market_prob": 0.52, "best_book": "Pinnacle", "best_odds": 1.95,
             "line": None, "clv_is_proxy": True},
            {"market_type": "total", "side": "over", "model_prob": None,
             "market_prob": 0.50, "best_book": "Pinnacle", "best_odds": 1.91,
             "line": 8.5, "clv_is_proxy": True},
            {"market_type": "spread", "side": "home", "model_prob": None,
             "market_prob": 0.49, "best_book": "Pinnacle", "best_odds": 1.95,
             "line": -1.5, "clv_is_proxy": True},
            # No model prob AND no line/odds -> omitted (M5).
            {"market_type": "total", "side": "under", "model_prob": None,
             "market_prob": None, "best_book": "", "best_odds": None,
             "line": None, "clv_is_proxy": True},
        ],
    }


def _run(tipoff: str) -> List[Dict[str, Any]]:
    view = {"status": "ok", "games": [_game(tipoff)]}
    with patch.object(bc, "_get_edge_view", return_value=view):
        return compute_best_bets("nba", include_props=False)["cards"]


def _has_dollar(obj: Any) -> bool:
    if isinstance(obj, dict):
        return any("$" in str(k) or _has_dollar(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_has_dollar(i) for i in obj)
    return False


def test_m1_three_distinct_cards():
    cards = _run(_future())
    assert len(cards) == 3, "ML + total + spread = 3 cards, got %d" % len(cards)
    assert sorted(c["market_type"] for c in cards) == ["moneyline", "spread", "total"]


def test_m2_market_line_and_best_book():
    by = {c["market_type"]: c for c in _run(_future())}
    assert by["total"]["line"] == 8.5
    assert by["total"]["best_book"] == "Pinnacle"
    assert by["spread"]["line"] == -1.5
    assert by["spread"]["best_book"] == "Pinnacle"
    assert by["moneyline"]["side"] == "home"


def test_m3_moneyline_is_a_bet():
    by = {c["market_type"]: c for c in _run(_future())}
    ml = by["moneyline"]
    assert ml["decision"] == "bet"
    assert ml["tier"] in ("A", "B", "C")
    assert ml["model_prob"] == 0.60


def test_m4_total_spread_model_only_honest():
    by = {c["market_type"]: c for c in _run(_future())}
    for mt in ("total", "spread"):
        c = by[mt]
        assert c["decision"] == "model_only", mt
        assert c["model_prob"] is None, "%s must not fabricate a model prob" % mt
        assert c["tier"] is None, mt
        assert c["units"] == 0.0, mt
        assert c["edge_vs_market"] == 0.0, mt
        assert c["market_prob"] is not None, "%s keeps the real devig prob" % mt
        assert c["line"] is not None, mt


def test_m5_unpriced_no_line_market_omitted():
    cards = _run(_future())
    # total/under has neither model prob nor a line -> never appears.
    unders = [c for c in cards
              if c["market_type"] == "total" and c["side"] == "under"]
    assert unders == [], "a market with no fresh line + no model prob is omitted"


def test_m6_stale_never_green_past_tipoff():
    cards = _run(_past())
    assert cards == [], "past-tipoff game must emit no cards (stale-never-green)"


def test_m7_no_dollar_field():
    view = {"status": "ok", "games": [_game(_future())]}
    with patch.object(bc, "_get_edge_view", return_value=view):
        result = compute_best_bets("nba", include_props=False)
    assert not _has_dollar(result), "no $ key anywhere"
    assert result["edge_claimed"] is False
