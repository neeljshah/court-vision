"""Tests for intel/team_ft_foul_environment.py.

Verifies:
  1. SCHEMA CONFORMANCE: artifact has all required sub_fields + cv_fields schema present.
  2. LEAK SAFETY: build() with a past as_of never returns data beyond that boundary.
  3. CV FIELDS: cv_fields() returns the expected slots with value=None.
  4. VALIDATE: validate() accepts a well-formed artifact and rejects bad ones.
"""
import datetime as _dt
import sys
from pathlib import Path

# Ensure repo root on path for imports
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import os
os.environ.setdefault("NBA_OFFLINE", "1")

import pytest

from src.loop.atlas import AtlasArtifact, CVSlot
from intel.team_ft_foul_environment import (
    TeamFTFoulEnvironment,
    _boxscore_team_ft_rows,
    build_and_register,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TRICODE = "BOS"  # Boston — reliably present in most parquet datasets
ANCIENT_AS_OF = _dt.datetime(2020, 1, 1)   # Before any boxscore data
RECENT_AS_OF = _dt.datetime(2024, 12, 1)   # Mid-season data


@pytest.fixture(scope="module")
def section() -> TeamFTFoulEnvironment:
    return TeamFTFoulEnvironment()


@pytest.fixture(scope="module")
def artifact_recent(section: TeamFTFoulEnvironment) -> AtlasArtifact:
    """Built artifact using a recent-enough as_of that has data."""
    art = section.build(TRICODE, RECENT_AS_OF)
    return art  # may be None if no local data; tests skip appropriately


# ---------------------------------------------------------------------------
# 1. Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact produced by build() must satisfy the AtlasSection schema contract."""

    def test_section_name_and_entity(self, section: TeamFTFoulEnvironment):
        assert section.name == "ft_foul_environment"
        assert section.entity == "team"

    def test_sec_fn_name(self, section: TeamFTFoulEnvironment):
        assert section.sec_fn_name() == "sec_ft_foul_environment"

    def test_parquet_name(self, section: TeamFTFoulEnvironment):
        assert section.parquet_name() == "atlas_team_ft_foul_environment.parquet"

    def test_artifact_has_required_sub_fields(
        self, section: TeamFTFoulEnvironment, artifact_recent: AtlasArtifact
    ):
        if artifact_recent is None:
            pytest.skip("No local boxscore data for RECENT_AS_OF; skip sub-field check.")

        required = {
            "fouls_committed", "ft_drawn", "ft_allowed",
            "officials_context", "pace_context",
            "foul_type_breakdown", "intentional_foul_rate", "clutch_foul_rate",
        }
        assert required.issubset(artifact_recent.sub_fields.keys()), (
            f"Missing sub_fields: {required - artifact_recent.sub_fields.keys()}"
        )

    def test_artifact_has_cv_fields(
        self, artifact_recent: AtlasArtifact
    ):
        if artifact_recent is None:
            pytest.skip("No local boxscore data; skip cv_fields check.")

        assert "opp_foul_draw_proximity" in artifact_recent.cv_fields
        assert "team_ft_pace_draw_rate" in artifact_recent.cv_fields

    def test_cv_fields_values_are_none(
        self, artifact_recent: AtlasArtifact
    ):
        """CV fields must be null until the CV branch fills them."""
        if artifact_recent is None:
            pytest.skip("No local boxscore data; skip cv_fields null check.")

        for slot_name, slot in artifact_recent.cv_fields.items():
            assert slot.value is None, (
                f"CV slot '{slot_name}' should be None at build time, got {slot.value!r}"
            )

    def test_artifact_provenance_keys(self, artifact_recent: AtlasArtifact):
        if artifact_recent is None:
            pytest.skip("No local boxscore data; skip provenance check.")

        prov = artifact_recent.provenance
        for key in ("source", "n", "confidence", "as_of"):
            assert key in prov, f"provenance missing key '{key}'"
        assert prov["confidence"] in ("low", "med", "high")
        assert int(prov["n"]) >= 0

    def test_to_profile_payload_shape(self, artifact_recent: AtlasArtifact):
        """to_profile_payload() returns (data, prov) with _cv_fields in data."""
        if artifact_recent is None:
            pytest.skip("No local boxscore data.")

        data, prov = artifact_recent.to_profile_payload()
        assert isinstance(data, dict)
        assert "_cv_fields" in data, "data must contain '_cv_fields' key"
        assert "opp_foul_draw_proximity" in data["_cv_fields"]
        assert "team_ft_pace_draw_rate" in data["_cv_fields"]
        # CV slot values must be None in the payload
        for slot_name, slot_meta in data["_cv_fields"].items():
            assert slot_meta["value"] is None, (
                f"payload cv slot '{slot_name}' value should be None"
            )
        assert "confidence" in prov
        assert "n" in prov


# ---------------------------------------------------------------------------
# 2. Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must not return data from after the as_of boundary."""

    def test_ancient_as_of_returns_none_or_no_future_data(
        self, section: TeamFTFoulEnvironment
    ):
        """With as_of before all data, build() should return None (no data)."""
        art = section.build(TRICODE, ANCIENT_AS_OF)
        # Either None (no data before 2020) or artifact with no games
        if art is not None:
            n = art.provenance.get("n", 0)
            assert n == 0 or art.sub_fields.get("fouls_committed", {}).get("n_games", 0) == 0, (
                "Expected no games for ancient as_of but found data"
            )

    def test_boxscore_rows_respect_as_of(self):
        """_boxscore_team_ft_rows() must not include rows beyond as_of."""
        past_as_of = _dt.datetime(2025, 1, 1)
        df = _boxscore_team_ft_rows(past_as_of)

        if df.empty:
            pytest.skip("No boxscore data available locally; skip leak-safety row check.")

        import pandas as pd
        max_date = pd.to_datetime(df["game_date"]).max()
        boundary = pd.Timestamp(past_as_of)
        assert max_date <= boundary, (
            f"Leak: max game_date {max_date} exceeds as_of boundary {boundary}"
        )

    def test_artifact_as_of_matches_boundary(
        self, section: TeamFTFoulEnvironment
    ):
        """Artifact's as_of field must equal the requested boundary date."""
        boundary = _dt.datetime(2024, 11, 15)
        art = section.build(TRICODE, boundary)
        if art is None:
            pytest.skip("No data for team/boundary combination.")
        assert art.as_of == boundary.date().isoformat(), (
            f"artifact.as_of={art.as_of!r} does not match boundary "
            f"{boundary.date().isoformat()!r}"
        )


# ---------------------------------------------------------------------------
# 3. CV fields schema
# ---------------------------------------------------------------------------

class TestCVFields:
    """cv_fields() returns the exact reserved slot schema."""

    def test_cv_fields_keys(self, section: TeamFTFoulEnvironment):
        slots = section.cv_fields()
        assert "opp_foul_draw_proximity" in slots
        assert "team_ft_pace_draw_rate" in slots

    def test_cv_fields_dtypes(self, section: TeamFTFoulEnvironment):
        slots = section.cv_fields()
        assert slots["opp_foul_draw_proximity"].dtype == "float"
        assert slots["team_ft_pace_draw_rate"].dtype == "float"

    def test_cv_fields_units(self, section: TeamFTFoulEnvironment):
        slots = section.cv_fields()
        assert slots["opp_foul_draw_proximity"].unit == "ft"
        assert slots["team_ft_pace_draw_rate"].unit is None

    def test_cv_fields_all_values_none(self, section: TeamFTFoulEnvironment):
        slots = section.cv_fields()
        for name, slot in slots.items():
            assert slot.value is None, (
                f"cv_fields() slot '{name}' must return value=None at build time"
            )

    def test_cv_fields_returns_cvslot_instances(self, section: TeamFTFoulEnvironment):
        slots = section.cv_fields()
        for name, slot in slots.items():
            assert isinstance(slot, CVSlot), (
                f"cv_fields()['{{name}}'] must be a CVSlot instance"
            )


# ---------------------------------------------------------------------------
# 4. validate()
# ---------------------------------------------------------------------------

class TestValidate:
    """validate() correctly accepts/rejects artifacts."""

    def _make_artifact(
        self,
        section: TeamFTFoulEnvironment,
        tricode: str = "LAL",
        overrides: dict = None,
    ) -> AtlasArtifact:
        """Construct a minimal valid artifact for validation tests."""
        sf = {
            "fouls_committed": {"pf_pg": 22.0, "pf_pg_l10": 21.5, "pf_pg_z": 0.1, "n_games": 30},
            "ft_drawn": {"fta_pg": 24.0, "ftm_pg": 19.0, "ft_pct_drawn": 0.792, "fta_pg_l10": 23.5, "n_games": 30},
            "ft_allowed": {"opp_fta_pg": 21.0, "opp_fta_pg_l10": 20.5, "fta_minus_opp_fta_pg": 3.0, "n_games": 30},
            "officials_context": {"ref_crew_fouls_z": 0.2, "ref_crew_fta_z": 0.1, "n_games": 30},
            "pace_context": {"pace": 99.5, "n_games": 30},
            "foul_type_breakdown": {"_note": "DEFER"},
            "intentional_foul_rate": {"_note": "DEFER"},
            "clutch_foul_rate": {"_note": "DEFER"},
        }
        if overrides:
            sf.update(overrides)
        return AtlasArtifact(
            section=section.name,
            entity=section.entity,
            entity_id=tricode,
            value=24.0,
            sub_fields=sf,
            provenance={"source": "test", "n": 30, "confidence": "high", "as_of": "2024-12-01"},
            confidence="high",
            as_of="2024-12-01",
            cv_fields=section.cv_fields(),
        )

    def test_valid_artifact_passes(self, section: TeamFTFoulEnvironment):
        art = self._make_artifact(section)
        assert section.validate(art) is True

    def test_wrong_section_name_fails(self, section: TeamFTFoulEnvironment):
        art = self._make_artifact(section)
        art.section = "wrong_section"
        assert section.validate(art) is False

    def test_wrong_entity_fails(self, section: TeamFTFoulEnvironment):
        art = self._make_artifact(section)
        art.entity = "player"
        assert section.validate(art) is False

    def test_missing_sub_field_fails(self, section: TeamFTFoulEnvironment):
        art = self._make_artifact(section)
        del art.sub_fields["fouls_committed"]
        assert section.validate(art) is False

    def test_invalid_ft_pct_fails(self, section: TeamFTFoulEnvironment):
        art = self._make_artifact(section, overrides={
            "ft_drawn": {"fta_pg": 20.0, "ftm_pg": 16.0, "ft_pct_drawn": 1.5, "n_games": 10}
        })
        assert section.validate(art) is False

    def test_negative_pf_pg_fails(self, section: TeamFTFoulEnvironment):
        art = self._make_artifact(section, overrides={
            "fouls_committed": {"pf_pg": -1.0, "n_games": 10}
        })
        assert section.validate(art) is False

    def test_invalid_pace_fails(self, section: TeamFTFoulEnvironment):
        art = self._make_artifact(section, overrides={
            "pace_context": {"pace": 200.0, "n_games": 10}
        })
        assert section.validate(art) is False

    def test_non_null_cv_slot_fails(self, section: TeamFTFoulEnvironment):
        """validate() must reject artifact where a CV slot has been pre-filled."""
        art = self._make_artifact(section)
        # Manually set a CV slot value (should only happen via fill_cv_slot post-build)
        art.cv_fields["opp_foul_draw_proximity"].value = 2.5
        assert section.validate(art) is False


# ---------------------------------------------------------------------------
# 5. dry_run build_and_register (smoke test)
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    """build_and_register() in dry_run mode returns a valid manifest."""

    def test_dry_run_returns_manifest(self, section: TeamFTFoulEnvironment):
        manifest = build_and_register(
            team_tricodes=["BOS", "LAL"],
            as_of=RECENT_AS_OF,
            dry_run=True,
        )
        assert isinstance(manifest, dict)
        assert manifest.get("section") == "ft_foul_environment"
        assert "cv_fields" in manifest
        assert "opp_foul_draw_proximity" in manifest["cv_fields"]
        assert "team_ft_pace_draw_rate" in manifest["cv_fields"]
