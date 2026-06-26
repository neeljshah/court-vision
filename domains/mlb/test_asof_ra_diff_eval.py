"""Per-file test for domains.mlb.asof_ra_diff_eval (sp_ra_diff_asof candidate gate).

Acceptance criteria
-------------------
1. build_candidate_frame (synthetic, no real-corpus touch):
   a. Left-merges sp_ra_diff_asof keyed on event_id; missing asof row -> NaN
      feature and _cov == False (honest NaN handling, never fabricated).
   b. Carries the required columns and stays chronologically sorted by date.
   c. p_base is a leak-free Elo probability in (0, 1).

2. _gate_once:
   a. Returns verdict in {'SHIP', 'REJECT'} (never None / missing).
   b. Reports brier_base, brier_cand, brier_delta, dm_p, feat_weight.
   c. No $ / P&L / ROI / edge field anywhere in the result dict.

3. _planted_null:
   a. A shuffled feature collapses (DM not significant) -> verdict REJECT.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_asof_ra_diff_eval.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb import asof_ra_diff_eval as mod


def _synthetic() -> tuple:
    """Two small synthetic frames: a games corpus + an asof sidecar (1 row absent)."""
    rng = np.random.default_rng(7)
    n = 400
    dates = pd.date_range("2015-04-01", periods=n, freq="D")
    teams = [f"T{i%8}" for i in range(n)]
    aways = [f"T{(i+3)%8}" for i in range(n)]
    eids = [f"{d.strftime('%Y%m%d')}-{h}-{a}-1" for d, h, a in zip(dates, teams, aways)]
    hr = rng.integers(0, 9, n)
    ar = rng.integers(0, 9, n)
    games = pd.DataFrame({
        "event_id": eids, "date": dates, "season": 2015,
        "home_team": teams, "away_team": aways,
        "home_runs": hr, "away_runs": ar,
        "target_home_win": (hr > ar).astype(float),
    })
    # asof sidecar: drop the last row (absent) so the merge must yield NaN + _cov False
    asof = pd.DataFrame({
        "event_id": eids[:-1],
        "sp_ra_diff_asof": rng.normal(0, 1.3, n - 1),
        "home_sp_starts_prior": rng.integers(0, 10, n - 1),
        "away_sp_starts_prior": rng.integers(0, 10, n - 1),
    })
    return games, asof


def test_build_candidate_frame_merge_and_nan():
    games, asof = _synthetic()
    df = mod.build_candidate_frame(games=games, asof=asof)
    for c in ("event_id", "target_home_win", "p_base",
              "sp_ra_diff_asof", "_cov"):
        assert c in df.columns
    # chronological
    assert df["date"].is_monotonic_increasing
    # the absent asof row -> NaN feature and _cov False (honest, not fabricated)
    last = df.iloc[-1]
    assert pd.isna(last["sp_ra_diff_asof"])
    assert not bool(last["_cov"])
    # p_base is a leak-free probability
    pb = df["p_base"].dropna().values
    assert np.all((pb > 0.0) & (pb < 1.0))


def test_gate_once_shape_and_no_dollar():
    games, asof = _synthetic()
    df = mod.build_candidate_frame(games=games, asof=asof)
    r = mod._gate_once(df)
    assert r["verdict"] in {"SHIP", "REJECT"}
    for k in ("brier_base", "brier_cand", "brier_delta", "dm_p", "feat_weight"):
        assert k in r
    banned = {"roi", "pnl", "p_l", "edge", "profit", "dollars", "units"}
    assert not (banned & {k.lower() for k in r})


def test_planted_null_collapses():
    games, asof = _synthetic()
    df = mod.build_candidate_frame(games=games, asof=asof)
    nn = mod._planted_null(df, seed=1)
    # a shuffled feature must NOT be a significant winner
    assert nn["verdict"] == "REJECT"
