"""Per-file test: frontend.exec_decision -- model-only (line-only) decisions.

A comparison row that has a FRESH book line (line and/or best_odds) but NO model
probability (the model does not price this market -- e.g. total / run-line) must
become an honest MODEL-ONLY row, NOT a bet and NOT a silent drop:

  * decision == 'model_only'
  * tier is None, stake_units/flat_unit/kelly_units all 0.0
  * NO fabricated model_prob (stays None), NO fabricated edge/EV
  * the real line + best_book + best_odds + market_prob are preserved
  * decide_game surfaces these in a NEW info_bets[] list, separate from best_bets[]
  * a normal priced row still becomes a bet (regression guard)
  * NO dollar / $ key anywhere

Run: cd /c/Users/neelj/nba-ai-system && \
  python -m pytest frontend/test_exec_decision_model_only.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from frontend.exec_decision import decide_game, decide_row  # noqa: E402

_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "bankroll")


def _no_money(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            for bad in _FORBIDDEN:
                assert bad not in str(k).lower(), "forbidden key %r" % k
            _no_money(v)
    elif isinstance(obj, list):
        for i in obj:
            _no_money(i)


def _total_row() -> dict:
    return {
        "market_type": "total", "side": "over",
        "model_prob": None, "market_prob": 0.50,
        "best_book": "Pinnacle", "best_odds": 1.91, "line": 8.5,
        "clv_is_proxy": True,
    }


def _spread_row() -> dict:
    return {
        "market_type": "spread", "side": "home",
        "model_prob": None, "market_prob": 0.49,
        "best_book": "Pinnacle", "best_odds": 1.95, "line": -1.5,
        "clv_is_proxy": True,
    }


def _ml_row() -> dict:
    return {
        "market_type": "moneyline", "side": "home",
        "model_prob": 0.60, "market_prob": 0.52,
        "best_book": "Pinnacle", "best_odds": 1.95, "line": None,
        "clv_is_proxy": True, "ev": None, "tier": None,
    }


class TestDecideRowModelOnly:
    def test_total_line_only_is_model_only(self):
        out = decide_row(_total_row())
        assert out["decision"] == "model_only"
        assert out["tier"] is None
        assert out["model_prob"] is None, "must NOT fabricate a model prob"
        assert out["stake_units"] == 0.0
        assert out["flat_unit"] == 0.0
        assert out["line"] == 8.5
        assert out["best_book"] == "Pinnacle"
        assert out["best_odds"] == 1.91
        assert out["market_prob"] == 0.50

    def test_spread_line_only_is_model_only(self):
        out = decide_row(_spread_row())
        assert out["decision"] == "model_only"
        assert out["line"] == -1.5
        assert out["model_prob"] is None

    def test_no_line_no_odds_no_model_stays_no_bet(self):
        """A row with neither a line/odds nor a model prob is a plain no_bet."""
        row = {"market_type": "total", "side": "over", "model_prob": None,
               "market_prob": None, "best_book": "", "best_odds": None,
               "line": None}
        out = decide_row(row)
        assert out["decision"] == "no_bet"

    def test_priced_row_still_bets(self):
        out = decide_row(_ml_row())
        assert out["decision"] == "bet"
        assert out["tier"] in ("A", "B", "C")
        assert out["model_prob"] == 0.60


class TestDecideGameSplits:
    def test_info_bets_and_best_bets_separated(self):
        game = {
            "status": "ok", "game_id": "G1", "home": "H", "away": "A",
            "tipoff": "2026-06-20T23:00:00Z",
            "comparison": [_ml_row(), _total_row(), _spread_row()],
        }
        dec = decide_game(game)
        assert len(dec["best_bets"]) == 1
        assert dec["best_bets"][0]["market_type"] == "moneyline"
        info_markets = sorted(b["market_type"] for b in dec["info_bets"])
        assert info_markets == ["spread", "total"]
        for b in dec["info_bets"]:
            assert b["decision"] == "model_only"
            assert b["line"] is not None

    def test_unavailable_game_has_empty_info_bets(self):
        dec = decide_game({"status": "unavailable", "game_id": "x"})
        assert dec["best_bets"] == []
        assert dec["info_bets"] == []

    def test_no_money_keys(self):
        game = {
            "status": "ok", "game_id": "G1", "home": "H", "away": "A",
            "tipoff": "2026-06-20T23:00:00Z",
            "comparison": [_ml_row(), _total_row(), _spread_row()],
        }
        _no_money(decide_game(game))
