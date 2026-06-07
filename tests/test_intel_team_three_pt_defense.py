"""Tests for intel/team_three_pt_defense.py — TeamThreePtDefense atlas section.

Covers:
  - build() returns a valid AtlasArtifact for known teams (OKC, BOS)
  - provenance n >= 5 (real game count, not n_seasons)
  - opp_3pa_rate_allowed and opp_3p_pct_allowed are in [0, 1]
  - signed/z fields are correctly named (exempt from [0,1] validator gate)
  - as_of leak boundary works: future as_of returns data, past (before season) returns None
  - validate() passes for a well-formed artifact
  - cv_fields() declares avg_closeout_distance_cv with value=None
  - intel_validator checks pass (face_valid + coverage + cv_schema)
"""
from __future__ import annotations

import datetime as _dt
import sys
import os

import pytest

# Ensure NBA_OFFLINE=1 before any import that might touch live endpoints
os.environ.setdefault("NBA_OFFLINE", "1")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from intel.team_three_pt_defense import TeamThreePtDefense, build_and_register
from src.loop.atlas import AtlasArtifact
from src.loop.intel_validator import validate as intel_validate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AS_OF_FULL = _dt.datetime(2026, 5, 31)  # post-season: all games available
AS_OF_EARLY = _dt.datetime(2010, 1, 1)  # well before any parquet data: no games


@pytest.fixture(scope="module")
def section() -> TeamThreePtDefense:
    return TeamThreePtDefense()


@pytest.fixture(scope="module")
def okc_artifact(section: TeamThreePtDefense) -> AtlasArtifact:
    art = section.build("OKC", AS_OF_FULL)
    assert art is not None, "OKC build returned None — check team_advanced_stats.parquet"
    return art


@pytest.fixture(scope="module")
def bos_artifact(section: TeamThreePtDefense) -> AtlasArtifact:
    art = section.build("BOS", AS_OF_FULL)
    assert art is not None, "BOS build returned None — check team_advanced_stats.parquet"
    return art


# ---------------------------------------------------------------------------
# Section identity
# ---------------------------------------------------------------------------


def test_section_name(section: TeamThreePtDefense) -> None:
    assert section.name == "three_pt_defense"
    assert section.entity == "team"


# ---------------------------------------------------------------------------
# Build returns valid artifact for OKC + BOS
# ---------------------------------------------------------------------------


def test_okc_builds(okc_artifact: AtlasArtifact) -> None:
    assert okc_artifact.section == "three_pt_defense"
    assert okc_artifact.entity == "team"
    assert okc_artifact.entity_id == "OKC"


def test_bos_builds(bos_artifact: AtlasArtifact) -> None:
    assert bos_artifact.section == "three_pt_defense"
    assert bos_artifact.entity_id == "BOS"


# ---------------------------------------------------------------------------
# CRITICAL LESSON 1: provenance n must be real game count >= 5
# ---------------------------------------------------------------------------


def test_okc_provenance_n(okc_artifact: AtlasArtifact) -> None:
    n = okc_artifact.provenance.get("n", 0)
    assert n >= 5, f"OKC provenance n={n} < 5 (must be real game count)"


def test_bos_provenance_n(bos_artifact: AtlasArtifact) -> None:
    n = bos_artifact.provenance.get("n", 0)
    assert n >= 5, f"BOS provenance n={n} < 5 (must be real game count)"


# ---------------------------------------------------------------------------
# CRITICAL LESSON 3: proportions in [0, 1]
# ---------------------------------------------------------------------------


def test_okc_proportions_in_range(okc_artifact: AtlasArtifact) -> None:
    sf = okc_artifact.sub_fields
    opp = sf.get("opp_3pa_allowed", {})
    for field_name in ("opp_3pa_rate_allowed", "opp_3p_pct_allowed"):
        val = opp.get(field_name)
        if val is not None:
            assert 0.0 <= val <= 1.0, f"OKC {field_name}={val} out of [0,1]"


def test_bos_proportions_in_range(bos_artifact: AtlasArtifact) -> None:
    sf = bos_artifact.sub_fields
    opp = sf.get("opp_3pa_allowed", {})
    for field_name in ("opp_3pa_rate_allowed", "opp_3p_pct_allowed"):
        val = opp.get(field_name)
        if val is not None:
            assert 0.0 <= val <= 1.0, f"BOS {field_name}={val} out of [0,1]"


# ---------------------------------------------------------------------------
# CRITICAL LESSON 4: signed/z fields correctly named (exempt from [0,1])
# ---------------------------------------------------------------------------


