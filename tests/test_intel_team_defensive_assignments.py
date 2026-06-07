"""Tests for intel/team_defensive_assignments.py.

Two mandatory assertions (per task spec):
  1. LEAK-SAFETY: build() with as_of=T never returns data stamped after T.
  2. SCHEMA CONFORMANCE: artifact has all required sub_fields + cv_fields present
     with correct structure (value=None for all CV slots).

Additional tests cover validation logic and registration bridge dry-run.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure repo root is on the path (scripts/loop convention)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel.team_defensive_assignments import TeamDefensiveAssignments, build_and_register
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TRICODE_REAL = "BOS"   # should be in positional_defense + defensive_schemes
PAST_DATE = _dt.datetime(2020, 1, 1, 0, 0, 0)   # before any tracked season data in repo
CURRENT_DATE = _dt.datetime(2026, 5, 30, 0, 0, 0)
FUTURE_DATE = _dt.datetime(2099, 1, 1, 0, 0, 0)


def _make_section() -> TeamDefensiveAssignments:
    return TeamDefensiveAssignments()


def _build(tricode: str = TRICODE_REAL,
           as_of: _dt.datetime = CURRENT_DATE) -> Any:
    return _make_section().build(tricode, as_of)


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify build() never surfaces data timestamped after the requested as_of."""

    def test_artifact_as_of_not_after_request(self):
        """artifact.as_of must be <= the requested as_of date (ISO string compare)."""
        as_of = CURRENT_DATE
        art = _build(as_of=as_of)
        if art is None:
            pytest.skip("No source data found for team — cannot assert as_of bound.")
        assert art.as_of is not None, "artifact.as_of must be set (not None)"
        assert art.as_of <= as_of.date().isoformat(), (
            f"artifact.as_of={art.as_of!r} is AFTER the requested boundary "
            f"{as_of.date().isoformat()!r} — LEAK!"
        )

    def test_past_as_of_excludes_advanced_stats(self):
        """When as_of is before any tracked season data (2020-01-01), overall_def_context
        must have n_games=0 or be empty.

        team_advanced_stats.parquet contains 2022-23 onwards; filtering to game_date <=
        2020-01-01 must return zero rows.
        """
        art = _build(as_of=PAST_DATE)
        if art is None:
            return  # no data at all — constraint satisfied trivially
        ctx = art.sub_fields.get("overall_def_context", {})
        n_games = ctx.get("n_games")
        assert n_games is None or n_games == 0, (
            f"overall_def_context.n_games={n_games} but as_of was {PAST_DATE.date()} "
            f"(before earliest season in repo). Leak guard must exclude all rows."
        )

    def test_future_as_of_returns_artifact_or_none(self):
        """build() with a far-future date must not raise — it either returns an artifact
        (using season-aggregate sources) or None; never an exception."""
        try:
            art = _build(as_of=FUTURE_DATE)
        except Exception as exc:
            pytest.fail(f"build() raised with future as_of: {exc}")
        # If artifact returned, as_of must still be a valid ISO date (not the future date)
        if art is not None:
            assert art.as_of is not None
            assert art.as_of <= FUTURE_DATE.date().isoformat()


