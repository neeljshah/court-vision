"""Tests for intel/team_turnover_forcing.py.

Two core assertions required by the task spec:
  1. LEAK-SAFETY — build() never returns data with as_of > the requested boundary.
  2. SCHEMA CONFORMANCE — the artifact has all required sub-field keys, valid ranges,
     and all cv_fields keys are present with value=None.

Additional tests cover the AtlasSection contract (name/entity/source_name attrs),
the validate() face-validity gate, and the build_and_register dry_run path.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Optional

import pytest

# Ensure the repo root is on sys.path so imports resolve.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from intel.team_turnover_forcing import TeamTurnoverForcing, build_and_register
from src.loop.atlas import AtlasArtifact, CVSlot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TRICODE = "BOS"  # well-covered team (246 games in team_advanced_stats.parquet)
TRICODE_OKC = "OKC"  # second well-covered team (245 games)
AS_OF_RECENT = _dt.datetime(2026, 5, 31)
AS_OF_EARLY = _dt.datetime(2023, 1, 15)


@pytest.fixture(scope="module")
def section() -> TeamTurnoverForcing:
    return TeamTurnoverForcing()


@pytest.fixture(scope="module")
def artifact_bos(section: TeamTurnoverForcing) -> AtlasArtifact:
    """Build BOS artifact as-of the most recent boundary."""
    art = section.build(TRICODE, AS_OF_RECENT)
    assert art is not None, (
        f"build() returned None for {TRICODE} as-of {AS_OF_RECENT.date()}; "
        "check that season_games_*.json files are present."
    )
    return art


@pytest.fixture(scope="module")
def artifact_okc(section: TeamTurnoverForcing) -> AtlasArtifact:
    """Build OKC artifact as-of the most recent boundary."""
    art = section.build(TRICODE_OKC, AS_OF_RECENT)
    assert art is not None, (
        f"build() returned None for {TRICODE_OKC} as-of {AS_OF_RECENT.date()}; "
        "check that season_games_*.json files are present."
    )
    return art


# ---------------------------------------------------------------------------
# 1. AtlasSection contract attributes
# ---------------------------------------------------------------------------

class TestSectionContract:
    """Verify the class-level AtlasSection contract attributes."""

    def test_name(self, section: TeamTurnoverForcing) -> None:
        assert section.name == "turnover_forcing"

    def test_entity(self, section: TeamTurnoverForcing) -> None:
        assert section.entity == "team"

    def test_source_name_nonempty(self, section: TeamTurnoverForcing) -> None:
        assert section.source_name and len(section.source_name) > 5

    def test_cv_fields_returns_dict(self, section: TeamTurnoverForcing) -> None:
        slots = section.cv_fields()
        assert isinstance(slots, dict)
        assert "avg_pressure_distance" in slots

    def test_cv_slot_dtype(self, section: TeamTurnoverForcing) -> None:
        slot = section.cv_fields()["avg_pressure_distance"]
        assert isinstance(slot, CVSlot)
        assert slot.dtype in {"float", "dist", "list", "categorical", "int"}
        assert slot.value is None


# ---------------------------------------------------------------------------
# 2. Leak-safety tests
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that no data future to the as_of boundary leaks into the artifact."""

    def test_as_of_is_not_future(self, section: TeamTurnoverForcing) -> None:
        """Artifact as_of must be <= the requested boundary date."""
        boundary = AS_OF_EARLY
        art = section.build(TRICODE, boundary)
        if art is not None:
            assert art.as_of is not None, "artifact.as_of must be set"
            assert art.as_of <= "2023-01-15", (
                f"artifact.as_of={art.as_of!r} is later than boundary 2023-01-15 — LEAK"
            )

    def test_early_boundary_fewer_games(self, section: TeamTurnoverForcing) -> None:
        """Building at an earlier as_of must yield n <= n from a later as_of."""
        art_early = section.build(TRICODE, AS_OF_EARLY)
        art_late = section.build(TRICODE, AS_OF_RECENT)
        if art_early is not None and art_late is not None:
            n_early = art_early.provenance.get("n", 0)
            n_late = art_late.provenance.get("n", 0)
            assert n_early <= n_late, (
                f"Earlier boundary n={n_early} > later boundary n={n_late} — possible leak"
            )

    def test_provenance_as_of_consistent(self, artifact_bos: AtlasArtifact) -> None:
        """provenance['as_of'] must equal artifact.as_of."""
        assert artifact_bos.as_of == artifact_bos.provenance.get("as_of")


