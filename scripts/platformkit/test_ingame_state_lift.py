"""Synthetic, package-qualified tests for in-game state lift scoring."""
from __future__ import annotations

import pytest
import pandas as pd

from scripts.platformkit import ingame_state_lift


def _ticks(signal: bool) -> tuple[list[dict[str, object]], pd.DataFrame]:
    ticks, features = [], []
    for day in range(16):
        date = "2026-01-%02d" % (day + 1)
        for game_number in range(10):
            game = "MLB_%02d_%02d" % (day, game_number)
            probability = 0.5 if signal else (0.8 if game_number % 2 else 0.2)
            token = (day + game_number * 2) % 5
            outcome = (float((day * 7 + game_number * 3) % 10 < 5) if signal else
                       float(token != 0) if game_number % 2 else float(token == 0))
            market = (0.9 if outcome else 0.1) if signal else probability
            for tick_number in range(12):
                timestamp = "%sT12:%02d:00Z" % (date, tick_number)
                score = {"home_score": int(tick_number >= 1 and outcome),
                         "away_score": int(tick_number >= 1 and not outcome)}
                ticks.append({"game": game, "timestamp": timestamp, "outcome": outcome,
                              "model_prob": probability, "market_prob": market,
                              "state_summary": score, "raw": {"sport": "mlb"}})
                features.append({"game": game, "timestamp": timestamp,
                                 "score_state": (1.0 if outcome else -1.0) if signal
                                 else float(tick_number % 7),
                                 "state_parsed": True, "parse_quality": "full"})
    return ticks, pd.DataFrame(features)


def test_predictive_state_narrows_market_gap() -> None:
    ticks, features = _ticks(signal=True)
    report = ingame_state_lift.evaluate(ticks, features, bootstrap_iterations=30)
    metrics = report["slices"]["in_window_ticks"]["metrics"]

    assert metrics is not None
    assert metrics["arm_b"]["brier"] < metrics["arm_a"]["brier"]
    assert abs(metrics["arm_b"]["brier"] - metrics["market"]["brier"]) < abs(
        metrics["arm_a"]["brier"] - metrics["market"]["brier"])
    assert report["slices"]["in_window_ticks"]["verdict"] in {"CLOSED THE GAP", "NARROWED"}


def test_noise_state_is_no_change() -> None:
    ticks, features = _ticks(signal=False)
    report = ingame_state_lift.evaluate(ticks, features, bootstrap_iterations=30)

    assert report["slices"]["all_ticks"]["verdict"] == "NO CHANGE"


def test_shuffled_dates_fail_prior_only_assertion() -> None:
    with pytest.raises(AssertionError, match="date ordering"):
        ingame_state_lift._assert_prior_dates(["2026-01-03"], ["2026-01-02"])


def test_unparseable_rows_and_games_are_excluded_before_modeling() -> None:
    ticks, features = _ticks(signal=False)
    excluded_game = ticks[0]["game"]
    excluded = features["game"].eq(excluded_game)
    features.loc[excluded, "state_parsed"] = False
    features.loc[excluded, "parse_quality"] = "none"

    report = ingame_state_lift.evaluate(ticks, features, bootstrap_iterations=5)

    assert report["excluded_unparsed_rows"] == 12
    assert report["excluded_unparsed_games"] == 1
    assert report["folds"][0]["train_games"] == 9
    assert report["slices"]["all_ticks"]["metrics"]["n_ticks"] < len(ticks)
