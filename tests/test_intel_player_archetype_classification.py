"""Tests for intel/player_archetype_classification.py.

Covers:
  1. Leak-safety: build() must NOT read data stamped after as_of.
  2. Schema conformance: required sub-fields present + cv_fields schema correct.
  3. validate(): accepts a well-formed artifact, rejects malformed ones.
  4. cv_fields(): all slots have value=None and required attributes.
  5. build_and_register() dry_run: returns manifest with expected keys.
"""
from __future__ import annotations

import datetime as _dt
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure repo root is on the path (scripts run from repo root)
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("NBA_OFFLINE", "1")

from intel.player_archetype_classification import (
    PlayerArchetypeClassification,
    build_and_register,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Fixtures: minimal synthetic DataFrames that mimic each real parquet
# ---------------------------------------------------------------------------

_AS_OF_PAST = _dt.datetime(2025, 12, 1)    # the "safe" build date (no leakage)
_AS_OF_FUTURE = _dt.datetime(2027, 6, 1)   # a future date that must NOT be readable

_PLAYER_ID = 1628983  # SGA (arbitrary real ID for naming; synthetic data below)


def _make_kbest_df(pid: int) -> pd.DataFrame:
    """Minimal player_fingerprints_kbest row keyed by player_id index."""
    data = {
        "player_id": [pid, pid + 1],
        "n_cv_games": [15, 8],
        "archetype_id": [2, 1],
        "archetype_name": ["Off-Ball Forward", "Versatile Forward"],
        "dist_from_centroid": [1.23, 0.87],
        "k_value": [5, 5],
        "player_name": ["Test Player A", "Test Player B"],
        "paint_dwell_pct": [0.35, 0.12],
        "shot_zone_3pt_pct": [0.55, 0.67],
        "avg_shot_distance": [18.5, 22.1],
        "touches_per_game": [28.0, 14.3],
        "shots_per_possession": [0.04, 0.09],
        "contested_shot_rate": [0.55, 0.30],
        "avg_defender_distance": [5.2, 8.1],
    }
    return pd.DataFrame(data)


def _make_sidecar_df(pid: int) -> pd.DataFrame:
    return pd.DataFrame(
        {"player_id": [pid], "archetype_id": [2],
         "archetype_name": ["Off-Ball Forward"], "source": ["fingerprints_v1"]}
    )


def _make_drift_df(pid: int) -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [pid],
        "player_name": ["Test Player A"],
        "primary_archetype": [2],
        "primary_archetype_name": ["Off-Ball Forward"],
        "n_games": [20],
        "consistency_score": [0.75],
        "drift_tag": ["STABLE"],
        "recent_archetype_name": ["Off-Ball Forward"],
        "top_alternate_archetype_name": ["Versatile Big"],
        "archetype_distribution": [None],
    })


def _make_bio_df(pid: int) -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [pid],
        "player_name": ["Test Player A"],
        "position": ["Forward"],
        "season_exp": [8],
        "profile_as_of": ["2025-11-01"],
    })


def _make_adv_df(pid: int) -> pd.DataFrame:
    """Two rows: one before as_of, one AFTER as_of (future leak test)."""
    return pd.DataFrame({
        "player_id": [pid, pid],
        "game_id": ["0022501000", "0022601999"],
        "game_date": [
            pd.Timestamp("2025-11-15"),   # before as_of → READABLE
            pd.Timestamp("2026-03-01"),   # after as_of  → MUST BE EXCLUDED
        ],
        "usagepercentage": [0.27, 0.31],
        "trueshootingpercentage": [0.61, 0.64],
        "effectivefieldgoalpercentage": [0.54, 0.57],
        "offensiverating": [115.0, 118.5],
        "defensiverating": [109.0, 107.0],
        "netrating": [6.0, 11.5],
        "minutes": [34.0, 35.0],
    })


def _make_synergy_df(pid: int) -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [pid],
        "season": ["2024-25"],
        "syn_pnr_bh_ppp": [0.87],
        "syn_spotup_ppp": [1.12],
        "syn_iso_ppp": [0.91],
        "syn_postup_ppp": [0.78],
        "syn_transition_ppp": [1.25],
    })


# ---------------------------------------------------------------------------
# Helper: build artifact with mocked parquets
# ---------------------------------------------------------------------------

