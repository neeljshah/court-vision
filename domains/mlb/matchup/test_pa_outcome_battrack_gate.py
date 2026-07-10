"""Per-file tests for pa_outcome_battrack_gate. Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/mlb/matchup/test_pa_outcome_battrack_gate.py -q

Fast (no real corpus IO -- synthetic frames only). The real end-to-end run
is `python -m domains.mlb.matchup.pa_outcome_battrack_gate` (loads the real
snapshot + corpus), exercised separately.

Acceptance criteria:
  (a) n_usable == 0 (no row survives the TRAILING_COLS dropna) -> NOT_TESTABLE,
      never a fabricated model fit.
  (b) 0 < n_usable < min_usable_n -> UNDERPOWERED, still no fit attempted.
  (c) enough usable rows spanning both seasons -> the reused
      _fit_calibrated_histgb path actually runs and returns a real verdict.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.matchup import pa_outcome_battrack_gate as m
from domains.mlb.matchup.pa_outcome_model import BUCKETS
from domains.mlb.matchup.pa_outcome_v2 import PROFILE_FEATURES


def _synthetic_feats(n_per_season: int = 50, with_trailing: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    frames = []
    for season, start in ((2022, "2022-04-01"), (2023, "2023-04-01")):
        n = n_per_season
        df = pd.DataFrame({col: rng.random(n) for col in PROFILE_FEATURES})
        df["platoon_match"] = (rng.random(n) > 0.5).astype(int)
        df["season"] = season
        df["bucket"] = [BUCKETS[i % len(BUCKETS)] for i in range(n)]
        df["game_date"] = pd.date_range(start, periods=n, freq="D")
        if with_trailing:
            df["avg_bat_speed"] = rng.normal(75, 3, n)
            df["swing_length"] = rng.normal(7.5, 0.5, n)
        else:
            df["avg_bat_speed"] = np.nan
            df["swing_length"] = np.nan
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_zero_usable_is_not_testable():
    feats = _synthetic_feats(with_trailing=False)
    report = m._gate(feats, min_usable_n=500, seasons=(2022, 2023))
    assert report["verdict"] == "NOT_TESTABLE"
    assert report["n_usable"] == 0


def test_below_floor_is_underpowered():
    feats = _synthetic_feats(n_per_season=5, with_trailing=True)
    report = m._gate(feats, min_usable_n=500, seasons=(2022, 2023))
    assert report["verdict"] == "UNDERPOWERED"
    assert 0 < report["n_usable"] < 500


def test_enough_usable_rows_runs_the_real_fit():
    # n=150/season so the isotonic calib tail (last 20% of train) clears
    # StratifiedKFold(5)'s "5+ rows per class" floor across all 5 buckets.
    feats = _synthetic_feats(n_per_season=150, with_trailing=True)
    report = m._gate(feats, min_usable_n=40, seasons=(2022, 2023))
    assert report["verdict"] in ("ADDS_SIGNAL", "NULL")
    assert report["n_train"] == 150 and report["n_test"] == 150
    assert isinstance(report["baseline_log_loss"], float)
    assert isinstance(report["candidate_log_loss"], float)


def demo() -> None:
    test_zero_usable_is_not_testable()
    test_below_floor_is_underpowered()
    test_enough_usable_rows_runs_the_real_fit()
    print("pa_outcome_battrack_gate demo: all checks passed")


if __name__ == "__main__":
    demo()
