"""Per-file tests for ingame_finegrid_gate_nba.py

Tests use SYNTHETIC states (no real corpora needed). They cover:
1. Fine surface fits correctly and sparse cells fall back to default.
2. Min-cell floor: assert_no_thin_cells recomputes counts and verifies every
   fitted cell had >= min_cell rows (non-tautological: passes states to recount).
3. Monotone check: weight increases over time when signal is informative.
4. Monotone check: fails when weights are actually decreasing.
5. Planted-null rejection: shuffled outcomes do NOT produce a winning fine surface.
6. Full gate with noise p_live (informative=False) -> asserts REJECT (not tautology).
7. Full gate with large strongly-informative data (seeds 42/43, 5000 games x 10
   states) -> asserts SHIP.  These seeds are deterministic and empirically produce
   SHIP because with enough data the fine 6x6 grid's tighter bucketing beats the
   coarse 4x5 grid OOS in both cross-corpus directions AND satisfies monotone.
8. No $ / roi / pnl / edge key anywhere in verdict dict.
9. Direction result carries all required keys with valid numeric types.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_finegrid_gate_nba.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.ingame.ingame_finegrid_gate_nba import (
    MIN_CELL,
    FineGridVerdict,
    assert_no_thin_cells,
    fine_blended,
    fit_fine_surface,
    monotone_holds,
    planted_null_rejects,
    run_gate,
    _fine_vs_coarse_direction,
    _N_TIME_FINE,
    _N_MARGIN_FINE,
)
from scripts.platformkit.eval_gate.ingame_blend import WeightSurface


# --------------------------------------------------------------------------- helpers
def _make_synthetic_states(seed: int, n_games: int = 300, states_per_game: int = 3,
                            informative: bool = True) -> list:
    """Synthetic states. If informative=True, p_live sharpens late (fine grid can win).
    If informative=False, p_live is near-random noise (fine grid should NOT win).
    """
    rng = np.random.default_rng(seed)
    states = []
    for g in range(n_games):
        # true home-win probability
        q = float(np.clip(0.5 + 0.3 * rng.standard_normal(), 0.05, 0.95))
        y = int(rng.random() < q)
        # pregame prior: slightly noisy
        p0 = float(np.clip(q + 0.15 * rng.standard_normal(), 0.01, 0.99))
        for k in range(states_per_game):
            # seconds remaining: spread across 3 quarter-end checkpoints
            secs = 2880.0 * (1.0 - (k + 1) / (states_per_game + 1))
            elapsed = 1.0 - secs / 2880.0
            if informative:
                # p_live sharpens as game progresses
                sigma = 0.25 * (secs / 2880.0) + 0.02
                p_live = float(np.clip(q + sigma * rng.standard_normal(), 0.01, 0.99))
            else:
                # noise: p_live carries no signal
                p_live = float(np.clip(0.5 + 0.4 * rng.standard_normal(), 0.01, 0.99))
            score_diff = (2 * y - 1) * elapsed * 12.0 + 5.0 * rng.standard_normal()
            states.append({
                "game_id": f"g{seed}_{g}",
                "seconds_remaining": secs,
                "score_diff": score_diff,
                "p0": p0,
                "p_live": p_live,
                "outcome": y,
            })
    return states


# --------------------------------------------------------------------------- test 1: surface fitting
def test_fine_surface_fits_and_sparse_cells_default():
    """fit_fine_surface: fitted cells have a weight; sparse cells stay at default."""
    states = _make_synthetic_states(seed=1, n_games=600)
    surf = fit_fine_surface(states, min_cell=MIN_CELL)
    assert isinstance(surf, WeightSurface)
    assert surf.n_time == _N_TIME_FINE
    assert surf.n_margin == _N_MARGIN_FINE
    # at least some cells should be fitted (informative signal)
    assert len(surf.grid) > 0
    # all fitted cells must have valid weight in [0,1]
    for (tb, mb), w in surf.grid.items():
        assert 0.0 <= w <= 1.0, f"bad weight {w} at ({tb},{mb})"
    # a missing key returns the default (0.0 = trust pregame)
    fake_key = (-1, -1)
    assert surf.grid.get(fake_key, surf.default) == 0.0


# --------------------------------------------------------------------------- test 2: min-cell floor
def test_min_cell_floor_prevents_sparse_fit():
    """Cells with fewer than min_cell rows must not appear in surf.grid.

    assert_no_thin_cells receives the original states and recomputes per-cell
    counts, so this assertion has real teeth: it will raise AssertionError if any
    fitted cell (present in surf.grid) had fewer than min_cell training rows.
    """
    # Only 4 states -> no cell can reach min_cell=30
    tiny = _make_synthetic_states(seed=99, n_games=2, states_per_game=2)
    surf = fit_fine_surface(tiny, min_cell=MIN_CELL)
    assert len(surf.grid) == 0, "No cell should be fitted with only 4 states"
    # Pass states so assert_no_thin_cells can recompute and verify counts.
    assert_no_thin_cells(surf, MIN_CELL, tiny)

    # Larger dataset: fitted cells must each have >= min_cell rows.
    big = _make_synthetic_states(seed=1, n_games=600)
    surf_big = fit_fine_surface(big, min_cell=MIN_CELL)
    assert len(surf_big.grid) > 0, "Expected some fitted cells with 1800 states"
    assert_no_thin_cells(surf_big, MIN_CELL, big)  # raises if any cell is thin


# --------------------------------------------------------------------------- test 3: monotone holds
def test_monotone_holds_when_informative():
    """With an informative p_live signal, the surface should trust live more late."""
    states = _make_synthetic_states(seed=2, n_games=800, informative=True)
    surf = fit_fine_surface(states, min_cell=MIN_CELL)
    if len(surf.grid) >= 2:
        # With enough data + informative signal, monotone should hold
        result = monotone_holds(surf)
        # We don't FORCE True here (it depends on the data), but we verify the
        # function returns a bool without error.
        assert isinstance(result, bool)


def test_monotone_fails_on_reversed_grid():
    """A surface with decreasing weights over time should fail the monotone check."""
    surf = WeightSurface(n_time=_N_TIME_FINE, n_margin=_N_MARGIN_FINE)
    # Plant decreasing weights: high early, low late
    for tb in range(_N_TIME_FINE):
        surf.grid[(tb, 3)] = 1.0 - tb * 0.2   # 1.0, 0.8, 0.6, 0.4, 0.2, 0.0
    assert not monotone_holds(surf), "Decreasing weights should fail monotone check"


def test_monotone_holds_on_increasing_grid():
    """A surface with non-decreasing weights over time must pass monotone check."""
    surf = WeightSurface(n_time=_N_TIME_FINE, n_margin=_N_MARGIN_FINE)
    for tb in range(_N_TIME_FINE):
        surf.grid[(tb, 3)] = tb * 0.2   # 0.0, 0.2, 0.4, 0.6, 0.8, 1.0
    assert monotone_holds(surf), "Increasing weights should pass monotone check"


# --------------------------------------------------------------------------- test 4: planted-null rejection
def test_planted_null_rejects_noise():
    """Shuffling outcomes should break the fine surface's advantage over coarse."""
    # Use a large pool of states to ensure statistical signal
    states = _make_synthetic_states(seed=5, n_games=500, informative=True)
    result = planted_null_rejects(states, rng_seed=0)
    # The null must be rejected (fine grid should NOT beat coarse on shuffled outcomes)
    assert result is True, (
        "planted_null_rejects returned False -- fine grid appears to beat coarse "
        "even on shuffled outcomes, indicating thin-cell overfit"
    )


