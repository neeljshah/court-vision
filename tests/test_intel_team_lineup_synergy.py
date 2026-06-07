"""Tests for intel.team_lineup_synergy (AtlasSection: lineup_synergy).

Assertions:
  1. LEAK-SAFETY: build(entity_id, as_of) never includes season data after as_of.
  2. SCHEMA CONFORMANCE: artifact sub_fields contain expected keys; cv_fields
     are present and all values are None (reserved, not yet filled by CV branch).
  3. VALIDATE: the section's own face-validity check passes on a well-formed artifact.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict

# Ensure repo root is on sys.path (required by DESIGN.md run rules).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest

from intel.team_lineup_synergy import SECTION, TeamLineupSynergy
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

# Use OKC as a canonical test team — present in lineup splits across seasons.
_TEST_TEAM = "OKC"

# A sufficiently late as_of that should include 2024-25 data.
_AS_OF_LATE = _dt.datetime(2025, 4, 20, 0, 0, 0)

# A very early as_of that should exclude all seasons (pre-2018).
_AS_OF_EARLY = _dt.datetime(2017, 1, 1, 0, 0, 0)


def _has_lineup_json() -> bool:
    """Check that at least one lineup splits JSON file exists."""
    from intel.team_lineup_synergy import LINEUPS_DIR
    return LINEUPS_DIR.exists() and any(LINEUPS_DIR.glob("lineup_splits_*_*.json"))


def _make_synthetic_artifact(team: str = _TEST_TEAM) -> AtlasArtifact:
    """Build a minimal valid artifact directly for schema tests (no disk needed)."""
    sub: Dict[str, Any] = {
        # Real sub-fields from lineup JSON
        "top_lineup_net": 12.5,
        "top3_lineup_net_avg": 8.3,
        "lineup_net_spread": 5.2,
        "lineup_pace_spread": 1.1,
        "lineup_efg": 0.545,
        "lineup_ast_to": 1.82,
        "lineup_depth": 42,
        "combo_5man": [
            {
                "lineup": ["S. Gilgeous-Alexander", "J. Williams", "I. Hartenstein",
                           "L. Dort", "J. Holmgren"],
                "net_rating": 15.2,
                "off_rating": 118.4,
                "def_rating": 103.2,
                "minutes": 210.0,
                "pace": 99.1,
                "efg_pct": 0.58,
                "ast_to": 2.1,
                "poss": 485.0,
            }
        ],
        "lineup_season": "2024-25",
        # DEFER sub-fields (must be present but None)
        "combo_2man": None,
        "combo_3man": None,
        # Depth baseline (from lineup_features)
        "league_baseline_top3_net": 2.1,
        "league_baseline_pace": 98.7,
        "depth_season": "2024-25",
        # Chemistry (from lineup_chemistry.parquet, CV-derived)
        "chemistry_score_median": 3.4,
        "chemistry_score_mean": 3.8,
        "chemistry_score_std": 1.9,
        "chemistry_n_games": 320,
    }
    return AtlasArtifact(
        section="lineup_synergy",
        entity="team",
        entity_id=team,
        value=12.5,
        sub_fields=sub,
        provenance={
            "source": "lineup_splits_json + lineup_features.parquet + lineup_chemistry.parquet",
            "n": 42,
            "confidence": "high",
            "as_of": "2025-04-20",
        },
        confidence="high",
        as_of="2025-04-20",
        cv_fields=SECTION.cv_fields(),
    )


# ---------------------------------------------------------------------------
# Test 1: LEAK-SAFETY
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build(entity_id, as_of) must not include data from after as_of."""

    def test_early_as_of_yields_none(self):
        """With as_of before any data exists (2017), build must return None."""
        art = SECTION.build(_TEST_TEAM, _AS_OF_EARLY)
        assert art is None, (
            f"Expected None for as_of=2017-01-01 (no pre-2017 lineup data), "
            f"got {art!r}"
        )

    @pytest.mark.skipif(not _has_lineup_json(), reason="lineup JSONs not on disk")
    def test_lineup_json_season_filtered_by_as_of(self):
        """_load_lineup_json must not include seasons ending after as_of."""
        result = SECTION._load_lineup_json(_TEST_TEAM, "2017-01-01")
        assert result is None, (
            "Expected None — all seasons end after 2017-01-01"
        )

    @pytest.mark.skipif(not _has_lineup_json(), reason="lineup JSONs not on disk")
    def test_lineup_json_late_as_of_returns_data(self):
        """_load_lineup_json with a 2025 as_of must find at least one valid season."""
        result = SECTION._load_lineup_json(_TEST_TEAM, "2025-04-20")
        assert result is not None, (
            "Expected lineup data for OKC as of 2025-04-20 (2024-25 should be available)"
        )
        assert result.get("n_lineups", 0) > 0, (
            "lineup JSON load returned 0 lineups"
        )

    @pytest.mark.skipif(not _has_lineup_json(), reason="lineup JSONs not on disk")
    def test_build_artifact_as_of_not_future(self):
        """Artifact as_of must be <= the requested as_of."""
        art = SECTION.build(_TEST_TEAM, _AS_OF_LATE)
        if art is None:
            pytest.skip("No data for OKC as of 2025-04-20")
        cutoff = _AS_OF_LATE.date().isoformat()
        assert art.as_of <= cutoff, (
            f"artifact.as_of={art.as_of!r} is after requested as_of={cutoff!r}"
        )

    def test_build_unknown_team_returns_none(self):
        """build() for an unknown team must return None gracefully."""
        art = SECTION.build("ZZZZZ", _AS_OF_LATE)
        assert art is None

    @pytest.mark.skipif(not _has_lineup_json(), reason="lineup JSONs not on disk")
    def test_build_returns_artifact_or_none_for_known_team(self):
        """build() must return an AtlasArtifact (or None) — never raises."""
        art = SECTION.build(_TEST_TEAM, _AS_OF_LATE)
        assert art is None or isinstance(art, AtlasArtifact), (
            f"build returned unexpected type: {type(art)}"
        )


