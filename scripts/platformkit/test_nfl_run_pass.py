"""Synthetic leak checks for the situation-only NFL run/pass evaluator."""
import pandas as pd

from scripts.platformkit.nfl_run_pass import FEATURE_COLUMNS, build_features, walk_forward


def _row(season, game_id, date, team, play_type, penalty=0):
    return {"season": season, "game_id": game_id, "game_date": date, "posteam": team,
            "play_type": play_type, "penalty": penalty, "down": 1, "ydstogo": 10,
            "yardline_100": 70, "qtr": 1, "half_seconds_remaining": 1700,
            "game_seconds_remaining": 3500, "posteam_score": 0, "defteam_score": 0,
            "posteam_timeouts_remaining": 3, "defteam_timeouts_remaining": 3,
            "shotgun": 1, "no_huddle": 0}


def test_asof_pass_rate_excludes_same_game_and_future_rows():
    base = pd.DataFrame([_row(2022, "a", "2022-09-01", "AAA", "run"),
                         _row(2022, "b", "2022-09-08", "AAA", "pass")])
    extended = pd.concat([base, pd.DataFrame([_row(2022, "b", "2022-09-08", "AAA", "pass"),
                                               _row(2022, "c", "2022-09-15", "AAA", "pass")])], ignore_index=True)
    left, right = build_features(base), build_features(extended)
    assert left.loc[left.game_id == "b", "team_asof_pass_rate"].tolist() == [0.0]
    assert right.loc[right.game_id == "b", "team_asof_pass_rate"].tolist() == [0.0, 0.0]


def test_walk_forward_keeps_strict_season_ordering():
    rows = []
    for season in range(2020, 2025):
        for index in range(12):
            row = {name: float(index % 3) for name in FEATURE_COLUMNS}
            row.update({"season": season, "game_id": "{}-{}".format(season, index), "offense_team": "AAA", "target": index % 2})
            rows.append(row)
    report = walk_forward(pd.DataFrame(rows))
    assert [fold["test_season"] for fold in report["folds"]] == [2022, 2023, 2024]
    assert all(fold["train_through_season"] < fold["test_season"] for fold in report["folds"])


def test_filter_drops_specials_and_penalty_rows():
    plays = pd.DataFrame([_row(2022, "a", "2022-09-01", "AAA", "run"),
                          _row(2022, "a", "2022-09-01", "AAA", "pass"),
                          _row(2022, "a", "2022-09-01", "AAA", "punt"),
                          _row(2022, "a", "2022-09-01", "AAA", "pass", penalty=1)])
    features = build_features(plays)
    assert len(features) == 2
    assert features.target.tolist() == [0, 1]