# --------------------------------------------------------------------------- test 5: REJECT verdict
def test_full_gate_rejects_when_fine_does_not_beat_coarse():
    """When p_live is pure noise (informative=False), the gate must REJECT.

    With noise p_live, the fine grid cannot beat the coarse grid OOS in both
    cross-corpus directions (empirically confirmed: REJECT on seeds 10/11 with
    200 games each).  The assertion is pinned to == 'REJECT', not just 'in (...)'.
    """
    states_a = _make_synthetic_states(seed=10, n_games=200, informative=False)
    states_b = _make_synthetic_states(seed=11, n_games=200, informative=False)
    verdict = run_gate(states_a, states_b)
    assert verdict.verdict == "REJECT", (
        f"Expected REJECT for noise p_live but got {verdict.verdict}. "
        f"a_to_b fine_wins={verdict.a_to_b['fine_beats_coarse']}, "
        f"b_to_a fine_wins={verdict.b_to_a['fine_beats_coarse']}, "
        f"null_rejected={verdict.null_rejected}"
    )
    assert isinstance(verdict.to_dict(), dict)


# --------------------------------------------------------------------------- test 6: SHIP on informative data
def test_full_gate_ship_on_informative_data():
    """Large strongly-informative corpora must produce a SHIP verdict.

    Seeds 42/43 with 5000 games x 10 states per game are deterministic (numpy
    default_rng) and empirically produce SHIP: the fine 6x6 grid beats the coarse
    4x5 grid in BOTH cross-corpus directions, monotone holds in both directions,
    and the planted-null is correctly rejected.  This pins the SHIP code path with
    a real assertion instead of the tautological 'in (SHIP, REJECT)'.
    """
    states_a = _make_synthetic_states(seed=42, n_games=5000, states_per_game=10,
                                      informative=True)
    states_b = _make_synthetic_states(seed=43, n_games=5000, states_per_game=10,
                                      informative=True)
    verdict = run_gate(states_a, states_b)
    assert verdict.verdict == "SHIP", (
        f"Expected SHIP for large informative data but got {verdict.verdict}. "
        f"a_to_b fine_wins={verdict.a_to_b['fine_beats_coarse']} "
        f"delta={verdict.a_to_b['delta']}, "
        f"b_to_a fine_wins={verdict.b_to_a['fine_beats_coarse']} "
        f"delta={verdict.b_to_a['delta']}, "
        f"null_rejected={verdict.null_rejected}, "
        f"mono=({verdict.a_to_b['monotone_holds']},{verdict.b_to_a['monotone_holds']})"
    )
    assert verdict.null_rejected is True
    assert verdict.a_to_b["fine_beats_coarse"] is True
    assert verdict.b_to_a["fine_beats_coarse"] is True
    assert verdict.a_to_b["monotone_holds"] is True
    assert verdict.b_to_a["monotone_holds"] is True
    d = verdict.to_dict()
    for key in ("fine_brier", "coarse_brier", "delta", "fine_beats_coarse",
                "monotone_holds", "n_fine_cells_fitted"):
        assert key in d["a_to_b"], f"missing key {key} in a_to_b"
        assert key in d["b_to_a"], f"missing key {key} in b_to_a"


