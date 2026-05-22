"""
test_backtest_system.py -- Tests for the full-system replay engine (18.5-01).

Acceptance criterion: backtest_system replays the historical bet ledger
end-to-end and outputs total ROI, CLV beat rate, max drawdown, Sharpe and
bet count to data/output/backtest_results.json.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.backtest_system import (  # noqa: E402
    REPLAY_STAGES,
    replay_bet_ledger,
    run_full_backtest,
)

_REQUIRED_METRICS = {
    "total_roi", "clv_beat_rate", "max_drawdown", "sharpe", "bet_count",
}


def _bet(date, won, stake=100.0, odds=-110, **extra) -> dict:
    b = {"game_date": date, "won": won, "stake": stake, "odds": odds,
         "direction": "over", "book_line": 25.0, "status": "won" if won else "lost"}
    b.update(extra)
    return b


def test_replay_outputs_all_required_metrics(tmp_path):
    """The results JSON carries every metric named in the acceptance criterion."""
    ledger = tmp_path / "bet_log.json"
    out = tmp_path / "backtest_results.json"
    ledger.write_text(json.dumps([
        _bet("2026-05-01", True), _bet("2026-05-02", False),
        _bet("2026-05-03", True), _bet("2026-05-04", True),
    ]), encoding="utf-8")

    result = run_full_backtest(str(ledger), str(out))
    assert out.exists()
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert _REQUIRED_METRICS.issubset(set(saved.keys()))
    assert saved["bet_count"] == 4
    assert saved["stages"] == REPLAY_STAGES


def test_roi_computed_correctly():
    """3 wins + 1 loss at even-money -> net +2 stakes over 4 staked."""
    bets = [_bet("2026-05-01", True), _bet("2026-05-02", True),
            _bet("2026-05-03", True), _bet("2026-05-04", False)]
    m = replay_bet_ledger(bets, starting_bankroll=1000.0)
    # +100 +100 +100 -100 = +200 pnl on 400 staked -> ROI 0.5
    assert m["total_pnl"] == 200.0
    assert m["total_roi"] == 0.5
    assert m["ending_bankroll"] == 1200.0


def test_max_drawdown_tracked():
    """A losing streak after a peak registers a drawdown."""
    bets = [_bet("2026-05-01", True), _bet("2026-05-02", False),
            _bet("2026-05-03", False)]
    m = replay_bet_ledger(bets, starting_bankroll=1000.0)
    # equity: 1000 -> 1100 -> 1000 -> 900; peak 1100, trough 900 -> dd ~0.1818
    assert m["max_drawdown"] > 0.18
    assert m["max_drawdown"] < 0.19


def test_clv_beat_rate_from_closing_lines():
    """CLV beat rate counts bets whose closing line moved in our favour."""
    bets = [
        _bet("2026-05-01", True, closing_line=26.5),   # over, line up -> beat
        _bet("2026-05-02", False, closing_line=24.0),  # over, line down -> miss
        _bet("2026-05-03", True, closing_line=27.0),   # over, line up -> beat
    ]
    m = replay_bet_ledger(bets)
    assert m["clv_sample"] == 3
    assert m["clv_beat_rate"] == round(2 / 3, 4)


def test_empty_ledger_does_not_crash(tmp_path):
    """An empty/absent ledger yields a zero-bet result, not an exception."""
    out = tmp_path / "backtest_results.json"
    result = run_full_backtest(str(tmp_path / "missing.json"), str(out))
    assert result["bet_count"] == 0
    assert result["total_roi"] is None
    assert out.exists()


def test_chronological_replay_order():
    """Bets are replayed in date order regardless of ledger ordering."""
    bets = [_bet("2026-05-09", False), _bet("2026-05-01", True),
            _bet("2026-05-05", True)]
    m = replay_bet_ledger(bets, starting_bankroll=1000.0)
    # Sorted: win, win, loss -> peak 1200 then 1100; dd from 1200 -> ~0.083
    assert m["ending_bankroll"] == 1100.0
    assert m["max_drawdown"] == round(100 / 1200, 4)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
