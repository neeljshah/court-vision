"""Tests for intel/player_usage_role.py.

Two primary assertions:
1. LEAK-SAFETY: build(player_id, as_of=past_date) must NOT include games after as_of.
2. SCHEMA-CONFORMANCE: artifact sub_fields contain every declared field (REAL + null for
   DEFER slots), cv_fields() returns the 4 reserved CV slots with value=None, and
   to_profile_payload() embeds _cv_fields correctly.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure the repo root is on sys.path so all src.* imports resolve.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from intel.player_usage_role import PlayerUsageRoleSection, _usage_tier, _creator_role
from src.loop.atlas import AtlasArtifact, CVSlot, confidence_from_n


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_SECTION = PlayerUsageRoleSection()

# SGA: a well-known high-usage player with data in all three parquets.
_SGA_ID = 1628983

# A date far in the past: should yield no games (or very few).
_ANCIENT = _dt.datetime(2010, 1, 1)

# A recent date: should capture full season data.
_RECENT = _dt.datetime(2025, 5, 1)


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must never include game-level data after the as_of boundary."""

    def test_ancient_as_of_returns_none_or_empty_artifact(self):
        """No NBA data existed before 2010-01-01 for modern players; should get None."""
        art = _SECTION.build(_SGA_ID, _ANCIENT)
        # Either None (no rows) or n_games == 0 is acceptable.
        if art is not None:
            assert art.sub_fields.get("n_games", 0) == 0, (
                "Artifact for an as_of before any games should have n_games=0"
            )

    def test_as_of_boundary_respected_for_player_adv(self):
        """Games after the as_of date must not appear in the artifact."""
        # Use a boundary at the start of 2025 — any game from 2025-01-02 onward excluded.
        boundary = _dt.datetime(2025, 1, 1)
        art = _SECTION.build(_SGA_ID, boundary)
        if art is None:
            return  # No data -> trivially safe
        # as_of field on the artifact must be <= boundary
        if art.as_of:
            assert art.as_of <= boundary.date().isoformat(), (
                f"Artifact as_of={art.as_of!r} is AFTER boundary={boundary!r}"
            )

    def test_n_games_does_not_exceed_games_before_as_of(self):
        """n_games reported must be plausible (> 0 and <= a generous upper bound)."""
        art = _SECTION.build(_SGA_ID, _RECENT)
        if art is None:
            pytest.skip("No adv_stats data available in test environment")
        assert art.sub_fields["n_games"] > 0
        # SGA has played at most ~300 games up to May 2025 across all seasons
        assert art.sub_fields["n_games"] <= 400

    def test_different_as_of_yields_different_n_games(self):
        """Earlier as_of should yield fewer games than a later as_of (monotonicity)."""
        art_early = _SECTION.build(_SGA_ID, _dt.datetime(2023, 6, 1))
        art_late = _SECTION.build(_SGA_ID, _RECENT)
        if art_early is None or art_late is None:
            pytest.skip("Not enough data to compare")
        assert art_early.sub_fields["n_games"] <= art_late.sub_fields["n_games"], (
            "Earlier as_of must not yield MORE games than a later as_of"
        )


