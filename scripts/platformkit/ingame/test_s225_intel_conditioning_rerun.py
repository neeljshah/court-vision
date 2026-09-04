"""Focused S225 strictly-prior and shared-evaluator checks; run this file only."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.ingame import s225_intel_conditioning_rerun as s225
from scripts.platformkit.ingame.s225_conditioning_prior import rebuild_prior_conditions


def _team_games() -> tuple[pd.DataFrame, pd.DataFrame]:
    entries, bridge = [], []
    for number in range(12):
        game, date = "g%02d" % number, "2026-01-%02d" % (number + 1)
        bridge.append({"game": game, "home_nba": "A", "away_nba": "B"})
        entries.extend([
            {"game": game, "team": "A", "game_date": date, "outcome": float(number % 2), "score_diff": float(number - 4)},
            {"game": game, "team": "B", "game_date": date, "outcome": float(1 - number % 2), "score_diff": float(4 - number)},
        ])
    return pd.DataFrame(entries), pd.DataFrame(bridge).set_index("game")


def _ticks() -> pd.DataFrame:
    rows = []
    for game in range(18):
        date = "2026-02-%02d" % (game + 1)
        for tick in range(2):
            rows.append({"game": "g%02d" % game, "game_date": date,
                         "timestamp": date + "T00:0%d:00Z" % tick, "y": float(game % 2),
                         "market": 0.25 + 0.5 * (game % 2), "condition": (game % 3 - 1) / 3.0,
                         "null_condition": (game % 5 - 2) / 5.0})
    return pd.DataFrame(rows)


def test_s225_prior_excludes_scored_future_and_null_runs_through_shared_evaluator():
    raw, bridge = _team_games()
    before = rebuild_prior_conditions(raw, bridge, "hot_night")
    changed = raw.copy()
    changed.loc[changed["game"].isin(["g06", "g07"]), ["outcome", "score_diff"]] = [99.0, 999.0]
    after = rebuild_prior_conditions(changed, bridge, "hot_night")
    old = before.loc[before["game"].eq("g06"), "condition"].iloc[0]
    new = after.loc[after["game"].eq("g06"), "condition"].iloc[0]
    assert old == new, "the scored game and a later game must not enter its prior"
    known = before["prior_last_game_date"].notna()
    assert (before.loc[known, "prior_last_game_date"] < before.loc[known, "game_date"]).all()
    null_prediction, null_folds = s225._predict(_ticks(), planted_null=True)
    real_prediction, real_folds = s225._predict(_ticks(), planted_null=False)
    assert len(null_prediction) == len(real_prediction) == 36
    assert null_prediction["game"].nunique() == real_prediction["game"].nunique() == 18
    assert len(null_folds) == len(real_folds) == s225.N_GROUPS
    assert null_prediction[["prediction_arm", "prediction_incumbent"]].notna().all().all()
    assert real_prediction[["prediction_arm", "prediction_incumbent"]].notna().all().all()
    trained = real_prediction["train_last_game_date"].notna()
    assert (real_prediction.loc[trained, "train_last_game_date"] < real_prediction.loc[trained, "game_date"]).all()


def test_s225_legacy_fold_aliases_remain_additive():
    _, folds = s225._predict(_ticks(), planted_null=False)
    for fold in folds:
        assert fold["fold"] == fold["split"]
        assert fold["train_games"] == fold["prior_train_games_min"]
        assert fold["fallback_market_ticks"] >= 0
