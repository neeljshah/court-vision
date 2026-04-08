"""Smoke tests for spatial_prior."""
import pytest
import pandas as pd
import numpy as np
from src.fusion.spatial_prior import SpatialPrior, _clock_bucket, _score_diff_bucket


def _make_df(n=50):
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "court_zone":        rng.choice(["paint", "mid_range", "3pt_arc"], n),
        "defender_distance": rng.uniform(1.0, 15.0, n),
        "team_spacing":      rng.uniform(5.0, 25.0, n),
        "shot_clock":        rng.uniform(0, 24, n),
        "score_diff":        rng.integers(-20, 21, n),
    })


def test_fit_returns_self():
    p = SpatialPrior(min_samples=2)
    ret = p.fit(_make_df())
    assert ret is p


def test_get_returns_source_value():
    p = SpatialPrior(min_samples=2).fit(_make_df(100))
    sv = p.get("defender_distance", "paint", shot_clock=10.0, score_diff=0)
    if sv is not None:
        assert 0.0 <= sv.confidence <= 0.40
        assert sv.source == "spatial_prior"


def test_unfitted_returns_none():
    p = SpatialPrior()
    assert p.get("defender_distance", "paint", 10.0) is None


def test_global_fallback():
    p = SpatialPrior(min_samples=999).fit(_make_df(50))  # no bucket will have 999
    sv = p.get("defender_distance", "paint", 10.0)
    if sv is not None:
        assert sv.meta["bucket"] == "global"
        assert sv.confidence == 0.25


def test_clock_buckets():
    assert _clock_bucket(4.0)  == "late"
    assert _clock_bucket(12.0) == "mid"
    assert _clock_bucket(20.0) == "early"


def test_score_diff_buckets():
    assert _score_diff_bucket(-15) == "losing_big"
    assert _score_diff_bucket(0)   == "close"
    assert _score_diff_bucket(12)  == "winning_big"


def test_save_load(tmp_path):
    p = SpatialPrior(cache_path=tmp_path / "sp.parquet", min_samples=2)
    p.fit(_make_df(100))
    p.save()
    p2 = SpatialPrior.load(tmp_path / "sp.parquet")
    assert p2._stats is not None
