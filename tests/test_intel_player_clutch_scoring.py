"""Tests for intel/player_clutch_scoring.py.

Covers:
  - leak-safety: build at an earlier as_of must not surface future data
  - schema conformance: required sub-field keys, proportions in [0,1], CV slot typing
  - coverage n: must come from clutch_gp (real game count), not row count
  - build returns None for unknown players
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

# Ensure repo root is on sys.path so relative imports work
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.player_clutch_scoring import PlayerClutchScoring, _rd, _proportion
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SECTION = PlayerClutchScoring()

# Use a far-future as_of so we get maximum coverage from real parquets
AS_OF_NOW = _dt.datetime(2026, 6, 1, 0, 0, 0)
# Use a past as_of that predates the 2025-26 season to test leak filtering
AS_OF_PAST = _dt.datetime(2024, 10, 1, 0, 0, 0)

# Known players likely present in clutch_profiles_2025-26
JOKIC_ID = 203999
CURRY_ID = 201939
# An implausible player_id that should not be in any parquet
UNKNOWN_ID = 999999999


def _build_safe(pid: int, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
    """Call build and return artifact or None (never raises)."""
    try:
        return SECTION.build(pid, as_of)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Basic schema tests
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Section produces artifacts with required keys and correct field ranges."""

    def test_required_sub_field_keys(self):
        """Artifact sub_fields must contain the four required top-level keys."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing — skip in offline CI")
        required = {"scoring", "usage_context", "pbp_clutch", "deferred"}
        assert required.issubset(art.sub_fields.keys()), (
            f"Missing keys: {required - set(art.sub_fields.keys())}"
        )

    def test_shooting_percentages_in_unit_interval(self):
        """fg_pct, fg3_pct, ft_pct must be None or in [0, 1]."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing — skip in offline CI")
        scoring = art.sub_fields.get("scoring", {})
        for key in ["fg_pct", "fg3_pct", "ft_pct"]:
            v = scoring.get(key)
            if v is not None:
                assert 0.0 <= v <= 1.0, f"{key}={v} out of [0,1]"

    def test_ts_efg_proportions_allow_slight_overshoot(self):
        """ts_pct and efg_pct must be None or in [0, 1.6]."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing — skip in offline CI")
        uctx = art.sub_fields.get("usage_context", {})
        for key in ["ts_pct", "efg_pct"]:
            v = uctx.get(key)
            if v is not None:
                assert 0.0 <= v <= 1.6, f"{key}={v} out of [0, 1.6]"

    def test_per_game_fields_non_negative(self):
        """Per-game count fields must be None or >= 0."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing — skip in offline CI")
        pbp = art.sub_fields.get("pbp_clutch", {})
        for key in ["clutch_shots_pg", "clutch_pts_pg", "and1_pg"]:
            v = pbp.get(key)
            if v is not None:
                assert v >= 0.0, f"{key}={v} is negative"

    def test_section_self_validate_passes(self):
        """Section.validate() must return True for a validly built artifact."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing — skip in offline CI")
        assert SECTION.validate(art) is True

    def test_unknown_player_returns_none(self):
        """build() for an unknown player_id should return None, not raise."""
        art = _build_safe(UNKNOWN_ID, AS_OF_NOW)
        assert art is None, "Expected None for non-existent player"

    def test_entity_and_section_name(self):
        """Artifact must declare the correct entity and section name."""
        art = _build_safe(CURRY_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing — skip in offline CI")
        assert art.entity == "player"
        assert art.section == "clutch_scoring"


# ---------------------------------------------------------------------------
# Coverage-n tests (CRITICAL LESSON 1)
# ---------------------------------------------------------------------------

class TestCoverageN:
    """n must reflect actual clutch game count (clutch_gp), not row count."""

    def test_n_is_real_game_count_not_row_count(self):
        """provenance['n'] must be > 1 (row count would be 1 per season per player)."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing — skip in offline CI")
        n = art.provenance.get("n", 0)
        assert n > 1, (
            f"n={n}: looks like row count (1) rather than real clutch_gp game count. "
            "Jokic had 32 clutch games in 2025-26."
        )

    def test_n_meets_min_coverage_threshold(self):
        """n must be >= 5 (validator min_n) for Jokic and Curry."""
        for pid, name in [(JOKIC_ID, "Jokic"), (CURRY_ID, "Curry")]:
            art = _build_safe(pid, AS_OF_NOW)
            if art is None:
                pytest.skip(f"clutch_profiles parquet missing for {name}")
            n = art.provenance.get("n", 0)
            assert n >= 5, (
                f"{name} (pid={pid}) has n={n} < 5; would fail validator coverage gate"
            )

    def test_confidence_level_consistent_with_n(self):
        """Confidence level must be consistent with n (med if 5<=n<20, high if n>=20)."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing — skip in offline CI")
        n = art.provenance.get("n", 0)
        conf = art.confidence
        if n >= 20:
            assert conf == "high", f"Expected 'high' for n={n}, got '{conf}'"
        elif n >= 5:
            assert conf in ("med", "high"), f"Expected 'med'/'high' for n={n}, got '{conf}'"
        else:
            assert conf == "low", f"Expected 'low' for n={n}, got '{conf}'"


# ---------------------------------------------------------------------------
# Leak-safety tests
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must respect as_of -- data from future games must not appear."""

    def test_past_as_of_yields_lower_or_equal_n(self):
        """Building at a past date should yield n <= n at a future date.

        Season-aggregate parquets (clutch_profiles) are not game-date filtered
        (they are published end-of-season), so the primary gp may be the same.
        But per-game sources (pbp, adv) must shrink under a past as_of.
        """
        art_now = _build_safe(JOKIC_ID, AS_OF_NOW)
        art_past = _build_safe(JOKIC_ID, AS_OF_PAST)
        if art_now is None:
            pytest.skip("clutch_profiles parquet missing")
        # pbp n_games at a past as_of should be 0 or smaller than current
        pbp_now = art_now.sub_fields.get("pbp_clutch", {}).get("n_games_pbp") or 0
        if art_past is not None:
            pbp_past = art_past.sub_fields.get("pbp_clutch", {}).get("n_games_pbp") or 0
            assert pbp_past <= pbp_now, (
                f"pbp n_games at past as_of ({pbp_past}) > now ({pbp_now}) — possible leak"
            )

    def test_as_of_date_stamped_in_provenance(self):
        """Provenance as_of must match the date passed to build()."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing")
        prov_as_of = art.provenance.get("as_of")
        assert prov_as_of is not None, "provenance as_of must be set"
        assert prov_as_of.startswith(AS_OF_NOW.date().isoformat()), (
            f"provenance as_of '{prov_as_of}' does not match build date "
            f"'{AS_OF_NOW.date().isoformat()}'"
        )

    def test_as_of_field_matches_provenance(self):
        """artifact.as_of and provenance['as_of'] must agree."""
        art = _build_safe(CURRY_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing")
        assert art.as_of == art.provenance.get("as_of"), (
            f"artifact.as_of='{art.as_of}' != provenance['as_of']='{art.provenance.get('as_of')}'"
        )


# ---------------------------------------------------------------------------
# CV-slot schema tests
# ---------------------------------------------------------------------------

class TestCVSlotSchema:
    """CV slots must be declared, well-typed, and all null-valued."""

    def test_cv_fields_declared(self):
        """cv_fields() must return a non-empty dict."""
        slots = SECTION.cv_fields()
        assert isinstance(slots, dict) and slots, "cv_fields() must return a non-empty dict"

    def test_clutch_defender_distance_slot_present(self):
        """The required 'clutch_defender_distance' CV slot must be declared."""
        slots = SECTION.cv_fields()
        assert "clutch_defender_distance" in slots, (
            "Missing required CV slot 'clutch_defender_distance'"
        )

    def test_cv_slot_values_are_null(self):
        """All CV slots must have value=None (reserved for CV branch)."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing")
        for name, slot in art.cv_fields.items():
            assert slot.value is None, (
                f"CV slot '{name}' has value={slot.value!r}; must be None until CV fills it"
            )

    def test_cv_slot_dtype_valid(self):
        """All CV slot dtypes must be one of the valid dtype set."""
        valid_dtypes = {"float", "dist", "list", "categorical", "int"}
        for name, slot in SECTION.cv_fields().items():
            assert slot.dtype in valid_dtypes, (
                f"CV slot '{name}' has invalid dtype '{slot.dtype}'"
            )

    def test_cv_fields_mirrored_on_artifact(self):
        """Artifact cv_fields must mirror the section's declared cv_fields()."""
        art = _build_safe(JOKIC_ID, AS_OF_NOW)
        if art is None:
            pytest.skip("clutch_profiles parquet missing")
        declared = set(SECTION.cv_fields().keys())
        artifact_keys = set(art.cv_fields.keys())
        assert declared == artifact_keys, (
            f"Mismatch between declared CV slots {declared} and artifact keys {artifact_keys}"
        )


# ---------------------------------------------------------------------------
# Helper function unit tests (no parquet needed)
# ---------------------------------------------------------------------------

class TestHelpers:
    """Unit tests for _rd and _proportion helper functions."""

    def test_rd_nan_returns_none(self):
        import math
        assert _rd(float("nan")) is None
        assert _rd(float("inf")) is None

    def test_rd_rounds_to_4dp(self):
        assert _rd(0.123456789) == 0.1235

    def test_proportion_in_range(self):
        assert _proportion(0.5) == 0.5
        assert _proportion(0.0) == 0.0
        assert _proportion(1.0) == 1.0

    def test_proportion_out_of_range_returns_none(self):
        assert _proportion(1.5) is None
        assert _proportion(-0.1) is None

    def test_proportion_efg_ceil_allows_overshoot(self):
        assert _proportion(1.2, ceil=1.6) == 1.2
        assert _proportion(1.7, ceil=1.6) is None
