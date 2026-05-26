"""tests/test_probe_R12_F3_cross_stat_covariance.py

Two tests:
  1. Leakage audit -- the target stat's own xstat_z_<stat> column is excluded
     from feature_names_for_stat(stat) for ALL stats.
  2. Regression smoke test -- compute_xstat_z_matrix builds a per-row mean of
     PRIOR z-residuals only (strict shift(1)), with no information about the
     current row leaking into its feature vector.
"""
from __future__ import annotations

import importlib
import os
import sys

import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

probe = importlib.import_module("probe_R12_F3_cross_stat_covariance")


def test_leakage_audit_each_stat_excludes_own_z():
    """For each target stat, feature_names_for_stat must NOT contain xstat_z_<stat>."""
    for stat in probe.STATS:
        names = probe.feature_names_for_stat(stat)
        own = f"xstat_z_{stat}"
        assert own not in names, (
            f"feature_names_for_stat({stat!r}) leaks target z column {own}"
        )
        # And exactly 6 cross-stat z features are present.
        xstat_present = [n for n in names if n.startswith("xstat_z_")]
        assert len(xstat_present) == len(probe.STATS) - 1, (
            f"expected {len(probe.STATS) - 1} xstat_z features for {stat}, "
            f"got {xstat_present}"
        )
        # And the n_prior_xstat coverage signal is present.
        assert "n_prior_xstat" in names, "missing n_prior_xstat coverage feature"
        # And assert_leakage_clean must not raise.
        probe.assert_leakage_clean(stat, names)


def test_assert_leakage_clean_raises_on_violation():
    """assert_leakage_clean must hard-fail if own z slips into the feature list."""
    bad_names = list(probe.feature_names_for_stat("pts")) + ["xstat_z_pts"]
    with pytest.raises(AssertionError, match="LEAKAGE"):
        probe.assert_leakage_clean("pts", bad_names)


def test_compute_xstat_z_matrix_shift1_is_strict():
    """Build a tiny synthetic OOF parquet and verify shift(1) discipline:

    A player with 3 games has xstat_z_<stat>:
      - game 1: 0.0 (no prior)
      - game 2: z1 only (prior=[game 1])
      - game 3: mean(z1, z2) (prior=[game 1, game 2])

    The CURRENT game's own residual NEVER appears in its own xstat_z value.
    """
    pid = 999_999
    rows = []
    # Fabricate 3 consecutive games for one player, all 7 stats.
    base_date = pd.Timestamp("2024-01-01")
    for game_idx, (gid, date_off, actual_off, pred_off) in enumerate(
        [("G1", 0, 10.0, 5.0),  # residual = 5
         ("G2", 1, 20.0, 5.0),  # residual = 15
         ("G3", 2, 0.0,  5.0)]  # residual = -5
    ):
        for stat in probe.STATS:
            rows.append({
                "player_id": pid,
                "game_id":   gid,
                "game_date": (base_date + pd.Timedelta(days=date_off)).strftime("%Y-%m-%d"),
                "stat":      stat,
                "oof_pred":  float(pred_off),
                "actual":    float(actual_off),
                "fold":      1,
                "season":    "",
            })
    df = pd.DataFrame(rows)
    xstat_df, sigmas = probe.compute_xstat_z_matrix(df)

    assert set(xstat_df["game_id"]) == {"G1", "G2", "G3"}
    # All seven sigmas must be > 0 (positive scale).
    for s in probe.STATS:
        assert sigmas[s] > 0.0

    g1 = xstat_df[xstat_df["game_id"] == "G1"].iloc[0]
    g2 = xstat_df[xstat_df["game_id"] == "G2"].iloc[0]
    g3 = xstat_df[xstat_df["game_id"] == "G3"].iloc[0]

    # Game 1 has no prior -> z columns are 0.0 (filled).
    for s in probe.STATS:
        assert g1[f"xstat_z_{s}"] == 0.0, (
            f"G1 must have zero-fill prior, got {g1[f'xstat_z_{s}']}"
        )
    assert g1["n_prior_xstat"] == 0.0

    # Game 2's xstat_z_<s> must equal G1's z-residual (single prior).
    for s in probe.STATS:
        z1 = (10.0 - 5.0) / sigmas[s]
        assert g2[f"xstat_z_{s}"] == pytest.approx(z1, rel=1e-5), (
            f"G2 xstat_z_{s} expected {z1}, got {g2[f'xstat_z_{s}']}"
        )
    assert g2["n_prior_xstat"] == 1.0

    # Game 3's xstat_z_<s> must equal the mean of G1 and G2 residuals.
    for s in probe.STATS:
        z1 = (10.0 - 5.0) / sigmas[s]
        z2 = (20.0 - 5.0) / sigmas[s]
        expected = (z1 + z2) / 2.0
        assert g3[f"xstat_z_{s}"] == pytest.approx(expected, rel=1e-5), (
            f"G3 xstat_z_{s} expected {expected}, got {g3[f'xstat_z_{s}']}"
        )
    assert g3["n_prior_xstat"] == 2.0


