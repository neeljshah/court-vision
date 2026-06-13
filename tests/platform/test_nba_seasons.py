"""tests.platform.test_nba_seasons — Unit tests for memory_atlas_seasons.

Uses tiny synthetic DataFrames; does NOT read real parquet data.
All tests are idempotent and run without network access.
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
def synthetic_player_df() -> pd.DataFrame:
    """Two seasons × four players of BPM / VORP data."""
    rows = [
        # 2022-23
        {"player_name": "Nikola Jokic", "team": "DEN", "season": "2022-23",
         "bpm": 13.0, "vorp": 9.5, "per": 31.5, "ts_pct": 0.660, "usg_pct": 27.0, "ws": 15.0,
         "obpm": 10.0, "dbpm": 3.0, "ws_per_48": 0.280},
        {"player_name": "Giannis Antetokounmpo", "team": "MIL", "season": "2022-23",
         "bpm": 9.2, "vorp": 6.8, "per": 29.8, "ts_pct": 0.620, "usg_pct": 33.0, "ws": 13.0,
         "obpm": 6.5, "dbpm": 2.7, "ws_per_48": 0.235},
        {"player_name": "Small Sample Player", "team": "HOU", "season": "2022-23",
         "bpm": 25.0, "vorp": 0.1, "per": 45.0, "ts_pct": 1.00, "usg_pct": 5.0, "ws": 0.1,
         "obpm": 22.0, "dbpm": 3.0, "ws_per_48": 0.500},
        # 2023-24
        {"player_name": "Nikola Jokic", "team": "DEN", "season": "2023-24",
         "bpm": 14.0, "vorp": 10.1, "per": 32.0, "ts_pct": 0.665, "usg_pct": 29.0, "ws": 17.0,
         "obpm": 11.0, "dbpm": 3.0, "ws_per_48": 0.285},
        {"player_name": "Shai Gilgeous-Alexander", "team": "OKC", "season": "2023-24",
         "bpm": 10.5, "vorp": 7.2, "per": 30.5, "ts_pct": 0.640, "usg_pct": 32.5, "ws": 14.0,
         "obpm": 9.0, "dbpm": 1.5, "ws_per_48": 0.252},
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildSeasons:
    def test_returns_list_of_paths(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_df: pd.DataFrame,
    ) -> None:
        written = build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_df,
        )
        assert isinstance(written, list)
        assert len(written) >= 1

    def test_index_file_exists(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_df,
        )
        index = tmp_path / "_Seasons_Index.md"
        assert index.exists(), "_Seasons_Index.md was not created"
        content = index.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_season_notes_created(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_df,
        )
        seasons_dir = tmp_path / "Seasons"
        assert seasons_dir.is_dir(), "Seasons/ subdirectory was not created"
        notes = list(seasons_dir.glob("*.md"))
        assert len(notes) == 2, f"Expected 2 season notes, got {len(notes)}"

    def test_frontmatter_present(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_df,
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
        synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_df,
        )
        note = tmp_path / "Seasons" / "2022-23.md"
        content = note.read_text(encoding="utf-8")
        # Should contain wikilinks to at least one team
        assert "[[Teams/" in content, "Season note must contain [[Teams/<TRICODE>]] wikilinks"

    def test_wikilinks_to_players(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_df,
        )
        note = tmp_path / "Seasons" / "2022-23.md"
        content = note.read_text(encoding="utf-8")
        # Should link to Jokic and Giannis (VORP >= 1.0); Small Sample Player filtered out
        assert "[[Players/" in content, "Season note must contain [[Players/<slug>]] wikilinks"
        assert "Nikola_Jokic" in content
        # Small-sample outlier (VORP=0.1) must NOT appear in player leaders
        assert "Small_Sample_Player" not in content

    def test_index_links_to_seasons(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_df,
        )
        index = tmp_path / "_Seasons_Index.md"
        content = index.read_text(encoding="utf-8")
        assert "[[Seasons/2022-23" in content
        assert "[[Seasons/2023-24" in content

    def test_idempotent(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_df: pd.DataFrame,
    ) -> None:
        """Running twice must produce the same files without exceptions."""
        kwargs = dict(
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_df,
        )
        written_first = build_seasons(tmp_path, **kwargs)
        written_second = build_seasons(tmp_path, **kwargs)
        assert [p.name for p in written_first] == [p.name for p in written_second]

    def test_no_betting_language(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_df: pd.DataFrame,
    ) -> None:
        """Notes must not contain edge / betting language."""
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_df,
        )
        forbidden = ("edge", "bet ", "kelly", "ROI", "EV", "closing line", "CLV")
        for note_path in (tmp_path / "Seasons").glob("*.md"):
            content = note_path.read_text(encoding="utf-8").lower()
            for word in forbidden:
                assert word.lower() not in content, (
                    f"Forbidden term '{word}' found in {note_path.name}"
                )

    def test_empty_data_returns_index_only(self, tmp_path: pathlib.Path) -> None:
        """When team_df is empty, only the index note is written (no crash)."""
        empty_team = pd.DataFrame(columns=["team_tricode", "season_label"])
        empty_player = pd.DataFrame(columns=["player_name", "team", "season", "bpm", "vorp"])
        written = build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=empty_team,
            _player_df=empty_player,
        )
        assert len(written) == 1
        assert written[0].name == "_Seasons_Index.md"
