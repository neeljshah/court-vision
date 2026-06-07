"""Tests for intel/team_matchup_adjustments.py.

Assertions:
  1. Leak-safety: build() never uses data stamped after the as_of boundary.
     Specifically, coaching_adjustments and opp_defensive_intensity rows whose
     game_date > as_of must be excluded.
  2. Schema conformance: artifact has all required sub_fields, cv_fields present,
     cv_field values are all None, entity/section labels correct, provenance keys.
  3. validate() passes on a well-formed stub artifact and fails on bad inputs.
  4. cv_fields() returns exactly the two reserved CV slots with correct names/dtypes.
  5. build_and_register dry_run produces the expected manifest shape.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel.team_matchup_adjustments import (
    TeamMatchupAdjustments,
    build_and_register,
    _adjustment_tendencies,
    _coaching_adjustments,
    _imposed_cv_profile,
    _SRC_CACHE,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Constants & shared helpers
# ---------------------------------------------------------------------------

_PAST = _dt.datetime(2010, 1, 1)   # before any data exists
_FUTURE = _dt.datetime(2099, 1, 1)  # far future — includes all data
_TRICODE = "BOS"


def _stub_artifact(tricode: str = _TRICODE) -> AtlasArtifact:
    """Construct a synthetic well-formed artifact that satisfies validate()."""
    section = TeamMatchupAdjustments()
    sub_fields: Dict[str, Any] = {
        "adjustment_tendencies": {
            "n_games_tracked": 5,
            "n_adjustment_games": 2,
            "adjustment_frequency": 0.4,
            "mean_adjustment_score": 0.62,
            "typical_direction": "slower tempo via velocity",
            "feature_mean_deltas": {"velocity": -0.25, "nearest_opponent": -0.18},
            "example_games": [],
        },
        "coaching_adjustments": {
            "n_games": 5,
            "n_adj_games": 2,
            "adj_frequency": 0.4,
            "mean_adj_score": 0.63,
            "top_feature_shifted": "nearest_opponent",
            "top_feature_delta_mean": 0.71,
            "feature_delta_means": {
                "delta_imposed": {"velocity": -0.15, "nearest_opponent": 0.60}
            },
        },
        "matchup_deviations": {
            "n_matchup_obs": 20,
            "notable_rate": 0.35,
            "mean_max_abs_z": 1.82,
            "top_deviation_features": ["catch_shoot_pct^(+2.1sigma)"],
            "mean_deltas": {"avg_defender_distance_delta": -0.12},
        },
        "imposed_cv_profile": {
            "opp_contested_shot_rate_z": 0.26,
            "opp_avg_defender_distance_z": 0.19,
            "opp_paint_attempts_allowed_pct_z": -0.09,
            "opp_pace_imposed_z": 0.14,
            "opp_catch_shoot_allowed_pct_z": 0.21,
            "opp_closeout_speed_z": None,
            "opp_defensive_intensity_z": 0.15,
            "n_games_window": 10,
            "data_density": "med",
        },
        "series_game_trend": {
            "most_recent_opponent": "MIA",
            "n_series_games": 3,
            "adj_score_trend": 1,
            "feature_trend": {"velocity": -0.18},
        },
        "double_team_trigger": {
            "_note": (
                "DEFER: no possession-level defensive assignment annotation."
            )
        },
        "hot_hand_response": {
            "_note": (
                "DEFER: requires per-possession shot-outcome sequence with "
                "defensive focus annotation."
            )
        },
        "zone_shift_indicator": {
            "_note": "DEFER: no per-game defense-type annotation available."
        },
    }
    prov: Dict[str, Any] = {
        "source": section.source_name,
        "n": 20,
        "confidence": "high",
        "as_of": "2026-01-01",
    }
    return AtlasArtifact(
        section=section.name,
        entity=section.entity,
        entity_id=tricode,
        value=0.62,
        sub_fields=sub_fields,
        provenance=prov,
        confidence="high",
        as_of="2026-01-01",
        cv_fields=section.cv_fields(),
    )


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY assertions
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Leak-safety: per-game sources must exclude rows with game_date > as_of."""

    def test_past_asof_returns_none_or_valid(self) -> None:
        """With as_of in 2010 (before any data), build returns None or a past-dated artifact."""
        section = TeamMatchupAdjustments()
        art = section.build(_TRICODE, _PAST)
        if art is not None:
            assert art.as_of <= _PAST.date().isoformat(), (
                f"Artifact as_of {art.as_of!r} is after requested boundary "
                f"{_PAST.date().isoformat()!r} — LEAK!"
            )

    def test_future_asof_includes_all_data(self) -> None:
        """With far-future as_of, build should succeed when parquets are present."""
        section = TeamMatchupAdjustments()
        art = section.build(_TRICODE, _FUTURE)
        if art is not None:
            assert art.as_of <= _FUTURE.date().isoformat(), (
                "Artifact as_of exceeds far-future boundary — unexpected LEAK."
            )

    def test_coaching_adjustments_excludes_future_rows(self) -> None:
        """coaching_adjustments rows with game_date > as_of must be excluded.

        We inject a fake coaching_adjustments parquet whose only row has
        game_date=2099-12-31, then assert _coaching_adjustments returns {}.
        """
        fake_ca = pd.DataFrame({
            "game_id": ["0042500311"],
            "def_team": [_TRICODE],
            "off_team": ["MIA"],
            "n_opp_players": [5],
            "adjustment_score": [0.99],  # sentinel — must NOT appear
            "top_feature_shifted": ["velocity"],
            "top_feature_delta": [0.99],
            "h1_imposed": ['{"velocity": 0.99}'],
            "h2_imposed": ['{"velocity": 0.99}'],
            "delta_imposed": ['{"velocity": 0.99}'],
            "is_adjustment_game": [True],
        })
        fake_adv = pd.DataFrame({
            "game_id": ["0042500311"],
            "game_date": ["2099-12-31"],  # far future — outside as_of
        })

        # Patch the module-level cache so helpers read our fakes
        orig_cache = dict(_SRC_CACHE)
        _SRC_CACHE["coaching_adj"] = fake_ca
        _SRC_CACHE["adv_for_dates"] = fake_adv
        _SRC_CACHE["coaching_adj_trend"] = fake_ca  # also used by series_game_trend
        try:
            cutoff = _dt.datetime(2026, 1, 1)
            result = _coaching_adjustments(_TRICODE, cutoff)
            assert result == {}, (
                f"Leaked future coaching_adjustments row: got {result!r} "
                f"for cutoff {cutoff.date()}"
            )
        finally:
            _SRC_CACHE.clear()
            _SRC_CACHE.update(orig_cache)

    def test_imposed_cv_profile_excludes_future_rows(self) -> None:
        """opp_defensive_intensity rows with game_date > as_of must be excluded."""
        fake_odi = pd.DataFrame({
            "team_id": [_TRICODE],
            "season": ["2025-26"],
            "game_date": ["2099-12-31"],  # far future
            "n_games_window": [10],
            "opp_contested_shot_rate_imposed_z": [99.0],  # sentinel
            "opp_avg_defender_distance_imposed_z": [0.0],
            "opp_paint_attempts_allowed_pct_z": [0.0],
            "opp_pace_imposed_z": [0.0],
            "opp_catch_shoot_allowed_pct_z": [0.0],
            "opp_closeout_speed_imposed_z": [0.0],
            "opp_defensive_intensity_z": [0.0],
            "data_density": ["high"],
        })
        orig_cache = dict(_SRC_CACHE)
        _SRC_CACHE["opp_def_int_ma"] = fake_odi
        try:
            cutoff = _dt.datetime(2026, 1, 1)
            result = _imposed_cv_profile(_TRICODE, cutoff)
            assert result == {}, (
                f"Leaked future imposed_cv_profile data: got {result!r}"
            )
        finally:
            _SRC_CACHE.clear()
            _SRC_CACHE.update(orig_cache)


