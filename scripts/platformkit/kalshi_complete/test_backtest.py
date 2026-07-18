"""Synthetic tests for backtest.py grading -- no parquet/data/ access needed.
Run: python -m pytest scripts/platformkit/kalshi_complete/test_backtest.py -q
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.platformkit.kalshi_complete import backtest as bt


def _synthetic_frame(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p_close = rng.uniform(0.35, 0.65, size=n)
    y = rng.binomial(1, p_close).astype(float)
    # model = close plus small noise -> should MATCH/TRAIL, never wildly beat
    p_model = np.clip(p_close + rng.normal(0, 0.03, size=n), 0.02, 0.98)
    return pd.DataFrame({"p_model": p_model, "p_close": p_close, "y": y})


def test_grade_frame_data_limited_below_min_n():
    rep = bt.grade_frame(_synthetic_frame(n=10), min_n=60)
    assert rep["status"] == "data_limited"
    assert rep["edge_claimed"] is False


def test_grade_frame_shape_and_paired_delta():
    df = _synthetic_frame(n=300)
    rep = bt.grade_frame(df)
    assert rep["status"] == "ok"
    assert rep["n"] == 300 and rep["n_holdout"] == 150
    assert rep["verdict"] in ("MATCHES_CLOSE_WITHIN_NOISE", "TRAILS_CLOSE")
    lo, hi = rep["brier_gap_ci95"]
    assert lo <= hi
    assert 0.0 <= rep["quote_containment_rate"] <= 1.0
    assert rep["edge_claimed"] is False


def test_grade_frame_containment_counts_within_band():
    # p_model == p_close exactly -> close always inside the band (band centers on p_model)
    n = 120
    p = np.linspace(0.1, 0.9, n)
    df = pd.DataFrame({"p_model": p, "p_close": p, "y": (p > 0.5).astype(float)})
    rep = bt.grade_frame(df)
    assert rep["quote_containment_rate"] == 1.0


def test_no_dollar_tokens_in_output():
    rep = bt.grade_frame(_synthetic_frame(n=300))
    dumped = json.dumps(rep).lower()
    for banned in ("roi", "profit", "bankroll", "pnl"):
        assert banned not in dumped, f"found banned token: {banned}"


def test_run_backtest_not_supported_sport():
    rep = bt.run_backtest("soccer")
    assert rep["status"] == "not_supported"
    assert rep["edge_claimed"] is False


if __name__ == "__main__":
    test_grade_frame_data_limited_below_min_n()
    test_grade_frame_shape_and_paired_delta()
    test_grade_frame_containment_counts_within_band()
    test_no_dollar_tokens_in_output()
    test_run_backtest_not_supported_sport()
    print("backtest synthetic checks OK")
