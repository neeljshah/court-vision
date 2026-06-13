"""tests.platform.test_nba_seasons_part2 — Additional tests for memory_atlas_seasons.

Continuation of test_nba_seasons.py; split to keep each file ≤ 300 LOC.
Uses the same synthetic fixtures (duplicated here so each file runs standalone).
All tests are idempotent and run without network access.
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from domains.basketball_nba.memory_atlas_seasons import build_seasons


# ---------------------------------------------------------------------------
# Fixtures — minimal synthetic DataFrames that mirror real parquet schemas
# (duplicated from test_nba_seasons.py so this file runs standalone)
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
    rows = []
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
# Tests (continued from test_nba_seasons.py)
# ---------------------------------------------------------------------------

class TestBuildSeasonsExtra:
    def test_idempotent(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        """Running twice must produce the same files without exceptions."""
        kwargs = dict(
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        written_first = build_seasons(tmp_path, **kwargs)
        written_second = build_seasons(tmp_path, **kwargs)
        assert [p.name for p in written_first] == [p.name for p in written_second]

    def test_no_betting_language(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
        synthetic_player_arch_df: pd.DataFrame,
    ) -> None:
        """Notes must not contain edge / betting language."""
        build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=synthetic_player_arch_df,
        )
        # "EV" and "ROI" checked as whole-word tokens to avoid substring hits
        # (e.g. "level" contains "ev", "roi" is not a substring concern)
        forbidden_substrings = ("edge", "bet ", "kelly", "closing line", "CLV")
        forbidden_words = ("ROI", "EV")
        for note_path in (tmp_path / "Seasons").glob("*.md"):
            content = note_path.read_text(encoding="utf-8")
            content_lower = content.lower()
            for word in forbidden_substrings:
                assert word.lower() not in content_lower, (
                    f"Forbidden term '{word}' found in {note_path.name}"
                )
            for word in forbidden_words:
                assert not re.search(rf"\b{re.escape(word.lower())}\b", content_lower), (
                    f"Forbidden term '{word}' found as a whole word in {note_path.name}"
                )

    def test_empty_data_returns_index_only(self, tmp_path: pathlib.Path) -> None:
        """When team_df is empty, only the index note is written (no crash)."""
        empty_team = pd.DataFrame(columns=["team_tricode", "season_label"])
        written = build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=empty_team,
            _player_df=pd.DataFrame(),
        )
        assert len(written) == 1
        assert written[0].name == "_Seasons_Index.md"

    def test_no_player_df_still_works(
        self,
        tmp_path: pathlib.Path,
        synthetic_team_df: pd.DataFrame,
    ) -> None:
        """build_seasons with _player_df=empty DataFrame must not crash."""
        written = build_seasons(
            tmp_path,
            data_dir=tmp_path / "does_not_exist",
            _team_df=synthetic_team_df,
            _player_df=pd.DataFrame(),
        )
        assert len(written) >= 3  # 2 season notes + index
