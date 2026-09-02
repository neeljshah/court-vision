"""Per-file test for S101 adaptive-conformal coverage.

    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_s101_aci_coverage.py -q

Covers the strictly-before (no-lookahead) guard on the online alpha update, the per-game alpha
reset, the train-only calibration seam, the grouped-coverage measure, and the Q3/Q6 rails.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s101_aci_coverage as m


def _frame(n_games: int = 3, n_ticks: int = 120, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        y = float(g % 2)
        p = np.clip(0.5 + 0.3 * rng.standard_normal(n_ticks), 0.02, 0.98)
        for t in range(n_ticks):
            rows.append({"game": "g%d" % g, "date": "2024-11-%02d" % (g + 1), "ts": 1000 + t,
                         "period_bucket": "P1" if t < n_ticks // 2 else "P4",
                         "cell": "P1|close_le5|rem_gt12", "market": float(p[t]),
                         "model": float(p[t]), "y": y})
    return pd.DataFrame(rows)


# --- the strictly-before guard: a future outcome cannot reach a past interval ---------------

def test_aci_alpha_and_bands_ignore_future_outcomes():
    f = _frame(n_games=1, n_ticks=200)
    lo = np.clip(f["market"].to_numpy(float) - 0.05, 0, 1)
    hi = np.clip(f["market"].to_numpy(float) + 0.05, 0, 1)
    cut = 90
    _, aci_hi_a, alpha_a, _ = m.aci_walk(f, lo, hi, 0.10)
    g = f.copy()
    g.loc[g.index[cut:], "y"] = 1.0 - g["y"].iloc[0]     # rewrite every outcome at/after `cut`
    _, aci_hi_b, alpha_b, _ = m.aci_walk(g, lo, hi, 0.10)
    # alpha USED at tick t is built from misses strictly before t, so ticks 0..cut are untouched.
    assert np.allclose(alpha_a[: cut + 1], alpha_b[: cut + 1])
    assert np.allclose(aci_hi_a[: cut + 1], aci_hi_b[: cut + 1])
    assert not np.allclose(alpha_a[cut + 1:], alpha_b[cut + 1:])   # and it does react afterwards


def test_alpha_resets_at_every_game_boundary():
    f = _frame(n_games=3, n_ticks=120)
    lo = np.clip(f["market"].to_numpy(float) - 0.01, 0, 1)
    hi = np.clip(f["market"].to_numpy(float) + 0.01, 0, 1)
    _, _, alpha_at, traj = m.aci_walk(f, lo, hi, 0.10)
    firsts = f.reset_index(drop=True).groupby("game", sort=False).indices
    for pos in firsts.values():
        assert alpha_at[int(np.min(pos))] == pytest.approx(0.10)
    assert len(traj) == 3 and all(t["status"] == "OK" for t in traj)


def test_short_game_returns_insufficient_and_keeps_static_band():
    f = _frame(n_games=1, n_ticks=20)                    # below aci_online's _MIN_STREAM_LEN
    lo = np.zeros(len(f))
    hi = np.ones(len(f))
    aci_lo, aci_hi, alpha_at, traj = m.aci_walk(f, lo, hi, 0.10)
    assert traj[0]["status"] == "INSUFFICIENT_DATA"
    assert np.array_equal(aci_lo, lo) and np.array_equal(aci_hi, hi)
    assert np.all(alpha_at == 0.10)


# --- calibration reads TRAIN only ------------------------------------------------------------

def test_calibrate_is_a_function_of_train_only():
    train = _frame(n_games=8, n_ticks=200, seed=1)
    q1, pooled1 = m.calibrate(train, "market", 0.10)
    q2, pooled2 = m.calibrate(train, "market", 0.10)
    assert q1 == q2 and pooled1 == pooled2
    assert pooled1 >= 0.0
    wide, _ = m.calibrate(train, "market", 0.20)          # a looser nominal -> a smaller quantile
    for cell in q1:
        assert wide[cell] <= q1[cell] + 1e-12


# --- the grouped-coverage measure ------------------------------------------------------------

def test_grouped_coverage_all_covered_and_none_covered():
    n = 2000
    rng = np.random.default_rng(11)
    p = rng.uniform(0.1, 0.9, n)
    y = (rng.uniform(size=n) < p).astype(float)
    wide = m.grouped_coverage(p, y, np.zeros(n), np.ones(n), 0.90)
    assert wide["coverage"] == 1.0 and wide["n_groups"] == 5 and wide["mean_miss"] == 0.0
    zero = m.grouped_coverage(p, y, p - 1e-9, p + 1e-9, 0.90)
    assert zero["coverage"] < 0.5 and zero["within_tolerance"] is False


def test_grouped_coverage_absent_below_two_groups():
    out = m.grouped_coverage(np.zeros(10), np.zeros(10), np.zeros(10), np.ones(10), 0.90)
    assert out["coverage"] is None and "absent_because" in out


# --- rails ------------------------------------------------------------------------------------

def test_bars_are_byte_identical_to_s97(monkeypatch=None):
    from scripts.platformkit.eval_gate import s97_nba_sensor_fusion as s97
    assert m.COVERAGE_TOL == s97.COVERAGE_TOL == 0.02
    assert m.COVERAGE_MIN_GROUP == s97.COVERAGE_MIN_GROUP == 400
    assert m.COVERAGE_MAX_GROUPS == s97.COVERAGE_MAX_GROUPS == 50
    assert m.NOMINALS == (0.90, 0.80) and s97.NOMINAL_COVERAGE == 0.90


def test_source_is_ascii_and_carries_no_edge_language():
    src = Path(m.__file__).read_bytes()
    assert all(c < 128 for c in src)
    low = src.decode("ascii").lower()
    for token in ("profit", "bankroll", "+18.38", "0.119", "+54", "78.11", "8.94", "54.57"):
        assert token not in low
    # the only "roi"/"edge" occurrence allowed is the disclaimer that denies both
    assert low.count("roi") == 1 and low.replace("ledger", "").count("edge") == 1
    assert "no $ / roi / edge claim" in low and "coverage is the\ndeliverable, not brier" in low
