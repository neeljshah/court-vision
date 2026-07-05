"""Per-file tests for soccer_intl_form_claims (PROGRAM v3 breadth, lane
soccer-widen).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_soccer_intl_form_claims.py -q

Acceptance criteria:
  1. build_form_table computes the trailing-N win rate using DATE order
     (not on-disk row order) -- proves the explicit re-sort is load-bearing.
  2. min_sample floor (n_matches) actually excludes below-floor teams.
  3. build_ranking_claim's claimed ranking independently re-verifies via
     claims_validator.validate_claim -> VERIFIED against the REAL on-disk
     corpus (proves reproducibility, not just self-consistency).
  4. Full population holds (no top-N cap) on the real on-disk corpus.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import soccer_intl_form_claims as sifc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_shuffled_dates() -> pd.DataFrame:
    """Alpha plays 15 matches: first 5 are LOSSES, last 10 (chronologically)
    are WINS -- but rows are written to the frame in a SHUFFLED (non-date-
    sorted) order, so a trailing-10 win rate computed WITHOUT an explicit
    date re-sort would pick up the wrong 10 rows. Trailing 10 (the true
    chronological last 10) must be 10/10 = 1.0 wins."""
    rows = []
    for i in range(5):  # earliest 5: losses
        rows.append({
            "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=i * 10),
            "home_team": "Alpha", "away_team": "Beta",
            "home_score": 0.0, "away_score": 2.0,
        })
    for i in range(10):  # latest 10: wins
        rows.append({
            "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i * 10),
            "home_team": "Alpha", "away_team": "Gamma",
            "home_score": 3.0, "away_score": 0.0,
        })
    df = pd.DataFrame(rows)
    # shuffle row order (fixed seed) so on-disk order != date order
    return df.sample(frac=1.0, random_state=7).reset_index(drop=True)


def test_build_form_table_uses_date_order_not_row_order():
    table = sifc.build_form_table(_fixture_shuffled_dates())
    alpha = table[table["team"] == "Alpha"].iloc[0]
    assert alpha["n_matches"] == 15
    # trailing 10 by DATE = the 10 most-recent (2024) matches, all wins
    assert alpha["form_win_rate"] == 1.0
    assert alpha["n_trailing"] == 10


def test_min_sample_floor_excludes_low_match_count_teams(tmp_path, monkeypatch):
    monkeypatch.setattr(sifc, "MIN_N_MATCHES", 12)
    monkeypatch.setattr(sifc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(sifc, "_SNAPSHOT_OUT", tmp_path / "soccer_intl_form_snapshot.parquet")
    monkeypatch.setattr(sifc, "REPO_ROOT", tmp_path.parent)
    results_path = tmp_path / "results.parquet"
    _fixture_shuffled_dates().to_parquet(results_path)  # Alpha:15, Beta:5, Gamma:10

    claim = sifc.build_ranking_claim(results_path)
    ranked_teams = {r["team"] for r in claim["ranking"]}
    assert "Alpha" in ranked_teams  # 15 >= floor 12
    assert "Beta" not in ranked_teams  # 5 < floor 12
    assert "Gamma" not in ranked_teams  # 10 < floor 12
    assert claim["n_excluded_below_floor"] == 2
    assert claim["n_considered"] == 3


def test_full_population_no_top_n_cap(tmp_path, monkeypatch):
    """FULL POPULATION: every team clearing the floor is ranked -- no cap."""
    monkeypatch.setattr(sifc, "MIN_N_MATCHES", 3)
    monkeypatch.setattr(sifc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(sifc, "_SNAPSHOT_OUT", tmp_path / "soccer_intl_form_snapshot.parquet")
    monkeypatch.setattr(sifc, "REPO_ROOT", tmp_path.parent)
    results_path = tmp_path / "results.parquet"

    rows = []
    for t in range(60):
        home, away = f"Team{t}A", f"Team{t}B"
        for i in range(5):
            rows.append({
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i * 7),
                "home_team": home, "away_team": away,
                "home_score": 2.0, "away_score": 0.0,
            })
    pd.DataFrame(rows).to_parquet(results_path)

    claim = sifc.build_ranking_claim(results_path)
    assert claim["n_considered"] == 120
    assert claim["n_excluded_below_floor"] == 0
    assert len(claim["ranking"]) == 120


def test_real_soccer_intl_form_claim_independently_verifies():
    """Cross-module check against the REAL on-disk results.parquet -- proves
    the emitted ranking is independently reproducible by claims_validator,
    not just self-consistent."""
    claim = sifc.build_ranking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_soccer_intl_form_claim_is_full_population():
    """The production ranking must cover EVERY team above the min_sample
    floor, not a top-N slice."""
    claim = sifc.build_ranking_claim()
    n_qualifying = claim["n_considered"] - claim["n_excluded_below_floor"]
    assert len(claim["ranking"]) == n_qualifying
    assert n_qualifying > 100, "expected a sizeable qualifying team pool on the real corpus"
    assert claim["n_considered"] > n_qualifying, "some below-floor teams must exist to prove honest counting"


def test_real_soccer_intl_form_claim_criteria():
    claim = sifc.build_ranking_claim()
    assert claim["criteria"]["entity_key"] == "team"
    assert claim["criteria"]["min_sample"] == {"n_matches": sifc.MIN_N_MATCHES}
    assert claim["criteria"]["formula"] == "form_win_rate"
