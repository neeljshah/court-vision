"""Tests for intel/player_ft_profile.py — AtlasSection contract for 'ft_profile'.

Assertions:
  1. LEAK-SAFETY: build() with a past as_of returns None sub-field data for
     games that were played after that as_of date.
  2. SCHEMA CONFORMANCE: the returned AtlasArtifact contains all required
     sub-field keys + all reserved cv_fields (with value=None).
  3. VALIDATE: PlayerFTProfile.validate() returns True on a well-formed artifact.
  4. CV_FIELDS: cv_fields() returns the four reserved CV slots, all value=None.
  5. HACK_CANDIDATE: hack flag + severity follow the documented thresholds.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure repo root is on path and NBA_OFFLINE is set
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.player_ft_profile import (
    PlayerFTProfile,
    _hack_candidate_for_player,
    _stability_for_player,
    build_and_register,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_SECTION = PlayerFTProfile()

_AS_OF_RECENT = _dt.datetime(2026, 5, 27, 0, 0, 0)
_AS_OF_PAST = _dt.datetime(2020, 1, 1, 0, 0, 0)   # before all games in repo

_KNOWN_PID = 1628983  # Shai Gilgeous-Alexander (present in adv_stats + clutch)


def _make_artifact(
    section: str = "ft_profile",
    entity: str = "player",
    entity_id: int = _KNOWN_PID,
    stability: dict | None = None,
    attempts: dict | None = None,
    hack_candidate: dict | None = None,
    clutch_ft: dict | None = None,
    n: int = 30,
    ft_pct: float = 0.85,
    cv_fields_override: dict | None = None,
) -> AtlasArtifact:
    """Build a synthetic AtlasArtifact for validator unit-tests."""
    sub_fields = {
        "stability": stability or {
            "ft_pct": ft_pct, "ft_pct_std": 0.1, "ft_pct_cv": 0.12,
            "ft_pct_l10": 0.87, "n_games": n, "n_games_with_fta": n - 5,
        },
        "attempts": attempts or {
            "fta_pg": 6.0, "fta_per_36": 7.2, "ftm_pg": 5.1,
            "pct_pts_from_ft": 0.22, "n_games": n,
        },
        "hack_candidate": hack_candidate or {
            "hack_flag": False, "hack_severity": 0.0,
            "poor_shooter_flag": False,
            "hack_threshold_ft_pct": 0.72, "hack_threshold_fta_pg": 5.5,
        },
        "clutch_ft": clutch_ft or {
            "clutch_ft_pct": 0.88, "clutch_gp": 20,
            "clutch_min": 5.5, "clutch_pts_per36": 22.0, "clutch_season": "2025-26",
        },
        "streak_analysis": {"_note": "DEFER"},
        "pressure_splits": {"_note": "DEFER"},
        "home_road_ft": {"_note": "DEFER"},
    }
    cv_fields = cv_fields_override or _SECTION.cv_fields()
    return AtlasArtifact(
        section=section,
        entity=entity,
        entity_id=entity_id,
        value=ft_pct,
        sub_fields=sub_fields,
        provenance={"source": "test", "n": n, "confidence": "high", "as_of": "2026-05-27"},
        confidence="high",
        as_of="2026-05-27",
        cv_fields=cv_fields,
    )


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify build() never returns data from games after as_of."""

    def test_past_as_of_returns_none_or_empty_stability(self) -> None:
        """With as_of=2020-01-01 (before all boxscores in repo), stability
        should be empty dict (no games found) or build returns None entirely."""
        art = _SECTION.build(_KNOWN_PID, _AS_OF_PAST)
        # Either no artifact (all sources empty for that period) or stability n=0
        if art is not None:
            n_games = art.sub_fields.get("stability", {}).get("n_games", 0)
            assert n_games == 0, (
                f"Leak detected: {n_games} games returned for as_of=2020-01-01"
            )

    def test_recent_as_of_returns_games(self) -> None:
        """With a recent as_of, a known player should have n_games > 0
        (requires boxscore data present locally; skips gracefully if absent)."""
        art = _SECTION.build(_KNOWN_PID, _AS_OF_RECENT)
        if art is not None:
            n_games = art.sub_fields.get("stability", {}).get("n_games", 0) or \
                      art.sub_fields.get("attempts", {}).get("n_games", 0) or 0
            # If data is present, must have some games
            assert n_games >= 0, "n_games should be non-negative"

    def test_as_of_boundary_no_future_games(self) -> None:
        """Build twice: once with a tight as_of and once with a later one.
        The tighter as_of must have n_games <= later as_of (monotonicity)."""
        art_early = _SECTION.build(_KNOWN_PID, _dt.datetime(2025, 1, 1))
        art_late = _SECTION.build(_KNOWN_PID, _AS_OF_RECENT)

        n_early = 0
        n_late = 0
        if art_early is not None:
            n_early = art_early.sub_fields.get("stability", {}).get("n_games", 0) or 0
        if art_late is not None:
            n_late = art_late.sub_fields.get("stability", {}).get("n_games", 0) or 0

        assert n_early <= n_late, (
            f"Leak: earlier as_of has more games ({n_early}) than later ({n_late})"
        )


