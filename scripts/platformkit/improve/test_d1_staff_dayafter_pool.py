"""Per-file test for improve.d1_staff_dayafter_pool. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_d1_staff_dayafter_pool.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.improve import d1_staff_dayafter_pool as pool


def test_welch_ci_excludes_zero_for_clearly_separated_groups():
    rng = np.random.default_rng(1)
    high = pd.Series(rng.normal(5.0, 0.01, 50))  # tiny variance, not zero (avoids Welch-Satterthwaite div/0)
    low = pd.Series(rng.normal(1.0, 0.01, 50))
    ci = pool._welch_ci(high, low)
    assert ci["effect"] > 3.9
    assert ci["ci_lo"] > 0 and ci["ci_hi"] > 0  # near-degenerate variance -> tight CI, both bounds positive


def test_welch_ci_straddles_zero_when_groups_overlap_heavily():
    rng = np.random.default_rng(0)
    high = pd.Series(rng.normal(5.0, 3.0, 40))
    low = pd.Series(rng.normal(4.9, 3.0, 40))
    ci = pool._welch_ci(high, low)
    assert ci["ci_lo"] < 0 < ci["ci_hi"]


def test_pooled_test_concats_all_seasons_and_matches_row_count(monkeypatch):
    def fake_pairs(season):
        n = 100
        return pd.DataFrame({
            "team": ["A"] * n, "game_date": pd.date_range("2025-01-01", periods=n),
            "prior_day_pitches": np.linspace(100, 200, n),
            "next_runs_allowed": np.linspace(3, 6, n) if season == 2023 else np.linspace(4, 4, n),
        })
    monkeypatch.setattr(pool, "_season_pairs", fake_pairs)
    r = pool._pooled_test([2023, 2024])
    assert r["seasons"] == [2023, 2024]
    assert r["n"] > 0  # top/bottom quartile of the pooled 200 rows
