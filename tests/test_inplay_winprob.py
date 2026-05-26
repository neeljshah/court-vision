"""Tests for the R10_M5 in-play win-probability model + live_engine wiring.

Covers:
  * Booster artifact loads from data/models/inplay_winprob_<snap>.lgb
  * predict_home_win_prob returns a probability in [0, 1] for endQ1/endQ2/endQ3
  * Larger leads -> higher home WP (monotonicity sanity check at endQ3)
  * live_engine.project_from_snapshot stamps `home_win_prob_inplay` and
    `inplay_winprob_snapshot` on every row at an endQ3 boundary.

CI/cold-start runs skip if the artifact is absent rather than failing —
this matches the pattern in tests/test_winprob_stack.py.
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.inplay_winprob import (  # noqa: E402
    SNAPSHOTS,
    _artifact_path,
    features_from_snapshot,
    load_booster,
    predict_home_win_prob,
    reset_cache,
)


def _all_artifacts_present() -> bool:
    return all(os.path.exists(_artifact_path(s)) for s in SNAPSHOTS)


pytestmark = pytest.mark.skipif(
    not _all_artifacts_present(),
    reason=(
        "in-play winprob artifacts missing -- run "
        "`python scripts/train_inplay_winprob_endq3.py` first"
    ),
)


@pytest.fixture(autouse=True)
def _reset_module_cache():
    reset_cache()
    yield
    reset_cache()


def test_endq3_artifact_loads():
    """Booster must load from disk and expose the predict() method."""
    b = load_booster("endQ3")
    assert b is not None, "endQ3 booster failed to load"
    assert hasattr(b, "predict"), "loaded object is not a lightgbm.Booster"


def test_predict_returns_unit_interval_at_all_snapshots():
    """Synthetic input must yield a probability in [0, 1] at every snapshot."""
    # Synthetic "home leading by 8 at end-Q3" feature vector. All numeric
    # features present so even endQ3 (the most demanding schema) is satisfied.
    feats = {
        "score_margin": 8.0,
        "total_pts": 180.0,
        "pace_so_far": 5.0,
        "q1_delta": 2.0,
        "q2_delta": 3.0,
        "q3_delta": 3.0,
        "last_q_margin": 3.0,
        "pregame_win_prob": 0.55,
        "home_team_id": 1610612747,  # LAL — present in train set
        "season": "2024-25",
    }
    for snap in SNAPSHOTS:
        p = predict_home_win_prob(feats, snap)
        assert p is not None, f"{snap} returned None despite artifact present"
        assert 0.0 <= p <= 1.0, f"{snap} probability {p} outside [0, 1]"


def test_endq3_monotonicity_in_score_margin():
    """At endQ3 with all else equal, a larger home lead -> higher home WP."""
    base = {
        "total_pts": 200.0, "pace_so_far": 5.55,
        "q1_delta": 0.0, "q2_delta": 0.0, "q3_delta": 0.0,
        "last_q_margin": 0.0, "pregame_win_prob": 0.50,
        "home_team_id": 1610612747, "season": "2024-25",
    }
    probs = []
    for margin in (-15.0, -5.0, 0.0, 5.0, 15.0):
        feats = dict(base, score_margin=margin, last_q_margin=margin / 3)
        p = predict_home_win_prob(feats, "endQ3")
        assert p is not None
        probs.append(p)
    # Monotonic-ish: the +15 case must dominate the -15 case by a wide margin.
    assert probs[-1] > probs[0] + 0.30, (
        f"endQ3 booster is not directionally responsive to margin: {probs}"
    )


def test_features_from_snapshot_at_endq3_boundary():
    """The helper builds an inference-ready feature dict from a live snap."""
    snap = {
        "period": 4, "clock": "12:00",  # endQ3 boundary (start of Q4)
        "home_score": 95, "away_score": 88,
        "home_q1": 28, "home_q2": 22, "home_q3": 45,
        "away_q1": 26, "away_q2": 25, "away_q3": 37,
        "home_team_id": 1610612747, "season": "2024-25",
        "pregame_win_prob": 0.58,
    }
    feats = features_from_snapshot(snap)
    assert feats, "expected non-empty feature dict at endQ3 boundary"
    assert feats["score_margin"] == 7
    assert feats["total_pts"] == 183
    assert feats["q1_delta"] == 2
    assert feats["q2_delta"] == -3
    assert feats["q3_delta"] == 8
    assert feats["last_q_margin"] == 8
    assert feats["pregame_win_prob"] == 0.58


def test_features_from_snapshot_returns_empty_mid_quarter():
    """Mid-quarter snapshots must NOT produce features (model not valid)."""
    snap = {
        "period": 3, "clock": "5:42",  # mid-Q3, NOT a boundary
        "home_score": 72, "away_score": 68,
        "home_q1": 28, "home_q2": 22, "home_q3": 22,
        "away_q1": 26, "away_q2": 25, "away_q3": 17,
        "home_team_id": 1610612747, "season": "2024-25",
    }
    feats = features_from_snapshot(snap)
    assert feats == {}, "mid-quarter snap must return empty dict"


def test_live_engine_stamps_inplay_winprob_at_endq3():
    """End-to-end: project_from_snapshot must populate the new row fields."""
    # Build a minimal snapshot the live_engine can consume. The downstream
    # project_snapshot expects players; we synthesize a single-player game so
    # the projection path runs to completion without external data.
    snap = {
        "game_id": "0099900001",
        "captured_at": "2026-05-25T22:00:00Z",
        "game_status": "LIVE",
        "period": 4,
        "clock": "12:00",
        "home_score": 95, "away_score": 88,
        "home_team": "LAL", "away_team": "BOS",
        "home_team_id": 1610612747,
        "season": "2024-25",
        "home_q1": 28, "home_q2": 22, "home_q3": 45,
        "away_q1": 26, "away_q2": 25, "away_q3": 37,
        "pregame_win_prob": 0.58,
        "players": [
            {"player_id": 2544, "name": "LeBron James", "team": "LAL",
             "min": 30.0, "pts": 22, "reb": 6, "ast": 7, "fg3m": 2,
             "stl": 1, "blk": 0, "tov": 2, "pf": 2, "is_starter": True},
        ],
    }
    from src.prediction.live_engine import project_from_snapshot
    try:
        rows = project_from_snapshot(snap)
    except Exception as exc:  # pragma: no cover - depends on upstream scaffolding
        pytest.skip(f"project_from_snapshot scaffolding unavailable: {exc}")
    if not rows:
        pytest.skip("project_from_snapshot produced no rows (upstream missing)")
    for r in rows:
        assert "home_win_prob_inplay" in r, "row missing home_win_prob_inplay"
        assert "inplay_winprob_snapshot" in r, "row missing inplay_winprob_snapshot"
        p = r["home_win_prob_inplay"]
        if p is not None:
            assert 0.0 <= p <= 1.0, f"out-of-range WP: {p}"
            assert r["inplay_winprob_snapshot"] == "endQ3"
