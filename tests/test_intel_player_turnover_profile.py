"""Tests for intel.player_turnover_profile (PlayerTurnoverProfile atlas section).

Assertions:
  1. Leak-safety: build(pid, as_of) never returns data from after the as_of date.
  2. Schema conformance: artifact has all required sub_field keys, correct cv_fields
     schema (all slots present with value=None), and valid provenance shape.
  3. Validate() accepts a well-formed artifact and rejects obviously bad ones.
  4. cv_fields() returns the three reserved CV slots with value=None.
  5. section_key / sec_fn_name / parquet_name follow the AtlasSection contract.

These tests are fully self-contained: they build from parquets that exist locally
(NBA_OFFLINE=1).  If the parquets are absent, tests gracefully skip or assert None.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

# Ensure repo root is on the path for src.loop imports
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intel.player_turnover_profile import PlayerTurnoverProfile, build_and_register
from src.loop.atlas import AtlasArtifact, CVSlot

# ---------------------------------------------------------------------------
# Fixtures / constants
# ---------------------------------------------------------------------------

# Use a well-known player who appears in player_adv_stats (SGA)
_SGA_ID = 1628983

# A far-past as_of date to test that data from later seasons is excluded
_PAST_AS_OF = _dt.datetime(2023, 1, 15, 0, 0, 0)

# Today's date for standard build
_NOW_AS_OF = _dt.datetime(2026, 5, 30, 0, 0, 0)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_section() -> PlayerTurnoverProfile:
    return PlayerTurnoverProfile()


# ---------------------------------------------------------------------------
# 1. Section contract attributes
# ---------------------------------------------------------------------------

class TestSectionContract:
    def test_name(self):
        s = _make_section()
        assert s.name == "turnover_profile"

    def test_entity(self):
        s = _make_section()
        assert s.entity == "player"

    def test_section_key(self):
        s = _make_section()
        assert s.section_key() == "turnover_profile"

    def test_sec_fn_name(self):
        s = _make_section()
        assert s.sec_fn_name() == "sec_turnover_profile"

    def test_parquet_name(self):
        s = _make_section()
        assert s.parquet_name() == "atlas_player_turnover_profile.parquet"


# ---------------------------------------------------------------------------
# 2. cv_fields schema
# ---------------------------------------------------------------------------

class TestCVFields:
    def test_returns_dict(self):
        s = _make_section()
        cv = s.cv_fields()
        assert isinstance(cv, dict)

    def test_three_slots_present(self):
        s = _make_section()
        cv = s.cv_fields()
        expected = {
            "ball_handler_speed_at_tov",
            "defender_proximity_at_tov",
            "spacing_at_tov_commit",
        }
        assert expected == set(cv.keys()), f"cv_fields keys mismatch: {set(cv.keys())}"

    def test_all_values_none(self):
        """CV branch has not run yet -- all slot values must be None."""
        s = _make_section()
        cv = s.cv_fields()
        for name, slot in cv.items():
            assert isinstance(slot, CVSlot), f"slot {name!r} is not a CVSlot"
            assert slot.value is None, (
                f"cv_fields slot {name!r} has non-None value {slot.value!r}; "
                "CV branch should not have filled it yet."
            )

    def test_slot_dtypes_and_units(self):
        s = _make_section()
        cv = s.cv_fields()
        expected_units = {
            "ball_handler_speed_at_tov": "ft/s",
            "defender_proximity_at_tov": "ft",
            "spacing_at_tov_commit": "ft^2",
        }
        for name, slot in cv.items():
            assert slot.dtype == "float", f"slot {name!r} dtype should be float"
            assert slot.unit == expected_units[name], (
                f"slot {name!r} unit: expected {expected_units[name]!r}, got {slot.unit!r}"
            )
            assert len(slot.description) > 10, f"slot {name!r} description too short"


# ---------------------------------------------------------------------------
# 3. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    def test_past_as_of_returns_none_or_older_data(self):
        """Build at _PAST_AS_OF=2023-01-15 must never include post-2023-01-15 records.

        If the player has NO data before this date (parquet absent or empty), we assert
        the build returns None (correct; not a failure).  If it returns an artifact, we
        check the as_of field on the artifact is <= the leak boundary.
        """
        s = _make_section()
        try:
            art = s.build(_SGA_ID, _PAST_AS_OF)
        except Exception as exc:
            pytest.fail(f"build raised unexpectedly: {exc}")

        if art is None:
            # Acceptable: player has no data before the leak boundary
            return

        # The artifact as_of must be on or before the requested leak boundary
        art_as_of = _dt.date.fromisoformat(art.as_of)
        leak_boundary = _PAST_AS_OF.date()
        assert art_as_of <= leak_boundary, (
            f"LEAK: artifact as_of={art_as_of} is AFTER the requested boundary "
            f"{leak_boundary}. build() is NOT leak-safe."
        )

    def test_future_as_of_not_stricter_than_past(self):
        """An artifact built at _NOW_AS_OF should have >= n_games than at _PAST_AS_OF.

        This verifies the time-filter is directionally correct (more data with later
        as_of), not just that it passes.  Skip if either build returns None.
        """
        s = _make_section()
        art_past = s.build(_SGA_ID, _PAST_AS_OF)
        art_now = s.build(_SGA_ID, _NOW_AS_OF)

        if art_past is None or art_now is None:
            pytest.skip("one of the builds returned None -- parquets may be absent")

        n_past = art_past.provenance.get("n", 0)
        n_now = art_now.provenance.get("n", 0)
        assert n_now >= n_past, (
            f"Later as_of should have more games: n_now={n_now} < n_past={n_past}. "
            "Possible leak or inverted as_of filter."
        )


# ---------------------------------------------------------------------------
# 4. Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    @pytest.fixture
    def artifact(self):
        s = _make_section()
        art = s.build(_SGA_ID, _NOW_AS_OF)
        if art is None:
            pytest.skip("build returned None (player_adv_stats not available)")
        return art

    def test_section_is_correct(self, artifact):
        assert artifact.section == "turnover_profile"

    def test_entity_is_player(self, artifact):
        assert artifact.entity == "player"

    def test_entity_id_matches(self, artifact):
        assert artifact.entity_id == _SGA_ID

    def test_as_of_present(self, artifact):
        assert artifact.as_of is not None
        # Must be a valid ISO date
        _dt.date.fromisoformat(artifact.as_of)

    def test_provenance_shape(self, artifact):
        prov = artifact.provenance
        assert "source" in prov
        assert "n" in prov
        assert "confidence" in prov
        assert "as_of" in prov
        assert prov["confidence"] in ("low", "med", "high")
        assert isinstance(prov["n"], int)
        assert prov["n"] >= 1

    def test_all_required_sub_fields_present(self, artifact):
        required = {
            "season_rate", "rolling", "by_quarter",
            "pressure_sensitivity", "by_type", "opponent_pressure",
        }
        missing = required - set(artifact.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {missing}"

    def test_defer_stubs_have_note(self, artifact):
        """DEFER sub-fields must carry a _note explaining the data gap."""
        for defer_key in ("by_type", "opponent_pressure"):
            stub = artifact.sub_fields.get(defer_key, {})
            assert "_note" in stub, (
                f"DEFER sub_field {defer_key!r} must have '_note' key"
            )
            assert len(stub["_note"]) > 20, (
                f"DEFER note for {defer_key!r} is too short (< 20 chars)"
            )

    def test_cv_fields_in_artifact(self, artifact):
        """cv_fields must be present in the artifact with the three reserved slots."""
        cv = artifact.cv_fields
        assert isinstance(cv, dict)
        expected = {
            "ball_handler_speed_at_tov",
            "defender_proximity_at_tov",
            "spacing_at_tov_commit",
        }
        assert expected == set(cv.keys()), f"Artifact cv_fields keys mismatch: {set(cv.keys())}"

    def test_cv_fields_all_none_in_artifact(self, artifact):
        for name, slot in artifact.cv_fields.items():
            assert slot.value is None, (
                f"cv_fields slot {name!r} in artifact has non-None value; "
                "CV branch should not have filled it."
            )

    def test_to_profile_payload_shape(self, artifact):
        """to_profile_payload() must return (data, prov) with _cv_fields embedded."""
        data, prov = artifact.to_profile_payload()
        assert isinstance(data, dict)
        assert isinstance(prov, dict)
        assert "_cv_fields" in data
        cv_embedded = data["_cv_fields"]
        assert isinstance(cv_embedded, dict)
        for slot_name in ("ball_handler_speed_at_tov", "defender_proximity_at_tov",
                          "spacing_at_tov_commit"):
            assert slot_name in cv_embedded, f"CV slot {slot_name!r} missing from payload"
            slot_dict = cv_embedded[slot_name]
            assert slot_dict["value"] is None
            assert slot_dict["dtype"] == "float"


# ---------------------------------------------------------------------------
# 5. Validate method
# ---------------------------------------------------------------------------

class TestValidate:
    def test_valid_artifact_passes(self):
        s = _make_section()
        art = s.build(_SGA_ID, _NOW_AS_OF)
        if art is None:
            pytest.skip("build returned None")
        assert s.validate(art) is True

    def test_wrong_section_fails(self):
        s = _make_section()
        art = s.build(_SGA_ID, _NOW_AS_OF)
        if art is None:
            pytest.skip("build returned None")
        art.section = "wrong_section"
        assert s.validate(art) is False

    def test_missing_sub_field_fails(self):
        s = _make_section()
        art = s.build(_SGA_ID, _NOW_AS_OF)
        if art is None:
            pytest.skip("build returned None")
        del art.sub_fields["by_quarter"]
        assert s.validate(art) is False

    def test_negative_turnover_ratio_fails(self):
        s = _make_section()
        art = s.build(_SGA_ID, _NOW_AS_OF)
        if art is None:
            pytest.skip("build returned None")
        art.sub_fields["rolling"]["l5_turnover_ratio"] = -1.0
        assert s.validate(art) is False

    def test_empty_cv_fields_fails(self):
        s = _make_section()
        art = s.build(_SGA_ID, _NOW_AS_OF)
        if art is None:
            pytest.skip("build returned None")
        art.cv_fields = {}
        assert s.validate(art) is False

    def test_filled_cv_slot_fails(self):
        """If a CV slot is pre-filled (non-None), validate should reject it."""
        s = _make_section()
        art = s.build(_SGA_ID, _NOW_AS_OF)
        if art is None:
            pytest.skip("build returned None")
        art.cv_fields["defender_proximity_at_tov"].value = 3.5
        assert s.validate(art) is False


# ---------------------------------------------------------------------------
# 6. build_and_register dry_run smoke test
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    def test_dry_run_returns_manifest(self):
        """dry_run=True should compute the manifest without touching disk."""
        manifest = build_and_register(
            player_ids=[_SGA_ID],
            as_of=_NOW_AS_OF,
            store=None,
            dry_run=True,
        )
        assert isinstance(manifest, dict)
        assert manifest.get("section") == "turnover_profile"
        assert "parquet" in manifest
        assert "sec_fn" in manifest
        assert manifest.get("sec_fn") == "sec_turnover_profile"
        cv_keys = manifest.get("cv_fields", [])
        assert set(cv_keys) == {
            "ball_handler_speed_at_tov",
            "defender_proximity_at_tov",
            "spacing_at_tov_commit",
        }

    def test_dry_run_n_entities(self):
        """With a single valid player_id, n_entities should be 0 or 1."""
        manifest = build_and_register(
            player_ids=[_SGA_ID],
            as_of=_NOW_AS_OF,
            store=None,
            dry_run=True,
        )
        assert manifest.get("n_entities", -1) in (0, 1)
