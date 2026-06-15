"""Per-file tests for fusion_nba (run ONLY this file; full pytest freezes the box).
Run: python -m pytest scripts/platformkit/proof_nba/test_fusion_nba.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba import fusion_nba as F  # noqa: E402


def _toy(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    teams = ["AAA", "BBB", "CCC", "DDD"]
    rows = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        hp, ap = rng.integers(95, 125), rng.integers(95, 125)
        rows.append({"home_abbr": h, "away_abbr": a, "home_pts": float(hp), "away_pts": float(ap)})
    return pd.DataFrame(rows)


def test_margin_leakfree_first_game_zero():
    """First game's margin signal must be 0 (no prior history) -> no look-ahead."""
    df = _toy()
    sig = F._walk_forward_margin(df)
    assert sig[0] == 0.0
    assert len(sig) == len(df)
    assert np.all(np.isfinite(sig))


def test_margin_responds_to_history():
    """A team that keeps winning by a lot must develop a positive margin signal."""
    df = pd.DataFrame({
        "home_abbr": ["AAA", "AAA", "AAA"],
        "away_abbr": ["BBB", "BBB", "BBB"],
        "home_pts": [120.0, 120.0, 120.0],
        "away_pts": [100.0, 100.0, 100.0],
    })
    sig = F._walk_forward_margin(df)
    # game 0 -> 0; later games -> home (AAA, winning) net margin exceeds away (BBB) -> positive
    assert sig[0] == 0.0
    assert sig[2] > sig[1] > 0.0


def test_logistic_fits_separable():
    """The ridge logistic must learn a strongly separable 1-D signal (positive slope)."""
    rng = np.random.default_rng(1)
    x = rng.normal(size=400)
    y = (x + 0.1 * rng.normal(size=400) > 0).astype(float)
    X = np.column_stack([np.ones(len(x)), x])
    w = F._fit_logistic(X, y)
    assert w[1] > 0.5  # positive weight on the predictive feature


def test_fuse_is_leakfree_and_masked():
    """WF fuse emits NaN before _MIN_TRAIN and finite probs in [0,1] after."""
    rng = np.random.default_rng(2)
    n = 150
    elo_logit = rng.normal(scale=0.5, size=n)
    margin = elo_logit * 2 + rng.normal(scale=0.3, size=n)
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-elo_logit))).astype(float)
    fused, valid = F._walk_forward_fuse(elo_logit, margin, y)
    assert not valid[: F._MIN_TRAIN].any()
    assert valid[F._MIN_TRAIN:].all()
    assert np.all(np.isnan(fused[~valid]))
    fv = fused[valid]
    assert np.all((fv > 0) & (fv < 1))


def test_run_shape_and_honest_verdict():
    """run() returns the contract keys and an honest verdict_kind from the real corpus."""
    rep = F.run()
    if rep.get("status") != "ok":
        assert rep.get("status") == "data_limited"
        return
    for k in ("base_brier", "fused_brier", "close_brier", "gap_base_to_close",
              "gap_fused_to_close", "gap_narrowed_by_fusion", "verdict_kind"):
        assert k in rep
    assert rep["verdict_kind"] in {
        "narrows_gap", "calibration_win", "absorbed_null", "data_limited"}
    # the close is the comparison forecaster; it should be at least as sharp as base here
    assert rep["close_brier"] <= rep["base_brier"] + 1e-6
