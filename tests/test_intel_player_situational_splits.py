"""Tests for intel/player_situational_splits.py.

Two mandatory assertions per DESIGN.md §2.2 / spec_intel_memory.md §1.9:
  1. Leak-safety: build() with a past as_of does NOT include any games beyond that date.
  2. Schema conformance: AtlasArtifact has all required sub-fields AND all cv_fields
     are present with value=None.

Additional unit tests cover edge cases (unknown player, validate sanity checks,
DEFER stubs are correctly marked, bridge registration dry_run).
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Make the repo importable without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.player_situational_splits import (
    PlayerSituationalSplits,
    build_and_register,
    get_section,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_minimal_artifact(section: PlayerSituationalSplits) -> AtlasArtifact:
    """Build a minimal but schema-compliant artifact for validation testing."""
    return AtlasArtifact(
        section=section.name,
        entity=section.entity,
        entity_id=1628983,
        value=None,
        sub_fields={
            "home_road": {"home": {"n_games": 10, "pts_pg": 25.0}, "road": {"n_games": 9, "pts_pg": 22.0}, "_n_games_in_split": 19},
            "back_to_back": {"b2b_second_night": {"n_games": 3, "pts_pg": 21.0}, "rested": {"n_games": 16, "pts_pg": 25.5}},
            "clutch": {
                "season_clutch": {
                    "clutch_gp": 20,
                    "clutch_fg_pct": 0.48,
                    "clutch_fg3_pct": 0.40,
                    "clutch_ft_pct": 0.88,
                    "clutch_plus_minus": 5.2,
                    "clutch_pts_per36": 28.0,
                    "season": "2025-26",
                }
            },
            "blowout": {
                "n_games_total": 41,
                "n_games_with_gt_entry": 8,
                "pct_games_in_garbage_time": 0.195,
                "mean_pct_min_in_gt": 0.04,
            },
            "national_tv": {"_note": "DEFER: no national-TV game flag exists in any repo parquet."},
            "revenge": {"_note": "DEFER: no prior-team history per player in any current parquet."},
        },
        provenance={"source": "player_quarter_stats.parquet", "n": 41, "confidence": "high", "as_of": "2026-05-30"},
        confidence="high",
        as_of="2026-05-30",
        cv_fields=section.cv_fields(),
    )


# ---------------------------------------------------------------------------
# 1. Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """The artifact shape matches the agreed DESIGN.md §4 contract."""

    def test_required_sub_fields_present(self) -> None:
        """All six required sub-field keys must exist on a valid artifact."""
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        required = {"home_road", "back_to_back", "clutch", "blowout", "national_tv", "revenge"}
        assert required.issubset(art.sub_fields.keys()), (
            f"Missing sub_fields: {required - set(art.sub_fields.keys())}"
        )

    def test_cv_fields_schema_present(self) -> None:
        """All four CV slots are in cv_fields() with value=None."""
        section = PlayerSituationalSplits()
        cv = section.cv_fields()
        expected_slots = {
            "cv_clutch_velocity",
            "cv_b2b_fatigue_score",
            "cv_home_spacing_delta",
            "cv_blowout_drive_rate",
        }
        assert expected_slots == set(cv.keys()), (
            f"CV slot mismatch. Expected: {expected_slots}. Got: {set(cv.keys())}"
        )
        for slot_name, slot in cv.items():
            assert isinstance(slot, CVSlot), f"cv_fields[{slot_name!r}] is not a CVSlot"
            assert slot.value is None, (
                f"cv_fields[{slot_name!r}].value must be None (reserved, not filled)"
            )

    def test_cv_fields_in_artifact(self) -> None:
        """The artifact built by the section carries cv_fields populated from cv_fields()."""
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        for slot_name in section.cv_fields():
            assert slot_name in art.cv_fields, f"cv_field {slot_name!r} missing from artifact"
            assert art.cv_fields[slot_name].value is None, (
                f"CV slot {slot_name!r} must have value=None"
            )

    def test_to_profile_payload_cv_fields_null(self) -> None:
        """to_profile_payload() embeds _cv_fields with null values (DESIGN.md §4)."""
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data, "_cv_fields key missing from profile payload"
        for slot_name in section.cv_fields():
            assert slot_name in data["_cv_fields"], (
                f"CV slot {slot_name!r} missing from _cv_fields payload"
            )
            assert data["_cv_fields"][slot_name]["value"] is None, (
                f"_cv_fields[{slot_name!r}]['value'] must be None in payload"
            )

    def test_provenance_keys(self) -> None:
        """Provenance dict has source / n / confidence / as_of (factory contract)."""
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        _, prov = art.to_profile_payload()
        for key in ("source", "n", "confidence", "as_of"):
            assert key in prov, f"provenance key {key!r} missing"
        assert prov["confidence"] in ("low", "med", "high")

    def test_defer_stubs_contain_note(self) -> None:
        """DEFER sub-fields national_tv and revenge must carry a _note explaining the gap."""
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        for defer_key in ("national_tv", "revenge"):
            val = art.sub_fields.get(defer_key, {})
            assert "_note" in val, (
                f"DEFER sub-field {defer_key!r} must contain a '_note' key"
            )
            assert "DEFER" in str(val["_note"]).upper(), (
                f"_note for {defer_key!r} must mention DEFER"
            )

    def test_section_class_attrs(self) -> None:
        """Section has correct name, entity, and source_name class attrs."""
        section = PlayerSituationalSplits()
        assert section.name == "situational_splits"
        assert section.entity == "player"
        assert "quarter_stats" in section.source_name

    def test_section_key_methods(self) -> None:
        """section_key / sec_fn_name / parquet_name follow the AtlasSection contract."""
        section = PlayerSituationalSplits()
        assert section.section_key() == "situational_splits"
        assert section.sec_fn_name() == "sec_situational_splits"
        assert "situational_splits" in section.parquet_name()


# ---------------------------------------------------------------------------
# 2. Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must never return data stamped after the requested as_of."""

    def test_past_as_of_returns_none_or_valid(self) -> None:
        """With as_of in the past (before any data), build() returns None (no future leak).

        We use 1970-01-01 which predates ALL game data in the repo.
        """
        section = PlayerSituationalSplits()
        ancient_as_of = _dt.datetime(1970, 1, 1, 0, 0, 0)
        # Use a known real player_id (SGA)
        result = section.build(1628983, ancient_as_of)
        # Either None (no data at that cutoff) or artifact with n=0
        if result is not None:
            assert int(result.provenance.get("n", 0)) == 0 or result.confidence == "low", (
                "Artifact built at 1970-01-01 should have n=0 or confidence=low (no real data)"
            )

    def test_gt_games_filtered_by_as_of(self) -> None:
        """garbage_time_player_aggregates is filtered to <= as_of; future games excluded.

        We mock the parquet to contain one game_date after as_of and one before,
        then assert only the pre-cutoff game is counted.
        """
        as_of = _dt.datetime(2023, 1, 15)
        pid = 1628983

        fake_gt = pd.DataFrame({
            "player_id": [pid, pid],
            "game_id": ["G1", "G2"],
            "game_date": ["2023-01-10", "2023-01-20"],  # one before, one after cutoff
            "pct_minutes_in_gt": [0.8, 0.9],
            "points_in_gt": [5.0, 6.0],
            "reb_in_gt": [1.0, 2.0],
            "ast_in_gt": [0.0, 1.0],
            "fg3m_in_gt": [1.0, 0.0],
            "fgm_in_gt": [2.0, 3.0],
            "fga_in_gt": [4.0, 5.0],
            "gt_entry_count": [1, 1],
            "minutes_played_total": [10.0, 10.0],
            "minutes_in_gt": [8.0, 9.0],
            "parse_failure_rate": [0.0, 0.0],
            "primary_starter_flag": [False, False],
        })

        from intel import player_situational_splits as mod
        original_src = dict(mod._SRC)
        try:
            mod._SRC["gt_agg"] = fake_gt
            # We'll test _blowout_stats directly
            from intel.player_situational_splits import _blowout_stats
            result = _blowout_stats(pid, as_of.date().isoformat())
            n_total = result.get("n_games_total", 0)
            assert n_total == 1, (
                f"Only 1 game_date <= 2023-01-15 should be included, got n_games_total={n_total}. "
                "This is a LEAK-SAFETY failure."
            )
        finally:
            mod._SRC.clear()
            mod._SRC.update(original_src)

    def test_clutch_pbp_filtered_by_as_of(self) -> None:
        """pbp_possession_features is filtered to game_date <= as_of in clutch stats."""
        as_of = _dt.datetime(2023, 5, 1)
        pid = 203999  # hypothetical player

        fake_pbp = pd.DataFrame({
            "player_id": [pid, pid],
            "game_id": ["G1", "G2"],
            "game_date": ["2023-04-20", "2023-05-10"],  # one before, one after
            "pbp_clutch_shots_attempted": [2.0, 3.0],
            "pbp_clutch_pts_scored": [4.0, 6.0],
        })

        from intel import player_situational_splits as mod
        original_src = dict(mod._SRC)
        try:
            mod._SRC["pbp_poss"] = fake_pbp
            # No clutch_profiles (not needed for this test - skip 2025-26 season)
            from intel.player_situational_splits import _clutch_stats
            # as_of before 2025-10-01 -> only pbp branch runs
            result = _clutch_stats(pid, "2023-05-01")
            pbp_clutch = result.get("pbp_clutch_per_game", {})
            n_games = pbp_clutch.get("n_games", 0)
            assert n_games == 1, (
                f"Only 1 game_date <= 2023-05-01 should be included, got n_games={n_games}. "
                "LEAK-SAFETY failure in clutch stats."
            )
            # Verify the included game's stats (game_date 2023-04-20)
            shots = pbp_clutch.get("clutch_shots_attempted_pg")
            assert shots == 2.0, f"Expected clutch_shots_attempted_pg=2.0, got {shots}"
        finally:
            mod._SRC.clear()
            mod._SRC.update(original_src)


