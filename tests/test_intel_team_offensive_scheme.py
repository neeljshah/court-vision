"""Tests for intel/team_offensive_scheme.py.

Two core assertions required by the task spec:
  1. LEAK-SAFETY — build() never returns data with as_of > the requested boundary.
  2. SCHEMA CONFORMANCE — the artifact has all required sub-field keys, valid ranges,
     and all cv_fields keys are present with value=None.

Additional tests cover the AtlasSection contract (name/entity/source_name attrs),
the validate() face-validity gate, and build_and_register dry_run path.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

# Ensure the repo root is on sys.path so imports resolve.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------

from intel.team_offensive_scheme import TeamOffensiveScheme, build_and_register
from src.loop.atlas import AtlasArtifact, CVSlot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TRICODE = "BOS"  # well-covered team in team_advanced_stats.parquet (246 games)


@pytest.fixture(scope="module")
def section() -> TeamOffensiveScheme:
    return TeamOffensiveScheme()


@pytest.fixture(scope="module")
def artifact_recent(section: TeamOffensiveScheme) -> AtlasArtifact:
    """Build artifact as-of today (max data available)."""
    as_of = _dt.datetime(2026, 5, 30)
    art = section.build(TRICODE, as_of)
    assert art is not None, (
        f"build() returned None for {TRICODE} as-of 2026-05-30; "
        "check that team_advanced_stats.parquet is present."
    )
    return art


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that no data future to the as_of boundary leaks into the artifact."""

    def test_as_of_is_not_future(self, section: TeamOffensiveScheme) -> None:
        """Artifact as_of must be <= the requested boundary date."""
        boundary = _dt.datetime(2023, 1, 15)  # an early historical date
        art = section.build(TRICODE, boundary)
        # If data is available, artifact as_of must be <= boundary
        if art is not None:
            assert art.as_of is not None, "artifact.as_of must be set"
            assert art.as_of <= "2023-01-15", (
                f"artifact.as_of={art.as_of!r} is later than boundary 2023-01-15 — LEAK"
            )

    def test_early_boundary_fewer_games(self, section: TeamOffensiveScheme) -> None:
        """Building at an earlier as_of boundary must return fewer or equal n games."""
        early = _dt.datetime(2023, 3, 1)
        late = _dt.datetime(2026, 5, 30)

        art_early = section.build(TRICODE, early)
        art_late = section.build(TRICODE, late)

        if art_early is None or art_late is None:
            pytest.skip("One build returned None — cannot compare; skip.")

        n_early = art_early.provenance.get("n", 0)
        n_late = art_late.provenance.get("n", 0)
        assert n_early <= n_late, (
            f"Early build (n={n_early}) > late build (n={n_late}); "
            "suggests data beyond the as_of boundary is being included — potential LEAK."
        )

    def test_pace_identity_label_is_non_null_when_pace_exists(
        self, artifact_recent: AtlasArtifact
    ) -> None:
        """Pace identity label must be populated when pace_pg is populated."""
        pace_sub = artifact_recent.sub_fields.get("pace", {})
        pace_pg = pace_sub.get("pace_pg")
        pace_id = pace_sub.get("pace_identity")
        if pace_pg is not None:
            assert pace_id is not None, (
                "pace.pace_identity must be non-null when pace.pace_pg is present."
            )
            assert pace_id in ("SLOW", "MODERATE", "FAST", "VERY_FAST"), (
                f"Unexpected pace_identity value: {pace_id!r}"
            )


# ---------------------------------------------------------------------------
# 2. SCHEMA CONFORMANCE assertion
# ---------------------------------------------------------------------------

_REQUIRED_TOP_KEYS = {
    "pace", "shot_diet", "pnr", "ball_movement", "drive_rate",
    "tempo_spacing_cv", "iso_rate", "transition_rate", "three_point_rate",
}

_EXPECTED_CV_SLOTS = {
    "transition_rate_cv",
    "spacing_dist_cv",
    "drive_rate_cv",
    "pnr_spacing_cv",
    "handler_isolation_cv",
}


