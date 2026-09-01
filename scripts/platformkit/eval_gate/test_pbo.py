"""Synthetic coverage for CSCV probability of backtest overfitting."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate.pbo import (
    build_pred_matrix,
    contiguous_blocks,
    cscv_pbo,
    enumerate_split_indices,
)


def test_contiguous_blocks_covers_every_row_once():
    n_obs = 200
    blocks = contiguous_blocks(n_obs, 16)
    assert sum(len(b) for b in blocks) == n_obs
    seen = np.concatenate(blocks)
    assert list(seen) == list(range(n_obs))  # disjoint, ascending, covers every row
    with pytest.raises(ValueError):
        contiguous_blocks(10, 16)


def test_enumerate_split_indices_is_deterministic_and_capped():
    first = enumerate_split_indices(s_blocks=16, max_splits=1000, seed=2718)
    second = enumerate_split_indices(s_blocks=16, max_splits=1000, seed=2718)
    assert len(first) == 1000
    assert first == second
    small = enumerate_split_indices(s_blocks=4, max_splits=1000, seed=2718)
    assert len(small) == 6  # C(4,2) = 6 < max_splits -> untouched


def _noise_matrix(n_obs=400, n_configs=8, seed=0):
    rng = np.random.default_rng(seed)
    true_rate = 0.5
    outcome = rng.binomial(1, true_rate, size=n_obs)
    pred = np.clip(true_rate + rng.normal(scale=0.15, size=(n_obs, n_configs)), 0.01, 0.99)
    return pred, outcome


def test_pure_noise_configs_give_pbo_near_one_half():
    pred, outcome = _noise_matrix()
    result = cscv_pbo(pred, outcome, s_blocks=16, max_splits=200, seed=2718)
    assert result.n_configs == 8 and result.n_obs == 400
    assert 0.3 <= result.pbo <= 0.7


def test_dominant_config_has_low_pbo():
    pred, outcome = _noise_matrix()
    rng = np.random.default_rng(1)
    pred[:, 0] = np.clip(outcome + rng.normal(scale=0.02, size=len(outcome)), 0.01, 0.99)
    result = cscv_pbo(pred, outcome, s_blocks=16, max_splits=200, seed=2718)
    assert result.pbo < 0.2


def test_cscv_pbo_is_deterministic_for_a_fixed_seed():
    pred, outcome = _noise_matrix()
    first = cscv_pbo(pred, outcome, s_blocks=16, max_splits=200, seed=2718)
    second = cscv_pbo(pred, outcome, s_blocks=16, max_splits=200, seed=2718)
    assert first.pbo == second.pbo
    assert first.is_best_idx == second.is_best_idx


def test_raises_on_single_config_or_shape_mismatch():
    pred, outcome = _noise_matrix(n_configs=1)
    with pytest.raises(ValueError):
        cscv_pbo(pred, outcome)
    pred, outcome = _noise_matrix()
    with pytest.raises(ValueError):
        cscv_pbo(pred, outcome[:-1])


def test_raises_on_too_few_obs_for_blocks():
    pred, outcome = _noise_matrix(n_obs=10, n_configs=3)
    with pytest.raises(ValueError):
        cscv_pbo(pred, outcome, s_blocks=16)


def _frame(n=180):
    rng = np.random.default_rng(7)
    close = np.clip(rng.uniform(.2, .8, n), .05, .95)
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n),
                         "game_id": ["g{0}".format(i) for i in range(n)],
                         "outcome": rng.binomial(1, close), "close_prob": close,
                         "noise": rng.normal(size=n), "zero": 0.0})


def test_build_pred_matrix_columns_share_one_valid_mask():
    frame = _frame()
    pred_matrix, outcome, used = build_pred_matrix(frame, ["noise", "zero"], lambdas=(.1, 1.0))
    assert pred_matrix.shape[1] == len(used) == 2
    assert pred_matrix.shape[0] == len(outcome) > 0


def test_blocks_are_adjacent_runs_never_shuffled():
    # each block must be an ascending run of ADJACENT rows -- a shuffled block
    # would leak future rows into an "earlier" block.
    for block in contiguous_blocks(203, 8):
        assert np.all(np.diff(block) == 1)


def test_is_and_oos_halves_are_exact_equal_complements():
    s_blocks = 6
    for combo in enumerate_split_indices(s_blocks=s_blocks, max_splits=1000):
        oos = [b for b in range(s_blocks) if b not in combo]
        assert len(set(combo)) == len(combo) == len(oos) == s_blocks // 2
        assert not set(combo) & set(oos)
        assert set(combo) | set(oos) == set(range(s_blocks))


def test_nan_or_inf_input_raises_instead_of_silently_lowering_pbo():
    # np.argmin SELECTS a NaN column as IS-best, its OOS rank is NaN, and
    # `nan <= 0` is False -- so without this guard one NaN quietly pushes PBO
    # toward 0, the reassuring direction.
    pred, outcome = _noise_matrix()
    assert np.argmin(np.array([0.3, np.nan, 0.1])) == 1  # documents the numpy behavior
    assert not (float("nan") <= 0.0)
    pred[5, 2] = np.nan
    with pytest.raises(ValueError):
        cscv_pbo(pred, outcome, s_blocks=16, max_splits=50)
    pred[5, 2] = np.inf
    with pytest.raises(ValueError):
        cscv_pbo(pred, outcome, s_blocks=16, max_splits=50)
    pred, outcome = _noise_matrix()
    with pytest.raises(ValueError):
        cscv_pbo(pred, outcome.astype(float) * np.nan, s_blocks=16, max_splits=50)


def test_non_probability_matrix_or_non_binary_outcome_raises():
    pred, outcome = _noise_matrix()
    with pytest.raises(ValueError):
        cscv_pbo(pred * 10.0, outcome, s_blocks=16, max_splits=50)  # logits, not probabilities
    with pytest.raises(ValueError):
        cscv_pbo(pred, outcome + 1, s_blocks=16, max_splits=50)     # not binary


def test_all_tied_configs_give_finite_logits_never_infinite():
    # omega = rank / (n_configs + 1) keeps omega strictly inside (0, 1); the
    # degenerate all-identical case lands on the median (lam == 0), counted as
    # overfit by the `<= 0` convention rather than blowing up to +/-inf.
    _, outcome = _noise_matrix()
    pred = np.repeat(np.full((len(outcome), 1), 0.5), 6, axis=1)
    result = cscv_pbo(pred, outcome, s_blocks=16, max_splits=50)
    assert np.isfinite(result.logit_lambdas).all()
    assert set(result.omegas) == {0.5} and set(result.logit_lambdas) == {0.0}
    assert result.pbo == 1.0


def test_enumerate_rejects_odd_blocks_and_nonpositive_max_splits():
    with pytest.raises(ValueError):
        enumerate_split_indices(s_blocks=5)      # complement would not be a half
    with pytest.raises(ValueError):
        enumerate_split_indices(s_blocks=16, max_splits=0)  # would yield nan PBO


def test_build_pred_matrix_rejects_bad_lambda_sets_and_accepts_a_generator():
    frame = _frame()
    with pytest.raises(ValueError):
        build_pred_matrix(frame, ["noise"], lambdas=(1.0,))
    with pytest.raises(ValueError):
        build_pred_matrix(frame, ["noise"], lambdas=(1.0, 1.0))
    _, _, used = build_pred_matrix(frame, ["noise"], lambdas=(x for x in (0.1, 1.0)))
    assert used == [0.1, 1.0]  # generator materialized, not exhausted on the 2nd pass
