"""Tests for intel/player_foul_tendency.py — PlayerFoulTendency AtlasSection.

Covers:
  1. Schema-conformance: AtlasArtifact has all required sub-field keys and
     all cv_fields present (contract is stable / CV-slot shape matches spec).
  2. Leak-safety: build() with a strict as_of boundary never returns data
     stamped after that boundary.
  3. Validate() rejects malformed artifacts.
  4. cv_fields() always returns exactly 3 slots, all with value=None.
  5. build_and_register() dry_run returns a valid manifest without disk I/O.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import pytest

# Ensure repo root is on sys.path for NBA_OFFLINE-safe imports
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import os
os.environ.setdefault("NBA_OFFLINE", "1")

from src.loop.atlas import AtlasArtifact, CVSlot
from intel.player_foul_tendency import (
    PlayerFoulTendency,
    _SRC_CACHE,
    build_and_register,
)

# ---------------------------------------------------------------------------
# Helpers: minimal synthetic DataFrames that mirror real parquet schemas
# ---------------------------------------------------------------------------

_PLAYER_ID = 999999  # synthetic; absent from all real data


def _make_section() -> PlayerFoulTendency:
    return PlayerFoulTendency()


def _make_real_dataframes(pid: int, game_date: str) -> None:
    """Inject synthetic per-game rows into the module-level cache for one player.

    This approach sidesteps disk I/O while exercising the full aggregation logic.
    We clear and repopulate _SRC_CACHE so each test group starts clean.
    """
    import numpy as np

    game_id = "0022400001"

    # foul_features: one game row
    _SRC_CACHE["foul_feat"] = pd.DataFrame([{
        "player_id": pid,
        "game_id": game_id,
        "game_date": pd.Timestamp(game_date),
        "team_abbreviation": "TST",
        "pf_per_36_l5": 3.5,
        "pf_per_36_l10": 3.2,
        "foul_trouble_rate_l10": 0.2,
        "last_game_pf": 2,
        "min_l5": 32.0,
    }])

    # player_pf: one game row
    _SRC_CACHE["pf_raw"] = pd.DataFrame([{
        "game_id": game_id,
        "player_id": pid,
        "team_abbreviation": "TST",
        "game_date": game_date,
        "pf": 2.0,
        "min": 32.0,
    }])
    _SRC_CACHE["pf_raw_disc"] = _SRC_CACHE["pf_raw"]

    # player_pf_per36: one row
    _SRC_CACHE["pf_per36"] = pd.DataFrame([{
        "player_id": pid,
        "game_date": pd.Timestamp(game_date),
        "season_pf_per_36": 3.1,
    }])

    # player_quarter_stats: 4 quarters for one game
    qrows = []
    for period, pf_val in [(1, 1.0), (2, 0.0), (3, 1.0), (4, 0.0)]:
        qrows.append({
            "game_id": game_id,
            "player_id": pid,
            "period": period,
            "pf": pf_val,
            "min": 8.0,
            "pts": 4.0,
            "reb": 2.0,
            "ast": 1.0,
            "fg3m": 0.0,
            "stl": 0.0,
            "blk": 0.0,
            "tov": 0.0,
            "plus_minus": 2.0,
        })
    _SRC_CACHE["qstats"] = pd.DataFrame(qrows)

    # hustle features: fresh season
    _SRC_CACHE["hustle26"] = pd.DataFrame([{
        "player_id": pid,
        "player_name": "Test Player",
        "season": "2025-26",
        "hustle_games_played": 40.0,
        "hustle_deflections": 1.2,
        "hustle_contested_shots": 3.5,
        "hustle_screen_assists": 0.5,
        "hustle_box_outs": 2.1,
        "hustle_loose_balls": 0.3,
        "hustle_charges_drawn": 0.15,
    }])
    # no fallback needed since hustle26 is present


def _clear_cache() -> None:
    _SRC_CACHE.clear()


# ---------------------------------------------------------------------------
# 1. cv_fields contract
# ---------------------------------------------------------------------------

class TestCVFields:
    def test_returns_exactly_three_slots(self) -> None:
        s = _make_section()
        cv = s.cv_fields()
        assert len(cv) == 3, f"Expected 3 CV slots, got {len(cv)}"

    def test_expected_slot_names(self) -> None:
        s = _make_section()
        cv = s.cv_fields()
        expected = {
            "contest_proximity_at_foul",
            "foul_body_angle",
            "spacing_at_foul_commit",
        }
        assert set(cv.keys()) == expected

    def test_all_values_are_none(self) -> None:
        """CV slots must be null until the CV branch fills them."""
        s = _make_section()
        for name, slot in s.cv_fields().items():
            assert isinstance(slot, CVSlot), f"Slot {name!r} is not a CVSlot"
            assert slot.value is None, (
                f"CV slot {name!r} has non-None value {slot.value!r} — "
                "CV branch hasn't run; values must be reserved-null."
            )

    def test_slot_types_and_units(self) -> None:
        s = _make_section()
        cv = s.cv_fields()
        assert cv["contest_proximity_at_foul"].unit == "ft"
        assert cv["foul_body_angle"].unit == "deg"
        assert cv["spacing_at_foul_commit"].unit == "ft²"
        assert cv["contest_proximity_at_foul"].dtype == "float"


# ---------------------------------------------------------------------------
# 2. Schema-conformance (artifact shape)
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    def setup_method(self) -> None:
        _clear_cache()
        _make_real_dataframes(_PLAYER_ID, "2025-01-15")

    def teardown_method(self) -> None:
        _clear_cache()

    def _build(self) -> Optional[AtlasArtifact]:
        s = _make_section()
        as_of = _dt.datetime(2025, 6, 1)  # well after the synthetic game
        return s.build(_PLAYER_ID, as_of)

    def test_build_returns_artifact(self) -> None:
        art = self._build()
        assert art is not None, "build() returned None for a player with real data"

    def test_section_and_entity_fields(self) -> None:
        art = self._build()
        assert art.section == "foul_tendency"
        assert art.entity == "player"
        assert art.entity_id == _PLAYER_ID

    def test_required_sub_field_keys_present(self) -> None:
        art = self._build()
        required = {"committed", "by_quarter", "early_trouble", "foul_out_risk",
                    "charges_drawn", "drawn", "by_type"}
        missing = required - set(art.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {missing}"

    def test_defer_stubs_have_note(self) -> None:
        art = self._build()
        for key in ["drawn", "by_type"]:
            stub = art.sub_fields[key]
            assert "_note" in stub, f"DEFER stub '{key}' missing '_note'"
            assert "DEFER" in stub["_note"], (
                f"DEFER stub '{key}' note doesn't contain 'DEFER': {stub['_note']!r}"
            )

    def test_cv_fields_present_on_artifact(self) -> None:
        art = self._build()
        assert art.cv_fields, "cv_fields dict is empty"
        expected = {"contest_proximity_at_foul", "foul_body_angle", "spacing_at_foul_commit"}
        assert set(art.cv_fields.keys()) == expected

    def test_cv_fields_all_null_on_artifact(self) -> None:
        art = self._build()
        for name, slot in art.cv_fields.items():
            assert slot.value is None, (
                f"CV slot {name!r} on artifact has value {slot.value!r} — must be null."
            )

    def test_provenance_keys(self) -> None:
        art = self._build()
        for k in ["source", "n", "confidence", "as_of"]:
            assert k in art.provenance, f"provenance missing key: {k!r}"
        assert art.provenance["n"] >= 1

    def test_confidence_level_valid(self) -> None:
        art = self._build()
        assert art.confidence in ("low", "med", "high")

    def test_validate_passes_for_good_artifact(self) -> None:
        s = _make_section()
        art = self._build()
        assert s.validate(art), "validate() failed for a well-formed artifact"

    def test_to_profile_payload_shape(self) -> None:
        art = self._build()
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data
        for slot_name in ("contest_proximity_at_foul", "foul_body_angle",
                          "spacing_at_foul_commit"):
            assert slot_name in data["_cv_fields"], (
                f"CV slot {slot_name!r} missing from to_profile_payload() output"
            )
        assert prov["confidence"] in ("low", "med", "high")


# ---------------------------------------------------------------------------
# 3. Leak-safety assertion (core contract)
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Leak-safety: build() with as_of BEFORE the game date must return None or
    an artifact containing no data from after the as_of boundary.

    We inject data stamped on 2025-01-15 and call build() with as_of=2025-01-01
    (14 days earlier).  The player must appear to have NO game data (None return
    or an artifact whose committed.n_games == 0).
    """

    def setup_method(self) -> None:
        _clear_cache()
        _make_real_dataframes(_PLAYER_ID, "2025-01-15")

    def teardown_method(self) -> None:
        _clear_cache()

    def test_as_of_before_all_data_returns_none_or_empty(self) -> None:
        s = _make_section()
        # as_of is 2 weeks before the only game in our synthetic data
        as_of_early = _dt.datetime(2025, 1, 1)
        art = s.build(_PLAYER_ID, as_of_early)
        if art is not None:
            # If returned, committed.n_games must be 0 (no games seen)
            n = art.sub_fields.get("committed", {}).get("n_games", 0)
            assert n == 0, (
                f"Leak violation: build() returned an artifact with n_games={n} "
                f"for as_of={as_of_early.date()} but all data is stamped 2025-01-15."
            )

    def test_as_of_on_game_date_includes_data(self) -> None:
        """as_of exactly on the game date must include that game."""
        s = _make_section()
        # Timestamp is end-of-day on 2025-01-15 — the synthetic game date
        as_of_same = _dt.datetime(2025, 1, 15, 23, 59, 59)
        art = s.build(_PLAYER_ID, as_of_same)
        assert art is not None, (
            "build() returned None for as_of exactly on the game date — "
            "should include that game."
        )


