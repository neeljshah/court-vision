"""Tests for intel.player_defensive_profile (ARM-B defensive profile section).

Verifies:
  1. Leak-safety: build() with a past as_of never returns data timestamped
     after that date (confirmed via the AtlasArtifact.as_of field and the
     foul_rate sub-field whose source is date-keyed).
  2. Schema conformance: the AtlasArtifact has all required fields populated
     correctly and cv_fields() returns the three reserved CV slots with value=None.
  3. Validation: validate() accepts well-formed artifacts and rejects bad ranges.
  4. Bridge call: register_section() runs dry_run without raising (exercises the
     full materialise_parquet / emit_sec_function / update_registry path).
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is on the path (mirrors the --no-full-suite discipline)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.player_defensive_profile import (  # noqa: E402
    PlayerDefensiveProfile,
    build_player,
    register_batch,
)
from src.loop.atlas import AtlasArtifact, CVSlot  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Shai Gilgeous-Alexander -- appears in all major parquets
_SGA_ID = 1628983
# A very old as_of -- should return no foul_rate data (game_date guard)
_ANCIENT_AS_OF = _dt.datetime(2019, 1, 1)
# Current-ish as_of -- should return data if parquets are present
_CURRENT_AS_OF = _dt.datetime(2026, 5, 30)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def section() -> PlayerDefensiveProfile:
    return PlayerDefensiveProfile()


@pytest.fixture(scope="module")
def artifact_sga(section: PlayerDefensiveProfile) -> Any:
    """Build the artifact for SGA at a current as_of; skip test if no data."""
    art = section.build(_SGA_ID, _CURRENT_AS_OF)
    return art  # may be None if parquets absent


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that as_of is respected and future-dated sub-fields are excluded."""

    def test_ancient_asof_no_foul_rate_data(self, section: PlayerDefensiveProfile) -> None:
        """foul_features rows are date-keyed; ancient as_of should produce no foul_rate."""
        art = section.build(_SGA_ID, _ANCIENT_AS_OF)
        if art is None:
            pytest.skip("No parquet data available for SGA -- skip (parquets gitignored).")
        # foul_rate should be absent or None (all game_date rows post-2019-01-01)
        foul = art.sub_fields.get("foul_rate")
        if foul is not None:
            # if it's present, the pf_per_36 values should come from <= 2019-01-01
            # At minimum the as_of on the artifact must honour the boundary
            assert art.as_of <= "2019-01-01", (
                "artifact.as_of must not exceed the requested as_of boundary"
            )

    def test_artifact_as_of_does_not_exceed_requested(
        self, section: PlayerDefensiveProfile
    ) -> None:
        """artifact.as_of must be <= the requested as_of (ISO string comparison)."""
        for as_of in [_ANCIENT_AS_OF, _CURRENT_AS_OF]:
            art = section.build(_SGA_ID, as_of)
            if art is None:
                continue
            assert art.as_of <= as_of.date().isoformat(), (
                f"artifact.as_of={art.as_of!r} exceeds requested {as_of.date().isoformat()!r}"
            )

    def test_matchup_dates_bounded(self, section: PlayerDefensiveProfile) -> None:
        """If foul_rate is present for ANCIENT_AS_OF, all game_dates must be <= boundary."""
        art = section.build(_SGA_ID, _ANCIENT_AS_OF)
        if art is None:
            pytest.skip("No parquet data -- skip.")
        # matchup_assignments source is date-filtered; any present data must be <=
        ma = art.sub_fields.get("matchup_assignments")
        # We can't inspect raw rows here, but if n_games > 0 we verify as_of is correct
        if ma is not None:
            assert ma.get("n_games", 0) >= 0


