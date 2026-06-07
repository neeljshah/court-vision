"""Tests for intel/team_paint_defense.py — TeamPaintDefense AtlasSection.

Verifies:
  - Contract compliance (section name, entity, cv_fields reserved/null)
  - Leak-safety (as_of filtering: build at distant past returns None or sane artifact)
  - Face-validity (proportions in [0,1], def_rtg in plausible range)
  - provenance n >= 5 (actual game count, not n_seasons) for OKC/BOS
  - validate() passes for a well-formed artifact
  - DEFER placeholders present for blk_pg and paint_touch_rate
  - build_and_register dry_run returns a manifest with expected keys
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path for src.loop imports
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("NBA_OFFLINE", "1")

from intel.team_paint_defense import TeamPaintDefense, build_and_register  # noqa: E402
from src.loop.atlas import AtlasArtifact  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AS_OF_FULL = _dt.datetime(2026, 5, 31, 0, 0, 0)
_AS_OF_PAST = _dt.datetime(2020, 1, 1, 0, 0, 0)  # before any data


@pytest.fixture(scope="module")
def section() -> TeamPaintDefense:
    return TeamPaintDefense()


@pytest.fixture(scope="module")
def okc_artifact(section: TeamPaintDefense) -> AtlasArtifact:
    art = section.build("OKC", _AS_OF_FULL)
    assert art is not None, "OKC build returned None — check team_advanced_stats.parquet"
    return art


@pytest.fixture(scope="module")
def bos_artifact(section: TeamPaintDefense) -> AtlasArtifact:
    art = section.build("BOS", _AS_OF_FULL)
    assert art is not None, "BOS build returned None — check team_advanced_stats.parquet"
    return art


# ---------------------------------------------------------------------------
# Contract / metadata tests
# ---------------------------------------------------------------------------

class TestContract:
    def test_section_name(self, section: TeamPaintDefense) -> None:
        assert section.name == "paint_defense"

    def test_entity_is_team(self, section: TeamPaintDefense) -> None:
        assert section.entity == "team"

    def test_parquet_name(self, section: TeamPaintDefense) -> None:
        assert section.parquet_name() == "atlas_team_paint_defense.parquet"

    def test_sec_fn_name(self, section: TeamPaintDefense) -> None:
        assert section.sec_fn_name() == "sec_paint_defense"

    def test_cv_fields_keys(self, section: TeamPaintDefense) -> None:
        cv = section.cv_fields()
        assert "avg_rim_contest" in cv

    def test_cv_fields_values_are_none(self, section: TeamPaintDefense) -> None:
        cv = section.cv_fields()
        for slot in cv.values():
            assert slot.value is None, f"CV slot {slot.name} has non-None value"

    def test_cv_fields_dtype(self, section: TeamPaintDefense) -> None:
        cv = section.cv_fields()
        assert cv["avg_rim_contest"].dtype == "float"
        assert cv["avg_rim_contest"].unit == "ft"


# ---------------------------------------------------------------------------
# Build output structure tests
# ---------------------------------------------------------------------------

class TestBuildStructure:
    def test_okc_section(self, okc_artifact: AtlasArtifact) -> None:
        assert okc_artifact.section == "paint_defense"

    def test_okc_entity(self, okc_artifact: AtlasArtifact) -> None:
        assert okc_artifact.entity == "team"

    def test_okc_entity_id_uppercase(self, okc_artifact: AtlasArtifact) -> None:
        assert okc_artifact.entity_id == "OKC"

    def test_required_sub_field_keys(self, okc_artifact: AtlasArtifact) -> None:
        required = {"opp_paint_allowed", "rim_defense", "def_rtg", "blk_pg", "paint_touch_rate"}
        assert required.issubset(okc_artifact.sub_fields.keys())

    def test_defer_blk_pg_present(self, okc_artifact: AtlasArtifact) -> None:
        blk = okc_artifact.sub_fields.get("blk_pg", {})
        assert "_note" in blk, "blk_pg DEFER note missing"
        assert "DEFER" in blk["_note"]

    def test_defer_paint_touch_present(self, okc_artifact: AtlasArtifact) -> None:
        pt = okc_artifact.sub_fields.get("paint_touch_rate", {})
        assert "_note" in pt, "paint_touch_rate DEFER note missing"
        assert "DEFER" in pt["_note"]

    def test_cv_slots_embedded(self, okc_artifact: AtlasArtifact) -> None:
        assert "avg_rim_contest" in okc_artifact.cv_fields
        assert okc_artifact.cv_fields["avg_rim_contest"].value is None

    def test_as_of_str_format(self, okc_artifact: AtlasArtifact) -> None:
        # Should be YYYY-MM-DD
        assert okc_artifact.as_of is not None
        parts = okc_artifact.as_of.split("-")
        assert len(parts) == 3

    def test_provenance_has_source(self, okc_artifact: AtlasArtifact) -> None:
        assert "source" in okc_artifact.provenance
        assert len(okc_artifact.provenance["source"]) > 0


# ---------------------------------------------------------------------------
# Coverage (n >= 5) — CRITICAL LESSON 1
# ---------------------------------------------------------------------------

class TestCoverage:
    def test_okc_n_ge_5(self, okc_artifact: AtlasArtifact) -> None:
        n = okc_artifact.provenance.get("n", 0)
        assert n >= 5, f"OKC provenance n={n} — must be actual game count >= 5"

    def test_bos_n_ge_5(self, bos_artifact: AtlasArtifact) -> None:
        n = bos_artifact.provenance.get("n", 0)
        assert n >= 5, f"BOS provenance n={n} — must be actual game count >= 5"

    def test_okc_confidence_not_low(self, okc_artifact: AtlasArtifact) -> None:
        assert okc_artifact.confidence in ("med", "high"), (
            f"OKC confidence={okc_artifact.confidence} — expected med or high"
        )

    def test_bos_confidence_not_low(self, bos_artifact: AtlasArtifact) -> None:
        assert bos_artifact.confidence in ("med", "high"), (
            f"BOS confidence={bos_artifact.confidence} — expected med or high"
        )


# ---------------------------------------------------------------------------
# Face-validity / proportion range checks
# ---------------------------------------------------------------------------

class TestFaceValidity:
    def test_def_rtg_in_range(self, okc_artifact: AtlasArtifact) -> None:
        def_rtg = okc_artifact.sub_fields.get("def_rtg", {}).get("def_rtg")
        if def_rtg is not None:
            assert 90.0 <= def_rtg <= 135.0, f"def_rtg={def_rtg} out of range"

    def test_rim_fg_pct_in_0_1(self, okc_artifact: AtlasArtifact) -> None:
        pct = okc_artifact.sub_fields.get("rim_defense", {}).get("rim_fg_pct_allowed")
        if pct is not None:
            assert 0.0 <= pct <= 1.0, f"rim_fg_pct_allowed={pct} out of [0,1]"

    def test_paint_fg_pct_in_0_1(self, okc_artifact: AtlasArtifact) -> None:
        pct = okc_artifact.sub_fields.get("rim_defense", {}).get("paint_fg_pct_allowed")
        if pct is not None:
            assert 0.0 <= pct <= 1.0, f"paint_fg_pct_allowed={pct} out of [0,1]"

    def test_dreb_pct_in_0_1(self, okc_artifact: AtlasArtifact) -> None:
        dreb = okc_artifact.sub_fields.get("def_rtg", {}).get("dreb_pct")
        if dreb is not None:
            assert 0.0 <= dreb <= 1.0, f"dreb_pct={dreb} out of [0,1]"

    def test_rim_freq_faced_in_0_1(self, okc_artifact: AtlasArtifact) -> None:
        freq = okc_artifact.sub_fields.get("rim_defense", {}).get("rim_freq_faced")
        if freq is not None:
            assert 0.0 <= freq <= 1.0, f"rim_freq_faced={freq} out of [0,1]"

    def test_z_scores_can_be_negative(self, okc_artifact: AtlasArtifact) -> None:
        """Z-scores are legitimately negative — validate() must not reject them."""
        opp = okc_artifact.sub_fields.get("opp_paint_allowed", {})
        z = opp.get("opp_paint_pct_allowed_z")
        # Just ensure the field is present and numeric (can be negative)
        if z is not None:
            assert isinstance(z, (int, float))


# ---------------------------------------------------------------------------
# validate() method
# ---------------------------------------------------------------------------

class TestValidate:
    def test_validate_okc(self, section: TeamPaintDefense, okc_artifact: AtlasArtifact) -> None:
        assert section.validate(okc_artifact), "validate() returned False for OKC"

    def test_validate_bos(self, section: TeamPaintDefense, bos_artifact: AtlasArtifact) -> None:
        assert section.validate(bos_artifact), "validate() returned False for BOS"

    def test_validate_wrong_section_fails(
        self, section: TeamPaintDefense, okc_artifact: AtlasArtifact
    ) -> None:
        bad = AtlasArtifact(
            section="wrong_section",
            entity="team",
            entity_id="OKC",
            sub_fields=okc_artifact.sub_fields,
            provenance=okc_artifact.provenance,
            confidence=okc_artifact.confidence,
            as_of=okc_artifact.as_of,
            cv_fields=okc_artifact.cv_fields,
        )
        assert not section.validate(bad)

    def test_validate_wrong_entity_fails(
        self, section: TeamPaintDefense, okc_artifact: AtlasArtifact
    ) -> None:
        bad = AtlasArtifact(
            section="paint_defense",
            entity="player",
            entity_id="OKC",
            sub_fields=okc_artifact.sub_fields,
            provenance=okc_artifact.provenance,
            confidence=okc_artifact.confidence,
            as_of=okc_artifact.as_of,
            cv_fields=okc_artifact.cv_fields,
        )
        assert not section.validate(bad)


# ---------------------------------------------------------------------------
# Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    def test_distant_past_returns_none(self, section: TeamPaintDefense) -> None:
        """Build at as_of before any data should return None (no games in source)."""
        art = section.build("OKC", _AS_OF_PAST)
        assert art is None, (
            "Expected None for as_of before any data; got an artifact "
            "(possible data-leak: source has rows before 2020-01-01)"
        )

    def test_as_of_respected_in_provenance(self, okc_artifact: AtlasArtifact) -> None:
        """Provenance as_of must not be after the artifact as_of."""
        prov_date = okc_artifact.provenance.get("as_of")
        art_date = okc_artifact.as_of
        if prov_date and art_date:
            assert prov_date <= art_date, (
                f"provenance.as_of={prov_date} > artifact.as_of={art_date} — leak!"
            )


# ---------------------------------------------------------------------------
# to_profile_payload()
# ---------------------------------------------------------------------------

class TestProfilePayload:
    def test_payload_has_cv_fields(self, okc_artifact: AtlasArtifact) -> None:
        data, prov = okc_artifact.to_profile_payload()
        assert "_cv_fields" in data
        assert "avg_rim_contest" in data["_cv_fields"]
        assert data["_cv_fields"]["avg_rim_contest"]["value"] is None

    def test_payload_prov_has_n(self, okc_artifact: AtlasArtifact) -> None:
        _data, prov = okc_artifact.to_profile_payload()
        assert isinstance(prov.get("n"), int)
        assert prov["n"] >= 5


# ---------------------------------------------------------------------------
# dry-run registration
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    def test_dry_run_manifest(self) -> None:
        manifest = build_and_register(
            team_tricodes=["OKC", "BOS"],
            as_of=_AS_OF_FULL,
            dry_run=True,
        )
        assert manifest["section"] == "paint_defense"
        assert manifest["n_entities"] >= 1
        assert "avg_rim_contest" in manifest["cv_fields"]
        assert manifest["sec_fn"] == "sec_paint_defense"

    def test_dry_run_no_disk_write(self) -> None:
        """dry_run=True must NOT write the parquet to disk."""
        parquet = Path(_REPO) / "data" / "cache" / "atlas_team_paint_defense.parquet"
        existed_before = parquet.exists()
        build_and_register(
            team_tricodes=["DAL"],
            as_of=_AS_OF_FULL,
            dry_run=True,
        )
        assert parquet.exists() == existed_before, (
            "dry_run=True should not write parquet to disk"
        )
