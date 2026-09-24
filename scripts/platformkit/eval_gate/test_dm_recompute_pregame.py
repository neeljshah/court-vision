"""Plant a known Brier gap on synthetic rows; check the interval, MDE and the verdict rule."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_recompute_pregame import MDE_FACTOR, summarize, verdict


def _rows(n: int, noise: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p_true = rng.uniform(0.2, 0.8, n)
    y = (rng.uniform(size=n) < p_true).astype(float)
    p_model = np.clip(p_true + rng.normal(0.0, noise, n), 0.01, 0.99)
    return pd.DataFrame({
        "split": ["fit"] * (n // 2) + ["holdout"] * (n - n // 2),
        "y": y, "p_model": p_model, "p_close": p_true,
        "cluster_id": [f"g{i}" for i in range(n)],
        "date": [f"d{i // 10}" for i in range(n)],
    })


def test_verdict_rule():
    assert verdict(-0.001, 0.002) == "MATCHES_CLOSE"
    assert verdict(0.0, 0.002) == "MATCHES_CLOSE"          # boundary counts as including 0
    assert verdict(0.001, 0.003) == "TRAILS_CLOSE"
    assert verdict(-0.003, -0.001) == "BEATS_CLOSE"


def test_planted_gap_is_recovered_and_trails():
    # noise sd 0.10 on the model adds E[(noise)^2] = 0.01 Brier over the true-prob close
    rep = summarize(_rows(40000, 0.10))
    assert rep["n"] == 20000                                  # holdout half only
    assert rep["ci95"][0] < 0.01 < rep["ci95"][1]            # planted gap inside the CI
    assert abs(rep["gap"] - 0.01) < 0.001
    assert rep["verdict"] == "TRAILS_CLOSE"
    assert rep["bss_vs_close"] < 0
    assert abs(rep["mde"] - MDE_FACTOR * (rep["ci95"][1] - rep["ci95"][0]) / 2) < 1e-12


def test_no_gap_matches_and_split_is_respected():
    df = _rows(4000, 0.0)
    df.loc[df["split"] == "fit", "p_model"] = 0.99            # a wrecked fit half is ignored
    rep = summarize(df)
    assert rep["gap"] == 0.0 and rep["verdict"] == "MATCHES_CLOSE"


def test_model_sharper_beats():
    df = _rows(40000, 0.10)
    df = df.rename(columns={"p_model": "p_close", "p_close": "p_model"})
    assert summarize(df)["verdict"] == "BEATS_CLOSE"
