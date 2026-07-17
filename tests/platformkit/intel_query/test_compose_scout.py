"""Per-file test: python -m pytest tests/platformkit/intel_query/test_compose_scout.py -q

compose_scout has no profiles_dir injection seam (it reads the real profiles
parquet + concept registry through contracts.answer_superlative), so the
happy-path axes are exercised against the real NBA artifacts and SKIPPED when
they are absent from a clean clone. The fail-closed paths (unknown player,
sport with no registry) need no data and always run.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from scripts.platformkit.intel_query import compose_scout as cs

_NBA_PARQUET = os.path.join(cs._profiles.PROFILES_DIR, "nba_player_profiles.parquet")
_have_nba = os.path.exists(_NBA_PARQUET)


@pytest.mark.skipif(not _have_nba, reason="nba_player_profiles.parquet absent in this clone")
def test_known_player_is_multi_axis_vector_with_shooting_facet():
    r = cs.compose_scout("nba", "LeBron James")
    assert r["status"] == "ok"
    assert r["category"] == "scouting_report"
    assert r["edge_claimed"] is False
    # Multi-axis VECTOR: more than one concept axis, none collapsed into a score.
    ok_axes = [a for a in r["concept_axes"] if a["status"] == "ok"]
    assert len(ok_axes) >= 2
    for a in ok_axes:
        assert a["rating"] is not None and a["percentile"] is not None
        assert a["citation"]["source_artifact"].endswith("nba_player_profiles.parquet")
    # Shooting facet present (NBA claim-based) and top raw attributes present.
    assert "shooting_facet" in r and "status" in r["shooting_facet"]
    assert r["raw_attributes"]["status"] == "ok"
    assert len(r["raw_attributes"]["attributes"]) >= 1
    assert r["axes_hit"]["shooting_facet"] is True
    # injury_context block: always present, NBA -> mlb_injury_recency is n/a.
    assert "injury_context" in r
    assert r["injury_context"]["injury_facts"]["status"] in ("ok", "no_data", "refused")
    assert r["injury_context"]["mlb_injury_recency"]["status"] == "not_applicable"


def test_injury_context_absent_injury_store_reports_reason_not_kill_dossier():
    """No injury facts store built (or lookup raises) -> injury_facts marked
    absent with a reason; the rest of the dossier is unaffected."""
    block = cs._injury_facts_block("nba", "Nobody Real Player")
    assert block["status"] in ("no_data", "refused")
    assert block.get("note") or block.get("status") == "refused"


def test_injury_context_mlb_recency_block_absent_claim_reports_no_data(monkeypatch):
    def _raise(*a, **kw):
        raise RuntimeError("store missing")

    monkeypatch.setattr(
        "scripts.platformkit.intel_query.ask.load_verified_claims", _raise, raising=False
    )
    block = cs._mlb_injury_recency_block(123456)
    assert block["status"] == "no_data"
    assert "note" in block


def test_injury_context_mlb_recency_not_in_ranking_when_id_absent():
    r = cs._injury_context("mlb", "Some Player", entity_id=999999999)
    assert r["mlb_injury_recency"]["status"] in ("ok", "not_in_ranking", "no_data")
    if r["mlb_injury_recency"]["status"] == "not_in_ranking":
        assert "citation" in r["mlb_injury_recency"]
        assert r["mlb_injury_recency"]["citation"]["claim_id"] == cs._MLB_INJURY_RECENCY_CLAIM_ID


def test_injury_context_non_mlb_sport_is_not_applicable():
    r = cs._injury_context("tennis", "Roger Federer", entity_id=None)
    assert r["mlb_injury_recency"]["status"] == "not_applicable"


def test_unknown_player_is_unanswerable_no_data():
    r = cs.compose_scout("nba", "Zzzq Notaplayer Xyz")
    assert r["status"] == "no_data"
    assert r["answerable"] is False
    assert r["missing"] and "NO scouting axis" in r["missing"][0]


def test_sport_without_registry_is_no_data():
    r = cs.compose_scout("cricket", "Somebody")
    assert r["status"] == "no_data"
    assert r["answerable"] is False
    assert "no concept registry" in r["note"]


def test_resolve_entity_dedupes_dup_spelling_of_same_id():
    """gap 2 (docs/research/resolver_coverage_2026_07_17.md): the parquet
    can carry two different entity_name spellings for the SAME entity_id
    (nba_player_profiles.parquet has plain + accented "Luka Doncic" both
    under 1629029) -- that must collapse to ONE candidate, not inflate a
    real 2-way tie (vs "Luka Garza") into a false 3-way ambiguity."""
    df = pd.DataFrame([
        {"entity_id": 1629029, "entity_name": "Luka Doncic", "sport": "nba"},
        {"entity_id": 1629029, "entity_name": "Luka Dončić", "sport": "nba"},  # accented dup spelling
        {"entity_id": 99, "entity_name": "Luka Garza", "sport": "nba"},
    ])
    status, payload = cs._resolve_entity(df, "Luka")
    assert status == "ambiguous"
    assert len(payload) == 2  # 2 distinct entity_ids, not 3


def test_resolve_entity_unique_match_is_ok():
    df = pd.DataFrame([{"entity_id": 1, "entity_name": "LeBron James", "sport": "nba"}])
    status, payload = cs._resolve_entity(df, "LeBron James")
    assert status == "ok"
    assert payload == (1, "LeBron James")


def test_resolve_entity_no_match_is_no_entity():
    df = pd.DataFrame([{"entity_id": 1, "entity_name": "LeBron James", "sport": "nba"}])
    status, payload = cs._resolve_entity(df, "Zzzq Notaplayer Xyz")
    assert status == "no_entity"
    assert payload is None


def test_compose_scout_surfaces_ambiguous_with_candidates():
    """compose_scout's top-level envelope must expose status='ambiguous' +
    candidates, not collapse into a misleading 'no scouting data' no_data
    (the original gap-2 symptom)."""

    class _FakeReg:
        def list_concepts(self):
            return []

    orig_get_registry = cs.get_registry
    orig_load_profiles = cs._profiles.load_profiles
    try:
        cs.get_registry = lambda sport: _FakeReg()
        df = pd.DataFrame([
            {"entity_id": 1629029, "entity_name": "Luka Doncic", "sport": "nba", "kind": "player"},
            {"entity_id": 1629029, "entity_name": "Luka Dončić", "sport": "nba", "kind": "player"},
            {"entity_id": 99, "entity_name": "Luka Garza", "sport": "nba", "kind": "player"},
        ])
        cs._profiles.load_profiles = lambda sport: df
        r = cs.compose_scout("nba", "Luka")
        assert r["status"] == "ambiguous"
        assert len(r["candidates"]) == 2
    finally:
        cs.get_registry = orig_get_registry
        cs._profiles.load_profiles = orig_load_profiles