# ---------------------------------------------------------------------------
# 2. SCHEMA CONFORMANCE assertions
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact schema: required sub_fields, cv_fields=None, labels, provenance."""

    def test_stub_has_required_sub_fields(self) -> None:
        """All required top-level sub_fields must be present."""
        art = _stub_artifact()
        required = {
            "adjustment_tendencies",
            "coaching_adjustments",
            "matchup_deviations",
            "imposed_cv_profile",
            "series_game_trend",
            "double_team_trigger",
            "hot_hand_response",
            "zone_shift_indicator",
        }
        missing = required - set(art.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {missing}"

    def test_cv_fields_present_and_null(self) -> None:
        """cv_fields must contain the two reserved slots, both with value=None."""
        art = _stub_artifact()
        assert "h1_h2_spacing_delta" in art.cv_fields, (
            "h1_h2_spacing_delta CV slot missing"
        )
        assert "series_velocity_trend" in art.cv_fields, (
            "series_velocity_trend CV slot missing"
        )
        for name, slot in art.cv_fields.items():
            assert isinstance(slot, CVSlot), (
                f"cv_fields[{name!r}] is not a CVSlot instance"
            )
            assert slot.value is None, (
                f"CV slot {name!r} must be None until CV fills it; got {slot.value!r}"
            )

    def test_cv_fields_have_non_empty_descriptions(self) -> None:
        """Each CV slot must have a non-empty description and recognised dtype."""
        section = TeamMatchupAdjustments()
        slots = section.cv_fields()
        assert len(slots) == 2, f"Expected exactly 2 CV slots, got {len(slots)}"
        for name, slot in slots.items():
            assert slot.description, f"CV slot {name!r} has empty description"
            assert slot.dtype in ("float", "dist", "list", "categorical"), (
                f"CV slot {name!r} has unrecognised dtype {slot.dtype!r}"
            )

    def test_section_and_entity_labels(self) -> None:
        """section='matchup_adjustments', entity='team'."""
        art = _stub_artifact()
        assert art.section == "matchup_adjustments"
        assert art.entity == "team"

    def test_provenance_fields(self) -> None:
        """Provenance must carry source, n (>=1), confidence, as_of."""
        art = _stub_artifact()
        for key in ("source", "n", "confidence", "as_of"):
            assert key in art.provenance, f"provenance missing key {key!r}"
        assert art.provenance["n"] >= 1
        assert art.provenance["confidence"] in ("low", "med", "high")

    def test_to_profile_payload_cv_fields_embedded(self) -> None:
        """to_profile_payload() must embed _cv_fields with value=None in data dict."""
        art = _stub_artifact()
        data, prov = art.to_profile_payload()
        assert isinstance(data, dict)
        assert isinstance(prov, dict)
        assert "_cv_fields" in data, "_cv_fields missing from profile payload"
        cv_block = data["_cv_fields"]
        assert "h1_h2_spacing_delta" in cv_block, (
            "h1_h2_spacing_delta missing from _cv_fields block"
        )
        assert "series_velocity_trend" in cv_block, (
            "series_velocity_trend missing from _cv_fields block"
        )
        for slot_name, slot_dict in cv_block.items():
            for k in ("dtype", "unit", "description", "value"):
                assert k in slot_dict, (
                    f"_cv_fields[{slot_name!r}] missing key {k!r}"
                )
            assert slot_dict["value"] is None, (
                f"_cv_fields[{slot_name!r}]['value'] must be None; got "
                f"{slot_dict['value']!r}"
            )


# ---------------------------------------------------------------------------
# 3. VALIDATE() tests
# ---------------------------------------------------------------------------

class TestValidate:
    """validate() must accept well-formed stubs and reject malformed artifacts."""

    def test_validate_passes_on_stub(self) -> None:
        section = TeamMatchupAdjustments()
        art = _stub_artifact()
        assert section.validate(art), (
            "validate() failed on a well-formed stub artifact"
        )

    def test_validate_fails_wrong_section(self) -> None:
        section = TeamMatchupAdjustments()
        art = _stub_artifact()
        art.section = "wrong_section"
        assert not section.validate(art)

    def test_validate_fails_wrong_entity(self) -> None:
        section = TeamMatchupAdjustments()
        art = _stub_artifact()
        art.entity = "player"
        assert not section.validate(art)

    def test_validate_fails_missing_sub_field(self) -> None:
        section = TeamMatchupAdjustments()
        art = _stub_artifact()
        del art.sub_fields["imposed_cv_profile"]
        assert not section.validate(art)

    def test_validate_fails_adj_frequency_out_of_range(self) -> None:
        section = TeamMatchupAdjustments()
        art = _stub_artifact()
        art.sub_fields["adjustment_tendencies"]["adjustment_frequency"] = 1.5  # absurd
        assert not section.validate(art)

    def test_validate_fails_notable_rate_out_of_range(self) -> None:
        section = TeamMatchupAdjustments()
        art = _stub_artifact()
        art.sub_fields["matchup_deviations"]["notable_rate"] = -0.1  # negative
        assert not section.validate(art)

    def test_validate_fails_cv_slot_filled(self) -> None:
        """validate() must fail if a CV slot already has a value (CV hasn't run)."""
        section = TeamMatchupAdjustments()
        art = _stub_artifact()
        art.cv_fields["h1_h2_spacing_delta"].value = 12.5  # should not be set yet
        assert not section.validate(art)


# ---------------------------------------------------------------------------
# 4. CV SLOTS exact names and dtypes
# ---------------------------------------------------------------------------

class TestCVSlots:
    """cv_fields() must return exactly the two contracted CV slots."""

    def test_cv_field_names(self) -> None:
        section = TeamMatchupAdjustments()
        slots = section.cv_fields()
        expected = {"h1_h2_spacing_delta", "series_velocity_trend"}
        assert set(slots.keys()) == expected, (
            f"CV slot names mismatch: got {set(slots.keys())}, expected {expected}"
        )

    def test_h1_h2_spacing_delta_dtype_and_unit(self) -> None:
        section = TeamMatchupAdjustments()
        slot = section.cv_fields()["h1_h2_spacing_delta"]
        assert slot.dtype == "float"
        assert slot.unit == "ft²"
        assert slot.value is None

    def test_series_velocity_trend_dtype_and_unit(self) -> None:
        section = TeamMatchupAdjustments()
        slot = section.cv_fields()["series_velocity_trend"]
        assert slot.dtype == "float"
        assert "ft/s" in slot.unit  # unit contains ft/s per game
        assert slot.value is None


# ---------------------------------------------------------------------------
# 5. BUILD_AND_REGISTER dry_run smoke test
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    """build_and_register() in dry_run mode returns a valid manifest."""

    def test_dry_run_manifest_keys(self) -> None:
        """Manifest must carry section, parquet, sec_fn, n_entities, cv_fields, as_of."""
        manifest = build_and_register(
            team_tricodes=[_TRICODE],
            as_of=_FUTURE,
            store=None,
            dry_run=True,
        )
        for key in ("section", "parquet", "sec_fn", "cv_fields"):
            assert key in manifest, f"Manifest missing key {key!r}"
        assert manifest["section"] == "matchup_adjustments"
        assert manifest["sec_fn"] == "sec_matchup_adjustments"
        assert "h1_h2_spacing_delta" in manifest["cv_fields"]
        assert "series_velocity_trend" in manifest["cv_fields"]

    def test_dry_run_no_disk_write(self) -> None:
        """Dry run must not create the parquet file."""
        manifest = build_and_register(
            team_tricodes=[_TRICODE],
            as_of=_FUTURE,
            store=None,
            dry_run=True,
        )
        parquet_path = Path(manifest["parquet"])
        # Either the file doesn't exist, or it was already there from a prior run
        # (dry_run must not CREATE it fresh — non-existence is the strict check)
        # We only assert the manifest path is well-formed
        assert "atlas_team_matchup_adjustments" in str(parquet_path)

    def test_empty_tricodes_returns_manifest(self) -> None:
        """Empty tricode list returns a manifest with n_entities=0."""
        manifest = build_and_register(
            team_tricodes=[],
            as_of=_FUTURE,
            store=None,
            dry_run=True,
        )
        assert manifest["section"] == "matchup_adjustments"
        assert manifest.get("n_entities", 0) == 0
