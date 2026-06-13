"""domains.basketball_nba.memory_atlas_seasons — Season-level Obsidian atlas for NBA.

Reads one real parquet:
  data/team_advanced_stats.parquet  — per-game team ratings (off_rtg, def_rtg, pace …)

Optionally reads player stats for archetype-mix counts (no names emitted):
  data/player_adv_stats.parquet    — per-player-season usage/ts/ast_pct/def_rtg/reb_pct
  data/player_positions.parquet   — player_id → position mapping

Emits one Markdown note per NBA season found in the data plus an index.
NO individual player names appear in any emitted file.

    out_dir/
        _Seasons_Index.md                   hub with wikilinks to each season
        Seasons/2022-23.md                  league-wide team rankings + stat distributions
        Seasons/2023-24.md
        Seasons/2024-25.md
        …

F5-clean: stdlib + pandas only.  No src.* / kernel.* / edge language.
Idempotent: re-running overwrites notes with the same content.

Public API
----------
build_seasons(out_dir, data_dir) -> list[pathlib.Path]
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.basketball_nba.memory_atlas_archetypes import _classify, ARCHETYPES
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

_ARCHETYPE_LABELS: List[str] = [a["label"] for a in ARCHETYPES]

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


def _load_player_archetype_stats(data_dir: pathlib.Path) -> pd.DataFrame:
    """Load player stats needed for archetype classification (no names used).

    Returns a DataFrame with columns: player_id, season_label, usage, ts, efg,
    ast_pct, def_rtg, reb_pct, minutes_avg, position.  Returns empty DataFrame
    if source parquets are absent.
    """
    adv_path = data_dir / "player_adv_stats.parquet"
    pos_path = data_dir / "player_positions.parquet"
    if not adv_path.exists():
        return pd.DataFrame()

    adv = pd.read_parquet(adv_path)

    # Derive season_label from game_date if present
    if "game_date" in adv.columns:
        adv["game_date"] = pd.to_datetime(adv["game_date"])
        adv["season_label"] = _derive_season_label(adv["game_date"])
    elif "season" in adv.columns:
        adv["season_label"] = adv["season"]
    else:
        return pd.DataFrame()

    # Rename stat columns to match _classify expectations
    col_map = {
        "usagepercentage": "usage",
        "trueshootingpercentage": "ts",
        "effectivefieldgoalpercentage": "efg",
        "assistpercentage": "ast_pct",
        "defensiverating": "def_rtg",
        "reboundpercentage": "reb_pct",
        "minutes": "minutes_avg",
    }
    adv = adv.rename(columns={k: v for k, v in col_map.items() if k in adv.columns})

    keep_cols = ["player_id", "season_label", "game_id", "usage", "ts", "efg",
                 "ast_pct", "def_rtg", "reb_pct", "minutes_avg"]
    present = [c for c in keep_cols if c in adv.columns]
    adv = adv[present].copy()

    # Merge positions (no names)
    if pos_path.exists():
        pos = pd.read_parquet(pos_path)[["player_id", "position"]]
        adv = adv.merge(pos, on="player_id", how="left")
        adv["position"] = adv["position"].fillna("Guard")
    else:
        adv["position"] = "Guard"

    return adv


def _compute_archetype_mix(
    player_df: pd.DataFrame,
    season: str,
    min_games: int = 10,
) -> Dict[str, int]:
    """Classify players for *season* and return archetype-label -> count mapping.

    Counts only — no player names stored or returned.

    Parameters
    ----------
    player_df:
        Output of _load_player_archetype_stats (may be empty).
    season:
        Season label to filter on (e.g. '2023-24').
    min_games:
        Minimum games played to include a player in the archetype count.

    Returns
    -------
    Dict[str, int]
        Mapping from archetype label to player count (zero if no data).
    """
    base: Dict[str, int] = {label: 0 for label in _ARCHETYPE_LABELS}
    if player_df.empty or "season_label" not in player_df.columns:
        return base

    sub = player_df[player_df["season_label"] == season].copy()
    if sub.empty:
        return base

    # Aggregate per player (player_id) to get season averages
    agg_cols = [c for c in ["usage", "ts", "efg", "ast_pct", "def_rtg", "reb_pct", "minutes_avg"] if c in sub.columns]
    grp = sub.groupby("player_id")
    stats_parts = []
    if agg_cols:
        stats_parts.append(grp[agg_cols].mean())

    # Compute n_games: prefer explicit n_games column (summed), else count rows per player_id
    if "n_games" in sub.columns:
        n_games_s = grp["n_games"].sum().rename("n_games")
    elif "game_id" in sub.columns:
        # If game_id is a numeric count (single row per player), sum it; else count rows
        # Heuristic: if there is only 1 row per player, use the value directly (it IS the count)
        rows_per_player = sub.groupby("player_id").size()
        single_row = (rows_per_player == 1).all()
        if single_row:
            n_games_s = grp["game_id"].sum().rename("n_games")
        else:
            n_games_s = grp["game_id"].count().rename("n_games")
    else:
        n_games_s = None

    if n_games_s is not None:
        stats_parts.append(n_games_s)

    if not stats_parts:
        return base

    season_stats = pd.concat(stats_parts, axis=1).reset_index()

    if "position" in sub.columns:
        pos_mode = sub.groupby("player_id")["position"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else "Guard"
        )
        season_stats = season_stats.merge(pos_mode.rename("position"), on="player_id", how="left")
        season_stats["position"] = season_stats["position"].fillna("Guard")
    else:
        season_stats["position"] = "Guard"

    if "n_games" in season_stats.columns:
        season_stats = season_stats[season_stats["n_games"] >= min_games].copy()

    if season_stats.empty:
        return base

    season_stats["archetype"] = season_stats.apply(_classify, axis=1)
    counts = season_stats["archetype"].value_counts().to_dict()
    for label in _ARCHETYPE_LABELS:
        base[label] = int(counts.get(label, 0))
    return base


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_seasons(
    out_dir: pathlib.Path,
    data_dir: pathlib.Path = DEFAULT_DATA_DIR,
    *,
    _team_df: Optional[pd.DataFrame] = None,
    _player_df: Optional[pd.DataFrame] = None,
) -> List[pathlib.Path]:
    """Generate NBA season atlas notes and return written paths.

    No individual player names are emitted in any output file.

    Parameters
    ----------
    out_dir:
        Directory where notes are emitted (created if absent).
    data_dir:
        Root data directory (default: <repo>/data).
    _team_df:
        Optional override for team_advanced_stats DataFrame (used in tests).
        Expected columns: team_tricode, season_label, off_rtg, def_rtg, pace, efg_pct, ts_pct.
    _player_df:
        Optional override for player archetype stats DataFrame (used in tests).
        Used only for archetype-mix counts — no names stored.
        Pass an empty DataFrame to suppress archetype section.

    Returns
    -------
    list[pathlib.Path]
        All written note files (idempotent — reruns overwrite with same content).
    """
    out_dir = pathlib.Path(out_dir)
    data_dir = pathlib.Path(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Load team data ---
    if _team_df is not None:
        team_agg = _team_df.copy()
    else:
        team_agg = _load_team_season_agg(data_dir)

    # --- Load player archetype stats (names never used) ---
    if _player_df is not None:
        player_arch_df = _player_df.copy()
    else:
        player_arch_df = _load_player_archetype_stats(data_dir)

    if team_agg.empty:
        # No data: write empty index and return
        index_path = out_dir / "_Seasons_Index.md"
        write_note(index_path, render_index([]))
        return [index_path]

    seasons = sorted(team_agg["season_label"].unique())
    written: List[pathlib.Path] = []

    # --- One note per season ---
    for season in seasons:
        season_df = team_agg[team_agg["season_label"] == season].copy()
        archetype_mix = _compute_archetype_mix(player_arch_df, season)
        note_text = render_season_note(season, season_df, archetype_mix)
        note_path = out_dir / "Seasons" / f"{season}.md"
        write_note(note_path, note_text)
        written.append(note_path)

    # --- Index note ---
    index_path = out_dir / "_Seasons_Index.md"
    write_note(index_path, render_index(seasons))
    written.append(index_path)

    return written
