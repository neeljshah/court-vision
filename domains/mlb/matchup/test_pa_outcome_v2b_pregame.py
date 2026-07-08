"""Per-file tests for pa_outcome_v2b_pregame. Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/mlb/matchup/test_pa_outcome_v2b_pregame.py -q

Fast (no real corpus IO) -- the real end-to-end run is `python -m
domains.mlb.matchup.pa_outcome_v2b_pregame` (minutes), exercised separately.

Acceptance criteria:
  (a) as-of leak guard: on a 2-date toy, the day-2 expanding share reflects
      ONLY day-1 counts, not day-2's own (proven on the value, since
      _expanding_asof_share takes pre-aggregated counts directly -- no IO to
      stub).
  (b) a pitcher's first-ever game_date (no prior history) gets NaN, not 0 or
      any other silently-wrong number -- imputation to a neutral value is the
      caller's (add_v2b_features's) job, not this function's.
  (c) verdict_rule (reused from pa_outcome_v2) still returns NULL when the
      candidate ties the baseline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.matchup import pa_outcome_v2b_pregame as m


def test_asof_leak_guard_day2_reflects_only_day1():
    daily = pd.DataFrame({
        "pitcher": [1, 1],
        "game_date": ["2022-04-01", "2022-04-08"],
        "n_ahead": [10, 10],
        "n_breaking_ahead": [3, 7],
    })
    out = m._expanding_asof_share(daily).set_index("game_date")

    day2_share = out.loc["2022-04-08", "pitcher_ahead_breaking_share_asof"]
    assert day2_share == 0.3, (
        f"day-2 as-of share must equal day-1's 3/10=0.3 (STRICTLY prior), got {day2_share}"
    )


def test_first_appearance_is_nan_not_zero():
    daily = pd.DataFrame({
        "pitcher": [1, 1],
        "game_date": ["2022-04-01", "2022-04-08"],
        "n_ahead": [10, 10],
        "n_breaking_ahead": [3, 7],
    })
    out = m._expanding_asof_share(daily).set_index("game_date")

    day1_share = out.loc["2022-04-01", "pitcher_ahead_breaking_share_asof"]
    assert np.isnan(day1_share), (
        f"a pitcher's first game_date has no prior history -- expected NaN, got {day1_share}"
    )


def test_verdict_rule_null_when_candidate_ties_baseline():
    tied = m.verdict_rule(league_ll=1.9, profiles_ll=1.5, candidate_ll=1.5,
                           profiles_brier_ipo=0.2, candidate_brier_ipo=0.2)
    assert tied == "NULL"

    improved = m.verdict_rule(league_ll=1.9, profiles_ll=1.5, candidate_ll=1.4,
                               profiles_brier_ipo=0.2, candidate_brier_ipo=0.19)
    assert improved == "SHIP_PROVISIONAL"
