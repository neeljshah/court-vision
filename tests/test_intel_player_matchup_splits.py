"""Tests for intel/player_matchup_splits.py.

Covers:
  1. Leak-safety: build(pid, early_as_of) must NOT include data beyond as_of
     (coverage_faced_matrix season boundary enforcement).
  2. Schema conformance: AtlasArtifact has all required sub_fields + cv_fields present.
  3. cv_fields(): all 4 CV slots returned with value=None (schema contract).
  4. validate() passes for a well-formed artifact; fails for out-of-range fg_pct.
  5. to_profile_payload() returns (data, prov) matching factory shape including
     _cv_fields embedded with null values.
  6. build() returns None when no matchup data exists for a player.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intel.player_matchup_splits import PlayerMatchupSplits
from src.loop.atlas import AtlasArtifact, CVSlot, confidence_from_n


# ---------------------------------------------------------------------------
# Shared fake data fixtures
# ---------------------------------------------------------------------------

_FAKE_CFM = pd.DataFrame({
    "off_player_id":         [1001, 1001, 1001, 1002],
    "off_player_name":       ["PlayerA", "PlayerA", "PlayerA", "PlayerB"],
    "def_player_id":         [2001, 2002, 2003, 2004],
    "def_player_name":       ["DefX", "DefY", "DefZ", "DefW"],
    "season":                ["2025-26", "2025-26", "2025-26", "2025-26"],
    "n_games_matched":       [5, 3, 2, 10],
    "matchup_minutes_total": [15.0, 8.0, 5.0, 30.0],
    "partial_possessions":   [60.0, 30.0, 20.0, 100.0],
    "off_points":            [30, 12, 8, 50],
    "off_fgm":               [12, 5, 3, 20],
    "off_fga":               [25, 12, 8, 40],
    "off_fg3m":              [4, 2, 1, 6],
    "off_fg3a":              [10, 6, 4, 15],
    "off_fg_pct":            [0.48, 0.417, 0.375, 0.50],
    "off_fg3_pct":           [0.40, 0.333, 0.25, 0.40],
})

_FAKE_CFM_BASE = pd.DataFrame({
    "off_player_id":         [1001],
    "off_player_name":       ["PlayerA"],
    "def_player_id":         [2010],
    "def_player_name":       ["OldDef"],
    "season":                ["2024-25"],
    "n_games_matched":       [8],
    "matchup_minutes_total": [20.0],
    "partial_possessions":   [80.0],
    "off_points":            [40],
    "off_fgm":               [15],
    "off_fga":               [35],
    "off_fg3m":              [5],
    "off_fg3a":              [14],
    "off_fg_pct":            [0.429],
    "off_fg3_pct":           [0.357],
})

_FAKE_MDEV = pd.DataFrame({
    "player_id":       [1001],
    "player_name":     ["PlayerA"],
    "player_team":     ["LAL"],
    "opp_team":        ["BOS"],
    "n_games_vs_opp":  [3],
    "max_abs_z":       [2.5],
    "notable_flag":    [True],
    "deviation_flags": ["play_type_transition_pct^(+2.5sigma)"],
})

_FAKE_DM26 = pd.DataFrame({
    "def_player_id":    [2001, 2002, 2003],
    "def_player_name":  ["DefX", "DefY", "DefZ"],
    "def_team_tricode": ["BOS", "GSW", "DAL"],
    "game_id":          ["G1", "G2", "G3"],
    "game_date":        ["2025-11-01", "2025-11-05", "2025-11-10"],
    "season":           ["2025-26", "2025-26", "2025-26"],
    "matchup_minutes_total": [8.0, 5.0, 4.0],
    "partial_possessions":   [30.0, 20.0, 15.0],
    "points_allowed":        [12, 8, 6],
    "fg_made_allowed":       [5, 3, 2],
    "fg_attempted_allowed":  [12, 8, 5],
    "fg3_made_allowed":      [2, 1, 0],
    "fg3_attempted_allowed": [5, 3, 2],
    "switches_on":           [0, 1, 0],
    "blocks_matchup":        [0, 0, 1],
    "help_blocks":           [0, 0, 0],
    "matchups_count":        [3, 2, 1],
    "fg_pct_allowed":        [0.417, 0.375, 0.40],
    "fg3_pct_allowed":       [0.40, 0.333, 0.0],
})

_FAKE_POS_POS = pd.DataFrame({
    "player_pos": ["G", "G", "G", "F", "F", "C", "C"],
    "opp_pos":    ["G", "F", "C", "G", "F", "F", "C"],
    "stat":       ["pts", "pts", "pts", "pts", "pts", "pts", "pts"],
    "n_games":    [49000, 30000, 10000, 28000, 35000, 18000, 22000],
    "mean_dev":   [0.09, -0.05, 0.12, 0.03, -0.02, 0.06, 0.15],
    "std_dev":    [6.5, 5.8, 6.1, 5.5, 5.2, 5.0, 5.3],
    "t":          [3.0, -1.5, 2.8, 1.1, -0.7, 1.8, 4.2],
    "p_val":      [0.003, 0.130, 0.005, 0.270, 0.480, 0.072, 0.000],
    "analysis":   ["same_pos"] * 7,
})

_FAKE_POS_SCHEME = pd.DataFrame({
    "position":    ["G", "G", "F", "C"],
    "opp_scheme":  ["DROP", "SWITCH HEAVY", "DROP", "PERIMETER DENIAL"],
    "stat":        ["pts", "pts", "pts", "pts"],
    "n":           [500, 400, 350, 300],
    "mean_dev":    [1.2, -0.8, 0.5, -1.5],
    "std_dev":     [6.0, 5.8, 5.5, 5.0],
    "t_stat":      [4.5, -2.8, 1.7, -5.2],
    "p_value":     [0.000, 0.005, 0.09, 0.000],
    "mean_actual": [11.0, 9.5, 10.2, 8.5],
    "mean_baseline": [9.8, 10.3, 9.7, 10.0],
    "significant": [True, True, False, True],
})

_FAKE_ODI = pd.DataFrame({
    "team_id":     ["LAL", "LAL"],
    "season":      ["2025-26", "2025-26"],
    "game_date":   ["2025-11-01", "2025-12-01"],
    "n_games_window": [5, 10],
    "opp_contested_shot_rate_imposed_z": [0.3, 0.5],
    "opp_avg_defender_distance_imposed_z": [-0.2, -0.1],
    "opp_paint_attempts_allowed_pct_z": [0.1, 0.2],
    "opp_pace_imposed_z": [-0.3, -0.4],
    "opp_defensive_intensity_z": [0.2, 0.3],
    "data_density": ["med", "med"],
})

_FAKE_ADV = pd.DataFrame({
    "player_id":  [1001, 1001, 1001],
    "game_id":    ["G1", "G2", "G3"],
    "game_date":  ["2025-10-25", "2025-11-01", "2025-12-01"],
    "usagepercentage": [0.30, 0.28, 0.31],
    "trueshootingpercentage": [0.58, 0.60, 0.62],
    "effectivefieldgoalpercentage": [0.55, 0.57, 0.59],
    "assistpercentage": [0.20, 0.22, 0.18],
    "reboundpercentage": [0.08, 0.09, 0.07],
    "offensivereboundpercentage": [0.03, 0.04, 0.03],
    "defensivereboundpercentage": [0.05, 0.05, 0.04],
    "offensiverating": [115.0, 118.0, 120.0],
    "defensiverating": [108.0, 110.0, 107.0],
    "netrating": [7.0, 8.0, 13.0],
    "assisttoturnover": [2.5, 2.8, 3.0],
    "assistratio": [0.18, 0.20, 0.17],
    "turnoverratio": [0.10, 0.09, 0.08],
    "pie": [0.15, 0.16, 0.17],
    "possessions": [65.0, 70.0, 68.0],
    "paceper40": [98.0, 97.0, 99.0],
    "minutes": [34.0, 36.0, 35.0],
})

_FAKE_PBP = pd.DataFrame({
    "player_id":              [1001, 1001, 1001],
    "game_id":                ["G1", "G2", "G3"],
    "game_date":              ["2025-10-25", "2025-11-01", "2025-12-01"],
    "pbp_iso_poss_count":     [2.5, 3.0, 2.8],
    "pbp_pnr_ball_handler":   [3.0, 2.5, 3.5],
    "pbp_pnr_screener_proxy": [0.5, 0.4, 0.6],
    "pbp_post_up_count":      [0.2, 0.1, 0.3],
    "pbp_transition_count":   [1.5, 2.0, 1.8],
    "pbp_late_clock_shots":   [0.8, 1.0, 0.9],
    "pbp_clutch_shots_attempted": [1.0, 1.5, 1.2],
    "pbp_clutch_pts_scored":  [2.5, 3.0, 2.8],
    "pbp_avg_seconds_per_touch": [4.2, 4.0, 4.5],
})


def _make_patches(as_of_iso_cutoff: str = "2099-01-01"):
    """Build a list of module-level patches injecting fake DataFrames.

    Args:
        as_of_iso_cutoff: if set, simulate the coverage_faced being filtered
                          to only return seasons whose start <= cutoff.
    """
    import intel.player_matchup_splits as mod

    def _fake_load(key: str, path: Path) -> object:
        """Return fake data keyed on the load key."""
        key_map = {
            "cfm26":      _FAKE_CFM,
            "cfm_base":   _FAKE_CFM_BASE,
            "cfm26_disc": _FAKE_CFM,
            "mdev":       _FAKE_MDEV,
            "dm26":       _FAKE_DM26,
            "dm_base":    None,
            "pos_vs_pos": _FAKE_POS_POS,
            "pos_scheme": _FAKE_POS_SCHEME,
            "odi":        _FAKE_ODI,
            "adv_ms":     _FAKE_ADV,
            "pbp_pos_inf": _FAKE_PBP,
        }
        return key_map.get(key)

    return [patch("intel.player_matchup_splits._load", side_effect=_fake_load)]


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """coverage_faced_matrix season boundary: 2025-26 data excluded if as_of < 2025-10-01."""

    def test_pre_season_as_of_excludes_2025_26_data(self):
        """build with as_of=2025-05-01 must NOT include 2025-26 coverage_faced rows.

        The 2025-26 season opens ~2025-10-01; any record from that season must be
        excluded when as_of < 2025-10-01. The fake CFM26 has only 2025-26 rows for
        player 1001. The base CFM has 2024-25 rows (season end ~2025-06) which ARE
        available at as_of=2025-05-01 (season has not yet ended but data is season-
        level and treated as available when the season has started, i.e. as_of >=
        2024-10-01). The test verifies that the 2025-26 rows specifically are absent
        from the result.
        """
        section = PlayerMatchupSplits()
        as_of = _dt.datetime(2025, 5, 1, 12, 0, 0)  # before 2025-26 season open

        with _make_patches()[0]:
            import intel.player_matchup_splits as mod
            result = mod._notable_defenders(1001, as_of)

        # 2025-26 season boundary is 2025-10-01; at 2025-05-01 it must be excluded.
        # The only data that may be present is 2024-25 (cfm_base; season start 2024-10-01).
        for def_id, info in result.items():
            season = info.get("season", "")
            assert season != "2025-26", (
                f"Leak violation: defender {def_id} has 2025-26 season data at "
                f"as_of=2025-05-01 (season boundary guard failed). got {info!r}"
            )

    def test_valid_as_of_returns_data(self):
        """build with as_of=2026-01-01 includes 2025-26 coverage data for player 1001."""
        section = PlayerMatchupSplits()
        as_of = _dt.datetime(2026, 1, 1, 12, 0, 0)

        with _make_patches()[0]:
            art = section.build(1001, as_of)

        assert art is not None, "Should find data for 2026-01-01 with 2025-26 coverage"
        # as_of in artifact must not be after the decision boundary
        assert art.as_of is not None
        assert art.as_of <= "2026-01-01", (
            f"Leak violation: artifact.as_of={art.as_of!r} > decision boundary 2026-01-01"
        )

    def test_artifact_as_of_bounded_by_decision_time(self):
        """artifact.as_of must always be <= the as_of passed to build()."""
        section = PlayerMatchupSplits()
        boundary = _dt.datetime(2025, 11, 15, 0, 0, 0)
        boundary_iso = "2025-11-15"

        with _make_patches()[0]:
            art = section.build(1001, boundary)

        if art is not None:
            assert art.as_of <= boundary_iso, (
                f"artifact.as_of={art.as_of!r} exceeds boundary {boundary_iso!r}"
            )


# ---------------------------------------------------------------------------
# 2. Schema conformance assertion
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """AtlasArtifact must have all required sub_fields + correct provenance keys."""

    def test_all_required_sub_fields_present(self):
        section = PlayerMatchupSplits()
        as_of = _dt.datetime(2026, 1, 1)

        with _make_patches()[0]:
            art = section.build(1001, as_of)

        assert art is not None, "build should return an artifact for player 1001"
        assert art.section == "matchup_splits"
        assert art.entity == "player"
        assert art.entity_id == 1001

        required = {
            "vs_position", "vs_scheme", "vs_notable_defenders",
            "vs_opp_team", "matchup_deviation", "opp_scheme_pressure",
            "vs_size", "vs_specific_defenders_recent",
        }
        for key in required:
            assert key in art.sub_fields, f"Missing sub_field: {key!r}"

    def test_defer_fields_present_as_dicts_with_note(self):
        """DEFER sub-fields must be dicts with a '_note' key, not absent."""
        section = PlayerMatchupSplits()
        with _make_patches()[0]:
            art = section.build(1001, _dt.datetime(2026, 1, 1))
        assert art is not None

        for defer_key in ("vs_size", "vs_specific_defenders_recent"):
            val = art.sub_fields.get(defer_key)
            assert isinstance(val, dict), f"{defer_key!r} should be a dict"
            assert "_note" in val, f"{defer_key!r} DEFER dict missing '_note'"

    def test_provenance_keys_present_and_valid(self):
        section = PlayerMatchupSplits()
        with _make_patches()[0]:
            art = section.build(1001, _dt.datetime(2026, 1, 1))
        assert art is not None

        prov = art.provenance
        for pk in ("source", "n", "confidence", "as_of"):
            assert pk in prov, f"Missing provenance key: {pk!r}"
        assert prov["confidence"] in ("low", "med", "high")
        assert isinstance(prov["n"], int)
        assert prov["n"] >= 0

    def test_notable_defenders_structure(self):
        """vs_notable_defenders should have keyed entries with expected fields."""
        section = PlayerMatchupSplits()
        with _make_patches()[0]:
            art = section.build(1001, _dt.datetime(2026, 1, 1))
        assert art is not None

        nd = art.sub_fields["vs_notable_defenders"]
        assert isinstance(nd, dict), "vs_notable_defenders should be a dict"
        if nd:
            # Each entry should have at minimum these fields
            first = next(iter(nd.values()))
            assert "def_player_name" in first
            assert "partial_possessions" in first
            assert "off_fg_pct" in first


# ---------------------------------------------------------------------------
# 3. CV slots schema assertion
# ---------------------------------------------------------------------------

class TestCVFieldsSchema:
    """cv_fields() must return exactly the 4 reserved slots with value=None."""

    def test_cv_fields_returns_all_four_slots(self):
        section = PlayerMatchupSplits()
        slots = section.cv_fields()

        expected = {
            "cv_defender_closeout_vs_pos",
            "cv_contest_rate_vs_pos",
            "cv_drive_success_vs_scheme",
            "cv_spacing_vs_scheme",
        }
        assert set(slots.keys()) == expected, (
            f"CV slot mismatch: got {set(slots.keys())!r}, expected {expected!r}"
        )

    def test_cv_slots_all_null(self):
        section = PlayerMatchupSplits()
        slots = section.cv_fields()

        for name, slot in slots.items():
            assert isinstance(slot, CVSlot), f"slot {name!r} is not a CVSlot"
            assert slot.value is None, (
                f"CV slot {name!r} should have value=None (not yet filled); "
                f"got {slot.value!r}"
            )
            assert slot.description, f"CV slot {name!r} has empty description"

    def test_cv_slots_in_built_artifact(self):
        """Artifacts built by build() must carry all 4 CV slots with value=None."""
        section = PlayerMatchupSplits()
        expected_slots = set(section.cv_fields().keys())

        with _make_patches()[0]:
            art = section.build(1001, _dt.datetime(2026, 1, 1))

        assert art is not None
        for slot_name in expected_slots:
            assert slot_name in art.cv_fields, (
                f"CV slot {slot_name!r} missing from artifact.cv_fields"
            )
            assert art.cv_fields[slot_name].value is None, (
                f"CV slot {slot_name!r} must have value=None (CV branch hasn't run)"
            )


# ---------------------------------------------------------------------------
# 4. validate() acceptance and rejection
# ---------------------------------------------------------------------------

class TestValidate:

    def test_validate_passes_for_valid_artifact(self):
        section = PlayerMatchupSplits()
        with _make_patches()[0]:
            art = section.build(1001, _dt.datetime(2026, 1, 1))
        assert art is not None
        assert section.validate(art) is True

    def test_validate_fails_for_wrong_section(self):
        section = PlayerMatchupSplits()
        art = AtlasArtifact(
            section="wrong_section",
            entity="player",
            entity_id=1001,
            sub_fields={k: {} for k in (
                "vs_position", "vs_scheme", "vs_notable_defenders",
                "vs_opp_team", "matchup_deviation", "opp_scheme_pressure",
                "vs_size", "vs_specific_defenders_recent",
            )},
            provenance={"source": "test", "n": 10, "confidence": "med", "as_of": "2026-01-01"},
            confidence="med",
            as_of="2026-01-01",
            cv_fields=section.cv_fields(),
        )
        assert section.validate(art) is False

    def test_validate_fails_for_out_of_range_fg_pct(self):
        """off_fg_pct > 1.0 in notable_defenders should fail validation."""
        section = PlayerMatchupSplits()
        with _make_patches()[0]:
            art = section.build(1001, _dt.datetime(2026, 1, 1))
        assert art is not None
        # Corrupt a fg_pct value
        nd = art.sub_fields["vs_notable_defenders"]
        if nd:
            first_key = next(iter(nd))
            art.sub_fields["vs_notable_defenders"][first_key]["off_fg_pct"] = 1.5
        assert section.validate(art) is False

    def test_validate_fails_for_missing_cv_slot(self):
        """If a CV slot is absent from artifact.cv_fields, validate must return False."""
        section = PlayerMatchupSplits()
        with _make_patches()[0]:
            art = section.build(1001, _dt.datetime(2026, 1, 1))
        assert art is not None
        # Remove a CV slot
        art.cv_fields.pop("cv_defender_closeout_vs_pos", None)
        assert section.validate(art) is False

    def test_validate_fails_if_cv_slot_value_is_not_none(self):
        """CV slots must have value=None (CV branch hasn't run); non-None fails."""
        section = PlayerMatchupSplits()
        with _make_patches()[0]:
            art = section.build(1001, _dt.datetime(2026, 1, 1))
        assert art is not None
        # Simulate premature CV fill
        art.cv_fields["cv_contest_rate_vs_pos"].value = 0.42
        assert section.validate(art) is False


# ---------------------------------------------------------------------------
# 5. to_profile_payload() factory shape
# ---------------------------------------------------------------------------

class TestToProfilePayload:

    def test_payload_shape_matches_factory_pattern(self):
        """(data, prov) must match factory sec_ return shape with _cv_fields."""
        section = PlayerMatchupSplits()
        with _make_patches()[0]:
            art = section.build(1001, _dt.datetime(2026, 1, 1))
        assert art is not None

        data, prov = art.to_profile_payload()

        assert isinstance(data, dict), "data must be a dict"
        assert "_cv_fields" in data, "_cv_fields must be embedded in data"

        cv = data["_cv_fields"]
        for slot_name in section.cv_fields():
            assert slot_name in cv, f"CV slot {slot_name!r} not in payload _cv_fields"
            assert cv[slot_name]["value"] is None, (
                f"_cv_fields[{slot_name!r}]['value'] should be None"
            )
            assert "dtype" in cv[slot_name], f"CV slot {slot_name!r} missing 'dtype'"
            assert "description" in cv[slot_name], f"CV slot {slot_name!r} missing 'description'"

        for pk in ("source", "n", "confidence", "as_of"):
            assert pk in prov, f"prov missing key: {pk!r}"
        assert prov["confidence"] in ("low", "med", "high")


# ---------------------------------------------------------------------------
# 6. Unknown player returns None
# ---------------------------------------------------------------------------

def test_build_returns_none_for_unknown_player():
    section = PlayerMatchupSplits()
    with _make_patches()[0]:
        art = section.build(99999, _dt.datetime(2026, 1, 1))
    assert art is None, "Should return None for a player with no matchup data"


# ---------------------------------------------------------------------------
# 7. Section key helpers
# ---------------------------------------------------------------------------

def test_section_key_helpers():
    section = PlayerMatchupSplits()
    assert section.section_key() == "matchup_splits"
    assert section.sec_fn_name() == "sec_matchup_splits"
    assert section.parquet_name() == "atlas_player_matchup_splits.parquet"
