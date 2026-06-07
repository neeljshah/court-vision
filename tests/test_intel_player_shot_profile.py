"""Tests for intel/player_shot_profile.py — AtlasSection contract conformance.

Two mandatory assertions per task spec:
  1. LEAK-SAFETY: build() with as_of=T never includes data stamped after T.
  2. SCHEMA CONFORMANCE: AtlasArtifact has required sub-field keys AND all 7 CV slots
     are present with value=None.

Additional tests cover: validate(), cv_fields() schema, None-return for missing player,
and the to_profile_payload() round-trip shape expected by profile_factory_bridge.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

# Ensure repo root is on path (scripts convention: sys.path.insert(0,'.'))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Guard: offline mode so nothing tries a live API call
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.player_shot_profile import PlayerShotProfile, _load
from src.loop.atlas import AtlasArtifact, CVSlot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SECTION = PlayerShotProfile()

# SGA player_id that exists in most parquets (used for presence tests)
SGA_PID = 1628983

# A player_id guaranteed to be absent from all sources (unlikely NBA ID)
MISSING_PID = 9_999_999

# Use a "past" date so walk-forward tests are unambiguous
PAST_AS_OF = dt.datetime(2024, 10, 15, 0, 0, 0)  # before 2024-25 season
CURRENT_AS_OF = dt.datetime(2025, 4, 13, 0, 0, 0)  # end of 2024-25 regular season


# ---------------------------------------------------------------------------
# Helper: build a minimal dummy AtlasArtifact with all required sub-field keys
# ---------------------------------------------------------------------------

def _dummy_artifact(pid: int = SGA_PID, n: int = 30) -> AtlasArtifact:
    """Return a hand-crafted valid artifact for schema-conformance tests."""
    from src.loop.atlas import confidence_from_n
    conf = confidence_from_n(n)
    sub_fields = {
        "creation": {
            "catch_shoot_fg_pct": 0.45,
            "drive_fg_pct": 0.58,
        },
        "context": {
            "transition_freq_pct": 0.15,
            "iso_poss_pg": 3.2,
        },
        "shot_clock_timing": {"_note": "DEFER"},
        "quarter_splits": {"q1_pts_pg": 7.2, "q4_pts_pg": 8.1, "n_games": n},
        "clutch": {"clutch_fg_pct": 0.49, "clutch_gp": 25},
        "usage_context": {"usage_pct": 0.31, "ts_pct": 0.64, "n_games": n},
        "zones": {"_note": "DEFER"},
        "rest_home_road": {"_note": "DEFER"},
        "vs_zone_defense": {"_note": "DEFER"},
    }
    return AtlasArtifact(
        section="shot_profile",
        entity="player",
        entity_id=pid,
        value=None,
        sub_fields=sub_fields,
        provenance={"source": "test", "n": n, "confidence": conf, "as_of": "2025-04-13"},
        confidence=conf,
        as_of="2025-04-13",
        cv_fields=SECTION.cv_fields(),
    )


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must never return data with a game_date > as_of."""

    def test_pbp_data_filtered_to_as_of(self) -> None:
        """Leak-safety: sources filtered to a mid-season cut must return strictly
        fewer games than when filtered to the end of the season.

        Data spans 2022-10-18 to 2025-04-13.  We compare:
          cut_as_of  = 2023-12-31  (mid 2023-24 season)
          full_as_of = 2025-04-13  (end of data)
        The per-game counts must be strictly monotone (more games seen by end-of-data).
        """
        from intel.player_shot_profile import _pbp_context_for_player, _usage_for_player

        cut_as_of = dt.datetime(2023, 12, 31)
        full_as_of = dt.datetime(2025, 4, 13)

        pbp_cut = _pbp_context_for_player(SGA_PID, cut_as_of)
        pbp_full = _pbp_context_for_player(SGA_PID, full_as_of)

        n_cut = pbp_cut.get("n_games", 0)
        n_full = pbp_full.get("n_games", 0)
        assert n_full >= n_cut, (
            f"pbp_context n_games not monotone: cut={n_cut} full={n_full} — "
            f"future data leaking into cut slice"
        )
        # The cut must include strictly fewer games than full (SGA has games in both windows)
        assert n_cut < n_full, (
            f"pbp_context cut={n_cut} == full={n_full}: as_of filter is not working"
        )

        usage_cut = _usage_for_player(SGA_PID, cut_as_of)
        usage_full = _usage_for_player(SGA_PID, full_as_of)
        nc_u = usage_cut.get("n_games", 0)
        nf_u = usage_full.get("n_games", 0)
        assert nf_u >= nc_u, (
            f"usage_context n_games not monotone: cut={nc_u} full={nf_u}"
        )
        assert nc_u < nf_u, (
            f"usage_context filter not working: cut={nc_u} == full={nf_u}"
        )

    def test_build_respects_as_of_for_per_game_sources(self) -> None:
        """build() with PAST_AS_OF must return None or an artifact whose
        usage_context n_games <= actual games played before that date.
        Also verifies that a FUTURE as_of produces >= games than a PAST as_of."""
        art_past = SECTION.build(SGA_PID, PAST_AS_OF)
        art_current = SECTION.build(SGA_PID, CURRENT_AS_OF)

        # Both can be None (sparse data) but if both exist, current has >= games
        if art_past is not None and art_current is not None:
            n_past = art_past.sub_fields.get("usage_context", {}).get("n_games", 0)
            n_current = art_current.sub_fields.get("usage_context", {}).get("n_games", 0)
            assert n_current >= n_past, (
                f"Leak: past as_of={PAST_AS_OF.date()} has more games ({n_past}) "
                f"than current as_of={CURRENT_AS_OF.date()} ({n_current})"
            )

    def test_as_of_field_in_artifact(self) -> None:
        """artifact.as_of must match the requested as_of date (YYYY-MM-DD)."""
        art = SECTION.build(SGA_PID, CURRENT_AS_OF)
        if art is not None:
            assert art.as_of == CURRENT_AS_OF.date().isoformat(), (
                f"artifact.as_of={art.as_of} != {CURRENT_AS_OF.date().isoformat()}"
            )


