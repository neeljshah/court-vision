"""Per-file tests for wnba_claims_ext (lane wnba-atlas, WNBA DESCRIPTIVE
extraction only -- no gate, per the ratified power audit). Mirrors test_
wnba_claims.py's acceptance criteria for this sibling module's 3 claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_wnba_claims_ext.py -q

Acceptance criteria:
  1. min_sample floor actually excludes below-floor entities (per dim).
  2. FULL POPULATION: every entity clearing the floor is ranked, no top-N cap.
  3. the ranking dict's entity-id key matches criteria.entity_key.
  4. all three real-corpus claims independently re-verify via
     claims_validator.validate_claim -> VERIFIED against the REAL on-disk
     atlas_wnba_player_playmaking/_defense_activity/_usage_volume parquets.
  5. every emitted claim's caveats explicitly disclaim gate/predictive/
     calibration status.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import wnba_claims_ext as wce
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_player_df(metric_col: str) -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": ["1", "2", "3"],
        "player_name": ["Vet Player", "Mid Player", "Callup Player"],
        "n_games_played": [22, 11, 2],
        metric_col: [6.0, 4.0, 9.0],
    })


def test_playmaking_min_sample_floor(monkeypatch):
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_player_df("assists_per_game"))
    claim = wce.build_player_playmaking_claim()
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert {"1", "2"} <= ranked_ids
    assert "3" not in ranked_ids  # 2 games < floor of 10
    assert claim["n_excluded_below_floor"] == 1
    assert claim["ranking"][0]["player_id"] == "1"  # 6.0 beats 4.0


def test_defense_activity_min_sample_floor(monkeypatch):
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_player_df("stocks_per_game"))
    claim = wce.build_player_defense_activity_claim()
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert {"1", "2"} <= ranked_ids
    assert "3" not in ranked_ids
    assert claim["n_excluded_below_floor"] == 1


def test_usage_volume_min_sample_floor(monkeypatch):
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_player_df("fga_per_game"))
    claim = wce.build_player_usage_volume_claim()
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert {"1", "2"} <= ranked_ids
    assert "3" not in ranked_ids
    assert claim["n_excluded_below_floor"] == 1


def test_entity_key_matches_ranking_dict_key(monkeypatch):
    """Regression guard (same bug class documented in test_wnba_claims.py):
    the ranking dict's id key must equal criteria.entity_key, never a
    hardcoded alias -- claims_validator reads claimed_row.get(entity_key)
    directly and would MISMATCH otherwise."""
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_player_df("assists_per_game"))
    claim = wce.build_player_playmaking_claim()
    assert claim["criteria"]["entity_key"] == "player_id"
    for row in claim["ranking"]:
        assert "player_id" in row
        assert isinstance(row["player_id"], str)


def test_full_population_no_top_n_cap(monkeypatch):
    big = pd.DataFrame({
        "player_id": [str(i) for i in range(60)],
        "player_name": [f"Player{i}" for i in range(60)],
        "n_games_played": [15] * 60,
        "fga_per_game": [float(i) for i in range(60)],
    })
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: big)
    claim = wce.build_player_usage_volume_claim()
    assert claim["n_considered"] == 60
    assert claim["n_excluded_below_floor"] == 0
    assert len(claim["ranking"]) == 60


def test_no_gate_or_predictive_language_in_caveats():
    for builder in (
        wce.build_player_playmaking_claim,
        wce.build_player_defense_activity_claim,
        wce.build_player_usage_volume_claim,
    ):
        claim = builder()
        caveats_text = " ".join(claim["caveats"]).lower()
        assert "descriptive" in caveats_text
        assert "not a gate" in caveats_text
        assert "no market/$ edge claimed" in caveats_text
        assert claim["kind"] == "ranking"


def test_real_playmaking_claim_independently_verifies():
    claim = wce.build_player_playmaking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_defense_activity_claim_independently_verifies():
    claim = wce.build_player_defense_activity_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_usage_volume_claim_independently_verifies():
    claim = wce.build_player_usage_volume_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_all_ext_claims_returns_three_in_stable_order():
    claims = wce.all_ext_claims()
    assert len(claims) == 3
    ids = [c["claim_id"] for c in claims]
    assert ids == [
        "wnba_player_playmaking_full_2026",
        "wnba_player_defense_activity_full_2026",
        "wnba_player_usage_volume_full_2026",
    ]
