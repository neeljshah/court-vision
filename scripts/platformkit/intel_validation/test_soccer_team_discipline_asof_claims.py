"""Per-file tests for soccer_team_discipline_asof_claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_soccer_team_discipline_asof_claims.py -q

Acceptance:
  1. Floor exclusion is COUNTED (below-floor team excluded, honest tally).
  2. As-of shift excludes self-match: BOTH the wrapped EW builder's asof
     read AND the season-to-date rate this module computes itself must
     never reflect the team's own most-recent (sentinel-extreme) match.
  3. Identity round-trip: validator independently recomputes the exact same
     values straight from the snapshot parquet + criteria.formula (VERIFIED).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import soccer_team_discipline_asof_claims as dc


def _synthetic_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """AAA plays 12 steady matches (1 yellow card each, season 2020) vs ZZZ,
    then a 13th (final, most-recent) match with a SENTINEL 50-yellow-card
    blowup -- if either the EW as-of read or the season-to-date mean leaked
    that sentinel match into AAA's own snapshot, yellow_per_game_asof /
    cards_rate_season would be pulled sharply upward. BBB/YYY play only 3
    matches (below the n_prior_season>=5 / n_prior>=10 floors)."""
    m_rows, s_rows = [], []
    for i in range(12):
        eid = f"m{i}"
        m_rows.append({"event_id": eid, "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=i * 7),
                       "season": 2020, "home_team": "AAA", "away_team": "ZZZ"})
        s_rows.append({"event_id": eid, "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=i * 7),
                       "home_team": "AAA", "away_team": "ZZZ",
                       "home_yellow": 1, "away_yellow": 1, "home_red": 0, "away_red": 0,
                       "home_fouls": 8, "away_fouls": 8})
    eid = "m_last"
    m_rows.append({"event_id": eid, "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=12 * 7),
                   "season": 2020, "home_team": "AAA", "away_team": "ZZZ"})
    s_rows.append({"event_id": eid, "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=12 * 7),
                   "home_team": "AAA", "away_team": "ZZZ",
                   "home_yellow": 50, "away_yellow": 1, "home_red": 0, "away_red": 0,
                   "home_fouls": 8, "away_fouls": 8})
    for i in range(3):
        eid = f"b{i}"
        m_rows.append({"event_id": eid, "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=(13 + i) * 7),
                       "season": 2020, "home_team": "BBB", "away_team": "YYY"})
        s_rows.append({"event_id": eid, "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=(13 + i) * 7),
                       "home_team": "BBB", "away_team": "YYY",
                       "home_yellow": 1, "away_yellow": 1, "home_red": 0, "away_red": 0,
                       "home_fouls": 5, "away_fouls": 5})
    matches = pd.DataFrame(m_rows).sample(frac=1.0, random_state=9).reset_index(drop=True)
    match_stats = pd.DataFrame(s_rows).sample(frac=1.0, random_state=9).reset_index(drop=True)
    return matches, match_stats


@pytest.fixture()
def synthetic_snapshot(monkeypatch, tmp_path):
    claims_dir = tmp_path / "intel_claims"
    claims_dir.mkdir(parents=True)
    monkeypatch.setattr(dc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dc, "_OUT_DIR", claims_dir)
    monkeypatch.setattr(dc, "_SNAPSHOT", claims_dir / "soccer_team_discipline_asof_snapshot.parquet")
    return _synthetic_frames()


def test_floor_excludes_below_floor_team_and_counts_it(synthetic_snapshot):
    matches, match_stats = synthetic_snapshot
    long_df = dc.build_long_frame(matches, match_stats)
    snap = dc.build_snapshot(long_df)
    claims = dc.build_all_claims(snap)
    yellow_claim = next(c for c in claims if c["criteria"]["metric"] == "yellow_per_game_asof")
    ranked_teams = {r["team"] for r in yellow_claim["ranking"]}
    assert "AAA" in ranked_teams          # n_prior = 12 >= floor 10
    assert "BBB" not in ranked_teams      # n_prior = 2 < floor 10
    assert "YYY" not in ranked_teams      # n_prior = 2 < floor 10
    assert yellow_claim["n_excluded_below_floor"] == 2  # BBB and YYY


def test_asof_shift_excludes_self_match(synthetic_snapshot):
    """The final match's 50-yellow-card blowup must not leak into either
    the wrapped EW as-of read or the season-to-date mean this module owns."""
    matches, match_stats = synthetic_snapshot
    long_df = dc.build_long_frame(matches, match_stats)
    snap = dc.build_snapshot(long_df)
    aaa = snap[snap["team"] == "AAA"].iloc[0]
    # EW as-of (wrapped builder): steady state near 1.0 yellow/game, nowhere
    # close to what a 50-card fold-in would produce (~1 + 0.2*(50-1) ~ 10.8).
    assert aaa["yellow_per_game_asof"] < 3.0
    # season-to-date (this module's own logic): exact mean over the 12
    # prior 1-yellow matches only, the 50-card match is excluded entirely.
    assert aaa["n_prior_season"] == 12
    assert aaa["cards_rate_season"] == pytest.approx(1.0)


def test_identity_roundtrip_validator_verifies(synthetic_snapshot):
    matches, match_stats = synthetic_snapshot
    long_df = dc.build_long_frame(matches, match_stats)
    snap = dc.build_snapshot(long_df)
    dc.write_snapshot(snap, dc._SNAPSHOT)
    claims = dc.build_all_claims(snap)
    assert len(claims) > 0
    orig_root = claims_validator.REPO_ROOT
    claims_validator.REPO_ROOT = dc.REPO_ROOT
    try:
        for claim in claims:
            verdict = claims_validator.validate_claim(claim)
            assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"
    finally:
        claims_validator.REPO_ROOT = orig_root


def test_honest_caveats_and_edge_claimed_false(synthetic_snapshot):
    matches, match_stats = synthetic_snapshot
    long_df = dc.build_long_frame(matches, match_stats)
    snap = dc.build_snapshot(long_df)
    claims = dc.build_all_claims(snap)
    for claim in claims:
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        for word in ("roi", "pnl", "$", "bankroll"):
            assert word not in blob
        assert "descriptive" in blob
        assert "floor" in blob
        assert claim["criteria"]["entity_key"] == "team"
