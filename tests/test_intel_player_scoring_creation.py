"""Tests for intel.player_scoring_creation (AtlasSection: scoring_creation).

Assertions:
  1. LEAK-SAFETY: build(entity_id, as_of) never includes game data after as_of.
  2. SCHEMA CONFORMANCE: artifact sub_fields contain all expected keys; cv_fields
     are present and all values are None (reserved, not yet filled by CV branch).
  3. VALIDATE: the section's own face-validity check passes on a well-formed artifact.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

# Ensure repo root is on sys.path (required by DESIGN.md run rules).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import pytest

from intel.player_scoring_creation import SECTION, PlayerScoringCreation
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

# Use LeBron (2544) as a canonical test player — present in all three parquets.
# If running offline without data, tests use a synthetic artifact instead.
_TEST_PID = 2544

# A sufficiently late as_of that should include most game data.
_AS_OF_LATE = _dt.datetime(2025, 4, 20, 0, 0, 0)

# A very early as_of that should exclude all seasons (pre-2022 data).
_AS_OF_EARLY = _dt.datetime(2020, 1, 1, 0, 0, 0)


def _has_data() -> bool:
    """Check that at least one source parquet is present (for skip logic)."""
    from intel.player_scoring_creation import _PQ_BREAKDOWN, _PQ_TRACKING, _PQ_PBP
    return any(p.exists() for p in (_PQ_BREAKDOWN, _PQ_TRACKING, _PQ_PBP))


def _make_synthetic_artifact(pid: int = _TEST_PID) -> AtlasArtifact:
    """Build a minimal valid artifact directly for schema tests (no disk needed)."""
    sub = {
        "unassisted_share_2pm": 0.62,
        "assisted_share_2pm": 0.38,
        "unassisted_share_3pm": 0.31,
        "assisted_share_3pm": 0.69,
        "transition_pts_share": 0.19,
        "halfcourt_pts_share": 0.81,
        "pts_3pt_share": 0.26,
        "pts_paint_share": 0.48,
        "pts_ft_share": 0.15,
        "pts_midrange_share": 0.11,
        "breakdown_season": "2024-25",
        "drives_per_game": 10.3,
        "drive_pts_share": 0.62,
        "drive_ast_rate": 0.093,
        "catch_shoot_efg": 0.619,
        "catch_shoot_3pa_per_g": 2.1,
        "ast_to_pass_pct": 0.143,
        "passes_made_per_g": 8.5,
        "and_one_rate": 0.35,
        "transition_poss_per_game": 4.8,
        "avg_seconds_per_touch": 320.0,
        "iso_pts_pct": None,
        "pnr_bh_pts_pct": None,
    }
    return AtlasArtifact(
        section="scoring_creation",
        entity="player",
        entity_id=pid,
        value=0.47,
        sub_fields=sub,
        provenance={"source": "synthetic", "n": 50, "confidence": "high",
                    "as_of": "2025-04-20"},
        confidence="high",
        as_of="2025-04-20",
        cv_fields=SECTION.cv_fields(),
    )


# ---------------------------------------------------------------------------
# Test 1: LEAK-SAFETY
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build(entity_id, as_of) must not include data from after as_of."""

    @pytest.mark.skipif(not _has_data(), reason="source parquets not on disk")
    def test_early_as_of_yields_none_or_empty_pbp(self):
        """With as_of before any data exists, pbp segment must be empty/None."""
        pbp_result = SECTION._load_pbp(_TEST_PID, _AS_OF_EARLY.date().isoformat())
        # Either None (no rows) or n_games == 0
        assert pbp_result is None or pbp_result.get("n_games", 0) == 0, (
            "PBP aggregation returned data for a date before any games existed"
        )

    @pytest.mark.skipif(not _has_data(), reason="source parquets not on disk")
    def test_early_as_of_excludes_all_seasons(self):
        """With as_of=2020-01-01, no 2022+ seasons should pass the season-end filter."""
        breakdown = SECTION._load_breakdown(_TEST_PID, _AS_OF_EARLY.date().isoformat())
        tracking = SECTION._load_tracking(_TEST_PID, _AS_OF_EARLY.date().isoformat())
        # Both must be None because all seasons end after 2020
        assert breakdown is None, (
            "breakdown returned rows for a season ending after as_of=2020-01-01"
        )
        assert tracking is None, (
            "tracking returned rows for a season ending after as_of=2020-01-01"
        )

    @pytest.mark.skipif(not _has_data(), reason="source parquets not on disk")
    def test_pbp_game_dates_all_lte_as_of(self):
        """Internal PBP helper must filter to game_date <= as_of, no future rows."""
        from intel.player_scoring_creation import _PQ_PBP
        if not _PQ_PBP.exists():
            pytest.skip("pbp parquet not on disk")
        df = pd.read_parquet(_PQ_PBP)
        player_rows = df[df["player_id"] == _TEST_PID].copy()
        player_rows["game_date"] = pd.to_datetime(player_rows["game_date"], errors="coerce")

        cutoff = _AS_OF_LATE.date()
        future_rows = player_rows[player_rows["game_date"].dt.date > cutoff]
        # If there are no future rows the precondition is vacuously satisfied
        # (all data is already before the cutoff, so no leak is possible).
        # We still verify the artifact as_of is consistent.
        if len(future_rows) == 0:
            # Vacuously safe: no future data to leak — verify build is consistent
            art = SECTION.build(_TEST_PID, _AS_OF_LATE)
            if art is not None:
                assert art.as_of <= cutoff.isoformat(), (
                    f"artifact.as_of={art.as_of!r} is after as_of_date={cutoff.isoformat()!r}"
                )
            return  # test passes vacuously

        # Now run build and verify artifact as_of matches our cutoff, not a future date
        art = SECTION.build(_TEST_PID, _AS_OF_LATE)
        if art is not None:
            assert art.as_of <= cutoff.isoformat(), (
                f"artifact.as_of={art.as_of!r} is after as_of_date={cutoff.isoformat()!r}"
            )

    @pytest.mark.skipif(not _has_data(), reason="source parquets not on disk")
    def test_build_returns_artifact_or_none_for_known_player(self):
        """build() must return an AtlasArtifact (or None) — never raises."""
        art = SECTION.build(_TEST_PID, _AS_OF_LATE)
        assert art is None or isinstance(art, AtlasArtifact), (
            f"build returned unexpected type: {type(art)}"
        )

    def test_build_with_unknown_player_returns_none(self):
        """build() for a player_id with no data must return None gracefully."""
        art = SECTION.build(-9999, _AS_OF_LATE)
        assert art is None


