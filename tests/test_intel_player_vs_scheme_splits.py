"""Tests for intel/player_vs_scheme_splits.py.

Checks:
  1. Leak-safety: build at an earlier as_of never includes future games.
  2. Schema conformance: required keys, pct ranges, CV-slot schema.
  3. Face-validity: pct fields in [0, ceil], per-game rates non-negative.
  4. n is actual game count (not season count).
  5. Signed difference field name ends with _minus_ (exempt from pct rule).
  6. CV slots are null-valued and correctly typed.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure repo root on path for local imports
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from intel.player_vs_scheme_splits import PlayerVsSchemeSplits, _build_per_game_frame
from src.loop.atlas import AtlasArtifact
from src.loop.intel_validator import check_face_validity, check_cv_schema, check_coverage

# Known test players with substantial game histories.
JOKIC_ID = 203999   # Nikola Jokic
CURRY_ID = 201939   # Stephen Curry

# Use a fixed as_of well within the data range.
AS_OF_FULL = _dt.datetime(2026, 5, 30, 0, 0, 0)
# An earlier cut-off to test leak safety.
AS_OF_EARLY = _dt.datetime(2023, 12, 31, 0, 0, 0)


@pytest.fixture(scope="module")
def section() -> PlayerVsSchemeSplits:
    return PlayerVsSchemeSplits()


@pytest.fixture(scope="module")
def jokic_artifact(section):
    art = section.build(JOKIC_ID, AS_OF_FULL)
    if art is None:
        pytest.skip("Jokic artifact is None — source data unavailable in this environment.")
    return art


@pytest.fixture(scope="module")
def curry_artifact(section):
    art = section.build(CURRY_ID, AS_OF_FULL)
    if art is None:
        pytest.skip("Curry artifact is None — source data unavailable in this environment.")
    return art


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """The artifact contains all required keys and correct section/entity labels."""

    def test_section_and_entity_labels(self, jokic_artifact):
        assert jokic_artifact.section == "vs_scheme_splits"
        assert jokic_artifact.entity == "player"
        assert jokic_artifact.entity_id == JOKIC_ID

    def test_required_top_level_keys(self, jokic_artifact):
        sf = jokic_artifact.sub_fields
        required = {
            "by_scheme", "best_scheme", "worst_scheme",
            "scheme_ts_pct_best_minus_worst", "n_games_total",
        }
        assert required.issubset(sf.keys()), (
            f"Missing keys: {required - sf.keys()}"
        )

    def test_by_scheme_is_nonempty_dict(self, jokic_artifact):
        by_scheme = jokic_artifact.sub_fields["by_scheme"]
        assert isinstance(by_scheme, dict)
        assert len(by_scheme) >= 1, "Expected at least one scheme entry."

    def test_scheme_entry_has_required_keys(self, jokic_artifact):
        required = {
            "tag", "n_games", "ts_pct", "efg_pct", "usage_pct",
            "pts_pg", "reb_pg", "ast_pg", "fg3m_pg",
            "stl_pg", "blk_pg", "tov_pg",
        }
        for tag_key, entry in jokic_artifact.sub_fields["by_scheme"].items():
            assert required.issubset(entry.keys()), (
                f"Scheme entry '{tag_key}' missing keys: {required - entry.keys()}"
            )

    def test_signed_diff_field_ends_with_minus(self, jokic_artifact):
        """scheme_ts_spread must use _minus_ suffix so the validator exempts it."""
        sf = jokic_artifact.sub_fields
        assert "scheme_ts_pct_best_minus_worst" in sf, (
            "Signed difference field must end with _minus_ for validator exemption."
        )


# ---------------------------------------------------------------------------
# Face-validity (pct/rate ranges)
# ---------------------------------------------------------------------------

class TestFaceValidity:
    """Pct fields in [0, ceil]; per-game rates non-negative; validator passes."""

    def test_ts_pct_in_range(self, jokic_artifact):
        for tag_key, entry in jokic_artifact.sub_fields["by_scheme"].items():
            v = entry.get("ts_pct")
            if v is not None:
                assert 0.0 <= v <= 1.6, f"ts_pct={v} out of [0,1.6] in {tag_key}"

    def test_efg_pct_in_range(self, jokic_artifact):
        for tag_key, entry in jokic_artifact.sub_fields["by_scheme"].items():
            v = entry.get("efg_pct")
            if v is not None:
                assert 0.0 <= v <= 1.6, f"efg_pct={v} out of [0,1.6] in {tag_key}"

    def test_usage_pct_in_range(self, jokic_artifact):
        for tag_key, entry in jokic_artifact.sub_fields["by_scheme"].items():
            v = entry.get("usage_pct")
            if v is not None:
                assert 0.0 <= v <= 1.0, f"usage_pct={v} out of [0,1] in {tag_key}"

    def test_per_game_rates_nonnegative(self, jokic_artifact):
        stat_keys = ["pts_pg", "reb_pg", "ast_pg", "fg3m_pg",
                     "stl_pg", "blk_pg", "tov_pg"]
        for tag_key, entry in jokic_artifact.sub_fields["by_scheme"].items():
            for k in stat_keys:
                v = entry.get(k)
                if v is not None:
                    assert v >= 0.0, f"{k}={v} is negative in scheme {tag_key}"

    def test_intel_validator_face_validity_passes(self, section, jokic_artifact):
        reasons = check_face_validity(jokic_artifact)
        assert reasons == [], f"Face-validity failures: {reasons}"


# ---------------------------------------------------------------------------
# Coverage (n = actual game count)
# ---------------------------------------------------------------------------

class TestCoverage:
    """n must be actual games played (>= 5 to pass the coverage gate)."""

    def test_n_is_large_enough_jokic(self, jokic_artifact):
        n = jokic_artifact.provenance["n"]
        assert n >= 5, f"Jokic n={n} is below min_n=5; n must be actual game count."

    def test_n_is_large_enough_curry(self, curry_artifact):
        n = curry_artifact.provenance["n"]
        assert n >= 5, f"Curry n={n} is below min_n=5; n must be actual game count."

    def test_n_equals_n_games_total(self, jokic_artifact):
        n_prov = jokic_artifact.provenance["n"]
        n_sf = jokic_artifact.sub_fields.get("n_games_total")
        assert n_prov == n_sf, (
            f"Provenance n={n_prov} != sub_fields.n_games_total={n_sf}"
        )

    def test_n_is_not_season_count(self, jokic_artifact):
        """n must be much larger than the number of seasons (1-3), never 1 or 2."""
        n = jokic_artifact.provenance["n"]
        assert n > 5, (
            f"n={n} looks like a season count (1-5), not an actual game count. "
            "CRITICAL LESSON 1: n MUST be set from len(game rows), not n_seasons."
        )

    def test_coverage_gate_passes(self, section, jokic_artifact):
        assert check_coverage(jokic_artifact, min_n=5), (
            f"Coverage gate failed: n={jokic_artifact.provenance['n']} < 5"
        )


# ---------------------------------------------------------------------------
# CV-slot schema
# ---------------------------------------------------------------------------

class TestCVSlotSchema:
    """cv_fields present, well-typed, all values None (reserved for CV branch)."""

    def test_cv_fields_present(self, section, jokic_artifact):
        declared = section.cv_fields()
        assert "contest_vs_scheme" in declared
        assert "contest_vs_scheme" in jokic_artifact.cv_fields

    def test_cv_slot_dtype_valid(self, section):
        for name, slot in section.cv_fields().items():
            assert slot.dtype in {"float", "dist", "list", "categorical", "int"}, (
                f"CV slot '{name}' has invalid dtype '{slot.dtype}'"
            )

    def test_cv_slot_values_null(self, jokic_artifact):
        for name, slot in jokic_artifact.cv_fields.items():
            assert slot.value is None, (
                f"CV slot '{name}' has non-null value={slot.value}; "
                "CV branch has not run yet — values must be reserved as None."
            )

    def test_intel_validator_cv_schema_passes(self, section, jokic_artifact):
        assert check_cv_schema(section, jokic_artifact), (
            "intel_validator.check_cv_schema failed for Jokic artifact."
        )


# ---------------------------------------------------------------------------
# Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() at an earlier as_of must not include games from after that date."""

    def test_early_as_of_yields_fewer_or_equal_games(self, section):
        art_full = section.build(JOKIC_ID, AS_OF_FULL)
        art_early = section.build(JOKIC_ID, AS_OF_EARLY)
        if art_full is None or art_early is None:
            pytest.skip("One artifact is None — cannot compare.")
        n_full = art_full.provenance["n"]
        n_early = art_early.provenance["n"]
        assert n_early <= n_full, (
            f"Early as_of has MORE games ({n_early}) than full as_of ({n_full}); "
            "future games leaked into the early build."
        )

    def test_as_of_stamp_respects_boundary(self, section):
        art = section.build(JOKIC_ID, AS_OF_EARLY)
        if art is None:
            pytest.skip("Artifact is None for early as_of.")
        # The artifact as_of stamp must match what was passed in
        assert art.as_of == AS_OF_EARLY.date().isoformat(), (
            f"Artifact as_of={art.as_of!r} does not match "
            f"expected={AS_OF_EARLY.date().isoformat()!r}"
        )

    def test_per_game_frame_respects_as_of(self):
        """_build_per_game_frame must not return rows with game_date > as_of."""
        import pandas as pd
        df = _build_per_game_frame(JOKIC_ID, AS_OF_EARLY)
        if df is None:
            pytest.skip("No frame returned for early as_of.")
        max_date = pd.to_datetime(df["game_date"]).max()
        boundary = pd.Timestamp(AS_OF_EARLY)
        assert max_date <= boundary, (
            f"game_date {max_date} exceeds as_of boundary {boundary}: "
            "future-data leak in _build_per_game_frame."
        )


# ---------------------------------------------------------------------------
# Section self-validation
# ---------------------------------------------------------------------------

class TestSectionValidate:
    """section.validate() must pass for well-formed artifacts."""

    def test_validate_passes_jokic(self, section, jokic_artifact):
        assert section.validate(jokic_artifact), "section.validate() returned False for Jokic."

    def test_validate_passes_curry(self, section, curry_artifact):
        assert section.validate(curry_artifact), "section.validate() returned False for Curry."

    def test_validate_fails_on_wrong_section(self, section, jokic_artifact):
        bad = AtlasArtifact(
            section="wrong_section",
            entity=jokic_artifact.entity,
            entity_id=jokic_artifact.entity_id,
            sub_fields=jokic_artifact.sub_fields,
            provenance=jokic_artifact.provenance,
            confidence=jokic_artifact.confidence,
            as_of=jokic_artifact.as_of,
            cv_fields=jokic_artifact.cv_fields,
        )
        assert not section.validate(bad), "validate() should fail on wrong section name."
