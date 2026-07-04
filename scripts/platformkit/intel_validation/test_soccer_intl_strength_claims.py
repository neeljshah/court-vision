"""Per-file tests for soccer_intl_strength_claims (mission spine 5, lane
claims-breadth-2).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_soccer_intl_strength_claims.py -q

Acceptance criteria:
  1. build_strength_snapshot writes one row per team with the replay's
     gf_ew/ga_ew/n_matches, as-of the day AFTER the corpus's last match date.
  2. min_sample floor (n_matches) actually excludes below-floor teams.
  3. build_ranking_claim's claimed ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED against the REAL on-disk
     corpus -- proves reproducibility, not just self-consistency.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from scripts.platformkit.intel_validation import soccer_intl_strength_claims as sisc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_results() -> pd.DataFrame:
    # Alpha beats Beta repeatedly (high gf, low ga); Gamma/Delta play a small,
    # noisy 2-match sample that should be excluded by a 3-match floor.
    rows = []
    for i in range(10):
        rows.append({
            "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i * 7),
            "home_team": "Alpha", "away_team": "Beta",
            "home_score": 3.0, "away_score": 0.0,
            "tournament": "Friendly", "city": "X", "country": "Alpha", "neutral": False,
        })
    rows.append({
        "date": pd.Timestamp("2024-03-01"),
        "home_team": "Gamma", "away_team": "Delta",
        "home_score": 1.0, "away_score": 1.0,
        "tournament": "Friendly", "city": "Y", "country": "Gamma", "neutral": True,
    })
    return pd.DataFrame(rows)


def test_build_strength_snapshot_one_row_per_team(tmp_path, monkeypatch):
    monkeypatch.setattr(sisc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(sisc, "_SNAPSHOT_OUT", tmp_path / "soccer_intl_strength_snapshot.parquet")
    results_path = tmp_path / "results.parquet"
    _fixture_results().to_parquet(results_path)

    out_path, as_of_iso, n_teams = sisc.build_strength_snapshot(results_path)
    snapshot = pd.read_parquet(out_path)
    assert n_teams == 4
    assert set(snapshot["team"]) == {"Alpha", "Beta", "Gamma", "Delta"}
    # as-of is strictly AFTER the corpus's last match date (10 weekly Alpha/Beta
    # matches from 2024-01-01 -> last is 2024-03-04, later than Gamma/Delta's 2024-03-01)
    assert as_of_iso == (dt.date(2024, 3, 4) + dt.timedelta(days=1)).isoformat()
    alpha_row = snapshot[snapshot["team"] == "Alpha"].iloc[0]
    assert int(alpha_row["n_matches"]) == 10
    assert alpha_row["gf_ew"] > alpha_row["ga_ew"]  # Alpha dominates 3-0 every match


def test_min_sample_floor_excludes_low_match_count_teams(tmp_path, monkeypatch):
    monkeypatch.setattr(sisc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(sisc, "_SNAPSHOT_OUT", tmp_path / "soccer_intl_strength_snapshot.parquet")
    monkeypatch.setattr(sisc, "_CLAIMS_OUT", tmp_path / "soccer_intl_strength_claims.jsonl")
    monkeypatch.setattr(sisc, "REPO_ROOT", tmp_path.parent)
    monkeypatch.setattr(sisc, "MIN_N_MATCHES", 3)
    results_path = tmp_path / "results.parquet"
    _fixture_results().to_parquet(results_path)
    monkeypatch.setattr(sisc, "_RESULTS", results_path)

    claim = sisc.build_ranking_claim()
    ranked_teams = {r["team"] for r in claim["ranking"]}
    # Alpha/Beta: 10 matches each -> qualify; Gamma/Delta: 1 match each -> excluded
    assert {"Alpha", "Beta"} <= ranked_teams
    assert "Gamma" not in ranked_teams
    assert "Delta" not in ranked_teams
    assert claim["n_excluded_below_floor"] == 2
    # Alpha (net +3/match dominance) outranks Beta
    assert claim["ranking"][0]["team"] == "Alpha"


def test_real_soccer_intl_claim_independently_verifies():
    """Cross-module check against the REAL on-disk corpus (matches the
    production claim this module ships) -- proves the emitted ranking is
    independently reproducible by claims_validator, not just self-consistent."""
    claim = sisc.build_ranking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
