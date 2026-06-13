"""tests.platform.test_nba_seasons — Unit tests for memory_atlas_seasons (part 1 of 2).

Uses tiny synthetic DataFrames; does NOT read real parquet data.
All tests are idempotent and run without network access.

No individual player names are expected in any output — the suite verifies that
team-level data is present and that player names are absent.

See also: test_nba_seasons_part2.py for additional coverage.
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from domains.basketball_nba.memory_atlas_seasons import build_seasons


# ---------------------------------------------------------------------------
# Fixtures — minimal synthetic DataFrames that mirror real parquet schemas
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_team_df() -> pd.DataFrame:
    """Two seasons × three teams of aggregated team stats."""
    rows = []
    for season in ["2022-23", "2023-24"]:
        for tricode, off, defr, pace, efg, ts, tov in [
            ("NYK", 115.0, 110.0, 97.5, 0.545, 0.575, 13.2),
            ("BOS", 119.0, 108.0, 96.0, 0.560, 0.590, 12.8),
            ("LAL", 112.0, 112.0, 99.0, 0.525, 0.555, 14.5),
        ]:
            rows.append(
                {
                    "team_tricode": tricode,
                    "season_label": season,
                    "off_rtg": off + (1.0 if season == "2023-24" else 0.0),
                    "def_rtg": defr - (0.5 if season == "2023-24" else 0.0),
                    "pace": pace,
                    "efg_pct": efg,
                    "ts_pct": ts,
                    "tov_ratio": tov,
                    "n_games": 82,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture()
def synthetic_player_arch_df() -> pd.DataFrame:
    """Two seasons × a handful of players for archetype classification (no names needed)."""
    # Uses player_id only — no player_name column
    rows = []
    # season 2022-23: 3 players at various archetypes
    for pid, usg, ts, efg, ast_pct, def_rtg, reb_pct, mins, pos, n_games in [
        (1, 0.25, 0.59, 0.53, 0.25, 108.0, 0.08, 32.0, "Guard", 60),
        (2, 0.20, 0.62, 0.55, 0.10, 105.0, 0.14, 30.0, "Center", 55),
        (3, 0.10, 0.57, 0.50, 0.08, 114.0, 0.07, 14.0, "Guard", 40),
    ]:
        rows.append({
            "player_id": pid,
            "season_label": "2022-23",
            "game_id": n_games,
            "usage": usg, "ts": ts, "efg": efg, "ast_pct": ast_pct,
            "def_rtg": def_rtg, "reb_pct": reb_pct, "minutes_avg": mins,
            "position": pos,
        })
    # season 2023-24: 2 players
    for pid, usg, ts, efg, ast_pct, def_rtg, reb_pct, mins, pos, n_games in [
        (4, 0.26, 0.64, 0.57, 0.22, 107.0, 0.09, 34.0, "Guard", 70),
        (5, 0.12, 0.58, 0.52, 0.09, 113.0, 0.06, 12.0, "Forward", 50),
    ]:
        rows.append({
            "player_id": pid,
            "season_label": "2023-24",
            "game_id": n_games,
            "usage": usg, "ts": ts, "efg": efg, "ast_pct": ast_pct,
            "def_rtg": def_rtg, "reb_pct": reb_pct, "minutes_avg": mins,
            "position": pos,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildSeasons:
    def test_returns_list_of_paths(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        written = build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        assert isinstance(written, list)
        assert len(written) >= 1

    def test_index_file_exists(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        index = tmp_path / "_Seasons_Index.md"
        assert index.exists(), "_Seasons_Index.md was not created"
        content = index.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_season_notes_created(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        seasons_dir = tmp_path / "Seasons"
        assert seasons_dir.is_dir(), "Seasons/ subdirectory was not created"
        notes = list(seasons_dir.glob("*.md"))
        assert len(notes) == 2, f"Expected 2 season notes, got {len(notes)}"

    def test_frontmatter_present(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        note = tmp_path / "Seasons" / "2022-23.md"
        assert note.exists()
        content = note.read_text(encoding="utf-8")
        assert content.startswith("---"), "Note must begin with YAML frontmatter (---)"
        assert "tags:" in content

    def test_wikilinks_to_teams(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        note = tmp_path / "Seasons" / "2022-23.md"
        content = note.read_text(encoding="utf-8")
        # Should contain wikilinks to at least one team
        assert "[[Teams/" in content, "Season note must contain [[Teams/<TRICODE>]] wikilinks"

    def test_no_player_wikilinks(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        """Season notes must NOT contain [[Players/...]] wikilinks (no named players)."""
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        for note_path in (tmp_path / "Seasons").glob("*.md"):
            content = note_path.read_text(encoding="utf-8")
            assert "[[Players/" not in content, (
                f"Season note {note_path.name} must NOT contain [[Players/...]] wikilinks"
            )

    def test_no_player_names_in_notes(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        """Known player names must not appear anywhere in the season notes."""
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        forbidden_names = [
            "jokic", "giannis", "antetokounmpo", "gilgeous", "alexander",
            "doncic", "luka", "tatum", "embiid",
        ]
        for note_path in (tmp_path / "Seasons").glob("*.md"):
            content = note_path.read_text(encoding="utf-8").lower()
            for name in forbidden_names:
                assert name not in content, (
                    f"Player name '{name}' found in {note_path.name} — names must not appear"
                )

    def test_archetype_mix_section_present(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        """Season notes should contain the Archetype Mix section when player data is provided."""
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        note = tmp_path / "Seasons" / "2022-23.md"
        content = note.read_text(encoding="utf-8")
        assert "Archetype Mix" in content, "Season note must contain Archetype Mix section"

    def test_stat_distributions_section_present(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        """Season notes should contain league stat distributions."""
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        note = tmp_path / "Seasons" / "2022-23.md"
        content = note.read_text(encoding="utf-8")
        assert "League Stat Distributions" in content

    def test_index_links_to_seasons(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        index = tmp_path / "_Seasons_Index.md"
        content = index.read_text(encoding="utf-8")
        assert "[[Seasons/2022-23" in content
        assert "[[Seasons/2023-24" in content
