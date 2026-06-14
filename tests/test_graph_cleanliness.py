"""tests/test_graph_cleanliness.py — Per-file unit tests for graph_cleanliness.py.

Tests the detector logic for specific-player nodes, specific-match nodes,
wikilink violations, and hub-link coverage.  Uses only tmp_path (no network,
no vault/ reads).  Run: pytest tests/test_graph_cleanliness.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.graph_cleanliness import (  # noqa: E402
    _is_player_filename,
    _is_match_filename,
    _wikilink_is_player,
    _wikilink_is_match,
    scan_file,
    scan_vault,
)


# ── _is_player_filename ───────────────────────────────────────────────────────

class TestIsPlayerFilename:
    def test_player_id_prefix(self):
        assert _is_player_filename("2544_lebron_james") is True

    def test_short_id_prefix(self):
        assert _is_player_filename("123_john_doe") is True

    def test_first_last_lowercase(self):
        assert _is_player_filename("aaron_holiday") is True

    def test_concept_combo_not_player(self):
        # "high_usage" — both tokens are concept words
        assert _is_player_filename("high_usage_creator") is False

    def test_drop_coverage_not_player(self):
        assert _is_player_filename("drop_coverage") is False

    def test_archetype_index_not_player(self):
        assert _is_player_filename("_Archetypes_Index") is False

    def test_team_identity_not_player(self):
        assert _is_player_filename("NYK_Identity") is False

    def test_season_trend_not_player(self):
        assert _is_player_filename("style_trends_2010") is False

    def test_hyphenated_player_name(self):
        # shai_gilgeous-alexander — contains a proper name
        assert _is_player_filename("shai_gilgeous-alexander") is True

    def test_balanced_contender_not_player(self):
        # Both words are concept-ish
        assert _is_player_filename("balanced_contender") is False


# ── _is_match_filename ────────────────────────────────────────────────────────

class TestIsMatchFilename:
    def test_iso_date_hyphen(self):
        assert _is_match_filename("2025-06-14") is True

    def test_iso_date_underscore(self):
        assert _is_match_filename("game_2025_06_14") is True

    def test_game_id_pattern(self):
        assert _is_match_filename("20251014LAL") is True

    def test_normal_archetype_not_match(self):
        assert _is_match_filename("High_Usage_Creator") is False

    def test_trends_overview_not_match(self):
        assert _is_match_filename("_Trends_Overview") is False

    def test_season_trend_not_match(self):
        # style_trends_2010 has a 4-digit year but not YYYY-MM-DD
        assert _is_match_filename("style_trends_2010") is False

    def test_two_digit_year_not_match(self):
        assert _is_match_filename("2024-25_Archetypes") is False


# ── _wikilink_is_player ───────────────────────────────────────────────────────

class TestWikilinkIsPlayer:
    def test_title_case_name(self):
        assert _wikilink_is_player("LeBron James") is True

    def test_title_case_with_path(self):
        assert _wikilink_is_player("Players/LeBron James") is True

    def test_concept_title_not_player(self):
        assert _wikilink_is_player("Drop Coverage") is False

    def test_high_usage_creator_not_player(self):
        assert _wikilink_is_player("High Usage") is False

    def test_player_id_prefix_link(self):
        assert _wikilink_is_player("2544_lebron") is True

    def test_brain_moc_not_player(self):
        assert _wikilink_is_player("_Brain_MOC") is False

    def test_what_wins_not_player(self):
        assert _wikilink_is_player("_WhatWins") is False

    def test_identity_hub_not_player(self):
        assert _wikilink_is_player("NYK/_Identity") is False


# ── _wikilink_is_match ────────────────────────────────────────────────────────

class TestWikilinkIsMatch:
    def test_date_link(self):
        assert _wikilink_is_match("game-2025-06-14") is True

    def test_game_id_link(self):
        assert _wikilink_is_match("20251014LAL") is True

    def test_archetype_link_not_match(self):
        assert _wikilink_is_match("High_Usage_Creator") is False

    def test_brain_link_not_match(self):
        assert _wikilink_is_match("_Brain") is False


# ── scan_file ─────────────────────────────────────────────────────────────────

class TestScanFile:
    def test_clean_archetype_file(self, tmp_path):
        f = tmp_path / "High_Usage_Creator.md"
        f.write_text("# High-Usage Creator\n\n[[_Index]] [[_Brain]]\n", encoding="utf-8")
        violations = scan_file(f, tmp_path)
        assert violations == []

    def test_player_filename_flagged(self, tmp_path):
        f = tmp_path / "aaron_holiday.md"
        f.write_text("# Aaron Holiday\n", encoding="utf-8")
        violations = scan_file(f, tmp_path)
        kinds = {v.kind for v in violations}
        assert "player_node" in kinds

    def test_date_filename_flagged(self, tmp_path):
        f = tmp_path / "2025-06-14_game.md"
        f.write_text("# Game recap\n", encoding="utf-8")
        violations = scan_file(f, tmp_path)
        kinds = {v.kind for v in violations}
        assert "match_node" in kinds

    def test_player_wikilink_in_content(self, tmp_path):
        f = tmp_path / "some_scheme.md"
        f.write_text(
            "# Scheme\n\nSee [[LeBron James]] for usage data.\n",
            encoding="utf-8",
        )
        violations = scan_file(f, tmp_path)
        kinds = {v.kind for v in violations}
        assert "player_link" in kinds

    def test_match_wikilink_in_content(self, tmp_path):
        f = tmp_path / "some_scheme.md"
        f.write_text(
            "# Scheme\n\nSee [[game-2025-06-14]] for data.\n",
            encoding="utf-8",
        )
        violations = scan_file(f, tmp_path)
        kinds = {v.kind for v in violations}
        assert "match_link" in kinds

    def test_tactical_vs_link_allowed(self, tmp_path):
        f = tmp_path / "scheme.md"
        f.write_text("Compare [[Drop vs Switch]] patterns.\n", encoding="utf-8")
        violations = scan_file(f, tmp_path)
        # Drop and Switch are concept tokens; should NOT flag player_link
        player_links = [v for v in violations if v.kind == "player_link"]
        assert player_links == []


# ── scan_vault ────────────────────────────────────────────────────────────────

class TestScanVault:
    def test_empty_dir_clean(self, tmp_path):
        rep = scan_vault(tmp_path)
        assert rep["clean"] is True
        assert rep["n_files"] == 0

    def test_nonexistent_dir_error(self, tmp_path):
        rep = scan_vault(tmp_path / "nonexistent")
        assert rep["clean"] is False
        assert "error" in rep

    def test_clean_vault(self, tmp_path):
        (tmp_path / "Archetype.md").write_text(
            "# High-Usage Creator\n\n[[_Brain]] [[_Index]]\n", encoding="utf-8"
        )
        rep = scan_vault(tmp_path)
        assert rep["clean"] is True
        assert rep["player_nodes"] == 0
        assert rep["match_nodes"] == 0

    def test_player_node_fails(self, tmp_path):
        (tmp_path / "aaron_holiday.md").write_text("# Aaron Holiday\n", encoding="utf-8")
        rep = scan_vault(tmp_path)
        assert rep["clean"] is False
        assert rep["player_nodes"] >= 1

    def test_match_node_fails(self, tmp_path):
        (tmp_path / "2025-06-14.md").write_text("# Game\n", encoding="utf-8")
        rep = scan_vault(tmp_path)
        assert rep["clean"] is False
        assert rep["match_nodes"] >= 1

    def test_hub_link_counted(self, tmp_path):
        (tmp_path / "a.md").write_text("[[_Brain]]\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("no links here\n", encoding="utf-8")
        rep = scan_vault(tmp_path)
        assert rep["n_hub_linked"] == 1
        assert rep["n_files"] == 2
        assert rep["pct_hub_linked"] == 50.0

    def test_season_trend_allowed(self, tmp_path):
        (tmp_path / "style_trends_2010.md").write_text(
            "# Style Trends 2010\n\n[[_Index]]\n", encoding="utf-8"
        )
        rep = scan_vault(tmp_path)
        assert rep["player_nodes"] == 0
        assert rep["match_nodes"] == 0

    def test_two_digit_season_allowed(self, tmp_path):
        (tmp_path / "2024-25_Archetypes.md").write_text(
            "# Archetypes 2024-25\n", encoding="utf-8"
        )
        rep = scan_vault(tmp_path)
        assert rep["match_nodes"] == 0
