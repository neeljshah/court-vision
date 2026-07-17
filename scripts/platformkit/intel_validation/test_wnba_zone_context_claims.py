"""Per-file tests for wnba_zone_context_claims (Depth-wave-1 Lane 1).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_wnba_zone_context_claims.py -q

Acceptance:
  1. FULL POPULATION: every entity clearing FLOOR is ranked, no top-N cap;
     below-floor entities are counted honestly in n_excluded_below_floor.
  2. Sorted desc by raw_value; entity_key="entity_id" matches the ranking dict key.
  3. Validator VERIFIED end-to-end on a synthetic parquet fixture.
  4. Honest caveats + edge_claimed False, no forbidden edge words.
  5. Golden asserts: known top entity present, below-floor entity absent.
"""
from __future__ import annotations

import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import wnba_zone_context_claims as zc


@pytest.fixture()
def fixture_source(tmp_path, monkeypatch):
    # entity_id, entity_name, raw_value, n -- one row below FLOOR (n=8), rest qualify
    df = pd.DataFrame({
        "entity_id": ["100", "101", "102", "103"],
        "entity_name": ["A. Wilson", "B. Stewart", "C. Below", "D. Ionescu"],
        "raw_value": [0.55, 0.62, 0.48, 0.70],
        "n": [15, 30, 8, 22],
    })
    src_dir = tmp_path / "intel_claims"
    src_dir.mkdir(parents=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), src_dir / "wnba_profile_source_zone_rim_efg.parquet")
    monkeypatch.setattr(zc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(zc, "_SRC_DIR", src_dir)
    return src_dir


@pytest.fixture()
def fixture_source_nameless(tmp_path, monkeypatch):
    # legacy source snapshot with no entity_name column -- graceful degrade
    df = pd.DataFrame({
        "entity_id": ["200", "201"],
        "raw_value": [0.44, 0.58],
        "n": [12, 25],
    })
    src_dir = tmp_path / "intel_claims"
    src_dir.mkdir(parents=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), src_dir / "wnba_profile_source_zone_rim_efg.parquet")
    monkeypatch.setattr(zc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(zc, "_SRC_DIR", src_dir)
    return src_dir


def test_full_population_no_top_n_cap_and_honest_exclusion(fixture_source):
    claim = zc.build_claim("zone_rim_efg")
    assert claim["n_considered"] == 4
    assert claim["n_excluded_below_floor"] == 1  # entity 102, n=8 < FLOOR=10
    assert len(claim["ranking"]) == 3
    ranked_ids = {r["entity_id"] for r in claim["ranking"]}
    assert "102" not in ranked_ids


def test_sorted_desc_and_entity_key_matches(fixture_source):
    claim = zc.build_claim("zone_rim_efg")
    assert claim["criteria"]["entity_key"] == "entity_id"
    values = [r["value"] for r in claim["ranking"]]
    assert values == sorted(values, reverse=True)
    ranks = [r["rank"] for r in claim["ranking"]]
    assert ranks == list(range(1, len(ranks) + 1))


def test_golden_top_entity_and_below_floor_absent(fixture_source):
    claim = zc.build_claim("zone_rim_efg")
    assert claim["ranking"][0]["entity_id"] == "103"  # raw_value=0.70, highest
    assert claim["ranking"][0]["value"] == 0.70
    assert claim["ranking"][0]["entity_name"] == "D. Ionescu"
    ranked_ids = {r["entity_id"] for r in claim["ranking"]}
    assert "102" not in ranked_ids  # below-floor entity never ranked


def test_entity_name_fallback_for_nameless_source(fixture_source_nameless):
    claim = zc.build_claim("zone_rim_efg")
    assert claim["ranking"][0]["entity_id"] == "201"
    assert claim["ranking"][0]["entity_name"] == "201"  # falls back to entity_id


def test_validator_independently_reverifies(fixture_source):
    claim = zc.build_claim("zone_rim_efg")
    import scripts.platformkit.intel_validation.claims_validator as cv_mod
    orig_root = cv_mod.REPO_ROOT
    cv_mod.REPO_ROOT = zc.REPO_ROOT
    try:
        verdict = claims_validator.validate_claim(claim)
    finally:
        cv_mod.REPO_ROOT = orig_root
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_honest_caveats_and_edge_claimed_false(fixture_source):
    claim = zc.build_claim("zone_rim_efg")
    assert claim["edge_claimed"] is False
    blob = json.dumps([claim["caveats"], claim["question"]]).lower()
    for word in ("roi", "pnl", "$", "bankroll"):
        assert word not in blob
    assert "descriptive" in blob
    assert "floor" in blob


def test_available_dimensions_skips_missing_source(fixture_source):
    # only zone_rim_efg's source parquet was written by the fixture; the
    # other 3 declared dimensions have no on-disk file in this tmp_path.
    avail = zc.available_dimensions()
    assert avail == ["zone_rim_efg"]


def test_build_all_claims_matches_available_dimensions(fixture_source):
    claims = zc.build_all_claims()
    assert len(claims) == 1
    assert claims[0]["claim_id"] == "wnba_zone_context_zone_rim_efg_full_2026"
