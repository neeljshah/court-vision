"""Per-file tests for mlb_career_leaders_claims (mlb_career_counting_leaders,
Family 2). Synthetic gamelogs frame (no data/ corpus needed in this
worktree) -- hand-computed career sums, floor exclusion, active-only
variant, and an independent claims_validator round-trip.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_mlb_career_leaders_claims.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import mlb_career_leaders_claims as mcl
from scripts.platformkit.intel_validation.claims_validator import validate_claim

# Alpha: 2 games (2022, 2023) -> career_hr=3, last_season=2023.
# Beta: 1 game (2024, the corpus max) -> career_hr=5, last_season=2024=is_active.
_ROWS = [
    {"player_id": 1, "player": "Alpha", "date": pd.Timestamp("2022-04-10"), "game_pk": 100,
     "homeRuns": 1, "rbi": 2, "hits": 1, "doubles": 0, "triples": 0, "runs": 1,
     "stolenBases": 0, "baseOnBalls": 0, "strikeOuts": 1},
    {"player_id": 1, "player": "Alpha", "date": pd.Timestamp("2023-05-01"), "game_pk": 101,
     "homeRuns": 2, "rbi": 1, "hits": 2, "doubles": 1, "triples": 0, "runs": 0,
     "stolenBases": 1, "baseOnBalls": 1, "strikeOuts": 0},
    {"player_id": 2, "player": "Beta", "date": pd.Timestamp("2024-06-01"), "game_pk": 200,
     "homeRuns": 5, "rbi": 3, "hits": 3, "doubles": 0, "triples": 1, "runs": 2,
     "stolenBases": 0, "baseOnBalls": 2, "strikeOuts": 2},
]


@pytest.fixture()
def synthetic_gamelogs(tmp_path):
    path = tmp_path / "gamelogs.parquet"
    pd.DataFrame(_ROWS).to_parquet(path)
    return path


def test_build_snapshot_career_sums_and_active_flag(synthetic_gamelogs):
    snap_path, report = mcl.build_snapshot(synthetic_gamelogs)
    wide = pd.read_parquet(snap_path).set_index("player_id")

    assert wide.loc[1, "career_hr"] == 3
    assert wide.loc[1, "n_games"] == 2
    assert wide.loc[1, "last_season"] == 2023
    assert wide.loc[1, "is_active"] == 0

    assert wide.loc[2, "career_hr"] == 5
    assert wide.loc[2, "n_games"] == 1
    assert wide.loc[2, "last_season"] == 2024
    assert wide.loc[2, "is_active"] == 1

    assert report["max_season"] == 2024
    assert report["n_players"] == 2
    assert report["n_active"] == 1


def test_full_population_ranking_ordered_desc_by_career_hr(synthetic_gamelogs):
    snap_path, report = mcl.build_snapshot(synthetic_gamelogs)
    claim = mcl._build_leaderboard_claim("career_hr", snap_path, report, active_only=False)
    assert [r["player_id"] for r in claim["ranking"]] == [2, 1]  # Beta (5) before Alpha (3)
    assert claim["n_considered"] == 2
    assert claim["n_excluded_below_floor"] == 0  # n_games>=1 floor excludes nobody here


def test_active_only_variant_excludes_inactive_player(synthetic_gamelogs):
    snap_path, report = mcl.build_snapshot(synthetic_gamelogs)
    claim = mcl._build_leaderboard_claim("career_hr", snap_path, report, active_only=True)
    assert [r["player_id"] for r in claim["ranking"]] == [2]  # only Beta is active
    assert claim["n_excluded_below_floor"] == 1  # Alpha excluded (not active)
    assert claim["criteria"]["metric"] == "career_hr_active"


def test_claims_independently_verify(synthetic_gamelogs):
    snap_path, report = mcl.build_snapshot(synthetic_gamelogs)
    for stat, _ in mcl._STAT_DIMS:
        for active_only in (False, True):
            claim = mcl._build_leaderboard_claim(stat, snap_path, report, active_only)
            verdict = validate_claim(claim)
            assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"


def test_no_edge_language_in_claims(synthetic_gamelogs):
    snap_path, report = mcl.build_snapshot(synthetic_gamelogs)
    claim = mcl._build_leaderboard_claim("career_hr", snap_path, report, active_only=False)
    text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
    for banned in ("18.38", "0.119", "+54%", "78.11", "roi", "bankroll", "pnl"):
        assert banned not in text
    assert claim["edge_claimed"] is False
