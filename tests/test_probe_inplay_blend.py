"""tests/test_probe_inplay_blend.py — cycle 95e (loop 5).

Three offline tests for scripts/probe_inplay_blend.py — the multi-snapshot
weighted-blend probe. All tests use synthetic fixtures so they run in <1s.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import probe_inplay_blend as pib  # noqa: E402


# ── 1. Weighted blend computation matches manual calc on a fixture ────────────

def test_weighted_blend_matches_manual_calc():
    """blend_projection(q1=10, q2=20, q3=30, weights=(0.1, 0.3, 0.6))
       == 0.1*10 + 0.3*20 + 0.6*30 = 1 + 6 + 18 = 25.0
    And normalize_weights((0.1, 0.3, 0.6)) is already sum=1 so blend is
    a pure dot product."""
    out = pib.blend_projection(10.0, 20.0, 30.0, (0.1, 0.3, 0.6))
    assert abs(out - 25.0) < 1e-9, f"expected 25.0, got {out}"

    # Equal Q2+Q3 blend with Q1 dropped (weight 0).
    out2 = pib.blend_projection(99.0, 10.0, 20.0, (0.0, 0.5, 0.5))
    assert abs(out2 - 15.0) < 1e-9, f"expected 15.0, got {out2}"

    # Renormalization on missing snapshot: q1 None drops, q2/q3 split.
    out3 = pib.blend_projection(None, 10.0, 20.0, (0.5, 0.25, 0.25))
    # remaining weights 0.25 + 0.25 = 0.5; (0.25*10 + 0.25*20) / 0.5 = 15.0
    assert abs(out3 - 15.0) < 1e-9, f"expected 15.0, got {out3}"

    # All-None returns None.
    assert pib.blend_projection(None, None, None, (0.3, 0.3, 0.4)) is None


# ── 2. 100% Q3 weights produce same MAE as cycle 94d baseline ────────────────

def test_q3_only_weights_match_cycle94d_baseline():
    """With weights (0,0,1), the blend == Q3 snapshot exactly, so the MAE
    must equal the bare Q3 MAE — i.e. the cycle 94d endQ3 result on the
    same triples."""
    # Synthetic snaps_per_game with 2 games, 1 player, 1 stat each.
    snaps_per_game = {
        "G1": {
            "endQ1": {(101, "pts"): 5.0},
            "endQ2": {(101, "pts"): 12.0},
            "endQ3": {(101, "pts"): 20.0},
        },
        "G2": {
            "endQ1": {(101, "pts"): 8.0},
            "endQ2": {(101, "pts"): 18.0},
            "endQ3": {(101, "pts"): 25.0},
        },
    }
    actuals = {
        "G1": {(101, "pts"): 22.0},   # |20-22| = 2.0
        "G2": {(101, "pts"): 28.0},   # |25-28| = 3.0
    }
    # Q3-only blend.
    blend_mae = pib.compute_blend_mae(
        snaps_per_game, actuals, (0.0, 0.0, 1.0), game_subset=["G1", "G2"],
    )
    assert "pts" in blend_mae
    n, m = blend_mae["pts"]
    assert n == 2
    # MAE = mean(2.0, 3.0) = 2.5
    assert abs(m - 2.5) < 1e-9, f"expected 2.5, got {m}"

    # Normalization invariance: (0,0,5) normalizes to (0,0,1) so MAE identical.
    blend_mae_scaled = pib.compute_blend_mae(
        snaps_per_game, actuals, pib.normalize_weights((0.0, 0.0, 5.0)),
        game_subset=["G1", "G2"],
    )
    assert abs(blend_mae_scaled["pts"][1] - 2.5) < 1e-9


# ── 3. NNLS-derived weights sum to 1.0 and are non-negative ──────────────────

def test_nnls_weights_sum_to_one_and_nonneg():
    """Per-stat NNLS solution must satisfy w_i >= 0 (NNLS gate) and the
    post-normalization step in fit_nnls_weights_per_stat must produce a
    weights-tuple that sums to 1.0 (or 0.0 when under-determined)."""
    # Build a fixture with 12 games, 1 player, 1 stat. Actuals = 1.0*Q3
    # (so NNLS should converge to weights close to (0, 0, 1)). We need
    # >=10 rows per stat or NNLS returns (0,0,0) per the under-determined
    # guard — so 12 games is enough.
    snaps_per_game = {}
    actuals = {}
    fit_games = []
    rng_seed = 0  # deterministic
    for i in range(12):
        gid = f"G{i:02d}"
        fit_games.append(gid)
        # Q3 = i+10, Q2 = (i+10)*0.7, Q1 = (i+10)*0.4 — collinear but ranked.
        q3 = float(i + 10)
        snaps_per_game[gid] = {
            "endQ1": {(101, "pts"): q3 * 0.4},
            "endQ2": {(101, "pts"): q3 * 0.7},
            "endQ3": {(101, "pts"): q3},
        }
        # actual == Q3 exactly => NNLS should weight Q3 strongly.
        actuals[gid] = {(101, "pts"): q3}

    weights = pib.fit_nnls_weights_per_stat(snaps_per_game, actuals, fit_games)
    assert "pts" in weights
    w = weights["pts"]
    # Non-negativity.
    assert all(x >= 0.0 for x in w), f"NNLS weights must be >= 0, got {w}"
    # Sum to 1.0 (or 0.0 if under-determined — but we built 12 rows).
    s = sum(w)
    assert abs(s - 1.0) < 1e-6, f"weights must sum to 1.0, got {s} (w={w})"
    # Q3 should dominate (actual == Q3 by construction; collinearity may
    # spread weight a touch, but Q3 should still be the largest component
    # OR Q3 component should be >= 0.5).
    # NOTE: NNLS on perfectly-collinear A may put all mass on one column —
    # we just assert "some positive mass on Q3 OR Q2" (since Q2 also
    # carries the signal scaled by 0.7).
    assert w[2] > 0 or w[1] > 0, f"expected positive Q3 or Q2 weight, got {w}"


# ── bonus: under-determined stat returns (0,0,0) ──────────────────────────────

def test_nnls_underdetermined_returns_zeros():
    """When a stat has <10 rows, fit_nnls_weights_per_stat returns (0,0,0)
    rather than letting NNLS converge on noise."""
    snaps_per_game = {
        "G1": {
            "endQ1": {(101, "pts"): 1.0},
            "endQ2": {(101, "pts"): 2.0},
            "endQ3": {(101, "pts"): 3.0},
        },
    }
    actuals = {"G1": {(101, "pts"): 3.5}}
    w = pib.fit_nnls_weights_per_stat(snaps_per_game, actuals, ["G1"])
    assert w["pts"] == (0.0, 0.0, 0.0)
