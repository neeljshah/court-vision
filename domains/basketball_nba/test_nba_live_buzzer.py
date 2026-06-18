"""domains.basketball_nba.test_nba_live_buzzer - per-file test for FIX 3 (NBA buzzer recal).

Verifies that NBAPredictor.predict_live does NOT apply the temperature recalibrator
to a DETERMINED final-buzzer surface: a decided win must report EXACTLY 1.0 (not
0.9999) and a buzzer tie must stay 0.5. The temperature map is for live PROBABILISTIC
forecasts; a finished result is deterministic and must pass through untouched.

We drive predict_live with a tiny synthetic 2-game box so the predictor builds without
the full corpus and self.live_temp is exercised (it stays identity on a tiny corpus, so
to PROVE the skip we force a non-identity temperature on the instance).

HONEST: calibration/coherence only; no $ edge asserted. Run ONLY this file:
    python -m pytest domains/basketball_nba/test_nba_live_buzzer.py -q -s
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.predictor import NBAPredictor


def _mini_predictor() -> NBAPredictor:
    """Build NBAPredictor from a tiny in-memory box so no corpus is needed."""
    rows = []
    for i in range(8):
        rows.append({
            "home_abbr": "BOS", "away_abbr": "LAL",
            "home_pts": 112 + i, "away_pts": 104 + i,
            "home_fg_attempted": 88, "away_fg_attempted": 90,
            "home_ft_attempted": 20, "away_ft_attempted": 22,
            "home_oreb": 10, "away_oreb": 11, "home_tov": 13, "away_tov": 14,
        })
        rows.append({
            "home_abbr": "LAL", "away_abbr": "BOS",
            "home_pts": 100 + i, "away_pts": 108 + i,
            "home_fg_attempted": 90, "away_fg_attempted": 88,
            "home_ft_attempted": 22, "away_ft_attempted": 20,
            "home_oreb": 11, "away_oreb": 10, "home_tov": 14, "away_tov": 13,
        })
    return NBAPredictor(pd.DataFrame(rows))


def _live(p, elapsed, h, a):
    return p.predict_live("BOS", "LAL", elapsed, h, a)


def test_buzzer_win_is_exactly_one():
    """A decided game at 48' must report p_home_win == 1.0, NOT 0.9999."""
    p = _mini_predictor()
    p.live_temp = 1.45  # force a non-identity temp to PROVE the recal is skipped
    out = _live(p, 48.0, 110, 99)
    print(f"\nbuzzer win 110-99 @48' (T={p.live_temp}): p_home={out['p_home_win']} "
          f"raw={out['p_home_win_raw']}")
    assert out["p_home_win_raw"] == 1.0
    assert out["p_home_win"] == 1.0  # not 0.9999 -- recal skipped on a determined game
    away = _live(p, 48.0, 99, 110)
    assert away["p_home_win"] == 0.0


def test_buzzer_tie_stays_half():
    """A tie at the buzzer (-> OT, neutral 0.5) must stay exactly 0.5 after recal-skip."""
    p = _mini_predictor()
    p.live_temp = 1.45
    out = _live(p, 48.0, 100, 100)
    print(f"\nbuzzer tie 100-100 @48': p_home={out['p_home_win']}")
    assert out["p_home_win_raw"] == 0.5
    assert out["p_home_win"] == 0.5  # 0.5 is a fixed point of the temp map, must be untouched


def test_midgame_prob_still_recalibrated():
    """The skip must NOT disable recal for a genuine in-progress (non-0/1) forecast."""
    p = _mini_predictor()
    p.live_temp = 1.45
    out = _live(p, 24.0, 58, 55)
    # in-progress raw prob is strictly between 0 and 1 -> the temperature map IS applied,
    # so cal != raw (T != 1.0 shifts a non-extreme prob).
    print(f"\nmidgame 58-55 @24': raw={out['p_home_win_raw']} cal={out['p_home_win']}")
    assert 0.0 < out["p_home_win_raw"] < 1.0
    assert out["p_home_win"] != out["p_home_win_raw"]
