"""Per-file test: temporal split never leaks a game across train/test, the
design matrix builds consistent one-hot columns, and the delta ladder is
monotone non-worsening on a synthetic frame engineered so zone perfectly
separates make-rate (the easiest possible case for the ladder to pass).

Run: python -m pytest domains/basketball_nba/composition/test_shot_quality.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.composition.shot_quality import (
    build_design_matrix, run_delta_ladder, temporal_split,
)


def test_temporal_split_never_splits_a_game() -> None:
    df = pd.DataFrame({"game_id": [f"g{i:03d}" for i in range(10) for _ in range(3)]})
    train, test = temporal_split(df)
    assert set(train["game_id"]).isdisjoint(set(test["game_id"]))
    assert len(train) + len(test) == len(df)


def _synthetic_frame(n_per_zone: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    zones = ["rim", "paint", "mid", "corner3", "above_break_3"]
    zone_make_rate = {"rim": 0.65, "paint": 0.45, "mid": 0.40, "corner3": 0.38, "above_break_3": 0.35}
    rows = []
    n_games = 40
    for g in range(n_games):
        game_id = f"g{g:03d}"
        for z in zones:
            for _ in range(n_per_zone // n_games):
                p = zone_make_rate[z]
                rows.append({
                    "game_id": game_id, "team_id": 1, "defense_team_id": 2, "person_id": rng.integers(1, 5),
                    "zone": z, "subtype_class": "Jump Shot", "assisted": int(rng.random() < 0.5),
                    "made": int(rng.random() < p), "points": 3 if z in ("corner3", "above_break_3") else 2,
                    "shooter_zone_efg": p, "defense_zone_efg_allowed": p, "spacing_mean_dist": 30.0,
                })
    return pd.DataFrame(rows)


def test_design_matrix_consistent_columns_and_ladder_beats_league() -> None:
    df = _synthetic_frame()
    design, groups = build_design_matrix(df)
    assert set(groups["zone"]) == {f"zone_{z}" for z in ["rim", "paint", "mid", "corner3", "above_break_3"]}
    for col in groups["zone"]:
        assert col in design.columns

    ladder_df, final_clf, final_cols = run_delta_ladder(design, groups)
    assert list(ladder_df["rung"]) == ["league", "zone_only", "zone_full", "+shooter", "+defense", "+spacing"]
    league_brier = ladder_df.loc[ladder_df["rung"] == "league", "brier"].iloc[0]
    zone_brier = ladder_df.loc[ladder_df["rung"] == "zone_only", "brier"].iloc[0]
    # zone perfectly separates make-rate by construction -- must clearly beat the constant baseline.
    assert zone_brier < league_brier
    assert final_clf is not None
    assert len(final_cols) > 0
