"""Per-file tests for soccer_intl_h2h_claims (PROGRAM v3 breadth, lane
soccer-widen).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_soccer_intl_h2h_claims.py -q

Acceptance criteria:
  1. build_pair_table merges BOTH home/away directions of the same rivalry
     into ONE (team_lo, team_hi) row -- proves the canonical-ordering merge
     is real, not assumed.
  2. min_sample floor (meetings) actually excludes below-floor pairs.
  3. build_ranking_claim's claimed ranking independently re-verifies via
     claims_validator.validate_claim -> VERIFIED against the REAL on-disk
     corpus (proves reproducibility, not just self-consistency).
  4. Full pair population holds (no top-N cap) on the real on-disk corpus.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import soccer_intl_h2h_claims as sihc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_both_directions() -> pd.DataFrame:
    """Alpha hosts Beta 3 times (Alpha wins all 3); Beta ALSO hosts Alpha 2
    times (Beta wins both) -- same rivalry, opposite home/away direction.
    A naive groupby(['home_team','away_team']) would produce TWO rows
    (5 total meetings split 3/2); the canonical team_lo/team_hi merge must
    produce ONE row with meetings=5."""
    rows = []
    for i in range(3):
        rows.append({
            "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i * 30),
            "home_team": "Alpha", "away_team": "Beta",
            "home_score": 2.0, "away_score": 0.0,
        })
    for i in range(2):
        rows.append({
            "date": pd.Timestamp("2024-06-01") + pd.Timedelta(days=i * 30),
            "home_team": "Beta", "away_team": "Alpha",
            "home_score": 1.0, "away_score": 0.0,
        })
    return pd.DataFrame(rows)


def test_build_pair_table_merges_both_home_away_directions():
    table = sihc.build_pair_table(_fixture_both_directions())
    assert len(table) == 1, "both home/away directions must merge into ONE pair row"
    row = table.iloc[0]
    assert {row["team_lo"], row["team_hi"]} == {"Alpha", "Beta"}
    assert row["team_lo"] == "Alpha" and row["team_hi"] == "Beta"  # alphabetical
    assert row["meetings"] == 5  # 3 + 2, both directions summed
    # Alpha won all 3 as home + lost both as away = 3 wins total (team_lo=Alpha)
    assert row["wins_lo"] == 3


def test_draws_count_toward_neither_team():
    df = pd.DataFrame([{
        "date": pd.Timestamp("2024-01-01"), "home_team": "Alpha", "away_team": "Beta",
        "home_score": 1.0, "away_score": 1.0,
    }])
    table = sihc.build_pair_table(df)
    row = table.iloc[0]
    assert row["meetings"] == 1
    assert row["wins_lo"] == 0  # draw is not a win for either side


def test_min_sample_floor_excludes_low_meetings_pairs(tmp_path, monkeypatch):
    monkeypatch.setattr(sihc, "MIN_MEETINGS", 3)
    monkeypatch.setattr(sihc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(sihc, "_PAIR_PARQUET_OUT", tmp_path / "soccer_intl_h2h_pairs.parquet")
    monkeypatch.setattr(sihc, "REPO_ROOT", tmp_path.parent)
    results_path = tmp_path / "results.parquet"
    _fixture_both_directions().to_parquet(results_path)  # 1 pair, 5 meetings -> above floor

    low_meeting_pair = pd.DataFrame([{
        "date": pd.Timestamp("2024-01-01"), "home_team": "Gamma", "away_team": "Delta",
        "home_score": 1.0, "away_score": 0.0,
    }])
    combined = pd.concat([_fixture_both_directions(), low_meeting_pair], ignore_index=True)
    combined.to_parquet(results_path)

    claim = sihc.build_ranking_claim(results_path)
    ranked_pairs = {(r["team_lo"], r["team_hi"]) for r in claim["ranking"]}
    assert ("Alpha", "Beta") in ranked_pairs
    assert ("Delta", "Gamma") not in ranked_pairs  # 1 meeting, below floor 3
    assert claim["n_excluded_below_floor"] == 1
    assert claim["n_considered"] == 2


def test_real_soccer_intl_h2h_claim_independently_verifies():
    """Cross-module check against the REAL on-disk results.parquet -- proves
    the emitted pair-keyed ranking is independently reproducible by
    claims_validator, not just self-consistent."""
    claim = sihc.build_ranking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_soccer_intl_h2h_claim_is_full_pair_population():
    """The production ranking must cover EVERY qualifying pair above the
    min_sample floor, not a top-N slice."""
    claim = sihc.build_ranking_claim()
    n_qualifying = claim["n_considered"] - claim["n_excluded_below_floor"]
    assert len(claim["ranking"]) == n_qualifying
    assert n_qualifying > 1000, "expected the real soccer_intl h2h qualifying pool to be large"
    assert claim["n_considered"] > n_qualifying, "some below-floor pairs must exist to prove honest counting"


def test_real_soccer_intl_h2h_claim_criteria_uses_pair_entity_key():
    claim = sihc.build_ranking_claim()
    assert claim["criteria"]["entity_key"] == ["team_lo", "team_hi"]
    assert claim["criteria"]["min_sample"] == {"meetings": sihc.MIN_MEETINGS}
