"""Tests for scripts.platformkit.models.gbm_tennis_match."""

import numpy as np
import pandas as pd

from scripts.platformkit.models import gbm_tennis_match as g


def _toy_matches(n=60, seed=0):
    rng = np.random.default_rng(seed)
    players = list(range(1, 9))
    surfaces = ["Hard", "Clay", "Grass"]
    dates = pd.date_range("2015-01-01", periods=n, freq="3D")
    rows = []
    for i in range(n):
        p1, p2 = sorted(rng.choice(players, size=2, replace=False).tolist())
        rows.append({
            "event_id": f"evt-{i}", "date": dates[i].strftime("%Y-%m-%d"),
            "p1_id": p1, "p2_id": p2, "winner": int(rng.integers(1, 3)),
            "surface": surfaces[i % 3], "score": "6-3 6-4", "best_of": 3,
            "p1_rank": float(rng.integers(1, 200)), "p2_rank": float(rng.integers(1, 200)),
        })
    return pd.DataFrame(rows)


def _toy_asof_hold(matches: pd.DataFrame, seed=1):
    rng = np.random.default_rng(seed)
    n = len(matches)
    cols = {"event_id": matches["event_id"].to_numpy()}
    for c in ("p1_hold_pct_asof", "p2_hold_pct_asof", "p1_svpts_won_asof", "p2_svpts_won_asof",
              "p1_hold_pct_hard_asof", "p2_hold_pct_hard_asof",
              "p1_hold_pct_clay_asof", "p2_hold_pct_clay_asof",
              "p1_hold_pct_grass_asof", "p2_hold_pct_grass_asof"):
        cols[c] = rng.uniform(0.5, 0.9, size=n)
    return pd.DataFrame(cols)


def test_leak_trap_features_ignore_own_game_outcome():
    """Row i's features must be identical regardless of game i's own winner/score --
    only games strictly BEFORE i may influence row i's feature values."""
    matches = _toy_matches()
    asof_hold = _toy_asof_hold(matches)
    feat_a = g.build_features(matches, asof_hold, is_wta=0.0)

    corrupted = matches.copy()
    victim = 30
    corrupted.loc[victim, "winner"] = 3 - corrupted.loc[victim, "winner"]
    feat_b = g.build_features(corrupted, asof_hold, is_wta=0.0)

    row_a = feat_a.loc[victim, g._FEATURES]
    row_b = feat_b.loc[victim, g._FEATURES]
    pd.testing.assert_series_equal(row_a, row_b)

    # a LATER match involving either player must now differ (elo state changed)
    p1, p2 = matches.loc[victim, "p1_id"], matches.loc[victim, "p2_id"]
    later = matches.loc[victim + 1:]
    nxt = later[(later["p1_id"].isin([p1, p2])) | (later["p2_id"].isin([p1, p2]))].index[0]
    assert not feat_a.loc[nxt, g._FEATURES].equals(feat_b.loc[nxt, g._FEATURES])


def test_fold_structure_train_strictly_before_test():
    matches = _toy_matches(n=500)
    matches["date"] = pd.date_range("2015-01-01", periods=500, freq="8D").strftime("%Y-%m-%d")
    asof_hold = _toy_asof_hold(matches)
    feat = g.build_features(matches, asof_hold, is_wta=0.0)
    m = feat.copy()
    m["p_market"] = 0.5
    folds = g.make_folds(feat, m)
    assert len(folds) >= 3
    for fo in folds:
        test_dates = m.loc[fo["test_mask"], "date"]
        train_dates = feat.loc[fo["train_mask"], "date"]
        if len(test_dates) and len(train_dates):
            assert train_dates.max() < test_dates.min()


def test_artifact_schema():
    rep = g.run()
    assert rep["status"] == "ok"
    assert rep["edge_claimed"] is False
    for key in ("features", "folds", "overall", "per_tour", "vs_elo_platt", "verdict",
                "top10_gain_features", "honest_note", "hyperparam_selection_note"):
        assert key in rep, key
    assert len(rep["features"]) == len(g._FEATURES)
    assert set(rep["per_tour"]) == {"atp", "wta"}
    assert len(rep["top10_gain_features"]) <= 10
    for section in (rep["overall"], rep["per_tour"]["atp"], rep["per_tour"]["wta"]):
        assert section["verdict"].split(":")[0] in ("SHARPER", "MATCHES", "TRAILS")


def test_deterministic_seed():
    matches = _toy_matches(n=150)
    asof_hold = _toy_asof_hold(matches)
    feat = g.build_features(matches, asof_hold, is_wta=0.0)
    params = {"max_depth": 2, "n_estimators": 50}
    m1, _ = g._fit(feat[g._FEATURES], feat["p1_win"], params, seed=7)
    m2, _ = g._fit(feat[g._FEATURES], feat["p1_win"], params, seed=7)
    p1 = m1.predict_proba(feat[g._FEATURES])[:, 1]
    p2 = m2.predict_proba(feat[g._FEATURES])[:, 1]
    np.testing.assert_allclose(p1, p2)
