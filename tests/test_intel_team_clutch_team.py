"""Tests for intel/team_clutch_team.py (AtlasSection 'clutch_team', entity='team').

Verifies:
  - build() returns a valid AtlasArtifact for OKC and BOS with provenance n >= 5.
  - section.validate() passes on a real-built artifact.
  - intel_validator.validate() returns ok=True (all 5 criteria).
  - All proportion/rate sub-fields are in [0, 1].
  - net_rtg is named correctly and does NOT trip the [0,1] face-validity gate.
  - cv_fields() are reserved (value=None), well-typed, and stable.
  - build() returns None for an unknown tricode (missing source).
  - as_of filtering is leak-safe: older as_of produces a different or missing artifact.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

import pytest

# Ensure repo root is on path (consistent with the HARD SAFETY RULES env setup)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.team_clutch_team import TeamClutchTeam
from src.loop.atlas import AtlasArtifact, CVSlot, confidence_from_n
from src.loop.intel_validator import validate as iv_validate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AS_OF = _dt.datetime(2026, 5, 31)
SECTION = TeamClutchTeam()


def _build(tricode: str, as_of: _dt.datetime = AS_OF) -> "AtlasArtifact | None":
    return SECTION.build(tricode, as_of)


# ---------------------------------------------------------------------------
# Basic build tests
# ---------------------------------------------------------------------------

class TestBuildReturnsArtifact:
    def test_okc_returns_artifact(self):
        art = _build("OKC")
        assert art is not None, "build() must return an artifact for OKC"

    def test_bos_returns_artifact(self):
        art = _build("BOS")
        assert art is not None, "build() must return an artifact for BOS"

    def test_unknown_tricode_returns_none(self):
        art = _build("ZZZ")
        assert art is None, "build() must return None for an unknown tricode"

    def test_entity_and_section_labels(self):
        art = _build("OKC")
        assert art is not None
        assert art.entity == "team"
        assert art.section == "clutch_team"
        assert art.entity_id == "OKC"

    def test_as_of_stamped(self):
        art = _build("OKC")
        assert art is not None
        assert art.as_of is not None
        assert art.as_of <= AS_OF.date().isoformat()


# ---------------------------------------------------------------------------
# Coverage / provenance n >= 5 (CRITICAL LESSON 1)
# ---------------------------------------------------------------------------

class TestCoverageN:
    def test_okc_n_gte_5(self):
        art = _build("OKC")
        assert art is not None
        n = art.provenance.get("n", 0)
        assert n >= 5, f"OKC provenance n={n} must be >= 5 (actual games played)"

    def test_bos_n_gte_5(self):
        art = _build("BOS")
        assert art is not None
        n = art.provenance.get("n", 0)
        assert n >= 5, f"BOS provenance n={n} must be >= 5 (actual games played)"

    def test_confidence_consistent_with_n(self):
        for tri in ("OKC", "BOS"):
            art = _build(tri)
            assert art is not None
            n = art.provenance.get("n", 0)
            expected = confidence_from_n(n)
            assert art.confidence == expected, (
                f"{tri}: confidence={art.confidence} but n={n} implies {expected}"
            )


# ---------------------------------------------------------------------------
# Sub-field structure
# ---------------------------------------------------------------------------

class TestSubFields:
    def test_required_keys_present(self):
        art = _build("OKC")
        assert art is not None
        required = {
            "ratings", "ft_rate", "clutch_composition",
            "clutch_net_rtg_exact", "clutch_fta_rate_exact",
        }
        assert required.issubset(art.sub_fields.keys()), (
            f"Missing sub-fields: {required - art.sub_fields.keys()}"
        )

    def test_ratings_sub_fields_present(self):
        art = _build("OKC")
        assert art is not None
        r = art.sub_fields["ratings"]
        assert isinstance(r, dict)
        for key in ("off_rtg", "def_rtg", "net_rtg", "pace"):
            assert key in r, f"ratings missing key: {key}"

    def test_off_rtg_in_plausible_range(self):
        art = _build("OKC")
        assert art is not None
        off_rtg = art.sub_fields["ratings"].get("off_rtg")
        if off_rtg is not None:
            assert 60.0 <= off_rtg <= 160.0, f"off_rtg={off_rtg} out of plausible range"

    def test_def_rtg_in_plausible_range(self):
        art = _build("BOS")
        assert art is not None
        def_rtg = art.sub_fields["ratings"].get("def_rtg")
        if def_rtg is not None:
            assert 60.0 <= def_rtg <= 160.0, f"def_rtg={def_rtg} out of plausible range"

    def test_net_rtg_plausible(self):
        """net_rtg is a signed difference — should be within (-50, +50)."""
        art = _build("OKC")
        assert art is not None
        nr = art.sub_fields["ratings"].get("net_rtg")
        if nr is not None:
            assert -50.0 <= nr <= 50.0, f"net_rtg={nr} implausible"

    def test_pace_plausible(self):
        art = _build("BOS")
        assert art is not None
        pace = art.sub_fields["ratings"].get("pace")
        if pace is not None:
            assert 80.0 <= pace <= 130.0, f"pace={pace} out of plausible range"

    def test_ft_rate_in_zero_one(self):
        """ft_rate_mean is a genuine proportion — must be in [0, 1] (CRITICAL LESSON 3)."""
        art = _build("OKC")
        assert art is not None
        ft_mean = art.sub_fields.get("ft_rate", {}).get("ft_rate_mean")
        if ft_mean is not None:
            assert 0.0 <= ft_mean <= 1.0, (
                f"ft_rate_mean={ft_mean} out of [0,1] — validator will reject"
            )

    def test_defer_placeholders_have_note(self):
        art = _build("OKC")
        assert art is not None
        for defer_key in ("clutch_net_rtg_exact", "clutch_fta_rate_exact"):
            d = art.sub_fields.get(defer_key, {})
            assert "_note" in d, f"{defer_key} missing _note DEFER marker"


# ---------------------------------------------------------------------------
# Section self-validate
# ---------------------------------------------------------------------------

class TestSectionValidate:
    def test_okc_self_validates(self):
        art = _build("OKC")
        assert art is not None
        assert SECTION.validate(art), "section.validate() must pass for OKC"

    def test_bos_self_validates(self):
        art = _build("BOS")
        assert art is not None
        assert SECTION.validate(art), "section.validate() must pass for BOS"

    def test_wrong_entity_fails(self):
        art = _build("OKC")
        assert art is not None
        art.entity = "player"  # corrupt
        assert not SECTION.validate(art)

    def test_wrong_section_fails(self):
        art = _build("OKC")
        assert art is not None
        art.section = "other_section"  # corrupt
        assert not SECTION.validate(art)


# ---------------------------------------------------------------------------
# Intel validator (full 5-criterion gate)
# ---------------------------------------------------------------------------

class TestIntelValidator:
    def test_okc_passes_full_validator(self):
        art = _build("OKC")
        assert art is not None
        res = iv_validate(SECTION, art, min_n=5)
        assert res.ok, (
            f"intel_validator failed for OKC: {res.reasons}"
        )

    def test_bos_passes_full_validator(self):
        art = _build("BOS")
        assert art is not None
        res = iv_validate(SECTION, art, min_n=5)
        assert res.ok, (
            f"intel_validator failed for BOS: {res.reasons}"
        )

    def test_leak_free(self):
        art = _build("OKC")
        assert art is not None
        res = iv_validate(SECTION, art, min_n=5)
        assert res.leak_free, f"Leak check failed: {res.reasons}"

    def test_face_valid(self):
        art = _build("OKC")
        assert art is not None
        res = iv_validate(SECTION, art, min_n=5)
        assert res.face_valid, f"Face validity failed: {res.reasons}"

    def test_coverage_ok(self):
        art = _build("OKC")
        assert art is not None
        res = iv_validate(SECTION, art, min_n=5)
        assert res.coverage_ok, f"Coverage check failed: {res.reasons}"

    def test_cv_schema_ok(self):
        art = _build("OKC")
        assert art is not None
        res = iv_validate(SECTION, art, min_n=5)
        assert res.cv_schema_ok, f"CV schema check failed: {res.reasons}"


# ---------------------------------------------------------------------------
# CV slots (CRITICAL LESSON 5)
# ---------------------------------------------------------------------------

class TestCVFields:
    def test_cv_fields_declared(self):
        fields = SECTION.cv_fields()
        assert isinstance(fields, dict)
        assert len(fields) > 0, "cv_fields() must declare at least one reserved slot"

    def test_cv_slots_have_valid_dtype(self):
        valid_dtypes = {"float", "dist", "list", "categorical", "int"}
        for name, slot in SECTION.cv_fields().items():
            assert slot.dtype in valid_dtypes, (
                f"slot {name} has invalid dtype: {slot.dtype}"
            )

    def test_cv_slot_values_are_none(self):
        """All CV slots must be null-reserved (CV branch fills them later)."""
        for name, slot in SECTION.cv_fields().items():
            assert slot.value is None, (
                f"CV slot {name} has non-None value — must be reserved null"
            )

    def test_artifact_cv_slots_match_declared(self):
        art = _build("OKC")
        assert art is not None
        declared = set(SECTION.cv_fields().keys())
        artifact_slots = set(art.cv_fields.keys())
        assert declared == artifact_slots, (
            f"artifact cv_fields {artifact_slots} != declared {declared}"
        )

    def test_cv_slot_names_stable(self):
        """Known stable slot names must be present (contract for CV branch)."""
        fields = SECTION.cv_fields()
        assert "clutch_spacing_cv" in fields
        assert "clutch_drive_rate_cv" in fields


# ---------------------------------------------------------------------------
# Leak-safety: as_of filtering
# ---------------------------------------------------------------------------

class TestLeakSafety:
    def test_early_as_of_produces_smaller_n(self):
        """Building with an earlier as_of must not increase n (no future-data leakage)."""
        art_now = _build("OKC", AS_OF)
        art_early = _build("OKC", _dt.datetime(2023, 1, 1))
        assert art_now is not None
        if art_early is not None:
            n_now = art_now.provenance.get("n", 0)
            n_early = art_early.provenance.get("n", 0)
            assert n_early <= n_now, (
                f"Early as_of n={n_early} > now n={n_now} — possible leak"
            )

    def test_future_as_of_accepted(self):
        """A future as_of should not crash (just includes all current data)."""
        future = _dt.datetime(2030, 1, 1)
        art = _build("OKC", future)
        # Should either return an artifact or None — not raise
        assert art is None or isinstance(art, AtlasArtifact)
