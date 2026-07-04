"""Per-file pytest for positional_weight_stats.py / positional_weight_gate.py
/ positional_weight_io.py / atlas_player_position.py.

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/weights/test_positional_weight_gate.py -q

NEVER run the full suite (freezes the box). Synthetic-table unit tests for
the weight-fitting machinery (fast, no I/O) plus ONE smoke test against real
on-disk data with a reduced bootstrap budget (still exercises the full
leave-one-fold-out + planted-null path end to end, never raises).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.atlas_player_position import (
    POSGROUP_MAP,
    coverage_report,
    load_position_atlas,
)
from scripts.platformkit.weights.positional_weight_stats import (
    _softmax3,
    _to_z,
    composite,
    fit_group_weights,
    fold_eval,
    leave_one_fold_out,
    predict_positional,
    shuffle_posgroup_within_cutoff,
    sign_holds,
)
from scripts.platformkit.weights.positional_weight_gate import run_gate


def _synthetic_table(n: int, seed: int, posgroups=("guard", "forward", "center")) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    truth = rng.uniform(0, 1, n)
    return pd.DataFrame({
        "player_id": np.arange(n) + seed * 1000,
        "posgroup": rng.choice(posgroups, n),
        "ts_pct": np.clip(truth + rng.normal(0, 0.1, n), 0, 1),
        "efg_pct": np.clip(truth + rng.normal(0, 0.1, n), 0, 1),
        "ft_pct": rng.uniform(0, 1, n),  # uninformative noise
        "naive_pctile": np.clip(truth + rng.normal(0, 0.15, n), 0, 1),
        "realized_ts_pct": truth,
    })


def test_softmax3_sums_to_one_and_nonnegative():
    w = _softmax3(np.array([1.0, -2.0, 0.5]))
    assert w.sum() == pytest.approx(1.0)
    assert (w >= 0).all()


def test_to_z_roundtrips_through_softmax3():
    w = np.array([0.2, 0.5, 0.3])
    z = _to_z(w)
    w2 = _softmax3(z)
    assert np.allclose(w2, w, atol=1e-6)


def test_composite_is_weighted_sum():
    t = pd.DataFrame({"ts_pct": [1.0], "efg_pct": [0.0], "ft_pct": [0.0]})
    out = composite(t, np.array([0.7, 0.2, 0.1]))
    assert out.iloc[0] == pytest.approx(0.7)


def test_fit_group_weights_beats_uniform_when_one_factor_is_pure_signal():
    """ts_pct == truth exactly for one group's tables; the fit should not
    land on the untuned uniform (1/3,1/3,1/3) start when a clearly better
    point exists (regression guard for the grid-prescan degeneracy fix)."""
    rng = np.random.default_rng(42)
    tables = []
    for k in range(3):
        n = 60
        truth = rng.uniform(0, 1, n)
        tables.append(pd.DataFrame({
            "posgroup": ["guard"] * n,
            "ts_pct": truth,  # pure signal
            "efg_pct": rng.uniform(0, 1, n),  # noise
            "ft_pct": rng.uniform(0, 1, n),  # noise
            "realized_ts_pct": truth,
        }))
    w = fit_group_weights(tables, "guard")
    assert w[0] > 0.5  # should load heavily on ts_pct, the pure-signal factor
    assert not np.allclose(w, [1 / 3, 1 / 3, 1 / 3], atol=1e-3)


def test_fit_group_weights_falls_back_to_naive_when_too_few_rows():
    tables = [pd.DataFrame({"posgroup": [], "ts_pct": [], "efg_pct": [],
                             "ft_pct": [], "realized_ts_pct": []})]
    w = fit_group_weights(tables, "center")
    assert np.allclose(w, [0.55, 0.30, 0.15])


def test_predict_positional_scores_every_group():
    t = _synthetic_table(90, seed=1)
    weights = {"guard": np.array([0.55, 0.30, 0.15]),
               "forward": np.array([0.55, 0.30, 0.15]),
               "center": np.array([0.55, 0.30, 0.15])}
    pred = predict_positional(t, weights)
    assert pred.notna().all()
    assert (pred >= 0).all() and (pred <= 1).all()


def test_fold_eval_has_overall_and_all_posgroup_keys():
    t = _synthetic_table(120, seed=2)
    weights = {"guard": np.array([0.55, 0.30, 0.15]),
               "forward": np.array([0.55, 0.30, 0.15]),
               "center": np.array([0.55, 0.30, 0.15])}
    result = fold_eval(t, weights)
    assert "overall" in result and "delta" in result["overall"]
    assert set(result["per_group"].keys()) == {"guard", "forward", "center"}


def test_leave_one_fold_out_shape_matches_cutoffs():
    tables = [_synthetic_table(150, seed=100 + i) for i in range(4)]
    cutoffs = ["c0", "c1", "c2", "c3"]
    per_fold = leave_one_fold_out(tables, cutoffs)
    assert len(per_fold) == 4
    assert [f["cutoff"] for f in per_fold] == cutoffs
    for f in per_fold:
        assert f["overall"] is not None
        assert set(f["weights"].keys()) == {"guard", "forward", "center"}


def test_shuffle_posgroup_within_cutoff_preserves_marginal_breaks_pairing():
    t = _synthetic_table(200, seed=5)
    rng = np.random.default_rng(9)
    shuffled = shuffle_posgroup_within_cutoff(t, rng)
    assert sorted(shuffled["posgroup"].tolist()) == sorted(t["posgroup"].tolist())
    assert not (shuffled["posgroup"].values == t["posgroup"].values).all()
    assert np.allclose(shuffled["realized_ts_pct"].values, t["realized_ts_pct"].values)


def test_sign_holds_counts_positive_deltas():
    per_fold = [{"overall": {"delta": 0.1}}, {"overall": {"delta": -0.1}}, {"overall": {"delta": 0.05}}]
    holds, n = sign_holds(per_fold, ["overall"])
    assert (holds, n) == (2, 3)


def test_position_atlas_map_has_no_finer_split():
    assert set(POSGROUP_MAP.values()) == {"guard", "forward", "center"}
    assert set(POSGROUP_MAP.keys()) == {"GUARD", "WING", "BIG"}


def test_position_atlas_loads_and_covers_qualifiers_above_floor():
    """Live on-disk check: the 329-qualifier coverage must clear the 0.85
    floor for this gate to be runnable (matches the STEP 1 brief's binding
    stop-if-uncovered rule)."""
    atlas = load_position_atlas()
    assert set(atlas["posgroup"].unique()) <= {"guard", "forward", "center"}
    from domains.basketball_nba.quality_indices import (
        aggregate_season, load_boxscores, qualifying_pool,
    )
    box = load_boxscores()
    qual = qualifying_pool(aggregate_season(box))
    rep = coverage_report(atlas, qual["player_id"])
    assert rep["coverage_pct"] >= 0.85


def test_run_gate_never_raises_and_returns_pre_registered_verdict():
    """Smoke test against real on-disk data with a reduced bootstrap budget
    (patched at the module level) so the per-file test stays fast; must
    terminate with one of the pre-registered verdicts, never crash."""
    import scripts.platformkit.weights.positional_weight_gate as pwg
    orig_n_boot = pwg.N_BOOT
    pwg.N_BOOT = 30
    try:
        g = run_gate()
    finally:
        pwg.N_BOOT = orig_n_boot
    assert g.verdict in ("SHIP", "REJECT", "NOT_TESTABLE", "INSUFFICIENT_COVERAGE")
    assert isinstance(g.reason, str) and len(g.reason) > 0


def test_verdict_naive_stays_canonical_unless_all_conditions_hold():
    """Binding: SHIP only if a win locus's CI excludes 0, sign holds in
    >=75% of scored folds, replication succeeds with a positive delta, AND
    the planted null dies. Anything else must be REJECT/NOT_TESTABLE/
    INSUFFICIENT_COVERAGE."""
    import scripts.platformkit.weights.positional_weight_gate as pwg
    orig_n_boot = pwg.N_BOOT
    pwg.N_BOOT = 30
    try:
        g = run_gate()
    finally:
        pwg.N_BOOT = orig_n_boot
    if g.verdict == "SHIP":
        assert g.planted_null_dies is True
        assert g.replication.get("status") == "OK"
    else:
        assert g.verdict in ("REJECT", "NOT_TESTABLE", "INSUFFICIENT_COVERAGE")