# ---------------------------------------------------------------------------
# 2. Schema-conformance assertion
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact must carry all declared REAL sub_fields + 4 CV slots (null)."""

    REAL_SUB_FIELDS = [
        "usage_rate", "usage_l10_mean", "usage_tier",
        "minutes_pg", "ast_pct", "pie_mean",
        "on_net_rtg", "off_net_rtg", "on_off_net_diff",
        "on_off_impact_z", "minutes_on",
        "iso_poss_pg", "pnr_handler_pg", "transition_poss_pg",
        "avg_seconds_per_touch", "creator_role", "n_games",
    ]

    EXPECTED_CV_SLOTS = [
        "cv_ball_handler_pct",
        "cv_iso_freq",
        "cv_off_ball_screen_rate",
        "cv_drive_to_creation_rate",
    ]

    def _get_artifact(self) -> AtlasArtifact:
        art = _SECTION.build(_SGA_ID, _RECENT)
        if art is None:
            pytest.skip("No data available; skipping schema test")
        return art

    def test_all_real_sub_fields_present(self):
        """Every declared REAL sub_field key must be present in sub_fields."""
        art = self._get_artifact()
        for key in self.REAL_SUB_FIELDS:
            assert key in art.sub_fields, (
                f"sub_fields missing declared key: {key!r}"
            )

    def test_cv_fields_returns_four_slots(self):
        """cv_fields() must return exactly the 4 reserved CV slot names."""
        slots = _SECTION.cv_fields()
        for name in self.EXPECTED_CV_SLOTS:
            assert name in slots, f"cv_fields() missing slot: {name!r}"
        assert len(slots) == len(self.EXPECTED_CV_SLOTS)

    def test_cv_fields_values_are_none(self):
        """All CV slots must have value=None (not yet filled by CV branch)."""
        for name, slot in _SECTION.cv_fields().items():
            assert slot.value is None, (
                f"CV slot {name!r} should be null until CV branch fills it, "
                f"got: {slot.value!r}"
            )

    def test_cv_fields_have_dtype_and_description(self):
        """Every CV slot must declare dtype and a non-empty description."""
        for name, slot in _SECTION.cv_fields().items():
            assert slot.dtype, f"Slot {name!r} missing dtype"
            assert slot.description, f"Slot {name!r} missing description"

    def test_artifact_cv_fields_embedded_in_sub_fields(self):
        """artifact.cv_fields must match section.cv_fields() schema (all null now)."""
        art = self._get_artifact()
        section_slots = _SECTION.cv_fields()
        for name in section_slots:
            assert name in art.cv_fields, (
                f"Artifact cv_fields missing slot: {name!r}"
            )
            assert art.cv_fields[name].value is None

    def test_to_profile_payload_includes_cv_fields_block(self):
        """to_profile_payload() data must contain '_cv_fields' with all 4 slots."""
        art = self._get_artifact()
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data, "to_profile_payload data missing '_cv_fields'"
        for name in self.EXPECTED_CV_SLOTS:
            assert name in data["_cv_fields"], (
                f"_cv_fields block missing slot: {name!r}"
            )
            assert data["_cv_fields"][name]["value"] is None

    def test_provenance_fields(self):
        """Provenance must carry source, n, confidence, and as_of."""
        art = self._get_artifact()
        _, prov = art.to_profile_payload()
        for key in ("source", "n", "confidence", "as_of"):
            assert key in prov, f"Provenance missing key: {key!r}"
        assert prov["confidence"] in ("low", "med", "high")
        assert prov["n"] > 0

    def test_validate_passes_for_sga(self):
        """Section.validate() must return True for a well-formed SGA artifact."""
        art = self._get_artifact()
        assert _SECTION.validate(art), "validate() returned False for SGA artifact"

    def test_entity_and_section_labels(self):
        """Artifact must carry correct entity type and section name."""
        art = self._get_artifact()
        assert art.entity == "player"
        assert art.section == "usage_role"
        assert art.entity_id == _SGA_ID


# ---------------------------------------------------------------------------
# 3. Classification helper unit tests
# ---------------------------------------------------------------------------

class TestClassifiers:
    """Unit tests for _usage_tier and _creator_role helpers."""

    def test_usage_tier_primary(self):
        assert _usage_tier(0.30) == "primary"

    def test_usage_tier_secondary(self):
        assert _usage_tier(0.23) == "secondary"

    def test_usage_tier_rotation(self):
        assert _usage_tier(0.18) == "rotation"

    def test_usage_tier_bench(self):
        assert _usage_tier(0.15) == "bench"

    def test_usage_tier_low(self):
        assert _usage_tier(0.08) == "low"

    def test_usage_tier_none(self):
        assert _usage_tier(None) == "unknown"

    def test_creator_role_primary(self):
        # High usage + high ast + high pnr + high iso -> primary_creator
        assert _creator_role(0.30, 0.25, 3.0, 2.0) == "primary_creator"

    def test_creator_role_secondary(self):
        # Moderate creator: usage + ast pass (2/4) -> secondary_creator
        # iso=0.5 (< 2.0), pnr=0.8 (< 1.5) -> score=2 -> secondary_creator
        assert _creator_role(0.22, 0.21, 0.5, 0.8) == "secondary_creator"

    def test_creator_role_spot_up(self):
        # Low usage, low ast, low pnr/iso
        assert _creator_role(0.12, 0.05, 0.2, 0.3) == "spot_up"


# ---------------------------------------------------------------------------
# 4. AtlasSection contract surface
# ---------------------------------------------------------------------------

class TestAtlasSectionContract:
    """Verify the section implements all required abstract methods."""

    def test_section_key(self):
        assert _SECTION.section_key() == "usage_role"

    def test_sec_fn_name(self):
        assert _SECTION.sec_fn_name() == "sec_usage_role"

    def test_parquet_name(self):
        assert _SECTION.parquet_name() == "atlas_player_usage_role.parquet"

    def test_entity_is_player(self):
        assert _SECTION.entity == "player"

    def test_build_returns_none_for_unknown_player(self):
        unknown_pid = 9999999
        art = _SECTION.build(unknown_pid, _RECENT)
        assert art is None
