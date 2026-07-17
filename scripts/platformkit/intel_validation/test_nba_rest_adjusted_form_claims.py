"""Per-file tests for nba_rest_adjusted_form_claims (light lane, mirrors
test_nba_venue_split_claims.py).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_rest_adjusted_form_claims.py -q

Acceptance:
  1. Floor n_short>=8 AND n_long>=8 -- below-floor team excluded, honest count.
  2. Sorted asc by raw_value (short-rest minus long-rest ppg); entity_key="team".
  3. Validator VERIFIED end-to-end on the snapshot this test builds.
  4. Honest caveats + edge_claimed False, no forbidden edge words.
  5. Golden asserts: known team present with expected diff + rest-day math.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_rest_adjusted_form_claims as rf


def _team_rows(team: str, start: pd.Timestamp, short_n: int, long_n: int) -> list[dict]:
    """short_n games on 1-day gaps (rest_days=0, score=100) then long_n games
    on 4-day gaps (rest_days=3, score=110). First game of the block has no
    prior date (unknown rest, excluded); every subsequent gap in the short
    run yields short_n-1 short readings and every subsequent gap in the long
    run (including the short->long transition) yields long_n long readings."""
    rows = []
    date = start
    for _ in range(short_n):
        rows.append({"date": date, "home_abbr": team, "away_abbr": "ZZZ", "home_score": 100.0, "away_score": 95.0})
        date = date + pd.Timedelta(days=1)
    date = date - pd.Timedelta(days=1) + pd.Timedelta(days=4)  # transition gap = 4 days -> long
    for _ in range(long_n):
        rows.append({"date": date, "home_abbr": team, "away_abbr": "ZZZ", "home_score": 110.0, "away_score": 95.0})
        date = date + pd.Timedelta(days=4)
    return rows


@pytest.fixture()
def rest_gap_games(monkeypatch, tmp_path):
    """Synthetic 2-team fixture. AAA: 9 games on 1-day gaps (8 short-rest
    readings, score=100) then 8 games on 4-day gaps (8 long-rest readings,
    score=110) -- a clean -10 short-minus-long dip. BBB: only 6 games on
    1-day gaps (5 short-rest readings, below the n_short>=8 floor)."""
    rows = _team_rows("AAA", pd.Timestamp("2024-11-01"), short_n=9, long_n=8)
    rows += _team_rows("BBB", pd.Timestamp("2025-01-01"), short_n=6, long_n=8)
    games = pd.DataFrame(rows)

    nba_dir = tmp_path / "basketball_nba"
    nba_dir.mkdir(parents=True)
    games.to_parquet(nba_dir / "espn_boxscores.parquet", index=False)
    # second source file empty-but-valid (same schema, zero rows) -- exercises
    # the two-file concat path without adding data.
    games.iloc[0:0].to_parquet(nba_dir / "espn_boxscores_2023_24.parquet", index=False)

    claims_dir = tmp_path / "intel_claims"
    claims_dir.mkdir(parents=True)
    monkeypatch.setattr(rf, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rf, "_NBA_DIR", nba_dir)
    monkeypatch.setattr(rf, "_OUT_DIR", claims_dir)
    monkeypatch.setattr(rf, "_SNAPSHOT", claims_dir / "nba_rest_adjusted_form_snapshot.parquet")
    return claims_dir


def test_floor_excludes_below_floor_team(rest_gap_games):
    snap = rf.build_snapshot()
    claim = rf.build_claim(snap)
    ranked_teams = {r["team"] for r in claim["ranking"]}
    assert "BBB" not in ranked_teams  # n_short=6 < FLOOR=8
    assert "AAA" in ranked_teams
    assert claim["n_excluded_below_floor"] == 1  # BBB only


def test_sorted_asc_and_entity_key(rest_gap_games):
    snap = rf.build_snapshot()
    claim = rf.build_claim(snap)
    assert claim["criteria"]["entity_key"] == "team"
    values = [r["value"] for r in claim["ranking"]]
    assert values == sorted(values)


def test_golden_top_team_diff(rest_gap_games):
    snap = rf.build_snapshot()
    claim = rf.build_claim(snap)
    aaa = next(r for r in claim["ranking"] if r["team"] == "AAA")
    # AAA scores 100 on short rest (0-1 days), 110 on long rest -> diff=-10.0
    assert aaa["value"] == -10.0
    assert aaa["n_short"] == 8
    assert aaa["n_long"] == 8


def test_validator_verifies_end_to_end(rest_gap_games):
    snap = rf.build_snapshot()
    rf.write_snapshot(snap, rf._SNAPSHOT)
    claim = rf.build_claim(snap)
    import scripts.platformkit.intel_validation.claims_validator as cv_mod
    orig_root = cv_mod.REPO_ROOT
    cv_mod.REPO_ROOT = rf.REPO_ROOT
    try:
        verdict = claims_validator.validate_claim(claim)
    finally:
        cv_mod.REPO_ROOT = orig_root
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_honest_caveats_and_edge_claimed_false(rest_gap_games):
    snap = rf.build_snapshot()
    claim = rf.build_claim(snap)
    assert claim["edge_claimed"] is False
    blob = json.dumps([claim["caveats"], claim["question"]]).lower()
    for word in ("roi", "pnl", "$", "bankroll"):
        assert word not in blob
    assert "descriptive" in blob
    assert "floor" in blob
