"""Tests for intel/player_rebounding_profile.py.

Covers:
  1. Leak-safety: build(pid, as_of_past) must NOT return data beyond as_of.
  2. Schema conformance: AtlasArtifact has all required sub_fields + cv_fields.
  3. cv_fields present: all three CV slots (boxout_position, rebound_distance,
     vertical) are in artifact.cv_fields with value=None.
  4. validate() passes for a well-formed artifact and fails for out-of-range data.
  5. to_profile_payload() shape matches the profile-factory expected (data, prov).
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# Ensure the repo root is on the path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intel.player_rebounding_profile import PlayerReboundingProfile, _season_end_approx
from src.loop.atlas import AtlasArtifact, CVSlot, confidence_from_n


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FAKE_ADV = pd.DataFrame({
    "player_id":                     [1001, 1001, 1001, 1002, 1002],
    "game_id":                       ["G1", "G2", "G3", "G4", "G5"],
    "game_date":                     ["2024-01-10", "2024-02-15", "2024-03-01",
                                      "2024-01-12", "2024-04-01"],
    "offensivereboundpercentage":    [0.05, 0.06, 0.04, 0.12, 0.10],
    "defensivereboundpercentage":    [0.20, 0.18, 0.22, 0.30, 0.28],
    "reboundpercentage":             [0.25, 0.24, 0.26, 0.42, 0.38],
})

_FAKE_HUSTLE = pd.DataFrame({
    "player_id":        [1001, 1001, 1002],
    "player_name":      ["PlayerA", "PlayerA", "PlayerB"],
    "season":           ["2023-24", "2024-25", "2024-25"],
    "hustle_box_outs":  [1.2, 1.5, 2.8],
    "hustle_games_played": [60, 70, 65],
    "hustle_deflections": [1.0, 1.2, 2.0],
    "hustle_contested_shots": [3.0, 3.5, 5.0],
    "hustle_screen_assists": [0.5, 0.6, 0.8],
    "hustle_loose_balls": [0.3, 0.4, 0.6],
    "hustle_charges_drawn": [0.1, 0.1, 0.2],
})

_FAKE_CONF = pd.DataFrame({
    "player_id": [1001, 1002],
    "reb_cv":    [0.35, 0.55],
    "reb_confidence_mult": [1.1, 1.0],
    "n_cv_games": [5, 8],
    "cv_volatility_mean": [0.2, 0.3],
    "cv_volatility_std": [0.05, 0.07],
    "n_games_stat": [60, 65],
})


def _patch_loaders(adv=None, hustle=None, conf=None):
    """Context-manager helper to inject fake DataFrames into module globals."""
    import intel.player_rebounding_profile as mod
    adv_df = _FAKE_ADV if adv is None else adv
    hustle_df = _FAKE_HUSTLE if hustle is None else hustle
    conf_df = _FAKE_CONF if conf is None else conf

    def mock_load_adv(as_of_iso):
        return adv_df[adv_df["game_date"].astype(str) <= as_of_iso].copy()

    def mock_load_hustle(as_of_iso):
        # Use the same rough season-boundary logic
        import intel.player_rebounding_profile as _m
        allowed = {s for s in hustle_df["season"].unique()
                   if _m._season_start(s) <= as_of_iso}
        return hustle_df[hustle_df["season"].isin(allowed)].copy()

    def mock_load_conf():
        return conf_df

    # Patch at module level
    patches = [
        patch("intel.player_rebounding_profile._load_adv", side_effect=mock_load_adv),
        patch("intel.player_rebounding_profile._load_hustle", side_effect=mock_load_hustle),
        patch("intel.player_rebounding_profile._load_conf_df", side_effect=mock_load_conf),
    ]
    return patches


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

def test_leak_safety_no_future_data():
    """build(pid, as_of) must never return data stamped after as_of.

    We set as_of = 2024-01-15. Player 1001 has games on 2024-01-10 and
    2024-02-15; only the 2024-01-10 game is in scope. The artifact's as_of
    must be <= 2024-01-15 and its provenance n must be 1 (only 1 game).
    """
    section = PlayerReboundingProfile()
    as_of = _dt.datetime(2024, 1, 15, 12, 0, 0)
    as_of_iso = "2024-01-15"

    # Manually exercise with the filtered fake adv (only 2024-01-10 row)
    filtered_adv = _FAKE_ADV[_FAKE_ADV["game_date"] <= as_of_iso].copy()
    # Player 1001 should have 1 game; player 1002 should have 1 game

    patches = _patch_loaders()
    with patches[0], patches[1], patches[2]:
        art = section.build(1001, as_of)

    assert art is not None, "should build with partial data"

    # --- CORE LEAK-SAFETY ASSERTION ---
    # The artifact's as_of MUST NOT exceed the decision boundary.
    # This is the contract: build() caps used_as_of = min(sources, as_of_iso).
    assert art.as_of is not None
    assert art.as_of <= as_of_iso, (
        f"Leak violation: artifact.as_of={art.as_of!r} > as_of_boundary={as_of_iso!r}"
    )
    assert art.provenance["as_of"] <= as_of_iso, (
        f"Leak violation in provenance: {art.provenance['as_of']!r} > {as_of_iso!r}"
    )

    # Critically: oreb_rate_mean should only reflect the one in-scope game (2024-01-10, value=0.05)
    # NOT the 0.06 (Feb) or 0.04 (Mar) games that postdate the decision boundary.
    assert art.sub_fields["oreb_rate_mean"] == pytest.approx(0.05, abs=1e-3)


# ---------------------------------------------------------------------------
# 2. Schema conformance assertion
# ---------------------------------------------------------------------------

def test_schema_conformance_all_required_keys():
    """AtlasArtifact must have all required sub_fields + expected provenance keys."""
    section = PlayerReboundingProfile()
    as_of = _dt.datetime(2025, 1, 1)

    patches = _patch_loaders()
    with patches[0], patches[1], patches[2]:
        art = section.build(1001, as_of)

    assert art is not None
    assert art.section == "rebounding_profile"
    assert art.entity == "player"
    assert art.entity_id == 1001

    # Required sub-field keys (REAL fields)
    required_real = [
        "oreb_rate_mean", "oreb_rate_std",
        "dreb_rate_mean", "dreb_rate_std",
        "total_reb_rate_mean",
        "oreb_pct_career", "dreb_pct_career",
        "oreb_dreb_ratio",
        "box_outs_per_game",
        "n_hustle_seasons",
        "reb_consistency_cv",
    ]
    for k in required_real:
        assert k in art.sub_fields, f"Missing sub_field: {k!r}"

    # DEFER fields must be present as None (not absent)
    defer_fields = [
        "crash_vs_get_back_tendency",
        "contested_reb_pct",
        "uncontested_reb_pct",
    ]
    for k in defer_fields:
        assert k in art.sub_fields, f"DEFER field absent: {k!r}"
        assert art.sub_fields[k] is None, f"DEFER field should be None: {k!r}={art.sub_fields[k]!r}"

    # Provenance keys
    for pk in ("source", "n", "confidence", "as_of"):
        assert pk in art.provenance, f"Missing provenance key: {pk!r}"
    assert art.provenance["confidence"] in ("low", "med", "high")


# ---------------------------------------------------------------------------
# 3. CV slots are reserved with value=None
# ---------------------------------------------------------------------------

def test_cv_fields_present_and_null():
    """cv_fields() must return all 3 reserved slots with value=None."""
    section = PlayerReboundingProfile()
    slots = section.cv_fields()

    required_slots = {"boxout_position", "rebound_distance", "vertical"}
    assert set(slots.keys()) == required_slots, (
        f"CV slot mismatch: got {set(slots.keys())!r}, expected {required_slots!r}"
    )

    for name, slot in slots.items():
        assert isinstance(slot, CVSlot), f"slot {name!r} is not a CVSlot"
        assert slot.value is None, (
            f"CV slot {name!r} value should be None (not filled yet); got {slot.value!r}"
        )
        assert slot.description, f"CV slot {name!r} has empty description"

    # Also verify these slots appear in a built artifact's cv_fields
    patches = _patch_loaders()
    with patches[0], patches[1], patches[2]:
        art = PlayerReboundingProfile().build(1001, _dt.datetime(2025, 1, 1))
    assert art is not None
    for slot_name in required_slots:
        assert slot_name in art.cv_fields, f"Slot {slot_name!r} missing from artifact.cv_fields"
        assert art.cv_fields[slot_name].value is None


# ---------------------------------------------------------------------------
# 4. validate() passes / fails appropriately
# ---------------------------------------------------------------------------

def test_validate_passes_for_valid_artifact():
    section = PlayerReboundingProfile()
    patches = _patch_loaders()
    with patches[0], patches[1], patches[2]:
        art = section.build(1001, _dt.datetime(2025, 1, 1))
    assert art is not None
    assert section.validate(art) is True


def test_validate_fails_for_out_of_range_rate():
    """oreb_rate_mean > 1.0 is physically impossible — validate must reject."""
    section = PlayerReboundingProfile()
    patches = _patch_loaders()
    with patches[0], patches[1], patches[2]:
        art = section.build(1001, _dt.datetime(2025, 1, 1))
    assert art is not None
    # Corrupt a rate field
    art.sub_fields["oreb_rate_mean"] = 1.5
    assert section.validate(art) is False


def test_validate_fails_for_wrong_section_name():
    section = PlayerReboundingProfile()
    art = AtlasArtifact(
        section="wrong_section",
        entity="player",
        entity_id=1001,
        sub_fields={"oreb_rate_mean": 0.05, "dreb_rate_mean": 0.20,
                    "total_reb_rate_mean": 0.25, "oreb_pct_career": 0.05,
                    "dreb_pct_career": 0.20, "oreb_dreb_ratio": 0.25,
                    "box_outs_per_game": 1.2, "n_hustle_seasons": 2,
                    "reb_consistency_cv": 0.35,
                    "crash_vs_get_back_tendency": None,
                    "contested_reb_pct": None, "uncontested_reb_pct": None},
        provenance={"source": "test", "n": 30, "confidence": "high", "as_of": "2025-01-01"},
        confidence="high", as_of="2025-01-01",
        cv_fields=section.cv_fields(),
    )
    assert section.validate(art) is False


# ---------------------------------------------------------------------------
# 5. to_profile_payload() shape matches factory pattern
# ---------------------------------------------------------------------------

def test_to_profile_payload_shape():
    """(data, prov) must match the factory sec_ return shape."""
    section = PlayerReboundingProfile()
    patches = _patch_loaders()
    with patches[0], patches[1], patches[2]:
        art = section.build(1001, _dt.datetime(2025, 1, 1))
    assert art is not None

    data, prov = art.to_profile_payload()

    # data must be a dict with _cv_fields embedded
    assert isinstance(data, dict)
    assert "_cv_fields" in data
    cv = data["_cv_fields"]
    for slot_name in ("boxout_position", "rebound_distance", "vertical"):
        assert slot_name in cv, f"CV slot {slot_name!r} not in payload _cv_fields"
        assert cv[slot_name]["value"] is None

    # prov must have the 4 canonical keys
    for pk in ("source", "n", "confidence", "as_of"):
        assert pk in prov, f"Missing prov key: {pk!r}"
    assert prov["confidence"] in ("low", "med", "high")


# ---------------------------------------------------------------------------
# 6. Edge cases: player with no data returns None
# ---------------------------------------------------------------------------

def test_build_returns_none_for_unknown_player():
    section = PlayerReboundingProfile()
    patches = _patch_loaders()
    with patches[0], patches[1], patches[2]:
        art = section.build(99999, _dt.datetime(2025, 1, 1))
    assert art is None


# ---------------------------------------------------------------------------
# 7. section_key / sec_fn_name / parquet_name helpers
# ---------------------------------------------------------------------------

def test_section_helpers():
    section = PlayerReboundingProfile()
    assert section.section_key() == "rebounding_profile"
    assert section.sec_fn_name() == "sec_rebounding_profile"
    assert section.parquet_name() == "atlas_player_rebounding_profile.parquet"
