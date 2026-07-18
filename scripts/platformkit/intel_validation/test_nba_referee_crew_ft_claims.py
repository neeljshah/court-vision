"""Per-file tests for nba_referee_crew_ft_claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_referee_crew_ft_claims.py -q

Acceptance:
  1. load_officials_by_season: missing season file skipped honestly.
  2. build_crew_long: one row per (game_id, official).
  3. build_game_stats: both-teams-combined per-game PF/FTA sum.
  4. build_snapshot: officials with no boxscore-backed game excluded (inner join).
  5. Golden asserts: heavy-environment official ranks first for both metrics.
  6. Validator VERIFIED end-to-end against the written snapshot parquet.
  7. edge_claimed False + forbidden-edge-token ban + b2b-hypothesis disclaimer.
  8. Empty-ranking honest skip.

All fixtures are tiny synthetic tmp_path/in-memory frames (<50 rows) -- no
real data/ is read or written by this test.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_referee_crew_ft_claims as rft

FLOOR = rft.FLOOR_GAMES


def test_load_officials_by_season_skips_missing_file(tmp_path):
    (tmp_path / "officials_2023-24.json").write_text(json.dumps({"g1": ["A. Ref", "B. Ump"]}))
    out = rft.load_officials_by_season(seasons=("2022-23", "2023-24"), officials_dir=tmp_path)
    assert "2022-23" not in out  # missing file skipped, not raised
    assert out["2023-24"] == {"g1": ["A. Ref", "B. Ump"]}


def test_build_crew_long_one_row_per_official():
    officials_by_season = {"2023-24": {"g1": ["A. Ref", "B. Ump"], "g2": ["A. Ref"]}}
    crew = rft.build_crew_long(officials_by_season)
    assert len(crew) == 3
    assert set(crew["official"]) == {"A. Ref", "B. Ump"}


def test_build_game_stats_sums_both_teams():
    box = pd.DataFrame([
        {"game_id": "g1", "pf": 10, "fta": 20},
        {"game_id": "g1", "pf": 12, "fta": 18},  # other team, same game
        {"game_id": "g2", "pf": 5, "fta": 8},
    ])
    stats = rft.build_game_stats(box)
    g1 = stats[stats["game_id"] == "g1"].iloc[0]
    assert g1["total_pf"] == 22
    assert g1["total_fta"] == 38


def test_build_snapshot_excludes_officials_with_no_boxscore_game():
    officials_by_season = {"2023-24": {
        "g1": ["A. Ref"], "g2": ["A. Ref"], "g_missing": ["A. Ref"], "g3": ["B. Ump"]}}
    game_stats = pd.DataFrame([
        {"game_id": "g1", "total_pf": 40, "total_fta": 50},
        {"game_id": "g2", "total_pf": 44, "total_fta": 54},
        {"game_id": "g3", "total_pf": 30, "total_fta": 32},
        # g_missing has no boxscore row -- dropped by the inner join
    ])
    snapshot = rft.build_snapshot(officials_by_season, game_stats)
    a_ref = snapshot[snapshot["entity_id"] == "A. Ref"].iloc[0]
    assert a_ref["n_games"] == 2  # g1, g2 only -- g_missing excluded, not zero-filled
    assert pytest.approx(a_ref["mean_pf"], abs=1e-9) == 42.0
    b_ump = snapshot[snapshot["entity_id"] == "B. Ump"].iloc[0]
    assert b_ump["n_games"] == 1


def _build_snapshot_fixture(n_light: int, n_heavy: int) -> pd.DataFrame:
    """light official: pf=30/fta=32 every game. heavy official: pf=60/fta=64
    every game. Both cleared of the n_games floor by caller args."""
    officials_by_season = {"2023-24": {}}
    game_stats_rows = []
    for i in range(n_light):
        gid = f"L{i}"
        officials_by_season["2023-24"][gid] = ["Light Ref"]
        game_stats_rows.append({"game_id": gid, "total_pf": 30, "total_fta": 32})
    for i in range(n_heavy):
        gid = f"H{i}"
        officials_by_season["2023-24"][gid] = ["Heavy Ref"]
        game_stats_rows.append({"game_id": gid, "total_pf": 60, "total_fta": 64})
    game_stats = pd.DataFrame(game_stats_rows)
    return rft.build_snapshot(officials_by_season, game_stats)


def test_floor_excludes_below_floor_officials():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR - 5)
    claim = rft._build_ranking_claim(snapshot, "mean_pf", "mean_pf_environment")
    ranked = {r["entity_id"] for r in claim["ranking"]}
    assert "Light Ref" in ranked  # n=FLOOR+5, clears
    assert "Heavy Ref" not in ranked  # n=FLOOR-5, excluded
    assert claim["n_excluded_below_floor"] >= 1


def test_golden_heavy_environment_ranks_first():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    pf_claim = rft._build_ranking_claim(snapshot, "mean_pf", "mean_pf_environment")
    assert pf_claim["ranking"][0]["entity_id"] == "Heavy Ref"  # 60 >> 30
    fta_claim = rft._build_ranking_claim(snapshot, "mean_fta", "mean_fta_environment")
    assert fta_claim["ranking"][0]["entity_id"] == "Heavy Ref"


def test_empty_ranking_is_skipped_honestly():
    empty = pd.DataFrame(columns=["entity_id", "official", "n_games", "mean_pf", "mean_fta"])
    assert rft.build_all_claims(empty) == []


def test_validator_independently_reverifies(tmp_path, monkeypatch):
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    snap_path = tmp_path / "nba_referee_crew_ft_snapshot.parquet"
    monkeypatch.setattr(rft, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rft, "_SNAPSHOT_PATH", snap_path)
    rft.write_snapshot(snapshot, snap_path)
    claim = rft._build_ranking_claim(snapshot, "mean_pf", "mean_pf_environment")

    import scripts.platformkit.intel_validation.claims_validator as cv_mod
    orig_root = cv_mod.REPO_ROOT
    cv_mod.REPO_ROOT = tmp_path
    try:
        verdict = claims_validator.validate_claim(claim)
    finally:
        cv_mod.REPO_ROOT = orig_root
    assert verdict.verdict == "VERIFIED", verdict.reason


_FORBIDDEN_TOKENS = ("edge", "roi", "$", "bankroll", "beat", "profit")


def test_honest_caveats_and_edge_claimed_false():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    for claim in rft.build_all_claims(snapshot):
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        negation_clause = "not an advantage, not a beatable gap, not a predictor -- no market/roi/dollar edge is claimed"
        stripped = blob.replace(negation_clause, "")
        for word in _FORBIDDEN_TOKENS:
            assert word not in stripped, f"forbidden token {word!r} found outside negation context"
        assert "not an advantage" in blob
        assert "not a predictor" in blob
        assert "crew_b2b_fatigue" in blob  # disclaims the causal sibling family
