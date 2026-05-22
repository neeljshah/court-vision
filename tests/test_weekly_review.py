"""
test_weekly_review.py -- Tests for the paper-trade go/no-go review (19-02).

Acceptance criterion: weekly_review reads the bet ledger and computes paper
bets settled, CLV beat rate, paper ROI, calibration drift per stat, backtest
vs paper ROI ratio, and circuit-breaker events; prints PASS/FAIL per criterion
and an overall GO/NO-GO verdict.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

from weekly_review import run_paper_trade_review  # noqa: E402

_CRITERIA = {
    "paper_bets_settled", "clv_beat_rate", "paper_roi",
    "calibration_drift", "backtest_paper_ratio", "circuit_breaker_events",
}


def _winning_bet(i: int, won: bool = True) -> dict:
    """A settled paper bet that beat its closing line."""
    return {
        "bet_id": f"b{i}", "stat": "pts", "direction": "over",
        "status": "won" if won else "lost", "won": won,
        "stake": 100.0, "pnl": 100.0 if won else -100.0,
        "book_line": 25.0, "closing_line": 26.0,   # over + line up -> CLV beat
    }


def _write(tmp_path, name, data) -> str:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_review_reports_all_six_criteria(tmp_path):
    """The review evaluates exactly the six named go/no-go criteria."""
    ledger = _write(tmp_path, "bet_log.json", [_winning_bet(i) for i in range(25)])
    review = run_paper_trade_review(
        bet_log_path=ledger,
        backtest_path=str(tmp_path / "none.json"),
        circuit_state_path=str(tmp_path / "none.json"),
        residuals_path=str(tmp_path / "none.json"),
    )
    names = {c["name"] for c in review["criteria"]}
    assert names == _CRITERIA
    assert review["total"] == 6


def test_healthy_book_yields_go_verdict(tmp_path):
    """A profitable, well-calibrated paper book passes all criteria -> GO."""
    ledger = _write(tmp_path, "bet_log.json", [_winning_bet(i) for i in range(30)])
    backtest = _write(tmp_path, "backtest.json", {"total_roi": 1.0})  # paper roi 1.0 too
    residuals = _write(tmp_path, "residuals.json", [
        {"stat": "pts", "predicted": 25.0, "actual": 25.0} for _ in range(25)
    ])
    circuit = _write(tmp_path, "circuit.json", {})

    review = run_paper_trade_review(ledger, backtest, circuit, residuals)
    assert review["verdict"] == "GO"
    assert review["passed"] == 6


def test_insufficient_settled_bets_fails(tmp_path):
    """Too few settled bets fails the sample-size criterion."""
    ledger = _write(tmp_path, "bet_log.json", [_winning_bet(i) for i in range(3)])
    review = run_paper_trade_review(
        ledger, str(tmp_path / "n.json"), str(tmp_path / "n.json"),
        str(tmp_path / "n.json"),
    )
    settled = next(c for c in review["criteria"] if c["name"] == "paper_bets_settled")
    assert settled["pass"] is False
    assert review["verdict"] == "NO-GO"


def test_losing_book_fails_roi(tmp_path):
    """A net-losing paper book fails the ROI criterion."""
    ledger = _write(tmp_path, "bet_log.json", [_winning_bet(i, won=False) for i in range(25)])
    review = run_paper_trade_review(
        ledger, str(tmp_path / "n.json"), str(tmp_path / "n.json"),
        str(tmp_path / "n.json"),
    )
    roi = next(c for c in review["criteria"] if c["name"] == "paper_roi")
    assert roi["pass"] is False
    assert roi["value"] < 0


def test_calibration_drift_detected(tmp_path):
    """A stat whose predictions are badly biased trips the drift criterion."""
    ledger = _write(tmp_path, "bet_log.json", [_winning_bet(i) for i in range(25)])
    # pts predicted 35 vs actual 25 -> ~40% relative bias -> drifted
    residuals = _write(tmp_path, "residuals.json", [
        {"stat": "pts", "predicted": 35.0, "actual": 25.0} for _ in range(25)
    ])
    review = run_paper_trade_review(
        ledger, str(tmp_path / "n.json"), str(tmp_path / "n.json"), residuals,
    )
    drift = next(c for c in review["criteria"] if c["name"] == "calibration_drift")
    assert drift["pass"] is False
    assert drift["value"] >= 1


def test_recent_breaker_events_fail_criterion(tmp_path):
    """Multiple circuit-breaker trips in the last 7 days fail the criterion."""
    ledger = _write(tmp_path, "bet_log.json", [_winning_bet(i) for i in range(25)])
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    circuit = _write(tmp_path, "circuit.json", {
        "daily_loss_halt_tripped_at": recent,
        "drawdown_kill_switch_tripped_at": recent,
        "streak_paper_tripped_at": recent,
    })
    review = run_paper_trade_review(
        ledger, str(tmp_path / "n.json"), circuit, str(tmp_path / "n.json"),
    )
    breakers = next(c for c in review["criteria"] if c["name"] == "circuit_breaker_events")
    assert breakers["value"] == 3
    assert breakers["pass"] is False


def test_old_breaker_events_do_not_count(tmp_path):
    """Circuit-breaker trips older than the window are not counted."""
    ledger = _write(tmp_path, "bet_log.json", [_winning_bet(i) for i in range(25)])
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    circuit = _write(tmp_path, "circuit.json", {"daily_loss_halt_tripped_at": old})
    review = run_paper_trade_review(
        ledger, str(tmp_path / "n.json"), circuit, str(tmp_path / "n.json"),
    )
    breakers = next(c for c in review["criteria"] if c["name"] == "circuit_breaker_events")
    assert breakers["value"] == 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
