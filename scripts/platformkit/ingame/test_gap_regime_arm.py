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