# ---------------------------------------------------------------------------
# 4. Validate rejects malformed artifacts
# ---------------------------------------------------------------------------

class TestValidateRejects:
    def setup_method(self) -> None:
        _clear_cache()
        _make_real_dataframes(_PLAYER_ID, "2025-01-15")

    def teardown_method(self) -> None:
        _clear_cache()

    def _good_artifact(self) -> AtlasArtifact:
        s = _make_section()
        art = s.build(_PLAYER_ID, _dt.datetime(2025, 6, 1))
        assert art is not None
        return art

    def test_wrong_section_rejected(self) -> None:
        s = _make_section()
        art = self._good_artifact()
        art.section = "wrong_section"
        assert not s.validate(art)

    def test_wrong_entity_rejected(self) -> None:
        s = _make_section()
        art = self._good_artifact()
        art.entity = "team"
        assert not s.validate(art)

    def test_rate_out_of_range_rejected(self) -> None:
        s = _make_section()
        art = self._good_artifact()
        art.sub_fields["early_trouble"]["early_foul_trouble_rate"] = 1.5  # > 1.0
        assert not s.validate(art)

    def test_negative_pf_per36_rejected(self) -> None:
        s = _make_section()
        art = self._good_artifact()
        art.sub_fields["committed"]["pf_per_36_l5"] = -1.0
        assert not s.validate(art)

    def test_missing_sub_field_key_rejected(self) -> None:
        s = _make_section()
        art = self._good_artifact()
        del art.sub_fields["by_type"]
        assert not s.validate(art)

    def test_cv_field_non_null_rejected(self) -> None:
        s = _make_section()
        art = self._good_artifact()
        art.cv_fields["contest_proximity_at_foul"].value = 3.5  # CV already filled
        assert not s.validate(art)