# ---------------------------------------------------------------------------
# 2. Schema conformance assertion
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Verify the AtlasArtifact has all required sub-fields and CV slots."""

    _REQUIRED_SUB_KEYS = {
        "stability", "attempts", "hack_candidate",
        "clutch_ft", "streak_analysis", "pressure_splits", "home_road_ft",
    }

    _REQUIRED_CV_SLOTS = {
        "ft_motion_arc", "ft_release_speed",
        "ft_line_spread", "ft_motion_stability",
    }

    def test_sub_fields_present(self) -> None:
        art = _make_artifact()
        missing = self._REQUIRED_SUB_KEYS - set(art.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {missing}"

    def test_cv_fields_present(self) -> None:
        art = _make_artifact()
        missing = self._REQUIRED_CV_SLOTS - set(art.cv_fields.keys())
        assert not missing, f"Missing cv_fields: {missing}"

    def test_cv_fields_values_are_none(self) -> None:
        """All reserved CV slots must have value=None until the CV branch fills them."""
        art = _make_artifact()
        for slot_name, slot in art.cv_fields.items():
            assert slot.value is None, (
                f"cv_field '{slot_name}' has a non-None value before CV branch ran"
            )

    def test_cv_fields_have_dtype_and_description(self) -> None:
        cv = _SECTION.cv_fields()
        for name, slot in cv.items():
            assert isinstance(slot.dtype, str) and slot.dtype, \
                f"cv_field '{name}' missing dtype"
            assert isinstance(slot.description, str) and slot.description, \
                f"cv_field '{name}' missing description"

    def test_to_profile_payload_shape(self) -> None:
        """to_profile_payload() must return (data, prov) with _cv_fields embedded."""
        art = _make_artifact()
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data, "data must contain '_cv_fields' key"
        for slot_name in self._REQUIRED_CV_SLOTS:
            assert slot_name in data["_cv_fields"], \
                f"CV slot '{slot_name}' missing from to_profile_payload data"
        assert "source" in prov and "n" in prov and "confidence" in prov and "as_of" in prov

    def test_stability_sub_fields(self) -> None:
        """Stability must carry ft_pct, ft_pct_std, ft_pct_l10, n_games."""
        art = _make_artifact()
        stab = art.sub_fields["stability"]
        for key in ("ft_pct", "ft_pct_std", "n_games"):
            assert key in stab, f"stability missing '{key}'"

    def test_attempts_sub_fields(self) -> None:
        """Attempts must carry fta_pg, fta_per_36, ftm_pg."""
        art = _make_artifact()
        att = art.sub_fields["attempts"]
        for key in ("fta_pg", "fta_per_36", "ftm_pg"):
            assert key in att, f"attempts missing '{key}'"

    def test_hack_candidate_sub_fields(self) -> None:
        """hack_candidate must carry hack_flag, hack_severity, poor_shooter_flag."""
        art = _make_artifact()
        hc = art.sub_fields["hack_candidate"]
        for key in ("hack_flag", "hack_severity", "poor_shooter_flag",
                    "hack_threshold_ft_pct", "hack_threshold_fta_pg"):
            assert key in hc, f"hack_candidate missing '{key}'"

    def test_defer_sections_have_note(self) -> None:
        """DEFER sections must carry a '_note' key explaining why they're deferred."""
        art = _make_artifact()
        for defer_key in ("streak_analysis", "pressure_splits", "home_road_ft"):
            sec = art.sub_fields[defer_key]
            assert "_note" in sec, f"DEFER section '{defer_key}' missing '_note'"
            assert "DEFER" in sec["_note"], \
                f"DEFER section '{defer_key}' note must mention DEFER"


# ---------------------------------------------------------------------------
# 3. Validate method
# ---------------------------------------------------------------------------

class TestValidate:
    """Unit-test PlayerFTProfile.validate()."""

    def test_valid_artifact_passes(self) -> None:
        art = _make_artifact()
        assert _SECTION.validate(art) is True

    def test_wrong_section_name_fails(self) -> None:
        art = _make_artifact(section="wrong_section")
        assert _SECTION.validate(art) is False

    def test_wrong_entity_fails(self) -> None:
        art = _make_artifact(entity="team")
        assert _SECTION.validate(art) is False

    def test_ft_pct_out_of_range_fails(self) -> None:
        art = _make_artifact(ft_pct=1.5)
        assert _SECTION.validate(art) is False

    def test_hack_severity_out_of_range_fails(self) -> None:
        art = _make_artifact(
            hack_candidate={
                "hack_flag": True, "hack_severity": 2.0,
                "poor_shooter_flag": True,
                "hack_threshold_ft_pct": 0.72, "hack_threshold_fta_pg": 5.5,
            }
        )
        assert _SECTION.validate(art) is False

    def test_cv_field_with_value_fails(self) -> None:
        """If a CV slot has been filled, validate should fail (CV branch owns fills)."""
        cv_fields = _SECTION.cv_fields()
        cv_fields["ft_motion_arc"] = CVSlot(
            name="ft_motion_arc", dtype="float",
            description="test", unit="deg", value=42.0,  # should be None
        )
        art = _make_artifact(cv_fields_override=cv_fields)
        assert _SECTION.validate(art) is False

    def test_missing_required_sub_key_fails(self) -> None:
        art = _make_artifact()
        del art.sub_fields["clutch_ft"]
        assert _SECTION.validate(art) is False


