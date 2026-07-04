"""Per-file test for scripts.platformkit.ceiling.asof_replication (LANE 1:
cross-corpus replication gate for the 3 wave-1 asof-reclaim survivors).

Acceptance criteria
--------------------
1. Synthetic-data replication math:
   a. A PLANTED real signal (feature strongly correlated with the outcome,
      injected into all 4 sub-corpora) REPLICATES (SHIP_REVIEW verdict).
   b. A HALF-ONLY signal (real correlation in era_a/parity_even only, pure
      noise elsewhere) does NOT replicate -- honest REJECT.
2. md5 determinism: md5_parity_split assigns the same rows to the same bucket
   across repeated calls and across process-independent hashlib.md5 (not
   builtin hash(), which is per-process randomized).
3. No leak across the split boundary: season_era_split / md5_parity_split
   partition rows so each row appears in EXACTLY one half; the two halves'
   index sets are disjoint and their union is the full frame.
4. Verdict-rule wiring: _scheme_verdict / replicate_one correctly gate on
   all_improve + same_sign + n_significant, and INSUFFICIENT_DATA halves are
   excluded from usable-count/replication logic (not silently counted as
   passing).

Fast, synthetic-only -- no real parquet I/O.  Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ceiling/test_asof_replication.py -q
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from scripts.platformkit.ceiling import asof_replication as R
from scripts.platformkit.ceiling import asof_replication_core as C


# --------------------------------------------------------------------------- #
# Synthetic fixtures + a self-contained gate (mirrors the real candidates'
# _gate_once contract without needing real parquet data)
# --------------------------------------------------------------------------- #

def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def _make_frame(n: int, seed: int, signal_strength: float, mask=None) -> pd.DataFrame:
    """event_id/date + p_base (noisy 0.5-centered baseline) + feat_col that is
    correlated with the outcome (scaled by signal_strength; 0 = pure noise) and
    a target column.  mask (bool array) restricts the signal to a subset of
    rows -- used to build a 'half-only' (non-replicating) planted signal."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=n, freq="D")
    z_base = rng.normal(0, 0.5, size=n)
    feat = rng.normal(0, 1.0, size=n)
    if mask is None:
        mask = np.ones(n, dtype=bool)
    signal_component = np.where(mask, signal_strength * feat, 0.0)
    p_true = _sigmoid(z_base + signal_component)
    y = (rng.uniform(0, 1, size=n) < p_true).astype(float)
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "date": dates,
        "p_base": _sigmoid(z_base),
        "feat": feat,
        "target": y,
        "_cov": True,
        "home_n_prior": 10, "away_n_prior": 10,
    })


def _synthetic_gate_once(df: pd.DataFrame, feat_col: str, train_frac: float) -> dict:
    """A minimal, self-contained walk-forward 2-feature-vs-1-feature Brier/DM
    gate mirroring the real candidates' _gate_once shape (same fields), used
    so replication tests do not depend on real domain parquet files."""
    from scipy.optimize import minimize
    from scripts.platformkit.eval_gate.dm_test import diebold_mariano

    d = df.sort_values("date", kind="mergesort").reset_index(drop=True)
    n = len(d)
    split = int(n * train_frac)
    tr, te = d.iloc[:split], d.iloc[split:]
    if len(tr) < 10 or len(te) < 10:
        return {"verdict": "INSUFFICIENT_DATA", "n_cov_test": len(te),
                "brier_delta": None, "dm_p": None, "feat_weight": None}

    def _logit(p):
        p = np.clip(p, 1e-7, 1 - 1e-7)
        return np.log(p / (1 - p))

    y_tr, y_te = tr["target"].values, te["target"].values
    lz_tr, lz_te = _logit(tr["p_base"].values), _logit(te["p_base"].values)
    f_tr, f_te = tr[feat_col].values, te[feat_col].values
    m, s = f_tr.mean(), max(f_tr.std(), 1e-8)
    fz_tr, fz_te = (f_tr - m) / s, (f_te - m) / s

    def _nll_base(par):
        w, b = par
        p = np.clip(_sigmoid(w * lz_tr + b), 1e-7, 1 - 1e-7)
        return float(-np.mean(y_tr * np.log(p) + (1 - y_tr) * np.log(1 - p)))

    rb = minimize(_nll_base, x0=[1.0, 0.0], method="L-BFGS-B", bounds=[(0.05, 10), (-3, 3)])
    p_base = _sigmoid(rb.x[0] * lz_te + rb.x[1])

    def _nll_cand(par):
        w1, w2, b = par
        p = np.clip(_sigmoid(w1 * lz_tr + w2 * fz_tr + b), 1e-7, 1 - 1e-7)
        return float(-np.mean(y_tr * np.log(p) + (1 - y_tr) * np.log(1 - p)))

    rc = minimize(_nll_cand, x0=[1.0, 0.1, 0.0], method="L-BFGS-B",
                  bounds=[(0.05, 10), (-5, 5), (-3, 3)])
    p_cand = _sigmoid(rc.x[0] * lz_te + rc.x[1] * fz_te + rc.x[2])
    w2 = float(rc.x[1])

    br_base = float(np.mean((p_base - y_te) ** 2))
    br_cand = float(np.mean((p_cand - y_te) ** 2))
    dd = (p_base - y_te) ** 2 - (p_cand - y_te) ** 2
    dm = diebold_mariano(dd, te["event_id"].astype(str).values)
    return {"n_cov_test": int(len(te)), "brier_base": br_base, "brier_cand": br_cand,
            "brier_delta": br_base - br_cand, "dm_p": dm.p_value, "feat_weight": w2,
            "verdict": "SHIP" if (br_cand < br_base and dm.p_value < 0.05) else "REJECT"}


