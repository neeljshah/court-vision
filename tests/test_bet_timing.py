"""
test_bet_timing.py -- Tests for the timing optimiser (16.7-03).

Acceptance criterion: bet_selector calls line_timing.get_fire_recommendation
and either fires immediately or schedules a delayed fire; the delay queue
persists to data/output/bet_timing_queue.json.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data.line_timing import get_fire_recommendation  # noqa: E402
from src.prediction import bet_selector  # noqa: E402

_CFG = {
    "edge_min": 0.04, "bankroll": 1000.0,
    "clv_filter_enabled": False,            # isolate the timing path
    "timing_optimizer_enabled": True,
    "max_bets_per_game": 10, "max_combined_pct": 0.5, "default_odds": -110,
}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(bet_selector, "_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(bet_selector, "_BET_LOG_PATH", str(tmp_path / "bet_log.json"))
    monkeypatch.setattr(bet_selector, "_load_config", lambda: dict(_CFG))
    return tmp_path


def _edge_row(player: str, edge: float = 0.08) -> dict:
    return {
        "player": player, "stat": "pts", "edge": edge, "direction": "over",
        "book_line": 25.0, "projection": 27.0, "odds": -110,
        "game_id": "G1", "confidence": "high", "team": "BOS", "opp_team": "NYK",
    }


# ── get_fire_recommendation ───────────────────────────────────────────────────

def test_recommend_wait_when_line_moves_in_our_favour():
    """Over bet + predicted closing below current line -> wait for the drop."""
    bet = {"direction": "over", "book_line": 25.0, "time_to_game": 4.0}
    rec = get_fire_recommendation(bet, predict_fn=lambda f: 23.5)
    assert rec["action"] == "wait"
    assert rec["expected_gain"] == pytest.approx(1.5)
    assert rec["delay_minutes"] > 0


def test_recommend_fire_now_when_line_moves_against_us():
    """Over bet + predicted closing above current line -> fire now."""
    bet = {"direction": "over", "book_line": 25.0, "time_to_game": 4.0}
    rec = get_fire_recommendation(bet, predict_fn=lambda f: 26.5)
    assert rec["action"] == "fire_now"


def test_under_bet_waits_when_line_expected_to_rise():
    """Under bet wants a higher line — a predicted rise justifies waiting."""
    bet = {"direction": "under", "book_line": 25.0, "time_to_game": 2.0}
    rec = get_fire_recommendation(bet, predict_fn=lambda f: 26.0)
    assert rec["action"] == "wait"


def test_recommend_fire_now_when_no_model(tmp_path):
    """No closing-price model -> degrade gracefully to fire_now."""
    bet = {"direction": "over", "book_line": 25.0, "time_to_game": 4.0}
    rec = get_fire_recommendation(bet, model_path=str(tmp_path / "missing.pkl"))
    assert rec["action"] == "fire_now"


# ── bet_selector wiring ───────────────────────────────────────────────────────

def test_wait_bet_diverted_to_queue(_isolate):
    """A 'wait' recommendation diverts the bet out of the immediate list."""
    wait_fn = lambda bet: {"action": "wait", "delay_minutes": 30.0,
                           "expected_gain": 1.2, "reason": "line will drop"}
    bets = bet_selector.select(
        [_edge_row("Star A")], "2026-05-21", dry_run=True,
        timing_recommend_fn=wait_fn,
    )
    assert bets == []   # diverted, not fired immediately


def test_timing_queue_persisted(_isolate):
    """The delay queue is written to bet_timing_queue.json."""
    wait_fn = lambda bet: {"action": "wait", "delay_minutes": 45.0,
                           "expected_gain": 0.9, "reason": "wait"}
    bet_selector.select(
        [_edge_row("Star A")], "2026-05-21", dry_run=True,
        timing_recommend_fn=wait_fn,
    )
    queue_path = os.path.join(str(_isolate), "bet_timing_queue.json")
    assert os.path.exists(queue_path)
    with open(queue_path) as f:
        payload = json.load(f)
    assert payload["count"] == 1
    entry = payload["queue"][0]
    assert entry["bet"]["player"] == "Star A"
    assert entry["bet"]["status"] == "scheduled"
    assert "fire_at" in entry


def test_fire_now_keeps_bet_in_list(_isolate):
    """A 'fire_now' recommendation keeps the bet in the immediate list."""
    fire_fn = lambda bet: {"action": "fire_now", "delay_minutes": 0.0,
                           "expected_gain": -0.3, "reason": "lock now"}
    bets = bet_selector.select(
        [_edge_row("Star A")], "2026-05-21", dry_run=True,
        timing_recommend_fn=fire_fn,
    )
    assert len(bets) == 1
    assert bets[0]["timing"]["action"] == "fire_now"


def test_mixed_fire_and_wait(_isolate):
    """With two bets, one fires immediately and one is scheduled."""
    def split_fn(bet):
        if bet["player"] == "Wait Guy":
            return {"action": "wait", "delay_minutes": 20.0,
                    "expected_gain": 1.0, "reason": "wait"}
        return {"action": "fire_now", "delay_minutes": 0.0,
                "expected_gain": 0.0, "reason": "fire"}

    bets = bet_selector.select(
        [_edge_row("Fire Guy"), _edge_row("Wait Guy")],
        "2026-05-21", dry_run=True, timing_recommend_fn=split_fn,
    )
    assert len(bets) == 1
    assert bets[0]["player"] == "Fire Guy"

    with open(os.path.join(str(_isolate), "bet_timing_queue.json")) as f:
        assert json.load(f)["count"] == 1


def test_timing_failure_fires_bet(_isolate):
    """A timing recommender that raises must not drop the bet."""
    def boom(bet):
        raise RuntimeError("timing exploded")

    bets = bet_selector.select(
        [_edge_row("Star A")], "2026-05-21", dry_run=True,
        timing_recommend_fn=boom,
    )
    assert len(bets) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
