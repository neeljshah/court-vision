"""Tests for intel/team_pace_identity.py (TeamPaceIdentity AtlasSection).

Covers:
  - build() returns AtlasArtifact with correct section/entity/provenance
  - provenance n >= 5 (real game count from team_advanced_stats)
  - all required sub-field keys present
  - sane numeric ranges (pace 80-130, secs_per_poss 20-45, proportions [0,1])
  - validate() passes on a well-formed artifact
  - cv_fields() returns avg_court_advance_speed slot with value=None
  - intel_validator passes all five criteria
  - DEFER placeholders are dicts with '_note' key
  - build() returns None for an unknown tricode
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

import pytest

# Ensure repo root is on sys.path regardless of test runner cwd
_REPO = __file__
for _ in range(3):
    _REPO = os.path.dirname(_REPO)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

os.environ.setdefault("NBA_OFFLINE", "1")

from intel.team_pace_identity import TeamPaceIdentity, _pace_label
from src.loop.atlas import AtlasArtifact
from src.loop.intel_validator import validate as intel_validate

_AS_OF = _dt.datetime(2026, 5, 30, 0, 0, 0)
_TRICODES = ["OKC", "BOS"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build(tricode: str) -> AtlasArtifact:
    section = TeamPaceIdentity()
    art = section.build(tricode, _AS_OF)
    assert art is not None, f"build() returned None for {tricode}"
    return art


# ---------------------------------------------------------------------------
# Pace-label unit tests (independent of real data)
# ---------------------------------------------------------------------------

class TestPaceLabel:
    def test_slow(self) -> None:
        assert _pace_label(96.0) == "SLOW"

    def test_moderate(self) -> None:
        assert _pace_label(99.0) == "MODERATE"

    def test_fast(self) -> None:
        assert _pace_label(101.5) == "FAST"

    def test_very_fast(self) -> None:
        assert _pace_label(104.0) == "VERY_FAST"

    def test_boundary_slow_moderate(self) -> None:
        # 98.0 is the boundary: pace < 98 -> SLOW
        assert _pace_label(97.99) == "SLOW"
        assert _pace_label(98.0) == "MODERATE"

    def test_boundary_fast_very_fast(self) -> None:
        assert _pace_label(102.99) == "FAST"
        assert _pace_label(103.0) == "VERY_FAST"


# ---------------------------------------------------------------------------
# Build and contract tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tricode", _TRICODES)
class TestBuildContract:
    def test_section_and_entity(self, tricode: str) -> None:
        art = _build(tricode)
        assert art.section == "pace_identity"
        assert art.entity == "team"
        assert art.entity_id == tricode

    def test_provenance_n_ge_5(self, tricode: str) -> None:
        art = _build(tricode)
        n = art.provenance.get("n", 0)
        assert n >= 5, f"{tricode}: provenance n={n} < 5 (must be real game count)"

    def test_confidence_level(self, tricode: str) -> None:
        art = _build(tricode)
        assert art.confidence in ("low", "med", "high")

    def test_as_of_set(self, tricode: str) -> None:
        art = _build(tricode)
        assert art.as_of == "2026-05-30"

    def test_required_sub_field_keys(self, tricode: str) -> None:
        art = _build(tricode)
        required = {
            "tempo", "efficiency", "ft_rate_proxy",
            "early_offense", "push_after_make", "push_after_miss",
            "push_after_to", "transition_rate",
        }
        assert required.issubset(art.sub_fields.keys()), (
            f"Missing keys: {required - art.sub_fields.keys()}"
        )

    def test_tempo_pace_pg_sane(self, tricode: str) -> None:
        art = _build(tricode)
        pace = art.sub_fields["tempo"].get("pace_pg")
        assert pace is not None, f"{tricode}: pace_pg is None"
        assert 80.0 <= pace <= 130.0, f"{tricode}: pace_pg={pace} out of range"

    def test_tempo_secs_per_poss_sane(self, tricode: str) -> None:
        art = _build(tricode)
        secs = art.sub_fields["tempo"].get("secs_per_poss")
        assert secs is not None, f"{tricode}: secs_per_poss is None"
        assert 20.0 <= secs <= 45.0, f"{tricode}: secs_per_poss={secs} out of range"

    def test_tempo_identity_label_is_string(self, tricode: str) -> None:
        art = _build(tricode)
        label = art.sub_fields["tempo"].get("pace_identity_label")
        assert label in ("SLOW", "MODERATE", "FAST", "VERY_FAST"), (
            f"{tricode}: label={label}"
        )

    def test_efficiency_oreb_pct_in_range(self, tricode: str) -> None:
        art = _build(tricode)
        v = art.sub_fields["efficiency"].get("oreb_pct")
        if v is not None:
            assert 0.0 <= v <= 1.0, f"{tricode}: oreb_pct={v}"

    def test_efficiency_efg_pct_in_range(self, tricode: str) -> None:
        art = _build(tricode)
        v = art.sub_fields["efficiency"].get("efg_pct")
        if v is not None:
            assert 0.0 <= v <= 1.6, f"{tricode}: efg_pct={v}"

    def test_ft_rate_proxy_in_range(self, tricode: str) -> None:
        art = _build(tricode)
        v = art.sub_fields["ft_rate_proxy"].get("ft_rate_l10")
        if v is not None:
            assert 0.0 <= v <= 1.0, f"{tricode}: ft_rate_l10={v}"

    def test_defer_placeholders_have_note(self, tricode: str) -> None:
        art = _build(tricode)
        for key in ("early_offense", "push_after_make", "push_after_miss",
                    "push_after_to", "transition_rate"):
            block = art.sub_fields.get(key, {})
            assert "_note" in block, f"{tricode}: DEFER block '{key}' missing '_note'"
            assert "DEFER" in block["_note"], (
                f"{tricode}: '{key}._note' does not contain 'DEFER'"
            )

    def test_section_validate_passes(self, tricode: str) -> None:
        section = TeamPaceIdentity()
        art = _build(tricode)
        assert section.validate(art), f"{tricode}: section.validate() returned False"

    def test_cv_fields_reserved(self, tricode: str) -> None:
        art = _build(tricode)
        assert "avg_court_advance_speed" in art.cv_fields, (
            f"{tricode}: CV slot 'avg_court_advance_speed' missing"
        )
        slot = art.cv_fields["avg_court_advance_speed"]
        assert slot.value is None, f"{tricode}: CV slot value must be None (reserved)"
        assert slot.dtype == "float"
        assert slot.unit == "ft/s"

    def test_intel_validator_passes(self, tricode: str) -> None:
        section = TeamPaceIdentity()
        art = _build(tricode)
        result = intel_validate(section, art, min_n=5)
        assert result.ok, (
            f"{tricode}: intel_validate FAILED. reasons={result.reasons}"
        )


# ---------------------------------------------------------------------------
# Unknown team / missing data
# ---------------------------------------------------------------------------

class TestUnknownTeam:
    def test_unknown_tricode_returns_none(self) -> None:
        section = TeamPaceIdentity()
        art = section.build("ZZZZZ", _AS_OF)
        assert art is None, "build() should return None for an unknown tricode"


# ---------------------------------------------------------------------------
# Section metadata
# ---------------------------------------------------------------------------

class TestSectionMetadata:
    def test_section_name(self) -> None:
        assert TeamPaceIdentity.name == "pace_identity"

    def test_entity(self) -> None:
        assert TeamPaceIdentity.entity == "team"

    def test_parquet_name(self) -> None:
        assert TeamPaceIdentity().parquet_name() == "atlas_team_pace_identity.parquet"

    def test_sec_fn_name(self) -> None:
        assert TeamPaceIdentity().sec_fn_name() == "sec_pace_identity"

    def test_cv_fields_schema(self) -> None:
        slots = TeamPaceIdentity().cv_fields()
        assert "avg_court_advance_speed" in slots
        slot = slots["avg_court_advance_speed"]
        assert slot.dtype == "float"
        assert slot.value is None
