"""
Tests for src/data/pbp_features.py — PBP feature extraction.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data.pbp_features import (
    _season_from_game_id,
    _desc_contains,
    _parse_margin,
    build,
)


# ── _season_from_game_id ────────────────────────────────────────────────────

class TestSeasonFromGameId:
    def test_regular_2022_23(self):
        assert _season_from_game_id("0022200001") == "2022-23"

    def test_regular_2023_24(self):
        assert _season_from_game_id("0022300001") == "2023-24"

    def test_regular_2024_25(self):
        assert _season_from_game_id("0022400001") == "2024-25"

    def test_playoffs_2022_23(self):
        assert _season_from_game_id("0042200001") == "2022-23"

    def test_playoffs_2023_24(self):
        assert _season_from_game_id("0042300001") == "2023-24"

    def test_playoffs_2024_25(self):
        assert _season_from_game_id("0042400001") == "2024-25"

    def test_unknown_prefix_returns_none(self):
        assert _season_from_game_id("0012200001") is None

    def test_empty_string_returns_none(self):
        assert _season_from_game_id("") is None


# ── _desc_contains ──────────────────────────────────────────────────────────

class TestDescContains:
    def test_home_desc_match(self):
        event = {"HOMEDESCRIPTION": "3PT JUMP SHOT by Curry", "VISITORDESCRIPTION": None}
        assert _desc_contains(event, "3PT") is True

    def test_visitor_desc_match(self):
        event = {"HOMEDESCRIPTION": None, "VISITORDESCRIPTION": "MISS 3PT"}
        assert _desc_contains(event, "miss") is True

    def test_case_insensitive(self):
        event = {"HOMEDESCRIPTION": "3pt jump shot", "VISITORDESCRIPTION": None}
        assert _desc_contains(event, "3PT") is True

    def test_no_match(self):
        event = {"HOMEDESCRIPTION": "DUNK by LeBron", "VISITORDESCRIPTION": "REBOUND"}
        assert _desc_contains(event, "3PT") is False

    def test_empty_event(self):
        assert _desc_contains({}, "3PT") is False


# ── _parse_margin ───────────────────────────────────────────────────────────

class TestParseMargin:
    def test_positive_int(self):
        assert _parse_margin("5") == 5

    def test_negative_int(self):
        assert _parse_margin("-10") == -10

    def test_zero(self):
        assert _parse_margin("0") == 0

    def test_tie_returns_none(self):
        assert _parse_margin("TIE") is None

    def test_none_input_returns_none(self):
        assert _parse_margin(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_margin("") is None

    def test_int_input(self):
        assert _parse_margin(7) == 7


# ── build() integration ─────────────────────────────────────────────────────

class TestBuildOutput:
    """Integration test against the real pbp_features_2024-25.json if present."""

    def test_cache_file_exists_with_expected_keys(self):
        cache = os.path.join(PROJECT_DIR, "data", "nba", "pbp_features_2024-25.json")
        if not os.path.exists(cache):
            pytest.skip("pbp_features_2024-25.json not built yet")
        d = json.load(open(cache))
        assert len(d) > 100, "Expected > 100 players in 2024-25"
        # Check a random player has the expected feature keys
        pid = list(d.keys())[0]
        feats = d[pid]
        expected_keys = {
            "q4_shot_rate", "q4_pts_share", "fta_rate_pbp",
            "foul_drawn_rate_pbp", "comeback_pts_pg", "games_seen",
        }
        assert expected_keys.issubset(set(feats.keys()))

    def test_feature_values_in_valid_range(self):
        cache = os.path.join(PROJECT_DIR, "data", "nba", "pbp_features_2024-25.json")
        if not os.path.exists(cache):
            pytest.skip("pbp_features_2024-25.json not built yet")
        d = json.load(open(cache))
        for pid, feats in list(d.items())[:20]:
            assert 0.0 <= feats["q4_shot_rate"] <= 1.0, f"q4_shot_rate OOB for {pid}"
            assert 0.0 <= feats["q4_pts_share"] <= 1.0, f"q4_pts_share OOB for {pid}"
            assert feats["fta_rate_pbp"] >= 0.0, f"fta_rate_pbp negative for {pid}"
            assert feats["games_seen"] >= 1, f"games_seen < 1 for {pid}"
