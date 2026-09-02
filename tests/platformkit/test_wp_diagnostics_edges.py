"""S42: one bin-edge rule across reliability / ece / decompose.

The defect: wp_diagnostics.reliability binned by min(9, int(p*10)) while
scoring.ece and calib_decomp.decompose bin by numpy edge comparison, so any
artifact publishing a bin table beside a summary ECE disagreed with itself on
predictions landing exactly on the 0.1 grid. Calibration only, no edge claim.

Per file: python -m pytest tests/platformkit/test_wp_diagnostics_edges.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.calib_decomp import bin_edges, bin_index, decompose
from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.wp_diagnostics import reliability

# The whole 0.1 grid plus the closed-interval end points. 0.6 is the member that
# the legacy rule and the numpy edges actually disagree on (0.6*10 is
# 6.000000000000001 while np.linspace(0,1,11)[6] is 0.6000000000000001).
_GRID = [round(0.1 * k, 1) for k in range(11)]


def _ticks(probs, outcomes):
    return [{"game": "g%03d" % i, "model_prob": float(p), "outcome": float(y), "phase": "Q1"}
            for i, (p, y) in enumerate(zip(probs, outcomes))]


def test_shared_edges_are_the_linspace_scoring_and_decompose_use():
    assert np.array_equal(bin_edges(10), np.linspace(0.0, 1.0, 11))
    assert bin_index(1.0, bin_edges(10)) == 9      # last bin closed on both sides
    assert bin_index(0.0, bin_edges(10)) == 0


def test_reliability_bin_counts_match_decompose_bins_detail_on_the_grid():
    probs = [p for p in _GRID for _ in range(30)]
    outcomes = [float(i % 2) for i in range(len(probs))]
    rows = reliability(_ticks(probs, outcomes))
    detail = {round(b["lo"], 6): b["n"] for b in decompose(probs, outcomes)["bins_detail"]}
    for index, row in enumerate(rows):
        if row["n"]:
            assert detail[round(float(bin_edges(10)[index]), 6)] == row["n"], row["bin"]
    assert sum(row["n"] for row in rows) == len(probs)


def test_ece_recomputed_from_the_bin_table_equals_the_summary_ece():
    rng = np.random.default_rng(42)
    probs = list(rng.choice(_GRID, size=400)) + list(rng.uniform(0.0, 1.0, 400))
    outcomes = list((rng.uniform(size=len(probs)) < np.array(probs)).astype(float))
    rows = reliability(_ticks(probs, outcomes))
    n = len(probs)
    from_bins = sum(row["n"] / n * abs(row["observed_win_freq"] - row["mean_predicted_prob"])
                    for row in rows if row["n"])
    assert abs(from_bins - ece(probs, outcomes)) < 1e-12


def test_legacy_bins_flag_still_reproduces_the_pre_s42_assignment():
    probs = [0.6] * 40
    outcomes = [1.0] * 20 + [0.0] * 20
    legacy = reliability(_ticks(probs, outcomes), legacy_bins=True)
    shared = reliability(_ticks(probs, outcomes))
    assert legacy[6]["n"] == 40 and legacy[5]["n"] == 0   # min(9, int(0.6*10)) == 6
    assert shared[5]["n"] == 40 and shared[6]["n"] == 0   # linspace edge 6 > 0.6
