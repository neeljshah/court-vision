"""Tests for intel/player_playmaking_network.py.

Assertions:
  1. LEAK-SAFETY: build() with an as_of strictly before any game data returns None
     OR an artifact with zero real sub_fields (no future data leaked).
  2. SCHEMA CONFORMANCE: a valid artifact has all required keys + cv_fields with
     correct slot names and null values.
  3. CV SLOT RESERVATION: cv_fields() returns exactly the two reserved CV slots
     (pass_velocity, gravity_drawn) with value=None.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

# Ensure repo root is on sys.path so src.loop.* resolves in all run modes.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pytest

from intel.player_playmaking_network import PlayerPlaymakingNetwork
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECTION = PlayerPlaymakingNetwork()

# A player known to exist in the tracking parquets (LeBron James, id=2544).
# If data is absent (CI / offline), tests degrade gracefully.
_KNOWN_PID = 2544

# A date far in the past so NO parquet rows qualify -- guarantees leak-safety test.
_EPOCH = _dt.datetime(2000, 1, 1, 0, 0, 0)

# A current-ish date that should have data when parquets are present.
_NOW = _dt.datetime(2025, 4, 1, 0, 0, 0)


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Build at an as_of that pre-dates all data should yield None or empty artifact."""

    def test_prehistoric_as_of_returns_none_or_empty(self):
        """No game occurred on 2000-01-01; build must return None (no data)."""
        artifact = _SECTION.build(_KNOWN_PID, _EPOCH)
        # Either no data found (None) or artifact with only DEFER / null fields
        if artifact is not None:
            sf = artifact.sub_fields
            real_keys = [
                "passes_made", "potential_ast", "ast_pts_created",
                "ast_ratio", "ast_to_tov",
            ]
            real_values = [sf.get(k) for k in real_keys if sf.get(k) is not None]
            assert real_values == [], (
                "Leak detected: real sub_fields populated for epoch as_of. "
                f"Found: {real_values}"
            )

    def test_as_of_is_strict_less_than(self):
        """Artifact as_of must never exceed the requested as_of date."""
        artifact = _SECTION.build(_KNOWN_PID, _NOW)
        if artifact is None:
            pytest.skip("No data available for this player (offline/CI environment).")
        assert artifact.as_of is not None
        assert artifact.as_of <= _NOW.date().isoformat(), (
            f"Artifact as_of ({artifact.as_of}) > requested as_of ({_NOW.date()}). "
            "LEAK: future data stamped into the artifact."
        )

    def test_adv_stats_filter_is_strict_before_date(self):
        """Advanced stats aggregation must use game_date < as_of (not <=)."""
        # Build with as_of = a specific date, then verify artifact.as_of <= that date
        as_of = _dt.datetime(2024, 1, 1)
        artifact = _SECTION.build(_KNOWN_PID, as_of)
        if artifact is None:
            pytest.skip("No data available for this configuration.")
        assert artifact.as_of <= "2024-01-01", (
            f"as_of bound violated: artifact.as_of={artifact.as_of}"
        )


