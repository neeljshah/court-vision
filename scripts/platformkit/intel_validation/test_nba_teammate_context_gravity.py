"""Per-file tests for nba_teammate_context_gravity.py.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_teammate_context_gravity.py -q

Acceptance criteria: gravity quartile assignment, with/without seconds
math, floor skip, caveat presence, validator VERIFIED round-trip.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_teammate_context_gravity as ntg
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_gravity() -> pd.DataFrame:
    # 4 players, one team. gravity_proxy = [10, 20, 30, 40] -> 75th pctile = 32.5
    # (linear interpolation: pos = 0.75*3 = 2.25 -> 30 + 0.25*(40-30) = 32.5)
    # -> only player 4 (40) clears the top-quartile threshold.
    return pd.DataFrame({
        "player_id": [1, 2, 3, 4], "team_id": [10, 10, 10, 10],
        "gravity_proxy": [10.0, 20.0, 30.0, 40.0],
    })


def _fixture_stints() -> pd.DataFrame:
    # Player 1 shares the floor with top-gravity player 4 in stint 1
    # (with_seconds=12000, pts_for=100 -> pts_per48_with = 100*48*60/12000 = 24)
    # and without him in stint 2 (without_seconds=12500, pts_for=50
    # -> pts_per48_without = 50*48*60/12500 = 11.52). delta = 12.48
    return pd.DataFrame({
        "game_id": ["g1", "g1"], "team_id": [10, 10],
        "lineup_key": ["1,2,3,4,5", "1,2,3,5,6"], "n_on_court": [5, 5],
        "elapsed_s": [12000.0, 12500.0],
        "pts_for": [100.0, 50.0], "pts_against": [0.0, 0.0],
    })


def _fixture_names() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [1, 2, 3, 4, 5, 6],
        "player_name": ["P1", "P2", "P3", "P4", "P5", "P6"],
    })


def _wire_fake_repo(tmp_path, monkeypatch):
    lineups_dir = tmp_path / "data" / "cache" / "team_system" / "lineups"
    lineups_dir.mkdir(parents=True)
    box_dir = tmp_path / "data" / "domains" / "basketball_nba"
    box_dir.mkdir(parents=True)
    _fixture_stints().to_parquet(lineups_dir / "stints_2025_26.parquet", index=False)
    _fixture_gravity().to_parquet(lineups_dir / "gravity_proxy_2025_26.parquet", index=False)
    _fixture_names().to_parquet(box_dir / "player_boxscores.parquet", index=False)

    monkeypatch.setattr(ntg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ntg, "_LINEUPS_DIR", lineups_dir)
    monkeypatch.setattr(ntg, "_BOX_SRC", box_dir / "player_boxscores.parquet")
    monkeypatch.setattr(ntg, "_OUT_DIR", tmp_path / "data" / "cache" / "intel_claims")


def test_gravity_threshold_is_75th_percentile():
    threshold = ntg.gravity_threshold(_fixture_gravity())
    assert abs(threshold - 32.5) < 1e-9


def test_quartile_assignment_and_seconds_math():
    table, threshold = ntg.compute_gravity_context(_fixture_stints(), _fixture_gravity())
    row1 = table[(table["player_id"] == 1) & (table["team_id"] == 10)].iloc[0]
    assert row1["with_seconds"] == 12000.0
    assert row1["without_seconds"] == 12500.0
    assert abs(row1["pts_per48_with"] - 24.0) < 1e-6
    assert abs(row1["pts_per48_without"] - 11.52) < 1e-6
    assert abs(threshold - 32.5) < 1e-9


def test_floor_skips_players_below_min_sample(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    claim = ntg.build_gravity_claim("2025_26")

    ranked_players = {r["player_id"] for r in claim["ranking"]}
    assert 1 in ranked_players  # 12000/12500 seconds both clear the 12000 floor
    # player 4 is the top-gravity teammate himself -- his own row (if any) has
    # with_seconds=0 (never shares the floor with ANOTHER top-gravity teammate)
    assert claim["n_excluded_below_floor"] >= 1


def test_caveats_present(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    claim = ntg.build_gravity_claim("2025_26")

    caveats_text = " ".join(claim["caveats"])
    assert "ROSTER CONFOUND" in caveats_text
    assert "COACH-DEPLOYMENT CONFOUND" in caveats_text
    assert "GARBAGE-TIME CONTAMINATION" in caveats_text
    assert "top-quartile gravity_proxy threshold" in caveats_text
    assert claim["label"] == "DESCRIPTIVE_ONLY"
    assert claim["edge_claimed"] is False


def test_validator_verifies_gravity_claim(tmp_path, monkeypatch):
    _wire_fake_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path)

    claim = ntg.build_gravity_claim("2025_26")
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