def _build_artifact(pid: int = _PLAYER_ID,
                    as_of: _dt.datetime = _AS_OF_PAST) -> Optional[AtlasArtifact]:
    """Build artifact with synthetic parquets injected via module-level _SRC_CACHE."""
    import intel.player_archetype_classification as _mod

    # Inject synthetic DataFrames directly into the module's cache
    _mod._SRC_CACHE.clear()
    _mod._SRC_CACHE["fp_kbest"] = _make_kbest_df(pid)
    _mod._SRC_CACHE["arch_sidecar"] = _make_sidecar_df(pid)
    _mod._SRC_CACHE["arch_drift"] = _make_drift_df(pid)
    _mod._SRC_CACHE["bio"] = _make_bio_df(pid)
    _mod._SRC_CACHE["adv"] = _make_adv_df(pid)
    _mod._SRC_CACHE["syn"] = _make_synergy_df(pid)

    section = PlayerArchetypeClassification()
    return section.build(pid, as_of)


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY ASSERTION
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() MUST exclude game_date > as_of from player_adv_stats."""

    def test_usage_n_games_excludes_future_rows(self) -> None:
        """With as_of=2025-12-01 and two adv rows (one in 2025, one in 2026),
        usage_efficiency.n_games must equal 1 (the 2025 row only)."""
        art = _build_artifact(as_of=_AS_OF_PAST)
        assert art is not None, "Expected artifact for known player"
        n_games = art.sub_fields.get("usage_efficiency", {}).get("n_games")
        assert n_games == 1, (
            f"Leak! usage_efficiency.n_games={n_games} but only 1 row is before as_of"
        )

    def test_future_as_of_sees_both_rows(self) -> None:
        """With as_of in 2027, both adv rows (2025 + 2026) are readable → n_games=2."""
        art = _build_artifact(as_of=_AS_OF_FUTURE)
        assert art is not None
        n_games = art.sub_fields.get("usage_efficiency", {}).get("n_games")
        assert n_games == 2, (
            f"Expected 2 games visible from 2027 as_of, got {n_games}"
        )

    def test_usage_values_reflect_only_past_row(self) -> None:
        """usage_pct should reflect the 2025-11-15 row (0.27), not the leaked 2026 row (0.31)."""
        art = _build_artifact(as_of=_AS_OF_PAST)
        assert art is not None
        usage_pct = art.sub_fields.get("usage_efficiency", {}).get("usage_pct")
        # Should be 0.27 (only the 2025 row)
        assert usage_pct is not None
        assert abs(usage_pct - 0.27) < 0.001, (
            f"Leak! usage_pct={usage_pct!r} — should be 0.27 (the pre-as_of row only)"
        )


# ---------------------------------------------------------------------------
# 2. SCHEMA CONFORMANCE ASSERTION
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact must have all required sub-fields and correct cv_fields schema."""

    def test_required_sub_fields_present(self) -> None:
        art = _build_artifact()
        assert art is not None
        required = {
            "archetype", "cluster_features", "drift", "scheme_role",
            "usage_efficiency", "synergy", "on_off_by_archetype", "scheme_interaction",
        }
        missing = required - set(art.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {missing}"

    def test_archetype_sub_has_name(self) -> None:
        art = _build_artifact()
        assert art is not None
        arch = art.sub_fields["archetype"]
        assert arch.get("primary_archetype_name") is not None
        assert isinstance(arch["primary_archetype_name"], str)

    def test_cv_fields_present_in_artifact(self) -> None:
        """cv_fields dict must be populated and contain the 4 reserved slots."""
        art = _build_artifact()
        assert art is not None
        assert isinstance(art.cv_fields, dict)
        expected_slots = {
            "cv_archetype_dist",
            "cv_spacing_profile",
            "cv_paint_touch_rate",
            "cv_ball_handler_rate",
        }
        assert expected_slots == set(art.cv_fields.keys()), (
            f"cv_fields keys mismatch: got {set(art.cv_fields.keys())}"
        )

    def test_cv_fields_all_none(self) -> None:
        """All CV slot values must be None (CV branch hasn't run yet)."""
        art = _build_artifact()
        assert art is not None
        for slot_name, slot in art.cv_fields.items():
            assert slot.value is None, (
                f"CV slot '{slot_name}' has value={slot.value!r} — must be None"
            )

    def test_cv_fields_have_dtype_and_description(self) -> None:
        """Each CVSlot must have a non-empty dtype and description."""
        section = PlayerArchetypeClassification()
        for slot_name, slot in section.cv_fields().items():
            assert isinstance(slot, CVSlot)
            assert slot.dtype, f"Slot '{slot_name}' missing dtype"
            assert slot.description, f"Slot '{slot_name}' missing description"
            assert slot.value is None

    def test_to_profile_payload_shape(self) -> None:
        """to_profile_payload() must return (data, prov) with _cv_fields embedded."""
        art = _build_artifact()
        assert art is not None
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data
        assert "source" in prov
        assert "confidence" in prov
        assert "n" in prov
        assert prov["n"] >= 1
        # cv slots embedded under _cv_fields in data
        for slot_name in ("cv_archetype_dist", "cv_spacing_profile",
                          "cv_paint_touch_rate", "cv_ball_handler_rate"):
            assert slot_name in data["_cv_fields"], (
                f"CV slot '{slot_name}' not embedded in data['_cv_fields']"
            )
            assert data["_cv_fields"][slot_name]["value"] is None

    def test_section_name_and_entity(self) -> None:
        section = PlayerArchetypeClassification()
        assert section.name == "archetype_classification"
        assert section.entity == "player"

    def test_parquet_name(self) -> None:
        section = PlayerArchetypeClassification()
        assert section.parquet_name() == "atlas_player_archetype_classification.parquet"

    def test_sec_fn_name(self) -> None:
        section = PlayerArchetypeClassification()
        assert section.sec_fn_name() == "sec_archetype_classification"


# ---------------------------------------------------------------------------
# 3. VALIDATE METHOD
# ---------------------------------------------------------------------------

class TestValidate:
    """Validate accepts well-formed artifacts, rejects malformed ones."""

    def test_valid_artifact_passes(self) -> None:
        art = _build_artifact()
        section = PlayerArchetypeClassification()
        assert art is not None
        assert section.validate(art) is True

    def test_wrong_section_rejected(self) -> None:
        art = _build_artifact()
        assert art is not None
        art.section = "wrong_section"
        section = PlayerArchetypeClassification()
        assert section.validate(art) is False

    def test_missing_archetype_name_rejected(self) -> None:
        art = _build_artifact()
        assert art is not None
        art.sub_fields["archetype"]["primary_archetype_name"] = None
        section = PlayerArchetypeClassification()
        assert section.validate(art) is False

    def test_out_of_range_usage_pct_rejected(self) -> None:
        art = _build_artifact()
        assert art is not None
        art.sub_fields["usage_efficiency"]["usage_pct"] = 1.5  # > 1.0 = invalid
        section = PlayerArchetypeClassification()
        assert section.validate(art) is False

    def test_filled_cv_slot_rejected(self) -> None:
        """If CV branch mistakenly pre-fills a slot, validate must reject."""
        art = _build_artifact()
        assert art is not None
        art.cv_fields["cv_archetype_dist"].value = 2.5
        section = PlayerArchetypeClassification()
        assert section.validate(art) is False


# ---------------------------------------------------------------------------
# 4. build() RETURNS NONE FOR UNKNOWN PLAYER
# ---------------------------------------------------------------------------

class TestMissingPlayer:
    """build() returns None for a player absent from all archetype sources."""

    def test_unknown_player_returns_none(self) -> None:
        import intel.player_archetype_classification as _mod
        _mod._SRC_CACHE.clear()
        _mod._SRC_CACHE["fp_kbest"] = _make_kbest_df(9999)   # different pid
        _mod._SRC_CACHE["arch_sidecar"] = _make_sidecar_df(9999)
        _mod._SRC_CACHE["arch_drift"] = _make_drift_df(9999)
        _mod._SRC_CACHE["bio"] = _make_bio_df(9999)
        _mod._SRC_CACHE["adv"] = _make_adv_df(9999)
        _mod._SRC_CACHE["syn"] = _make_synergy_df(9999)

        section = PlayerArchetypeClassification()
        art = section.build(1111, _AS_OF_PAST)  # pid=1111 not in any df
        assert art is None


# ---------------------------------------------------------------------------
# 5. build_and_register DRY-RUN
# ---------------------------------------------------------------------------

class TestBuildAndRegisterDryRun:
    """build_and_register with dry_run=True should return a valid manifest."""

    def test_dry_run_returns_manifest(self) -> None:
        import intel.player_archetype_classification as _mod
        _mod._SRC_CACHE.clear()
        _mod._SRC_CACHE["fp_kbest"] = _make_kbest_df(_PLAYER_ID)
        _mod._SRC_CACHE["arch_sidecar"] = _make_sidecar_df(_PLAYER_ID)
        _mod._SRC_CACHE["arch_drift"] = _make_drift_df(_PLAYER_ID)
        _mod._SRC_CACHE["bio"] = _make_bio_df(_PLAYER_ID)
        _mod._SRC_CACHE["adv"] = _make_adv_df(_PLAYER_ID)
        _mod._SRC_CACHE["syn"] = _make_synergy_df(_PLAYER_ID)

        manifest = build_and_register(
            player_ids=[_PLAYER_ID],
            as_of=_AS_OF_PAST,
            dry_run=True,
        )
        assert isinstance(manifest, dict)
        assert manifest.get("section") == "archetype_classification"
        assert manifest.get("n_entities", 0) >= 1
        assert "cv_fields" in manifest
        assert set(manifest["cv_fields"]) == {
            "cv_archetype_dist", "cv_spacing_profile",
            "cv_paint_touch_rate", "cv_ball_handler_rate",
        }
        assert manifest.get("sec_fn") == "sec_archetype_classification"
