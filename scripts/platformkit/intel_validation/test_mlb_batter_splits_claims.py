"""Per-file tests for mlb_batter_splits_claims (mlb_batter_splits, Family 3).
Synthetic gamelogs + synthetic game-map frames (no data/ corpus needed) --
hand-computed home/away resolution (incl. the OAK->ATH alias), rest-bucket
math, floor exclusion, and an independent claims_validator round-trip.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_mlb_batter_splits_claims.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import mlb_batter_splits_claims as msc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _game_map():
    return pd.DataFrame([
        {"game_pk": 1, "home_team": "NYY", "away_team": "BOS"},
        {"game_pk": 2, "home_team": "BOS", "away_team": "NYY"},
        {"game_pk": 3, "home_team": "ATH", "away_team": "SEA"},  # team recorded as OAK below
    ])


def test_team_alias_resolves_oak_to_ath():
    gl = pd.DataFrame([
        {"player_id": 1, "player": "Gamma", "date": pd.Timestamp("2024-01-01"), "team": "OAK",
         "game_pk": 3, "homeRuns": 1, "rbi": 1, "hits": 1, "atBats": 4, "strikeOuts": 0,
         "totalBases": 1, "baseOnBalls": 0, "hitByPitch": 0},
    ])
    result = _prep(gl)
    assert result.loc[0, "loc"] == "home"  # OAK normalized to ATH, matches home_team


def _prep(gl_df):
    """Call the module's real _prep_gamelogs against an in-memory gamelogs
    frame written to a tmp parquet (the function reads from a path)."""
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".parquet")
    os.close(fd)
    try:
        gl_df.to_parquet(path)
        return msc._prep_gamelogs(path, _game_map())
    finally:
        os.remove(path)


def test_rest_bucket_b2b_and_rested_and_excluded_gap():
    gl = pd.DataFrame([
        {"player_id": 5, "player": "Delta", "date": pd.Timestamp("2024-05-01"), "team": "NYY",
         "game_pk": 1, "homeRuns": 0, "rbi": 0, "hits": 0, "atBats": 3, "strikeOuts": 1,
         "totalBases": 0, "baseOnBalls": 0, "hitByPitch": 0},
        {"player_id": 5, "player": "Delta", "date": pd.Timestamp("2024-05-02"), "team": "NYY",
         "game_pk": 2, "homeRuns": 0, "rbi": 0, "hits": 0, "atBats": 3, "strikeOuts": 1,
         "totalBases": 0, "baseOnBalls": 0, "hitByPitch": 0},  # diff=1 day -> rest_days=0 -> b2b
        {"player_id": 5, "player": "Delta", "date": pd.Timestamp("2024-05-05"), "team": "NYY",
         "game_pk": 1, "homeRuns": 0, "rbi": 0, "hits": 0, "atBats": 3, "strikeOuts": 1,
         "totalBases": 0, "baseOnBalls": 0, "hitByPitch": 0},  # diff=3 days -> rest_days=2 -> rested
    ])
    result = _prep(gl)
    assert list(result["rest_bucket"]) == [None, "b2b", "rested"]  # first row has no prior game


def test_delta_claim_hand_computed_and_validator_verified():
    # player 1: home cell 25 games avg .400 (100 hits/250 AB), away cell 25 games avg .200 (50/250)
    # both >= floor 20 -> delta(avg) = .400-.200 = .200
    hi = pd.DataFrame({
        "player_id": [1], "n_games_hi": [25], "sum_hr_hi": [10], "sum_rbi_hi": [20],
        "sum_hits_hi": [100], "sum_ab_hi": [250], "sum_k_hi": [50], "sum_tb_hi": [150],
        "sum_pa_hi": [270],
    })
    lo = pd.DataFrame({
        "player_id": [1], "n_games_lo": [25], "sum_hr_lo": [2], "sum_rbi_lo": [5],
        "sum_hits_lo": [50], "sum_ab_lo": [250], "sum_k_lo": [80], "sum_tb_lo": [60],
        "sum_pa_lo": [270],
    })
    joined = hi.merge(lo, on="player_id")

    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".parquet")
    os.close(fd)
    try:
        joined.to_parquet(path)
        from pathlib import Path
        claim = msc.build_delta_claim("avg", "home_away", Path(path), {1: "Epsilon"})
        assert claim["ranking"][0]["value"] == pytest.approx(0.2)
        assert claim["n_excluded_below_floor"] == 0
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", verdict.reason
    finally:
        os.remove(path)


def test_floor_excludes_below_threshold_player():
    hi = pd.DataFrame({
        "player_id": [1, 2], "n_games_hi": [25, 5], "sum_hr_hi": [10, 1], "sum_rbi_hi": [20, 1],
        "sum_hits_hi": [100, 5], "sum_ab_hi": [250, 20], "sum_k_hi": [50, 5], "sum_tb_hi": [150, 5],
        "sum_pa_hi": [270, 21],
    })
    lo = pd.DataFrame({
        "player_id": [1, 2], "n_games_lo": [25, 25], "sum_hr_lo": [2, 2], "sum_rbi_lo": [5, 5],
        "sum_hits_lo": [50, 50], "sum_ab_lo": [250, 250], "sum_k_lo": [80, 80], "sum_tb_lo": [60, 60],
        "sum_pa_lo": [270, 270],
    })
    joined = hi.merge(lo, on="player_id")
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".parquet")
    os.close(fd)
    try:
        joined.to_parquet(path)
        from pathlib import Path
        claim = msc.build_delta_claim("hr_rate", "rest", Path(path), {})
        ranked_ids = [r["player_id"] for r in claim["ranking"]]
        assert ranked_ids == [1]  # player 2's n_games_hi=5 < floor=20
        assert claim["n_excluded_below_floor"] == 1
    finally:
        os.remove(path)


def test_no_edge_language():
    joined = pd.DataFrame({
        "player_id": [1], "n_games_hi": [25], "sum_hr_hi": [10], "sum_rbi_hi": [20],
        "sum_hits_hi": [100], "sum_ab_hi": [250], "sum_k_hi": [50], "sum_tb_hi": [150],
        "sum_pa_hi": [270], "n_games_lo": [25], "sum_hr_lo": [2], "sum_rbi_lo": [5],
        "sum_hits_lo": [50], "sum_ab_lo": [250], "sum_k_lo": [80], "sum_tb_lo": [60], "sum_pa_lo": [270],
    })
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".parquet")
    os.close(fd)
    try:
        joined.to_parquet(path)
        from pathlib import Path
        claim = msc.build_delta_claim("avg", "home_away", Path(path), {1: "Epsilon"})
        text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
        for banned in ("18.38", "0.119", "+54%", "78.11", "roi", "bankroll", "pnl"):
            assert banned not in text
        assert claim["edge_claimed"] is False
    finally:
        os.remove(path)