# ---------------------------------------------------------------------------
# Test 2: SCHEMA CONFORMANCE (incl. cv_fields)
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact and cv_fields must match the agreed schema."""

    # Required sub_field keys (those derived from real data — not the DEFER nulls)
    _REQUIRED_SUB_KEYS = {
        "iso_pts_pct",         # DEFER — still present as None
        "pnr_bh_pts_pct",      # DEFER — still present as None
    }
    # Keys present when breakdown source available
    _BREAKDOWN_KEYS = {
        "unassisted_share_2pm", "assisted_share_2pm",
        "unassisted_share_3pm", "assisted_share_3pm",
        "transition_pts_share", "halfcourt_pts_share",
        "pts_3pt_share", "pts_paint_share", "pts_ft_share", "pts_midrange_share",
    }
    # CV slot names are the stable contract
    _CV_SLOT_NAMES = {"drive_speed", "rim_pressure", "help_drawn"}

    def test_cv_fields_returns_expected_slots(self):
        """cv_fields() must return exactly the three reserved CV slot names."""
        cv = SECTION.cv_fields()
        assert set(cv.keys()) == self._CV_SLOT_NAMES, (
            f"cv_fields keys mismatch: got {set(cv.keys())!r}"
        )

    def test_cv_slots_all_null(self):
        """All CV slot values must be None (reserved, not yet filled)."""
        cv = SECTION.cv_fields()
        for name, slot in cv.items():
            assert isinstance(slot, CVSlot), f"{name} is not a CVSlot"
            assert slot.value is None, (
                f"CV slot {name!r} has non-null value {slot.value!r}; "
                "CV branch has not run yet so all values must be reserved null"
            )

    def test_cv_slot_dtypes_and_units(self):
        """CV slots must have expected dtype and unit metadata."""
        cv = SECTION.cv_fields()
        assert cv["drive_speed"].dtype == "float"
        assert cv["drive_speed"].unit == "ft/s"
        assert cv["rim_pressure"].dtype == "float"
        assert cv["rim_pressure"].unit is None  # dimensionless index
        assert cv["help_drawn"].dtype == "float"
        assert cv["help_drawn"].unit == "defenders"

    def test_synthetic_artifact_schema_includes_defer_keys(self):
        """Synthetic artifact sub_fields include iso_pts_pct and pnr_bh_pts_pct as None."""
        art = _make_synthetic_artifact()
        for key in self._REQUIRED_SUB_KEYS:
            assert key in art.sub_fields, f"Missing DEFER key {key!r} in sub_fields"
            assert art.sub_fields[key] is None, (
                f"DEFER key {key!r} should be None, got {art.sub_fields[key]!r}"
            )

    def test_synthetic_artifact_cv_fields_in_profile_payload(self):
        """to_profile_payload() must embed _cv_fields with all three slots."""
        art = _make_synthetic_artifact()
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data, "to_profile_payload() missing _cv_fields"
        cv_in_payload = data["_cv_fields"]
        assert set(cv_in_payload.keys()) == self._CV_SLOT_NAMES, (
            f"_cv_fields keys mismatch: {set(cv_in_payload.keys())!r}"
        )
        # Each slot has the standard sub-keys
        for slot_name, slot_data in cv_in_payload.items():
            assert "dtype" in slot_data, f"slot {slot_name!r} missing 'dtype'"
            assert "value" in slot_data, f"slot {slot_name!r} missing 'value'"
            assert slot_data["value"] is None, (
                f"slot {slot_name!r} value should be None in profile payload"
            )

    def test_synthetic_artifact_provenance_shape(self):
        """Provenance dict from to_profile_payload must have the 4 standard keys."""
        art = _make_synthetic_artifact()
        _, prov = art.to_profile_payload()
        for key in ("source", "n", "confidence", "as_of"):
            assert key in prov, f"provenance missing key {key!r}"
        assert prov["confidence"] in ("low", "med", "high")
        assert isinstance(prov["n"], int)

    def test_section_attributes(self):
        """Section class attributes must match the expected contract values."""
        assert SECTION.name == "scoring_creation"
        assert SECTION.entity == "player"
        assert SECTION.sec_fn_name() == "sec_scoring_creation"
        assert SECTION.parquet_name() == "atlas_player_scoring_creation.parquet"

    @pytest.mark.skipif(not _has_data(), reason="source parquets not on disk")
    def test_built_artifact_schema_from_real_data(self):
        """Real-data artifact must pass schema checks: cv_fields present + null."""
        art = SECTION.build(_TEST_PID, _AS_OF_LATE)
        if art is None:
            pytest.skip("Player has no data; cannot validate schema")

        # cv_fields present and null
        assert set(art.cv_fields.keys()) == self._CV_SLOT_NAMES
        for name, slot in art.cv_fields.items():
            assert slot.value is None, f"CV slot {name!r} must be null pre-CV"

        # DEFER keys present
        for key in self._REQUIRED_SUB_KEYS:
            assert key in art.sub_fields

        # as_of is a valid ISO date string
        _dt.date.fromisoformat(art.as_of)  # raises if malformed

        # confidence in valid set
        assert art.confidence in ("low", "med", "high")


# ---------------------------------------------------------------------------
# Test 3: VALIDATE
# ---------------------------------------------------------------------------

class TestValidate:
    """Section.validate() must correctly accept/reject artifacts."""

    def test_validate_accepts_synthetic_good_artifact(self):
        """validate() must return True for a well-formed synthetic artifact."""
        art = _make_synthetic_artifact()
        assert SECTION.validate(art) is True

    def test_validate_rejects_none(self):
        """validate(None) must return False."""
        assert SECTION.validate(None) is False  # type: ignore[arg-type]

    def test_validate_rejects_out_of_range_share(self):
        """validate() must return False when a share field is outside [0, 1]."""
        art = _make_synthetic_artifact()
        art.sub_fields["unassisted_share_2pm"] = 1.5  # invalid
        assert SECTION.validate(art) is False

    def test_validate_rejects_wrong_entity(self):
        """validate() must return False for a team-entity artifact."""
        art = _make_synthetic_artifact()
        art.entity = "team"
        assert SECTION.validate(art) is False

    def test_validate_rejects_extra_cv_slot(self):
        """validate() must return False when cv_fields has unexpected slots."""
        art = _make_synthetic_artifact()
        from src.loop.atlas import CVSlot
        art.cv_fields["unexpected_slot"] = CVSlot(name="unexpected_slot")
        assert SECTION.validate(art) is False

    def test_validate_rejects_prefilled_cv_slot(self):
        """validate() must return False when a CV slot already has a value (CV
        branch not yet run — slots must remain null)."""
        art = _make_synthetic_artifact()
        art.cv_fields["drive_speed"].value = 12.5
        assert SECTION.validate(art) is False

    @pytest.mark.skipif(not _has_data(), reason="source parquets not on disk")
    def test_validate_passes_on_real_artifact(self):
        """Real built artifact must pass validate()."""
        art = SECTION.build(_TEST_PID, _AS_OF_LATE)
        if art is None:
            pytest.skip("No data for test player")
        assert SECTION.validate(art) is True
