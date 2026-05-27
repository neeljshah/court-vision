"""
test_player_profile_wire.py — Verify prof_* features are wired into assemble_features.
"""

from __future__ import annotations

import math
import sys
import os

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

PROF_KEYS = [
    "prof_height_in",
    "prof_weight_lb",
    "prof_draft_year",
    "prof_draft_number",
    "prof_undrafted_flag",
    "prof_intl_flag",
    "prof_college_d1_flag",
    "prof_greatest_75_flag",
    "prof_age_days",
    "prof_years_in_league",
    "prof_rookie_flag",
    "prof_season_exp",
]

# Chris Paul — player_id=101108, confirmed in parquet
_KNOWN_PLAYER_ID = 101108
_KNOWN_GAME_ID = "0022400001"
_DATE = "2025-01-15"


class TestPlayerProfileLoader:
    def test_load_profiles_nonempty(self):
        from src.data.player_profile_loader import load_player_profiles
        df = load_player_profiles()
        assert len(df) > 0, "Expected at least one row in player_profile_features.parquet"

    def test_get_known_player(self):
        from src.data.player_profile_loader import get_player_profile
        prof = get_player_profile(_KNOWN_PLAYER_ID)
        assert prof is not None, f"player_id={_KNOWN_PLAYER_ID} not found in profiles"
        assert prof["player_id"] == _KNOWN_PLAYER_ID

    def test_as_of_date_recomputes_age(self):
        from src.data.player_profile_loader import get_player_profile
        prof = get_player_profile(_KNOWN_PLAYER_ID, as_of_date=_DATE)
        assert prof is not None
        age_days = prof.get("age_precise_days_as_of")
        assert age_days is not None and age_days > 0, f"age_precise_days_as_of={age_days} should be positive"

    def test_unknown_player_returns_none(self):
        from src.data.player_profile_loader import get_player_profile
        assert get_player_profile(999999999) is None

    def test_module_cache(self):
        from src.data.player_profile_loader import load_player_profiles
        df1 = load_player_profiles()
        df2 = load_player_profiles()
        assert df1 is df2, "Expected module-level cache to return the same DataFrame object"


class TestProfileAssemblerWire:
    def test_prof_keys_present(self):
        from src.pipeline.feature_assembler import assemble_features
        feats = assemble_features(
            game_id=_KNOWN_GAME_ID,
            player_id=_KNOWN_PLAYER_ID,
            date=_DATE,
            season="2024-25",
        )
        for key in PROF_KEYS:
            assert key in feats, f"Expected key '{key}' in assemble_features output"

    def test_prof_age_days_positive(self):
        from src.pipeline.feature_assembler import assemble_features
        feats = assemble_features(
            game_id=_KNOWN_GAME_ID,
            player_id=_KNOWN_PLAYER_ID,
            date=_DATE,
            season="2024-25",
        )
        age = feats.get("prof_age_days")
        assert age is not None and not math.isnan(float(age)) and float(age) > 0, (
            f"prof_age_days={age} should be a positive number"
        )

    def test_prof_player_not_in_parquet_no_crash(self):
        """Assembler must not raise for a player absent from the profile parquet."""
        from src.pipeline.feature_assembler import assemble_features
        feats = assemble_features(
            game_id=_KNOWN_GAME_ID,
            player_id=999999999,
            date=_DATE,
            season="2024-25",
        )
        # prof_* keys absent is acceptable; key presence is not required for unknown player
        # but the call must not raise
        assert isinstance(feats, dict)