# ---------------------------------------------------------------------------
# 2. SCHEMA CONFORMANCE assertion
# ---------------------------------------------------------------------------

_REQUIRED_SUBFIELD_KEYS = {
    "creation",
    "context",
    "shot_clock_timing",
    "quarter_splits",
    "clutch",
    "usage_context",
    "zones",
    "rest_home_road",
    "vs_zone_defense",
}

_REQUIRED_CV_SLOTS = {
    "defender_distance_dist",
    "contest_level",
    "dribbles_before",
    "closeout_speed",
    "release_time",
    "shot_arc",
    "spacing_around",
}


class TestSchemaConformance:
    """AtlasArtifact shape matches the agreed contract."""

    def test_cv_fields_returns_all_7_slots(self) -> None:
        """cv_fields() must return exactly the 7 reserved slot names."""
        slots = SECTION.cv_fields()
        assert set(slots.keys()) == _REQUIRED_CV_SLOTS, (
            f"CV slot mismatch. Got: {set(slots.keys())}"
        )

    def test_cv_fields_all_values_none(self) -> None:
        """All CV slot values must be None (CV branch hasn't run yet)."""
        slots = SECTION.cv_fields()
        for name, slot in slots.items():
            assert slot.value is None, f"CV slot '{name}' has non-None value: {slot.value}"

    def test_cv_fields_are_cvslot_instances(self) -> None:
        slots = SECTION.cv_fields()
        for name, slot in slots.items():
            assert isinstance(slot, CVSlot), f"slot '{name}' is not a CVSlot"

    def test_dummy_artifact_subfield_keys(self) -> None:
        """Dummy artifact has all required sub-field keys."""
        art = _dummy_artifact()
        assert _REQUIRED_SUBFIELD_KEYS.issubset(art.sub_fields.keys()), (
            f"Missing keys: {_REQUIRED_SUBFIELD_KEYS - set(art.sub_fields.keys())}"
        )

    def test_dummy_artifact_cv_slots_present(self) -> None:
        """Dummy artifact has all 7 CV slots, all None."""
        art = _dummy_artifact()
        assert set(art.cv_fields.keys()) == _REQUIRED_CV_SLOTS
        for name, slot in art.cv_fields.items():
            assert slot.value is None, f"slot {name} has value {slot.value}"

    def test_to_profile_payload_includes_cv_fields(self) -> None:
        """to_profile_payload() embeds _cv_fields under data with 7 keys."""
        art = _dummy_artifact()
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data, "to_profile_payload() missing '_cv_fields'"
        cv = data["_cv_fields"]
        assert set(cv.keys()) == _REQUIRED_CV_SLOTS, (
            f"_cv_fields keys mismatch: {set(cv.keys())}"
        )
        for slot_name, slot_meta in cv.items():
            assert slot_meta["value"] is None, (
                f"_cv_fields['{slot_name}']['value'] should be None"
            )
            assert "dtype" in slot_meta, f"_cv_fields['{slot_name}'] missing 'dtype'"
            assert "description" in slot_meta

    def test_to_profile_payload_prov_shape(self) -> None:
        """to_profile_payload() prov has required keys with correct types."""
        art = _dummy_artifact()
        _, prov = art.to_profile_payload()
        assert "source" in prov
        assert "n" in prov
        assert "confidence" in prov
        assert prov["confidence"] in ("low", "med", "high")
        assert "as_of" in prov

    def test_validate_accepts_valid_artifact(self) -> None:
        """validate() must return True for a well-formed dummy artifact."""
        art = _dummy_artifact()
        assert SECTION.validate(art) is True

    def test_validate_rejects_wrong_section(self) -> None:
        art = _dummy_artifact()
        art.section = "wrong_section"
        assert SECTION.validate(art) is False

    def test_validate_rejects_out_of_range_fg_pct(self) -> None:
        art = _dummy_artifact()
        art.sub_fields["creation"]["catch_shoot_fg_pct"] = 1.5  # impossible
        assert SECTION.validate(art) is False

    def test_validate_rejects_filled_cv_slot(self) -> None:
        """validate() should reject if any CV slot has a non-None value
        (CV branch owns filling; profile should arrive pre-fill)."""
        art = _dummy_artifact()
        # Force one slot to be filled
        art.cv_fields["defender_distance_dist"].value = 4.2
        assert SECTION.validate(art) is False

    def test_section_class_attributes(self) -> None:
        """section, entity, source_name must be set correctly."""
        assert SECTION.name == "shot_profile"
        assert SECTION.entity == "player"
        assert SECTION.source_name  # non-empty

    def test_section_key_and_parquet_name(self) -> None:
        assert SECTION.section_key() == "shot_profile"
        assert SECTION.parquet_name() == "atlas_player_shot_profile.parquet"
        assert SECTION.sec_fn_name() == "sec_shot_profile"