class TestSchemaConformance:
    """Verify the artifact schema matches the contract."""

    def test_section_name_and_entity(self, section: TeamOffensiveScheme) -> None:
        assert section.name == "offensive_scheme"
        assert section.entity == "team"

    def test_section_key_and_fn_name(self, section: TeamOffensiveScheme) -> None:
        assert section.section_key() == "offensive_scheme"
        assert section.sec_fn_name() == "sec_offensive_scheme"
        assert section.parquet_name() == "atlas_team_offensive_scheme.parquet"

    def test_required_top_level_keys_present(
        self, artifact_recent: AtlasArtifact
    ) -> None:
        """All required sub_field top-level keys must be in the artifact."""
        missing = _REQUIRED_TOP_KEYS - set(artifact_recent.sub_fields.keys())
        assert not missing, f"Missing sub_field keys: {missing}"

    def test_cv_fields_all_present(self, section: TeamOffensiveScheme) -> None:
        """cv_fields() must return all 5 reserved CV slot keys."""
        cv = section.cv_fields()
        missing = _EXPECTED_CV_SLOTS - set(cv.keys())
        assert not missing, f"Missing CV slot keys: {missing}"

    def test_cv_fields_are_cvslot_instances(self, section: TeamOffensiveScheme) -> None:
        """Every entry in cv_fields() must be a CVSlot with value=None."""
        for slot_name, slot in section.cv_fields().items():
            assert isinstance(slot, CVSlot), (
                f"cv_fields()[{slot_name!r}] is not a CVSlot instance."
            )
            assert slot.value is None, (
                f"CVSlot {slot_name!r} has value={slot.value!r}; must be None "
                "(CV branch hasn't run yet)."
            )

    def test_artifact_cv_fields_present_and_null(
        self, artifact_recent: AtlasArtifact
    ) -> None:
        """Artifact.cv_fields must contain all reserved slots with value=None."""
        art_cv = artifact_recent.cv_fields
        missing = _EXPECTED_CV_SLOTS - set(art_cv.keys())
        assert not missing, f"Artifact missing CV slots: {missing}"

        for slot_name in _EXPECTED_CV_SLOTS:
            slot = art_cv[slot_name]
            assert slot.value is None, (
                f"Artifact CVSlot {slot_name!r} has value={slot.value!r}; must be None."
            )

    def test_profile_payload_includes_cv_fields_json(
        self, artifact_recent: AtlasArtifact
    ) -> None:
        """to_profile_payload() data dict must contain _cv_fields with all 5 slots."""
        data, prov = artifact_recent.to_profile_payload()
        assert "_cv_fields" in data, "to_profile_payload() data must have '_cv_fields' key."
        cv_blob = data["_cv_fields"]
        for slot_name in _EXPECTED_CV_SLOTS:
            assert slot_name in cv_blob, (
                f"_cv_fields missing slot {slot_name!r} in to_profile_payload() output."
            )
            assert cv_blob[slot_name]["value"] is None, (
                f"_cv_fields[{slot_name!r}]['value'] must be null in profile payload."
            )

    def test_prov_has_required_keys(self, artifact_recent: AtlasArtifact) -> None:
        """Provenance dict must carry source, n, confidence, as_of."""
        prov = artifact_recent.provenance
        for key in ("source", "n", "confidence", "as_of"):
            assert key in prov, f"Provenance missing key: {key!r}"

    def test_confidence_is_valid_level(self, artifact_recent: AtlasArtifact) -> None:
        assert artifact_recent.confidence in ("low", "med", "high"), (
            f"confidence={artifact_recent.confidence!r} not in (low, med, high)."
        )

    def test_shot_diet_ranges(self, artifact_recent: AtlasArtifact) -> None:
        """ast_pct and efg_pct must be in [0, 1] when present."""
        sd = artifact_recent.sub_fields.get("shot_diet", {})
        for key in ("ast_pct", "efg_pct"):
            val = sd.get(key)
            if val is not None:
                assert 0.0 <= val <= 1.0, (
                    f"shot_diet.{key}={val} out of [0, 1] range."
                )

    def test_pace_range(self, artifact_recent: AtlasArtifact) -> None:
        """pace_pg must be in [80, 130] when present."""
        pace_pg = artifact_recent.sub_fields.get("pace", {}).get("pace_pg")
        if pace_pg is not None:
            assert 80.0 <= pace_pg <= 130.0, (
                f"pace.pace_pg={pace_pg} outside expected [80, 130] range."
            )

    def test_validate_passes_for_valid_artifact(
        self, section: TeamOffensiveScheme, artifact_recent: AtlasArtifact
    ) -> None:
        assert section.validate(artifact_recent), (
            "validate() returned False for a recently built artifact."
        )

    def test_validate_fails_wrong_section(
        self, section: TeamOffensiveScheme, artifact_recent: AtlasArtifact
    ) -> None:
        """validate() must reject an artifact with wrong section name."""
        bad = AtlasArtifact(
            section="wrong_section",
            entity="team",
            entity_id="BOS",
            sub_fields=artifact_recent.sub_fields,
            provenance=artifact_recent.provenance,
            confidence=artifact_recent.confidence,
            as_of=artifact_recent.as_of,
            cv_fields=artifact_recent.cv_fields,
        )
        assert not section.validate(bad)

    def test_validate_fails_cv_slot_with_value(
        self, section: TeamOffensiveScheme, artifact_recent: AtlasArtifact
    ) -> None:
        """validate() must reject an artifact where a CV slot already has a value."""
        import copy
        bad_cv = copy.deepcopy(artifact_recent.cv_fields)
        bad_cv["transition_rate_cv"] = CVSlot(
            name="transition_rate_cv",
            dtype="float",
            description="test",
            value=0.12,  # non-None — CV branch hasn't run, should fail
        )
        bad = AtlasArtifact(
            section=self.name if hasattr(self, "name") else "offensive_scheme",
            entity="team",
            entity_id="BOS",
            sub_fields=artifact_recent.sub_fields,
            provenance=artifact_recent.provenance,
            confidence=artifact_recent.confidence,
            as_of=artifact_recent.as_of,
            cv_fields=bad_cv,
        )
        # We need section name to be correct for validate to reach the cv check
        bad.section = "offensive_scheme"
        assert not section.validate(bad), (
            "validate() should return False when a CV slot has a non-None value."
        )


# ---------------------------------------------------------------------------
# 3. Dry-run registration path
# ---------------------------------------------------------------------------

class TestRegistration:
    """Verify build_and_register works in dry_run mode (no disk writes)."""

    def test_dry_run_returns_manifest(self) -> None:
        as_of = _dt.datetime(2026, 5, 30)
        manifest = build_and_register(
            team_tricodes=["BOS", "LAL"],
            as_of=as_of,
            dry_run=True,
        )
        assert "section" in manifest, "manifest must have 'section' key"
        assert manifest["section"] == "offensive_scheme"
        assert "cv_fields" in manifest
        assert set(manifest["cv_fields"]) == _EXPECTED_CV_SLOTS

    def test_dry_run_n_entities_positive(self) -> None:
        as_of = _dt.datetime(2026, 5, 30)
        manifest = build_and_register(
            team_tricodes=["BOS"],
            as_of=as_of,
            dry_run=True,
        )
        assert manifest.get("n_entities", 0) >= 1, (
            "Expected at least 1 entity built for BOS."
        )