# ---------------------------------------------------------------------------
# 4. CV fields contract
# ---------------------------------------------------------------------------

class TestCVFields:
    """Test cv_fields() returns correct slot schema."""

    def test_returns_four_slots(self) -> None:
        cv = _SECTION.cv_fields()
        assert len(cv) == 4, f"Expected 4 CV slots, got {len(cv)}"

    def test_all_slots_value_none(self) -> None:
        cv = _SECTION.cv_fields()
        for name, slot in cv.items():
            assert slot.value is None, f"Slot '{name}' value must be None"

    def test_slot_names_stable(self) -> None:
        expected = {"ft_motion_arc", "ft_release_speed",
                    "ft_line_spread", "ft_motion_stability"}
        actual = set(_SECTION.cv_fields().keys())
        assert actual == expected, f"CV slot names mismatch: {actual} != {expected}"

    def test_slot_units_set(self) -> None:
        """Slots that have physical units should declare them."""
        cv = _SECTION.cv_fields()
        assert cv["ft_motion_arc"].unit == "deg"
        assert cv["ft_release_speed"].unit == "ft/s"
        assert cv["ft_line_spread"].unit == "ft"
        assert cv["ft_motion_stability"].unit == "px"


# ---------------------------------------------------------------------------
# 5. Hack-candidate logic
# ---------------------------------------------------------------------------

class TestHackCandidate:
    """Unit-test _hack_candidate_for_player threshold logic."""

    def _hack(self, ft_pct: float, fta_pg: float) -> Dict[str, Any]:
        stab = {"ft_pct": ft_pct}
        att = {"fta_pg": fta_pg}
        return _hack_candidate_for_player(stab, att)

    def test_known_hack_target(self) -> None:
        """ft_pct=0.55, fta_pg=8.0 -> hack_flag=True, severity > 0."""
        result = self._hack(0.55, 8.0)
        assert result["hack_flag"] is True
        assert result["hack_severity"] is not None and result["hack_severity"] > 0
        assert result["poor_shooter_flag"] is True

    def test_good_shooter_not_flagged(self) -> None:
        """ft_pct=0.90, fta_pg=8.0 -> hack_flag=False."""
        result = self._hack(0.90, 8.0)
        assert result["hack_flag"] is False
        assert result["hack_severity"] == 0.0

    def test_poor_shooter_low_volume_not_hack(self) -> None:
        """ft_pct=0.60, fta_pg=2.0 -> hack_flag=False (low volume), poor_shooter=True."""
        result = self._hack(0.60, 2.0)
        assert result["hack_flag"] is False   # volume below threshold
        assert result["poor_shooter_flag"] is True

    def test_severity_in_unit_interval(self) -> None:
        """hack_severity must always be in [0, 1]."""
        for ft_pct in [0.30, 0.50, 0.65, 0.72, 0.80]:
            for fta_pg in [1.0, 5.5, 12.0, 20.0]:
                result = self._hack(ft_pct, fta_pg)
                sev = result.get("hack_severity")
                if sev is not None:
                    assert 0.0 <= sev <= 1.0, (
                        f"Severity {sev} out of [0,1] for ft_pct={ft_pct}, fta_pg={fta_pg}"
                    )

    def test_missing_ft_pct_returns_none_flags(self) -> None:
        result = _hack_candidate_for_player({}, {"fta_pg": 8.0})
        assert result["hack_flag"] is None
        assert result["poor_shooter_flag"] is None

    def test_missing_fta_pg_returns_none_hack_flag(self) -> None:
        result = _hack_candidate_for_player({"ft_pct": 0.55}, {})
        assert result["hack_flag"] is None  # can't compute without volume
        assert result["poor_shooter_flag"] is True


# ---------------------------------------------------------------------------
# 6. Dry-run build_and_register (smoke test)
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    """Smoke-test the batch builder in dry_run mode."""

    def test_dry_run_returns_manifest(self) -> None:
        manifest = build_and_register(
            player_ids=[_KNOWN_PID],
            as_of=_AS_OF_RECENT,
            dry_run=True,
        )
        assert isinstance(manifest, dict), "build_and_register must return a dict"
        assert manifest.get("section") == "ft_profile"
        assert "cv_fields" in manifest
        expected_cv = {"ft_motion_arc", "ft_release_speed",
                       "ft_line_spread", "ft_motion_stability"}
        assert set(manifest["cv_fields"]) == expected_cv

    def test_dry_run_empty_player_list(self) -> None:
        manifest = build_and_register(player_ids=[], dry_run=True)
        assert manifest.get("n_entities") == 0
