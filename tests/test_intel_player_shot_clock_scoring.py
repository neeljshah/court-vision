"""Tests for intel/player_shot_clock_scoring.py.

Covers:
  1. Leak-safety: build at an earlier as_of never returns more games than at current as_of.
  2. Schema conformance: required sub-field keys, proportions in [0,1], CV slots null.
  3. n >= 5 for Jokic (203999) and Curry (201939) with real data.
  4. Validator criteria 1-5 all pass for the two test players.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

# Ensure repo root is on path and NBA_OFFLINE set
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.player_shot_clock_scoring import (
    PlayerShotClockScoring,
    _adv_efficiency_for_player,
    _pbp_late_clock_for_player,
)
from src.loop.atlas import AtlasArtifact
from src.loop.intel_validator import validate as iv_validate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def section() -> PlayerShotClockScoring:
    return PlayerShotClockScoring()


@pytest.fixture(scope="module")
def as_of_full() -> _dt.datetime:
    """Current-season as_of (all data visible)."""
    return _dt.datetime(2026, 5, 30, 0, 0, 0)


@pytest.fixture(scope="module")
def as_of_early() -> _dt.datetime:
    """Early-season as_of: only games before 2023-01-01 visible."""
    return _dt.datetime(2023, 1, 1, 0, 0, 0)


@pytest.fixture(scope="module")
def jokic_artifact(section, as_of_full) -> Optional[AtlasArtifact]:
    return section.build(203999, as_of_full)


@pytest.fixture(scope="module")
def curry_artifact(section, as_of_full) -> Optional[AtlasArtifact]:
    return section.build(201939, as_of_full)


# ---------------------------------------------------------------------------
# Helper: count game rows in a build
# ---------------------------------------------------------------------------

def _n_from_artifact(art: Optional[AtlasArtifact]) -> int:
    if art is None:
        return 0
    return int(art.provenance.get("n", 0) or 0)


# ---------------------------------------------------------------------------
# 1. Leak-safety tests
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Rebuild at an earlier as_of must never return MORE games than the later build."""

    def test_jokic_earlier_as_of_not_more_games(self, section, as_of_full):
        """n at early as_of must be <= n at full as_of."""
        art_full = section.build(203999, as_of_full)
        art_early = section.build(203999, _dt.datetime(2023, 1, 1, 0, 0, 0))
        n_full = _n_from_artifact(art_full)
        n_early = _n_from_artifact(art_early)
        # Early should have fewer or equal games (never more)
        assert n_early <= n_full, (
            f"Leak: early as_of returned n={n_early} > n_full={n_full}"
        )

    def test_curry_earlier_as_of_not_more_games(self, section, as_of_full):
        """n at early as_of must be <= n at full as_of."""
        art_full = section.build(201939, as_of_full)
        art_early = section.build(201939, _dt.datetime(2023, 1, 1, 0, 0, 0))
        n_full = _n_from_artifact(art_full)
        n_early = _n_from_artifact(art_early)
        assert n_early <= n_full, (
            f"Leak: early as_of returned n={n_early} > n_full={n_full}"
        )

    def test_provenance_as_of_not_future(self, jokic_artifact, as_of_full):
        """Provenance as_of must not be strictly after the build as_of."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (missing data)")
        prov_as_of = jokic_artifact.provenance.get("as_of")
        if prov_as_of:
            assert prov_as_of <= as_of_full.date().isoformat(), (
                f"Provenance as_of={prov_as_of} is after build as_of={as_of_full.date()}"
            )

    def test_pbp_helper_respects_as_of_filter(self):
        """_pbp_late_clock_for_player returns fewer rows at an early as_of."""
        pid = 203999  # Jokic
        full = _pbp_late_clock_for_player(pid, _dt.datetime(2026, 5, 30))
        early = _pbp_late_clock_for_player(pid, _dt.datetime(2022, 10, 1))
        # Either early is empty (no data before cutoff) or has fewer games
        n_full = full.get("n_games", 0) or 0
        n_early = early.get("n_games", 0) or 0
        assert n_early <= n_full, (
            f"Leak in _pbp_late_clock_for_player: early n={n_early} > full n={n_full}"
        )

    def test_adv_helper_respects_as_of_filter(self):
        """_adv_efficiency_for_player returns fewer rows at an early as_of."""
        pid = 201939  # Curry
        full = _adv_efficiency_for_player(pid, _dt.datetime(2026, 5, 30))
        early = _adv_efficiency_for_player(pid, _dt.datetime(2022, 10, 1))
        n_full = full.get("n_games", 0) or 0
        n_early = early.get("n_games", 0) or 0
        assert n_early <= n_full, (
            f"Leak in _adv_efficiency_for_player: early n={n_early} > full n={n_full}"
        )


# ---------------------------------------------------------------------------
# 2. Schema conformance tests
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """All required sub-field keys present; proportions in [0,1]; CV slots null."""

    _REQUIRED_KEYS = {"early", "mid", "late", "shot_quality"}

    def test_jokic_required_sub_fields(self, jokic_artifact):
        """Jokic artifact must have all four required top-level sub-field keys."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        assert self._REQUIRED_KEYS.issubset(jokic_artifact.sub_fields.keys()), (
            f"Missing keys: {self._REQUIRED_KEYS - set(jokic_artifact.sub_fields.keys())}"
        )

    def test_curry_required_sub_fields(self, curry_artifact):
        """Curry artifact must have all four required top-level sub-field keys."""
        if curry_artifact is None:
            pytest.skip("Curry artifact not built")
        assert self._REQUIRED_KEYS.issubset(curry_artifact.sub_fields.keys())

    def test_efg_pct_in_range(self, jokic_artifact):
        """efg_pct must be in [0, 1.6] (validator ceiling for eFG)."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        v = jokic_artifact.sub_fields.get("shot_quality", {}).get("efg_pct")
        if v is not None:
            assert 0.0 <= v <= 1.6, f"efg_pct={v} out of [0, 1.6]"

    def test_ts_pct_in_range(self, curry_artifact):
        """ts_pct must be in [0, 1.6]."""
        if curry_artifact is None:
            pytest.skip("Curry artifact not built")
        v = curry_artifact.sub_fields.get("shot_quality", {}).get("ts_pct")
        if v is not None:
            assert 0.0 <= v <= 1.6, f"ts_pct={v} out of [0, 1.6]"

    def test_usage_pct_in_range(self, jokic_artifact):
        """usage_pct must be in [0, 1]."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        v = jokic_artifact.sub_fields.get("shot_quality", {}).get("usage_pct")
        if v is not None:
            assert 0.0 <= v <= 1.0, f"usage_pct={v} out of [0, 1]"

    def test_late_clock_rate_in_range(self, curry_artifact):
        """late_clock_rate must be in [0, 1] (it is a *_rate field)."""
        if curry_artifact is None:
            pytest.skip("Curry artifact not built")
        v = curry_artifact.sub_fields.get("late", {}).get("late_clock_rate")
        if v is not None:
            assert 0.0 <= v <= 1.0, f"late_clock_rate={v} out of [0, 1]"

    def test_shots_pg_non_negative(self, jokic_artifact):
        """shots_pg must be >= 0 (per-game count)."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        v = jokic_artifact.sub_fields.get("late", {}).get("shots_pg")
        if v is not None:
            assert v >= 0, f"shots_pg={v} is negative"

    def test_cv_slots_all_null(self, jokic_artifact):
        """All CV slots must have value=None (reserved for CV branch)."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        for name, slot in jokic_artifact.cv_fields.items():
            assert slot.value is None, f"CV slot {name}.value is not None: {slot.value}"

    def test_cv_slot_contest_by_clock_present(self, jokic_artifact):
        """The contest_by_clock CV slot must be declared."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        assert "contest_by_clock" in jokic_artifact.cv_fields, (
            "CV slot 'contest_by_clock' missing from artifact.cv_fields"
        )

    def test_cv_slot_dtype_valid(self, jokic_artifact):
        """contest_by_clock slot dtype must be a recognised CV dtype."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        slot = jokic_artifact.cv_fields.get("contest_by_clock")
        assert slot is not None
        from src.loop.intel_validator import _VALID_CV_DTYPES
        assert slot.dtype in _VALID_CV_DTYPES, (
            f"CV slot dtype '{slot.dtype}' not in {_VALID_CV_DTYPES}"
        )

    def test_section_name_and_entity(self, section):
        """Section metadata constants must be correct."""
        assert section.name == "shot_clock_scoring"
        assert section.entity == "player"


