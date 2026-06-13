"""domains.basketball_nba.memory_atlas — Obsidian intelligence-atlas generator for NBA.

Reads real NBA parquet files from data/ (player_adv_stats, player_positions,
player_pf, team_advanced_stats, data/cache/atlas_player_*.parquet,
data/cache/atlas_team_*.parquet) and emits a linked Obsidian markdown graph.

Public API
----------
build_atlas(out_dir, data_dir) -> list[pathlib.Path]
    Emit all notes and return the written paths.  Idempotent (reruns overwrite).

Emitted note layout::

    out_dir/
        _Index.md                         corpus hub, top-20 usage table
        Players/<Name>.md                 top ~150 players by usage rate
        Teams/<Tricode>.md                all 30 NBA teams

F5-clean: imports only stdlib, numpy, pandas, and domains.basketball_nba.*.
No src.* / kernel.* / other-domain imports.
No edge / betting language anywhere.
"""
from __future__ import annotations

import glob
import pathlib
import re
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parents[2]

DEFAULT_DATA_DIR: pathlib.Path = _REPO_ROOT / "data"
DEFAULT_OUT: pathlib.Path = _REPO_ROOT / "vault" / "Sports" / "Basketball_NBA"

TOP_N_PLAYERS: int = 150       # max player notes emitted
MIN_GAMES_PLAYER: int = 10     # skip players with fewer game appearances

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


def _build_team_roster(
    players_df: pd.DataFrame,
    adv_by_player: dict[int, pd.Series],
) -> dict[str, list[str]]:
    """Return dict tricode -> sorted list of display_names (top 10 by usage rate)."""
    roster: dict[str, list[tuple[float, str]]] = {}
    for _, r in players_df.iterrows():
        team = str(r.get("team", "—"))
        name = str(r.get("display_name", ""))
        usg = float(r.get("usage_rate", 0.0) or 0.0)
        roster.setdefault(team, []).append((usg, name))
    return {
        t: [n for _, n in sorted(players, reverse=True)[:10]]
        for t, players in roster.items()
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_atlas(
    out_dir: pathlib.Path,
    data_dir: pathlib.Path = DEFAULT_DATA_DIR,
    *,
    _adv_df: Optional[pd.DataFrame] = None,
    _base_df: Optional[pd.DataFrame] = None,
) -> list[pathlib.Path]:
    """Generate the Obsidian NBA intelligence atlas and return written paths.

    Parameters
    ----------
    out_dir:
        Directory where notes are emitted.  Created if it does not exist.
    data_dir:
        Root data directory (default: <repo>/data).
    _adv_df:
        Optional override for player_adv_stats DataFrame (used in tests).
    _base_df:
        Optional override for the merged player base table (used in tests).

    Returns
    -------
    list[pathlib.Path]
        All note files written.
    """
    from domains.basketball_nba.memory_atlas_render import render_all

    out_dir = pathlib.Path(out_dir)
    data_dir = pathlib.Path(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Base player table ---
    if _base_df is not None:
        base = _base_df.copy()
    else:
        base = _load_player_base(data_dir)

    # --- Usage stats (for ranking + sort) ---
    pids_all = set(base["player_id"].tolist())

    if data_dir.exists():
        usage = _load_usage_stats(data_dir, pids_all)
    else:
        usage = pd.DataFrame(columns=["player_id"])

    base = base.merge(usage, on="player_id", how="left")

    # Filter to players with enough games and rank by usage
    if "n_games" in base.columns:
        base = base[base["n_games"].fillna(0) >= MIN_GAMES_PLAYER]
    elif "usage_rate" in base.columns:
        base = base[base["usage_rate"].notna()]

    if "usage_rate" in base.columns:
        base = base.sort_values("usage_rate", ascending=False)
    base = base.head(TOP_N_PLAYERS).reset_index(drop=True)

    pids_top = set(int(p) for p in base["player_id"].tolist())

    # --- Per-player advanced stats (most recent game row) ---
    if _adv_df is not None:
        adv_by_player = _load_adv_stats_by_player(data_dir, list(pids_top), _df=_adv_df)
    elif (data_dir / "player_adv_stats.parquet").exists():
        adv_by_player = _load_adv_stats_by_player(data_dir, list(pids_top))
    else:
        adv_by_player = {}

    # --- Player section caches ---
    if data_dir.exists():
        player_sections = _load_player_sections(data_dir, pids_top)
    else:
        player_sections = {}

    # --- Team section caches + adv ---
    if data_dir.exists():
        team_sections = _load_team_sections(data_dir)
        team_adv_by_tricode = _load_team_adv(data_dir)
    else:
        team_sections = {}
        team_adv_by_tricode = {}

    # Ensure every team that appears in the player base gets a stub entry
    # so team notes are always emitted even when cache parquets are absent.
    for team in base["team"].dropna().unique():
        team_sections.setdefault(str(team), {})

    # --- Team roster map (top players per team by usage) ---
    team_roster = _build_team_roster(base, adv_by_player)

    return render_all(
        out_dir=out_dir,
        players_df=base,
        adv_by_player=adv_by_player,
        player_sections=player_sections,
        team_sections=team_sections,
        team_adv_by_tricode=team_adv_by_tricode,
        team_roster=team_roster,
    )
