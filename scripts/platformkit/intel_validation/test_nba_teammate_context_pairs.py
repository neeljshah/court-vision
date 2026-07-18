"""Per-file tests for nba_teammate_context_pairs.py.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_teammate_context_pairs.py -q

Acceptance criteria: pair membership parse, with/without seconds math,
floor skip, both-direction distinct rows, caveat presence, validator
VERIFIED round-trip.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_teammate_context_pairs as ntp
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_stints() -> pd.DataFrame:
    # One game, one team, roster {1,2,3}. Two stints:
    #   stint 1: lineup {1,2,3} for 20000s, pts_for=100, pts_against=50
    #     (net/48 = 50*48*60/20000 = 7.2)
    #   stint 2: lineup {1,3} (2 off) for 13000s, pts_for=40, pts_against=40
    #     (net/48 = 0)
    # Pair (1,2): both_on_seconds=20000 (>=18000 floor), a(1)_without_b(2)=13000 (>=12000 floor)
    #   lift = 7.2 - 0 = 7.2
    # Pair (2,1): both_on_seconds=20000, a(2)_without_b(1)_seconds=0 -> below floor, excluded
    return pd.DataFrame({
        "game_id": ["g1", "g1"], "team_id": [10, 10],
        "lineup_key": ["1,2,3", "1,3"], "n_on_court": [5, 5],
        "elapsed_s": [20000.0, 13000.0],
        "pts_for": [100.0, 40.0], "pts_against": [50.0, 40.0],
    })


def _fixture_names() -> pd.DataFrame:
    return pd.DataFrame({"player_id": [1, 2, 3], "player_name": ["Alice", "Bob", "Carol"]})


def _wire_fake_repo(tmp_path, monkeypatch):
    """Point the producer (and, for round-trip tests, the validator) at a
    tmp fake repo root with real on-disk fixture parquet files -- no pandas
    monkeypatching, so the validator's independent re-read hits the SAME
    real bytes the producer wrote, exactly like the real pipeline."""
    lineups_dir = tmp_path / "data" / "cache" / "team_system" / "lineups"
    lineups_dir.mkdir(parents=True)
    box_dir = tmp_path / "data" / "domains" / "basketball_nba"
    box_dir.mkdir(parents=True)
    _fixture_stints().to_parquet(lineups_dir / "stints_2025_26.parquet", index=False)
    _fixture_names().to_parquet(box_dir / "player_boxscores.parquet", index=False)

    monkeypatch.setattr(ntp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ntp, "_LINEUPS_DIR", lineups_dir)
    monkeypatch.setattr(ntp, "_BOX_SRC", box_dir / "player_boxscores.parquet")
    monkeypatch.setattr(ntp, "_OUT_DIR", tmp_path / "data" / "cache" / "intel_claims")


def test_compute_pair_table_parses_membership_and_seconds_math():
    table = ntp.compute_pair_table(_fixture_stints())
    row_12 = table[(table["player_a"] == 1) & (table["player_b"] == 2)].iloc[0]
    assert row_12["both_on_seconds"] == 20000.0
    assert row_12["a_without_b_seconds"] == 13000.0
    assert abs(row_12["net_per48_both"] - 7.2) < 1e-6
    assert row_12["net_per48_a_without_b"] == 0.0
    assert abs(row_12["lift"] - 7.2) < 1e-6


def test_both_direction_rows_are_distinct():
    table = ntp.compute_pair_table(_fixture_stints())
    row_21 = table[(table["player_a"] == 2) & (table["player_b"] == 1)].iloc[0]
    # player 2 is NEVER on court without player 1 in this fixture -> 0 seconds
    assert row_21["a_without_b_seconds"] == 0.0
    row_12 = table[(table["player_a"] == 1) & (table["player_b"] == 2)].iloc[0]
    assert (row_12["player_a"], row_12["player_b"]) != (row_21["player_a"], row_21["player_b"])


def test_floor_skips_pairs_below_min_sample(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    claim = ntp.build_pair_claim("2025_26")

    ranked_pairs = {(r["player_a"], r["player_b"]) for r in claim["ranking"]}
    assert (2, 1) not in ranked_pairs  # below a_without_b_seconds floor (0 < 12000)
    assert (1, 3) not in ranked_pairs  # 3 never on-court without... (3 stays on in stint 2)
    assert (1, 2) in ranked_pairs  # 1 stays on, 2 leaves in stint 2 -> qualifies
    assert claim["n_excluded_below_floor"] >= 1
    # (1,2) and (3,2) are a genuine tie (7.2) in this fixture -- both 1 and 3 stay on
    # while 2 leaves in stint 2 -- so only the rank-1 VALUE, not a specific entity, is fixed.
    assert claim["ranking"][0]["value"] == 7.2
    assert claim["ranking"][0]["player_b"] == 2


def test_caveats_present(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    claim = ntp.build_pair_claim("2025_26")

    caveats_text = " ".join(claim["caveats"])
    assert "ROSTER CONFOUND" in caveats_text
    assert "COACH-DEPLOYMENT CONFOUND" in caveats_text
    assert "GARBAGE-TIME CONTAMINATION" in caveats_text
    assert claim["label"] == "DESCRIPTIVE_ONLY"
    assert claim["edge_claimed"] is False


def test_validator_verifies_pair_claim(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    # The validator resolves claim["source_files"] against ITS OWN REPO_ROOT
    # constant -- point it at the same fake root so it reads the same
    # on-disk snapshot the producer just wrote.
    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path)

    claim = ntp.build_pair_claim("2025_26")
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
