"""Tests for scripts.platformkit.pod_sprint.gbm_nba_enriched."""

import numpy as np
import pandas as pd

from scripts.platformkit.models import gbm_nba_ml as g
from scripts.platformkit.pod_sprint import gbm_nba_enriched as e


def _toy_box(n=80, seed=0):
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


def test_leak_trap_extra_features_ignore_own_game():
    """Row i's 6 enriched features must be identical regardless of game i's own score
    -- only games strictly BEFORE i may influence row i's venue_split/rest_form/
    l10_oppadj. The corrupted game's outcome must, however, shift a LATER row for
    either team (state does update, just not into the game that produced it)."""
    box = _toy_box()
    feat_a = e.build_features(box)
    corrupted = box.copy()
    victim = 40
    corrupted.loc[victim, "home_pts"] = 999.0
    corrupted.loc[victim, "away_pts"] = 1.0
    feat_b = e.build_features(corrupted)

    row_a = feat_a.loc[victim, e.ENRICHED_FEATURES]
    row_b = feat_b.loc[victim, e.ENRICHED_FEATURES]
    pd.testing.assert_series_equal(row_a, row_b)

    ht, at = box.loc[victim, "home_abbr"], box.loc[victim, "away_abbr"]
    later = box.loc[victim + 1:]
    nxt = later[(later["home_abbr"].isin([ht, at])) | (later["away_abbr"].isin([ht, at]))].index[0]
    assert not feat_a.loc[nxt, e.ENRICHED_FEATURES].equals(feat_b.loc[nxt, e.ENRICHED_FEATURES])


def test_extra_features_default_neutral_before_history():
    """A team's very first games (before _MIN_ASOF_N on both sides of each split)
    must read 0.0 -- no history yet, never a divide-by-zero or leaked value."""
    box = _toy_box(n=6)
    feat = e.build_features(box)
    first_row = feat.iloc[0]
    for col in ("venue_split_home", "venue_split_away", "rest_form_home",
                "rest_form_away", "l10_oppadj_home", "l10_oppadj_away"):
        assert first_row[col] == 0.0


def test_build_features_shape_matches_enriched_feature_list():
    box = _toy_box(n=50)
    feat = e.build_features(box)
    assert set(e.ENRICHED_FEATURES) <= set(feat.columns)
    assert len(e.ENRICHED_FEATURES) == len(g._FEATURES) + 6
    assert not feat[e.ENRICHED_FEATURES].isna().any().any()


def test_end_to_end_synthetic_fit_and_select():
    """Tiny synthetic end-to-end: build enriched features, fabricate a market overlap,
    fold it, and fit both the plain and enriched models on a fold -- mirrors run()'s
    inner loop without touching the real corpus or network."""
    box = _toy_box(n=300, seed=1)
    feat = e.build_features(box)
    m = feat.iloc[150:].reset_index(drop=True).copy()
    m["p_market"] = 0.5
    folds = g.make_folds(feat, m, k=4)
    assert len(folds) >= 1

    train_mask, lo, hi = folds[0]
    tr, te = feat.loc[train_mask], m.iloc[lo:hi]
    params = {"max_depth": 2, "n_estimators": 50}
    m_plain, _ = g._fit(tr[g._FEATURES], tr["home_win"], params)
    m_enr, _ = g._fit(tr[e.ENRICHED_FEATURES], tr["home_win"], params)
    p_plain = m_plain.predict_proba(te[g._FEATURES])[:, 1]
    p_enr = m_enr.predict_proba(te[e.ENRICHED_FEATURES])[:, 1]
    assert ((p_plain >= 0) & (p_plain <= 1)).all()
    assert ((p_enr >= 0) & (p_enr <= 1)).all()
    assert len(p_plain) == len(te) == len(p_enr)

    # _select must restore gbm_nba_ml's globals afterward (monkeypatch-and-restore)
    saved_f, saved_g = g._FEATURES, g._GRID
    e._select(feat, train_mask, e.ENRICHED_FEATURES)
    assert g._FEATURES is saved_f and g._GRID is saved_g


def test_real_corpus_artifact_schema():
    """Real-corpus smoke: same shape assertions as gbm_nba_ml's own
    test_artifact_schema, plus the honest-gate keys this module adds."""
    rep = e.run()
    assert rep["status"] == "ok"
    assert rep["edge_claimed"] is False
    for key in ("features", "folds", "brier_enriched", "brier_plain_features", "brier_close",
                "paired_delta_vs_plain_features_mean", "paired_delta_vs_plain_features_95ci",
                "paired_delta_vs_close_mean", "verdict", "verdict_vs_close", "honest_note"):
        assert key in rep, key
    assert len(rep["features"]) == len(e.ENRICHED_FEATURES)
    assert rep["verdict"].split(":")[0] in ("ENRICHED-IMPROVED", "NO-IMPROVEMENT")