def _make_spec(build_frame_fn, feat_col: str = "feat") -> C.ReplicationSpec:
    return C.ReplicationSpec(
        sport="synthetic", signal="synthetic_signal", feat_col=feat_col,
        build_frame=build_frame_fn, gate_once=_synthetic_gate_once,
        wave1_dm_p=0.03, wave1_weight_sign=0,
    )


# --------------------------------------------------------------------------- #
# 1a. Planted REAL signal (present everywhere) -> replicates
# --------------------------------------------------------------------------- #

class TestPlantedSignalReplicates:
    def test_strong_uniform_signal_ships_review(self):
        df = _make_frame(n=2000, seed=1, signal_strength=1.5)
        spec = _make_spec(lambda: df)
        res = R.replicate_one(spec)
        assert res["verdict"] == "SHIP_REVIEW", res["verdict_reason"]
        assert res["n_significant_sub_corpora"] >= C.MIN_SIGNIFICANT
        assert res["season_era_scheme"]["all_improve"]
        assert res["md5_parity_scheme"]["all_improve"]


# --------------------------------------------------------------------------- #
# 1b. Half-only signal (real in era_a subset only) -> honest REJECT
# --------------------------------------------------------------------------- #

class TestHalfOnlySignalRejects:
    def test_era_only_signal_does_not_replicate(self):
        n = 2000
        df = _make_frame(n=n, seed=2, signal_strength=0.0)
        # Inject a strong signal ONLY into the first quarter of rows by date
        # (era_a's first half after season_era_split will carry it; era_b and
        # roughly half of each parity bucket will not) -- a classic single-
        # fold artifact that must not survive cross-corpus replication.
        d = df.sort_values("date", kind="mergesort").reset_index(drop=True)
        mask = np.zeros(n, dtype=bool)
        mask[: n // 8] = True
        rng = np.random.default_rng(3)
        z_base = rng.normal(0, 0.5, size=n)
        feat = d["feat"].values
        signal_component = np.where(mask, 2.5 * feat, 0.0)
        p_true = _sigmoid(z_base + signal_component)
        d["target"] = (rng.uniform(0, 1, size=n) < p_true).astype(float)
        d["p_base"] = _sigmoid(z_base)

        spec = _make_spec(lambda: d)
        res = R.replicate_one(spec)
        assert res["verdict"] == "REJECT", (
            f"half-only planted signal should not replicate, got {res['verdict']}"
        )
        assert res["n_significant_sub_corpora"] < C.MIN_SIGNIFICANT


# --------------------------------------------------------------------------- #
# 2. md5 determinism
# --------------------------------------------------------------------------- #

class TestMd5Determinism:
    def test_parity_split_deterministic_across_calls(self):
        df = _make_frame(n=500, seed=5, signal_strength=0.5)
        even1, odd1 = C.md5_parity_split(df)
        even2, odd2 = C.md5_parity_split(df)
        assert set(even1["event_id"]) == set(even2["event_id"])
        assert set(odd1["event_id"]) == set(odd2["event_id"])

    def test_parity_split_matches_raw_hashlib_md5(self):
        df = _make_frame(n=300, seed=6, signal_strength=0.5)
        even, odd = C.md5_parity_split(df)
        for eid in even["event_id"]:
            assert int(hashlib.md5(str(eid).encode("utf-8")).hexdigest(), 16) % 2 == 0
        for eid in odd["event_id"]:
            assert int(hashlib.md5(str(eid).encode("utf-8")).hexdigest(), 16) % 2 == 1

    def test_parity_split_does_not_use_builtin_hash(self):
        # builtin hash() of str is salted per-process (PYTHONHASHSEED) -- assert
        # the module's source uses hashlib.md5, not hash(), for the split.
        import inspect
        src = inspect.getsource(C.md5_parity_split)
        assert "hashlib.md5" in src
        assert "builtins.hash(" not in src


# --------------------------------------------------------------------------- #
# 3. No leak across split boundary
# --------------------------------------------------------------------------- #

class TestNoLeakAcrossSplit:
    def test_season_era_halves_disjoint_and_complete(self):
        df = _make_frame(n=400, seed=7, signal_strength=0.3)
        era_a, era_b = C.season_era_split(df)
        assert len(era_a) + len(era_b) == len(df)
        assert set(era_a["event_id"]).isdisjoint(set(era_b["event_id"]))
        assert set(era_a["event_id"]) | set(era_b["event_id"]) == set(df["event_id"])

    def test_season_era_split_is_chronological(self):
        df = _make_frame(n=400, seed=8, signal_strength=0.3)
        era_a, era_b = C.season_era_split(df)
        assert era_a["date"].max() <= era_b["date"].min()

    def test_md5_parity_halves_disjoint_and_complete(self):
        df = _make_frame(n=400, seed=9, signal_strength=0.3)
        even, odd = C.md5_parity_split(df)
        assert len(even) + len(odd) == len(df)
        assert set(even["event_id"]).isdisjoint(set(odd["event_id"]))
        assert set(even["event_id"]) | set(odd["event_id"]) == set(df["event_id"])

    def test_gate_sub_corpus_only_trains_within_the_half(self):
        # Sanity: _gate_sub_corpus on era_a must produce a test-set size that is
        # a fraction of len(era_a) alone, never referencing era_b's row count.
        df = _make_frame(n=2000, seed=10, signal_strength=1.0)
        era_a, era_b = C.season_era_split(df)
        spec = _make_spec(lambda: df)
        res_a = C._gate_sub_corpus(spec, era_a)
        expected_test_n = len(era_a) - int(len(era_a) * 0.70)
        assert res_a["n_cov_test"] == expected_test_n


# --------------------------------------------------------------------------- #
# 4. Verdict-rule wiring
# --------------------------------------------------------------------------- #

class TestVerdictRuleWiring:
    def test_insufficient_data_excluded_from_usable_count(self):
        halves = {
            "era_a": {"verdict": "INSUFFICIENT_DATA", "brier_delta": None, "feat_weight": None},
            "era_b": {"verdict": "REJECT", "brier_delta": 0.001, "feat_weight": 0.2, "dm_p": 0.02},
        }
        scheme = C._scheme_verdict(halves)
        assert scheme["n_usable"] == 1
        # all_improve/same_sign computed only over usable halves
        assert scheme["all_improve"] is True
        assert scheme["same_sign"] is True

    def test_scheme_verdict_flags_mixed_sign_as_not_same_sign(self):
        halves = {
            "a": {"verdict": "REJECT", "brier_delta": 0.001, "feat_weight": 0.2, "dm_p": 0.02},
            "b": {"verdict": "REJECT", "brier_delta": 0.001, "feat_weight": -0.2, "dm_p": 0.02},
        }
        scheme = C._scheme_verdict(halves)
        assert scheme["same_sign"] is False

    def test_registry_returns_three_specs(self):
        specs = R.registry()
        names = {s.signal for s in specs}
        assert names == {
            "wta_hold_pct_diff_asof", "soccer_diff_sot_for_asof", "soccer_diff_shots_for_asof",
        }