# ---------------------------------------------------------------------------
# Test 2: SCHEMA CONFORMANCE (incl. cv_fields)
# ---------------------------------------------------------------------------

_CV_SLOT_NAMES = {"spacing_cv", "ball_movement_cv", "cohesion_cv"}

# Required sub-field keys (DEFER fields must be present as None)
_DEFER_KEYS = {"combo_2man", "combo_3man"}

# Required real sub-field keys (present whenever lineup JSON data exists)
_REAL_KEYS_LINEUP = {
    "top_lineup_net",
    "top3_lineup_net_avg",
    "lineup_depth",
    "combo_5man",
}


class TestSchemaConformance:
    """Artifact and cv_fields must match the agreed schema."""

    def test_cv_fields_returns_expected_slots(self):
        """cv_fields() must return exactly the three reserved CV slot names."""
        cv = SECTION.cv_fields()
        assert set(cv.keys()) == _CV_SLOT_NAMES, (
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
        assert cv["spacing_cv"].dtype == "float"
        assert cv["spacing_cv"].unit == "sq_ft"
        assert cv["ball_movement_cv"].dtype == "float"
        assert cv["ball_movement_cv"].unit is None   # dimensionless
        assert cv["cohesion_cv"].dtype == "float"
        assert cv["cohesion_cv"].unit is None         # dimensionless

    def test_synthetic_artifact_defer_keys_present_and_none(self):
        """Synthetic artifact sub_fields must include DEFER keys set to None."""
        art = _make_synthetic_artifact()
        for key in _DEFER_KEYS:
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
        assert set(cv_in_payload.keys()) == _CV_SLOT_NAMES, (
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
        assert SECTION.name == "lineup_synergy"
        assert SECTION.entity == "team"
        assert SECTION.sec_fn_name() == "sec_lineup_synergy"
        assert SECTION.parquet_name() == "atlas_team_lineup_synergy.parquet"

    def test_synthetic_artifact_real_keys_present(self):
        """Synthetic artifact must have all expected real (non-DEFER) keys."""
        art = _make_synthetic_artifact()
        for key in _REAL_KEYS_LINEUP:
            assert key in art.sub_fields, f"Missing real key {key!r} in sub_fields"

    def test_combo_5man_is_list(self):
        """combo_5man must be a list (even when empty)."""
        art = _make_synthetic_artifact()
        assert isinstance(art.sub_fields.get("combo_5man"), list), (
            "combo_5man must be a list"
        )

    def test_synthetic_artifact_as_of_parseable(self):
        """artifact.as_of must be a valid ISO date string."""
        art = _make_synthetic_artifact()
        _dt.date.fromisoformat(art.as_of)  # raises if malformed

    @pytest.mark.skipif(not _has_lineup_json(), reason="lineup JSONs not on disk")
    def test_built_artifact_schema_from_real_data(self):
        """Real-data artifact must pass schema checks: cv_fields present + null."""
        art = SECTION.build(_TEST_TEAM, _AS_OF_LATE)
        if art is None:
            pytest.skip("Team has no data; cannot validate schema")

        # cv_fields present and null
        assert set(art.cv_fields.keys()) == _CV_SLOT_NAMES
        for name, slot in art.cv_fields.items():
            assert slot.value is None, f"CV slot {name!r} must be null pre-CV"

        # DEFER keys present
        for key in _DEFER_KEYS:
            assert key in art.sub_fields, f"DEFER key {key!r} missing in built artifact"

        # as_of is a valid ISO date string
        _dt.date.fromisoformat(art.as_of)  # raises if malformed

        # confidence in valid set
        assert art.confidence in ("low", "med", "high")

        # combo_5man is a list
        assert isinstance(art.sub_fields.get("combo_5man", []), list)


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

    def test_validate_rejects_wrong_entity(self):
        """validate() must return False for a player-entity artifact."""
        art = _make_synthetic_artifact()
        art.entity = "player"
        assert SECTION.validate(art) is False

    def test_validate_rejects_out_of_range_net_rating(self):
        """validate() must return False when net_rating is outside [-120, 120]."""
        art = _make_synthetic_artifact()
        art.sub_fields["top_lineup_net"] = 150.0  # impossible even for garbage time
        assert SECTION.validate(art) is False

    def test_validate_rejects_out_of_range_efg(self):
        """validate() must return False when eFG% is outside [0, 1]."""
        art = _make_synthetic_artifact()
        art.sub_fields["lineup_efg"] = 1.5  # invalid
        assert SECTION.validate(art) is False

    def test_validate_rejects_negative_lineup_depth(self):
        """validate() must return False when lineup_depth is negative."""
        art = _make_synthetic_artifact()
        art.sub_fields["lineup_depth"] = -1
        assert SECTION.validate(art) is False

    def test_validate_rejects_extra_cv_slot(self):
        """validate() must return False when cv_fields has unexpected slots."""
        art = _make_synthetic_artifact()
        art.cv_fields["unexpected_slot"] = CVSlot(name="unexpected_slot")
        assert SECTION.validate(art) is False

    def test_validate_rejects_prefilled_cv_slot(self):
        """validate() must return False when a CV slot already has a value."""
        art = _make_synthetic_artifact()
        art.cv_fields["spacing_cv"].value = 312.5
        assert SECTION.validate(art) is False

    @pytest.mark.skipif(not _has_lineup_json(), reason="lineup JSONs not on disk")
    def test_validate_passes_on_real_artifact(self):
        """Real built artifact must pass validate()."""
        art = SECTION.build(_TEST_TEAM, _AS_OF_LATE)
        if art is None:
            pytest.skip("No data for test team")
        assert SECTION.validate(art) is True
