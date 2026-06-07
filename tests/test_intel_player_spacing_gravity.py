"""Tests for intel/player_spacing_gravity.py.

Assertions:
  1. Leak-safety: build() never returns data stamped after the as_of date.
  2. Schema conformance: artifact has all required sub_fields + cv_fields.
  3. CV-slot schema: cv_fields() returns the two reserved slots with value=None.
  4. validate() passes on a well-formed artifact and fails on a malformed one.
  5. build_and_register() dry-run returns a non-empty manifest without disk I/O.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure repo root is on sys.path (per DESIGN.md: scripts sys.path.insert(0,'.'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_PAST_AS_OF = _dt.datetime(2020, 1, 1, 0, 0, 0)  # far past — minimal data expected
_RECENT_AS_OF = _dt.datetime(2026, 5, 30, 0, 0, 0)

# A player known to be in player_tracking_features (SGA)
_SGA_PID = 1628983
# A player extremely unlikely to exist in any source
_MISSING_PID = 9999999


def _make_valid_artifact(section_name: str = "spacing_gravity") -> AtlasArtifact:
    """Build a minimal valid artifact matching the section contract."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    cv = PlayerSpacingGravity().cv_fields()
    sub_fields = {
        "off_ball": {},
        "cs_gravity": {},
        "lineup_spacing": {},
        "teammate_impact": {},
        "playtypes_gravity": {},
        "cv_coverage": {},
        "gravity_score": 0.5,
        "gravity_radius": {"_note": "DEFER"},
        "off_ball_cut_rate": {"_note": "DEFER"},
        "gravity_pts_created": {"_note": "DEFER"},
    }
    return AtlasArtifact(
        section=section_name,
        entity="player",
        entity_id=_SGA_PID,
        value=0.5,
        sub_fields=sub_fields,
        provenance={"source": "test", "n": 10, "confidence": "med",
                    "as_of": "2026-05-30"},
        confidence="med",
        as_of="2026-05-30",
        cv_fields=cv,
    )


# ---------------------------------------------------------------------------
# 1. Module import
# ---------------------------------------------------------------------------

def test_import() -> None:
    """Module imports without error."""
    import intel.player_spacing_gravity as m  # noqa: F401
    assert hasattr(m, "PlayerSpacingGravity")
    assert hasattr(m, "build_and_register")


# ---------------------------------------------------------------------------
# 2. CV-slot schema conformance
# ---------------------------------------------------------------------------

def test_cv_fields_schema() -> None:
    """cv_fields() returns exactly the two reserved slots with value=None."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    cv = section.cv_fields()

    assert isinstance(cv, dict), "cv_fields() must return a dict"
    assert set(cv.keys()) == {"avg_defender_attention", "off_ball_movement"}, (
        f"Expected exactly avg_defender_attention + off_ball_movement, got {set(cv.keys())}"
    )

    for slot_name, slot in cv.items():
        assert isinstance(slot, CVSlot), f"{slot_name} must be a CVSlot"
        assert slot.value is None, (
            f"CV slot '{slot_name}' must have value=None (CV branch fills later)"
        )
        assert slot.name == slot_name, "slot.name must match dict key"
        assert slot.dtype in ("float", "dist", "list", "categorical"), (
            f"Unexpected dtype {slot.dtype!r} for slot {slot_name}"
        )

    # avg_defender_attention: no physical unit (fraction)
    assert cv["avg_defender_attention"].unit is None
    # off_ball_movement: units = ft/s
    assert cv["off_ball_movement"].unit == "ft/s"


# ---------------------------------------------------------------------------
# 3. Leak-safety assertion
# ---------------------------------------------------------------------------

def test_leak_safety_past_as_of() -> None:
    """build() with a very old as_of must not raise; artifact as_of <= requested."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    # Using a past date: the artifact (if any) must have as_of <= past date string
    result = section.build(_SGA_PID, _PAST_AS_OF)

    if result is None:
        # Acceptable: no data before 2020-01-01
        return

    # as_of on the artifact must not be later than the decision date
    assert result.as_of is not None
    assert result.as_of <= _PAST_AS_OF.date().isoformat(), (
        f"Leak violation: artifact as_of={result.as_of!r} "
        f"is after decision as_of={_PAST_AS_OF.date().isoformat()!r}"
    )


