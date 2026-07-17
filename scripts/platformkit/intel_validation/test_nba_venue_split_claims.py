"""Per-file tests for nba_venue_split_claims (Depth-wave-2 Lane D).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_venue_split_claims.py -q

Acceptance:
  1. Floor n_home>=10 AND n_away>=10 -- below-floor team excluded, honest count.
  2. Sorted desc by raw_value (home minus away ppg); entity_key="team".
  3. Validator VERIFIED end-to-end on the snapshot this test builds.
  4. Honest caveats + edge_claimed False, no forbidden edge words.
  5. Golden asserts: known top team present with expected diff.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_venue_split_claims as vs


@pytest.fixture()
def two_team_games(monkeypatch, tmp_path):
    """Synthetic 2-team fixture: AAA clears the n_home/n_away>=10 floor with
    a clean +5 home-court bump; BBB has only 8 home games (below floor)."""
    rows = []
    for i in range(12):
        rows.append({"home_abbr": "AAA", "away_abbr": "ZZZ", "home_score": 110.0, "away_score": 100.0})
        rows.append({"home_abbr": "ZZZ", "away_abbr": "AAA", "home_score": 100.0, "away_score": 105.0})
    for i in range(8):
        rows.append({"home_abbr": "BBB", "away_abbr": "ZZZ", "home_score": 108.0, "away_score": 100.0})
        rows.append({"home_abbr": "ZZZ", "away_abbr": "BBB", "home_score": 100.0, "away_score": 108.0})
    games = pd.DataFrame(rows)

    nba_dir = tmp_path / "basketball_nba"
    nba_dir.mkdir(parents=True)
    games.to_parquet(nba_dir / "espn_boxscores.parquet", index=False)
    # second source file empty-but-valid (same schema, zero rows) -- exercises
    # the two-file concat path without adding data.
    games.iloc[0:0].to_parquet(nba_dir / "espn_boxscores_2023_24.parquet", index=False)

    claims_dir = tmp_path / "intel_claims"
    claims_dir.mkdir(parents=True)
    monkeypatch.setattr(vs, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(vs, "_NBA_DIR", nba_dir)
    monkeypatch.setattr(vs, "_OUT_DIR", claims_dir)
    monkeypatch.setattr(vs, "_SNAPSHOT", claims_dir / "nba_venue_split_snapshot.parquet")
    return claims_dir


def test_floor_excludes_below_floor_team(two_team_games):
    snap = vs.build_snapshot()
    claim = vs.build_claim(snap)
    ranked_teams = {r["team"] for r in claim["ranking"]}
    assert "BBB" not in ranked_teams  # n_home=8 < FLOOR=10
    assert "AAA" in ranked_teams
    assert claim["n_excluded_below_floor"] == 1  # BBB only


def test_sorted_desc_and_entity_key(two_team_games):
    snap = vs.build_snapshot()
    claim = vs.build_claim(snap)
    assert claim["criteria"]["entity_key"] == "team"
    values = [r["value"] for r in claim["ranking"]]
    assert values == sorted(values, reverse=True)


def test_golden_top_team_diff(two_team_games):
    snap = vs.build_snapshot()
    claim = vs.build_claim(snap)
    aaa = next(r for r in claim["ranking"] if r["team"] == "AAA")
    # AAA home_ppg=110, away_ppg=105 (as away team it scores 105) -> diff=5.0
    assert aaa["value"] == 5.0
    assert aaa["n_home"] == 12
    assert aaa["n_away"] == 12


def test_validator_verifies_end_to_end(two_team_games):
    snap = vs.build_snapshot()
    vs.write_snapshot(snap, vs._SNAPSHOT)
    claim = vs.build_claim(snap)
    import scripts.platformkit.intel_validation.claims_validator as cv_mod
    orig_root = cv_mod.REPO_ROOT
    cv_mod.REPO_ROOT = vs.REPO_ROOT
    try:
        verdict = claims_validator.validate_claim(claim)
    finally:
        cv_mod.REPO_ROOT = orig_root
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_honest_caveats_and_edge_claimed_false(two_team_games):
    snap = vs.build_snapshot()
    claim = vs.build_claim(snap)
    assert claim["edge_claimed"] is False
    blob = json.dumps([claim["caveats"], claim["question"]]).lower()
    for word in ("roi", "pnl", "$", "bankroll"):
        assert word not in blob
    assert "descriptive" in blob
    assert "floor" in blob