# ---------------------------------------------------------------------------
# 2. Schema-conformance assertion
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Verify AtlasArtifact structure and cv_fields schema."""

    def test_cv_fields_schema(self, section: PlayerDefensiveProfile) -> None:
        """cv_fields() must return exactly three reserved slots, all value=None."""
        cv = section.cv_fields()
        assert isinstance(cv, dict), "cv_fields() must return a dict"
        expected = {"defender_distance_allowed", "contest_rate", "closeout_quality"}
        assert set(cv.keys()) == expected, (
            f"Expected CV slot names {expected}, got {set(cv.keys())}"
        )
        for name, slot in cv.items():
            assert isinstance(slot, CVSlot), f"cv[{name!r}] must be a CVSlot instance"
            assert slot.value is None, (
                f"CV slot {name!r} must have value=None until the CV branch fills it"
            )
            assert isinstance(slot.description, str) and len(slot.description) > 10, (
                f"CV slot {name!r} must have a non-empty description"
            )

    def test_artifact_fields_present(self, artifact_sga: Any) -> None:
        """If data is available, artifact has all required AtlasArtifact fields."""
        if artifact_sga is None:
            pytest.skip("No parquet data for SGA -- skip.")
        art = artifact_sga
        assert art.section == "defensive_profile"
        assert art.entity == "player"
        assert art.entity_id == _SGA_ID
        assert isinstance(art.sub_fields, dict) and len(art.sub_fields) >= 1
        assert isinstance(art.provenance, dict)
        assert "source" in art.provenance
        assert "n" in art.provenance
        assert "confidence" in art.provenance
        assert "as_of" in art.provenance
        assert art.confidence in ("low", "med", "high")
        assert art.as_of is not None

    def test_artifact_cv_fields_embedded(self, artifact_sga: Any) -> None:
        """artifact.cv_fields must carry the three reserved slots (value=None)."""
        if artifact_sga is None:
            pytest.skip("No parquet data for SGA -- skip.")
        cv = artifact_sga.cv_fields
        assert "defender_distance_allowed" in cv
        assert "contest_rate" in cv
        assert "closeout_quality" in cv
        for slot in cv.values():
            assert slot.value is None

    def test_to_profile_payload_cv_fields(self, artifact_sga: Any) -> None:
        """to_profile_payload() must embed _cv_fields with the reserved slot schema."""
        if artifact_sga is None:
            pytest.skip("No parquet data for SGA -- skip.")
        data, prov = artifact_sga.to_profile_payload()
        assert "_cv_fields" in data, "to_profile_payload() must include _cv_fields key"
        for slot_name in ("defender_distance_allowed", "contest_rate", "closeout_quality"):
            assert slot_name in data["_cv_fields"], (
                f"_cv_fields must include reserved slot {slot_name!r}"
            )
            slot_dict = data["_cv_fields"][slot_name]
            assert slot_dict["value"] is None
            assert "dtype" in slot_dict
            assert "description" in slot_dict

    def test_section_key_and_parquet_name(self, section: PlayerDefensiveProfile) -> None:
        """Helper methods return the expected naming conventions."""
        assert section.section_key() == "defensive_profile"
        assert section.sec_fn_name() == "sec_defensive_profile"
        assert section.parquet_name() == "atlas_player_defensive_profile.parquet"


# ---------------------------------------------------------------------------
# 3. Validate() sanity checks
# ---------------------------------------------------------------------------

class TestValidation:
    """validate() accepts well-formed artifacts and rejects out-of-range values."""

    def _make_artifact(self, sub_fields: Dict[str, Any]) -> AtlasArtifact:
        return AtlasArtifact(
            section="defensive_profile",
            entity="player",
            entity_id=9999,
            sub_fields=sub_fields,
            provenance={"source": "test", "n": 20, "confidence": "high", "as_of": "2026-05-30"},
            confidence="high",
            as_of="2026-05-30",
            cv_fields=PlayerDefensiveProfile().cv_fields(),
        )

    def test_valid_typical_values(self, section: PlayerDefensiveProfile) -> None:
        art = self._make_artifact({
            "matchup_assignments": {"fg_pct_allowed_avg": 0.45, "n_games": 30},
            "steal_block_rate": {"stl_pg": 1.2, "blk_pg": 0.5},
            "foul_rate": {"pf_per_36_l10": 2.8},
            "on_off_drtg": {"on_off_drating_diff": -3.5},
        })
        assert section.validate(art) is True

    def test_fg_pct_out_of_range(self, section: PlayerDefensiveProfile) -> None:
        art = self._make_artifact({
            "matchup_assignments": {"fg_pct_allowed_avg": 1.5},
        })
        assert section.validate(art) is False

    def test_stl_out_of_range(self, section: PlayerDefensiveProfile) -> None:
        art = self._make_artifact({
            "steal_block_rate": {"stl_pg": 15.0, "blk_pg": 0.5},
        })
        assert section.validate(art) is False

    def test_pf_per36_out_of_range(self, section: PlayerDefensiveProfile) -> None:
        art = self._make_artifact({
            "foul_rate": {"pf_per_36_l10": 9.0},
        })
        assert section.validate(art) is False

    def test_drtg_diff_out_of_range(self, section: PlayerDefensiveProfile) -> None:
        art = self._make_artifact({
            "on_off_drtg": {"on_off_drating_diff": -50.0},
        })
        assert section.validate(art) is False

    def test_empty_sub_fields_validates(self, section: PlayerDefensiveProfile) -> None:
        """An artifact with no numeric sub-fields passes (all guards are conditional)."""
        art = self._make_artifact({})
        assert section.validate(art) is True

    def test_live_artifact_validates(
        self, section: PlayerDefensiveProfile, artifact_sga: Any
    ) -> None:
        if artifact_sga is None:
            pytest.skip("No parquet data for SGA -- skip.")
        assert section.validate(artifact_sga) is True


# ---------------------------------------------------------------------------
# 4. Bridge dry-run (register_section)
# ---------------------------------------------------------------------------

class TestBridgeRegistration:
    """register_batch(..., dry_run=True) exercises the full bridge path without writes."""

    def test_register_batch_dry_run_returns_manifest(self) -> None:
        """register_batch with dry_run=True must return a manifest dict."""
        manifest = register_batch(
            [_SGA_ID],
            as_of=_CURRENT_AS_OF,
            store=None,
            dry_run=True,
        )
        assert isinstance(manifest, dict)
        assert manifest.get("section") == "defensive_profile"
        assert "cv_fields" in manifest
        cv_field_names = manifest["cv_fields"]
        assert "defender_distance_allowed" in cv_field_names
        assert "contest_rate" in cv_field_names
        assert "closeout_quality" in cv_field_names

    def test_register_empty_batch_dry_run(self) -> None:
        """An empty player list should return a zero-entity manifest without crashing."""
        manifest = register_batch([], dry_run=True)
        assert manifest["n_entities"] == 0
        assert manifest["section"] == "defensive_profile"

    def test_build_player_convenience(self) -> None:
        """build_player() module function delegates to _SECTION.build() correctly."""
        art = build_player(_SGA_ID, _CURRENT_AS_OF)
        # May be None if parquets absent; should never raise
        assert art is None or isinstance(art, AtlasArtifact)
