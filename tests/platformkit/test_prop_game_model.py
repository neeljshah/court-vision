"""tests.platformkit.test_prop_game_model -- Q15 deliverable 2 checks (+ review-round adds).
No network.

(a) as-of leakage: a row's feature must not change when THAT row's own stat changes.
(b) the pinball computation (inside score_quantiles) on a fixed vector.
(c) the game-clustered bootstrap CI contains its own point estimate.
(d) split_corpus enforces the EMBARGO_DAYS boundary, cross_season and fallback alike.
(e) build_opp_allowed only uses the opponent's PRIOR games (shift proof).
(f) clustered_ci's verdict direction: model-better -> AHEAD, model-worse -> BEHIND.

Run: python -m pytest tests/platformkit/test_prop_game_model.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.proof_nba.prop_game_model import (
    EMBARGO_DAYS, build_opp_allowed, build_player_features, clustered_ci,
    score_quantiles, split_corpus)

_BASE_STATS = ("min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov",
               "usagepercentage", "trueshootingpercentage")


def _synthetic_frame(last_row_stat_value: float) -> pd.DataFrame:
    """One player, 3 games; the LAST game's `pts` is the value under test."""
    n = 3
    data = {stat: [10.0, 20.0, 30.0][:n] for stat in _BASE_STATS}
    data["pts"] = [10.0, 20.0, last_row_stat_value]
    data["player_id"] = [1, 1, 1]
    data["date"] = pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-05"])
    data["is_home"] = [True, False, True]
    data["starter"] = [True, True, False]
    return pd.DataFrame(data)


def test_asof_leakage_feature_ignores_current_row_stat():
    df_a = _synthetic_frame(last_row_stat_value=30.0)
    df_b = _synthetic_frame(last_row_stat_value=999.0)  # only the LAST row's pts differs
    build_player_features(df_a)
    build_player_features(df_b)
    last = 2
    # every trailing/EWM pts feature on the last row must be identical across A and B --
    # it is computed from shift(1) (prior games only) and must not see the current value.
    for col in ("pts_ma5", "pts_ma10", "pts_ma20", "pts_ewm10"):
        assert df_a.loc[last, col] == df_b.loc[last, col], f"{col} leaked the current-row stat"
    # sanity: the two frames really do differ only in the current-row raw stat
    assert df_a.loc[last, "pts"] != df_b.loc[last, "pts"]
    # and the trailing mean is NOT trivially equal to the (differing) raw value -- confirms
    # the assertion above is actually exercising prior-only history, not a no-op column
    assert df_a.loc[last, "pts_ma5"] == 15.0  # mean of the two PRIOR games (10, 20)


def test_pinball_on_fixed_vector():
    y = np.array([10.0])
    taus = (0.1, 0.25, 0.5, 0.75, 0.9)
    q_pred = np.array([[8.0, 9.0, 10.0, 11.0, 12.0]])  # matches TAUS order in the module
    out = score_quantiles(y, q_pred)
    # hand-computed: diffs [2,1,0,-1,-2] -> losses [.2,.25,0,.25,.2] -> mean .18
    assert abs(out["pinball_avg"] - 0.18) < 1e-9
    assert out["mae_median"] == 0.0  # median (tau=0.5) prediction hit exactly
    assert out["coverage_10_90"] == 1.0  # 10 in [8, 12]


def test_clustered_bootstrap_ci_contains_point_estimate():
    rng = np.random.default_rng(7)
    n_games = 40
    rows_per_game = 3
    game_ids = np.repeat(np.arange(n_games), rows_per_game)
    # per-game true delta varies (some rows favour the model, some the baseline)
    per_game_delta = rng.normal(loc=0.5, scale=2.0, size=n_games)
    row_delta = np.repeat(per_game_delta, rows_per_game)
    ci = clustered_ci(row_delta, game_ids)
    assert ci["ci_lo"] <= ci["point"] <= ci["ci_hi"]
    assert ci["verdict"] in ("AHEAD", "BEHIND", "UNDERPOWERED")


def test_split_corpus_enforces_embargo_boundary():
    # cross_season: two seasons back-to-back with only a 2-day gap (< EMBARGO_DAYS=3) --
    # the embargo must still cut training rows short of the test season's start.
    two_season = pd.DataFrame({
        "season": ["2022-23"] * 5 + ["2023-24"] * 5,
        "date": pd.to_datetime(["2023-03-01", "2023-03-02", "2023-03-03", "2023-03-04", "2023-03-05",
                                 "2023-03-07", "2023-03-08", "2023-03-09", "2023-03-10", "2023-03-11"]),
        "game_id": [f"g{i}" for i in range(10)],
    })
    train_df, test_df, meta = split_corpus(two_season, "2023-24")
    assert meta["split"] == "cross_season"
    assert train_df["date"].max() <= test_df["date"].min() - pd.Timedelta(days=EMBARGO_DAYS)
    assert len(train_df) == 4  # 2023-03-05 (2 days before 2023-03-07) falls inside the embargo

    # within_season_fallback: only one season present -> the internal 70/30 cut is also embargoed
    one_season = pd.DataFrame({
        "season": ["2023-24"] * 20,
        "date": pd.date_range("2023-10-01", periods=20, freq="D"),
        "game_id": [f"h{i}" for i in range(20)],
    })
    train_df2, test_df2, meta2 = split_corpus(one_season, "2023-24")
    assert meta2["split"] == "within_season_fallback"
    assert train_df2["date"].max() <= test_df2["date"].min() - pd.Timedelta(days=EMBARGO_DAYS)


def test_opp_allowed_uses_only_opponents_prior_games():
    # two teams, 3 games; team-level rows (one row per team per game) are enough since
    # build_opp_allowed sums to team-game grain internally.
    base = pd.DataFrame({
        "game_id": ["g1", "g1", "g2", "g2", "g3", "g3"],
        "date": pd.to_datetime(["2024-01-01"] * 2 + ["2024-01-03"] * 2 + ["2024-01-05"] * 2),
        "team": ["A", "B", "A", "B", "A", "B"],
        "opp": ["B", "A", "B", "A", "B", "A"],
        "pts": [100.0, 90.0, 110.0, 95.0, 105.0, 92.0],
    })
    allowed = build_opp_allowed(base, "pts")
    # team A's g3 row: opp=B, B's trailing-allowed = mean of what B allowed in g1,g2 = mean(100,110)
    a_g3_idx = base.index[(base["game_id"] == "g3") & (base["team"] == "A")][0]
    assert allowed[a_g3_idx] == 105.0

    # leak check: changing B's OWN g3 score must not change A's g3 opp_allowed feature
    base_leaked = base.copy()
    base_leaked.loc[(base_leaked["game_id"] == "g3") & (base_leaked["team"] == "B"), "pts"] = 999.0
    allowed_leaked = build_opp_allowed(base_leaked, "pts")
    assert allowed_leaked[a_g3_idx] == allowed[a_g3_idx] == 105.0


def test_clustered_ci_verdict_direction():
    game_ids = np.repeat(np.arange(20), 3)
    rng = np.random.default_rng(3)
    # model clearly BETTER than baseline (positive baseline-minus-model delta) -> AHEAD
    better = np.full(60, 2.0) + rng.normal(0, 0.01, 60)
    assert clustered_ci(better, game_ids)["verdict"] == "AHEAD"
    # model clearly WORSE -> BEHIND
    assert clustered_ci(-better, game_ids)["verdict"] == "BEHIND"
