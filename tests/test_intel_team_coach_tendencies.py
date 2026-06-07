"""Tests for intel/team_coach_tendencies.py (TeamCoachTendencies AtlasSection).

Covers:
  1. Leak-safety: build with as_of in the past produces no data stamped after as_of.
  2. Schema conformance: AtlasArtifact has required sub_fields + cv_fields present.
  3. CV fields are all null (unfilled until CV branch runs).
  4. validate() accepts a well-formed artifact.
  5. validate() rejects a structurally bad artifact.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict
import sys
import os

# Ensure repo root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.loop.atlas import AtlasArtifact, CVSlot
from intel.team_coach_tendencies import TeamCoachTendencies, build_and_register


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SECTION = TeamCoachTendencies()

# A historical as_of that is before ANY real game data (so data may be sparse
# but the leak assertion is meaningful regardless of data presence).
PAST_AS_OF = _dt.datetime(2020, 1, 1, 0, 0, 0)

# A recent as_of used for schema tests (may or may not return data).
RECENT_AS_OF = _dt.datetime(2026, 5, 30, 0, 0, 0)

# A known team tricode present in team_advanced_stats
TEAM = "GSW"


# ---------------------------------------------------------------------------
# Helper: build artifact or construct a synthetic one for schema tests
# ---------------------------------------------------------------------------

def _make_synthetic_artifact(team: str = TEAM, n: int = 30) -> AtlasArtifact:
    """Construct a minimal valid artifact for schema/validate tests."""
    from src.loop.atlas import confidence_from_n
    conf = confidence_from_n(n)
    sub_fields: Dict[str, Any] = {
        "timeout_usage": {
            "to_avg_per_period": 3.1,
            "high_to_rate": 0.25,
            "n_games": n,
        },
        "lineup_rotation": {
            "dnp_per_game_avg": 0.8,
            "rotation_unique_5mans_avg": 34.5,
            "platoon_patterns": {"_note": "DEFER"},
        },
        "late_game_behavior": {
            "blowout_pct_l5_avg": 0.12,
            "garbage_time_pct_l5_avg": 0.08,
            "clutch_shots_pg_team": 4.2,
        },
        "hack_a": {
            "hacka_proxy_rate": 0.07,
            "avg_late_pf_cum": 7.3,
            "target_player": {"_note": "DEFER"},
        },
        "tempo_style": {
            "pace_mean": 99.4,
            "off_rtg_mean": 114.2,
            "def_rtg_mean": 110.8,
        },
    }
    prov = {
        "source": SECTION.source_name,
        "n": n,
        "confidence": conf,
        "as_of": RECENT_AS_OF.date().isoformat(),
    }
    return AtlasArtifact(
        section=SECTION.name,
        entity=SECTION.entity,
        entity_id=team,
        value=None,
        sub_fields=sub_fields,
        provenance=prov,
        confidence=conf,
        as_of=RECENT_AS_OF.date().isoformat(),
        cv_fields=SECTION.cv_fields(),
    )


# ---------------------------------------------------------------------------
# Test 1: Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that build() with a past as_of never returns data stamped after that date."""

    def test_build_past_as_of_no_future_data(self) -> None:
        """Building with PAST_AS_OF must produce no artifact, or one with as_of <= past."""
        art = SECTION.build(TEAM, PAST_AS_OF)
        if art is None:
            # Acceptable: no data before PAST_AS_OF exists
            return
        # If an artifact is returned, its as_of must be <= the requested date
        assert art.as_of is not None, "as_of must be set on the artifact"
        artifact_date = _dt.date.fromisoformat(art.as_of)
        assert artifact_date <= PAST_AS_OF.date(), (
            f"Artifact as_of {art.as_of} is AFTER the requested as_of "
            f"{PAST_AS_OF.date().isoformat()} — LEAK detected!"
        )

    def test_build_past_as_of_sub_field_n_games_plausible(self) -> None:
        """If an artifact is returned for PAST_AS_OF, n must be tiny (no future games)."""
        art = SECTION.build(TEAM, PAST_AS_OF)
        if art is None:
            return  # no data — fine
        # provenance n should reflect only games before 2020-01-01
        n = art.provenance.get("n", 0)
        # NBA game counts before 2020-01-01 for any team capped at ~3 full seasons ~246
        assert n <= 300, f"n={n} seems implausibly high for data before 2020-01-01"


