"""domains.basketball_nba.memory_atlas_data — Data-loading helpers for memory_atlas.

Extracted from memory_atlas.py to keep each file ≤ 300 LOC.
All functions are internal (underscore-prefixed); import them via memory_atlas.

F5-clean: imports only stdlib, pandas, and domains.basketball_nba.*.
"""
from __future__ import annotations

import glob
import pathlib
import re
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Constants (mirrored from memory_atlas so loaders are self-contained)
# ---------------------------------------------------------------------------

_PLAYER_CACHE_GLOB = "atlas_player_*.parquet"
_TEAM_CACHE_GLOB = "atlas_team_*.parquet"

_SECTION_RE = re.compile(r"atlas_(?:player|team)_(.+)\.parquet$")


def _section_name(fpath: str) -> str:
    m = _SECTION_RE.search(fpath.replace("\\", "/"))
    return m.group(1) if m else pathlib.Path(fpath).stem


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_player_base(data_dir: pathlib.Path) -> pd.DataFrame:
    """Return merged player base table: positions + latest team + adv stats summary."""
    pos = pd.read_parquet(data_dir / "player_positions.parquet")
    pos = pos[["player_id", "display_name", "position"]].copy()

    # Player -> latest team from player_pf
    pf = pd.read_parquet(data_dir / "player_pf.parquet")
    pf["game_date"] = pd.to_datetime(pf["game_date"])
    latest_team = (
        pf.sort_values("game_date")
        .groupby("player_id")["team_abbreviation"]
        .last()
        .reset_index()
        .rename(columns={"team_abbreviation": "team"})
    )
    base = pos.merge(latest_team, on="player_id", how="left")
    return base


def _load_usage_stats(data_dir: pathlib.Path, base_pids: set) -> pd.DataFrame:
    """Load usage_role cache for usage_rate, minutes_pg, pie_mean, on_off_net_diff."""
    path = data_dir / "cache" / "atlas_player_usage_role.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["player_id"])
    df = pd.read_parquet(path)
    cols = ["player_id", "usage_rate", "minutes_pg", "pie_mean",
            "on_off_net_diff", "n_games", "creator_role"]
    present = [c for c in cols if c in df.columns]
    return df[present].copy()


def _load_adv_stats_by_player(
    data_dir: pathlib.Path,
    pids: list[int],
    *,
    _df: Optional[pd.DataFrame] = None,
) -> dict[int, pd.Series]:
    """Return dict pid -> most-recent game row from player_adv_stats."""
    if _df is not None:
        adv = _df.copy()
    else:
        adv = pd.read_parquet(data_dir / "player_adv_stats.parquet")
    adv["game_date"] = pd.to_datetime(adv["game_date"])
    adv = adv[adv["player_id"].isin(pids)]
    latest = adv.sort_values("game_date").groupby("player_id").last()
    return {int(pid): row for pid, row in latest.iterrows()}


def _load_player_sections(
    data_dir: pathlib.Path,
    pids: set,
) -> dict[int, dict[str, pd.Series]]:
    """Load all atlas_player_*.parquet and index by player_id."""
    cache_dir = data_dir / "cache"
    pattern = str(cache_dir / _PLAYER_CACHE_GLOB)
    result: dict[int, dict[str, pd.Series]] = {}

    for fpath in sorted(glob.glob(pattern)):
        section = _section_name(fpath)
        try:
            df = pd.read_parquet(fpath)
        except Exception:
            continue
        if "player_id" not in df.columns:
            continue
        df = df[df["player_id"].isin(pids)]
        df = df.set_index("player_id")
        for pid, row in df.iterrows():
            pid_int = int(pid)
            result.setdefault(pid_int, {})[section] = row

    return result


def _load_team_sections(data_dir: pathlib.Path) -> dict[str, dict[str, pd.Series]]:
    """Load all atlas_team_*.parquet and index by team_tricode."""
    cache_dir = data_dir / "cache"
    pattern = str(cache_dir / _TEAM_CACHE_GLOB)
    result: dict[str, dict[str, pd.Series]] = {}

    for fpath in sorted(glob.glob(pattern)):
        section = _section_name(fpath)
        try:
            df = pd.read_parquet(fpath)
        except Exception:
            continue
        if "team_tricode" not in df.columns:
            continue
        df = df.set_index("team_tricode")
        for tricode, row in df.iterrows():
            result.setdefault(str(tricode), {})[section] = row

    return result


def _load_team_adv(data_dir: pathlib.Path) -> dict[str, pd.Series]:
    """Return dict tricode -> season-average advanced stats row."""
    path = data_dir / "team_advanced_stats.parquet"
    if not path.exists():
        return {}
    df = pd.read_parquet(path)
    numeric = [c for c in df.columns if c not in ("game_id", "game_date", "team_tricode")]
    agg = df.groupby("team_tricode")[numeric].mean()
    return {str(tc): row for tc, row in agg.iterrows()}
