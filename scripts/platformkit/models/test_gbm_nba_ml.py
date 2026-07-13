"""Tests for scripts.platformkit.models.gbm_nba_ml."""

import numpy as np
import pandas as pd

from scripts.platformkit.models import gbm_nba_ml as g


def _toy_box(n=40, seed=0):
    rng = np.random.default_rng(seed)
    teams = ["AAA", "BBB", "CCC", "DDD"]
    dates = pd.date_range("2025-10-01", periods=n, freq="2D")
    rows = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        hp, ap = rng.integers(90, 130), rng.integers(90, 130)
        rows.append({
            "date": dates[i], "home_abbr": h, "away_abbr": a,
            "home_pts": float(hp), "away_pts": float(ap),
            "home_fg_attempted": 85.0, "home_ft_attempted": 20.0,
            "home_oreb": 10.0, "home_tov": 13.0,
            "away_fg_attempted": 85.0, "away_ft_attempted": 20.0,
            "away_oreb": 10.0, "away_tov": 13.0,
        })
    return pd.DataFrame(rows)


def test_leak_trap_features_ignore_own_game_outcome():
    """Row i's features must be identical regardless of game i's own score/box stats --
    only games strictly BEFORE i may influence row i's feature values."""
    box = _toy_box()
    feat_a = g.build_features(box)
    corrupted = box.copy()
    victim = 20
    corrupted.loc[victim, "home_pts"] = 999.0
    corrupted.loc[victim, "away_pts"] = 1.0
    corrupted.loc[victim, "home_fg_attempted"] = 5.0
    feat_b = g.build_features(corrupted)
    row_a = feat_a.loc[victim, g._FEATURES]
    row_b = feat_b.loc[victim, g._FEATURES]
    pd.testing.assert_series_equal(row_a, row_b)
    # but the NEXT game involving either team from the corrupted game must now differ
    # (its walk-forward state was built on the corrupted outcome)
    ht, at = box.loc[victim, "home_abbr"], box.loc[victim, "away_abbr"]
    later = box.loc[victim + 1:]
    nxt = later[(later["home_abbr"].isin([ht, at])) | (later["away_abbr"].isin([ht, at]))].index[0]
    assert not feat_a.loc[nxt, g._FEATURES].equals(feat_b.loc[nxt, g._FEATURES])


def test_fold_structure_train_strictly_before_test():
    box = _toy_box(n=400)
    feat = g.build_features(box)
    # fabricate a market frame covering the second half so folds have something to slice
    m = feat.iloc[200:].reset_index(drop=True).copy()
    m["p_market"] = 0.5
    folds = g.make_folds(feat, m, k=4)
    assert len(folds) >= 1
    for train_mask, lo, hi in folds:
        test_start = m["date"].iloc[lo]
        train_dates = feat.loc[train_mask, "date"]
        assert (train_dates < test_start).all()
        assert hi > lo


def test_artifact_schema():
    rep = g.run()
    assert rep["status"] == "ok"
    assert rep["edge_claimed"] is False
    for key in ("features", "folds", "n_games_per_fold", "brier_gbm", "brier_close",
                "brier_existing_model", "logloss_gbm", "logloss_close", "verdict",
                "top10_gain_features", "honest_note", "season_coverage_note"):
        assert key in rep, key
    assert len(rep["features"]) == len(g._FEATURES)
    assert len(rep["top10_gain_features"]) <= 10
    assert rep["verdict"].split(":")[0] in ("SHARPER", "MATCHES", "TRAILS")


def test_deterministic_seed():
    box = _toy_box(n=150)
    feat = g.build_features(box)
    params = {"max_depth": 2, "n_estimators": 50}
    m1, _ = g._fit(feat[g._FEATURES], feat["home_win"], params, seed=7)
    m2, _ = g._fit(feat[g._FEATURES], feat["home_win"], params, seed=7)
    p1 = m1.predict_proba(feat[g._FEATURES])[:, 1]
    p2 = m2.predict_proba(feat[g._FEATURES])[:, 1]
    np.testing.assert_allclose(p1, p2)