# ---------------------------------------------------------------------------
# 3. Schema conformance tests
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Verify sub-field keys, types, and valid ranges."""

    REQUIRED_SUB_KEYS = {
        "opp_tov", "own_tov", "deflections",
        "pbp_transition", "live_ball_tov_pts", "steal_pct",
    }

    def test_required_sub_fields_present(self, artifact_bos: AtlasArtifact) -> None:
        missing = self.REQUIRED_SUB_KEYS - set(artifact_bos.sub_fields.keys())
        assert not missing, f"Missing sub-field keys: {missing}"

    def test_section_and_entity_match(self, artifact_bos: AtlasArtifact) -> None:
        assert artifact_bos.section == "turnover_forcing"
        assert artifact_bos.entity == "team"
        assert artifact_bos.entity_id == TRICODE

    def test_opp_tov_pct_forced_in_range(self, artifact_bos: AtlasArtifact) -> None:
        """opp_tov_pct_forced must be in [0, 1]."""
        forced = artifact_bos.sub_fields.get("opp_tov", {}).get("opp_tov_pct_forced")
        assert forced is not None, "opp_tov_pct_forced is None — primary source missing"
        assert 0.0 <= forced <= 1.0, f"opp_tov_pct_forced={forced} out of [0,1]"

    def test_opp_tov_pct_l10_in_range(self, artifact_bos: AtlasArtifact) -> None:
        """L10 rolling rate must also be in [0, 1] when present."""
        l10 = artifact_bos.sub_fields.get("opp_tov", {}).get("opp_tov_pct_l10")
        if l10 is not None:
            assert 0.0 <= l10 <= 1.0, f"opp_tov_pct_l10={l10} out of [0,1]"

    def test_opp_tov_identity_label(self, artifact_bos: AtlasArtifact) -> None:
        """opp_tov_rate_identity must be one of the known label values."""
        label = artifact_bos.sub_fields.get("opp_tov", {}).get("opp_tov_rate_identity")
        if label is not None:
            assert label in {"PASSIVE", "AVERAGE", "DISRUPTIVE", "ELITE"}, (
                f"Unexpected opp_tov_rate_identity label: {label!r}"
            )

    def test_own_tov_ratio_positive(self, artifact_bos: AtlasArtifact) -> None:
        """own_tov_ratio must be positive and < 30 when present."""
        ratio = artifact_bos.sub_fields.get("own_tov", {}).get("own_tov_ratio")
        if ratio is not None:
            assert 0.0 < ratio < 30.0, f"own_tov_ratio={ratio} out of plausible range"

    def test_defl_pg_proxy_non_negative(self, artifact_bos: AtlasArtifact) -> None:
        """defl_pg_proxy must be non-negative when present."""
        defl = artifact_bos.sub_fields.get("deflections", {}).get("defl_pg_proxy")
        if defl is not None:
            assert defl >= 0.0, f"defl_pg_proxy={defl} is negative"

    def test_transition_count_pg_non_negative(self, artifact_bos: AtlasArtifact) -> None:
        """transition_count_pg must be non-negative when present."""
        trans = artifact_bos.sub_fields.get("pbp_transition", {}).get("transition_count_pg")
        if trans is not None:
            assert trans >= 0.0, f"transition_count_pg={trans} is negative"

    def test_provenance_n_is_int(self, artifact_bos: AtlasArtifact) -> None:
        n = artifact_bos.provenance.get("n")
        assert isinstance(n, int), f"provenance['n'] should be int, got {type(n)}"

    def test_provenance_n_ge_5(self, artifact_bos: AtlasArtifact) -> None:
        """Coverage must reach min_n=5 for the validator gate to pass."""
        n = artifact_bos.provenance.get("n", 0)
        assert n >= 5, f"provenance['n']={n} < 5 — fails validator coverage gate"

    def test_confidence_level_valid(self, artifact_bos: AtlasArtifact) -> None:
        assert artifact_bos.confidence in {"low", "med", "high"}


# ---------------------------------------------------------------------------
# 4. CV-slot schema tests
# ---------------------------------------------------------------------------

class TestCVSlots:
    """CV slots must be reserved (null) and well-typed."""

    def test_cv_slots_present(self, artifact_bos: AtlasArtifact) -> None:
        assert "avg_pressure_distance" in artifact_bos.cv_fields, (
            "avg_pressure_distance CV slot must be present in artifact.cv_fields"
        )

    def test_cv_slot_values_null(self, artifact_bos: AtlasArtifact) -> None:
        """All CV slot values must be None (CV branch has not run yet)."""
        for name, slot in artifact_bos.cv_fields.items():
            assert slot.value is None, (
                f"CV slot '{name}' has non-None value={slot.value!r} — "
                "CV slots must be reserved (null) at build time"
            )

    def test_cv_slot_dtype_valid(self, artifact_bos: AtlasArtifact) -> None:
        valid_dtypes = {"float", "dist", "list", "categorical", "int"}
        for name, slot in artifact_bos.cv_fields.items():
            assert slot.dtype in valid_dtypes, (
                f"CV slot '{name}' has invalid dtype={slot.dtype!r}"
            )


# ---------------------------------------------------------------------------
# 5. Section self-validation gate
# ---------------------------------------------------------------------------

class TestValidate:
    """The section's own validate() must return True for a well-formed artifact."""

    def test_validate_returns_true_for_good_artifact(
        self, section: TeamTurnoverForcing, artifact_bos: AtlasArtifact
    ) -> None:
        assert section.validate(artifact_bos) is True

    def test_validate_rejects_wrong_section(
        self, section: TeamTurnoverForcing, artifact_bos: AtlasArtifact
    ) -> None:
        from dataclasses import replace
        bad = replace(artifact_bos, section="wrong_section")
        assert section.validate(bad) is False

    def test_validate_rejects_wrong_entity(
        self, section: TeamTurnoverForcing, artifact_bos: AtlasArtifact
    ) -> None:
        from dataclasses import replace
        bad = replace(artifact_bos, entity="player")
        assert section.validate(bad) is False


