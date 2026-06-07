"""Tests for intel/player_durability_load.py.

Covers:
  1. Leak-safety: build(pid, as_of_past) must NOT return data stamped after as_of;
     artifact.as_of <= as_of_boundary; sub-fields must reflect only in-scope rows.
  2. Schema conformance: all required sub_fields present (REAL + DEFER keys),
     provenance has the four canonical keys, confidence is a valid level.
  3. CV fields: both reserved slots (fatigue_velocity_trend, sprint_rate) present
     with value=None and non-empty descriptions in both cv_fields() and the artifact.
  4. validate() passes for a well-formed artifact and rejects out-of-range values.
  5. to_profile_payload() shape matches the factory (data, prov) contract including
     _cv_fields embedded in data.
  6. Edge case: player with no data returns None.
  7. Section helper methods return expected strings.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intel.player_durability_load import (
    PlayerDurabilityLoad,
    _count_injury_spells,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Shared fake DataFrames
# ---------------------------------------------------------------------------

# Two players: 1001 (injured / load-managed), 1002 (healthy)
_FAKE_DNP = pd.DataFrame({
    "player_id":    [1001, 1001, 1001, 1001, 1002],
    "game_id":      ["G01", "G02", "G03", "G04", "G05"],
    "game_date":    [
        "2024-01-05",   # 1001 injury DNP
        "2024-02-10",   # 1001 injury DNP (future — must be excluded pre 2024-01-20)
        "2024-03-01",   # 1001 coach_decision (load mgmt)
        "2024-04-01",   # 1001 coach_decision
        "2024-01-08",   # 1002 injury DNP
    ],
    "season":       ["2023-24", "2023-24", "2023-24", "2023-24", "2023-24"],
    "player":       ["P1", "P1", "P1", "P1", "P2"],
    "team":         ["DAL", "DAL", "DAL", "DAL", "LAL"],
    "dnp_reason":   [
        "injury", "injury", "coach_decision", "coach_decision", "injury"
    ],
    "dnp_comment":  [
        "DNP - Knee",
        "DNP - Knee",
        "Rest",
        "Rest",
        "DNP - Ankle",
    ],
    "expected_to_play": [True, True, False, False, True],
})

_FAKE_DNP_FEAT = pd.DataFrame({
    "player_id":             [1001, 1001, 1002],
    "game_date":             ["2024-01-05", "2024-02-10", "2024-01-08"],
    "player_dnp_rate_l20":   [0.10, 0.15, 0.05],
})

_FAKE_INJURY = pd.DataFrame({
    "player_id":            [1001, 1001],
    "player_name":          ["Player One", "Player One"],
    "team":                 ["DAL", "DAL"],
    "status":               ["QUESTIONABLE", "OUT"],
    "availability_factor":  [0.5, 0.0],
    "reason":               ["Knee", "Knee - out"],
    "source":               ["espn", "espn"],
    "fetched_at":           ["2024-01-05", "2024-01-10"],
    "report_date":          ["2024-01-05", "2024-01-10"],
    "listed_date":          ["2024-01-05 08:00:00", "2024-01-10 08:00:00"],
    "listed_date_str":      ["2024-01-05", "2024-01-10"],
})

_FAKE_BIO = pd.DataFrame({
    "player_id":              [1001, 1002],
    "player_name":            ["Player One", "Player Two"],
    "age_precise_days_as_of": [10950.0, 8760.0],  # ~30 and ~24 years
    "years_in_league_as_of":  [8, 4],
    "profile_as_of":          ["2026-05-27", "2026-05-27"],
    "season_exp":             [8, 4],
    "from_year":              [2016, 2020],
    "to_year":                [2025, 2025],
})

_FAKE_ADV = pd.DataFrame({
    "player_id":  [1001, 1001, 1001, 1002, 1002],
    "game_id":    ["G10", "G11", "G12", "G20", "G21"],
    "game_date":  [
        "2024-01-10",   # 1001 — just before 2024-01-20 boundary
        "2024-02-20",   # 1001 — after 2024-01-20 (should be excluded)
        "2024-03-15",   # 1001 — after 2024-01-20 (should be excluded)
        "2024-01-08",
        "2024-03-10",
    ],
    "minutes":    [28.5, 36.0, 37.5, 24.0, 30.0],
    "usagepercentage": [0.25, 0.26, 0.27, 0.20, 0.21],
})


# ---------------------------------------------------------------------------
# Patch helper
# ---------------------------------------------------------------------------

def _patch_loaders(
    dnp=None, dnp_feat=None, inj=None, bio=None, adv=None
):
    """Return list of patches injecting fake data into module load functions."""
    import intel.player_durability_load as mod

    _dnp = _FAKE_DNP if dnp is None else dnp
    _dnp_feat = _FAKE_DNP_FEAT if dnp_feat is None else dnp_feat
    _inj = _FAKE_INJURY if inj is None else inj
    _bio = _FAKE_BIO if bio is None else bio
    _adv = _FAKE_ADV if adv is None else adv

    def mock_load_dnp(as_of_iso):
        df = _dnp.copy()
        return df[df["game_date"] <= as_of_iso].copy()

    def mock_load_dnp_feat(as_of_iso):
        df = _dnp_feat.copy()
        return df[df["game_date"] <= as_of_iso].copy()

    def mock_load_injury(as_of_iso):
        df = _inj.copy()
        if "listed_date_str" in df.columns:
            return df[df["listed_date_str"] <= as_of_iso].copy()
        return df

    def mock_load_bio():
        return _bio.copy()

    def mock_load_adv(as_of_iso):
        df = _adv.copy()
        return df[df["game_date"] <= as_of_iso].copy()

    return [
        patch("intel.player_durability_load._load_dnp", side_effect=mock_load_dnp),
        patch("intel.player_durability_load._load_dnp_feat", side_effect=mock_load_dnp_feat),
        patch("intel.player_durability_load._load_injury", side_effect=mock_load_injury),
        patch("intel.player_durability_load._load_bio", side_effect=mock_load_bio),
        patch("intel.player_durability_load._load_adv", side_effect=mock_load_adv),
    ]


def _apply_patches(patches, func, *args, **kwargs):
    """Enter all patches as context managers and call func."""
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        return func(*args, **kwargs)


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

def test_leak_safety_as_of_boundary():
    """build(pid, as_of=2024-01-20) must cap artifact.as_of to <= 2024-01-20.

    Player 1001 has a DNP on 2024-01-05 (in scope) and 2024-02-10 (out of scope).
    The adv_stats row on 2024-02-20 is also out of scope.
    The artifact's as_of and provenance.as_of must be <= 2024-01-20.
    """
    section = PlayerDurabilityLoad()
    as_of = _dt.datetime(2024, 1, 20, 12, 0, 0)
    as_of_iso = "2024-01-20"

    patches = _patch_loaders()
    art = _apply_patches(patches, section.build, 1001, as_of)

    assert art is not None, "should build with partial in-scope data"

    # --- CORE LEAK-SAFETY ASSERTIONS ---
    assert art.as_of is not None
    assert art.as_of <= as_of_iso, (
        f"Leak violation: artifact.as_of={art.as_of!r} > boundary={as_of_iso!r}"
    )
    assert art.provenance["as_of"] <= as_of_iso, (
        f"Provenance leak: {art.provenance['as_of']!r} > {as_of_iso!r}"
    )

    # Only 1 DNP row (2024-01-05 injury) is in scope before 2024-01-20
    # 2024-02-10 injury DNP is excluded
    assert art.sub_fields["games_missed_injury_total"] == 1, (
        f"Expected 1 injury DNP in scope; got {art.sub_fields['games_missed_injury_total']}"
    )

    # adv_stats: only 2024-01-10 row is in scope (28.5 min)
    assert art.sub_fields["minutes_per_game_mean"] == pytest.approx(28.5, abs=0.01)


def test_leak_safety_future_data_excluded():
    """build with as_of before all time-series data must exclude all time-series fields.

    player_profile_features (bio) is a static snapshot with no game_date so it is
    always visible (per spec_intel_memory 1.4 — the factory pattern applies bio
    build-time, not game-by-game). All per-game sources (DNP, adv_stats, injury
    snapshots) are filtered to as_of, so a 2020-01-01 boundary means those fields
    are all None. The artifact may still be built from bio alone (age, seniority).
    """
    section = PlayerDurabilityLoad()
    as_of = _dt.datetime(2020, 1, 1)  # before all per-game fake data
    as_of_iso = "2020-01-01"

    patches = _patch_loaders()
    art = _apply_patches(patches, section.build, 1001, as_of)

    # Bio data is static — an artifact may be returned with age/seniority only
    # The key assertion is that all TIME-SERIES sub-fields are None (no future data)
    if art is not None:
        assert art.as_of <= as_of_iso, (
            f"Leak: artifact.as_of={art.as_of!r} > boundary={as_of_iso!r}"
        )
        # All per-game fields must be None (no time-series data in scope)
        time_series_fields = [
            "games_missed_injury_total", "injury_dnp_rate",
            "minutes_per_game_mean", "current_status", "rolling_dnp_rate_l20",
        ]
        for fld in time_series_fields:
            assert art.sub_fields[fld] is None, (
                f"Leak: time-series field {fld!r} should be None before 2020; "
                f"got {art.sub_fields[fld]!r}"
            )


# ---------------------------------------------------------------------------
# 2. Schema conformance assertion
# ---------------------------------------------------------------------------

def test_schema_conformance_all_required_keys():
    """AtlasArtifact must have all required sub_fields + provenance keys."""
    section = PlayerDurabilityLoad()
    as_of = _dt.datetime(2025, 1, 1)

    patches = _patch_loaders()
    art = _apply_patches(patches, section.build, 1001, as_of)

    assert art is not None
    assert art.section == "durability_load"
    assert art.entity == "player"
    assert art.entity_id == 1001

    # REAL sub-field keys that must be present (may be None if data absent)
    required_keys = [
        "games_missed_injury_total",
        "games_missed_injury_l3seas",
        "injury_dnp_rate",
        "load_mgmt_dnp_count",
        "load_mgmt_dnp_rate",
        "rolling_dnp_rate_l20",
        "current_status",
        "current_availability",
        "age_years",
        "seasons_in_league",
        "minutes_per_game_mean",
        "minutes_per_game_std",
        "high_minutes_game_rate",
        "minutes_cap_return_mean",
        "n_injury_return_spells",
    ]
    for k in required_keys:
        assert k in art.sub_fields, f"Missing required sub_field: {k!r}"

    # DEFER fields must be present as None (key exists, value is None)
    defer_keys = [
        "injury_body_part_breakdown",
        "soft_tissue_vs_structural",
        "rpe_load_score",
    ]
    for k in defer_keys:
        assert k in art.sub_fields, f"DEFER field absent from sub_fields: {k!r}"
        assert art.sub_fields[k] is None, (
            f"DEFER field {k!r} should be None; got {art.sub_fields[k]!r}"
        )

    # Provenance must have the 4 canonical keys
    for pk in ("source", "n", "confidence", "as_of"):
        assert pk in art.provenance, f"Missing provenance key: {pk!r}"
    assert art.provenance["confidence"] in ("low", "med", "high"), (
        f"Invalid confidence: {art.provenance['confidence']!r}"
    )

    # n must be a non-negative integer
    assert isinstance(art.provenance["n"], int) and art.provenance["n"] >= 0


# ---------------------------------------------------------------------------
# 3. CV fields reserved with value=None
# ---------------------------------------------------------------------------

def test_cv_fields_present_and_null():
    """cv_fields() must return both reserved slots with value=None."""
    section = PlayerDurabilityLoad()
    slots = section.cv_fields()

    expected_slots = {"fatigue_velocity_trend", "sprint_rate"}
    assert set(slots.keys()) == expected_slots, (
        f"CV slot mismatch: got {set(slots.keys())!r}, expected {expected_slots!r}"
    )

    for name, slot in slots.items():
        assert isinstance(slot, CVSlot), f"slot {name!r} is not a CVSlot"
        assert slot.value is None, (
            f"CV slot {name!r} value should be None (not filled yet); got {slot.value!r}"
        )
        assert slot.description, f"CV slot {name!r} has empty description"
        assert slot.dtype in ("float", "dist", "list", "categorical"), (
            f"CV slot {name!r} dtype {slot.dtype!r} not recognised"
        )

    # Slots must appear in a built artifact's cv_fields
    patches = _patch_loaders()
    art = _apply_patches(patches, PlayerDurabilityLoad().build, 1001, _dt.datetime(2025, 1, 1))
    assert art is not None
    for slot_name in expected_slots:
        assert slot_name in art.cv_fields, (
            f"Slot {slot_name!r} missing from artifact.cv_fields"
        )
        assert art.cv_fields[slot_name].value is None


# ---------------------------------------------------------------------------
# 4. validate() passes / fails appropriately
# ---------------------------------------------------------------------------

def test_validate_passes_for_valid_artifact():
    section = PlayerDurabilityLoad()
    patches = _patch_loaders()
    art = _apply_patches(patches, section.build, 1001, _dt.datetime(2025, 1, 1))
    assert art is not None
    assert section.validate(art) is True


def test_validate_fails_for_out_of_range_rate():
    """injury_dnp_rate > 1.0 is impossible — validate must reject."""
    section = PlayerDurabilityLoad()
    patches = _patch_loaders()
    art = _apply_patches(patches, section.build, 1001, _dt.datetime(2025, 1, 1))
    assert art is not None
    art.sub_fields["injury_dnp_rate"] = 1.5  # corrupt
    assert section.validate(art) is False


def test_validate_fails_for_impossible_minutes():
    """minutes_per_game_mean > 60 is physically impossible."""
    section = PlayerDurabilityLoad()
    patches = _patch_loaders()
    art = _apply_patches(patches, section.build, 1001, _dt.datetime(2025, 1, 1))
    assert art is not None
    art.sub_fields["minutes_per_game_mean"] = 65.0  # corrupt
    assert section.validate(art) is False


def test_validate_fails_for_wrong_section():
    section = PlayerDurabilityLoad()
    art = AtlasArtifact(
        section="wrong_section",
        entity="player",
        entity_id=1001,
        sub_fields={
            "games_missed_injury_total": 2,
            "games_missed_injury_l3seas": 2,
            "injury_dnp_rate": 0.05,
            "load_mgmt_dnp_count": 3,
            "load_mgmt_dnp_rate": 0.07,
            "rolling_dnp_rate_l20": 0.10,
            "current_status": "ACTIVE",
            "current_availability": 1.0,
            "age_years": 28.0,
            "seasons_in_league": 7,
            "minutes_per_game_mean": 32.0,
            "minutes_per_game_std": 4.0,
            "high_minutes_game_rate": 0.40,
            "minutes_cap_return_mean": 22.0,
            "n_injury_return_spells": 1,
            "injury_body_part_breakdown": None,
            "soft_tissue_vs_structural": None,
            "rpe_load_score": None,
        },
        provenance={"source": "test", "n": 50, "confidence": "high", "as_of": "2025-01-01"},
        confidence="high", as_of="2025-01-01",
        cv_fields=section.cv_fields(),
    )
    assert section.validate(art) is False


def test_validate_fails_negative_games_missed():
    """games_missed_injury_total < 0 is nonsensical."""
    section = PlayerDurabilityLoad()
    patches = _patch_loaders()
    art = _apply_patches(patches, section.build, 1001, _dt.datetime(2025, 1, 1))
    assert art is not None
    art.sub_fields["games_missed_injury_total"] = -1
    assert section.validate(art) is False


# ---------------------------------------------------------------------------
# 5. to_profile_payload() matches factory shape
# ---------------------------------------------------------------------------

def test_to_profile_payload_shape():
    """(data, prov) must match the factory sec_ return shape."""
    section = PlayerDurabilityLoad()
    patches = _patch_loaders()
    art = _apply_patches(patches, section.build, 1001, _dt.datetime(2025, 1, 1))
    assert art is not None

    data, prov = art.to_profile_payload()

    # data is a dict with _cv_fields embedded
    assert isinstance(data, dict)
    assert "_cv_fields" in data
    cv = data["_cv_fields"]

    # Both reserved CV slots appear in the payload with value=None
    for slot_name in ("fatigue_velocity_trend", "sprint_rate"):
        assert slot_name in cv, f"CV slot {slot_name!r} not in payload _cv_fields"
        assert cv[slot_name]["value"] is None
        assert "description" in cv[slot_name]
        assert "dtype" in cv[slot_name]

    # prov must carry the 4 canonical keys
    for pk in ("source", "n", "confidence", "as_of"):
        assert pk in prov, f"Missing prov key: {pk!r}"
    assert prov["confidence"] in ("low", "med", "high")


# ---------------------------------------------------------------------------
# 6. Edge case: unknown player returns None
# ---------------------------------------------------------------------------

def test_build_returns_none_for_unknown_player():
    section = PlayerDurabilityLoad()
    patches = _patch_loaders()
    art = _apply_patches(patches, section.build, 99999, _dt.datetime(2025, 1, 1))
    assert art is None


# ---------------------------------------------------------------------------
# 7. Section helper methods
# ---------------------------------------------------------------------------

def test_section_helpers():
    section = PlayerDurabilityLoad()
    assert section.section_key() == "durability_load"
    assert section.sec_fn_name() == "sec_durability_load"
    assert section.parquet_name() == "atlas_player_durability_load.parquet"


# ---------------------------------------------------------------------------
# 8. Internal helper: _count_injury_spells
# ---------------------------------------------------------------------------

def test_count_injury_spells_empty():
    assert _count_injury_spells([]) == 0


def test_count_injury_spells_single():
    assert _count_injury_spells(["2024-01-01"]) == 1


def test_count_injury_spells_consecutive_same_spell():
    # Gap <= 7 days → same spell
    dates = ["2024-01-01", "2024-01-03", "2024-01-05"]
    assert _count_injury_spells(dates, gap_days=7) == 1


def test_count_injury_spells_two_spells():
    # First cluster Jan, second cluster Mar → 2 spells
    dates = ["2024-01-01", "2024-01-03", "2024-03-10", "2024-03-12"]
    assert _count_injury_spells(dates, gap_days=7) == 2


# ---------------------------------------------------------------------------
# 9. Player with only adv_stats (no DNP data) still builds
# ---------------------------------------------------------------------------

def test_build_with_only_adv_stats():
    """Player 9999 has no DNP records but has adv_stats — should build."""
    section = PlayerDurabilityLoad()
    as_of = _dt.datetime(2025, 1, 1)

    adv_only = pd.DataFrame({
        "player_id": [9999],
        "game_id":   ["G99"],
        "game_date": ["2024-06-01"],
        "minutes":   [30.0],
        "usagepercentage": [0.25],
    })
    bio_only = pd.DataFrame({
        "player_id": [9999],
        "player_name": ["Ghost Player"],
        "age_precise_days_as_of": [9855.0],
        "years_in_league_as_of": [5],
        "profile_as_of": ["2026-05-27"],
        "season_exp": [5],
        "from_year": [2019],
        "to_year": [2025],
    })

    patches = _patch_loaders(
        dnp=pd.DataFrame(columns=_FAKE_DNP.columns),
        dnp_feat=pd.DataFrame(columns=_FAKE_DNP_FEAT.columns),
        inj=pd.DataFrame(columns=_FAKE_INJURY.columns),
        bio=bio_only,
        adv=adv_only,
    )
    art = _apply_patches(patches, section.build, 9999, as_of)

    # Should build from adv_stats + bio alone
    assert art is not None
    assert art.sub_fields["minutes_per_game_mean"] == pytest.approx(30.0, abs=0.01)
    # DNP-derived fields should be None (no data)
    assert art.sub_fields["games_missed_injury_total"] is None
    assert art.sub_fields["injury_dnp_rate"] is None
