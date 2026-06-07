"""Tests for intel/player_catch_shoot_vs_pullup.py -- leak-safety + schema conformance.

Run with:
    NBA_OFFLINE=1 python -m pytest tests/test_intel_player_catch_shoot_vs_pullup.py -v
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Optional
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import intel.player_catch_shoot_vs_pullup as _mod
from intel.player_catch_shoot_vs_pullup import PlayerCatchShootVsPullup
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JOKIC_ID = 203999
CURRY_ID = 201939
AS_OF = _dt.datetime(2026, 5, 1)


def _minimal_tracking_df(pid: int) -> pd.DataFrame:
    """Single-row player_tracking with all trk_cs_* fields present."""
    return pd.DataFrame([{
        "player_id": pid,
        "season": "2025-26",
        "trk_cs_fga": 4.5,
        "trk_cs_fg_pct": 0.42,
        "trk_cs_efg_pct": 0.61,
        "trk_cs_pts": 5.3,
        "trk_drv_count": 6.0,
        "trk_drv_fg_pct": 0.50,
        "trk_drv_pts": 4.1,
    }])


def _minimal_playtypes_df(pid: int) -> pd.DataFrame:
    """Playtypes rows for Spotup / Isolation / PRBallHandler / OffScreen."""
    return pd.DataFrame([
        {"player_id": pid, "season": "2025-26", "play_type": "Spotup",       "freq_pct": 0.12, "ppp": 1.10},
        {"player_id": pid, "season": "2025-26", "play_type": "Isolation",    "freq_pct": 0.10, "ppp": 0.95},
        {"player_id": pid, "season": "2025-26", "play_type": "PRBallHandler", "freq_pct": 0.20, "ppp": 0.88},
        {"player_id": pid, "season": "2025-26", "play_type": "OffScreen",    "freq_pct": 0.05, "ppp": 1.05},
        {"player_id": pid, "season": "2025-26", "play_type": "Handoff",      "freq_pct": 0.07, "ppp": 1.15},
    ])


def _minimal_pbp_df(pid: int, n_games: int = 20, base_date: str = "2026-01-01") -> pd.DataFrame:
    """Per-game pbp_possession_features rows."""
    dates = pd.date_range(base_date, periods=n_games, freq="3D")
    return pd.DataFrame({
        "player_id": pid,
        "game_id": [f"00{i:08d}" for i in range(n_games)],
        "game_date": dates,
        "pbp_iso_poss_count": [2.0] * n_games,
        "pbp_pnr_ball_handler": [3.0] * n_games,
        "pbp_pnr_screener_proxy": [1.0] * n_games,
        "pbp_post_up_count": [0.5] * n_games,
        "pbp_transition_count": [1.5] * n_games,
        "pbp_late_clock_shots": [0.8] * n_games,
        "pbp_clutch_shots_attempted": [0.3] * n_games,
        "pbp_clutch_pts_scored": [0.6] * n_games,
        "pbp_and1_count": [0.1] * n_games,
        "pbp_avg_seconds_per_touch": [2.5] * n_games,
    })


def _patch_caches(trk_df: pd.DataFrame, pt_df: pd.DataFrame, pbp_df: pd.DataFrame) -> dict:
    """Return a replacement _SRC_CACHE dict for patching."""
    return {
        "trk26": trk_df,
        "trk_base": trk_df,
        "pt26": pt_df,
        "pt_base": pt_df,
        "pbp_poss_cs": pbp_df,
        "adv_cs": pd.DataFrame(columns=["player_id", "game_date"]),
    }


# ---------------------------------------------------------------------------
# 1. Schema conformance tests
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Validate that the built artifact matches the required schema."""

    def test_required_sub_field_keys_present(self):
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        assert art is not None
        assert set(art.sub_fields.keys()) >= {"catch_shoot", "pull_up", "off_dribble_3", "time_to_shot"}

    def test_section_and_entity_attributes(self):
        section = PlayerCatchShootVsPullup()
        assert section.name == "catch_shoot_vs_pullup"
        assert section.entity == "player"

    def test_proportions_in_range(self):
        """All *_pct / *_rate / *_share sub-fields must be in [0, 1] (eFG up to 1.6)."""
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        assert art is not None

        def check_sub(sub: dict) -> None:
            for k, v in sub.items():
                if isinstance(v, float) and ("_pct" in k or "_rate" in k or "_share" in k):
                    ceil = 1.6 if "efg" in k else 1.0
                    assert 0.0 <= v <= ceil, f"{k}={v} out of range [0,{ceil}]"

        for section_key in ("catch_shoot", "pull_up", "off_dribble_3"):
            check_sub(art.sub_fields[section_key])

    def test_cv_slots_reserved_and_null(self):
        """CV slots must be present with None values (not yet filled)."""
        section = PlayerCatchShootVsPullup()
        declared = section.cv_fields()
        assert "openness_on_cs" in declared
        assert "dribbles_pre_pull" in declared
        for name, slot in declared.items():
            assert isinstance(slot, CVSlot)
            assert slot.value is None, f"CV slot {name} must be null (reserved)"
            assert slot.dtype in {"float", "dist", "list", "categorical", "int"}

    def test_artifact_cv_fields_match_declared(self):
        """Artifact cv_fields must mirror the section's declared schema."""
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        assert art is not None
        declared = section.cv_fields()
        assert set(art.cv_fields.keys()) == set(declared.keys())
        for name, slot in art.cv_fields.items():
            assert slot.value is None

    def test_validate_returns_true_on_valid_artifact(self):
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        assert art is not None
        assert section.validate(art) is True

    def test_validate_fails_on_wrong_section(self):
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        art.section = "wrong_section"
        assert section.validate(art) is False

    def test_validate_fails_when_cv_slot_not_null(self):
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        # Manually fill a CV slot -- should fail validation
        art.cv_fields["openness_on_cs"] = CVSlot(
            name="openness_on_cs", dtype="float", value=4.2
        )
        assert section.validate(art) is False


