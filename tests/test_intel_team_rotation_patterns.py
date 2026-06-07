"""Tests for intel/team_rotation_patterns.py (TeamRotationPatterns AtlasSection).

Two mandatory assertions per spec:
  1. Leak-safety: build() with a past as_of returns None or an artifact stamped
     at or before that date (never a future record).
  2. Schema conformance: artifact carries all required sub-field keys, all CV slots
     are reserved (value=None), and validate() passes.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Dict

import pytest

# Ensure repo root on sys.path so imports resolve in offline mode.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Patch env before any project import to stay offline.
import os
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.team_rotation_patterns import (
    TeamRotationPatterns,
    build_and_register,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def section() -> TeamRotationPatterns:
    return TeamRotationPatterns()


@pytest.fixture
def as_of_past() -> _dt.datetime:
    """A firmly past date — ensures no future data leaks in."""
    return _dt.datetime(2020, 1, 1, 0, 0, 0)


@pytest.fixture
def as_of_recent() -> _dt.datetime:
    """Recent date for a real build test (data available for 2024-25 season)."""
    return _dt.datetime(2025, 6, 30, 0, 0, 0)


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

def test_leak_safety_past_date(section: TeamRotationPatterns, as_of_past: _dt.datetime) -> None:
    """build() with as_of=2020-01-01 must return None (no lineup JSON exists before 2020 end).

    Verifies the as_of guard correctly blocks data whose season end-date > as_of.
    The 2018-19 season ended in June 2019, so it should be available; however
    the artifact's as_of stamp must not exceed the requested date.
    """
    art = section.build("GSW", as_of_past)
    if art is not None:
        # If an artifact was returned, its as_of must not be after the requested date.
        assert art.as_of is not None, "artifact must carry an as_of stamp"
        assert art.as_of <= as_of_past.date().isoformat(), (
            f"LEAK: artifact as_of={art.as_of!r} is AFTER requested as_of={as_of_past.date().isoformat()!r}"
        )
        # Provenance must also be <= requested date
        prov_as_of = art.provenance.get("as_of", "")
        if prov_as_of:
            assert prov_as_of <= as_of_past.date().isoformat(), (
                f"LEAK: provenance as_of={prov_as_of!r} is AFTER requested as_of"
            )


def test_leak_safety_no_future_season(section: TeamRotationPatterns) -> None:
    """build() must never return data stamped after the requested as_of.

    Uses as_of=2022-01-01. Season 2022-23 ends June 2023, so its lineup file
    must NOT be used. Only 2018-19 / 2020-21 / 2021-22 files are eligible.
    """
    as_of = _dt.datetime(2022, 1, 1, 0, 0, 0)
    art = section.build("ATL", as_of)
    if art is not None:
        assert art.as_of <= "2022-01-01", (
            f"LEAK: returned artifact as_of={art.as_of!r} after requested 2022-01-01"
        )
        season_used = art.sub_fields.get("season_used", "")
        if season_used:
            from intel.team_rotation_patterns import _season_end
            assert _season_end(season_used) <= "2022-01-01", (
                f"LEAK: season {season_used!r} ends after requested as_of"
            )


# ---------------------------------------------------------------------------
# 2. Schema-conformance assertion (incl. cv_fields present and null)
# ---------------------------------------------------------------------------

def test_cv_fields_schema(section: TeamRotationPatterns) -> None:
    """cv_fields() returns the 4 reserved CV slots with value=None."""
    slots: Dict[str, CVSlot] = section.cv_fields()
    expected_slots = {
        "lineup_spacing_mean",
        "transition_pace_cv",
        "closer_velocity",
        "rotation_fatigue_cv",
    }
    assert set(slots.keys()) == expected_slots, (
        f"CV slots mismatch: got {set(slots.keys())!r}, expected {expected_slots!r}"
    )
    for slot_name, slot in slots.items():
        assert isinstance(slot, CVSlot), f"slot {slot_name!r} must be CVSlot"
        assert slot.value is None, (
            f"CV slot {slot_name!r} must have value=None (CV branch fills later)"
        )
        assert slot.dtype, f"CV slot {slot_name!r} must have dtype"
        assert slot.description, f"CV slot {slot_name!r} must have description"


def test_section_metadata(section: TeamRotationPatterns) -> None:
    """Section has correct name, entity, and helper method outputs."""
    assert section.name == "rotation_patterns"
    assert section.entity == "team"
    assert section.section_key() == "rotation_patterns"
    assert section.sec_fn_name() == "sec_rotation_patterns"
    assert section.parquet_name() == "atlas_team_rotation_patterns.parquet"


def test_schema_conformance_with_real_data(
    section: TeamRotationPatterns, as_of_recent: _dt.datetime
) -> None:
    """build() for a team with 2024-25 data produces a schema-valid artifact.

    Skipped if no lineup JSON files are present (CI without data).
    """
    lineup_dir = _ROOT / "data" / "nba" / "lineups"
    if not (lineup_dir / "lineup_splits_ATL_2024-25.json").exists():
        pytest.skip("No lineup JSON data available — skipping real-data schema test")

    art = section.build("ATL", as_of_recent)
    assert art is not None, "Expected artifact for ATL with 2024-25 data"

    # Required sub-field keys
    required_keys = {
        "starters", "closing_lineup", "depth", "rotation_stability",
        "pace_context", "star_rest", "q4_patterns",
        "playoff_shortening", "stagger_times",
    }
    assert required_keys.issubset(art.sub_fields.keys()), (
        f"Missing sub-fields: {required_keys - set(art.sub_fields.keys())}"
    )

    # CV fields present and all null
    assert art.cv_fields, "cv_fields must be non-empty"
    for slot_name, slot in art.cv_fields.items():
        assert slot.value is None, (
            f"CV slot {slot_name!r} must remain None (CV branch fills later)"
        )

    # Provenance keys
    prov = art.provenance
    assert "source" in prov
    assert "n" in prov and isinstance(prov["n"], int)
    assert "confidence" in prov and prov["confidence"] in ("low", "med", "high")
    assert "as_of" in prov

    # as_of stamp must not exceed the requested date
    assert art.as_of is not None
    assert art.as_of <= as_of_recent.date().isoformat(), (
        f"LEAK: artifact as_of={art.as_of!r} after requested as_of"
    )

    # validate() must pass
    assert section.validate(art), "validate() returned False for a well-formed artifact"


def test_validate_rejects_missing_keys(section: TeamRotationPatterns) -> None:
    """validate() returns False when required sub-field keys are absent."""
    art = AtlasArtifact(
        section="rotation_patterns",
        entity="team",
        entity_id="GSW",
        sub_fields={"starters": {}},  # missing most required keys
        provenance={"source": "test", "n": 10, "confidence": "med", "as_of": "2025-01-01"},
        confidence="med",
        as_of="2025-01-01",
        cv_fields=section.cv_fields(),
    )
    assert not section.validate(art), "validate() should reject artifact missing required sub-fields"


def test_validate_rejects_filled_cv_slot(section: TeamRotationPatterns) -> None:
    """validate() returns False when a CV slot already has a non-None value."""
    # Build full valid cv_fields then pollute one
    cv = section.cv_fields()
    cv["lineup_spacing_mean"] = CVSlot(
        name="lineup_spacing_mean",
        dtype="float",
        description="test",
        value=42.0,  # should be None until CV fills it
    )
    # Build minimal valid sub_fields
    sf = {k: {} for k in [
        "starters", "closing_lineup", "depth", "rotation_stability",
        "pace_context", "star_rest", "q4_patterns",
        "playoff_shortening", "stagger_times",
    ]}
    art = AtlasArtifact(
        section="rotation_patterns",
        entity="team",
        entity_id="GSW",
        sub_fields=sf,
        provenance={"source": "test", "n": 30, "confidence": "high", "as_of": "2025-01-01"},
        confidence="high",
        as_of="2025-01-01",
        cv_fields=cv,
    )
    assert not section.validate(art), "validate() should reject artifact with pre-filled CV slot"


def test_build_returns_none_for_unknown_team(section: TeamRotationPatterns) -> None:
    """build() returns None gracefully for a team tricode with no lineup files."""
    art = section.build("ZZZ", _dt.datetime(2025, 6, 30))
    assert art is None, "Expected None for unknown team tricode 'ZZZ'"


def test_to_profile_payload_shape(
    section: TeamRotationPatterns, as_of_recent: _dt.datetime
) -> None:
    """to_profile_payload() returns (data, prov) with _cv_fields embedded in data."""
    lineup_dir = _ROOT / "data" / "nba" / "lineups"
    if not (lineup_dir / "lineup_splits_ATL_2024-25.json").exists():
        pytest.skip("No lineup JSON data available")

    art = section.build("ATL", as_of_recent)
    if art is None:
        pytest.skip("No artifact built for ATL")

    data, prov = art.to_profile_payload()
    assert "_cv_fields" in data, "to_profile_payload must embed _cv_fields in data"
    assert set(data["_cv_fields"].keys()) == {
        "lineup_spacing_mean", "transition_pace_cv",
        "closer_velocity", "rotation_fatigue_cv",
    }
    for slot_key, slot_val in data["_cv_fields"].items():
        assert slot_val["value"] is None, f"_cv_fields[{slot_key!r}]['value'] must be null"
    assert prov["confidence"] in ("low", "med", "high")


def test_build_and_register_dry_run() -> None:
    """build_and_register with dry_run=True returns a manifest without disk writes."""
    lineup_dir = _ROOT / "data" / "nba" / "lineups"
    if not any(lineup_dir.glob("lineup_splits_*_2024-25.json")):
        pytest.skip("No lineup JSON data available for dry-run test")

    as_of = _dt.datetime(2025, 6, 30, 0, 0, 0)
    manifest = build_and_register(
        team_tricodes=["ATL", "GSW"],
        as_of=as_of,
        dry_run=True,
    )
    assert "section" in manifest
    assert manifest["section"] == "rotation_patterns"
    assert "cv_fields" in manifest
    assert set(manifest["cv_fields"]) == {
        "lineup_spacing_mean", "transition_pace_cv",
        "closer_velocity", "rotation_fatigue_cv",
    }
