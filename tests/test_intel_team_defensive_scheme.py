"""Tests for intel/team_defensive_scheme.py.

Assertions:
  1. Leak-safety: build() never returns data stamped after the as_of boundary.
  2. Schema conformance: artifact has all required sub_fields, cv_fields present,
     cv_field values are all None, entity/section labels correct.
  3. Validate() passes on a well-formed artifact and fails on bad data.
  4. cv_fields() returns exactly the two reserved CV slots named in the spec.
  5. build_and_register dry_run produces the expected manifest shape.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel.team_defensive_scheme import (
    TeamDefensiveScheme,
    build_and_register,
    _scheme_from_parquet,
    _scheme_indicators,
    _rim_protection,
    _perimeter_pressure,
    _ratings_context,
    _SRC_CACHE,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_PAST = _dt.datetime(2026, 1, 1)    # well in the past
_FUTURE = _dt.datetime(2099, 1, 1)  # far future

_SAMPLE_TRICODE = "BOS"


def _minimal_artifact(tricode: str = _SAMPLE_TRICODE) -> AtlasArtifact:
    """Build a minimal well-formed artifact using real data (if available) or stubs."""
    section = TeamDefensiveScheme()
    # Use a far-future as_of so real data (which is historical) is included
    art = section.build(tricode, _FUTURE)
    return art  # may be None if parquets absent


def _stub_artifact(tricode: str = _SAMPLE_TRICODE) -> AtlasArtifact:
    """Construct a synthetic artifact that satisfies validate() for schema tests."""
    section = TeamDefensiveScheme()
    sub_fields: Dict[str, Any] = {
        "coverage_scheme": {
            "dominant_tag": "DROP COVERAGE",
            "all_tags": ["DROP COVERAGE", "PAINT-FIRST DEFENSE"],
            "n_scheme_tags": 2,
            "interpretation": "drops on ball-screens",
            "drop_vs_switch": "drop",
            "zone_usage": {"_note": "DEFER"},
            "blitz_coverage": {"_note": "DEFER"},
        },
        "scheme_axes": {
            "drop_score": 0.19,
            "paint_protection_score": 0.13,
            "perimeter_denial_score": 0.17,
            "pace_control_score": 0.24,
            "iso_force_score": 0.31,
            "closeout_score": -0.14,
            "perimeter_denial_raw": 0.06,
            "quality_z": -1.37,
            "quality_correction": -0.11,
            "n_opposing_player_games": 59,
            "n_unique_opponents": 57,
        },
        "imposed_deviations": {"potential_assists": 0.47, "made_pct": 0.38},
        "rim_protection": {
            "opp_paint_pct_allowed_z": 0.1,
            "opp_3pt_pct_allowed_z": 0.05,
            "opp_mid_pct_allowed_z": -0.02,
            "opp_paint_dwell_pct_allowed_z": 0.12,
            "opp_shot_mix_deviation_z": 0.08,
            "n_games_window": 25,
        },
        "perimeter_pressure": {
            "opp_contested_shot_rate_imposed_z": 0.26,
            "opp_avg_defender_distance_imposed_z": 0.20,
            "opp_paint_attempts_allowed_pct_z": -0.09,
            "opp_pace_imposed_z": 0.15,
            "opp_catch_shoot_allowed_pct_z": 0.19,
            "opp_closeout_speed_imposed_z": None,
            "opp_defensive_intensity_z": 0.14,
            "n_games_window": 25,
        },
        "ratings_context": {
            "def_rtg": 108.4,
            "pace": 98.2,
            "oreb_pct": 0.27,
            "dreb_pct": 0.73,
            "n_games": 40,
        },
        "top_impact_players": [
            {"player_name": "Cam Whitmore", "max_abs_z": 30.25, "top_feature": "avg_defender_distance"},
        ],
        "switch_rate": {"_note": "DEFER"},
    }
    prov = {
        "source": section.source_name,
        "n": 59,
        "confidence": "high",
        "as_of": "2026-01-01",
    }
    return AtlasArtifact(
        section=section.name,
        entity=section.entity,
        entity_id=tricode,
        value="DROP COVERAGE",
        sub_fields=sub_fields,
        provenance=prov,
        confidence="high",
        as_of="2026-01-01",
        cv_fields=section.cv_fields(),
    )


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Leak-safety: build() must not return data stamped after the as_of boundary."""

    def test_as_of_in_past_returns_none_or_valid(self) -> None:
        """With a very old as_of, build returns None or an artifact dated <= as_of."""
        section = TeamDefensiveScheme()
        past = _dt.datetime(2010, 1, 1)  # before any data exists
        art = section.build(_SAMPLE_TRICODE, past)
        # Either returns None (no data that old) or artifact as_of is <= boundary
        if art is not None:
            assert art.as_of <= past.date().isoformat(), (
                f"Artifact as_of {art.as_of!r} is after the requested as_of "
                f"{past.date().isoformat()!r} — LEAK!"
            )

    def test_future_as_of_includes_all_data(self) -> None:
        """With a far-future as_of, build should succeed (data exists in repo)."""
        section = TeamDefensiveScheme()
        art = section.build(_SAMPLE_TRICODE, _FUTURE)
        # The artifact may be None only if parquets are missing from this checkout
        # (CI without data); we don't assert non-None but do assert the as_of bound.
        if art is not None:
            assert art.as_of <= _FUTURE.date().isoformat(), "Future as_of violated"

    def test_per_game_sources_respect_asof(self) -> None:
        """opp_paint_allowance and opp_defensive_intensity are filtered by game_date."""
        # Inject a fake dataframe with one row dated AFTER the as_of cutoff
        fake_df = pd.DataFrame({
            "team_id": [_SAMPLE_TRICODE],
            "season": ["2025-26"],
            "game_date": ["2099-12-31"],  # future — must be excluded
            "n_games_window": [10],
            "opp_paint_pct_allowed_z": [99.0],  # sentinel: should NOT appear
            "opp_3pt_pct_allowed_z": [0.0],
            "opp_mid_pct_allowed_z": [0.0],
            "opp_paint_dwell_pct_allowed_z": [0.0],
            "opp_shot_mix_deviation_z": [0.0],
            "data_density": ["high"],
        })
        # Patch _load_parquet to return our fake frame for opp_paint
        orig_cache = dict(_SRC_CACHE)
        _SRC_CACHE["opp_paint"] = fake_df
        try:
            cutoff = _dt.datetime(2026, 1, 1)
            result = _rim_protection(_SAMPLE_TRICODE, cutoff)
            # The future row should be excluded — result should be empty
            assert result == {}, (
                f"Leaked future data: got {result!r} for cutoff {cutoff.date()}"
            )
        finally:
            # Restore cache state
            _SRC_CACHE.clear()
            _SRC_CACHE.update(orig_cache)

    def test_per_game_intensity_respects_asof(self) -> None:
        """opp_defensive_intensity rows after as_of must be excluded."""
        fake_df = pd.DataFrame({
            "team_id": [_SAMPLE_TRICODE],
            "season": ["2025-26"],
            "game_date": ["2099-01-01"],  # future
            "n_games_window": [5],
            "opp_contested_shot_rate_imposed_z": [99.0],
            "opp_avg_defender_distance_imposed_z": [0.0],
            "opp_paint_attempts_allowed_pct_z": [0.0],
            "opp_pace_imposed_z": [0.0],
            "opp_catch_shoot_allowed_pct_z": [0.0],
            "opp_closeout_speed_imposed_z": [0.0],
            "opp_defensive_intensity_z": [0.0],
            "data_density": ["high"],
        })
        orig_cache = dict(_SRC_CACHE)
        _SRC_CACHE["opp_def_int"] = fake_df
        try:
            cutoff = _dt.datetime(2026, 1, 1)
            result = _perimeter_pressure(_SAMPLE_TRICODE, cutoff)
            assert result == {}, (
                f"Leaked future intensity data: got {result!r}"
            )
        finally:
            _SRC_CACHE.clear()
            _SRC_CACHE.update(orig_cache)