def test_signed_fields_named_correctly(okc_artifact: AtlasArtifact) -> None:
    sf = okc_artifact.sub_fields
    opp = sf.get("opp_3pa_allowed", {})
    # plusminus: contains _minus_ in name → exempt from [0,1]
    plusminus = opp.get("opp_3p_pct_plusminus")
    # z-scores: end with _z → exempt from [0,1]
    z_pct = opp.get("opp_3p_pct_allowed_z")
    z_rate = opp.get("opp_3pa_rate_allowed_z")
    # trend: contains _trend (signed diff, not a proportion)
    dr = sf.get("def_rating", {})
    trend = dr.get("def_rtg_trend")
    # We only assert they are float or None (can be negative — that's correct)
    for name, val in [
        ("opp_3p_pct_plusminus", plusminus),
        ("opp_3p_pct_allowed_z", z_pct),
        ("opp_3pa_rate_allowed_z", z_rate),
        ("def_rtg_trend", trend),
    ]:
        assert val is None or isinstance(val, float), f"{name} has wrong type: {type(val)}"


# ---------------------------------------------------------------------------
# CRITICAL LESSON 5: leak-safe as_of
# ---------------------------------------------------------------------------


def test_pre_season_returns_none(section: TeamThreePtDefense) -> None:
    """Before the season starts, there are no games, so build returns None."""
    art = section.build("OKC", AS_OF_EARLY)
    assert art is None, f"Expected None for pre-season as_of; got {art}"


# ---------------------------------------------------------------------------
# sub_fields structure
# ---------------------------------------------------------------------------


def test_required_sub_fields_present(okc_artifact: AtlasArtifact) -> None:
    sf = okc_artifact.sub_fields
    required = {
        "opp_3pa_allowed",
        "def_rating",
        "closeout",
        "corner_vs_above_break",
        "run_off_line",
    }
    missing = required - set(sf.keys())
    assert not missing, f"Missing sub_fields: {missing}"


def test_defer_fields_have_note(okc_artifact: AtlasArtifact) -> None:
    sf = okc_artifact.sub_fields
    for defer_key in ("corner_vs_above_break", "run_off_line"):
        sub = sf.get(defer_key, {})
        assert "_note" in sub, f"DEFER field '{defer_key}' missing _note"
        assert "DEFER" in sub["_note"], f"'{defer_key}._note' does not say DEFER"


# ---------------------------------------------------------------------------
# CV slot schema (CRITICAL LESSON 5)
# ---------------------------------------------------------------------------


def test_cv_fields_declared(section: TeamThreePtDefense) -> None:
    cv = section.cv_fields()
    assert "avg_closeout_distance_cv" in cv
    slot = cv["avg_closeout_distance_cv"]
    assert slot.value is None
    assert slot.dtype == "float"
    assert slot.unit == "ft"


def test_artifact_cv_slots_null(okc_artifact: AtlasArtifact) -> None:
    for name, slot in okc_artifact.cv_fields.items():
        assert slot.value is None, f"CV slot {name} has non-null value before CV branch"


# ---------------------------------------------------------------------------
# section.validate()
# ---------------------------------------------------------------------------


def test_section_validate_okc(section: TeamThreePtDefense, okc_artifact: AtlasArtifact) -> None:
    assert section.validate(okc_artifact), "section.validate() returned False for OKC"


def test_section_validate_bos(section: TeamThreePtDefense, bos_artifact: AtlasArtifact) -> None:
    assert section.validate(bos_artifact), "section.validate() returned False for BOS"


# ---------------------------------------------------------------------------
# intel_validator full gate
# ---------------------------------------------------------------------------


def test_intel_validator_okc(section: TeamThreePtDefense, okc_artifact: AtlasArtifact) -> None:
    result = intel_validate(section, okc_artifact, min_n=5)
    assert result.face_valid, f"OKC face_valid failed: {result.reasons}"
    assert result.coverage_ok, f"OKC coverage failed: {result.reasons}"
    assert result.cv_schema_ok, f"OKC cv_schema failed: {result.reasons}"
    assert result.ok, f"OKC validator not OK: {result.reasons}"


def test_intel_validator_bos(section: TeamThreePtDefense, bos_artifact: AtlasArtifact) -> None:
    result = intel_validate(section, bos_artifact, min_n=5)
    assert result.face_valid, f"BOS face_valid failed: {result.reasons}"
    assert result.coverage_ok, f"BOS coverage failed: {result.reasons}"
    assert result.cv_schema_ok, f"BOS cv_schema failed: {result.reasons}"
    assert result.ok, f"BOS validator not OK: {result.reasons}"


# ---------------------------------------------------------------------------
# build_and_register (dry_run)
# ---------------------------------------------------------------------------


def test_build_and_register_dry_run() -> None:
    manifest = build_and_register(
        team_tricodes=["OKC", "BOS"],
        as_of=AS_OF_FULL,
        dry_run=True,
    )
    assert manifest["section"] == "three_pt_defense"
    assert manifest["n_entities"] == 2
    assert "avg_closeout_distance_cv" in manifest["cv_fields"]
