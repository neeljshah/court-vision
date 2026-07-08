"""Per-file tests for pa_outcome_v2. Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/mlb/matchup/test_pa_outcome_v2.py -q

Fast (no real corpus IO) -- the real end-to-end run is `python -m
domains.mlb.matchup.pa_outcome_v2` (minutes), exercised separately.

Acceptance criteria:
  (a) on a separable synthetic toy, the HistGB+calibration fit beats the
      plain league-marginal baseline on held-out log_loss.
  (b) IN_PLAY_OUT per-class Brier is computed and finite.
  (c) leak guard: build_platoon_breaking_lookup only ever requests the
      TRAIN season from load_pa_rows -- proven by substituting a season-
      capturing stand-in and checking what it was called with, not by
      inspecting output (a 2023-row could coincidentally look like a
      2022-row; the call itself is the guard).
  (d) verdict_rule returns NULL when candidate ties the baseline (a
      strict-improvement requirement, not >=).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.matchup import pa_outcome_model
from domains.mlb.matchup import pa_outcome_v2 as m


def _separable_frame(n_per_bucket: int, seed: int, with_dates: bool) -> pd.DataFrame:
    """One numeric feature ('signal') that cleanly separates the 5 buckets,
    row order shuffled so an assigned game_date does not correlate with
    bucket (else the temporal calibration tail could miss a whole class)."""
    rng = np.random.RandomState(seed)
    rows = []
    for i, b in enumerate(pa_outcome_model.BUCKETS):
        for _ in range(n_per_bucket):
            rows.append((b, i * 10.0 + rng.normal(0, 0.5)))
    rng.shuffle(rows)
    df = pd.DataFrame(rows, columns=["bucket", "signal"])
    if with_dates:
        df["game_date"] = pd.date_range("2022-01-01", periods=len(df)).strftime("%Y-%m-%d")
    return df


def test_calibrated_histgb_beats_league_marginal_on_separable_toy():
    train_df = _separable_frame(n_per_bucket=200, seed=0, with_dates=True)
    test_df = _separable_frame(n_per_bucket=60, seed=1, with_dates=False)

    league_ll = pa_outcome_model.fit_eval_layer(train_df, test_df, [])
    result = m._fit_calibrated_histgb(train_df, test_df, ["signal"])

    assert result["log_loss"] < league_ll, (
        f"candidate {result['log_loss']} did not beat league marginal {league_ll} "
        "on a deliberately separable toy dataset"
    )


def test_in_play_out_brier_is_finite():
    train_df = _separable_frame(n_per_bucket=200, seed=2, with_dates=True)
    test_df = _separable_frame(n_per_bucket=60, seed=3, with_dates=False)
    result = m._fit_calibrated_histgb(train_df, test_df, ["signal"])
    assert "IN_PLAY_OUT" in result["brier"]
    assert np.isfinite(result["brier"]["IN_PLAY_OUT"])


def test_leak_guard_platoon_lookup_only_requests_train_season():
    captured = {}

    def fake_load_pa_rows(seasons):
        captured["seasons"] = seasons
        # mirror platoon_context.load_pa_rows's OWN derived columns
        # (on_base/is_k) -- this stand-in replaces the loader, not the
        # aggregation it feeds.
        return pd.DataFrame({
            "batter": [1], "p_throws": ["R"], "pitch_type": ["FF"],
            "events": ["single"], "season": [seasons[0]],
            "on_base": [1], "is_k": [0],
        })

    original = m.load_pa_rows
    m.load_pa_rows = fake_load_pa_rows
    try:
        m.build_platoon_breaking_lookup(train_season=2022)
    finally:
        m.load_pa_rows = original

    assert captured["seasons"] == (2022,), (
        "build_platoon_breaking_lookup must request ONLY the train season -- "
        f"it requested {captured.get('seasons')}"
    )


def test_verdict_rule_null_when_candidate_ties_baseline():
    tied = m.verdict_rule(league_ll=1.9, profiles_ll=1.5, candidate_ll=1.5,
                           profiles_brier_ipo=0.2, candidate_brier_ipo=0.2)
    assert tied == "NULL"

    improved = m.verdict_rule(league_ll=1.9, profiles_ll=1.5, candidate_ll=1.4,
                               profiles_brier_ipo=0.2, candidate_brier_ipo=0.19)
    assert improved == "SHIP_PROVISIONAL"
