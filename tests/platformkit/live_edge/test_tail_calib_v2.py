"""Per-file test for tail_calib_v2 (parametric-tail fix for v1's
clip-beyond-anchors artifact). Synthetic fixture only -- no parquet I/O."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.live_edge.tail_calib import calib as tc
from scripts.platformkit.live_edge.tail_calib import calib_v2 as cv2


def _synthetic_box(n_disc=400, n_reserve=150, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_disc):
        base = rng.normal(15, 4)
        pts = base + (30 if rng.random() < 0.03 else 0)
        rows.append({"season": "2024-25", "player_id": "A", "pts": max(pts, 0), "min": 30})
    for i in range(n_reserve):
        base = rng.normal(15, 4)
        pts = base + (30 if rng.random() < 0.03 else 0)
        rows.append({"season": "2025-26", "player_id": "A", "pts": max(pts, 0), "min": 30})
    return pd.DataFrame(rows)


def _metrics_a():
    df = _synthetic_box()
    disc = df[df["season"] == "2024-25"]
    return tc.fit_predictors(disc, "player_id", "pts")["A"], df


def test_v2_ppf_matches_v1_inside_anchors():
    m, _ = _metrics_a()
    for q in (0.10, 0.25, 0.5, 0.75, 0.90):
        assert abs(cv2.tail_aware_v2_ppf(q, m["quantiles"]) -
                   tc.tail_aware_ppf(q, m["quantiles"])) < 1e-9


def test_v2_ppf_extrapolates_beyond_v1_flat_clip():
    m, _ = _metrics_a()
    v1_top = tc.tail_aware_ppf(0.999, m["quantiles"])   # v1: flat-clipped == 99.5% anchor
    v2_top = cv2.tail_aware_v2_ppf(0.999, m["quantiles"])
    anchor_995 = m["quantiles"]["0.995"]
    assert abs(v1_top - anchor_995) < 1e-9
    assert v2_top > anchor_995  # v2 extrapolates further out, not pinned


def test_v2_ppf_open_ends_are_infinite():
    m, _ = _metrics_a()
    assert cv2.tail_aware_v2_ppf(1.0, m["quantiles"]) == float("inf")
    assert cv2.tail_aware_v2_ppf(0.0, m["quantiles"]) == float("-inf")


def test_v2_ppf_monotonic_across_full_range():
    m, _ = _metrics_a()
    qs = [0.0001, 0.005, 0.05, 0.5, 0.95, 0.995, 0.9999]
    vals = [cv2.tail_aware_v2_ppf(q, m["quantiles"]) for q in qs]
    assert all(a < b for a, b in zip(vals, vals[1:]))


def test_v2_cdf_no_pileup_beyond_anchor():
    m, _ = _metrics_a()
    hi_anchor = m["quantiles"]["0.995"]
    x_far = hi_anchor + 50  # well beyond the empirical anchor
    pit_v1 = tc.tail_aware_cdf(x_far, m["quantiles"])
    pit_v2 = cv2.tail_aware_v2_cdf(x_far, m["quantiles"])
    assert abs(pit_v1 - 0.995) < 1e-9   # v1 pins at the anchor (the artifact)
    assert pit_v2 > pit_v1              # v2 spreads mass further toward 1.0


def test_v2_cdf_roundtrips_ppf_beyond_anchor():
    m, _ = _metrics_a()
    x = cv2.tail_aware_v2_ppf(0.999, m["quantiles"])
    q_back = cv2.tail_aware_v2_cdf(x, m["quantiles"])
    assert abs(q_back - 0.999) < 1e-6


def test_evaluate_reserve_3way_shape():
    m, df = _metrics_a()
    disc, reserve = df[df["season"] == "2024-25"], df[df["season"] == "2025-26"]
    metrics = tc.fit_predictors(disc, "player_id", "pts")
    row_eval = cv2.evaluate_reserve_3way(reserve, metrics, "player_id", "pts")
    assert len(row_eval) > 0
    for p in ("baseline", "tail_v1", "tail_v2"):
        assert row_eval[f"pit_{p}"].between(0, 1).all()


def test_coverage_table_3way_bounds():
    m, df = _metrics_a()
    disc, reserve = df[df["season"] == "2024-25"], df[df["season"] == "2025-26"]
    metrics = tc.fit_predictors(disc, "player_id", "pts")
    cov = cv2.coverage_table_3way(reserve, metrics, "player_id", "pts")
    assert list(cov["nominal"]) == cv2.COVERAGE_LEVELS
    for p in ("baseline", "tail_v1", "tail_v2"):
        assert cov[f"realized_{p}"].between(0, 1).all()


def test_tail_bin_check_3way_top_bin_nonzero_when_extreme_values_present():
    m, df = _metrics_a()
    disc, reserve = df[df["season"] == "2024-25"], df[df["season"] == "2025-26"]
    metrics = tc.fit_predictors(disc, "player_id", "pts")
    bins_v1 = cv2.tail_bin_check_3way(reserve, metrics, "tail_v1", "player_id", "pts")
    bins_v2 = cv2.tail_bin_check_3way(reserve, metrics, "tail_v2", "player_id", "pts")
    top_v1 = bins_v1[bins_v1["bin"] == "99.5-100%"].iloc[0]
    top_v2 = bins_v2[bins_v2["bin"] == "99.5-100%"].iloc[0]
    # v2's open-ended top bin (hi=+inf) must catch >= as many extreme rows as
    # v1's degenerate pinned bin (v1 structurally undercounts here)
    assert top_v2["realized"] >= top_v1["realized"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