def test_apply_xstat_residual_correction_runs_end_to_end():
    """Smoke test the live-engine wiring entry point.

    With XSTAT artifacts present and OOF parquet available, calling
    apply_xstat_residual_correction must:
      1. Return a dict (not mutate caller).
      2. Leave non-shipping stats (pts/reb/ast) UNCHANGED.
      3. Adjust at least one of the shipping stats (fg3m/stl/blk/tov)
         away from the input projection (modulo edge cases where the
         head emits 0 for a given player).
    """
    from src.prediction.residual_heads import (
        XSTAT_SHIP_STATS,
        apply_xstat_residual_correction,
        load_xstat_heads,
    )

    heads = load_xstat_heads()
    if not heads:
        pytest.skip("xstat heads not present in this environment")

    snap = {
        "game_date": "2024-12-15",
        "players": [
            {
                "player_id": 1630560,
                "pts": 12, "reb": 4, "ast": 2, "fg3m": 1,
                "stl": 0,  "blk": 1, "tov": 1, "pf": 2, "min": 28,
            },
        ],
    }
    projs = {
        (1630560, "pts"):  22.0,
        (1630560, "reb"):  8.0,
        (1630560, "ast"):  3.0,
        (1630560, "fg3m"): 1.8,
        (1630560, "stl"):  0.9,
        (1630560, "blk"):  1.4,
        (1630560, "tov"):  1.5,
    }
    out = apply_xstat_residual_correction(snap, projs)

    assert isinstance(out, dict)
    # Non-shipping stats are unchanged.
    for stat in ("pts", "reb", "ast"):
        assert out[(1630560, stat)] == projs[(1630560, stat)], (
            f"non-shipping stat {stat} should be unchanged"
        )
    # Shipping stats may be adjusted; at least one must move (heads are
    # non-trivial when L5 z residuals are non-zero, which they will be for
    # any player with prior OOF history).
    moved = sum(
        1 for stat in XSTAT_SHIP_STATS
        if abs(out[(1630560, stat)] - projs[(1630560, stat)]) > 1e-6
    )
    assert moved >= 1, (
        "expected at least one shipping stat to be adjusted by the xstat "
        f"residual heads, got 0 changes (out={out})"
    )


def test_apply_xstat_residual_correction_excludes_own_z_at_inference():
    """Smoke: the live inference path never feeds the target stat's own z."""
    from src.prediction.residual_heads import _xstat_feature_names_for, STATS
    for stat in STATS:
        if stat not in {"fg3m", "stl", "blk", "tov"}:
            continue  # Non-shipping stats have no inference call.
        names = _xstat_feature_names_for(stat)
        own = f"xstat_z_{stat}"
        assert own not in names, (
            f"inference path for {stat} leaks own z column {own}"
        )


def test_target_stat_z_never_used_in_own_residual_head_vector():
    """compute_xstat_z_matrix produces all 7 z columns, but the per-stat
    feature_names_for_stat MASKS the target stat's own z. Verify a synthetic
    feature dict path drops xstat_z_<target>."""
    # Distinct sentinel values per stat so we can search for them in the vector.
    row = {f"xstat_z_{s}": float((i + 1) * 13) for i, s in enumerate(probe.STATS)}
    row["n_prior_xstat"] = 9.0

    for stat in probe.STATS:
        names = probe.feature_names_for_stat(stat)
        vec = probe._row_to_feature_vec(row, names)
        target_z_value = row[f"xstat_z_{stat}"]
        assert target_z_value not in vec, (
            f"target z value {target_z_value} for stat {stat} appears in the "
            f"encoded feature vector {vec}"
        )
