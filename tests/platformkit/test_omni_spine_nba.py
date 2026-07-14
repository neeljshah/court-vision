"""Per-file tests for scripts.platformkit.omni.spine_nba (P6 next-possession
spine v0). Run: cd /c/Users/neelj/nba-ai-system && python -m pytest
tests/platformkit/test_omni_spine_nba.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.omni import spine_nba as SP


def test_points_to_class_buckets_4plus():
    pts = np.array([0, 1, 2, 3, 4, 5, 6])
    cls = SP.points_to_class(pts)
    assert list(cls) == [0, 1, 2, 3, 4, 4, 4]


def _synthetic_state_df(n=400, seasons=("2024-25", "2025-26")) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n):
        season = seasons[i % len(seasons)]
        rows.append({
            "game_id": f"g{i % 20}", "season": season,
            "period": int(rng.integers(1, 5)),
            "clock_start": float(rng.uniform(0, 720)),
            "off_margin": float(rng.uniform(-20, 20)),
            "home_margin": float(rng.uniform(-20, 20)),
            "time_b": int(rng.integers(0, 6)),
            "margin_b": int(rng.integers(0, 7)),
            "off_t": int(rng.integers(0, 3)),
            "def_t": int(rng.integers(0, 3)),
            "pace_t": int(rng.integers(0, 3)),
            "points": int(rng.choice([0, 1, 2, 3], p=[0.55, 0.05, 0.35, 0.05])),
        })
    return pd.DataFrame(rows)


def test_no_2025_26_in_train():
    """Leak guard: fit_spine_discovery must train on TRAIN_SEASON only."""
    df = _synthetic_state_df()
    _clf, train_df = SP.fit_spine_discovery(df, seed=42)
    assert set(train_df["season"].unique()) == {SP.TRAIN_SEASON}
    assert "2025-26" not in set(train_df["season"].unique())


def test_reproducibility_same_seed():
    df = _synthetic_state_df()
    clf_a, train_a = SP.fit_spine_discovery(df, seed=42)
    clf_b, train_b = SP.fit_spine_discovery(df, seed=42)
    test_df = df[df["season"] == "2025-26"].reset_index(drop=True)
    pa = SP.predict_proba(clf_a, test_df)
    pb = SP.predict_proba(clf_b, test_df)
    np.testing.assert_allclose(pa, pb)


def test_predict_proba_shape_and_normalized():
    df = _synthetic_state_df()
    clf, _train = SP.fit_spine_discovery(df, seed=42)
    test_df = df[df["season"] == "2025-26"].reset_index(drop=True)
    proba = SP.predict_proba(clf, test_df)
    assert proba.shape == (len(test_df), SP.N_CLASSES)
    np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-6)


def test_fit_spine_discovery_raises_on_empty_train():
    df = _synthetic_state_df(seasons=("2025-26",))
    with pytest.raises(ValueError):
        SP.fit_spine_discovery(df, seed=42)


# ---------------------------------------------------------------------------
# v1: team identity + K-asof team-strength (touches real parquets -- cached
# once at module scope so the 3 tests below share a single ~5s build).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def v1_frame() -> pd.DataFrame:
    return SP.build_state_frame_v1()


def test_v1_features_extend_v0(v1_frame):
    assert SP.FEATURES_V1[:len(SP.FEATURES)] == SP.FEATURES
    assert len(SP.FEATURES_V1) == len(SP.FEATURES) + 8
    assert set(SP.FEATURES_V1).issubset(v1_frame.columns)


def test_v1_no_leak_asof_constant_within_team_season(v1_frame):
    """Leak guard: team_offdef_asof is a fixed PRIOR-season value -- it must
    not vary possession-to-possession within the same (team, season). A
    feature that drifts within-season would mean it is (wrongly) reading
    same-season/future games instead of the frozen prior-season constant."""
    g = v1_frame.groupby(["off_team", "season"])["off_asof_off_rtg"].nunique()
    assert (g == 1).all(), "off_asof_off_rtg drifts within a (team, season) -- leak"
    g2 = v1_frame.groupby(["def_team", "season"])["def_asof_def_rtg"].nunique()
    assert (g2 == 1).all(), "def_asof_def_rtg drifts within a (team, season) -- leak"


def test_v1_no_leak_team_identity_consistent_with_home_away(v1_frame):
    """off_team/def_team must never collide (no self-play) and must decode
    to a valid 0..29 tricode index -- catches an off-by-one/self-join bug
    that would otherwise silently leak a team's own asof rating twice."""
    assert (v1_frame["off_team_code"] != v1_frame["def_team_code"]).all()
    assert v1_frame["off_team_code"].between(0, 29).all()
    assert v1_frame["def_team_code"].between(0, 29).all()
    assert (v1_frame["off_team"] != v1_frame["def_team"]).all()


