"""Synthetic leak-free checks for the NFL schedule baseline."""
import pandas as pd

from scripts.platformkit.nfl_game_model import build_features, walk_forward


def _games(last_season=2024):
    rows = []
    for season in range(2019, last_season + 1):
        for week in range(4):
            rows.append({"season": season, "gameday": "%d-09-%02d" % (season, 1 + week),
                         "game_id": "%d-%d-a" % (season, week), "home_team": "A", "away_team": "B",
                         "home_score": 24 if (season + week) % 2 else 17,
                         "away_score": 17 if (season + week) % 2 else 24})
    return pd.DataFrame(rows)


def test_features_are_invariant_when_future_games_are_appended():
    base = _games(2022)
    original = build_features(base)
    extended = build_features(pd.concat([base, _games(2024).query("season > 2022")], ignore_index=True))
    compared = extended[extended["game_id"].isin(original["game_id"])]
    columns = ["game_id", "home_win"] + [column for column in original.columns if column.endswith(("win_pct", "pf_l5", "pa_l5", "rest_days", "flag"))]
    assert original[columns].sort_values("game_id").reset_index(drop=True).equals(
        compared[columns].sort_values("game_id").reset_index(drop=True))


def test_walk_forward_has_strictly_ordered_season_folds():
    reports = walk_forward(build_features(_games()))
    assert len(reports) == 4
    assert all(row["max_train_season"] < row["test_season"] for row in reports)
