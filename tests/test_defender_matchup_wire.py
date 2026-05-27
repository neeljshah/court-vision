"""Tests for defender matchup feature wiring into assemble_features."""

from __future__ import annotations

import math
import pytest

from src.pipeline.feature_assembler import assemble_features
from src.data.defender_matchup_loader import (
    load_defender_matchup_features,
    get_defender_matchup_row,
)

# Known fixture from the parquet (game 0022300076, LeBron James = 2544).
_GAME_ID = "0022300076"
_PLAYER_ID = 2544

DMATCH_KEYS = [
    "dmatch_fg_pct_l10",
    "dmatch_partial_poss_share",
    "dmatch_switches_per_poss",
    "dmatch_primary_def_height_in",
    "dmatch_height_advantage_in",
    "dmatch_help_blocks_per_game",
    "dmatch_3p_pct_l10",
]


class TestLoaderDirectly:
    def test_load_returns_dataframe(self):
        df = load_defender_matchup_features()
        assert df is not None
        assert len(df) > 0

    def test_known_row_exists(self):
        row = get_defender_matchup_row(_GAME_ID, _PLAYER_ID)
        assert row is not None
        assert "matchup_fg_pct_l10" in row

    def test_missing_row_returns_none(self):
        row = get_defender_matchup_row("0000000000", 999999999)
        assert row is None

    def test_primary_def_def_rating_not_in_row(self):
        row = get_defender_matchup_row(_GAME_ID, _PLAYER_ID)
        assert row is not None
        assert "primary_def_def_rating" not in row


class TestAssembleFeaturesWiring:
    def test_dmatch_keys_present(self):
        feats = assemble_features(_GAME_ID, _PLAYER_ID)
        for key in DMATCH_KEYS:
            assert key in feats, f"Missing key: {key}"

    def test_at_least_one_non_nan(self):
        feats = assemble_features(_GAME_ID, _PLAYER_ID)
        non_nan = [k for k in DMATCH_KEYS if not math.isnan(float(feats[k]))]
        assert len(non_nan) >= 1, f"All dmatch_* keys are NaN: {feats}"

    def test_unknown_game_returns_nan_features(self):
        feats = assemble_features("0000000000", 999999, season="2024-25")
        for key in DMATCH_KEYS:
            assert key in feats
            assert math.isnan(float(feats[key])), f"{key} should be NaN for unknown game"

    def test_sample_values_reasonable(self):
        feats = assemble_features(_GAME_ID, _PLAYER_ID)
        fg = feats["dmatch_fg_pct_l10"]
        if not math.isnan(float(fg)):
            assert 0.0 <= float(fg) <= 1.0, f"fg_pct_l10 out of range: {fg}"
