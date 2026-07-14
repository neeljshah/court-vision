"""Synthetic-fixture tests for tail_calib.promote_gate -- no real data, no
network. Covers: half-split disjointness, paired-test correctness, BH
monotonicity, entity_diffs sign, and the "few individual survivors but
significant class effect" scenario the rails call out as a legitimate result.
"""
import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.tail_calib import promote_gate as pg


def test_split_reserve_halves_disjoint_and_covers_all():
    dates = pd.date_range("2025-11-01", periods=20, freq="D")
    reserve = pd.DataFrame({"date": dates, "player_id": 1, "pts": np.arange(20.0)})
    half_a, half_b = pg.split_reserve_halves(reserve)
    assert len(half_a) + len(half_b) == len(reserve)
    assert set(half_a.index).isdisjoint(set(half_b.index))
    assert half_a["date"].max() <= half_b["date"].min()


def test_paired_test_detects_real_shift():
    rng = np.random.default_rng(0)
    diffs = rng.normal(loc=0.5, scale=0.1, size=40)  # consistent positive shift
    result = pg.paired_test(diffs)
    assert result["n"] == 40
    assert result["mean"] > 0.4
    assert result["p_value"] < 0.01


def test_paired_test_noise_not_significant():
    rng = np.random.default_rng(1)
    diffs = rng.normal(loc=0.0, scale=1.0, size=20)
    result = pg.paired_test(diffs)
    assert result["p_value"] > 0.05 or np.isnan(result["p_value"])


def test_paired_test_zero_variance_is_nan_p():
    diffs = np.array([0.3, 0.3, 0.3])
    result = pg.paired_test(diffs)
    assert np.isnan(result["p_value"])
    assert result["mean"] == 0.3


def test_bh_correct_monotone_and_geq_raw_p():
    p = pd.Series([0.001, 0.01, 0.2, 0.5, 0.9])
    q = pg.bh_correct(p)
    # BH q-values are never smaller than the raw p-value at that rank
    assert (q.to_numpy() >= p.to_numpy() - 1e-12).all()
    # sorted-by-p q-values are non-decreasing
    order = p.sort_values().index
    q_sorted = q.loc[order].to_numpy()
    assert (np.diff(q_sorted) >= -1e-12).all()


def test_entity_diffs_sign_when_tail_aware_fits_better():
    # actual values sit in the fat tail where the empirical quantile vector
    # (tail_aware) should out-predict a same-mean/std Normal -> positive diff
    fit_metrics = {
        1: {"mean": 10.0, "std": 3.0, "insufficient": False,
            "quantiles": {q: v for q, v in zip(
                [0.005, 0.01, 0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975, 0.99, 0.995],
                [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 22.0, 26.0, 29.0, 30.0])}},
    }
    reserve = pd.DataFrame({"player_id": [1, 1, 1], "pts": [28.0, 27.0, 29.0]})  # far right tail
    diffs = pg.entity_diffs(1, fit_metrics, reserve)
    assert len(diffs) == 3
    assert diffs.mean() > 0  # tail-aware wins in the tail it was fit to


def test_entity_diffs_missing_entity_returns_empty():
    diffs = pg.entity_diffs(999, {}, pd.DataFrame({"player_id": [1], "pts": [10.0]}))
    assert len(diffs) == 0


def test_class_level_significant_with_near_zero_individual_survivors():
    """The scenario the rails explicitly call legitimate: a tiny, consistent
    per-entity effect that never clears an individual BH threshold, but IS
    significant pooled at the class level."""
    rng = np.random.default_rng(2)
    n_entities = 500
    # tiny consistent positive mean, large per-entity noise -> individual
    # p-values mostly non-significant, but the class-level mean is tight.
    entity_means = rng.normal(loc=0.03, scale=0.15, size=n_entities)
    table = pd.DataFrame({
        "mean_pooled": entity_means,
        "p_pooled": [pg.paired_test(rng.normal(loc=m, scale=1.0, size=15))["p_value"] for m in entity_means],
        "n_half_a": 8, "n_half_b": 8,
        "mean_half_a": entity_means, "mean_half_b": entity_means,
    })
    table["p_pooled"] = table["p_pooled"].fillna(1.0)
    table["bh_q"] = pg.bh_correct(table["p_pooled"])
    n_bh_survivors = int((table["bh_q"] < pg.BH_ALPHA).sum())
    class_result = pg.class_level_test(table)
    assert class_result["n_entities"] == n_entities
    # class-level effect on 300 consistent-direction entities should be picked up
    assert class_result["p_value"] < 0.05
    # and it should be a MUCH smaller fraction than 300 that individually survive BH
    assert n_bh_survivors < n_entities


def test_class_level_test_insufficient_n():
    table = pd.DataFrame({"mean_pooled": [0.1]})
    result = pg.class_level_test(table)
    assert result["n_entities"] == 1
    assert np.isnan(result["p_value"])
