"""Tests for intel/player_foul_drawing.py -- leak-safety + schema-conformance.

Run with:
    NBA_OFFLINE=1 python -m pytest tests/test_intel_player_foul_drawing.py -v

Two classes of checks:
  1. LEAK-SAFETY -- re-building at an earlier as_of must never return games
     from after that date (the n from the earlier build must be <= the n from
     the later build, and the earlier artifact.as_of must equal the earlier
     build date).
  2. SCHEMA-CONFORMANCE -- the artifact and its cv_fields must satisfy the
     AtlasSection contract (required sub-field keys, proportions in [0,1],
     CV slots null-valued, confidence/provenance well-formed).
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Optional

import pytest

# Ensure repo root is on sys.path
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from intel.player_foul_drawing import PlayerFoulDrawing
from src.loop.atlas import AtlasArtifact, confidence_from_n
from src.loop.intel_validator import (
    check_coverage,
    check_cv_schema,
    check_face_validity,
    check_leak_free,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JOKIC = 203999
CURRY = 201939
# A player almost certainly absent from all sources (synthetic dummy)
DUMMY_PID = 99999999

_AS_OF_PRESENT = _dt.datetime(2026, 5, 31, 0, 0, 0)
_AS_OF_PAST = _dt.datetime(2020, 1, 1, 0, 0, 0)  # before any 2024-25 data


@pytest.fixture(scope="module")
def section() -> PlayerFoulDrawing:
    """Shared PlayerFoulDrawing instance (section is stateless)."""
    return PlayerFoulDrawing()


@pytest.fixture(scope="module")
def jokic_artifact(section: PlayerFoulDrawing) -> Optional[AtlasArtifact]:
    """Build artifact for Jokic as-of the present cutoff."""
    return section.build(JOKIC, _AS_OF_PRESENT)


@pytest.fixture(scope="module")
def curry_artifact(section: PlayerFoulDrawing) -> Optional[AtlasArtifact]:
    """Build artifact for Curry as-of the present cutoff."""
    return section.build(CURRY, _AS_OF_PRESENT)


# ---------------------------------------------------------------------------
# Basic existence
# ---------------------------------------------------------------------------

class TestArtifactExists:
    """Artifacts build without raising and return an AtlasArtifact or None."""

    def test_jokic_builds(self, section: PlayerFoulDrawing) -> None:
        art = section.build(JOKIC, _AS_OF_PRESENT)
        assert art is None or isinstance(art, AtlasArtifact)

    def test_curry_builds(self, section: PlayerFoulDrawing) -> None:
        art = section.build(CURRY, _AS_OF_PRESENT)
        assert art is None or isinstance(art, AtlasArtifact)

    def test_dummy_player_returns_none(self, section: PlayerFoulDrawing) -> None:
        art = section.build(DUMMY_PID, _AS_OF_PRESENT)
        assert art is None

    def test_far_past_as_of_does_not_crash(self, section: PlayerFoulDrawing) -> None:
        """Building with a date before any data should return None (not raise)."""
        try:
            art = section.build(JOKIC, _AS_OF_PAST)
        except Exception as exc:
            pytest.fail(f"build() raised unexpectedly: {exc!r}")


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact structure, field names, and type rules."""

    def test_section_metadata(self, section: PlayerFoulDrawing) -> None:
        assert section.name == "foul_drawing"
        assert section.entity == "player"

    def test_required_sub_fields_present(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        required = {
            "ft_generation", "drive_draw", "contact_seeking",
            "and_one", "shooting_foul_share", "hustle_draw",
        }
        assert required.issubset(jokic_artifact.sub_fields.keys()), (
            f"Missing: {required - jokic_artifact.sub_fields.keys()}"
        )

    def test_entity_and_section_stamped(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        assert jokic_artifact.entity == "player"
        assert jokic_artifact.section == "foul_drawing"
        assert jokic_artifact.entity_id == JOKIC

    def test_as_of_present_in_artifact(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        assert jokic_artifact.as_of is not None
        assert len(jokic_artifact.as_of) >= 10

    def test_provenance_has_n_source_confidence(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        prov = jokic_artifact.provenance
        assert "n" in prov
        assert "source" in prov
        assert "confidence" in prov
        assert prov["confidence"] in ("low", "med", "high")

    def test_n_is_actual_game_count_not_seasons(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        """n must reflect actual game rows (>=5 for med or high confidence)."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        n = jokic_artifact.provenance["n"]
        assert isinstance(n, int), f"n must be int, got {type(n)}"
        # If confidence is med or high, n must support it
        if jokic_artifact.confidence in ("med", "high"):
            assert n >= 5, f"confidence={jokic_artifact.confidence} but n={n}"
        if jokic_artifact.confidence == "high":
            assert n >= 20, f"confidence=high but n={n}"

    def test_proportions_in_0_1(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        """All _pct / _share / _freq / _rate leaf values must be in [0, 1]."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")

        def _walk(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _walk(v, f"{path}.{k}")
            elif isinstance(obj, (int, float)):
                leaf = path.split(".")[-1].lower()
                if any(leaf.endswith(s) for s in (
                    "_pct", "_rate", "_share", "_freq", "freq_pct"
                )):
                    assert 0.0 <= obj <= 1.0, (
                        f"{path}={obj} is a proportion but out of [0,1]"
                    )

        _walk(jokic_artifact.sub_fields)

    def test_per_game_fields_non_negative(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        """Fields ending _pg must be >= 0."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")

        def _walk_pg(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _walk_pg(v, f"{path}.{k}")
            elif isinstance(obj, (int, float)):
                if path.split(".")[-1].lower().endswith("_pg"):
                    assert obj >= 0, f"{path}={obj} is negative"

        _walk_pg(jokic_artifact.sub_fields)


# ---------------------------------------------------------------------------
# CV slot schema
# ---------------------------------------------------------------------------

class TestCVSlotSchema:
    """CV reserved slots must be well-typed and null-valued."""

    def test_cv_fields_declared(self, section: PlayerFoulDrawing) -> None:
        slots = section.cv_fields()
        assert isinstance(slots, dict)
        assert len(slots) >= 1, "foul_drawing must declare at least 1 CV slot"

    def test_contact_seek_rate_slot_present(self, section: PlayerFoulDrawing) -> None:
        slots = section.cv_fields()
        assert "contact_seek_rate" in slots

    def test_all_cv_slots_null(self, section: PlayerFoulDrawing) -> None:
        for name, slot in section.cv_fields().items():
            assert slot.value is None, f"CV slot '{name}' is pre-populated"

    def test_all_cv_slots_valid_dtype(self, section: PlayerFoulDrawing) -> None:
        valid_dtypes = {"float", "dist", "list", "categorical", "int"}
        for name, slot in section.cv_fields().items():
            assert slot.dtype in valid_dtypes, (
                f"CV slot '{name}' has invalid dtype '{slot.dtype}'"
            )

    def test_cv_schema_check_passes(
        self,
        section: PlayerFoulDrawing,
        jokic_artifact: Optional[AtlasArtifact],
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        assert check_cv_schema(section, jokic_artifact), (
            "intel_validator.check_cv_schema failed for Jokic foul_drawing"
        )


# ---------------------------------------------------------------------------
# Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Leak boundary: an earlier as_of must never include data from after that date."""

    def test_artifact_as_of_matches_build_date(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        expected = _AS_OF_PRESENT.date().isoformat()
        assert jokic_artifact.as_of == expected, (
            f"Stamped as_of {jokic_artifact.as_of!r} != build date {expected!r}"
        )

    def test_earlier_as_of_n_leq_present_n(self, section: PlayerFoulDrawing) -> None:
        """Games seen at an earlier cutoff cannot exceed games at a later cutoff."""
        earlier = _dt.datetime(2025, 3, 1, 0, 0, 0)
        art_early = section.build(JOKIC, earlier)
        art_now = section.build(JOKIC, _AS_OF_PRESENT)
        if art_early is None or art_now is None:
            pytest.skip("Artifact(s) not built (data absent)")
        n_early = art_early.provenance["n"]
        n_now = art_now.provenance["n"]
        assert n_early <= n_now, (
            f"Earlier build has n={n_early} > later build n={n_now} -- potential leak"
        )

    def test_earlier_artifact_as_of_not_in_future(
        self, section: PlayerFoulDrawing
    ) -> None:
        earlier = _dt.datetime(2025, 3, 1, 0, 0, 0)
        art_early = section.build(JOKIC, earlier)
        if art_early is None:
            pytest.skip("Earlier artifact not built (data absent)")
        # The stamped as_of must be <= the build date
        assert art_early.as_of <= earlier.date().isoformat(), (
            f"Stamped as_of {art_early.as_of!r} is AFTER build date {earlier.date()!r}"
        )

    def test_intel_validator_leak_check(
        self,
        section: PlayerFoulDrawing,
        jokic_artifact: Optional[AtlasArtifact],
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        assert check_leak_free(section, jokic_artifact), (
            "intel_validator.check_leak_free failed for Jokic foul_drawing"
        )


# ---------------------------------------------------------------------------
# Coverage gate
# ---------------------------------------------------------------------------

class TestCoverage:
    """n >= 5 for med/high confidence; face-validity passes."""

    def test_jokic_coverage_min5(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        assert check_coverage(jokic_artifact, min_n=5), (
            f"Jokic n={jokic_artifact.provenance['n']} < 5 (min_n gate)"
        )

    def test_curry_coverage_min5(
        self, curry_artifact: Optional[AtlasArtifact]
    ) -> None:
        if curry_artifact is None:
            pytest.skip("Curry artifact not built (data absent)")
        assert check_coverage(curry_artifact, min_n=5), (
            f"Curry n={curry_artifact.provenance['n']} < 5 (min_n gate)"
        )

    def test_face_validity_jokic(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        reasons = check_face_validity(jokic_artifact)
        assert not reasons, f"Face-validity failures: {reasons}"

    def test_face_validity_curry(
        self, curry_artifact: Optional[AtlasArtifact]
    ) -> None:
        if curry_artifact is None:
            pytest.skip("Curry artifact not built (data absent)")
        reasons = check_face_validity(curry_artifact)
        assert not reasons, f"Face-validity failures: {reasons}"

    def test_section_self_validate_jokic(
        self,
        section: PlayerFoulDrawing,
        jokic_artifact: Optional[AtlasArtifact],
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        assert section.validate(jokic_artifact), "section.validate() returned False"

    def test_section_self_validate_curry(
        self,
        section: PlayerFoulDrawing,
        curry_artifact: Optional[AtlasArtifact],
    ) -> None:
        if curry_artifact is None:
            pytest.skip("Curry artifact not built (data absent)")
        assert section.validate(curry_artifact), "section.validate() returned False"


# ---------------------------------------------------------------------------
# to_profile_payload round-trip
# ---------------------------------------------------------------------------

class TestProfilePayload:
    """to_profile_payload() must return a (data, prov) 2-tuple."""

    def test_payload_is_2tuple(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        result = jokic_artifact.to_profile_payload()
        assert isinstance(result, tuple) and len(result) == 2

    def test_payload_data_has_cv_fields_key(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        data, _ = jokic_artifact.to_profile_payload()
        assert "_cv_fields" in data

    def test_payload_prov_shape(
        self, jokic_artifact: Optional[AtlasArtifact]
    ) -> None:
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (data absent)")
        _, prov = jokic_artifact.to_profile_payload()
        assert set(prov.keys()) == {"source", "n", "confidence", "as_of"}
        assert isinstance(prov["n"], int)