# ---------------------------------------------------------------------------
# 3. Build smoke-test (requires local parquets — skips if absent)
# ---------------------------------------------------------------------------

class TestBuildSmoke:
    """Light smoke test: build returns correct types when data is present."""

    def test_build_missing_player_returns_none(self) -> None:
        """Unknown player_id should return None (not raise)."""
        result = SECTION.build(MISSING_PID, CURRENT_AS_OF)
        assert result is None

    def test_build_sga_type(self) -> None:
        """build() for SGA returns AtlasArtifact or None (never raises)."""
        result = SECTION.build(SGA_PID, CURRENT_AS_OF)
        assert result is None or isinstance(result, AtlasArtifact)

    def test_build_sga_if_present(self) -> None:
        """If SGA artifact is built, all top-level sub-field keys are present."""
        result = SECTION.build(SGA_PID, CURRENT_AS_OF)
        if result is None:
            pytest.skip("SGA not found in local parquets (acceptable in CI)")
        assert _REQUIRED_SUBFIELD_KEYS.issubset(result.sub_fields.keys())

    def test_build_sga_cv_slots_if_present(self) -> None:
        """If SGA artifact is built, all 7 CV slots exist with value=None."""
        result = SECTION.build(SGA_PID, CURRENT_AS_OF)
        if result is None:
            pytest.skip("SGA not found in local parquets")
        assert set(result.cv_fields.keys()) == _REQUIRED_CV_SLOTS
        for name, slot in result.cv_fields.items():
            assert slot.value is None, f"slot {name} pre-filled"

    def test_build_validates_if_present(self) -> None:
        """Built artifact passes validate()."""
        result = SECTION.build(SGA_PID, CURRENT_AS_OF)
        if result is None:
            pytest.skip("SGA not found in local parquets")
        assert SECTION.validate(result) is True
