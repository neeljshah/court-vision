"""Focused synthetic coverage for the fixed-offset residual experiment."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.ingame import gap_offset_arm


def _fixture() -> tuple[list[dict[str, object]], pd.DataFrame]:
    ticks, features = [], []
    for day in range(12):
        date = "2026-02-%02d" % (day + 1)
        for number in range(6):
            game, state = "G_%02d_%02d" % (day, number), float((number + day) % 2)
            outcome, prior = state, 0.35 if state else 0.65
            # The shared window classifier requires ten later ticks after a score event.
            for tick in range(12):
                stamp = "%sT12:%02d:00Z" % (date, tick)
                ticks.append({"game": game, "timestamp": stamp, "outcome": outcome,
                              "model_prob": prior, "market_prob": 0.2 + 0.6 * state,
                              "state_summary": {"home_score": int(tick > 0 and state),
                                                "away_score": int(tick > 0 and not state)}})
                features.append({"game": game, "timestamp": stamp, "state_only": state})
    return ticks, pd.DataFrame(features)


def test_zero_capacity_reproduces_arm_a_to_six_decimals() -> None:
    ticks, features = _fixture()
    report = gap_offset_arm.evaluate(ticks, features, bootstrap_iterations=10, max_estimators=0)
    metrics = report["slices"]["in_window_ticks"]["metrics"]
    assert metrics is not None
    assert round(metrics["arm_a_brier"], 6) == round(metrics["arm_b_brier"], 6)


def test_offset_arm_excludes_prior_and_market_and_reports_games() -> None:
    ticks, features = _fixture()
    report = gap_offset_arm.evaluate(ticks, features, bootstrap_iterations=10, max_estimators=30)
    metrics = report["slices"]["in_window_ticks"]["metrics"]
    assert metrics is not None
    assert report["state_features"] == ["state_only"]
    assert metrics["n_games"] > 0
    assert "N_GAMES" in gap_offset_arm.render(report)
    assert all(fold["game_disjoint"] for fold in report["folds"])


def test_logit_offset_round_trips_probabilities() -> None:
    probability = np.array([0.1, 0.5, 0.9])
    assert np.allclose(gap_offset_arm.zero_capacity_prob(probability), probability)