# ---------------------------------------------------------------------------
# Test 2 + 3: Schema conformance + CV fields present and null
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Verify AtlasArtifact structural contract."""

    def test_required_sub_fields_present(self) -> None:
        """All 5 required top-level sub_fields must be present."""
        art = _make_synthetic_artifact()
        required = {
            "timeout_usage", "lineup_rotation", "late_game_behavior",
            "hack_a", "tempo_style",
        }
        missing = required - set(art.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {missing}"

    def test_cv_fields_schema_present(self) -> None:
        """cv_fields() must return all 3 reserved CV slots."""
        cv = SECTION.cv_fields()
        expected_slots = {"spacing_off_bench", "transition_pace_cv", "sub_pattern_frame"}
        assert expected_slots == set(cv.keys()), (
            f"cv_fields mismatch: got {set(cv.keys())}, expected {expected_slots}"
        )

    def test_cv_fields_all_null(self) -> None:
        """All CV slot values must be None (unfilled until CV branch runs)."""
        cv = SECTION.cv_fields()
        for slot_name, slot in cv.items():
            assert slot.value is None, (
                f"CV slot '{slot_name}' has value={slot.value!r}; "
                "must be None until CV branch fills it"
            )

    def test_cv_slots_have_dtype_and_description(self) -> None:
        """Each CV slot must have a non-empty dtype and description."""
        for slot_name, slot in SECTION.cv_fields().items():
            assert slot.dtype, f"CV slot '{slot_name}' has empty dtype"
            assert slot.description, f"CV slot '{slot_name}' has empty description"

    def test_artifact_cv_fields_match_section(self) -> None:
        """AtlasArtifact built with cv_fields() must carry all section CV slots."""
        art = _make_synthetic_artifact()
        section_slots = set(SECTION.cv_fields().keys())
        artifact_slots = set(art.cv_fields.keys())
        assert section_slots == artifact_slots, (
            f"Artifact cv_fields {artifact_slots} != section cv_fields {section_slots}"
        )

    def test_to_profile_payload_shape(self) -> None:
        """to_profile_payload() must return (data_dict, prov_dict) with _cv_fields key."""
        art = _make_synthetic_artifact()
        data, prov = art.to_profile_payload()
        assert isinstance(data, dict), "data must be a dict"
        assert isinstance(prov, dict), "prov must be a dict"
        assert "_cv_fields" in data, "data must contain _cv_fields"
        assert "source" in prov and "n" in prov and "confidence" in prov
        # _cv_fields values must all have value=None
        for slot_key, slot_dict in data["_cv_fields"].items():
            assert slot_dict.get("value") is None, (
                f"_cv_fields['{slot_key}']['value'] must be None"
            )

    def test_section_metadata(self) -> None:
        """Section must be named 'coach_tendencies' and entity 'team'."""
        assert SECTION.name == "coach_tendencies"
        assert SECTION.entity == "team"
        assert SECTION.sec_fn_name() == "sec_coach_tendencies"
        assert "team" in SECTION.parquet_name()


# ---------------------------------------------------------------------------
# Test 4: validate() accepts a well-formed artifact
# ---------------------------------------------------------------------------

class TestValidate:
    def test_validate_accepts_synthetic_artifact(self) -> None:
        """A structurally correct artifact must pass validate()."""
        art = _make_synthetic_artifact()
        assert SECTION.validate(art), "validate() should return True for a well-formed artifact"

    def test_validate_rejects_wrong_section(self) -> None:
        """An artifact with wrong section name must fail validate()."""
        art = _make_synthetic_artifact()
        art.section = "wrong_section"
        assert not SECTION.validate(art)

    def test_validate_rejects_wrong_entity(self) -> None:
        """An artifact with wrong entity must fail validate()."""
        art = _make_synthetic_artifact()
        art.entity = "player"
        assert not SECTION.validate(art)

    def test_validate_rejects_missing_sub_field(self) -> None:
        """An artifact missing a required sub_field key must fail validate()."""
        art = _make_synthetic_artifact()
        del art.sub_fields["hack_a"]
        assert not SECTION.validate(art)

    def test_validate_rejects_out_of_range_hacka_rate(self) -> None:
        """hacka_proxy_rate > 1.0 must fail validate()."""
        art = _make_synthetic_artifact()
        art.sub_fields["hack_a"]["hacka_proxy_rate"] = 1.5  # impossible rate
        assert not SECTION.validate(art)

    def test_validate_rejects_filled_cv_slot(self) -> None:
        """If a CV slot has value != None, validate() must reject (CV branch owns it)."""
        art = _make_synthetic_artifact()
        # Simulate CV branch filling a slot (should not happen at build time)
        art.cv_fields["spacing_off_bench"].value = 42.0
        assert not SECTION.validate(art)


# ---------------------------------------------------------------------------
# Test 5: build_and_register dry_run smoke test
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    def test_build_and_register_dry_run(self) -> None:
        """build_and_register with dry_run=True must return a manifest dict."""
        manifest = build_and_register(
            team_tricodes=["GSW"],
            as_of=RECENT_AS_OF,
            store=None,
            dry_run=True,
        )
        assert isinstance(manifest, dict), "manifest must be a dict"
        assert manifest.get("section") == "coach_tendencies"
        assert "cv_fields" in manifest
        assert set(manifest["cv_fields"]) == {
            "spacing_off_bench", "transition_pace_cv", "sub_pattern_frame"
        }
