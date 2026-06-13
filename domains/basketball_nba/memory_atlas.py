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
        Teams/<Tricode>.md                all 30 NBA teams (no player names)

Team notes contain archetype composition counts (e.g. "2 High-Usage Creators,
3 Low-Usage Connectors") rather than individual player names.

F5-clean: imports only stdlib, numpy, pandas, and domains.basketball_nba.*.
No src.* / kernel.* / other-domain imports.
No edge / betting language anywhere.
"""
from __future__ import annotations

import pathlib
from typing import Optional

import pandas as pd

from domains.basketball_nba.memory_atlas_data import (
    _load_player_base,
    _load_usage_stats,
    _load_adv_stats_by_player,
    _load_player_sections,
    _load_team_sections,
    _load_team_adv,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parents[2]

DEFAULT_DATA_DIR: pathlib.Path = _REPO_ROOT / "data"
DEFAULT_OUT: pathlib.Path = _REPO_ROOT / "vault" / "Sports" / "Basketball_NBA"

TOP_N_PLAYERS: int = 150       # max player notes emitted
MIN_GAMES_PLAYER: int = 10     # skip players with fewer game appearances


# ---------------------------------------------------------------------------
# Archetype composition helper
# ---------------------------------------------------------------------------

def _build_team_archetype_composition(
    players_df: pd.DataFrame,
    adv_by_player: dict[int, pd.Series],
) -> dict[str, list[tuple[int, str]]]:
    """Return dict tricode -> archetype composition as (count, label) pairs.

    Each player is classified into one of the 10 archetypes defined in
    ``domains.basketball_nba.memory_atlas_archetypes`` using only team-
    aggregate per-player statistics already present in *players_df*.  No
    player names are stored or returned.

    Parameters
    ----------
    players_df:
        Merged player base table (player_id, team, usage_rate, …).
    adv_by_player:
        Dict of pid -> most-recent advanced-stats row (may be empty).

    Returns
    -------
    dict[str, list[tuple[int, str]]]
        ``{tricode: [(count, archetype_label), …]}`` sorted descending by count,
        ties broken alphabetically.  Only archetypes with count >= 1 are included.
    """
    from collections import Counter

    try:
        from domains.basketball_nba.memory_atlas_archetypes import _classify
    except ImportError:
        # Graceful degradation: return empty composition if module unavailable
        return {}

    team_archetype_counts: dict[str, Counter] = {}
    for _, r in players_df.iterrows():
        team = str(r.get("team", "—"))
        pid = int(r.get("player_id", 0))

        # Build a stat row compatible with _classify
        adv = adv_by_player.get(pid)
        stat_row = pd.Series(
            {
                "usage": float(r.get("usage_rate", 0.0) or 0.0),
                "ts": float(adv.get("trueshootingpercentage", 0.0) if adv is not None else 0.0),
                "efg": float(adv.get("effectivefieldgoalpercentage", 0.0) if adv is not None else 0.0),
                "ast_pct": float(adv.get("assistpercentage", 0.0) if adv is not None else 0.0),
                "def_rtg": float(adv.get("defensiverating", 999.0) if adv is not None else 999.0),
                "reb_pct": float(adv.get("reboundpercentage", 0.0) if adv is not None else 0.0),
                "minutes_avg": float(r.get("minutes_pg", 0.0) or 0.0),
                "position": str(r.get("position", "") or ""),
            }
        )
        arch_label = _classify(stat_row)
        team_archetype_counts.setdefault(team, Counter())[arch_label] += 1

    return {
        t: sorted(
            [(cnt, lbl) for lbl, cnt in ctr.items() if cnt >= 1],
            key=lambda x: (-x[0], x[1]),
        )
        for t, ctr in team_archetype_counts.items()
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

    # --- Team archetype composition (name-free counts per team) ---
    team_archetype_composition = _build_team_archetype_composition(base, adv_by_player)

    return render_all(
        out_dir=out_dir,
        players_df=base,
        adv_by_player=adv_by_player,
        player_sections=player_sections,
        team_sections=team_sections,
        team_adv_by_tricode=team_adv_by_tricode,
        team_archetype_composition=team_archetype_composition,
    )