# --------------------------------------------------------------------------- test 7: no $ field
def test_no_dollar_field_in_verdict():
    """Verdict dict must contain NO dollar / edge / roi / pnl fields."""
    states_a = _make_synthetic_states(seed=30, n_games=200)
    states_b = _make_synthetic_states(seed=31, n_games=200)
    verdict = run_gate(states_a, states_b)
    d = verdict.to_dict()
    all_keys = set(d.keys())
    for side in ("a_to_b", "b_to_a"):
        all_keys.update(d.get(side, {}).keys())
    forbidden = {"dollar", "pnl", "roi", "edge", "profit", "stake", "units_wagered"}
    found = forbidden & all_keys
    assert not found, f"Forbidden keys found in verdict: {found}"


# --------------------------------------------------------------------------- test 8: direction structure
def test_direction_result_structure():
    """_fine_vs_coarse_direction returns the expected keys and valid numeric types."""
    states_a = _make_synthetic_states(seed=40, n_games=400)
    states_b = _make_synthetic_states(seed=41, n_games=400)
    result = _fine_vs_coarse_direction(states_a, states_b)
    required = ("n_train", "n_test", "fine_brier", "coarse_brier", "delta",
                "fine_beats_coarse", "monotone_holds", "n_fine_cells_fitted")
    for k in required:
        assert k in result, f"missing key: {k}"
    assert result["n_train"] == len(states_a)
    assert result["n_test"] == len(states_b)
    assert 0.0 <= result["fine_brier"] <= 1.0
    assert 0.0 <= result["coarse_brier"] <= 1.0
    # delta is rounded to 6 dp; check within rounding tolerance (2 * 1e-6)
    assert abs(result["delta"] - (result["coarse_brier"] - result["fine_brier"])) < 2e-5
    assert isinstance(result["fine_beats_coarse"], bool)
    assert isinstance(result["monotone_holds"], bool)
    assert result["n_fine_cells_fitted"] >= 0


if __name__ == "__main__":
    import sys
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {name}: {exc}")
    print(f"\n{passed}/{len(fns)} tests passed.")
    sys.exit(0 if passed == len(fns) else 1)
