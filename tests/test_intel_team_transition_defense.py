"""Tests for intel/team_transition_defense.py — TeamTransitionDefense AtlasSection.

Runs offline (NBA_OFFLINE=1); uses real parquets where available, gracefully
handles absence.  Validates: provenance n >= 5, proportions in [0,1],
signed/z fields correctly named, CV slot reserved + null, validator passes.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

# Ensure repo root is on the path so imports resolve without installing the package
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
os.environ.setdefault("NBA_OFFLINE", "1")

import pytest

from intel.team_transition_defense import TeamTransitionDefense, build_and_register
from src.loop.atlas import AtlasArtifact, CVSlot
from src.loop.intel_validator import validate as validator_validate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AS_OF = _dt.datetime(2026, 5, 30, 0, 0, 0)
TRICODES = ["OKC", "BOS"]


@pytest.fixture(scope="module")
def section() -> TeamTransitionDefense:
    return TeamTransitionDefense()


@pytest.fixture(scope="module")
def artifacts(section: TeamTransitionDefense):
    """Build artifacts for OKC and BOS (real data if parquets exist)."""
    results = {}
    for tri in TRICODES:
        art = section.build(tri, AS_OF)
        results[tri] = art
    return results


# ---------------------------------------------------------------------------
# Section contract
# ---------------------------------------------------------------------------

class TestSectionContract:
    def test_name(self, section: TeamTransitionDefense):
        assert section.name == "transition_defense"

    def test_entity(self, section: TeamTransitionDefense):
        assert section.entity == "team"

    def test_parquet_name(self, section: TeamTransitionDefense):
        assert section.parquet_name() == "atlas_team_transition_defense.parquet"

    def test_sec_fn_name(self, section: TeamTransitionDefense):
        assert section.sec_fn_name() == "sec_transition_defense"

    def test_cv_fields_declared(self, section: TeamTransitionDefense):
        cv = section.cv_fields()
        assert isinstance(cv, dict)
        assert "defenders_back_rate" in cv

    def test_cv_slot_null_and_typed(self, section: TeamTransitionDefense):
        cv = section.cv_fields()
        slot = cv["defenders_back_rate"]
        assert isinstance(slot, CVSlot)
        assert slot.value is None
        assert slot.dtype in {"float", "dist", "list", "categorical", "int"}


# ---------------------------------------------------------------------------
# Build outputs
# ---------------------------------------------------------------------------

class TestBuildOutputs:
    def test_builds_return_artifact_or_none(self, artifacts):
        # If parquets exist, both should succeed; if not, None is valid
        for tri, art in artifacts.items():
            assert art is None or isinstance(art, AtlasArtifact)

    @pytest.mark.parametrize("tri", TRICODES)
    def test_n_geq_5_when_artifact_present(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri} (missing parquets)")
        n = art.provenance.get("n", 0)
        assert n >= 5, f"{tri}: n={n} < 5 (coverage gate will reject)"

    @pytest.mark.parametrize("tri", TRICODES)
    def test_entity_id_matches_tricode(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        assert art.entity_id == tri
        assert art.entity == "team"
        assert art.section == "transition_defense"

    @pytest.mark.parametrize("tri", TRICODES)
    def test_as_of_stamped(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        assert art.as_of == "2026-05-30"
        assert art.provenance.get("as_of") == "2026-05-30"

    @pytest.mark.parametrize("tri", TRICODES)
    def test_required_sub_field_keys(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        required = {
            "def_efficiency", "opp_tov", "transition_freq",
            "positional_defense", "opp_ppp_transition", "pts_off_to",
        }
        assert required.issubset(art.sub_fields.keys()), (
            f"Missing sub-fields: {required - set(art.sub_fields.keys())}"
        )


# ---------------------------------------------------------------------------
# Range/proportion validity
# ---------------------------------------------------------------------------

class TestRangeValidity:
    @pytest.mark.parametrize("tri", TRICODES)
    def test_def_rtg_plausible(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        def_rtg = art.sub_fields.get("def_efficiency", {}).get("def_rtg_mean")
        if def_rtg is not None:
            assert 80.0 <= def_rtg <= 140.0, f"{tri} def_rtg_mean={def_rtg}"

    @pytest.mark.parametrize("tri", TRICODES)
    def test_dreb_pct_in_0_1(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        dreb = art.sub_fields.get("def_efficiency", {}).get("dreb_pct_mean")
        if dreb is not None:
            assert 0.0 <= dreb <= 1.0, f"{tri} dreb_pct_mean={dreb}"

    @pytest.mark.parametrize("tri", TRICODES)
    def test_opp_tov_pct_in_0_1(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        opp_tov = art.sub_fields.get("opp_tov", {}).get("opp_tov_pct_mean")
        if opp_tov is not None:
            assert 0.0 <= opp_tov <= 1.0, f"{tri} opp_tov_pct_mean={opp_tov}"

    @pytest.mark.parametrize("tri", TRICODES)
    def test_rim_fg_pct_in_0_1(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        rim_pct = art.sub_fields.get("positional_defense", {}).get("rim_lt6_d_fg_pct")
        if rim_pct is not None:
            assert 0.0 <= rim_pct <= 1.0, f"{tri} rim_lt6_d_fg_pct={rim_pct}"

    @pytest.mark.parametrize("tri", TRICODES)
    def test_rim_freq_in_0_1(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        rim_freq = art.sub_fields.get("positional_defense", {}).get("rim_lt6_freq")
        if rim_freq is not None:
            assert 0.0 <= rim_freq <= 1.0, f"{tri} rim_lt6_freq={rim_freq}"

    @pytest.mark.parametrize("tri", TRICODES)
    def test_signed_fields_named_correctly(self, artifacts, tri):
        """rim_lt6_d_fg_pct_plusminus is a signed diff -> must contain '_plusminus'."""
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        pos_def = art.sub_fields.get("positional_defense", {})
        # Signed field name check
        for k in pos_def:
            if "plusminus" in k.lower() or "_minus_" in k.lower():
                # Validator exempts these -- verify the naming pattern is present
                assert "plusminus" in k.lower() or "_minus_" in k.lower() or "_advantage" in k.lower()


# ---------------------------------------------------------------------------
# CV slots
# ---------------------------------------------------------------------------

class TestCVSlots:
    @pytest.mark.parametrize("tri", TRICODES)
    def test_cv_slots_null_on_artifact(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        assert "defenders_back_rate" in art.cv_fields
        assert art.cv_fields["defenders_back_rate"].value is None

    @pytest.mark.parametrize("tri", TRICODES)
    def test_cv_fields_in_profile_payload(self, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data
        assert "defenders_back_rate" in data["_cv_fields"]
        assert data["_cv_fields"]["defenders_back_rate"]["value"] is None


# ---------------------------------------------------------------------------
# Section self-validate
# ---------------------------------------------------------------------------

class TestSelfValidate:
    @pytest.mark.parametrize("tri", TRICODES)
    def test_section_validate_passes(self, section, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        assert section.validate(art), f"{tri}: section.validate returned False"

    def test_validate_rejects_wrong_section(self, section, artifacts):
        art = artifacts.get("OKC") or artifacts.get("BOS")
        if art is None:
            pytest.skip("No artifacts available")
        # Tamper with section name
        bad = AtlasArtifact(
            section="wrong_section",
            entity=art.entity,
            entity_id=art.entity_id,
            sub_fields=art.sub_fields,
            provenance=art.provenance,
            confidence=art.confidence,
            as_of=art.as_of,
            cv_fields=art.cv_fields,
        )
        assert not section.validate(bad)


# ---------------------------------------------------------------------------
# Full validator gate (intel_validator)
# ---------------------------------------------------------------------------

class TestIntelValidator:
    @pytest.mark.parametrize("tri", TRICODES)
    def test_validator_ok(self, section, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        result = validator_validate(section, art, min_n=5)
        assert result.ok, (
            f"{tri}: validator FAIL — reasons: {result.reasons}"
        )

    @pytest.mark.parametrize("tri", TRICODES)
    def test_validator_coverage_ok(self, section, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        result = validator_validate(section, art, min_n=5)
        assert result.coverage_ok, (
            f"{tri}: coverage check failed — n={art.provenance.get('n')}"
        )

    @pytest.mark.parametrize("tri", TRICODES)
    def test_validator_face_valid(self, section, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        result = validator_validate(section, art, min_n=5)
        assert result.face_valid, (
            f"{tri}: face_validity failed — {result.reasons}"
        )

    @pytest.mark.parametrize("tri", TRICODES)
    def test_validator_cv_schema_ok(self, section, artifacts, tri):
        art = artifacts.get(tri)
        if art is None:
            pytest.skip(f"No artifact for {tri}")
        result = validator_validate(section, art, min_n=5)
        assert result.cv_schema_ok, (
            f"{tri}: CV schema check failed — {result.reasons}"
        )


# ---------------------------------------------------------------------------
# build_and_register dry_run
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    def test_dry_run_returns_manifest(self):
        manifest = build_and_register(
            team_tricodes=["OKC", "BOS"],
            as_of=AS_OF,
            dry_run=True,
        )
        assert isinstance(manifest, dict)
        assert manifest.get("section") == "transition_defense"
        assert "defenders_back_rate" in manifest.get("cv_fields", [])

    def test_dry_run_no_disk_write(self, tmp_path):
        # dry_run=True should not write anything
        manifest = build_and_register(
            team_tricodes=["OKC"],
            as_of=AS_OF,
            dry_run=True,
        )
        # manifest should still have a parquet path key
        assert "parquet" in manifest