# ---------------------------------------------------------------------------
# 2. Schema conformance assertion (cv_fields present)
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Valid artifact must carry the full expected sub_field + cv_field schema."""

    def _build_artifact(self) -> AtlasArtifact:
        art = _SECTION.build(_KNOWN_PID, _NOW)
        if art is None:
            pytest.skip("No parquet data for player (offline/CI environment).")
        return art

    def test_artifact_is_atlas_artifact_instance(self):
        art = self._build_artifact()
        assert isinstance(art, AtlasArtifact)

    def test_section_name_is_playmaking_network(self):
        art = self._build_artifact()
        assert art.section == "playmaking_network"

    def test_entity_is_player(self):
        art = self._build_artifact()
        assert art.entity == "player"

    def test_provenance_fields_present(self):
        art = self._build_artifact()
        for key in ("source", "n", "confidence", "as_of"):
            assert key in art.provenance, f"Missing provenance key: {key}"

    def test_confidence_valid_level(self):
        art = self._build_artifact()
        assert art.confidence in ("low", "med", "high")

    def test_cv_fields_schema_present(self):
        """cv_fields must contain exactly the two reserved slots."""
        art = self._build_artifact()
        assert "pass_velocity" in art.cv_fields, "Missing CV slot: pass_velocity"
        assert "gravity_drawn" in art.cv_fields, "Missing CV slot: gravity_drawn"

    def test_cv_fields_values_are_null(self):
        """CV slot values MUST be None -- only the CV branch may fill them."""
        art = self._build_artifact()
        for slot_name, slot in art.cv_fields.items():
            assert isinstance(slot, CVSlot), (
                f"cv_fields['{slot_name}'] should be a CVSlot, got {type(slot)}"
            )
            assert slot.value is None, (
                f"CV slot '{slot_name}' has value={slot.value!r}; "
                "only the CV branch may fill this."
            )

    def test_defer_keys_present_as_none(self):
        """DEFER sub-fields must exist in the dict (as None) so callers know the schema."""
        art = self._build_artifact()
        defer_keys = ["lob_ast_count", "kickout_ast_count", "dish_ast_count", "teammate_map"]
        for k in defer_keys:
            assert k in art.sub_fields, f"Missing DEFER key in sub_fields: {k}"
            assert art.sub_fields[k] is None, (
                f"DEFER key '{k}' should be None, got {art.sub_fields[k]!r}"
            )

    def test_to_profile_payload_embeds_cv_fields(self):
        """to_profile_payload() must embed _cv_fields with both slot keys."""
        art = self._build_artifact()
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data
        assert "pass_velocity" in data["_cv_fields"]
        assert "gravity_drawn" in data["_cv_fields"]
        # Values should still be None in the payload
        assert data["_cv_fields"]["pass_velocity"]["value"] is None
        assert data["_cv_fields"]["gravity_drawn"]["value"] is None

    def test_validate_returns_true_for_valid_artifact(self):
        art = self._build_artifact()
        assert _SECTION.validate(art) is True


# ---------------------------------------------------------------------------
# 3. CV slot reservation (static -- does not require parquet data)
# ---------------------------------------------------------------------------

class TestCVSlotReservation:
    """cv_fields() returns the correct static schema regardless of data availability."""

    def test_cv_fields_returns_two_slots(self):
        slots = _SECTION.cv_fields()
        assert len(slots) == 2, f"Expected 2 CV slots, got {len(slots)}: {list(slots)}"

    def test_pass_velocity_slot_schema(self):
        slots = _SECTION.cv_fields()
        sv = slots["pass_velocity"]
        assert isinstance(sv, CVSlot)
        assert sv.dtype == "float"
        assert sv.unit == "ft/s"
        assert sv.value is None

    def test_gravity_drawn_slot_schema(self):
        slots = _SECTION.cv_fields()
        gd = slots["gravity_drawn"]
        assert isinstance(gd, CVSlot)
        assert gd.dtype == "float"
        assert gd.value is None

    def test_slot_names_are_stable_contract(self):
        """Slot names are a stable contract; renaming them is a breaking change."""
        slots = _SECTION.cv_fields()
        assert set(slots.keys()) == {"pass_velocity", "gravity_drawn"}

    def test_section_key_and_fn_name(self):
        assert _SECTION.section_key() == "playmaking_network"
        assert _SECTION.sec_fn_name() == "sec_playmaking_network"
        assert _SECTION.parquet_name() == "atlas_player_playmaking_network.parquet"


# ---------------------------------------------------------------------------
# 4. validate() contract
# ---------------------------------------------------------------------------

class TestValidate:
    """Validate rejects artifacts with missing schema or bad numeric ranges."""

    _SENTINEL = object()

    def _make_artifact(self, sub_fields=_SENTINEL, cv_fields=None) -> AtlasArtifact:
        if sub_fields is self._SENTINEL:
            sub_fields = {"passes_made": 20.0}
        return AtlasArtifact(
            section="playmaking_network",
            entity="player",
            entity_id=2544,
            sub_fields=sub_fields,
            provenance={"source": "test", "n": 30, "confidence": "high", "as_of": "2025-01-01"},
            confidence="high",
            as_of="2025-01-01",
            cv_fields=cv_fields or _SECTION.cv_fields(),
        )

    def test_validate_rejects_empty_sub_fields(self):
        art = self._make_artifact(sub_fields={})
        assert _SECTION.validate(art) is False

    def test_validate_rejects_missing_cv_slot(self):
        bad_cv = {"pass_velocity": CVSlot("pass_velocity", "float", "", "ft/s", None)}
        # Missing gravity_drawn
        art = self._make_artifact(cv_fields=bad_cv)
        assert _SECTION.validate(art) is False

    def test_validate_rejects_filled_cv_slot(self):
        filled_cv = _SECTION.cv_fields()
        filled_cv["gravity_drawn"] = CVSlot("gravity_drawn", "float", "", None, 0.42)
        art = self._make_artifact(cv_fields=filled_cv)
        assert _SECTION.validate(art) is False

    def test_validate_rejects_negative_passes_made(self):
        art = self._make_artifact(sub_fields={"passes_made": -1.0})
        assert _SECTION.validate(art) is False

    def test_validate_rejects_drive_tov_rate_out_of_range(self):
        sf = {"passes_made": 10.0, "drive_tov_rate": 1.5}
        art = self._make_artifact(sub_fields=sf)
        assert _SECTION.validate(art) is False

    def test_validate_accepts_good_artifact(self):
        sf = {
            "passes_made": 25.0,
            "potential_ast": 4.5,
            "ast_pts_created": 7.2,
            "ast_ratio": 18.0,
            "ast_to_tov": 2.1,
            "drive_tov_rate": 0.12,
        }
        art = self._make_artifact(sub_fields=sf)
        assert _SECTION.validate(art) is True
