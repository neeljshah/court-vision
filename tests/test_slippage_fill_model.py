"""
test_slippage_fill_model.py -- Tests for the slippage/repricing fill model (18.5-02).

Acceptance criterion: fill simulation applies a per-book slippage model
(configurable bps) and a repricing penalty for bet sizes > book limit;
the fill model is documented in backtest_results.json's fill_model field.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.backtest_system import (  # noqa: E402
    make_slippage_fill_model,
    replay_bet_ledger,
    run_full_backtest,
)


def test_per_book_slippage_worsens_over_line():
    """An over bet fills at a higher (worse) line by the book's slippage bps."""
    fill_model = make_slippage_fill_model(
        book_slippage_bps={"draftkings": 40.0}, book_limits={},
    )
    fill = fill_model({"book": "draftkings", "book_line": 25.0,
                       "stake": 100.0, "direction": "over"})
    # 40 bps of 25.0 = 0.10 pts; over bet -> line moves UP.
    assert fill["fill_line"] == 25.1
    assert fill["slippage_bps"] == 40.0


def test_per_book_slippage_worsens_under_line():
    """An under bet fills at a lower (worse) line."""
    fill_model = make_slippage_fill_model(
        book_slippage_bps={"fanduel": 40.0}, book_limits={},
    )
    fill = fill_model({"book": "fanduel", "book_line": 25.0,
                       "stake": 100.0, "direction": "under"})
    assert fill["fill_line"] == 24.9


def test_sharp_book_slips_less_than_retail():
    """Pinnacle slippage is configured lower than retail books."""
    fm = make_slippage_fill_model()
    pin = fm({"book": "pinnacle", "book_line": 25.0, "stake": 100.0, "direction": "over"})
    dk = fm({"book": "draftkings", "book_line": 25.0, "stake": 100.0, "direction": "over"})
    assert pin["slippage"] < dk["slippage"]


def test_repricing_penalty_applies_over_book_limit():
    """A stake above the book limit incurs an extra repricing penalty."""
    fm = make_slippage_fill_model(
        book_slippage_bps={"betmgm": 30.0},
        book_limits={"betmgm": 200.0},
        repricing_penalty_bps=50.0,
    )
    within = fm({"book": "betmgm", "book_line": 25.0, "stake": 150.0, "direction": "over"})
    over   = fm({"book": "betmgm", "book_line": 25.0, "stake": 400.0, "direction": "over"})
    assert within["reprice_bps"] == 0.0
    # 400 vs 200 limit -> overage 1.0 -> +50 bps repricing.
    assert over["reprice_bps"] == 50.0
    assert over["slippage_bps"] > within["slippage_bps"]


def test_repricing_penalty_caps_at_3x_overage():
    """The repricing penalty is capped at 3x the overage fraction."""
    fm = make_slippage_fill_model(
        book_slippage_bps={"betmgm": 0.0},
        book_limits={"betmgm": 100.0},
        repricing_penalty_bps=50.0,
    )
    huge = fm({"book": "betmgm", "book_line": 25.0, "stake": 10_000.0, "direction": "over"})
    assert huge["reprice_bps"] == 150.0   # 50 bps * cap(3.0)


def test_slippage_reduces_roi_vs_identity_fill():
    """Realistic fills produce a lower ROI than point-estimate fills."""
    bets = [
        {"game_date": "2026-05-01", "won": True, "stake": 100.0, "odds": -110,
         "direction": "over", "book_line": 25.0, "book": "draftkings",
         "actual": 25.05},   # marginal win — slippage can flip it
        {"game_date": "2026-05-02", "won": True, "stake": 100.0, "odds": -110,
         "direction": "over", "book_line": 20.0, "book": "draftkings",
         "actual": 26.0},
    ]
    identity = replay_bet_ledger(bets)
    slipped = replay_bet_ledger(bets, fill_model=make_slippage_fill_model())
    assert slipped["total_pnl"] <= identity["total_pnl"]


def test_fill_model_documented_in_results(tmp_path):
    """run_full_backtest records the slippage config in the fill_model field."""
    ledger = tmp_path / "bet_log.json"
    out = tmp_path / "backtest_results.json"
    ledger.write_text(json.dumps([
        {"game_date": "2026-05-01", "won": True, "stake": 100.0, "odds": -110,
         "direction": "over", "book_line": 25.0, "book": "draftkings", "actual": 27.0},
    ]), encoding="utf-8")

    desc = {"type": "slippage_repricing", "default_slippage_bps": 25.0}
    result = run_full_backtest(
        str(ledger), str(out),
        fill_model=make_slippage_fill_model(),
        fill_model_name=desc,
    )
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["fill_model"] == desc
    assert saved["fill_model"]["type"] == "slippage_repricing"
    assert result["bet_count"] == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
