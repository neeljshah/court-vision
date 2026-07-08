"""Per-file tests for wnba_lineup_claims: ranking + floor + negative-id
exclusion on synthetic frames, per (player_id, team_id)/(team_id, lineup_key)
entity keys, plus a real-data validator smoke test when the local corpus
is present.

Run: python -m pytest scripts/platformkit/intel_validation/test_wnba_lineup_claims.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import wnba_lineup_claims as m
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_on_off() -> pd.DataFrame:
    return pd.DataFrame([
        # qualifies, strongest net rating
        {"player_id": 10, "team_id": 1, "player_name": "A", "min_on": 350.0, "min_off": 200.0,
         "net_rating_on_per48": 8.0, "teammate_efg_on": 0.55, "teammate_efg_off": 0.45,
         "teammate_fga_on": 250, "teammate_fga_off": 250},
        # qualifies, weaker net rating
        {"player_id": 11, "team_id": 1, "player_name": "B", "min_on": 400.0, "min_off": 200.0,
         "net_rating_on_per48": 2.0, "teammate_efg_on": 0.50, "teammate_efg_off": 0.48,
         "teammate_fga_on": 300, "teammate_fga_off": 300},
        # below floor: min_on < 300
        {"player_id": 12, "team_id": 1, "player_name": "C", "min_on": 100.0, "min_off": 200.0,
         "net_rating_on_per48": 20.0, "teammate_efg_on": 0.60, "teammate_efg_off": 0.30,
         "teammate_fga_on": 300, "teammate_fga_off": 300},
        # negative-placeholder id -- must be excluded via player_id>=0
        {"player_id": -1, "team_id": 1, "player_name": "PLACEHOLDER", "min_on": 400.0, "min_off": 200.0,
         "net_rating_on_per48": 30.0, "teammate_efg_on": 0.70, "teammate_efg_off": 0.20,
         "teammate_fga_on": 300, "teammate_fga_off": 300},
    ])


def _fixture_spacing() -> pd.DataFrame:
    return pd.DataFrame([
        {"team_id": 1, "lineup_key": "10,11,12,13,14", "n_shots": 60, "spacing_mean_dist": 90.0},
        {"team_id": 1, "lineup_key": "20,21,22,23,24", "n_shots": 55, "spacing_mean_dist": 80.0},
        {"team_id": 1, "lineup_key": "30,31,32,33,34", "n_shots": 10, "spacing_mean_dist": 99.0},
    ])


def test_on_off_claim_applies_floor_and_negative_id_exclusion(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_LINEUPS_DIR", tmp_path)
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)
    src = tmp_path / "on_off_wnba_2026.parquet"
    _fixture_on_off().to_parquet(src)

    claim = m.build_on_off_claim()
    assert claim["n_considered"] == 4
    # excluded: min_on<300 row AND negative-id row
    assert claim["n_excluded_below_floor"] == 2
    ranked_ids = [r["player_id"] for r in claim["ranking"]]
    assert ranked_ids == [10, 11]
    assert 12 not in ranked_ids and -1 not in ranked_ids
    assert claim["ranking"][0]["value"] == 8.0
    assert "n=" in claim["ranking"][0]["text"]


def test_gravity_claim_computes_formula_and_applies_floors(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_LINEUPS_DIR", tmp_path)
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)
    src = tmp_path / "on_off_wnba_2026.parquet"
    _fixture_on_off().to_parquet(src)

    claim = m.build_gravity_claim()
    assert claim["n_considered"] == 4
    assert claim["n_excluded_below_floor"] == 2
    ranked_ids = [r["player_id"] for r in claim["ranking"]]
    assert ranked_ids == [10, 11]
    assert claim["ranking"][0]["value"] == round(0.55 - 0.45, 4)


def test_spacing_claim_applies_n_shots_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_LINEUPS_DIR", tmp_path)
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)
    src = tmp_path / "lineup_spacing_wnba_2026.parquet"
    _fixture_spacing().to_parquet(src)

    claim = m.build_spacing_claim()
    assert claim["n_considered"] == 3
    assert claim["n_excluded_below_floor"] == 1  # the 10-shot row
    ranked_keys = [r["lineup_key"] for r in claim["ranking"]]
    assert "30,31,32,33,34" not in ranked_keys
    assert ranked_keys == ["10,11,12,13,14", "20,21,22,23,24"]


def test_top_25_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_LINEUPS_DIR", tmp_path)
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(m, "TOP_N", 1)
    src = tmp_path / "on_off_wnba_2026.parquet"
    _fixture_on_off().to_parquet(src)
    claim = m.build_on_off_claim()
    assert len(claim["ranking"]) == 1
    assert claim["ranking"][0]["player_id"] == 10  # strongest, not just first-seen


@pytest.mark.skipif(
    not (m._LINEUPS_DIR / "on_off_wnba_2026.parquet").exists(),
    reason="local-only data not present",
)
def test_real_on_off_claim_independently_verifies():
    claim = m.build_on_off_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


@pytest.mark.skipif(
    not (m._LINEUPS_DIR / "lineup_spacing_wnba_2026.parquet").exists(),
    reason="local-only data not present",
)
def test_real_spacing_claim_independently_verifies():
    claim = m.build_spacing_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
