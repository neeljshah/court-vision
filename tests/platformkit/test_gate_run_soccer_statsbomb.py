"""tests.platformkit.test_gate_run_soccer_statsbomb -- OFFLINE checks for the StatsBomb
real-xG/event gate machinery. No network, no parquet: feeds SYNTHETIC frames straight
into the gate primitives and asserts (a) a pure-noise planted-null REJECTS, (b) a
genuinely informative feature can SHIP cross-corpus both directions, (c) the
degenerate-base guard fires, (d) the EW-Poisson base is leak-free + monotone."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.gate_run_soccer_statsbomb import (
    _ew_poisson_base, _gate_corpus, _logit, _poisson_home_win, gate_one,
)


def _frame(n: int, signal: float, seed: int) -> pd.DataFrame:
    """A corpus with a skillful base (p_base correlated with y) plus a feature whose
    informativeness is controlled by `signal` (0 = pure noise)."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)             # latent strength
    p_base = 1.0 / (1.0 + np.exp(-z))
    feat = signal * z + rng.standard_normal(n)     # feature ~ latent when signal>0
    # outcome driven by latent + a slice of the residual feature signal
    lin = z + 0.6 * signal * (feat - signal * z)
    y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-lin))).astype(float)
    return pd.DataFrame({
        "match_id": [str(i) for i in range(n)],
        "date": pd.date_range("2015-08-01", periods=n, freq="D"),
        "p_base": p_base, "y_home": y, "feat": feat,
        "planted_null": rng.standard_normal(n),
    })


def test_planted_null_rejects_both_corpora() -> None:
    a = _frame(400, signal=1.0, seed=1)
    b = _frame(400, signal=1.0, seed=2)
    res = gate_one(a, b, "planted_null", eps=0.05)
    assert res["verdict"] in ("REJECT", "PARTIAL"), res["verdict"]
    assert not (res["a_wins"] and res["b_wins"])


def test_strong_feature_can_ship() -> None:
    a = _frame(800, signal=1.4, seed=3)
    b = _frame(800, signal=1.4, seed=4)
    res = gate_one(a, b, "feat", eps=0.1)
    # an informative feature beats the base in BOTH directions (gate CAN pass)
    assert res["corpus_a"]["feat_better"] and res["corpus_b"]["feat_better"]
    assert res["verdict"] in ("SHIP", "PARTIAL")


def test_degenerate_base_guard() -> None:
    """A base with zero skill (p_base independent of y) -> base_degenerate True."""
    rng = np.random.default_rng(9)
    n = 400
    df = pd.DataFrame({
        "match_id": [str(i) for i in range(n)],
        "date": pd.date_range("2015-08-01", periods=n, freq="D"),
        "p_base": np.full(n, 0.5),                 # constant, no resolution
        "y_home": (rng.uniform(size=n) < 0.5).astype(float),
        "feat": rng.standard_normal(n),
    })
    out = _gate_corpus(df, "feat", eps=0.05)
    assert out["base_degenerate"] is True


def test_ew_poisson_base_leak_free_and_skillful() -> None:
    """EW-Poisson base: mutating a LATER match leaves earlier p_poisson unchanged."""
    rng = np.random.default_rng(7)
    rows = []
    teams = ["A", "B", "C", "D"]
    for i in range(40):
        h, a = rng.choice(teams, 2, replace=False)
        rows.append({"match_id": str(i), "match_date": f"2015-08-{i+1:02d}",
                     "home_team": h, "away_team": a,
                     "home_score": int(rng.integers(0, 4)),
                     "away_score": int(rng.integers(0, 3)), "corpus": "A"})
    meta = pd.DataFrame(rows)
    base = _ew_poisson_base(meta).set_index("match_id")
    meta2 = meta.copy(); meta2.loc[39, "home_score"] = 9
    after = _ew_poisson_base(meta2).set_index("match_id")
    for mid in ("5", "10", "20"):
        assert base.loc[mid, "p_poisson"] == pytest.approx(after.loc[mid, "p_poisson"])
    assert (base["p_poisson"] > 0).all() and (base["p_poisson"] < 1).all()


def test_poisson_home_win_monotone() -> None:
    """Higher home lambda (vs fixed away) raises P(home win)."""
    lo = _poisson_home_win(1.0, 1.2)
    hi = _poisson_home_win(2.5, 1.2)
    assert hi > lo
    assert 0.0 < lo < hi < 1.0