# ---------------------------------------------------------------------------
# 3. Coverage: n >= 5 for test players
# ---------------------------------------------------------------------------

class TestCoverage:
    """n must be >= 5 (the min_n gate in intel_validator) for Jokic and Curry."""

    def test_jokic_n_ge_5(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        n = _n_from_artifact(jokic_artifact)
        assert n >= 5, f"Jokic n={n} fails min_n=5 gate"

    def test_curry_n_ge_5(self, curry_artifact):
        if curry_artifact is None:
            pytest.skip("Curry artifact not built")
        n = _n_from_artifact(curry_artifact)
        assert n >= 5, f"Curry n={n} fails min_n=5 gate"

    def test_jokic_n_is_game_count_not_seasons(self, jokic_artifact):
        """n must reflect real per-game rows, not a season count (which would be 1-2)."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        n = _n_from_artifact(jokic_artifact)
        assert n > 2, (
            f"n={n} looks like a season count, not a game count. "
            "CRITICAL LESSON: n must come from len(game_rows), never n_seasons."
        )

    def test_curry_n_is_game_count_not_seasons(self, curry_artifact):
        if curry_artifact is None:
            pytest.skip("Curry artifact not built")
        n = _n_from_artifact(curry_artifact)
        assert n > 2, (
            f"n={n} looks like a season count, not a game count."
        )


# ---------------------------------------------------------------------------
# 4. Full validator pass (criteria 1-5)
# ---------------------------------------------------------------------------

class TestFullValidation:
    """intel_validator.validate must return ok=True for both test players."""

    def test_jokic_full_validation(self, section, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        result = iv_validate(section, jokic_artifact, min_n=5, dedup_threshold=0.97)
        assert result.ok, (
            f"Jokic validation failed: {result.reasons}"
        )

    def test_curry_full_validation(self, section, curry_artifact):
        if curry_artifact is None:
            pytest.skip("Curry artifact not built")
        result = iv_validate(section, curry_artifact, min_n=5, dedup_threshold=0.97)
        assert result.ok, (
            f"Curry validation failed: {result.reasons}"
        )

    def test_jokic_leak_free(self, section, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        result = iv_validate(section, jokic_artifact, min_n=5)
        assert result.leak_free, f"Jokic leak_free failed: {result.reasons}"

    def test_jokic_face_valid(self, section, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        result = iv_validate(section, jokic_artifact, min_n=5)
        assert result.face_valid, f"Jokic face_valid failed: {result.reasons}"

    def test_jokic_cv_schema_ok(self, section, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        result = iv_validate(section, jokic_artifact, min_n=5)
        assert result.cv_schema_ok, f"Jokic cv_schema_ok failed: {result.reasons}"

    def test_section_validate_method(self, section, jokic_artifact):
        """section.validate() (cheap self-check) must return True."""
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        assert section.validate(jokic_artifact)

    def test_unknown_player_returns_none(self, section, as_of_full):
        """build() must return None for an unknown player_id, not raise."""
        art = section.build(9999999, as_of_full)
        assert art is None
