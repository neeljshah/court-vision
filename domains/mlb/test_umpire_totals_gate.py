"""Per-file tests for domains.mlb.umpire_totals_gate.

Offline only: pure synthetic pandas DataFrames, no parquet reads, no network.

Run ONLY this file:
  python -m pytest domains/mlb/test_umpire_totals_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.umpire_totals_gate import (
    BURN_IN,
    MIN_PER_FOLD,
    N_FOLDS,
    run_gate,
    shuffle_umpire_assignment,
)


# --------------------------------------------------------------------------- #
# synthetic corpus builders
# --------------------------------------------------------------------------- #
def _pure_noise_corpus(n: int = 1200, n_umpires: int = 20, seed: int = 7) -> pd.DataFrame:
    """No real umpire effect: total_runs is iid noise, hp_umpire_id assigned
    independently of the outcome."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2022-04-01", periods=n, freq="D")
    home_team = rng.choice(["AAA", "BBB", "CCC", "DDD"], size=n)
    ump_id = rng.randint(1, n_umpires + 1, size=n)
    n_ooz = rng.randint(100, 180, size=n).astype(float)
    ooz_strikes = (n_ooz * rng.uniform(0.25, 0.35, size=n)).round()
    total_runs = np.round(np.clip(rng.normal(8.5, 2.0, n), 0, None))
    return pd.DataFrame({
        "game_pk": np.arange(n), "date": dates, "home_team": home_team,
        "hp_umpire_id": ump_id, "total_runs": total_runs,
        "n_ooz": n_ooz, "ooz_strikes": ooz_strikes,
    })


def _planted_umpire_effect_corpus(n: int = 1200, n_umpires: int = 20, seed: int = 42) -> pd.DataFrame:
    """Real, strong per-umpire effect: umpire's TRUE latent zone-strictness
    directly shifts total_runs (higher strictness -> fewer runs), so an
    as-of umpire term SHOULD find signal here (unlike the null corpus)."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2022-04-01", periods=n, freq="D")
    home_team = rng.choice(["AAA", "BBB", "CCC", "DDD"], size=n)
    ump_id = rng.randint(1, n_umpires + 1, size=n)
    # each umpire has a fixed latent strictness in [-1, 1]
    latent = {u: rng.uniform(-1, 1) for u in range(1, n_umpires + 1)}
    strictness = np.array([latent[u] for u in ump_id])
    n_ooz = rng.randint(100, 180, size=n).astype(float)
    ooz_rate = np.clip(0.30 + 0.15 * strictness + rng.normal(0, 0.01, n), 0.05, 0.95)
    ooz_strikes = (n_ooz * ooz_rate).round()
    noise = rng.normal(0, 1.0, n)
    total_runs = np.round(np.clip(8.5 - 3.0 * strictness + noise, 0, None))
    return pd.DataFrame({
        "game_pk": np.arange(n), "date": dates, "home_team": home_team,
        "hp_umpire_id": ump_id, "total_runs": total_runs,
        "n_ooz": n_ooz, "ooz_strikes": ooz_strikes,
    })


# --------------------------------------------------------------------------- #
# shuffle_umpire_assignment
# --------------------------------------------------------------------------- #
def test_shuffle_preserves_outcomes_and_umpire_multiset():
    df = _pure_noise_corpus(n=300)
    shuffled = shuffle_umpire_assignment(df, seed=1)
    assert np.array_equal(shuffled["total_runs"].values, df["total_runs"].values)
    assert np.array_equal(shuffled["date"].values, df["date"].values)
    assert sorted(shuffled["hp_umpire_id"].values) == sorted(df["hp_umpire_id"].values)


def test_shuffle_is_deterministic_given_seed():
    df = _pure_noise_corpus(n=200)
    a = shuffle_umpire_assignment(df, seed=5)
    b = shuffle_umpire_assignment(df, seed=5)
    assert np.array_equal(a["hp_umpire_id"].values, b["hp_umpire_id"].values)


# --------------------------------------------------------------------------- #
# run_gate verdicts
# --------------------------------------------------------------------------- #
def test_pure_noise_rejects():
    """No real umpire effect -> must not SHIP_REVIEW."""
    res = run_gate(_pure_noise_corpus())
    assert res["verdict"] in ("REJECT", "INCONCLUSIVE")
    assert res["verdict"] != "SHIP_REVIEW"


def test_planted_effect_can_survive_the_null_gate():
    """A strong, real, as-of-discoverable umpire effect should be able to beat
    baseline in all folds AND beat the planted-null candidate's improvement --
    i.e. the gate is not so conservative it can never ship a genuine signal."""
    res = run_gate(_planted_umpire_effect_corpus())
    assert res["real_result"]["beats_all_folds"]
    real_delta = res["real_result"]["overall_rmse_delta"]
    null_delta = res["null_result"]["overall_rmse_delta"]
    assert real_delta < null_delta
    assert res["verdict"] == "SHIP_REVIEW"


def test_too_few_rows_is_inconclusive():
    small = _pure_noise_corpus(n=BURN_IN + 50)
    res = run_gate(small)
    assert res["verdict"] == "INCONCLUSIVE"
    assert res["real_result"]["n_scorable"] < MIN_PER_FOLD * N_FOLDS


def test_verdict_payload_carries_pre_registered_fields():
    res = run_gate(_pure_noise_corpus())
    assert res["pre_registered_expectation"] == "REJECT"
    assert "hypothesis" in res and "scope_note" in res
    assert "no $ edge claimed" in res["scope_note"]
    assert res["n_umpires"] > 0


# --------------------------------------------------------------------------- #
# leak check: game i's prediction must not depend on game i's own outcome,
# nor on any game AFTER i.
# --------------------------------------------------------------------------- #
def test_no_leak_perturbing_future_outcome_does_not_change_earlier_fold():
    df = _pure_noise_corpus(n=900, seed=1)
    df_perturbed = df.copy()
    last_idx = df_perturbed.index[-1]
    df_perturbed.loc[last_idx, "total_runs"] = df_perturbed.loc[last_idx, "total_runs"] + 1000.0

    res_a = run_gate(df)
    res_b = run_gate(df_perturbed)

    # first fold is entirely determined by games strictly before it; perturbing
    # the LAST game's own outcome must not change it at all (byte-identical
    # walk-forward baseline/candidate predictions).
    assert res_a["real_result"]["folds"][0] == res_b["real_result"]["folds"][0]