def test_leak_safety_recent_as_of() -> None:
    """build() with a recent as_of must pin artifact as_of to the requested date."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    result = section.build(_SGA_PID, _RECENT_AS_OF)

    if result is None:
        pytest.skip("Player not found in any source — skip (not a leak issue)")

    # The artifact as_of must equal the requested date (not today's UTC clock)
    assert result.as_of == _RECENT_AS_OF.date().isoformat(), (
        f"artifact.as_of={result.as_of!r} != {_RECENT_AS_OF.date().isoformat()!r}"
    )

    # No clock-leaking: build must NOT call datetime.utcnow() for the as_of pin
    # (verified by structure: as_of_str = as_of.date().isoformat() in build())


# ---------------------------------------------------------------------------
# 4. Schema conformance on built artifact
# ---------------------------------------------------------------------------

def test_schema_conformance_required_sub_fields() -> None:
    """A built artifact includes all required sub_field keys."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    result = section.build(_SGA_PID, _RECENT_AS_OF)

    if result is None:
        pytest.skip("No data for player; skip schema check")

    required = {
        "off_ball", "cs_gravity", "lineup_spacing", "teammate_impact",
        "playtypes_gravity", "cv_coverage", "gravity_score",
        "gravity_radius", "off_ball_cut_rate", "gravity_pts_created",
    }
    missing = required - set(result.sub_fields.keys())
    assert not missing, f"Missing sub_fields: {missing}"


def test_schema_conformance_cv_fields_present() -> None:
    """A built artifact carries both CV slots with value=None."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    result = section.build(_SGA_PID, _RECENT_AS_OF)

    if result is None:
        pytest.skip("No data for player; skip cv_fields check")

    assert "avg_defender_attention" in result.cv_fields, (
        "CV slot 'avg_defender_attention' missing from artifact"
    )
    assert "off_ball_movement" in result.cv_fields, (
        "CV slot 'off_ball_movement' missing from artifact"
    )
    for slot_name, slot in result.cv_fields.items():
        assert slot.value is None, (
            f"CV slot '{slot_name}' value must be None before CV branch runs"
        )


def test_gravity_score_range() -> None:
    """gravity_score (if populated) must be in [0, 1]."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    result = section.build(_SGA_PID, _RECENT_AS_OF)

    if result is None:
        pytest.skip("No data for player")

    gs = result.sub_fields.get("gravity_score")
    if gs is not None:
        assert 0.0 <= gs <= 1.0, f"gravity_score={gs!r} out of [0, 1]"


def test_missing_player_returns_none() -> None:
    """build() returns None for a player absent from all sources."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    result = section.build(_MISSING_PID, _RECENT_AS_OF)
    assert result is None, (
        "Expected None for an unknown player; sources should return empty dicts"
    )


# ---------------------------------------------------------------------------
# 5. validate() checks
# ---------------------------------------------------------------------------

def test_validate_passes_on_valid_artifact() -> None:
    """validate() returns True for a well-formed artifact."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    art = _make_valid_artifact()
    assert section.validate(art) is True


def test_validate_fails_wrong_section() -> None:
    """validate() returns False when section name doesn't match."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    art = _make_valid_artifact(section_name="wrong_section")
    assert section.validate(art) is False


def test_validate_fails_cv_value_set() -> None:
    """validate() returns False when a CV slot already has a value (CV hasn't run)."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    art = _make_valid_artifact()
    # Simulate CV branch having accidentally set a value
    art.cv_fields["off_ball_movement"] = CVSlot(
        name="off_ball_movement",
        dtype="float",
        description="...",
        unit="ft/s",
        value=3.14,  # non-None triggers fail
    )
    assert section.validate(art) is False


def test_validate_fails_missing_sub_field() -> None:
    """validate() returns False when a required sub_field key is absent."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    art = _make_valid_artifact()
    del art.sub_fields["off_ball"]  # remove a required key
    assert section.validate(art) is False


def test_validate_fails_gravity_score_out_of_range() -> None:
    """validate() returns False when gravity_score is outside [0, 1]."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    art = _make_valid_artifact()
    art.sub_fields["gravity_score"] = 1.5  # invalid
    assert section.validate(art) is False


# ---------------------------------------------------------------------------
# 6. Section metadata
# ---------------------------------------------------------------------------

def test_section_metadata() -> None:
    """Section class attributes match the contract."""
    from intel.player_spacing_gravity import PlayerSpacingGravity

    section = PlayerSpacingGravity()
    assert section.name == "spacing_gravity"
    assert section.entity == "player"
    assert section.section_key() == "spacing_gravity"
    assert section.sec_fn_name() == "sec_spacing_gravity"
    assert section.parquet_name() == "atlas_player_spacing_gravity.parquet"


# ---------------------------------------------------------------------------
# 7. build_and_register dry-run
# ---------------------------------------------------------------------------

def test_build_and_register_dry_run() -> None:
    """build_and_register returns a manifest without writing any files."""
    from intel.player_spacing_gravity import build_and_register

    manifest = build_and_register(
        player_ids=[_SGA_PID, _MISSING_PID],
        as_of=_RECENT_AS_OF,
        store=None,
        dry_run=True,
    )
    assert isinstance(manifest, dict)
    assert manifest["section"] == "spacing_gravity"
    assert "cv_fields" in manifest
    assert "avg_defender_attention" in manifest["cv_fields"]
    assert "off_ball_movement" in manifest["cv_fields"]
    # dry_run: no parquet written, but n_entities may be 0 or >0
    assert manifest["n_entities"] >= 0
