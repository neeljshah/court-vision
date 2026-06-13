"""tests.platform.test_nba_trends — Unit tests for memory_atlas_trends.

Synthetic multi-season fixtures; no real parquets; no network access.
Covers: file creation, note content, no-names invariant, edge cases.
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from domains.basketball_nba.memory_atlas_trends import build_trends, _ARCHETYPE_LABELS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PLAYER_NAMES = ["jokic", "embiid", "doncic", "giannis", "tatum", "luka", "james"]


@pytest.fixture()
def synthetic_team_df() -> pd.DataFrame:
    """3 seasons x 3 teams."""
    rows = []
    for i, season in enumerate(["2022-23", "2023-24", "2024-25"]):
        for tricode, off, defr, pace, efg in [
            ("NYK", 115.0, 110.0, 97.5, 0.545),
            ("BOS", 119.0, 108.0, 96.0, 0.560),
            ("LAL", 112.0, 112.0, 99.0, 0.525),
        ]:
            rows.append({
                "team_tricode": tricode,
                "season_label": season,
                "off_rtg": off + i * 0.5,
                "def_rtg": defr - i * 0.3,
                "pace": pace + i * 0.2,
                "efg_pct": efg + i * 0.002,
                "ts_pct": efg + 0.03 + i * 0.001,
                "n_games": 82,
            })
    return pd.DataFrame(rows)


@pytest.fixture()
def synthetic_player_df() -> pd.DataFrame:
    """3 seasons x several players — player_id only, no names."""
    rows = []
    # (pid, usage, ts, efg, ast_pct, def_rtg, reb_pct, mins, pos, n_games)
    players_22 = [
        (1, 0.27, 0.59, 0.53, 0.26, 107.0, 0.08, 32.0, "Guard", 65),
        (2, 0.20, 0.63, 0.56, 0.10, 104.0, 0.15, 30.0, "Center", 58),
        (3, 0.10, 0.57, 0.51, 0.07, 115.0, 0.06, 14.0, "Forward", 40),
        (4, 0.16, 0.55, 0.49, 0.09, 113.0, 0.07, 22.0, "Guard", 50),
    ]
    players_23 = [
        (5, 0.25, 0.61, 0.55, 0.22, 108.0, 0.09, 34.0, "Guard", 70),
        (6, 0.14, 0.58, 0.52, 0.08, 112.0, 0.06, 13.0, "Forward-Guard", 55),
        (7, 0.19, 0.64, 0.58, 0.12, 106.0, 0.14, 28.0, "Center", 60),
    ]
    players_24 = [
        (8, 0.24, 0.60, 0.54, 0.21, 109.0, 0.10, 33.0, "Guard", 68),
        (9, 0.12, 0.56, 0.50, 0.07, 116.0, 0.05, 12.0, "Forward", 45),
        (10, 0.18, 0.62, 0.55, 0.16, 107.0, 0.13, 27.0, "Forward-Center", 60),
        (11, 0.17, 0.58, 0.52, 0.10, 111.0, 0.09, 20.0, "Forward", 50),
    ]

    for season, players in [("2022-23", players_22), ("2023-24", players_23), ("2024-25", players_24)]:
        for pid, usg, ts, efg, ast_pct, def_rtg, reb_pct, mins, pos, n_games in players:
            rows.append({
                "player_id": pid + (int(season[:4]) - 2022) * 100,
                "season_label": season,
                "game_id": n_games,
                "usage": usg, "ts": ts, "efg": efg, "ast_pct": ast_pct,
                "def_rtg": def_rtg, "reb_pct": reb_pct, "minutes_avg": mins,
                "position": pos,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests — file creation
# ---------------------------------------------------------------------------

class TestBuildTrendsFileCreation:
    def test_returns_list_of_paths(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        written = build_trends(
            tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df,
        )
        assert isinstance(written, list)
        assert len(written) >= 1
        for p in written:
            assert isinstance(p, pathlib.Path), f"Expected Path, got {type(p)}"
            assert p.exists(), f"File not written: {p}"

    def test_overview_note_created(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        overview = tmp_path / "Trends" / "_Trends_Overview.md"
        assert overview.exists(), "_Trends_Overview.md was not created"
        assert len(overview.read_text(encoding="utf-8")) > 50

    def test_per_season_notes_created(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        seasons_dir = tmp_path / "Trends" / "Seasons"
        assert seasons_dir.is_dir(), "Trends/Seasons/ subdirectory was not created"
        notes = list(seasons_dir.glob("*_Archetypes.md"))
        assert len(notes) == 3, f"Expected 3 per-season notes, got {len(notes)}"

    def test_idempotent(self, tmp_path, synthetic_team_df, synthetic_player_df) -> None:
        w1 = build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        w2 = build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        assert len(w1) == len(w2)


# ---------------------------------------------------------------------------
# Tests — note content
# ---------------------------------------------------------------------------

class TestTrendsNoteContent:
    def test_overview_has_frontmatter(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        text = (tmp_path / "Trends" / "_Trends_Overview.md").read_text(encoding="utf-8")
        assert text.startswith("---"), "Overview must begin with YAML frontmatter"
        assert "tags:" in text

    def test_overview_has_archetypes_link(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        text = (tmp_path / "Trends" / "_Trends_Overview.md").read_text(encoding="utf-8")
        assert "[[Archetypes/" in text, "Overview must link to [[Archetypes/...]]"

    def test_overview_has_efficiency_table(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        text = (tmp_path / "Trends" / "_Trends_Overview.md").read_text(encoding="utf-8")
        assert "League Efficiency" in text
        assert "Off Rtg" in text

    def test_overview_has_archetype_share_table(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        text = (tmp_path / "Trends" / "_Trends_Overview.md").read_text(encoding="utf-8")
        assert "Archetype Share" in text
        assert "%" in text

    def test_overview_has_sport_tag(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        text = (tmp_path / "Trends" / "_Trends_Overview.md").read_text(encoding="utf-8")
        assert "sport/nba" in text

    def test_season_note_has_frontmatter(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        note = tmp_path / "Trends" / "Seasons" / "2022-23_Archetypes.md"
        assert note.exists()
        text = note.read_text(encoding="utf-8")
        assert text.startswith("---"), "Season note must begin with YAML frontmatter"
        assert "tags:" in text

    def test_season_note_has_archetype_counts(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        note = tmp_path / "Trends" / "Seasons" / "2023-24_Archetypes.md"
        text = note.read_text(encoding="utf-8")
        assert "Archetype Counts" in text
        # At least one archetype label present
        found = any(label in text for label in _ARCHETYPE_LABELS)
        assert found, "No archetype label found in season note"

    def test_season_note_total_count_positive(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        for season in ["2022-23", "2023-24", "2024-25"]:
            note = tmp_path / "Trends" / "Seasons" / f"{season}_Archetypes.md"
            text = note.read_text(encoding="utf-8")
            m = re.search(r"Total player-seasons classified.*?:\s*(\d+)", text)
            assert m is not None, f"Missing total count in {season} note"
            assert int(m.group(1)) > 0, f"Zero players classified in {season}"

    def test_delta_column_present_from_second_season(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        """Second and third season notes must show Δ vs prev season column."""
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        for season in ["2023-24", "2024-25"]:
            note = tmp_path / "Trends" / "Seasons" / f"{season}_Archetypes.md"
            text = note.read_text(encoding="utf-8")
            assert "Δ vs prev" in text or "pp" in text, (
                f"{season} note missing delta column (pp)"
            )


# ---------------------------------------------------------------------------
# Tests — no player names
# ---------------------------------------------------------------------------

class TestNoPlayerNames:
    def test_no_known_player_names_in_output(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        """Known player surnames must NOT appear in any output file."""
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=synthetic_player_df)
        trends_dir = tmp_path / "Trends"
        all_md = list(trends_dir.rglob("*.md"))
        assert len(all_md) >= 1
        for md in all_md:
            content = md.read_text(encoding="utf-8").lower()
            for name in _PLAYER_NAMES:
                assert name not in content, (
                    f"Player name '{name}' found in {md.name} — must not appear"
                )

    def test_no_player_name_in_fixture_player_df_output(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
    ) -> None:
        """Even if a player_df had a player_name column, it must not surface in output."""
        # Build a player_df that has a player_name column (simulates accidental inclusion)
        rows = [
            {"player_id": 99, "player_name": "Jokic", "season_label": "2022-23",
             "game_id": 70, "usage": 0.25, "ts": 0.63, "efg": 0.56, "ast_pct": 0.22,
             "def_rtg": 108.0, "reb_pct": 0.15, "minutes_avg": 34.0, "position": "Center"},
        ]
        player_df = pd.DataFrame(rows)
        build_trends(tmp_path, _team_df=synthetic_team_df, _player_df=player_df)
        trends_dir = tmp_path / "Trends"
        for md in trends_dir.rglob("*.md"):
            content = md.read_text(encoding="utf-8").lower()
            assert "jokic" not in content, f"'jokic' leaked into {md.name}"


# ---------------------------------------------------------------------------
# Tests — edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_player_df_no_exception(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
    ) -> None:
        """Empty player DataFrame must not raise; overview still written."""
        written = build_trends(
            tmp_path, _team_df=synthetic_team_df, _player_df=pd.DataFrame(),
        )
        assert len(written) >= 1

    def test_empty_team_df_no_exception(self, tmp_path: pathlib.Path) -> None:
        """Empty team DataFrame must not raise; fallback file written."""
        written = build_trends(
            tmp_path, _team_df=pd.DataFrame(), _player_df=pd.DataFrame(),
        )
        assert len(written) >= 1
        overview = tmp_path / "Trends" / "_Trends_Overview.md"
        assert overview.exists()

    def test_single_season_no_delta(
        self, tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame, synthetic_player_df: pd.DataFrame,
    ) -> None:
        """With one season, the first season note must show '—' for delta."""
        # Restrict to one season
        one_team = synthetic_team_df[synthetic_team_df["season_label"] == "2022-23"].copy()
        one_player = synthetic_player_df[synthetic_player_df["season_label"] == "2022-23"].copy()
        build_trends(tmp_path, _team_df=one_team, _player_df=one_player)
        note = tmp_path / "Trends" / "Seasons" / "2022-23_Archetypes.md"
        assert note.exists()
        text = note.read_text(encoding="utf-8")
        assert "—" in text  # delta column shows "—" for the first season
