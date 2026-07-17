"""Per-file tests for soccer_team_venue_split_claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_soccer_team_venue_split_claims.py -q

Acceptance:
  1. Floor n_home>=20 AND n_away>=20 -- below-floor team excluded, honest count.
  2. Sorted desc; entity_key="team"; sign normalized ("home minus away").
  3. Validator VERIFIED end-to-end on the snapshot this test builds, for all 3 metrics.
  4. Honest caveats + edge_claimed False, no forbidden edge words.
  5. Golden asserts: known team's three diffs match hand-computed values.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import soccer_team_venue_split_claims as vs


@pytest.fixture()
def two_team_matches(monkeypatch, tmp_path):
    """Synthetic fixture: AAA clears the n_home/n_away>=20 floor with a clean
    home-court bump (wins 3-1 at home, draws 1-1 away); BBB has only 15 home
    and 15 away games (below floor). ZZZ is the shared opponent."""
    rows = []
    for _ in range(25):
        rows.append({"home_team": "AAA", "away_team": "ZZZ", "fthg": 3, "ftag": 1, "ftr": "H"})
        rows.append({"home_team": "ZZZ", "away_team": "AAA", "fthg": 1, "ftag": 1, "ftr": "D"})
    for _ in range(15):
        rows.append({"home_team": "BBB", "away_team": "ZZZ", "fthg": 2, "ftag": 0, "ftr": "H"})
        rows.append({"home_team": "ZZZ", "away_team": "BBB", "fthg": 0, "ftag": 0, "ftr": "D"})
    matches = pd.DataFrame(rows)

    soccer_dir = tmp_path / "soccer"
    soccer_dir.mkdir(parents=True)
    matches.to_parquet(soccer_dir / "matches.parquet", index=False)

    claims_dir = tmp_path / "intel_claims"
    claims_dir.mkdir(parents=True)
    monkeypatch.setattr(vs, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(vs, "_SOCCER_DIR", soccer_dir)
    monkeypatch.setattr(vs, "_OUT_DIR", claims_dir)
    monkeypatch.setattr(vs, "_SNAPSHOT", claims_dir / "soccer_team_venue_split_snapshot.parquet")
    return claims_dir


def test_floor_excludes_below_floor_team(two_team_matches):
    snap = vs.build_snapshot()
    claims = vs.build_all_claims(snap)
    gf_claim = next(c for c in claims if c["criteria"]["metric"] == "gf_diff")
    ranked_teams = {r["team"] for r in gf_claim["ranking"]}
    assert "BBB" not in ranked_teams  # n_home=15 < FLOOR=20
    assert "AAA" in ranked_teams
    assert gf_claim["n_excluded_below_floor"] == 1  # BBB only (ZZZ clears the floor too)


def test_sorted_desc_and_entity_key(two_team_matches):
    snap = vs.build_snapshot()
    claims = vs.build_all_claims(snap)
    assert len(claims) == 3
    for claim in claims:
        assert claim["criteria"]["entity_key"] == "team"
        values = [r["value"] for r in claim["ranking"]]
        assert values == sorted(values, reverse=True)


def test_golden_team_diffs(two_team_matches):
    snap = vs.build_snapshot()
    claims = vs.build_all_claims(snap)
    by_metric = {c["criteria"]["metric"]: c for c in claims}

    aaa_gf = next(r for r in by_metric["gf_diff"]["ranking"] if r["team"] == "AAA")
    aaa_ga = next(r for r in by_metric["ga_diff"]["ranking"] if r["team"] == "AAA")
    aaa_wr = next(r for r in by_metric["winrate_diff"]["ranking"] if r["team"] == "AAA")

    # AAA home: gf=3 ga=1 win=1.0 (25 games) | AAA away: gf=1 ga=1 win=0.0 (25 games)
    assert aaa_gf["value"] == 2.0   # 3 - 1
    assert aaa_ga["value"] == 0.0   # away_ga(1) - home_ga(1)
    assert aaa_wr["value"] == 1.0   # 1.0 - 0.0
    assert aaa_gf["n_home"] == 25 and aaa_gf["n_away"] == 25


def test_validator_verifies_end_to_end(two_team_matches):
    snap = vs.build_snapshot()
    vs.write_snapshot(snap, vs._SNAPSHOT)
    claims = vs.build_all_claims(snap)
    import scripts.platformkit.intel_validation.claims_validator as cv_mod
    orig_root = cv_mod.REPO_ROOT
    cv_mod.REPO_ROOT = vs.REPO_ROOT
    try:
        for claim in claims:
            verdict = claims_validator.validate_claim(claim)
            assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"
    finally:
        cv_mod.REPO_ROOT = orig_root


def test_honest_caveats_and_edge_claimed_false(two_team_matches):
    snap = vs.build_snapshot()
    claims = vs.build_all_claims(snap)
    for claim in claims:
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        for word in ("roi", "pnl", "$", "bankroll"):
            assert word not in blob
        assert "descriptive" in blob
        assert "floor" in blob
