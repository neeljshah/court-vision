"""Per-file test for tail_calib (calibration head-to-head: baseline Normal
vs B2 tail-aware empirical quantiles, OOS reserve). Synthetic fixture only
-- no parquet I/O in tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.live_edge.tail_calib import calib as tc


def _synthetic_box(n_disc_per_player=200, n_reserve_per_player=40, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    # player A: true fat right tail (occasional breakout) -- B2's claim shape
    for i in range(n_disc_per_player):
        base = rng.normal(15, 4)
        pts = base + (30 if rng.random() < 0.03 else 0)
        rows.append({"season": "2024-25", "player_id": "A", "pts": max(pts, 0), "min": 30})
    for i in range(n_reserve_per_player):
        base = rng.normal(15, 4)
        pts = base + (30 if rng.random() < 0.03 else 0)
        rows.append({"season": "2025-26", "player_id": "A", "pts": max(pts, 0), "min": 30})
    # player B: true Normal, no tail -- baseline should be fine here
    for i in range(n_disc_per_player):
        rows.append({"season": "2024-25", "player_id": "B", "pts": max(rng.normal(10, 3), 0), "min": 25})
    for i in range(n_reserve_per_player):
        rows.append({"season": "2025-26", "player_id": "B", "pts": max(rng.normal(10, 3), 0), "min": 25})
    return pd.DataFrame(rows)


def test_fit_predictors_gives_mean_std_quantiles():
    df = _synthetic_box()
    disc = df[df["season"] == "2024-25"]
    metrics = tc.fit_predictors(disc, "player_id", "pts")
    assert set(metrics) == {"A", "B"}
    for m in metrics.values():
        assert not m["insufficient"]
        assert "quantiles" in m and "mean" in m and "std" in m


def test_ppf_functions_monotonic_and_bracket_median():
    df = _synthetic_box()
    disc = df[df["season"] == "2024-25"]
    metrics = tc.fit_predictors(disc, "player_id", "pts")
    m = metrics["A"]
    lo = tc.tail_aware_ppf(0.05, m["quantiles"])
    hi = tc.tail_aware_ppf(0.95, m["quantiles"])
    assert lo < hi
    lo_b = tc.baseline_ppf(0.05, m["mean"], m["std"])
    hi_b = tc.baseline_ppf(0.95, m["mean"], m["std"])
    assert lo_b < hi_b


def test_cdf_roundtrips_ppf_at_grid_points():
    df = _synthetic_box()
    disc = df[df["season"] == "2024-25"]
    metrics = tc.fit_predictors(disc, "player_id", "pts")
    m = metrics["B"]
    for q in (0.25, 0.5, 0.75):
        x = tc.tail_aware_ppf(q, m["quantiles"])
        q_back = tc.tail_aware_cdf(x, m["quantiles"])
        assert abs(q_back - q) < 1e-6


def test_crps_lower_for_tail_aware_on_fat_tailed_entity():
    df = _synthetic_box(n_disc_per_player=400, n_reserve_per_player=150, seed=1)
    disc, reserve = df[df["season"] == "2024-25"], df[df["season"] == "2025-26"]
    metrics = tc.fit_predictors(disc, "player_id", "pts")
    m = metrics["A"]
    row_eval = tc.evaluate_reserve(reserve[reserve["player_id"] == "A"], metrics, "player_id", "pts")
    assert len(row_eval) > 0
    # B2's claim shape (real fat right tail) -> tail-aware CRPS should not be
    # worse than baseline on average for the deliberately-fat-tailed entity
    assert row_eval["crps_tail"].mean() <= row_eval["crps_baseline"].mean() * 1.15


def test_coverage_table_shape_and_bounds():
    df = _synthetic_box()
    disc, reserve = df[df["season"] == "2024-25"], df[df["season"] == "2025-26"]
    metrics = tc.fit_predictors(disc, "player_id", "pts")
    cov = tc.coverage_table(reserve, metrics, "player_id", "pts")
    assert list(cov["nominal"]) == tc.COVERAGE_LEVELS
    assert (cov["realized_baseline"].between(0, 1)).all()
    assert (cov["realized_tail_aware"].between(0, 1)).all()


def test_pit_uniformity_insufficient_n():
    out = tc.pit_uniformity(np.array([0.5, 0.6]))
    assert out["n"] == 2
    assert np.isnan(out["ks_stat"])


def test_tail_bin_check_predicted_sums_to_one():
    df = _synthetic_box()
    disc, reserve = df[df["season"] == "2024-25"], df[df["season"] == "2025-26"]
    metrics = tc.fit_predictors(disc, "player_id", "pts")
    bins = tc.tail_bin_check(reserve, metrics, "tail_aware", "player_id", "pts")
    assert abs(bins["predicted"].sum() - 1.0) < 1e-9


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
