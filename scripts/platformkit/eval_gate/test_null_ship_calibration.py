"""Focused checks for the sequential corrected-gate null calibration."""
from __future__ import annotations

from scripts.platformkit.eval_gate.golden_loader import load_golden
from scripts.platformkit.eval_gate.null_ship_calibration import (
    CalibrationResult, pure_noise_predictor, render_report, run_calibration,
    run_exploit_regressions,
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


def test_label_and_market_echoes_are_explicit_non_ships():
    results = run_exploit_regressions()
    assert [result.name for result in results] == ["LABEL-ECHO", "MARKET-ECHO"]
    assert all(result.blocked for result in results)
    assert {result.outcome for result in results} <= {"LEAK_ERROR", "REDACTED", "NON_SHIP"}


def test_s40b_rt6_a_provisional_run_can_never_report_pass():
    """RT-6: `.passed` never consulted `.provisional`. Measured before the fix:
    CalibrationResult(candidates=1, ships=0, provisional=True) -> passed=True and main()
    exit 0, so a wall-timed-out one-candidate run reported PASS. The 2*alpha ceiling is a
    pre-registered bar and is unchanged; only the provisional clause is new."""
    timed_out = CalibrationResult(1, 0, 1.0, 0.05, True)
    assert timed_out.ship_rate == 0.0            # would clear any ceiling
    assert timed_out.passed is False             # ...but it measured nothing
    report = render_report(timed_out)
    assert "verdict=UNDECIDED" in report
    assert "BROKEN: every SHIP" not in report    # stopping early is not misbehaviour

    # the same run, completed, does pass -- the ceiling itself has not moved.
    assert CalibrationResult(1, 0, 1.0, 0.05, False).passed is True
    # and the ceiling is still exactly twice the nominal alpha: 0.100 passes, 0.105 does not.
    assert CalibrationResult(200, 20, 1.0, 0.05, False).passed is True
    assert CalibrationResult(200, 21, 1.0, 0.05, False).passed is False
