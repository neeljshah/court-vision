"""Per-file tests for wnba_claims (lane soccer-wnba-fullpop, WNBA DESCRIPTIVE
extraction only -- no gate, per the ratified power audit).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_wnba_claims.py -q

Acceptance criteria:
  1. min_sample floor actually excludes below-floor entities (per dim).
  2. FULL POPULATION: every entity clearing the floor is ranked, no top-N cap.
  3. the ranking dict's entity-id key matches criteria.entity_key (the exact
     bug caught during build: hardcoding a fixed cross-sport key produces a
     MISMATCH against claims_validator when entity_key differs, e.g.
     official_id).
  4. all three real-corpus claims independently re-verify via
     claims_validator.validate_claim -> VERIFIED against the REAL on-disk
     WNBA parquets -- proves reproducibility, not just self-consistency.
  5. every emitted claim's caveats explicitly disclaim gate/predictive/
     calibration status (the hard rail this module must never cross).
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import wnba_claims as wc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_referee_df() -> pd.DataFrame:
    return pd.DataFrame({
        "official_id": ["100", "101", "102"],
        "official_name": ["Vet Official", "Mid Official", "Rookie Official"],
        "n_games": [19, 12, 3],
        "fouls_per_game": [16.2632, 12.5, 20.0],
    })


def _fixture_player_df(metric_col: str) -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": ["1", "2", "3"],
        "player_name": ["Vet Player", "Mid Player", "Callup Player"],
        "n_games_played": [22, 11, 2],
        metric_col: [0.60, 0.55, 0.90],
    })


def test_referee_min_sample_floor_excludes_low_game_count(monkeypatch):
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_referee_df())
    claim = wc.build_referee_crew_claim()
    ranked_ids = {r["official_id"] for r in claim["ranking"]}
    assert {"100", "101"} <= ranked_ids
    assert "102" not in ranked_ids  # 3 games < floor of 10
    assert claim["n_excluded_below_floor"] == 1
    assert claim["ranking"][0]["official_id"] == "100"  # highest fouls_per_game among qualifiers


def test_referee_ranking_uses_entity_key_as_dict_key(monkeypatch):
    """Regression guard for the build-time bug: the ranking dict's id key
    must equal criteria.entity_key ('official_id'), not a hardcoded
    'player_id' alias -- claims_validator reads claimed_row.get(entity_key)
    directly and would MISMATCH on a wrong key."""
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_referee_df())
    claim = wc.build_referee_crew_claim()
    assert claim["criteria"]["entity_key"] == "official_id"
    for row in claim["ranking"]:
        assert "official_id" in row
        assert isinstance(row["official_id"], str)


def test_player_shot_quality_min_sample_floor(monkeypatch):
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_player_df("ts_pct"))
    claim = wc.build_player_shot_quality_claim()
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert {"1", "2"} <= ranked_ids
    assert "3" not in ranked_ids  # 2 games < floor of 10
    assert claim["n_excluded_below_floor"] == 1
    assert claim["ranking"][0]["player_id"] == "1"  # ts_pct 0.60 beats 0.55


def test_player_rebounding_min_sample_floor(monkeypatch):
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_player_df("reb_per_game"))
    claim = wc.build_player_rebounding_claim()
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert {"1", "2"} <= ranked_ids
    assert "3" not in ranked_ids
    assert claim["n_excluded_below_floor"] == 1


def test_full_population_no_top_n_cap(monkeypatch):
    """FULL POPULATION: a fixture with 60 qualifying players (well past any
    historical top-50 cap) must all appear ranked, proving there is no cap."""
    big = pd.DataFrame({
        "player_id": [str(i) for i in range(60)],
        "player_name": [f"Player{i}" for i in range(60)],
        "n_games_played": [15] * 60,
        "reb_per_game": [float(i) for i in range(60)],
    })
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: big)
    claim = wc.build_player_rebounding_claim()
    assert claim["n_considered"] == 60
    assert claim["n_excluded_below_floor"] == 0
    assert len(claim["ranking"]) == 60


def test_no_gate_or_predictive_language_in_caveats():
    """HARD RAIL: every WNBA claim must explicitly disclaim gate/predictive/
    calibration status -- descriptive extraction only, per the ratified
    power audit (n<=172 games, today-only close corpus -> any gate is
    underpowered)."""
    for builder in (
        wc.build_referee_crew_claim,
        wc.build_player_shot_quality_claim,
        wc.build_player_rebounding_claim,
    ):
        claim = builder()
        caveats_text = " ".join(claim["caveats"]).lower()
        assert "descriptive" in caveats_text
        assert "not a gate" in caveats_text
        assert "no market/$ edge claimed" in caveats_text
        assert claim["kind"] == "ranking"  # never "verdict"


def test_real_referee_claim_independently_verifies():
    """Cross-module check against the REAL on-disk WNBA corpus -- proves the
    emitted ranking is independently reproducible by claims_validator, not
    just self-consistent."""
    claim = wc.build_referee_crew_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_player_shot_quality_claim_independently_verifies():
    claim = wc.build_player_shot_quality_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_player_rebounding_claim_independently_verifies():
    claim = wc.build_player_rebounding_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
