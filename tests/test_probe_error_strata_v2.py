"""Tests for scripts/probe_error_strata_v2.py (cycle 93d, loop 5).

Verifies that:
  1. Stratification produces consistent (axis, bucket, stat) bin counts.
  2. Per-bin MAE / bias are computed correctly on a synthetic 100-row fixture.
  3. Top-5 hardest strata are sorted by mae_delta descending.

These tests do NOT load the real holdout — they use a deterministic synthetic
fixture so the test runs in <1s and is reproducible regardless of dataset state.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.probe_error_strata_v2 as v2  # noqa: E402


# ── synthetic fixture ────────────────────────────────────────────────────────

def _synthetic_holdout(n: int = 100):
    """Build n rows with deterministic target_<stat> and predictable feature
    values. Two PTS-target groups: 50 with low MIN (l10_min=15, target_pts=10)
    and 50 with high MIN (l10_min=35, target_pts=25). Predictions are 5 above
    target in both groups → both groups have MAE=5 globally but different bins.
    """
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n):
        l10 = 15.0 if i < n // 2 else 35.0
        target_pts = 10.0 if i < n // 2 else 25.0
        # Inject a tiny per-row variance so bin MAEs differ from each other.
        jitter = float(rng.normal(0, 0.5))
        rows.append({
            "l10_min":       l10,
            "rest_days":     2.0,
            "opp_def_pts":   1.0,
            "target_pts":    target_pts + jitter,
            # other stats nan target → skipped
            "target_reb":    None,
            "target_ast":    None,
            "target_fg3m":   None,
            "target_stl":    None,
            "target_blk":    None,
            "target_tov":    None,
        })
    return rows


def _synthetic_preds(rows):
    """Predict target + 5 for PTS (systematic overprediction).
    Other stats absent.
    """
    pts = np.array([float(r["target_pts"]) + 5.0 for r in rows], dtype=float)
    return {"pts": pts}


# ── test 1: stratification bin counts ────────────────────────────────────────

def test_stratification_bin_counts_consistent():
    """Each bin's n must equal the count of rows that fall in [lo, hi)."""
    rows = _synthetic_holdout(100)
    preds = _synthetic_preds(rows)

    out = v2.compute_strata_table(
        rows, preds,
        feature_fn=lambda r: float(r["l10_min"]),
        bucket_edges=[0, 20, 40],
        bucket_labels=["low_min", "high_min"],
        axis_label="l10_min",
        min_bin_n=10,  # synthetic is small
    )

    # PTS only (other stats missing from preds)
    by_bucket = {r["bucket"]: r for r in out if r["stat"] == "pts"}
    assert "low_min" in by_bucket
    assert "high_min" in by_bucket
    assert by_bucket["low_min"]["n"] == 50
    assert by_bucket["high_min"]["n"] == 50


# ── test 2: per-bin MAE + bias correctness ───────────────────────────────────

def test_per_bin_mae_and_bias_correct_on_synthetic():
    """Predictions = target + 5 → expected MAE = 5, bias = +5 in every bucket
    (modulo the per-row 0.5-stddev jitter, which averages out across 50 rows)."""
    rows = _synthetic_holdout(100)
    preds = _synthetic_preds(rows)

    out = v2.compute_strata_table(
        rows, preds,
        feature_fn=lambda r: float(r["l10_min"]),
        bucket_edges=[0, 20, 40],
        bucket_labels=["low_min", "high_min"],
        axis_label="l10_min",
        min_bin_n=10,
    )
    pts_rows = [r for r in out if r["stat"] == "pts"]

    # Both buckets: prediction is +5 over target by construction
    # (no jitter in pred — jitter only on target). Actually: pred = target+5
    # where target has jitter. So |pred - target| = 5 EXACTLY (the +5 offset).
    # And signed (pred - target) = +5 exactly.
    for r in pts_rows:
        assert r["mae"] == pytest.approx(5.0, abs=1e-6), (
            f"bucket {r['bucket']} mae={r['mae']}"
        )
        assert r["bias"] == pytest.approx(5.0, abs=1e-6), (
            f"bucket {r['bucket']} bias={r['bias']}"
        )

    # Global MAE matches
    gmae = v2.global_mae(rows, preds)
    assert gmae["pts"] == pytest.approx(5.0, abs=1e-6)


# ── test 3: top-K hardest sorted descending ──────────────────────────────────

def test_top_k_hardest_sorted_descending():
    """rank_hardest must return rows with mae_delta in descending order;
    top_k_per_stat must return at most K rows per stat, all from the front."""
    # Build a synthetic strata-rows list with known mae_deltas.
    gmae = {"pts": 4.0, "reb": 2.0}
    fake_rows = [
        {"axis": "ax_a", "bucket": "b1", "stat": "pts", "n": 100, "mae": 7.0, "bias": 0.0},  # delta +3
        {"axis": "ax_a", "bucket": "b2", "stat": "pts", "n": 100, "mae": 4.5, "bias": 0.0},  # delta +0.5
        {"axis": "ax_b", "bucket": "b1", "stat": "pts", "n": 100, "mae": 5.5, "bias": 0.0},  # delta +1.5
        {"axis": "ax_b", "bucket": "b2", "stat": "pts", "n": 100, "mae": 6.5, "bias": 0.0},  # delta +2.5
        {"axis": "ax_c", "bucket": "b1", "stat": "pts", "n": 100, "mae": 5.0, "bias": 0.0},  # delta +1.0
        {"axis": "ax_c", "bucket": "b2", "stat": "pts", "n": 100, "mae": 4.2, "bias": 0.0},  # delta +0.2
        {"axis": "ax_a", "bucket": "b1", "stat": "reb", "n": 100, "mae": 3.5, "bias": 0.0},  # delta +1.5
        {"axis": "ax_a", "bucket": "b2", "stat": "reb", "n": 100, "mae": 2.5, "bias": 0.0},  # delta +0.5
    ]
    sorted_rows = v2.rank_hardest(list(fake_rows), gmae)

    # Verify descending mae_delta
    deltas = [r["mae_delta"] for r in sorted_rows]
    assert deltas == sorted(deltas, reverse=True), (
        f"rank_hardest order not descending: {deltas}"
    )

    # Verify the #1 hardest for PTS is the +3 delta row
    pts_first = next(r for r in sorted_rows if r["stat"] == "pts")
    assert pts_first["mae_delta"] == pytest.approx(3.0)
    assert pts_first["axis"] == "ax_a" and pts_first["bucket"] == "b1"

    # Top-5 per stat: PTS has 6 candidates → exactly 5 retained; REB has 2 → both retained.
    top5 = v2.top_k_per_stat(sorted_rows, k=5)
    assert len(top5["pts"]) == 5
    assert len(top5["reb"]) == 2
    # Top-5 PTS deltas are the 5 largest of the 6.
    pts_deltas = [r["mae_delta"] for r in top5["pts"]]
    assert pts_deltas == sorted(pts_deltas, reverse=True)
    assert pts_deltas[0] == pytest.approx(3.0)
    # The smallest (0.2 delta) must be dropped.
    assert min(pts_deltas) > 0.2
