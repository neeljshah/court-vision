"""Tests for intel/team_transition_halfcourt_splits.py.

Covers:
  1. Leak-safety assertion: build() must never return a record stamped after as_of.
  2. Schema-conformance assertion: artifact contains all required sub-field keys,
     cv_fields are present with value=None, and validate() passes.
  3. Edge-case: build() returns None for an unknown team (graceful fallback).
  4. Bridge dry-run: register_section in dry_run mode returns a valid manifest.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

# Ensure repo root is on the path
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from intel.team_transition_halfcourt_splits import (
    TeamTransitionHalfcourtSplits,
    build_and_register,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NBA_TEAMS = [
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
]

_PAST = _dt.datetime(2026, 1, 1, 0, 0, 0)   # safely in the past for leak tests
_FUTURE = _dt.datetime(2099, 1, 1, 0, 0, 0)  # far future — gets all data


def _get_any_artifact() -> AtlasArtifact:
    """Return the first non-None artifact found across all 30 teams."""
    section = TeamTransitionHalfcourtSplits()
    for tri in _NBA_TEAMS:
        art = section.build(tri, _FUTURE)
        if art is not None:
            return art
    pytest.skip("No team data found — parquets absent in this environment.")


# ---------------------------------------------------------------------------
# 1. Leak-safety: artifact.as_of must never exceed the requested as_of boundary
# ---------------------------------------------------------------------------

class TestLeakSafety:
    def test_as_of_never_after_boundary(self) -> None:
        """Build with a strict past as_of; artifact as_of must be <= that date."""
        section = TeamTransitionHalfcourtSplits()
        boundary_str = _PAST.date().isoformat()  # "2026-01-01"
        for tri in _NBA_TEAMS[:5]:  # test 5 teams for speed
            art = section.build(tri, _PAST)
            if art is None:
                continue  # no data at that cutoff — fine
            assert art.as_of is not None, f"{tri}: artifact.as_of should be set"
            assert art.as_of <= boundary_str, (
                f"{tri}: artifact.as_of={art.as_of!r} is after boundary {boundary_str!r} "
                "(LEAK)"
            )

    def test_future_boundary_allows_data(self) -> None:
        """With a far-future as_of, at least one team should have data."""
        section = TeamTransitionHalfcourtSplits()
        found_any = False
        for tri in _NBA_TEAMS:
            art = section.build(tri, _FUTURE)
            if art is not None:
                found_any = True
                break
        assert found_any, (
            "No artifact built for any team with far-future as_of — "
            "check that parquets exist in data/ and data/intelligence/"
        )


# ---------------------------------------------------------------------------
# 2. Schema conformance: required sub-field keys, cv_fields present + null
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    _REQUIRED_SUBFIELDS = {
        "pace",
        "tempo_z",
        "cv_pace",
        "pbp_possession_mix",
        "transition_pts_per_possession",
        "halfcourt_ppp",
        "early_offense_share",
    }
    _REQUIRED_CV_SLOTS = {"transition_velocity_mean", "halfcourt_setup_duration"}

    def test_required_subfield_keys_present(self) -> None:
        """artifact.sub_fields must contain all documented required keys."""
        art = _get_any_artifact()
        missing = self._REQUIRED_SUBFIELDS - set(art.sub_fields.keys())
        assert not missing, f"sub_fields missing keys: {missing}"

    def test_cv_fields_present_and_null(self) -> None:
        """cv_fields() must return all reserved slots with value=None."""
        section = TeamTransitionHalfcourtSplits()
        slots = section.cv_fields()
        assert set(slots.keys()) == self._REQUIRED_CV_SLOTS, (
            f"cv_fields keys mismatch: got {set(slots.keys())}, "
            f"expected {self._REQUIRED_CV_SLOTS}"
        )
        for slot_name, slot in slots.items():
            assert isinstance(slot, CVSlot), (
                f"cv_fields[{slot_name!r}] must be a CVSlot instance"
            )
            assert slot.value is None, (
                f"cv_fields[{slot_name!r}].value must be None (CV branch not yet run)"
            )

    def test_artifact_cv_fields_null(self) -> None:
        """All cv_fields on a built artifact must have value=None."""
        art = _get_any_artifact()
        for slot_name, slot in art.cv_fields.items():
            assert slot.value is None, (
                f"artifact.cv_fields[{slot_name!r}].value={slot.value!r} should be None"
            )

    def test_validate_passes(self) -> None:
        """section.validate(artifact) must return True for a well-formed artifact."""
        section = TeamTransitionHalfcourtSplits()
        art = _get_any_artifact()
        assert section.validate(art), (
            f"validate() returned False for artifact of team={art.entity_id!r}. "
            f"sub_fields keys: {list(art.sub_fields.keys())}"
        )

    def test_section_and_entity_attrs(self) -> None:
        """The AtlasSection must declare correct section name and entity type."""
        section = TeamTransitionHalfcourtSplits()
        assert section.name == "transition_halfcourt_splits"
        assert section.entity == "team"

    def test_provenance_fields(self) -> None:
        """artifact.provenance must contain source, n, confidence, as_of."""
        art = _get_any_artifact()
        for key in ("source", "n", "confidence", "as_of"):
            assert key in art.provenance, f"provenance missing key: {key!r}"
        assert art.provenance["n"] >= 1
        assert art.provenance["confidence"] in ("low", "med", "high")

    def test_defer_subfields_have_note(self) -> None:
        """DEFER sub-fields must contain a '_note' key documenting the gap."""
        art = _get_any_artifact()
        for defer_key in ("transition_pts_per_possession", "halfcourt_ppp", "early_offense_share"):
            val = art.sub_fields.get(defer_key, {})
            assert isinstance(val, dict), f"{defer_key} should be a dict"
            assert "_note" in val, f"{defer_key} missing '_note' key (DEFER documentation)"


# ---------------------------------------------------------------------------
# 3. Unknown team returns None gracefully
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unknown_team_returns_none(self) -> None:
        """build() for a team not in any source must return None, not raise."""
        section = TeamTransitionHalfcourtSplits()
        art = section.build("ZZZ", _FUTURE)
        assert art is None, "Expected None for unknown team tricode"

    def test_empty_tricode_returns_none(self) -> None:
        """build() for empty string tricode must return None."""
        section = TeamTransitionHalfcourtSplits()
        art = section.build("", _FUTURE)
        assert art is None


# ---------------------------------------------------------------------------
# 4. Bridge dry-run: register_section returns a valid manifest
# ---------------------------------------------------------------------------

class TestBridgeDryRun:
    def test_dry_run_manifest_schema(self) -> None:
        """build_and_register(dry_run=True) must return a well-formed manifest dict."""
        manifest = build_and_register(
            team_tricodes=_NBA_TEAMS[:2],
            as_of=_FUTURE,
            store=None,
            dry_run=True,
        )
        assert isinstance(manifest, dict)
        assert manifest.get("section") == "transition_halfcourt_splits"
        assert "parquet" in manifest
        assert "sec_fn" in manifest
        assert manifest.get("sec_fn") == "sec_transition_halfcourt_splits"
        cv_field_keys = set(manifest.get("cv_fields", []))
        assert "transition_velocity_mean" in cv_field_keys
        assert "halfcourt_setup_duration" in cv_field_keys