# ---------------------------------------------------------------------------
# 6. Multi-team coverage (OKC + BOS)
# ---------------------------------------------------------------------------

class TestMultiTeam:
    """Both OKC and BOS must produce valid artifacts with n >= 5."""

    def test_okc_n_ge_5(self, artifact_okc: AtlasArtifact) -> None:
        n = artifact_okc.provenance.get("n", 0)
        assert n >= 5, f"OKC n={n} < 5 — fails validator coverage gate"

    def test_bos_n_ge_5(self, artifact_bos: AtlasArtifact) -> None:
        n = artifact_bos.provenance.get("n", 0)
        assert n >= 5, f"BOS n={n} < 5 — fails validator coverage gate"

    def test_okc_opp_tov_forced_present(self, artifact_okc: AtlasArtifact) -> None:
        forced = artifact_okc.sub_fields.get("opp_tov", {}).get("opp_tov_pct_forced")
        assert forced is not None and 0.0 <= forced <= 1.0, (
            f"OKC opp_tov_pct_forced={forced!r} invalid"
        )

    def test_both_pass_validate(
        self, section: TeamTurnoverForcing,
        artifact_bos: AtlasArtifact, artifact_okc: AtlasArtifact
    ) -> None:
        assert section.validate(artifact_bos) is True
        assert section.validate(artifact_okc) is True


# ---------------------------------------------------------------------------
# 7. build_and_register dry-run
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    """Smoke-test the build_and_register helper in dry_run mode."""

    def test_dry_run_returns_manifest(self) -> None:
        manifest = build_and_register(
            team_tricodes=["BOS", "OKC"],
            as_of=AS_OF_RECENT,
            dry_run=True,
        )
        assert isinstance(manifest, dict)
        assert manifest.get("section") == "turnover_forcing"
        assert manifest.get("n_entities", 0) >= 1

    def test_dry_run_cv_fields_in_manifest(self) -> None:
        manifest = build_and_register(
            team_tricodes=["BOS"],
            as_of=AS_OF_RECENT,
            dry_run=True,
        )
        cv = manifest.get("cv_fields", [])
        assert "avg_pressure_distance" in cv

    def test_dry_run_unknown_team_returns_zero(self) -> None:
        manifest = build_and_register(
            team_tricodes=["XXX"],
            as_of=AS_OF_RECENT,
            dry_run=True,
        )
        assert manifest.get("n_entities", 0) == 0
