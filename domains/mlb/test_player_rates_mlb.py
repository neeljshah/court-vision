"""Per-file tests for domains/mlb/player_rates_mlb.py (canned in-memory df).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_player_rates_mlb.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.player_rates_mlb import (
    SHRINK_K,
    batter_rate,
    is_pitcher_stat,
    pitcher_rate,
)


def _batter_df():
    # Two prior games for player A + one post-as_of game (must be ignored).
    # League also has player B to make a baseline.
    rows = [
        # player A, before as_of
        dict(date="2026-05-01", player_id="A", is_pitcher=False, atBats=4,
             baseOnBalls=1, hitByPitch=0, hits=2, totalBases=3, runs=1, rbi=1,
             homeRuns=0, strikeOuts=1, stolenBases=0),
        dict(date="2026-05-03", player_id="A", is_pitcher=False, atBats=3,
             baseOnBalls=0, hitByPitch=0, hits=1, totalBases=1, runs=0, rbi=0,
             homeRuns=0, strikeOuts=2, stolenBases=0),
        # player A, AFTER as_of -> leak; must be excluded
        dict(date="2026-06-01", player_id="A", is_pitcher=False, atBats=5,
             baseOnBalls=0, hitByPitch=0, hits=5, totalBases=20, runs=5, rbi=9,
             homeRuns=5, strikeOuts=0, stolenBases=0),
        # player B (league filler), before as_of
        dict(date="2026-05-02", player_id="B", is_pitcher=False, atBats=4,
             baseOnBalls=0, hitByPitch=0, hits=1, totalBases=1, runs=0, rbi=0,
             homeRuns=0, strikeOuts=1, stolenBases=0),
    ]
    return pd.DataFrame(rows)


def test_batter_hits_per_pa_handchecked_and_leakfree():
    df = _batter_df()
    # Player A before 2026-06-01: PA = (4+1+0)+(3+0+0) = 8; hits = 2+1 = 3.
    # raw per_pa = 3/8 = 0.375. Post-as_of game (5 hits) MUST be ignored.
    res = batter_rate(df, "A", "Hits", as_of="2026-06-01")
    assert res["status"] == "ok"
    assert res["n_pa"] == 8
    # League baseline (all batters before as_of): hits 3+1=4 over PA 8+4=12 = 0.3333
    baseline = 4.0 / 12.0
    raw = 3.0 / 8.0
    expected = (8 * raw + SHRINK_K * baseline) / (8 + SHRINK_K)
    assert abs(res["per_pa"] - expected) < 1e-9
    assert res["shrunk"] is True


def test_thin_batter_shrinks_toward_baseline():
    df = _batter_df()
    # A thin player with 1 PA and 1 hit (raw=1.0) should be pulled hard toward the
    # league baseline because n_pa(1) << SHRINK_K(30).
    thin = pd.concat([df, pd.DataFrame([dict(
        date="2026-05-04", player_id="C", is_pitcher=False, atBats=1,
        baseOnBalls=0, hitByPitch=0, hits=1, totalBases=1, runs=0, rbi=0,
        homeRuns=0, strikeOuts=0, stolenBases=0)])], ignore_index=True)
    res = batter_rate(thin, "C", "Hits", as_of="2026-06-01")
    assert res["status"] == "ok"
    assert res["per_pa"] < 0.5  # nowhere near the raw 1.0; shrunk to ~baseline


def _pitcher_df():
    rows = [
        dict(date="2026-05-01", player_id="P", is_pitcher=True, battersFaced=25,
             pitch_strikeOuts=8, earnedRuns=2, hits_allowed=5,
             baseOnBalls_allowed=1, outs=18),
        dict(date="2026-05-06", player_id="P", is_pitcher=True, battersFaced=24,
             pitch_strikeOuts=6, earnedRuns=3, hits_allowed=6,
             baseOnBalls_allowed=2, outs=18),
        # post as_of -> leak
        dict(date="2026-06-10", player_id="P", is_pitcher=True, battersFaced=30,
             pitch_strikeOuts=15, earnedRuns=0, hits_allowed=0,
             baseOnBalls_allowed=0, outs=27),
        # league filler pitcher
        dict(date="2026-05-02", player_id="Q", is_pitcher=True, battersFaced=20,
             pitch_strikeOuts=4, earnedRuns=4, hits_allowed=8,
             baseOnBalls_allowed=3, outs=12),
    ]
    return pd.DataFrame(rows)


def test_pitcher_strikeouts_per_bf_leakfree():
    df = _pitcher_df()
    # P before 2026-06-01: BF = 25+24 = 49; K = 8+6 = 14; raw = 14/49.
    res = pitcher_rate(df, "P", "Pitcher Strikeouts", as_of="2026-06-01")
    assert res["status"] == "ok"
    assert res["n_bf"] == 49
    raw = 14.0 / 49.0
    # league baseline: K (14+4)=18 over BF (49+20)=69
    baseline = 18.0 / 69.0
    expected = (49 * raw + SHRINK_K * baseline) / (49 + SHRINK_K)
    assert abs(res["per_bf"] - expected) < 1e-9


def test_pitcher_outs_is_per_start():
    df = _pitcher_df()
    res = pitcher_rate(df, "P", "Outs", as_of="2026-06-01")
    assert res["status"] == "ok"
    assert "per_start" in res and res["n_start"] == 2
    # P outs before as_of: 18+18 = 36 over 2 starts = 18 raw; baseline (36+12)/3=16
    raw = 36.0 / 2.0
    baseline = 48.0 / 3.0
    from domains.mlb.player_rates_mlb import SHRINK_K_START
    expected = (2 * raw + SHRINK_K_START * baseline) / (2 + SHRINK_K_START)
    assert abs(res["per_start"] - expected) < 1e-9


def test_unknown_player_and_stat():
    df = _batter_df()
    # No data for this player and no league signal pre-2000 -> unknown.
    assert batter_rate(df, "ZZ", "Hits", as_of="2000-01-01")["status"] == "unknown"
    # Bad / pitcher stat passed to batter_rate -> unknown.
    assert batter_rate(df, "A", "Outs", as_of="2026-06-01")["status"] == "unknown"
    assert batter_rate(df, "A", "NotAStat", as_of="2026-06-01")["status"] == "unknown"


def test_is_pitcher_stat_routing():
    assert is_pitcher_stat("Pitcher Strikeouts") is True
    assert is_pitcher_stat("Outs") is True
    assert is_pitcher_stat("Hits") is False
    assert is_pitcher_stat("NotAStat") is False
