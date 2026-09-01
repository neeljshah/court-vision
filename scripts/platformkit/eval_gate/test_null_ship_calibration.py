"""Focused checks for the sequential corrected-gate null calibration."""
from __future__ import annotations

from scripts.platformkit.eval_gate.golden_loader import load_golden
from scripts.platformkit.eval_gate.null_ship_calibration import (
    CalibrationResult, pure_noise_predictor, render_report, run_calibration,
)


def test_noise_is_reproducible_and_constant_within_each_game():
    states = load_golden()
    _, first = pure_noise_predictor(states, 17)
    _, second = pure_noise_predictor(states, 17)
    assert first == second
    assert len(first) == len({(s["season"], s["game_id"]) for s in states})


def test_small_n_uses_the_real_corrected_gate_serially():
    result = run_calibration(n=2, seed=19, max_wall_seconds=600.0)
    assert result.candidates == 2
    assert 0 <= result.ships <= result.candidates
    assert result.provisional is False


def test_broken_report_suspends_prior_ships_in_exact_words():
    report = render_report(CalibrationResult(10, 2, 1.0, 0.05, False))
    assert "verdict=BROKEN" in report
    assert "every SHIP since the last passing calibration is suspended" in report
