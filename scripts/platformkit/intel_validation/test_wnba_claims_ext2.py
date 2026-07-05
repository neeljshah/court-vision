"""Per-file tests for wnba_claims_ext2 (lane wnba-atlas, WNBA DESCRIPTIVE
extraction only -- no gate, per the ratified power audit). Mirrors test_
wnba_claims.py's acceptance criteria for this sibling module's 2 claims
(one player-grain, one team-grain).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_wnba_claims_ext2.py -q

Acceptance criteria:
  1. min_sample floor actually excludes below-floor entities (player AND
     team grain).
  2. FULL POPULATION: every entity clearing the floor is ranked, no top-N cap.
  3. the ranking dict's entity-id key matches criteria.entity_key (team_id
     for the team-grain claim, not a hardcoded player-style alias).
  4. both real-corpus claims independently re-verify via claims_validator.
     validate_claim -> VERIFIED against the REAL on-disk atlas_wnba_player_
     ft_profile / atlas_wnba_team_defense_allowed parquets.
  5. every emitted claim's caveats explicitly disclaim gate/predictive/
     calibration status.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import wnba_claims_ext2 as wce2
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_player_ft_df() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": ["1", "2", "3"],
        "player_name": ["Vet Player", "Mid Player", "Callup Player"],
        "n_games_played": [22, 11, 2],
        "ft_pct_season": [0.90, 0.80, 0.95],
    })


def _fixture_team_df() -> pd.DataFrame:
    return pd.DataFrame({
        "team_id": ["100", "101", "102"],
        "team_tricode": ["NYL", "IND", "JNT"],
        "n_games": [24, 22, 2],
        "opp_paint_pts_allowed_per_game": [39.5, 43.8, 36.0],
    })


def test_ft_profile_min_sample_floor(monkeypatch):
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_player_ft_df())
    claim = wce2.build_player_ft_profile_claim()
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert {"1", "2"} <= ranked_ids
    assert "3" not in ranked_ids  # 2 games < floor of 10
    assert claim["n_excluded_below_floor"] == 1
    assert claim["ranking"][0]["player_id"] == "1"  # 0.90 beats 0.80


def test_team_defense_allowed_min_sample_floor(monkeypatch):
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_team_df())
    claim = wce2.build_team_defense_allowed_claim()
    ranked_ids = {r["team_id"] for r in claim["ranking"]}
    assert {"100", "101"} <= ranked_ids
    assert "102" not in ranked_ids  # 2 games < floor of 10
    assert claim["n_excluded_below_floor"] == 1
    assert claim["ranking"][0]["team_id"] == "101"  # 43.8 beats 39.5


def test_team_entity_key_matches_ranking_dict_key(monkeypatch):
    """Regression guard: team-grain claim's ranking dict key must be
    'team_id' (matching criteria.entity_key), not a player-style alias --
    claims_validator reads claimed_row.get(entity_key) directly."""
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_team_df())
    claim = wce2.build_team_defense_allowed_claim()
    assert claim["criteria"]["entity_key"] == "team_id"
    for row in claim["ranking"]:
        assert "team_id" in row
        assert isinstance(row["team_id"], str)


def test_full_population_no_top_n_cap_team_grain(monkeypatch):
    big = pd.DataFrame({
        "team_id": [str(i) for i in range(20)],
        "team_tricode": [f"T{i}" for i in range(20)],
        "n_games": [15] * 20,
        "opp_paint_pts_allowed_per_game": [float(i) for i in range(20)],
    })
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: big)
    claim = wce2.build_team_defense_allowed_claim()
    assert claim["n_considered"] == 20
    assert claim["n_excluded_below_floor"] == 0
    assert len(claim["ranking"]) == 20


def test_no_gate_or_predictive_language_in_caveats():
    for builder in (
        wce2.build_player_ft_profile_claim,
        wce2.build_team_defense_allowed_claim,
    ):
        claim = builder()
        caveats_text = " ".join(claim["caveats"]).lower()
        assert "descriptive" in caveats_text
        assert "not a gate" in caveats_text
        assert "no market/$ edge claimed" in caveats_text
        assert claim["kind"] == "ranking"


def test_real_ft_profile_claim_independently_verifies():
    claim = wce2.build_player_ft_profile_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_team_defense_allowed_claim_independently_verifies():
    claim = wce2.build_team_defense_allowed_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_all_ext2_claims_returns_two_in_stable_order():
    claims = wce2.all_ext2_claims()
    assert len(claims) == 2
    ids = [c["claim_id"] for c in claims]
    assert ids == [
        "wnba_player_ft_profile_full_2026",
        "wnba_team_defense_allowed_full_2026",
    ]
