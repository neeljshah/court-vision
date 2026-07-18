"""Per-file tests for soccer_team_form_asof_claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_soccer_team_form_asof_claims.py -q

Acceptance:
  1. Floor exclusion is COUNTED (below-floor team excluded from ranking but
     tallied in n_excluded_below_floor), never silently dropped.
  2. As-of shift excludes the team's own most-recent match's self result.
  3. Identity round-trip: validator independently recomputes the exact same
     values straight from the snapshot parquet + criteria.formula (VERIFIED).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import soccer_team_form_asof_claims as fc


def _synthetic_matches() -> pd.DataFrame:
    """AAA plays 14 matches vs ZZZ (its only opponent), chronologically
    ordered but written SHUFFLED to disk: first 4 are losses (0-1 away),
    next 9 are wins (2-0 home), and the FINAL (most-recent) match is a heavy
    loss (0-5 home) -- this last match must NEVER enter AAA's trailing-10
    window. Neither AAA nor ZZZ ever clears the home-only or away-only
    n_prior>=10 floor (9 and 4, or 4 and 9, respectively) -- so the home/
    away-split metrics are honestly SKIPPED for this fixture (never-emit-
    empty-ranking idiom), leaving only the all-venue + season metrics.
    BBB plays a separate opponent YYY, 3 matches only (below n_prior>=10)."""
    rows = []
    day = 0
    for _ in range(4):
        rows.append({"event_id": f"aaa_l{day}", "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                     "season": 2020, "home_team": "ZZZ", "away_team": "AAA", "fthg": 1, "ftag": 0, "ftr": "H"})
        day += 7
    for _ in range(9):
        rows.append({"event_id": f"aaa_w{day}", "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                     "season": 2020, "home_team": "AAA", "away_team": "ZZZ", "fthg": 2, "ftag": 0, "ftr": "H"})
        day += 7
    # AAA's own most-recent match: a 0-5 home loss (self-result must be excluded from L10)
    rows.append({"event_id": "aaa_last", "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                 "season": 2020, "home_team": "AAA", "away_team": "ZZZ", "fthg": 0, "ftag": 5, "ftr": "A"})
    day += 7
    for _ in range(3):
        rows.append({"event_id": f"bbb_{day}", "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                     "season": 2020, "home_team": "BBB", "away_team": "YYY", "fthg": 1, "ftag": 1, "ftr": "D"})
        day += 7
    df = pd.DataFrame(rows)
    return df.sample(frac=1.0, random_state=3).reset_index(drop=True)  # shuffled on-disk order


@pytest.fixture()
def synthetic_snapshot(monkeypatch, tmp_path):
    soccer_dir = tmp_path / "soccer"
    soccer_dir.mkdir(parents=True)
    _synthetic_matches().to_parquet(soccer_dir / "matches.parquet", index=False)

    claims_dir = tmp_path / "intel_claims"
    claims_dir.mkdir(parents=True)
    monkeypatch.setattr(fc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(fc, "_SOCCER_DIR", soccer_dir)
    monkeypatch.setattr(fc, "_OUT_DIR", claims_dir)
    monkeypatch.setattr(fc, "_SNAPSHOT", claims_dir / "soccer_team_form_asof_snapshot.parquet")
    return claims_dir


def test_floor_excludes_below_floor_team_and_counts_it(synthetic_snapshot):
    long_df = fc.build_long_frame(fc._load_matches())
    snap = fc.build_snapshot(long_df)
    claims = fc.build_all_claims(snap)
    ppg_claim = next(c for c in claims if c["criteria"]["metric"] == "ppg_l10")
    ranked_teams = {r["team"] for r in ppg_claim["ranking"]}
    assert "AAA" in ranked_teams          # n_prior = 13 >= floor 10
    assert "BBB" not in ranked_teams      # n_prior = 2 < floor 10
    assert ppg_claim["n_excluded_below_floor"] == 2  # BBB and YYY (both n_prior=2 < 10)


def test_asof_shift_excludes_self_match(synthetic_snapshot):
    """AAA's most-recent (14th) match is a 0-5 home LOSS (conceded 5). The
    trailing-10 window over the 13 STRICTLY PRIOR matches is [4th early loss
    (conceded 1), 9 wins (conceded 0 each)] -> ga_l10 = 1/10 = 0.1. If the
    as-of shift were broken and the self-match leaked in (replacing the 4th
    early loss with the final conceded-5 match), ga_l10 would jump to
    5/10 = 0.5 -- this is the discriminating check (pts/win/cs are 0 for
    EITHER loss, so only the goals-against margin can catch the leak)."""
    long_df = fc.build_long_frame(fc._load_matches())
    snap = fc.build_snapshot(long_df)
    aaa = snap[snap["team"] == "AAA"].iloc[0]
    assert aaa["n_prior"] == 13  # 13 prior matches; the 14th (conceded-5 loss) is dropped
    assert aaa["ga_l10"] == pytest.approx(0.1)   # NOT 0.5 -- proves the self-match never leaked in
    assert aaa["winrate_l10"] == pytest.approx(0.9)
    assert aaa["ppg_l10"] == pytest.approx(2.7)
    assert aaa["clean_sheet_rate_l10"] == pytest.approx(0.9)


def test_identity_roundtrip_validator_verifies(synthetic_snapshot):
    long_df = fc.build_long_frame(fc._load_matches())
    snap = fc.build_snapshot(long_df)
    fc.write_snapshot(snap, fc._SNAPSHOT)
    claims = fc.build_all_claims(snap)
    orig_root = claims_validator.REPO_ROOT
    claims_validator.REPO_ROOT = fc.REPO_ROOT
    try:
        for claim in claims:
            verdict = claims_validator.validate_claim(claim)
            assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"
    finally:
        claims_validator.REPO_ROOT = orig_root


def test_honest_caveats_and_edge_claimed_false(synthetic_snapshot):
    long_df = fc.build_long_frame(fc._load_matches())
    snap = fc.build_snapshot(long_df)
    claims = fc.build_all_claims(snap)
    # Only the all-venue (6) + season (1) metrics clear a qualifier in this
    # fixture; the 4 home/away-split metrics are honestly skipped (zero
    # teams clear n_prior_home/n_prior_away>=10) -- see _synthetic_matches.
    assert len(claims) == 7
    for claim in claims:
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        for word in ("roi", "pnl", "$", "bankroll"):
            assert word not in blob
        assert "descriptive" in blob
        assert "floor" in blob
        assert claim["criteria"]["entity_key"] == "team"
