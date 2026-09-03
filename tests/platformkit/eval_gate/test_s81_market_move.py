"""Per-file test for the S81 open-to-close market-move screen.

  python -m pytest tests/platformkit/eval_gate/test_s81_market_move.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s81_market_move as s81


def _bundle(n: int, signal: float, seed: int = 7) -> dict:
    """A synthetic screen-side bundle whose move is `signal` * x1 plus noise."""
    rng = np.random.default_rng(seed)
    x1, x2 = rng.normal(size=n), rng.normal(size=n)
    p_open = 1.0 / (1.0 + np.exp(-rng.normal(scale=0.6, size=n)))
    move = signal * x1 + rng.normal(scale=0.10, size=n)
    p_close = s81._sigmoid(s81._logit(p_open) + move)
    return {
        "sport": "synthetic", "incumbent": "devig_close",
        "X": pd.DataFrame({"x1": x1, "x2": x2, "logit_open": s81._logit(p_open)},
                          index=pd.Index(["e%04d" % i for i in range(n)], name="event_id")),
        "m": s81._logit(p_close) - s81._logit(p_open),
        "p_open": p_open, "p_close": p_close, "p_inc": p_close,
        "y": (rng.random(n) < p_close).astype(int),
        "dates": np.array([np.datetime64("2024-01-01") + np.timedelta64(i, "D")
                           for i in range(n)]),
        "units": np.array(["u%d" % (i % 4) for i in range(n)]),
        "cluster_ids": np.array(["c%d" % (i % 6) for i in range(n)]),
        "n_states": n, "n_screen": n, "n_with_both": n, "n_missing_cols": 0,
        "screen_sha256": "0" * 64, "partition_basis": "iso_week", "cluster_key": "unit",
    }


def test_bar_is_not_moved():
    """Q3: the register row's bar is 0.004 and no code path may lower it."""
    assert s81.IMPROVEMENT_BAR == 0.004


def test_devig_pair_is_fair_and_reuses_close_column():
    got = s81._devig_pair(np.array([2.0, 1.5, np.nan]), np.array([2.0, 3.0, 2.0]))
    assert got[0] == pytest.approx(0.5)
    assert got[1] == pytest.approx(2.0 / 3.0, abs=1e-6)   # devigged 1/1.5 vs 1/3
    assert np.isnan(got[2])                                # a missing side is dropped, not guessed


def test_ar1_null_recovers_a_planted_reversion_coefficient():
    rng = np.random.default_rng(3)
    open_logit = rng.normal(size=400)
    base = s81._logit(np.full(1, 0.5))[0]
    m = 0.4 * (base - open_logit)
    pred, c = s81._ar1(open_logit, m, open_logit[:50], np.array([0, 1] * 50))
    assert c == pytest.approx(0.4, abs=1e-9)
    assert pred == pytest.approx(0.4 * (base - open_logit[:50]), abs=1e-9)


def test_sports_without_a_local_open_are_refused_by_name():
    for sport in ("nba", "tennis"):
        with pytest.raises(ValueError, match="no local opening price"):
            s81.build_move(sport)


def _scored_arm(bundle: dict) -> dict:
    """Nested walk-forward over the bundle, scored against the zero-move null on its own rows."""
    oof = s81._oof(bundle, 5).sort_values("row").reset_index(drop=True)
    idx = oof["row"].to_numpy()
    return s81._arm(bundle["m"][idx], oof["m_hat_enet"].to_numpy(), bundle["units"][idx],
                    bundle["cluster_ids"][idx], np.zeros(len(idx)))


def test_oof_finds_a_real_move_and_reports_null_on_noise():
    real = _scored_arm(_bundle(700, 0.5))
    assert real["r2_vs_null"] > 0.5 and real["sign_acc"] > 0.7
    noise = _scored_arm(_bundle(700, 0.0))
    assert noise["r2_vs_null"] < 0.1
    assert noise["paired_dm"]["ci95"][0] < 0.0 < noise["paired_dm"]["ci95"][1]


def test_arm_is_scored_on_the_same_rows_the_folds_served():
    bundle = _bundle(700, 0.5)
    oof = s81._oof(bundle, 5)
    assert len(set(oof["row"])) == len(oof)               # A4: no row scored twice
    assert oof["row"].max() < len(bundle["m"])
    assert set(oof["fold"]) == set(range(oof["fold"].nunique()))
