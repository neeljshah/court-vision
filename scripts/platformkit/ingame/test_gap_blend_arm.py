"""Focused synthetic tests for E4 guarded one-parameter logit blending."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import gap_blend_arm


def _ticks(signal: bool = True) -> list[dict[str, object]]:
    rows = []
    for day in range(8):
        for game_number in range(8):
            outcome = float((day + game_number) % 2)
            for tick in range(3):
                rows.append({"game": "G%02d_%02d" % (day, game_number), "date": "2026-01-%02d" % (day + 1),
                             "outcome": outcome, "model_prob": .5, "market_prob": .5,
                             "state_signal": (3.0 if outcome else -3.0) if signal else 0.0,
                             "in_window": True})
    return rows


def test_zero_weight_reproduces_guarded_arm_a_brier() -> None:
    report = gap_blend_arm.evaluate(_ticks(), w_max=0.0, bootstrap_iterations=20)
    metrics = report["slices"]["in_window_ticks"]["metrics"]
    assert metrics is not None
    assert round(metrics["arm_a_brier"], 6) == round(metrics["arm_b_brier"], 6)


def test_extreme_signal_is_clamped_by_imported_market_guard() -> None:
    probabilities = gap_blend_arm._guarded_prob(np.asarray([.5]), np.asarray([.5]), np.asarray([100.0]),
                                                 1.0, .15)
    assert probabilities[0] == .65


def test_prior_fit_can_meet_in_window_gap_acceptance() -> None:
    report = gap_blend_arm.evaluate(_ticks(), bootstrap_iterations=30)
    section = report["slices"]["in_window_ticks"]
    metrics = section["metrics"]
    assert metrics is not None
    assert metrics["gap"] <= .044
    assert section["acceptance"]["ci_excludes_zero"]
    assert section["acceptance"]["accepted"]
