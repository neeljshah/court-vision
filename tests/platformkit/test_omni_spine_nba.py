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
