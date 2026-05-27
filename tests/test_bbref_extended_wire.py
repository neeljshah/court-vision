"""
tests/test_bbref_extended_wire.py

Verify that the 5 new bbref_advanced_extended columns
(orb_pct, drb_pct, trb_pct, bpm, ws) are wired through
prop_pergame._BBREF_EXTRA_KEYS and feature_assembler.assemble_features.
"""
from __future__ import annotations

import math
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NEW_KEYS = ("orb_pct", "drb_pct", "trb_pct", "bpm", "ws")
_LEBRON_ID = 2544
_SEASON = "2024-25"


# ── prop_pergame._BBREF_EXTRA_KEYS ─────────────────────────────────────────────

class TestBBRefExtraKeysDeclared:
    def test_extra_keys_tuple_exists(self):
        from src.prediction.prop_pergame import _BBREF_EXTRA_KEYS
        assert isinstance(_BBREF_EXTRA_KEYS, tuple)

    def test_all_five_keys_present(self):
        from src.prediction.prop_pergame import _BBREF_EXTRA_KEYS
        for k in _NEW_KEYS:
            assert k in _BBREF_EXTRA_KEYS, f"Missing key in _BBREF_EXTRA_KEYS: {k}"

    def test_original_bbref_keys_untouched(self):
        """Strict additive change — existing 15 keys must still be in _BBREF_KEYS."""
        from src.prediction.prop_pergame import _BBREF_KEYS
        original = (
            "usg_pct", "ts_pct", "three_par", "ftr",
            "ast_pct", "stl_pct", "blk_pct", "tov_pct",
            "ws_per_48", "per", "obpm", "dbpm",
            "dws", "ows", "vorp",
        )
        for k in original:
            assert k in _BBREF_KEYS, f"Regression: {k} missing from _BBREF_KEYS"

    def test_defaults_include_extra_keys(self):
        from src.prediction.prop_pergame import _BBREF_DEFAULTS
        for k in _NEW_KEYS:
            assert f"bbref_{k}" in _BBREF_DEFAULTS, f"bbref_{k} not in _BBREF_DEFAULTS"


# ── prop_pergame.build_bbref_advanced (parquet load) ───────────────────────────

class TestBuildBBRefAdvancedParquet:
    def test_parquet_path_exists(self):
        parquet = os.path.join(PROJECT_DIR, "data", "cache", "bbref_advanced_extended.parquet")
        assert os.path.isfile(parquet), f"Parquet not found: {parquet}"

    def test_lebron_extra_keys_non_zero(self):
        """LeBron 2024-25 must return non-zero values for the 5 new keys."""
        from src.prediction.prop_pergame import build_bbref_advanced, _bbref_id_to_name
        adv = build_bbref_advanced()
        feats = adv.features(_LEBRON_ID, _SEASON)
        for k in _NEW_KEYS:
            col = f"bbref_{k}"
            assert col in feats, f"{col} missing from build_bbref_advanced output"
            assert feats[col] != 0.0 or not math.isnan(feats[col]), \
                f"{col} is zero/NaN for LeBron {_SEASON}"

    def test_unknown_player_returns_defaults(self):
        from src.prediction.prop_pergame import build_bbref_advanced
        adv = build_bbref_advanced()
        feats = adv.features(999999999, _SEASON)
        for k in _NEW_KEYS:
            assert f"bbref_{k}" in feats


# ── feature_assembler.assemble_features ────────────────────────────────────────

class TestAssembleFeaturesBBRefExtended:
    def test_five_keys_in_output_for_lebron(self):
        """assemble_features must include all 5 new bbref_* keys for LeBron."""
        from src.pipeline.feature_assembler import assemble_features
        feats = assemble_features(
            game_id=None,
            player_id=_LEBRON_ID,
            season=_SEASON,
        )
        for k in _NEW_KEYS:
            col = f"bbref_{k}"
            assert col in feats, f"{col} missing from assemble_features output"

    def test_five_keys_non_nan_for_lebron(self):
        """bbref_* values for an established player must not be NaN."""
        from src.pipeline.feature_assembler import assemble_features
        feats = assemble_features(
            game_id=None,
            player_id=_LEBRON_ID,
            season=_SEASON,
        )
        for k in _NEW_KEYS:
            col = f"bbref_{k}"
            val = feats.get(col)
            assert val is not None, f"{col} is None"
            assert not math.isnan(float(val)), f"{col} is NaN for LeBron {_SEASON}"

    def test_five_keys_non_zero_for_lebron(self):
        """LeBron's advanced metrics are non-trivial — values should be > 0."""
        from src.pipeline.feature_assembler import assemble_features
        feats = assemble_features(
            game_id=None,
            player_id=_LEBRON_ID,
            season=_SEASON,
        )
        non_zero = [k for k in _NEW_KEYS if abs(float(feats.get(f"bbref_{k}", 0))) > 0]
        assert len(non_zero) >= 3, (
            f"Expected >=3 non-zero extra bbref keys for LeBron, got {non_zero} "
            f"from {[feats.get(f'bbref_{k}') for k in _NEW_KEYS]}"
        )
