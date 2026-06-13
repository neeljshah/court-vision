"""domains.basketball_nba.memory_atlas_seasons — Season-level Obsidian atlas for NBA.

Reads two real parquets:
  data/team_advanced_stats.parquet      — per-game team ratings (off_rtg, def_rtg, pace …)
  data/cache/bbref_advanced_extended.parquet — per-player-season BPM / VORP / PER / TS%

Emits one Markdown note per NBA season found in the data plus an index:

    out_dir/
        _Seasons_Index.md                   hub with wikilinks to each season
        Seasons/2022-23.md                  league-wide team rankings + top players
        Seasons/2023-24.md
        Seasons/2024-25.md
        …

Each note links back to existing Players/<Name>.md and Teams/<TRICODE>.md notes using
the same slug convention as memory_atlas_render._slug().

F5-clean: stdlib + pandas only.  No src.* / kernel.* / edge language.
Idempotent: re-running overwrites notes with the same content.

Public API
----------
build_seasons(out_dir, data_dir) -> list[pathlib.Path]
"""
from __future__ import annotations

import pathlib
from typing import Any, Optional

import pandas as pd

from domains.basketball_nba.memory_atlas_seasons_render import (
    render_index,
    render_season_note,
    write_note,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parents[2]

DEFAULT_DATA_DIR: pathlib.Path = _REPO_ROOT / "data"
DEFAULT_OUT: pathlib.Path = _REPO_ROOT / "vault" / "Sports" / "Basketball_NBA"

# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _derive_season_label(game_date: pd.Series) -> pd.Series:
    """Map game_date -> 'YYYY-YY' NBA season label."""
    def _label(d: Any) -> str:
        if pd.isna(d):
            return "unknown"
        month = d.month
        year = d.year
        if month >= 10:
            return f"{year}-{str(year + 1)[2:]}"
        return f"{year - 1}-{str(year)[2:]}"

    return game_date.apply(_label)


def _load_team_season_agg(data_dir: pathlib.Path) -> pd.DataFrame:
    """Return DataFrame indexed by (team_tricode, season_label) with averaged ratings."""
    path = data_dir / "team_advanced_stats.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["team_tricode", "season_label"])

    df = pd.read_parquet(path)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["season_label"] = _derive_season_label(df["game_date"])

    numeric_cols = [c for c in df.columns if c not in ("game_id", "game_date", "team_tricode", "season_label")]
    agg = (
        df.groupby(["team_tricode", "season_label"])[numeric_cols]
        .mean()
        .round(3)
        .reset_index()
    )
    # Add game count
    game_count = df.groupby(["team_tricode", "season_label"])["game_id"].count().reset_index(name="n_games")
    agg = agg.merge(game_count, on=["team_tricode", "season_label"])
    return agg


def _load_player_season_leaders(data_dir: pathlib.Path) -> pd.DataFrame:
    """Return resolved player-seasons with BPM / VORP / PER / TS% from bbref."""
    path = data_dir / "cache" / "bbref_advanced_extended.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["player_name", "team", "season", "bpm", "vorp", "per", "ts_pct", "usg_pct", "ws"])

    df = pd.read_parquet(path)
    # Keep only rows where the name could be resolved to a known player_id
    if "unresolved_name" in df.columns:
        df = df[df["unresolved_name"] == False].copy()  # noqa: E712

    keep = ["player_name", "team", "season", "bpm", "vorp", "per", "ts_pct", "usg_pct", "ws",
            "obpm", "dbpm", "ws_per_48"]
    present = [c for c in keep if c in df.columns]
    return df[present].copy()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_seasons(
    out_dir: pathlib.Path,
    data_dir: pathlib.Path = DEFAULT_DATA_DIR,
    *,
    _team_df: Optional[pd.DataFrame] = None,
    _player_df: Optional[pd.DataFrame] = None,
) -> list[pathlib.Path]:
    """Generate NBA season atlas notes and return written paths.

    Parameters
    ----------
    out_dir:
        Directory where notes are emitted (created if absent).
    data_dir:
        Root data directory (default: <repo>/data).
    _team_df:
        Optional override for team_advanced_stats DataFrame (used in tests).
    _player_df:
        Optional override for bbref_advanced_extended DataFrame (used in tests).

    Returns
    -------
    list[pathlib.Path]
        All written note files (idempotent — reruns overwrite with same content).
    """
    out_dir = pathlib.Path(out_dir)
    data_dir = pathlib.Path(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Load data ---
    if _team_df is not None:
        team_agg = _team_df.copy()
        # Expect columns: team_tricode, season_label, off_rtg, def_rtg, pace, efg_pct, ts_pct
    else:
        team_agg = _load_team_season_agg(data_dir)

    if _player_df is not None:
        player_leaders = _player_df.copy()
    else:
        player_leaders = _load_player_season_leaders(data_dir)

    if team_agg.empty:
        # No data: write empty index and return
        index_path = out_dir / "_Seasons_Index.md"
        write_note(index_path, render_index([]))
        return [index_path]

    seasons = sorted(team_agg["season_label"].unique())
    written: list[pathlib.Path] = []

    # --- One note per season ---
    for season in seasons:
        season_df = team_agg[team_agg["season_label"] == season].copy()
        note_text = render_season_note(season, season_df, player_leaders)
        note_path = out_dir / "Seasons" / f"{season}.md"
        write_note(note_path, note_text)
        written.append(note_path)

    # --- Index note ---
    index_path = out_dir / "_Seasons_Index.md"
    write_note(index_path, render_index(seasons))
    written.append(index_path)

    return written