# ---------------------------------------------------------------------------
# 2. Leak-safety tests
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that as_of filtering is enforced on per-game data sources."""

    def test_pbp_data_filtered_to_as_of(self):
        """Games AFTER as_of must not affect the build."""
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID

        # 10 games before as_of, 10 games after
        before = _minimal_pbp_df(pid, n_games=10, base_date="2025-10-01")
        after = _minimal_pbp_df(pid, n_games=10, base_date="2027-01-01")
        # Override avg_seconds_per_touch to a clearly different value in "future" rows
        after["pbp_avg_seconds_per_touch"] = 999.0
        combined = pd.concat([before, after], ignore_index=True)

        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)

        cache = _patch_caches(trk, pt, combined)
        with patch.dict(_mod._SRC_CACHE, cache, clear=True):
            art = section.build(pid, AS_OF)

        assert art is not None
        tts = art.sub_fields.get("time_to_shot", {})
        # avg should be 2.5 (from "before" rows only), not contaminated by 999.0
        avg = tts.get("avg_seconds_per_touch")
        assert avg is not None
        assert avg < 100.0, f"Future data leaked into time_to_shot: avg={avg}"

    def test_as_of_stored_in_provenance(self):
        """Provenance as_of must equal the build date, not any future date."""
        section = PlayerCatchShootVsPullup()
        pid = CURRY_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        assert art is not None
        assert art.as_of == AS_OF.date().isoformat()
        assert art.provenance["as_of"] == AS_OF.date().isoformat()

    def test_provenance_n_is_game_count_not_seasons(self):
        """n in provenance must be a per-game count (>= 5 for med confidence)."""
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid, n_games=25)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        assert art is not None
        n = art.provenance["n"]
        assert n >= 5, f"n={n} fails coverage gate min_n=5"
        assert n >= 20, f"Expected high confidence with 25 games, got n={n}"
        assert art.confidence in ("med", "high")

    def test_build_returns_none_when_all_sources_empty(self):
        """Must return None (skip) when there is no data for a player."""
        section = PlayerCatchShootVsPullup()
        empty_trk = pd.DataFrame(columns=["player_id", "season"])
        empty_pt = pd.DataFrame(columns=["player_id", "season", "play_type", "freq_pct", "ppp"])
        empty_pbp = pd.DataFrame(columns=["player_id", "game_id", "game_date"])

        cache = _patch_caches(empty_trk, empty_pt, empty_pbp)
        with patch.dict(_mod._SRC_CACHE, cache, clear=True):
            art = section.build(99999999, AS_OF)

        assert art is None

    def test_early_as_of_does_not_include_later_games(self):
        """Re-building at an earlier as_of must yield n <= build at later as_of."""
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid, n_games=30, base_date="2025-10-01")

        # Split point: 15 games before 2026-01-15, 15 games after
        early_as_of = _dt.datetime(2026, 1, 15)
        late_as_of = _dt.datetime(2026, 5, 1)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art_early = section.build(pid, early_as_of)
            _mod._SRC_CACHE.clear()  # force reload
            _mod._SRC_CACHE.update(_patch_caches(trk, pt, pbp))
            art_late = section.build(pid, late_as_of)

        assert art_early is not None
        assert art_late is not None
        assert art_early.provenance["n"] <= art_late.provenance["n"], (
            f"Earlier as_of has n={art_early.provenance['n']} > "
            f"later as_of n={art_late.provenance['n']} -- possible leak"
        )


# ---------------------------------------------------------------------------
# 3. to_profile_payload contract
# ---------------------------------------------------------------------------

class TestProfilePayload:
    """Ensure the artifact serialises correctly for the profile factory."""

    def test_to_profile_payload_returns_data_and_prov(self):
        section = PlayerCatchShootVsPullup()
        pid = JOKIC_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        assert art is not None
        data, prov = art.to_profile_payload()
        assert isinstance(data, dict)
        assert isinstance(prov, dict)
        assert "n" in prov
        assert "confidence" in prov
        assert "as_of" in prov
        assert "_cv_fields" in data
        # CV fields in the payload must carry null values
        cv = data["_cv_fields"]
        for slot_name, slot_payload in cv.items():
            assert slot_payload.get("value") is None

    def test_pct_fields_not_above_1_in_payload(self):
        """Proportion fields must stay <= 1.0 after serialisation."""
        section = PlayerCatchShootVsPullup()
        pid = CURRY_ID
        trk = _minimal_tracking_df(pid)
        pt = _minimal_playtypes_df(pid)
        pbp = _minimal_pbp_df(pid)

        with patch.dict(_mod._SRC_CACHE, _patch_caches(trk, pt, pbp), clear=True):
            art = section.build(pid, AS_OF)

        assert art is not None

        def _walk(d: Any) -> None:
            if isinstance(d, dict):
                for k, v in d.items():
                    if isinstance(v, (int, float)) and ("_pct" in k or "_rate" in k):
                        ceil = 1.6 if "efg" in k else 1.0
                        assert 0.0 <= v <= ceil, f"{k}={v} out of [0,{ceil}]"
                    elif isinstance(v, dict):
                        _walk(v)

        _walk(art.sub_fields)
