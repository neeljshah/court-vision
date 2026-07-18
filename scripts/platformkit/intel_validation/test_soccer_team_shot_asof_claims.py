"""Per-file tests for soccer_team_shot_asof_claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_soccer_team_shot_asof_claims.py -q

Acceptance:
  1. Floor exclusion is COUNTED (below-floor team excluded, honest tally).
  2. As-of shift excludes self-match: the LAST match's own SoT never enters
     its own snapshot (the snapshot columns are the PRE-match as-of values
     the source builder already computed -- this proves the melt/tail(1)
     light-read never substitutes a post-match/realized number).
  3. Identity round-trip: validator independently recomputes the exact same
     values straight from the snapshot parquet + criteria.formula (VERIFIED).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import soccer_team_shot_asof_claims as sc


def _synthetic_joined() -> pd.DataFrame:
    """12 matches for AAA vs ZZZ (clears the n_prior>=10 floor at AAA's
    11th prior match), then a 13th (final, most-recent) match where AAA's
    own as-of SoT reads 99 -- a sentinel value that must NEVER appear as
    AAA's snapshot if the melt correctly reads the PRE-match as-of column
    (the source builder already guarantees home_sot_for_asof at a match
    excludes that match's own SoT; this fixture proves the melt preserves
    that, not that it re-derives it). BBB/YYY play only 3 matches (below
    floor)."""
    rows = []
    for i in range(12):
        rows.append({
            "event_id": f"m{i}", "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=i * 7),
            "home_team": "AAA", "away_team": "ZZZ",
            "home_sot_for_asof": 5.0, "home_sot_against_asof": 2.0,
            "home_shots_for_asof": 10.0, "home_shots_against_asof": 6.0,
            "home_sot_ratio_for_asof": 0.5, "home_sot_for_l10": 5.0,
            "away_sot_for_asof": 3.0, "away_sot_against_asof": 4.0,
            "away_shots_for_asof": 7.0, "away_shots_against_asof": 8.0,
            "away_sot_ratio_for_asof": 0.4, "away_sot_for_l10": 3.0,
            "home_n_prior": i, "away_n_prior": i,
            "home_corners_asof": 6.0, "away_corners_asof": 4.0,
            "home_n_prior_corners": i, "away_n_prior_corners": i,
        })
    # AAA's final (most-recent) match: sentinel 99 values -- these are the
    # AS-OF-ENTERING values (still pre-match, per the real builder's
    # contract), and must be what the snapshot reports for AAA, not the
    # 12th row's values.
    rows.append({
        "event_id": "m_last", "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=12 * 7),
        "home_team": "AAA", "away_team": "ZZZ",
        "home_sot_for_asof": 99.0, "home_sot_against_asof": 99.0,
        "home_shots_for_asof": 99.0, "home_shots_against_asof": 99.0,
        "home_sot_ratio_for_asof": 0.99, "home_sot_for_l10": 99.0,
        "away_sot_for_asof": 3.0, "away_sot_against_asof": 4.0,
        "away_shots_for_asof": 7.0, "away_shots_against_asof": 8.0,
        "away_sot_ratio_for_asof": 0.4, "away_sot_for_l10": 3.0,
        "home_n_prior": 12, "away_n_prior": 12,
        "home_corners_asof": 6.0, "away_corners_asof": 4.0,
        "home_n_prior_corners": 12, "away_n_prior_corners": 12,
    })
    for i in range(3):
        rows.append({
            "event_id": f"b{i}", "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=(13 + i) * 7),
            "home_team": "BBB", "away_team": "YYY",
            "home_sot_for_asof": 1.0, "home_sot_against_asof": 1.0,
            "home_shots_for_asof": 1.0, "home_shots_against_asof": 1.0,
            "home_sot_ratio_for_asof": 0.1, "home_sot_for_l10": 1.0,
            "away_sot_for_asof": 1.0, "away_sot_against_asof": 1.0,
            "away_shots_for_asof": 1.0, "away_shots_against_asof": 1.0,
            "away_sot_ratio_for_asof": 0.1, "away_sot_for_l10": 1.0,
            "home_n_prior": i, "away_n_prior": i,
            "home_corners_asof": 1.0, "away_corners_asof": 1.0,
            "home_n_prior_corners": i, "away_n_prior_corners": i,
        })
    return pd.DataFrame(rows).sample(frac=1.0, random_state=5).reset_index(drop=True)


@pytest.fixture()
def synthetic_snapshot(monkeypatch, tmp_path):
    claims_dir = tmp_path / "intel_claims"
    claims_dir.mkdir(parents=True)
    monkeypatch.setattr(sc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sc, "_OUT_DIR", claims_dir)
    monkeypatch.setattr(sc, "_SNAPSHOT", claims_dir / "soccer_team_shot_asof_snapshot.parquet")
    return _synthetic_joined()


def test_floor_excludes_below_floor_team_and_counts_it(synthetic_snapshot):
    long_df = sc.build_long_frame(synthetic_snapshot)
    snap = sc.build_snapshot(long_df)
    claims = sc.build_all_claims(snap)
    sot_claim = next(c for c in claims if c["criteria"]["metric"] == "sot_for_asof")
    ranked_teams = {r["team"] for r in sot_claim["ranking"]}
    assert "AAA" in ranked_teams          # n_prior = 12 >= floor 10
    assert "BBB" not in ranked_teams      # n_prior = 2 < floor 10
    assert "YYY" not in ranked_teams      # n_prior = 2 < floor 10
    assert sot_claim["n_excluded_below_floor"] == 2  # BBB and YYY


def test_asof_shift_excludes_self_match(synthetic_snapshot):
    """AAA's snapshot must come from its most-recent row (m_last) -- and
    that row's OWN as-of value is 99 (the source builder's pre-match as-of
    contract, not a leaked realized value from that same match). The melt
    must read exactly that pre-match value, not the second-to-last row's."""
    long_df = sc.build_long_frame(synthetic_snapshot)
    snap = sc.build_snapshot(long_df)
    aaa = snap[snap["team"] == "AAA"].iloc[0]
    assert aaa["sot_for_asof"] == 99.0   # the LAST match's pre-match as-of value
    assert aaa["n_prior"] == 12


def test_identity_roundtrip_validator_verifies(synthetic_snapshot):
    long_df = sc.build_long_frame(synthetic_snapshot)
    snap = sc.build_snapshot(long_df)
    sc.write_snapshot(snap, sc._SNAPSHOT)
    claims = sc.build_all_claims(snap)
    assert len(claims) > 0
    orig_root = claims_validator.REPO_ROOT
    claims_validator.REPO_ROOT = sc.REPO_ROOT
    try:
        for claim in claims:
            verdict = claims_validator.validate_claim(claim)
            assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"
    finally:
        claims_validator.REPO_ROOT = orig_root


def test_honest_caveats_and_edge_claimed_false(synthetic_snapshot):
    long_df = sc.build_long_frame(synthetic_snapshot)
    snap = sc.build_snapshot(long_df)
    claims = sc.build_all_claims(snap)
    for claim in claims:
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        for word in ("roi", "pnl", "$", "bankroll"):
            assert word not in blob
        assert "descriptive" in blob
        assert "floor" in blob
        assert claim["criteria"]["entity_key"] == "team"