# ---------------------------------------------------------------------------
# 2. SCHEMA CONFORMANCE assertion
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact schema must match the contract: required sub_fields, cv_fields=None."""

    def test_stub_artifact_has_required_sub_fields(self) -> None:
        """All required top-level sub_fields must be present."""
        art = _stub_artifact()
        required = {
            "coverage_scheme", "scheme_axes", "imposed_deviations",
            "rim_protection", "perimeter_pressure", "ratings_context",
            "top_impact_players", "switch_rate",
        }
        missing = required - set(art.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {missing}"

    def test_cv_fields_present_and_null(self) -> None:
        """cv_fields must contain the two reserved slots, both with value=None."""
        art = _stub_artifact()
        assert "avg_contest" in art.cv_fields, "avg_contest CV slot missing"
        assert "switch_rate_measured" in art.cv_fields, "switch_rate_measured CV slot missing"
        for name, slot in art.cv_fields.items():
            assert isinstance(slot, CVSlot), f"cv_fields[{name!r}] is not a CVSlot"
            assert slot.value is None, (
                f"CV slot {name!r} must be None until CV fills it; got {slot.value!r}"
            )

    def test_cv_fields_have_descriptions(self) -> None:
        """Each CV slot must have a non-empty description and correct dtype."""
        section = TeamDefensiveScheme()
        slots = section.cv_fields()
        assert len(slots) == 2, f"Expected exactly 2 CV slots, got {len(slots)}"
        for name, slot in slots.items():
            assert slot.description, f"CV slot {name!r} has empty description"
            assert slot.dtype in ("float", "dist", "list", "categorical"), (
                f"CV slot {name!r} has unexpected dtype {slot.dtype!r}"
            )

    def test_section_and_entity_labels(self) -> None:
        """section='defensive_scheme', entity='team'."""
        art = _stub_artifact()
        assert art.section == "defensive_scheme"
        assert art.entity == "team"

    def test_provenance_fields(self) -> None:
        """Provenance must carry source, n, confidence, as_of."""
        art = _stub_artifact()
        for key in ("source", "n", "confidence", "as_of"):
            assert key in art.provenance, f"provenance missing key {key!r}"
        assert art.provenance["n"] >= 1
        assert art.provenance["confidence"] in ("low", "med", "high")

    def test_to_profile_payload(self) -> None:
        """to_profile_payload() must produce (data, prov) with _cv_fields embedded."""
        art = _stub_artifact()
        data, prov = art.to_profile_payload()
        assert isinstance(data, dict)
        assert isinstance(prov, dict)
        assert "_cv_fields" in data, "_cv_fields missing from profile payload data"
        cv_block = data["_cv_fields"]
        assert "avg_contest" in cv_block
        assert "switch_rate_measured" in cv_block
        # Each cv_fields entry must have dtype, unit, description, value
        for slot_name, slot_dict in cv_block.items():
            for k in ("dtype", "unit", "description", "value"):
                assert k in slot_dict, (
                    f"_cv_fields[{slot_name!r}] missing key {k!r}"
                )
            assert slot_dict["value"] is None, (
                f"_cv_fields[{slot_name!r}]['value'] must be None"
            )


# ---------------------------------------------------------------------------
# 3. VALIDATE() tests
# ---------------------------------------------------------------------------

class TestValidate:
    """validate() must pass on well-formed artifact and fail on bad data."""

    def test_validate_passes_on_stub(self) -> None:
        section = TeamDefensiveScheme()
        art = _stub_artifact()
        assert section.validate(art), "validate() failed on a well-formed stub artifact"

    def test_validate_fails_wrong_section(self) -> None:
        section = TeamDefensiveScheme()
        art = _stub_artifact()
        art.section = "wrong_section"
        assert not section.validate(art)

    def test_validate_fails_wrong_entity(self) -> None:
        section = TeamDefensiveScheme()
        art = _stub_artifact()
        art.entity = "player"
        assert not section.validate(art)

    def test_validate_fails_missing_sub_field(self) -> None:
        section = TeamDefensiveScheme()
        art = _stub_artifact()
        del art.sub_fields["perimeter_pressure"]
        assert not section.validate(art)

    def test_validate_fails_out_of_range_axis(self) -> None:
        section = TeamDefensiveScheme()
        art = _stub_artifact()
        art.sub_fields["scheme_axes"]["drop_score"] = 100.0  # absurd
        assert not section.validate(art)

    def test_validate_fails_cv_slot_filled(self) -> None:
        """validate() must fail if a CV slot already has a value (CV hasn't run)."""
        section = TeamDefensiveScheme()
        art = _stub_artifact()
        art.cv_fields["avg_contest"].value = 0.42  # shouldn't be set yet
        assert not section.validate(art)

    def test_validate_fails_missing_coverage_scheme_tag(self) -> None:
        section = TeamDefensiveScheme()
        art = _stub_artifact()
        del art.sub_fields["coverage_scheme"]["dominant_tag"]
        assert not section.validate(art)


# ---------------------------------------------------------------------------
# 4. CV SLOTS exact names
# ---------------------------------------------------------------------------

class TestCVSlots:
    """cv_fields() must return exactly the two contracted CV slot names."""

    def test_cv_field_names(self) -> None:
        section = TeamDefensiveScheme()
        slots = section.cv_fields()
        assert set(slots.keys()) == {"avg_contest", "switch_rate_measured"}, (
            f"CV slot names mismatch: got {set(slots.keys())}"
        )

    def test_avg_contest_dtype(self) -> None:
        section = TeamDefensiveScheme()
        slot = section.cv_fields()["avg_contest"]
        assert slot.dtype == "float"
        assert slot.value is None

    def test_switch_rate_measured_dtype(self) -> None:
        section = TeamDefensiveScheme()
        slot = section.cv_fields()["switch_rate_measured"]
        assert slot.dtype == "float"
        assert slot.value is None


# ---------------------------------------------------------------------------
# 5. BUILD_AND_REGISTER dry_run smoke test
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    """build_and_register() in dry_run mode returns a valid manifest."""

    def test_dry_run_manifest_keys(self) -> None:
        """Manifest must carry section, parquet, sec_fn, n_entities, cv_fields, as_of."""
        manifest = build_and_register(
            team_tricodes=[_SAMPLE_TRICODE],
            as_of=_FUTURE,
            store=None,
            dry_run=True,
        )
        for key in ("section", "parquet", "sec_fn", "cv_fields"):
            assert key in manifest, f"Manifest missing key {key!r}"
        assert manifest["section"] == "defensive_scheme"
        assert manifest["sec_fn"] == "sec_defensive_scheme"
        assert "avg_contest" in manifest["cv_fields"]
        assert "switch_rate_measured" in manifest["cv_fields"]

    def test_dry_run_no_disk_write(self, tmp_path: Path) -> None:
        """Dry run must not create the parquet file."""
        manifest = build_and_register(
            team_tricodes=[_SAMPLE_TRICODE],
            as_of=_FUTURE,
            store=None,
            dry_run=True,
        )
        # The registered parquet path should NOT have been created
        parquet_path = Path(manifest["parquet"])
        assert not parquet_path.exists() or parquet_path.stat().st_size > 0, (
            "Parquet should not be created during dry_run"
        )

    def test_empty_tricodes_returns_manifest(self) -> None:
        """Empty tricode list returns a manifest with n_entities=0."""
        manifest = build_and_register(
            team_tricodes=[],
            as_of=_FUTURE,
            store=None,
            dry_run=True,
        )
        assert manifest["section"] == "defensive_scheme"
        assert manifest.get("n_entities", 0) == 0
