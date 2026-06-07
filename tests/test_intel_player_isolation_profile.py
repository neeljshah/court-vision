"""Tests for intel/player_isolation_profile.py -- isolation_profile AtlasSection.

Covers:
  - Schema conformance: required sub_fields keys, CV slot schema
  - Proportion fields in [0,1]
  - Leak-safety: build at earlier as_of yields <= current n
  - Provenance n is actual game-row count (>= 5 for known players)
  - AtlasSection contract: section/entity constants, validate() and cv_fields()
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

# Ensure repo root is on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.player_isolation_profile import PlayerIsolationProfile, build_and_register
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JOKIC_ID = 203999
CURRY_ID = 201939
AS_OF = _dt.datetime(2026, 5, 30, 0, 0, 0)
EARLY_AS_OF = _dt.datetime(2025, 1, 1, 0, 0, 0)  # earlier boundary for leak tests


@pytest.fixture(scope="module")
def section() -> PlayerIsolationProfile:
    return PlayerIsolationProfile()


@pytest.fixture(scope="module")
def jokic_artifact(section: PlayerIsolationProfile):
    return section.build(JOKIC_ID, AS_OF)


@pytest.fixture(scope="module")
def curry_artifact(section: PlayerIsolationProfile):
    return section.build(CURRY_ID, AS_OF)


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

class TestSectionContract:
    def test_name(self, section):
        assert section.name == "isolation_profile"

    def test_entity(self, section):
        assert section.entity == "player"

    def test_source_name_non_empty(self, section):
        assert section.source_name and "playtypes" in section.source_name

    def test_sec_fn_name(self, section):
        assert section.sec_fn_name() == "sec_isolation_profile"

    def test_parquet_name(self, section):
        assert section.parquet_name() == "atlas_player_isolation_profile.parquet"


# ---------------------------------------------------------------------------
# CV slot schema
# ---------------------------------------------------------------------------

class TestCVSlots:
    def test_cv_fields_returns_dict(self, section):
        cvf = section.cv_fields()
        assert isinstance(cvf, dict)
        assert len(cvf) >= 2

    def test_required_slots_present(self, section):
        cvf = section.cv_fields()
        assert "defender_distance_iso" in cvf
        assert "blow_by_rate" in cvf

    def test_slot_values_are_none(self, section):
        for name, slot in section.cv_fields().items():
            assert slot.value is None, f"CV slot '{name}' must be None until CV fills it"

    def test_slot_dtypes_valid(self, section):
        valid_dtypes = {"float", "dist", "list", "categorical", "int"}
        for name, slot in section.cv_fields().items():
            assert slot.dtype in valid_dtypes, f"slot '{name}' has invalid dtype '{slot.dtype}'"

    def test_artifact_cv_fields_match_section(self, section, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built (missing source data)")
        declared = section.cv_fields()
        for name in declared:
            assert name in jokic_artifact.cv_fields, f"CV slot '{name}' missing from artifact"
        for name, slot in jokic_artifact.cv_fields.items():
            assert slot.value is None, f"artifact CV slot '{name}' must be null-reserved"


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    REQUIRED_KEYS = {
        "frequency", "efficiency", "ft_draw",
        "vs_set_defense", "late_clock",
        "defender_quality", "fg_pct_iso",
    }

    def _check_artifact(self, art: AtlasArtifact) -> None:
        assert art is not None, "artifact must not be None"
        assert art.section == "isolation_profile"
        assert art.entity == "player"
        assert isinstance(art.sub_fields, dict)
        assert self.REQUIRED_KEYS.issubset(art.sub_fields.keys()), (
            f"Missing keys: {self.REQUIRED_KEYS - set(art.sub_fields.keys())}"
        )

    def test_jokic_schema(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip("Jokic artifact not built")
        self._check_artifact(jokic_artifact)

    def test_curry_schema(self, curry_artifact):
        if curry_artifact is None:
            pytest.skip("Curry artifact not built")
        self._check_artifact(curry_artifact)

    def test_frequency_sub_dict_keys(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        freq = jokic_artifact.sub_fields.get("frequency", {})
        assert "iso_poss_per_game" in freq or "iso_freq_pct" in freq

    def test_ft_draw_sub_dict_keys(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        ft = jokic_artifact.sub_fields.get("ft_draw", {})
        assert "fta_per_36_q50" in ft

    def test_vs_set_defense_keys(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        vsd = jokic_artifact.sub_fields.get("vs_set_defense", {})
        assert "halfcourt_pts_share" in vsd or "_note" in vsd

    def test_late_clock_keys(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        lc = jokic_artifact.sub_fields.get("late_clock", {})
        assert "late_clock_shots_pg" in lc or "_note" in lc


# ---------------------------------------------------------------------------
# Proportion / range validation (CRITICAL LESSON 3)
# ---------------------------------------------------------------------------

class TestProportionRanges:
    def _check_proportions(self, art: AtlasArtifact) -> None:
        freq = art.sub_fields.get("frequency", {})
        v = freq.get("iso_freq_pct")
        if v is not None:
            assert 0.0 <= v <= 1.0, f"iso_freq_pct={v} out of [0,1]"

        vsd = art.sub_fields.get("vs_set_defense", {})
        for key in ["halfcourt_pts_share", "transition_pts_share"]:
            v = vsd.get(key)
            if v is not None:
                assert 0.0 <= v <= 1.0, f"{key}={v} out of [0,1]"

        eff = art.sub_fields.get("efficiency", {})
        for key in ["and_one_rate", "pts_ft_share"]:
            v = eff.get(key)
            if v is not None:
                assert 0.0 <= v <= 1.0, f"{key}={v} out of [0,1]"

    def test_jokic_proportions(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        self._check_proportions(jokic_artifact)

    def test_curry_proportions(self, curry_artifact):
        if curry_artifact is None:
            pytest.skip()
        self._check_proportions(curry_artifact)


# ---------------------------------------------------------------------------
# Provenance: n from actual game rows (CRITICAL LESSON 1)
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_jokic_n_from_game_rows(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        n = jokic_artifact.provenance.get("n", 0)
        # Jokic has 151 pbp_possession_features rows and 62 ft_rate rows
        assert n >= 5, f"n={n} is too low; expected actual game-row count >= 5"

    def test_curry_n_from_game_rows(self, curry_artifact):
        if curry_artifact is None:
            pytest.skip()
        n = curry_artifact.provenance.get("n", 0)
        # Curry has 134 pbp rows and 41 ft_rate rows
        assert n >= 5, f"n={n} is too low; expected actual game-row count >= 5"

    def test_as_of_string_set(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        assert jokic_artifact.as_of is not None
        assert len(jokic_artifact.as_of) >= 10  # "YYYY-MM-DD"

    def test_confidence_consistent_with_n(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        n = jokic_artifact.provenance.get("n", 0)
        conf = jokic_artifact.confidence
        if n >= 20:
            assert conf in ("med", "high")
        elif n >= 5:
            assert conf in ("low", "med", "high")  # any is ok (may be capped)


# ---------------------------------------------------------------------------
# Leak-safety: earlier as_of must not see future games (CRITICAL LESSON 5)
# ---------------------------------------------------------------------------

class TestLeakSafety:
    def test_early_as_of_n_le_current_n(self, section):
        """n at earlier as_of must be <= n at the current as_of (no future data in past)."""
        art_now = section.build(JOKIC_ID, AS_OF)
        art_early = section.build(JOKIC_ID, EARLY_AS_OF)

        if art_now is None:
            pytest.skip("Current artifact not built")

        n_now = int(art_now.provenance.get("n", 0))
        n_early = int(art_early.provenance.get("n", 0)) if art_early is not None else 0

        assert n_early <= n_now, (
            f"Earlier as_of has more games ({n_early}) than current ({n_now}) -- "
            "future data leaked into past build"
        )

    def test_as_of_does_not_exceed_build_date(self, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        art_date_str = jokic_artifact.as_of or ""
        prov_date_str = jokic_artifact.provenance.get("as_of") or ""
        # provenance as_of must not be later than artifact as_of
        if art_date_str and prov_date_str:
            assert prov_date_str <= art_date_str, (
                f"provenance as_of ({prov_date_str}) is after artifact as_of ({art_date_str})"
            )

    def test_curry_early_as_of_is_safe(self, section):
        art_now = section.build(CURRY_ID, AS_OF)
        art_early = section.build(CURRY_ID, EARLY_AS_OF)
        if art_now is None:
            pytest.skip()
        n_now = int(art_now.provenance.get("n", 0))
        n_early = int(art_early.provenance.get("n", 0)) if art_early is not None else 0
        assert n_early <= n_now


# ---------------------------------------------------------------------------
# section.validate() contract
# ---------------------------------------------------------------------------

class TestValidate:
    def test_validate_passes_for_jokic(self, section, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        assert section.validate(jokic_artifact) is True

    def test_validate_passes_for_curry(self, section, curry_artifact):
        if curry_artifact is None:
            pytest.skip()
        assert section.validate(curry_artifact) is True

    def test_validate_rejects_wrong_section(self, section, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        bad = AtlasArtifact(
            section="wrong_section",
            entity="player",
            entity_id=jokic_artifact.entity_id,
            sub_fields=jokic_artifact.sub_fields,
            provenance=jokic_artifact.provenance,
            confidence=jokic_artifact.confidence,
            as_of=jokic_artifact.as_of,
            cv_fields=jokic_artifact.cv_fields,
        )
        assert section.validate(bad) is False

    def test_validate_rejects_non_null_cv_slot(self, section, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        import copy
        bad_cv = copy.deepcopy(jokic_artifact.cv_fields)
        bad_cv["defender_distance_iso"].value = 5.0  # simulate CV filling prematurely
        bad = AtlasArtifact(
            section=jokic_artifact.section,
            entity=jokic_artifact.entity,
            entity_id=jokic_artifact.entity_id,
            sub_fields=jokic_artifact.sub_fields,
            provenance=jokic_artifact.provenance,
            confidence=jokic_artifact.confidence,
            as_of=jokic_artifact.as_of,
            cv_fields=bad_cv,
        )
        assert section.validate(bad) is False

    def test_validate_rejects_out_of_range_proportion(self, section, jokic_artifact):
        if jokic_artifact is None:
            pytest.skip()
        import copy
        bad_sf = copy.deepcopy(jokic_artifact.sub_fields)
        bad_sf["frequency"]["iso_freq_pct"] = 1.5  # > 1.0 — invalid
        bad = AtlasArtifact(
            section=jokic_artifact.section,
            entity=jokic_artifact.entity,
            entity_id=jokic_artifact.entity_id,
            sub_fields=bad_sf,
            provenance=jokic_artifact.provenance,
            confidence=jokic_artifact.confidence,
            as_of=jokic_artifact.as_of,
            cv_fields=jokic_artifact.cv_fields,
        )
        assert section.validate(bad) is False


# ---------------------------------------------------------------------------
# build_and_register dry_run smoke test
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    def test_dry_run_returns_manifest(self):
        manifest = build_and_register(
            player_ids=[JOKIC_ID, CURRY_ID],
            as_of=AS_OF,
            dry_run=True,
        )
        assert isinstance(manifest, dict)
        assert manifest.get("section") == "isolation_profile"
        assert manifest.get("sec_fn") == "sec_isolation_profile"
        assert "defender_distance_iso" in manifest.get("cv_fields", [])
        assert "blow_by_rate" in manifest.get("cv_fields", [])

    def test_dry_run_n_entities(self):
        manifest = build_and_register(
            player_ids=[JOKIC_ID, CURRY_ID],
            as_of=AS_OF,
            dry_run=True,
        )
        assert manifest.get("n_entities", 0) >= 1