# ---------------------------------------------------------------------------
# 5. build_and_register dry_run
# ---------------------------------------------------------------------------

class TestBuildAndRegisterDryRun:
    def setup_method(self) -> None:
        _clear_cache()
        _make_real_dataframes(_PLAYER_ID, "2025-01-15")

    def teardown_method(self) -> None:
        _clear_cache()

    def test_dry_run_returns_manifest(self) -> None:
        manifest = build_and_register(
            player_ids=[_PLAYER_ID],
            as_of=_dt.datetime(2025, 6, 1),
            dry_run=True,
        )
        assert isinstance(manifest, dict)
        assert manifest["section"] == "foul_tendency"
        assert manifest["n_entities"] >= 1
        assert "cv_fields" in manifest
        assert set(manifest["cv_fields"]) == {
            "contest_proximity_at_foul",
            "foul_body_angle",
            "spacing_at_foul_commit",
        }

    def test_dry_run_no_disk_write(self) -> None:
        """dry_run must not write the parquet."""
        cache_dir = _REPO / "data" / "cache"
        parquet_path = cache_dir / "atlas_player_foul_tendency.parquet"
        existed_before = parquet_path.exists()

        build_and_register(
            player_ids=[_PLAYER_ID],
            as_of=_dt.datetime(2025, 6, 1),
            dry_run=True,
        )

        # If the parquet didn't exist before, it must not exist after dry_run
        if not existed_before:
            assert not parquet_path.exists(), (
                "dry_run=True must not write the parquet to disk."
            )
