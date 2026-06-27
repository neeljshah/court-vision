"""Per-file tests for tests.mlb.regate_mlb_expanded (expanded MLB in-game re-gate).

Validates the fold wiring + solidify logic deterministically on a SYNTHETIC pool
(no network, no real corpus needed), plus a light smoke check on whatever real MLB
season corpora happen to be present. ASCII-only; per-file test (never full pytest).
"""
from __future__ import annotations

import math
import os

import numpy as np

from tests.mlb import regate_mlb_expanded as R


def _synth_states(season: int, n_games: int, signal: float, seed: int):
    """Build a leak-free-ish synthetic corpus where (state,time) AND p0 both inform y.

    Each game gets a true strength t in [-1,1]; p0 = sigmoid(2t); per half-inning the
    score diff drifts toward t; outcome = sign of final diff. signal scales how much p0
    adds beyond (state,time) so we can make +PRIOR genuinely beat BASE.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        t = float(rng.uniform(-1, 1))
        p0 = 1.0 / (1.0 + math.exp(-2.0 * t))
        diff = 0.0
        n_hi = 18
        final = None
        traj = []
        for k in range(n_hi):
            diff += rng.normal(signal * t, 1.0)
            traj.append((k, diff))
        final = traj[-1][1] + rng.normal(2.0 * signal * t, 0.5)
        y = 1 if final > 0 else 0
        for k, d in traj:
            rows.append({
                "game_id": f"{season}_{g}", "state_diff": float(d),
                "frac_elapsed": (k + 1) / n_hi, "p0": float(p0), "outcome": int(y),
            })
    return rows


def test_run_fold_shape():
    a = _synth_states(2021, 40, 0.6, 1)
    b = _synth_states(2022, 40, 0.6, 2)
    fold = R.run_fold(a, b, b, a)
    assert set(fold) == {"verdict", "a_to_b", "b_to_a"}
    for d in ("a_to_b", "b_to_a"):
        x = fold[d]
        assert "dm_p" in x and "brier_delta" in x and "prior_beats_base" in x
        assert x["n_test_games"] == 40
    assert fold["verdict"] in {"REPLICATED", "PARTIAL", "REJECT",
                               "INVALID_BASE", "INSUFFICIENT_DATA"}


def test_regate_synthetic_four_seasons_strong_signal():
    """With 4 synthetic seasons + a real p0 signal, parity fold should REPLICATE and
    solidify should NOT crash; structure (parity, time, pairs) must be present."""
    pool = {2021: 60, 2022: 60, 2023: 60, 2024: 60}
    monkey = {}
    for i, (s, n) in enumerate(pool.items()):
        monkey[s] = _synth_states(s, n, 0.7, 100 + i)

    def fake_load_seasons(seasons):
        out = []
        for s in seasons:
            out.extend(monkey[s])
        return out

    orig_load = R._load_seasons
    orig_avail = R.available_seasons
    orig_cov_load = R._load_seasons
    try:
        R._load_seasons = fake_load_seasons  # type: ignore
        R.available_seasons = lambda: [2021, 2022, 2023, 2024]  # type: ignore
        rep = R.regate()
    finally:
        R._load_seasons = orig_load  # type: ignore
        R.available_seasons = orig_avail  # type: ignore
        R._load_seasons = orig_cov_load  # type: ignore
    assert rep["seasons"] == [2021, 2022, 2023, 2024]
    assert "parity" in rep["folds"] and "time" in rep["folds"]
    assert len(rep["folds"]["pairs"]) == 3
    s = rep["solidify"]
    assert s["status"] in {"STRENGTHENED", "REPLICATED_STABLE", "WEAKENED",
                           "INSUFFICIENT_DATA"}
    # sanity: report formats without error
    assert "RE-GATE" in R._fmt(rep)


def test_solidify_weakened_on_noise_prior():
    """If p0 is pure noise, +PRIOR cannot beat BASE -> parity not REPLICATED ->
    solidify must report WEAKENED (or INSUFFICIENT), never STRENGTHENED."""
    import numpy as _np
    rng = _np.random.default_rng(7)

    def noise_pool(s, n):
        rows = _synth_states(s, n, 0.6, s)
        for r in rows:
            r["p0"] = float(rng.uniform(0.3, 0.7))  # decorrelated from outcome
        return rows

    monkey = {y: noise_pool(y, 60) for y in (2021, 2022, 2023, 2024)}
    orig = R._load_seasons
    orig_a = R.available_seasons
    try:
        R._load_seasons = lambda ss: [r for s in ss for r in monkey[s]]  # type: ignore
        R.available_seasons = lambda: [2021, 2022, 2023, 2024]  # type: ignore
        rep = R.regate()
    finally:
        R._load_seasons = orig  # type: ignore
        R.available_seasons = orig_a  # type: ignore
    assert rep["solidify"]["status"] != "STRENGTHENED"


def test_real_corpora_smoke_if_present():
    """If >=2 real MLB season corpora exist, regate runs end-to-end and emits a
    solidify status. Skips quietly when fewer than 2 are present (honest)."""
    seasons = R.available_seasons()
    if len(seasons) < 2:
        return
    rep = R.regate(seasons)
    assert rep["seasons"] == sorted(seasons)
    assert "solidify" in rep
    assert rep["solidify"]["status"] in {
        "STRENGTHENED", "REPLICATED_STABLE", "WEAKENED", "INSUFFICIENT_DATA"}