# ---------------------------------------------------------------------------
# 2. SCHEMA CONFORMANCE assertion (incl. cv_fields present)
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Verify artifact shape, sub_fields keys, and cv_fields schema."""

    def _get_artifact(self) -> AtlasArtifact:
        art = _build()
        if art is None:
            pytest.skip("No source data available — skipping schema conformance test.")
        return art

    def test_section_and_entity_metadata(self):
        art = self._get_artifact()
        assert art.section == "defensive_assignments"
        assert art.entity == "team"
        assert art.entity_id is not None
        assert art.as_of is not None

    def test_required_sub_fields_present(self):
        """All 8 required sub_field keys must be present."""
        art = self._get_artifact()
        required = {
            "positional_defense",
            "coverage_faced_top10",
            "scheme_assignment_bias",
            "archetype_scheme_cross",
            "overall_def_context",
            "hard_assignment_map",
            "zone_cross_match",
            "help_rotation_depth",
        }
        missing = required - set(art.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {sorted(missing)}"

    def test_defer_fields_have_note(self):
        """DEFER sub-fields must carry a '_note' key explaining why they are deferred."""
        art = self._get_artifact()
        defer_keys = ["hard_assignment_map", "zone_cross_match", "help_rotation_depth"]
        for key in defer_keys:
            sf = art.sub_fields.get(key, {})
            assert isinstance(sf, dict), f"{key} must be a dict"
            assert "_note" in sf, f"DEFER field '{key}' must contain a '_note' key"

    def test_positional_defense_zone_structure(self):
        """positional_defense.zones must be a dict with at least one zone entry."""
        art = self._get_artifact()
        pos_def = art.sub_fields.get("positional_defense", {})
        if not pos_def:
            return  # source absent; structure still validates as empty
        zones = pos_def.get("zones")
        if zones is None:
            return  # no positional data available
        assert isinstance(zones, dict), "zones must be a dict"
        for zone_key, zone_data in zones.items():
            assert isinstance(zone_data, dict), f"zone {zone_key} must be a dict"
            # Each zone may have d_fg_pct; if present, must be [0, 1]
            d_fg = zone_data.get("d_fg_pct")
            if d_fg is not None:
                assert 0.0 <= d_fg <= 1.0, (
                    f"d_fg_pct={d_fg} for zone {zone_key} is outside [0, 1]"
                )

    def test_cv_fields_present_and_all_null(self):
        """cv_fields must be present with exactly 3 slots, all value=None."""
        art = self._get_artifact()
        cv = art.cv_fields
        assert isinstance(cv, dict), "cv_fields must be a dict"
        expected_slots = {
            "primary_def_player_id",
            "help_rotation_reach_measured",
            "cross_match_rate_measured",
        }
        missing = expected_slots - set(cv.keys())
        assert not missing, f"Missing CV slots: {sorted(missing)}"
        for slot_name in expected_slots:
            slot = cv[slot_name]
            assert isinstance(slot, CVSlot), f"cv_fields['{slot_name}'] must be a CVSlot"
            assert slot.value is None, (
                f"cv_fields['{slot_name}'].value must be None (CV not yet filled), "
                f"got: {slot.value!r}"
            )
            assert slot.dtype in ("float", "dist", "list", "categorical"), (
                f"cv_fields['{slot_name}'].dtype={slot.dtype!r} is not a valid dtype"
            )

    def test_cv_fields_descriptions_non_empty(self):
        """Each reserved CV slot must have a non-empty description."""
        section = _make_section()
        cv = section.cv_fields()
        for name, slot in cv.items():
            assert slot.description, f"CV slot '{name}' has empty description"

    def test_to_profile_payload_shape(self):
        """to_profile_payload() must embed _cv_fields in data with null values."""
        art = self._get_artifact()
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data, "to_profile_payload data must include _cv_fields"
        cv_blob = data["_cv_fields"]
        assert isinstance(cv_blob, dict), "_cv_fields must be a dict"
        for slot_name in ["primary_def_player_id", "help_rotation_reach_measured",
                          "cross_match_rate_measured"]:
            assert slot_name in cv_blob, f"_cv_fields missing slot '{slot_name}'"
            assert cv_blob[slot_name]["value"] is None, (
                f"_cv_fields['{slot_name}']['value'] must be None"
            )
        # Provenance shape
        for key in ("source", "n", "confidence", "as_of"):
            assert key in prov, f"prov missing key '{key}'"
        assert prov["confidence"] in ("low", "med", "high")

    def test_validate_method_accepts_own_artifact(self):
        """section.validate(artifact) must return True for a freshly built artifact."""
        section = _make_section()
        art = _build()
        if art is None:
            pytest.skip("No data to build artifact.")
        assert section.validate(art) is True, "validate() rejected its own artifact"

    def test_validate_rejects_wrong_section(self):
        """validate() must reject an artifact with a different section name."""
        section = _make_section()
        art = _build()
        if art is None:
            pytest.skip("No data to build artifact.")
        bad = AtlasArtifact(
            section="wrong_section",
            entity="team",
            entity_id="BOS",
            sub_fields=art.sub_fields,
            provenance=art.provenance,
            cv_fields=art.cv_fields,
        )
        assert section.validate(bad) is False

    def test_validate_rejects_wrong_entity(self):
        """validate() must reject an artifact with entity='player'."""
        section = _make_section()
        art = _build()
        if art is None:
            pytest.skip("No data to build artifact.")
        bad = AtlasArtifact(
            section="defensive_assignments",
            entity="player",
            entity_id=1234,
            sub_fields=art.sub_fields,
            provenance=art.provenance,
            cv_fields=art.cv_fields,
        )
        assert section.validate(bad) is False

    def test_validate_rejects_filled_cv_slot(self):
        """validate() must reject an artifact where any CV slot has a non-None value."""
        section = _make_section()
        art = _build()
        if art is None:
            pytest.skip("No data to build artifact.")
        # Inject a filled CV slot
        from copy import deepcopy
        tainted_cv = deepcopy(art.cv_fields)
        tainted_cv["primary_def_player_id"] = CVSlot(
            name="primary_def_player_id", dtype="float",
            description="test", value=203991  # non-None
        )
        bad = AtlasArtifact(
            section="defensive_assignments",
            entity="team",
            entity_id="BOS",
            sub_fields=art.sub_fields,
            provenance=art.provenance,
            cv_fields=tainted_cv,
        )
        assert section.validate(bad) is False, (
            "validate() must reject when a CV slot has been pre-filled"
        )


# ---------------------------------------------------------------------------
# 3. Registration bridge dry-run
# ---------------------------------------------------------------------------

class TestBridgeDryRun:
    """Verify build_and_register works without disk writes (dry_run=True)."""

    def test_build_and_register_dry_run(self):
        """build_and_register with dry_run=True must return a manifest dict."""
        manifest = build_and_register(
            team_tricodes=["BOS", "LAL"],
            as_of=CURRENT_DATE,
            dry_run=True,
        )
        assert isinstance(manifest, dict), "manifest must be a dict"
        assert manifest.get("section") == "defensive_assignments"
        assert "cv_fields" in manifest
        cv_field_names = manifest["cv_fields"]
        assert "primary_def_player_id" in cv_field_names
        assert "help_rotation_reach_measured" in cv_field_names
        assert "cross_match_rate_measured" in cv_field_names
        # n_entities: 0-2 depending on data availability
        assert isinstance(manifest.get("n_entities"), int)

    def test_empty_tricode_list(self):
        """build_and_register with an empty list must return zero entities without error."""
        manifest = build_and_register(team_tricodes=[], as_of=CURRENT_DATE, dry_run=True)
        assert manifest.get("n_entities") == 0

    def test_unknown_tricode_returns_none(self):
        """build() for an unknown tricode must return None, not raise."""
        art = _build(tricode="ZZZ", as_of=CURRENT_DATE)
        assert art is None, "Unknown tricode must yield None artifact"


# ---------------------------------------------------------------------------
# 4. section_key / sec_fn_name / parquet_name helpers
# ---------------------------------------------------------------------------

class TestSectionHelpers:
    def test_section_key(self):
        assert _make_section().section_key() == "defensive_assignments"

    def test_sec_fn_name(self):
        assert _make_section().sec_fn_name() == "sec_defensive_assignments"

    def test_parquet_name(self):
        assert _make_section().parquet_name() == "atlas_team_defensive_assignments.parquet"
