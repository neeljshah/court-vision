"""Per-file tests for nba_teammate_context_claims.py (claim 3: synergy
top/bottom + orchestration + never-empty write_claims skip idiom).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_teammate_context_claims.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_teammate_context_claims as ntc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_synergy() -> pd.DataFrame:
    return pd.DataFrame({
        "team_id": [10, 10, 10, 20],
        "lineup_key": ["1,2,3,4,5", "6,7,8,9,10", "11,12,13,14,15", "16,17,18,19,20"],
        "n_games": [20, 20, 20, 5],
        "min": [150.0, 140.0, 130.0, 5.0],
        "net_per48": [10.0, -5.0, 2.0, 1.0],
        "expected_net_per48": [2.0, 3.0, 2.0, 1.0],
        "synergy_residual": [8.0, -8.0, 0.0, 0.0],
        "n_members_qualified": [5, 5, 5, 2],
        "qualifies": [True, True, True, False],
    })


def _wire_fake_repo(tmp_path, monkeypatch):
    lineups_dir = tmp_path / "data" / "cache" / "team_system" / "lineups"
    lineups_dir.mkdir(parents=True)
    _fixture_synergy().to_parquet(lineups_dir / "lineup_synergy_2024_25.parquet", index=False)

    monkeypatch.setattr(ntc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ntc, "_LINEUPS_DIR", lineups_dir)
    monkeypatch.setattr(ntc, "_OUT_DIR", tmp_path / "data" / "cache" / "intel_claims")
    monkeypatch.setattr(ntc, "_CLAIMS_OUT", tmp_path / "data" / "cache" / "intel_claims" / "x.jsonl")


def test_synergy_top_claim_ranks_best_lineup_first(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    claim = ntc._build_synergy_claim("desc")

    assert claim["ranking"][0]["lineup_key"] == "1,2,3,4,5"  # residual=8.0, best
    assert claim["ranking"][0]["value"] == 8.0
    # the 4th row (team 20) fails qualifies==True -> excluded
    assert claim["n_excluded_below_floor"] == 1
    assert claim["n_considered"] == 4
    assert len(claim["ranking"]) == 3


def test_synergy_bottom_claim_ranks_worst_lineup_first(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    claim = ntc._build_synergy_claim("asc")

    assert claim["ranking"][0]["lineup_key"] == "6,7,8,9,10"  # residual=-8.0, worst
    assert claim["ranking"][0]["value"] == -8.0


def test_synergy_caveats_present(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    claim = ntc._build_synergy_claim("desc")

    caveats_text = " ".join(claim["caveats"])
    assert "ROSTER CONFOUND" in caveats_text
    assert "COACH-DEPLOYMENT CONFOUND" in caveats_text
    assert "GARBAGE-TIME CONTAMINATION" in caveats_text
    assert "2024-25 ONLY" in caveats_text
    assert claim["label"] == "DESCRIPTIVE_ONLY"


def test_synergy_claim_validator_round_trip(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path)

    claim = ntc._build_synergy_claim("desc")
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_write_claims_skips_empty_ranking(tmp_path):
    empty_claim = {
        "claim_id": "x", "kind": "ranking", "ranking": [], "n_considered": 0,
        "n_excluded_below_floor": 0, "criteria": {}, "source_files": [], "caveats": [],
    }
    full_claim = {
        "claim_id": "y", "kind": "ranking", "ranking": [{"rank": 1, "value": 1.0}],
        "n_considered": 1, "n_excluded_below_floor": 0, "criteria": {}, "source_files": [],
        "caveats": [],
    }
    out_path = ntc.write_claims([empty_claim, full_claim], tmp_path / "out.jsonl")
    lines = out_path.read_text(encoding="ascii").strip().splitlines()
    assert len(lines) == 1
    assert '"claim_id": "y"' in lines[0]
