"""Tests for intel/player_post_up_profile.py.

Covers:
  - Schema conformance: required sub-field keys present, CV slots null + typed.
  - Leak-safety: build at an earlier as_of must not see later-game data.
  - Range validity: post_up_freq_pct in [0,1], post_up_pg >= 0, ppp >= 0.
  - Provenance n reflects actual game rows (not a constant like n_seasons).
  - validate() rejects artifacts with out-of-range or missing required fields.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure repo root is on sys.path (NBA_OFFLINE=1 avoids live API calls)
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import os
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.player_post_up_profile import PlayerPostUpProfile
from src.loop.atlas import AtlasArtifact, CVSlot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SECTION = PlayerPostUpProfile()
AS_OF = _dt.datetime(2026, 5, 31, 0, 0, 0)
AS_OF_EARLY = _dt.datetime(2023, 1, 1, 0, 0, 0)  # far-past leak test

# Two well-known player IDs
JOKIC_ID = 203999
CURRY_ID = 201939


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_artifact(
    sub_fields: Dict[str, Any] | None = None,
    n: int = 10,
    cv_fields: Dict[str, CVSlot] | None = None,
) -> AtlasArtifact:
    """Build a minimal artifact for validate() unit tests."""
    if sub_fields is None:
        sub_fields = {
            "post_up_freq_pct": 0.10,
            "post_up_ppp": 0.95,
            "post_up_pg": 2.5,
            "n_games": n,
            "kick_out_rate": None,
            "deep_seal_pct": None,
        }
    if cv_fields is None:
        cv_fields = SECTION.cv_fields()
    return AtlasArtifact(
        section="post_up_profile",
        entity="player",
        entity_id=JOKIC_ID,
        sub_fields=sub_fields,
        provenance={"source": "test", "n": n, "confidence": "med", "as_of": "2026-05-31"},
        confidence="med",
        as_of="2026-05-31",
        cv_fields=cv_fields,
    )


# ---------------------------------------------------------------------------
# 1. Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """The built artifact must have all required keys and typed CV slots."""

    def test_required_sub_field_keys_present(self) -> None:
        art = SECTION.build(JOKIC_ID, AS_OF)
        if art is None:
            pytest.skip("No source data for Jokic in this environment")
        required = {
            "post_up_freq_pct", "post_up_ppp", "post_up_pg",
            "n_games", "kick_out_rate", "deep_seal_pct",
        }
        assert required.issubset(art.sub_fields.keys()), (
            f"Missing keys: {required - art.sub_fields.keys()}"
        )

    def test_cv_slots_present_and_null(self) -> None:
        art = SECTION.build(JOKIC_ID, AS_OF)
        if art is None:
            pytest.skip("No source data for Jokic in this environment")
        assert "seal_depth" in art.cv_fields, "seal_depth CV slot missing"
        assert "double_team_drawn" in art.cv_fields, "double_team_drawn CV slot missing"
        for name, slot in art.cv_fields.items():
            assert slot.value is None, f"CV slot {name} should be null until CV fills it"

    def test_cv_slots_typed(self) -> None:
        declared = SECTION.cv_fields()
        valid_dtypes = {"float", "dist", "list", "categorical", "int"}
        for name, slot in declared.items():
            assert slot.dtype in valid_dtypes, (
                f"CV slot {name} has unrecognised dtype {slot.dtype!r}"
            )

    def test_section_and_entity_names(self) -> None:
        assert SECTION.name == "post_up_profile"
        assert SECTION.entity == "player"

    def test_validate_passes_minimal_valid_artifact(self) -> None:
        art = _make_minimal_artifact()
        assert SECTION.validate(art), "validate() should pass a well-formed artifact"

    def test_validate_rejects_wrong_section_name(self) -> None:
        art = _make_minimal_artifact()
        art.section = "wrong_section"
        assert not SECTION.validate(art)

    def test_validate_rejects_missing_required_key(self) -> None:
        sf = {
            "post_up_freq_pct": 0.10,
            "post_up_ppp": 0.95,
            # post_up_pg is missing
            "n_games": 10,
            "kick_out_rate": None,
            "deep_seal_pct": None,
        }
        art = _make_minimal_artifact(sub_fields=sf)
        assert not SECTION.validate(art)


# ---------------------------------------------------------------------------
# 2. Range validity
# ---------------------------------------------------------------------------

class TestRangeValidity:
    """Proportions and rates must be in sane ranges."""

    def test_post_up_freq_pct_in_unit_interval(self) -> None:
        art = SECTION.build(JOKIC_ID, AS_OF)
        if art is None:
            pytest.skip("No source data")
        freq = art.sub_fields.get("post_up_freq_pct")
        if freq is not None:
            assert 0.0 <= freq <= 1.0, f"freq_pct={freq} outside [0,1]"

    def test_post_up_ppp_non_negative(self) -> None:
        art = SECTION.build(JOKIC_ID, AS_OF)
        if art is None:
            pytest.skip("No source data")
        ppp = art.sub_fields.get("post_up_ppp")
        if ppp is not None:
            assert ppp >= 0.0, f"ppp={ppp} is negative"

    def test_post_up_pg_non_negative(self) -> None:
        art = SECTION.build(JOKIC_ID, AS_OF)
        if art is None:
            pytest.skip("No source data")
        pg = art.sub_fields.get("post_up_pg")
        if pg is not None:
            assert pg >= 0.0, f"post_up_pg={pg} is negative"

    def test_validate_rejects_freq_pct_above_one(self) -> None:
        sf = {
            "post_up_freq_pct": 1.5,  # out of range
            "post_up_ppp": 0.95,
            "post_up_pg": 2.5,
            "n_games": 10,
            "kick_out_rate": None,
            "deep_seal_pct": None,
        }
        art = _make_minimal_artifact(sub_fields=sf)
        assert not SECTION.validate(art), "validate() must reject freq_pct > 1"

    def test_validate_rejects_negative_post_up_pg(self) -> None:
        sf = {
            "post_up_freq_pct": 0.10,
            "post_up_ppp": 0.95,
            "post_up_pg": -1.0,  # invalid
            "n_games": 10,
            "kick_out_rate": None,
            "deep_seal_pct": None,
        }
        art = _make_minimal_artifact(sub_fields=sf)
        assert not SECTION.validate(art), "validate() must reject negative post_up_pg"

    def test_validate_rejects_non_null_cv_slot(self) -> None:
        cv = SECTION.cv_fields()
        cv["seal_depth"].value = 5.0  # CV branch has not run yet
        art = _make_minimal_artifact(cv_fields=cv)
        assert not SECTION.validate(art), "validate() must reject non-null CV slot"


# ---------------------------------------------------------------------------
# 3. Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Provenance n must come from actual game rows filtered by as_of."""

    def test_n_uses_actual_game_count_not_seasons(self) -> None:
        art = SECTION.build(JOKIC_ID, AS_OF)
        if art is None:
            pytest.skip("No source data")
        n = art.provenance.get("n", 0)
        # Jokic has 100+ games across multiple seasons; n must not be 1 or 2 (season count)
        assert n >= 5, (
            f"n={n} looks like a season count, not a real game count. "
            "Set n from pbp_possession_features row count, not n_seasons."
        )

    def test_early_as_of_has_fewer_games(self) -> None:
        """An earlier as_of should produce a lower or equal n (never higher)."""
        art_now = SECTION.build(JOKIC_ID, AS_OF)
        art_early = SECTION.build(JOKIC_ID, AS_OF_EARLY)
        if art_now is None or art_early is None:
            pytest.skip("Insufficient data for both as_of dates")
        n_now = art_now.provenance.get("n", 0)
        n_early = art_early.provenance.get("n", 0)
        assert n_early <= n_now, (
            f"Early as_of ({AS_OF_EARLY.date()}) gave n={n_early} > "
            f"current n={n_now}. Possible leak: future games visible at past as_of."
        )

    def test_as_of_stamped_on_artifact(self) -> None:
        art = SECTION.build(JOKIC_ID, AS_OF)
        if art is None:
            pytest.skip("No source data")
        assert art.as_of is not None, "artifact.as_of must be set"
        assert art.provenance.get("as_of") is not None, "provenance as_of must be set"
        # provenance as_of must not be after the build as_of
        from src.loop.intel_validator import _to_date
        prov_d = _to_date(art.provenance["as_of"])
        art_d = _to_date(art.as_of)
        assert prov_d is not None and art_d is not None
        assert prov_d <= art_d, (
            "provenance as_of is after artifact as_of -- indicates a leak boundary issue"
        )


# ---------------------------------------------------------------------------
# 4. Provenance n >= 5 for active post-up players
# ---------------------------------------------------------------------------

class TestCoverage:
    """Active post-up players (Jokic) should reach min_n=5 for the med confidence gate."""

    def test_jokic_n_ge_5(self) -> None:
        art = SECTION.build(JOKIC_ID, AS_OF)
        if art is None:
            pytest.skip("No source data for Jokic")
        n = art.provenance.get("n", 0)
        assert n >= 5, (
            f"Jokic provenance n={n} < 5; artifact will fail the validator coverage gate. "
            "Ensure n comes from pbp_possession_features row count."
        )

    def test_curry_build_returns_artifact_or_none(self) -> None:
        """Curry rarely posts up but build() must not raise."""
        try:
            art = SECTION.build(CURRY_ID, AS_OF)
            # If an artifact is returned, validate it
            if art is not None:
                assert SECTION.validate(art), "Curry artifact failed self-validation"
        except Exception as exc:
            pytest.fail(f"build() raised for Curry: {exc!r}")