def test_v1_reproducibility_same_seed(v1_frame):
    clf_a, _ = SP.fit_spine_discovery(v1_frame, seed=42, features=SP.FEATURES_V1)
    clf_b, _ = SP.fit_spine_discovery(v1_frame, seed=42, features=SP.FEATURES_V1)
    test_df = v1_frame[v1_frame["season"] == "2025-26"].reset_index(drop=True)
    pa = SP.predict_proba(clf_a, test_df, features=SP.FEATURES_V1)
    pb = SP.predict_proba(clf_b, test_df, features=SP.FEATURES_V1)
    np.testing.assert_allclose(pa, pb)


# ---------------------------------------------------------------------------
# v2: possession-grain lineup-identity rates (2024-25-fitted, fallback ladder)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def v2_frame() -> pd.DataFrame:
    return SP.build_state_frame_v2()


def test_v2_features_extend_v1(v2_frame):
    assert SP.FEATURES_V2[:len(SP.FEATURES_V1)] == SP.FEATURES_V1
    assert len(SP.FEATURES_V2) == len(SP.FEATURES_V1) + 2
    assert set(SP.FEATURES_V2).issubset(v2_frame.columns)
    assert set(v2_frame["off_lineup_tier_v2"].unique()) <= {"lineup", "player", "team"}


def test_v2_lineup_rating_fit_uses_train_season_only(monkeypatch):
    """Leak guard: the lineup/player rating tables must be fit on rows whose
    season == TRAIN_SEASON only -- 2025-26 outcomes must never enter a fit."""
    from scripts.platformkit.omni import lineup_possessions as LP
    seasons_seen = []
    orig_lineup, orig_player = LP.fit_lineup_rates, LP.fit_player_rates

    def _capture_lineup(df, *a, **kw):
        seasons_seen.append(set(df["season"].unique()))
        return orig_lineup(df, *a, **kw)

    def _capture_player(df, *a, **kw):
        seasons_seen.append(set(df["season"].unique()))
        return orig_player(df, *a, **kw)

    monkeypatch.setattr(LP, "fit_lineup_rates", _capture_lineup)
    monkeypatch.setattr(LP, "fit_player_rates", _capture_player)
    SP.build_state_frame_v2()
    assert seasons_seen, "fit functions were never called"
    assert all(s == {SP.TRAIN_SEASON} for s in seasons_seen)


def test_v2_reproducibility_same_seed(v2_frame):
    clf_a, _ = SP.fit_spine_discovery(v2_frame, seed=42, features=SP.FEATURES_V2)
    clf_b, _ = SP.fit_spine_discovery(v2_frame, seed=42, features=SP.FEATURES_V2)
    test_df = v2_frame[v2_frame["season"] == "2025-26"].reset_index(drop=True)
    pa = SP.predict_proba(clf_a, test_df, features=SP.FEATURES_V2)
    pb = SP.predict_proba(clf_b, test_df, features=SP.FEATURES_V2)
    np.testing.assert_allclose(pa, pb)
