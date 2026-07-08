"""Sanity tests for conditional_gate_v2.score_rung on synthetic arrays (no
real data/IO) -- mirrors test_conditional_gate.py's data-free unit style."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.ingame_compose.conditional_gate_v2 import score_rung


def _synthetic(n=400, seed=0):
    rng = np.random.default_rng(seed)
    elo_logit = rng.normal(0, 0.4, n)
    score_diff = rng.normal(0, 8, n)
    # a feature that IS informative beyond elo+score: strongly correlated with y
    signal = rng.normal(0, 1, n)
    noise1 = rng.normal(0, 1, n)
    logit = elo_logit + 0.3 * (score_diff / 8) + 1.2 * signal
    p = 1 / (1 + np.exp(-logit))
    y = (rng.random(n) < p).astype(float)
    gid = np.array([f"g{i}" for i in range(n)])
    feats = pd.DataFrame({"signal": signal, "noise1": noise1})
    return elo_logit, score_diff, feats, y, gid


def test_score_rung_untestable_below_min_test():
    elo, sd, feats, y, gid = _synthetic(n=50)
    r = score_rung("base", [], elo, sd, feats, y, gid, "half")
    assert r.verdict == "UNTESTABLE"


def test_score_rung_informative_feature_beats_base():
    elo, sd, feats, y, gid = _synthetic(n=600)
    base = score_rung("base", [], elo, sd, feats, y, gid, "half")
    with_signal = score_rung("+signal", ["signal"], elo, sd, feats, y, gid, "half")
    assert with_signal.brier_cond <= base.brier_base + 1e-9
    assert with_signal.delta >= -1e-9


def test_score_rung_cumulative_adds_noise_column_without_error():
    elo, sd, feats, y, gid = _synthetic(n=600)
    r = score_rung("+signal+noise1", ["signal", "noise1"], elo, sd, feats, y, gid, "half")
    assert set(r.betas.keys()) == {"signal", "noise1"}
    assert r.n_test > 0
