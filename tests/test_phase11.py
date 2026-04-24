"""tests/test_phase11.py — Phase 11: live models + betting edge."""
from __future__ import annotations

import os
import tempfile

import pytest

from src.prediction.live_models import (
    LivePropUpdater,
    ComebackProbabilityModel,
    GarbageTimePredictor,
    FoulTroubleModel,
    Q4UsageModel,
    MomentumRunModel,
)
from src.prediction.betting_edge import BettingEdge, CLVTracker, ArbDetector


# ── Live models: instantiate + predict valid range ────────────────────────────

def test_live_prop_updater_heuristic():
    m = LivePropUpdater()
    assert not m._trained
    result = m.predict(pre_game_proj=20.0, halftime_actual=10.0, minutes_played_ratio=0.5)
    assert 0.0 <= result <= 50.0


def test_comeback_prob_heuristic():
    m = ComebackProbabilityModel()
    assert not m._trained
    p_trailing = m.predict(score_diff=-10.0, minutes_remaining=12.0, home_flag=1)
    p_leading  = m.predict(score_diff=10.0,  minutes_remaining=12.0, home_flag=0)
    assert 0.0 <= p_trailing <= 1.0
    assert 0.0 <= p_leading  <= 1.0
    assert p_trailing < p_leading   # trailing has lower comeback prob


def test_garbage_time_heuristic():
    m = GarbageTimePredictor()
    assert not m._trained
    assert m.predict(score_diff=25.0, minutes_remaining=3.0, scoreboard_period=4) is True
    assert m.predict(score_diff=3.0,  minutes_remaining=10.0, scoreboard_period=3) is False


def test_foul_trouble_heuristic():
    m = FoulTroubleModel()
    assert not m._trained
    p_5fouls = m.predict(foul_count=5, period=3, minutes_remaining=10.0)
    p_1foul  = m.predict(foul_count=1, period=1, minutes_remaining=20.0)
    assert 0.0 <= p_5fouls <= 1.0
    assert 0.0 <= p_1foul  <= 1.0
    assert p_5fouls > p_1foul


def test_foul_trouble_fouled_out():
    m = FoulTroubleModel()
    assert m.predict(foul_count=6, period=4, minutes_remaining=0.0) == 1.0


def test_q4_usage_heuristic():
    m = Q4UsageModel()
    assert not m._trained
    mult_star_close = m.predict(score_diff=2.0, player_usage_rate=0.30, close_game_flag=1)
    mult_bench      = m.predict(score_diff=2.0, player_usage_rate=0.10, close_game_flag=0)
    assert 0.7 <= mult_star_close <= 1.5
    assert 0.7 <= mult_bench      <= 1.5
    assert mult_star_close >= mult_bench


def test_momentum_run_heuristic():
    m = MomentumRunModel()
    assert not m._trained
    p_long  = m.predict(run_length=6, team_fg_pct_last_10=0.60, time_since_last_timeout=120.0)
    p_short = m.predict(run_length=1, team_fg_pct_last_10=0.30, time_since_last_timeout=30.0)
    assert 0.0 <= p_long  <= 1.0
    assert 0.0 <= p_short <= 1.0
    assert p_long > p_short


# ── BettingEdge ───────────────────────────────────────────────────────────────

def test_betting_edge_known_odds():
    be = BettingEdge()
    # -110 implied ≈ 0.5238
    imp = be.implied_prob(-110)
    assert abs(imp - 0.5238) < 0.001

    # model says 0.60 vs -110 implied ~0.524 → edge ~0.076
    e = be.edge(0.60, -110)
    assert 0.07 < e < 0.09


def test_star_ratings():
    be = BettingEdge()
    assert be.star_rating(0.04) == 0
    assert be.star_rating(0.06) == 1
    assert be.star_rating(0.09) == 2
    assert be.star_rating(0.13) == 3


def test_evaluate_returns_all_keys():
    result = BettingEdge().evaluate(model_prob=0.65, american_odds=-110, bankroll=1000.0)
    for key in ("model_prob", "implied_prob", "edge", "stars", "kelly_size"):
        assert key in result
    assert result["stars"] >= 2   # 0.65 vs -110 is a big edge


# ── CLVTracker ────────────────────────────────────────────────────────────────

def test_clv_tracker_log_and_close():
    with tempfile.TemporaryDirectory() as d:
        tracker = CLVTracker(path=os.path.join(d, "clv.csv"))
        bet_id = tracker.log(market="LeBron_pts_over", model_prob=0.60, opening_line=-115)
        assert isinstance(bet_id, str) and len(bet_id) > 0

        clv = tracker.close(bet_id, closing_line=-130, result="win")
        # closing -130 implied > opening -115 implied → positive CLV
        assert clv is not None and clv > 0


def test_clv_summary_empty():
    with tempfile.TemporaryDirectory() as d:
        tracker = CLVTracker(path=os.path.join(d, "clv.csv"))
        s = tracker.clv_summary()
        assert s["count"] == 0
        assert s["avg_clv"] == 0.0


def test_clv_summary_populated():
    with tempfile.TemporaryDirectory() as d:
        tracker = CLVTracker(path=os.path.join(d, "clv.csv"))
        for _ in range(3):
            bid = tracker.log("market_x", 0.55, -110)
            tracker.close(bid, -120, "win")
        s = tracker.clv_summary()
        assert s["count"] == 3
        assert s["win_rate"] == 1.0


# ── ArbDetector ───────────────────────────────────────────────────────────────

def test_arb_detector_known_arb():
    det = ArbDetector()
    # DK: over +105, FD: under +102 → total implied = 0.488 + 0.495 = 0.983 < 1.0
    book_lines = {
        "LeBron_pts_over":  {"DraftKings": 105, "FanDuel": -115},
        "LeBron_pts_under": {"DraftKings": -115, "FanDuel": 102},
    }
    results = det.detect(book_lines)
    assert len(results) >= 1
    assert results[0].type == "arb"
    assert results[0].ev > 0


def test_arb_detector_no_arb():
    det = ArbDetector()
    # Standard -110/-110: total implied ~1.048 → no arb
    book_lines = {
        "total_over":  {"BookA": -110},
        "total_under": {"BookA": -110},
    }
    results = det.detect(book_lines)
    assert len(results) == 0


def test_middle_detector():
    det = ArbDetector()
    # DK at 27.5, FD at 28.5 → middle window
    book_lines = {"LeBron_pts": {"DraftKings": 27.5, "FanDuel": 28.5}}
    middles = det.detect_middles(book_lines)
    assert len(middles) == 1
    assert middles[0].type == "middle"
    assert middles[0].ev == 1.0
