"""scripts.platformkit.live_edge.replay.tick_replay -- B4 tick-grain replayer.

Walks the possession-grain series (data/cache/ingame/sim2_possessions.parquet,
780,166 rows / 3,652 games) in natural row order for a game and, at each
tick, exposes (current_state, active_situation_cells) -- the "every second
matters" engine B4 needs to ask "which claim conditions are ACTIVE right
now?" at any point in a game.

OOS DISCIPLINE (binding): B1 mined situational cells on the DISCOVERY slice
only (2023-24 + 2024-25, see situation_grid.RESERVE_SEASON). This module
only ever loads and tags the RESERVE slice (2025-26) for validation use --
never re-touches discovery rows. Reuses situation_grid's tagging (same axis
definitions) rather than re-deriving margin/period/pace bucket logic, per
DONT-REBUILD.

NEW module (premise-checked 2026-07-14: no replay/ package existed before
this lane). Sibling B1 module scripts/platformkit/live_edge/situation_grid.py
is IMPORTED, never edited (B1 owns it).
"""
from __future__ import annotations

import pathlib
from typing import Iterator

import pandas as pd

from scripts.platformkit.live_edge.situation_grid import (
    GROUP_COLS,
    load_box_rate,
    load_possessions,
    split_discovery_reserve,
    tag_situations,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]


def load_reserve_tagged(possessions_source=None, box_source=None, with_lineups: bool = True) -> pd.DataFrame:
    """Load + situation-tag ONLY the reserve season (2025-26) slice. Rows
    are returned in their on-disk order per game_id, which IS tick order
    (sim2_possessions is written possession-by-possession; situation_grid's
    own possession_key reconstruction relies on the same invariant).
    with_lineups=True by default -- 2025-26 is fully covered by
    situation_grid.LINEUP_SEASONS, needed to validate B1's lineup_unit
    claim family (entity_type="lineup", matched on off_lineup_ids)."""
    raw = load_possessions(possessions_source)
    _, reserve_raw = split_discovery_reserve(raw)
    box = load_box_rate(box_source)
    return tag_situations(reserve_raw, box, with_lineups=with_lineups)


def discovery_baseline_ppp(possessions_source=None) -> float:
    """State-only baseline: unconditional mean points-per-possession fit on
    the DISCOVERY slice only (never the reserve slice under test) -- the
    'no situational information' predictor every claim must beat."""
    raw = load_possessions(possessions_source)
    discovery, _ = split_discovery_reserve(raw)
    return float(discovery["points"].mean())


def cell_key(state: dict, group_cols=None) -> tuple:
    """Situation cell as a hashable key, in canonical GROUP_COLS order."""
    cols = group_cols or GROUP_COLS
    return tuple(state[c] for c in cols)


def active_mask_for_cell(tagged_df: pd.DataFrame, cell: dict,
                          entity_type: str = "league", entity_ids: list | None = None) -> pd.Series:
    """Boolean mask: possessions where every axis in *cell* matches AND (for
    team/lineup-scoped claims) the specific entity is on offense -- i.e.
    this claim's exact condition is ACTIVE. Mirrors grid_sweep.py's
    _claim_for_row scoping: team claims key on off_team, lineup claims key
    on off_lineup_ids (offense-only, per grid_sweep's lineup_unit pass)."""
    mask = pd.Series(True, index=tagged_df.index)
    for key, value in cell.items():
        if key in tagged_df.columns:
            mask &= tagged_df[key] == value
    entity_ids = entity_ids or []
    if entity_type == "team" and entity_ids:
        mask &= tagged_df["off_team"] == entity_ids[0]
    elif entity_type == "lineup" and entity_ids:
        mask &= tagged_df.get("off_lineup_ids", pd.Series(pd.NA, index=tagged_df.index)) == entity_ids[0]
    return mask


def replay_game(tagged_df: pd.DataFrame, game_id) -> Iterator[tuple]:
    """Walk one game's possessions in tick order. Yields
    (tick_idx, state_dict, active_cell_key, points) per possession -- the
    per-tick view: 'at this instant, which situation is active, what
    happened'."""
    game_df = tagged_df[tagged_df["game_id"] == game_id]
    for tick_idx, (_, row) in enumerate(game_df.iterrows()):
        state = {col: row[col] for col in GROUP_COLS}
        state["period"] = row["period"]
        state["clock_start"] = row["clock_start"]
        yield tick_idx, state, cell_key(state), row["points"]


__all__ = [
    "REPO_ROOT",
    "load_reserve_tagged",
    "discovery_baseline_ppp",
    "cell_key",
    "active_mask_for_cell",
    "replay_game",
]
