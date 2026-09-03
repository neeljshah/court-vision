"""Synthetic checks for E2's prior-only per-regime calibration arm."""
from __future__ import annotations

from scripts.platformkit.ingame import gap_regime_arm


def _ticks() -> list[dict[str, object]]:
    rows = []
    for day in range(12):
        month = "01" if day < 6 else "02"
        for game_number in range(24):
            outcome = float((game_number + day) % 10 < (7 if month == "01" else 3))
            for tick in range(10):
                rows.append({"game": "G%02d_%02d" % (day, game_number),
                             "date": "2026-%s-%02d" % (month, day + 1), "month": month,
                             "model_prob": .5, "market_prob": .48 if outcome else .52,
                             "outcome": outcome, "in_window": True, "tick": tick})
    return rows


def test_small_regime_reports_global_fallback_and_prior_only_fit() -> None:
    report = gap_regime_arm.evaluate(_ticks(), min_n=5000, bootstrap_iterations=30)

    assert report["status"] == "OK"
    assert all(fold["fitted_on_prior_games"] for fold in report["folds"] if fold["status"] == "OK")
    assert report["bucket_table"]
    assert all(row["fit_source"] == "GLOBAL" for row in report["bucket_table"])
    assert "FIT_SOURCE" in gap_regime_arm.render(report)


def test_acceptance_requires_gap_ci_and_bucket_non_regression() -> None:
    report = gap_regime_arm.evaluate(_ticks(), min_n=40, bootstrap_iterations=50)
    acceptance = report["acceptance"]

    assert acceptance is not None
    assert set(acceptance) >= {"gap", "movement_ci_90", "ci_excludes_zero", "no_bucket_regression", "status"}
    assert acceptance["status"] in {"PASS", "REJECT"}
    assert acceptance["no_bucket_regression"] == all(
        row["arm_b_brier"] - row["arm_a_brier"] <= .005 for row in report["bucket_table"])


def _midnight_spanning_ticks() -> list[dict[str, object]]:
    """Same disjointness scenario as gap_blend_arm's midnight fixture (S36
    correction): GA straddles the UTC boundary, GC is day-1 only (gives the
    day-1 train fold a second game), GB is day-2 only."""
    return [
        {"game": "GA", "date": "2026-01-01", "outcome": 1.0, "model_prob": .5, "market_prob": .5, "in_window": True},
        {"game": "GA", "date": "2026-01-02", "outcome": 1.0, "model_prob": .5, "market_prob": .5, "in_window": True},
        {"game": "GC", "date": "2026-01-01", "outcome": 0.0, "model_prob": .5, "market_prob": .5, "in_window": True},
        {"game": "GB", "date": "2026-01-02", "outcome": 0.0, "model_prob": .5, "market_prob": .5, "in_window": True},
    ]


def test_fit_window_tick_date_counts_self_leak_instead_of_raising() -> None:
    """S36 correction: tick_date (legacy default) must never raise -- it must
    count the midnight self-leak instead, so existing default-mode readers
    (hedge_trial_arms, stacker.py's main(), run_gap_arms_real_corpus.evaluate)
    keep running on the real corpus. GA's day-2 tick is the only leaked scored
    tick out of 2 scored (GA day-2, GB day-2) -- 50.00 pct."""
    report = gap_regime_arm.evaluate(_midnight_spanning_ticks(), min_n=1, bootstrap_iterations=5,
                                     fit_window="tick_date")
    assert report["status"] == "OK"
    assert report["self_leak_ticks"] == 1
    assert report["self_leak_pct"] == 50.0


def test_fit_window_game_first_date_has_zero_self_leak() -> None:
    report = gap_regime_arm.evaluate(_midnight_spanning_ticks(), min_n=1, bootstrap_iterations=5,
                                     fit_window="game_first_date")
    assert report["status"] == "OK"
    assert report["self_leak_ticks"] == 0
    assert report["self_leak_pct"] == 0.0


def test_check_disjoint_raises_only_in_game_first_date_mode() -> None:
    """Direct unit check on a constructed leaky fold (train/test share 'GA'):
    game_first_date raises (the S36 bar); tick_date counts and returns it."""
    try:
        gap_regime_arm._check_disjoint({"GA"}, {"GA", "GB"}, "game_first_date")
        raised = False
    except AssertionError:
        raised = True
    assert raised, "game_first_date mode must raise on a constructed leaky fold"

    assert gap_regime_arm._check_disjoint({"GA"}, {"GA", "GB"}, "tick_date") == {"GA"}
