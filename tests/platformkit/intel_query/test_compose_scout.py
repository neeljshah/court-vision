"""Per-file test: python -m pytest tests/platformkit/intel_query/test_compose_scout.py -q

compose_scout has no profiles_dir injection seam (it reads the real profiles
parquet + concept registry through contracts.answer_superlative), so the
happy-path axes are exercised against the real NBA artifacts and SKIPPED when
they are absent from a clean clone. The fail-closed paths (unknown player,
sport with no registry) need no data and always run.
"""
from __future__ import annotations

import os

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