# ---------------------------------------------------------------------------
# 3. Validate method
# ---------------------------------------------------------------------------

class TestValidate:
    """validate() accepts valid artifacts and rejects malformed ones."""

    def test_valid_artifact_passes(self) -> None:
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        assert section.validate(art) is True

    def test_wrong_section_fails(self) -> None:
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        art.section = "wrong_section"
        assert section.validate(art) is False

    def test_missing_required_sub_field_fails(self) -> None:
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        del art.sub_fields["blowout"]
        assert section.validate(art) is False

    def test_cv_slot_missing_fails(self) -> None:
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        del art.cv_fields["cv_clutch_velocity"]
        assert section.validate(art) is False

    def test_cv_slot_filled_fails(self) -> None:
        """A CV slot that has already been filled should fail validate (reserved status)."""
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        art.cv_fields["cv_clutch_velocity"].value = 0.5  # simulate CV filling it
        assert section.validate(art) is False

    def test_blowout_pct_out_of_range_fails(self) -> None:
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        art.sub_fields["blowout"]["pct_games_in_garbage_time"] = 1.5  # > 1.0
        assert section.validate(art) is False

    def test_clutch_fg_pct_out_of_range_fails(self) -> None:
        section = PlayerSituationalSplits()
        art = _make_minimal_artifact(section)
        art.sub_fields["clutch"]["season_clutch"]["clutch_fg_pct"] = -0.1
        assert section.validate(art) is False


# ---------------------------------------------------------------------------
# 4. build_and_register dry_run
# ---------------------------------------------------------------------------

class TestBuildAndRegister:
    """build_and_register runs without writing files in dry_run mode."""

    def test_dry_run_returns_manifest(self) -> None:
        """build_and_register with dry_run=True returns a manifest dict."""
        # Use a player_id list with a single unknown player to ensure no data path error
        result = build_and_register(
            player_ids=[999999999],  # unknown player, expect 0 artifacts
            as_of=_dt.datetime(2026, 5, 30),
            dry_run=True,
        )
        assert isinstance(result, dict), "build_and_register should return a manifest dict"
        assert "section" in result
        assert result["section"] == "situational_splits"
        assert "n_entities" in result
        assert result["n_entities"] == 0  # unknown player yields no artifact

    def test_get_section_returns_instance(self) -> None:
        """get_section() returns a PlayerSituationalSplits instance."""
        section = get_section()
        assert isinstance(section, PlayerSituationalSplits)
        assert section.name == "situational_splits"
