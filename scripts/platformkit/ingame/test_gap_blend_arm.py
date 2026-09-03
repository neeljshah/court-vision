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


def _midnight_spanning_ticks() -> list[dict[str, object]]:
    """GA's ticks straddle the UTC date boundary; GC is day-1 only (gives the
    day-1 train fold outcome diversity); GB is day-2 only. Under tick_date
    folds, GA's day-1 tick trains the fold that scores GA's own day-2 tick
    (self-leak). Under game_first_date folds GA's whole game keys to day 1,
    so it never lands in the day-2 test fold with GB."""
    return [
        {"game": "GA", "date": "2026-01-01", "outcome": 1.0, "model_prob": .5,
         "market_prob": .5, "state_signal": 3.0, "in_window": True},
        {"game": "GA", "date": "2026-01-02", "outcome": 1.0, "model_prob": .5,
         "market_prob": .5, "state_signal": 3.0, "in_window": True},
        {"game": "GC", "date": "2026-01-01", "outcome": 0.0, "model_prob": .5,
         "market_prob": .5, "state_signal": -3.0, "in_window": True},
        {"game": "GB", "date": "2026-01-02", "outcome": 0.0, "model_prob": .5,
         "market_prob": .5, "state_signal": -3.0, "in_window": True},
    ]


def test_fit_window_game_first_date_removes_midnight_self_leak() -> None:
    frame = gap_blend_arm._frame(_midnight_spanning_ticks())

    scored, folds = gap_blend_arm._walk_forward(frame, gap_blend_arm._DEFAULT_W_MAX,
                                                gap_blend_arm._DEFAULT_MAX_DEVIATION,
                                                fit_window="game_first_date")
    assert set(scored["game"]) == {"GB"}
    assert all(fold.get("status") in {"OK", "INSUFFICIENT"} for fold in folds)
    assert scored.attrs["self_leak_ticks"] == 0


def test_fit_window_tick_date_counts_self_leak_instead_of_raising() -> None:
    """S36 correction: tick_date (legacy default) must never raise -- it must
    count the same midnight self-leak the game_first_date bar removes, so
    existing default-mode readers (hedge_trial_arms.e4_blend_series,
    stacker.py's main(), run_gap_arms_real_corpus.evaluate) keep running on
    the real corpus. On this fixture GA's day-2 tick is the only leaked
    scored tick out of the 2 scored (GA day-2, GB day-2) -- 50.00 pct."""
    frame = gap_blend_arm._frame(_midnight_spanning_ticks())

    scored, folds = gap_blend_arm._walk_forward(frame, gap_blend_arm._DEFAULT_W_MAX,
                                                gap_blend_arm._DEFAULT_MAX_DEVIATION,
                                                fit_window="tick_date")
    assert set(scored["game"]) == {"GA", "GB"}
    assert scored.attrs["self_leak_ticks"] == 1
    assert round(100.0 * scored.attrs["self_leak_ticks"] / len(scored), 2) == 50.0
    assert all(fold.get("status") in {"OK", "INSUFFICIENT"} for fold in folds)

    report = gap_blend_arm.evaluate(_midnight_spanning_ticks(), bootstrap_iterations=5, fit_window="tick_date")
    assert report["status"] == "OK"
    assert report["self_leak_ticks"] == 1
    assert report["self_leak_pct"] == 50.0


def test_check_disjoint_raises_only_in_game_first_date_mode() -> None:
    """Direct unit check on a constructed leaky fold (train/test share 'GA'):
    game_first_date raises (the S36 bar); tick_date counts and returns it."""
    try:
        gap_blend_arm._check_disjoint({"GA"}, {"GA", "GB"}, "game_first_date")
        raised = False
    except AssertionError:
        raised = True
    assert raised, "game_first_date mode must raise on a constructed leaky fold"

    assert gap_blend_arm._check_disjoint({"GA"}, {"GA", "GB"}, "tick_date") == {"GA"}
