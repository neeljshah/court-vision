"""scripts.platformkit.live_edge.player_grid.player_grid -- PLAYER-grain
situation join (player analog of B1's situation_grid.py), on the new
scorer_possession substrate.

PREMISE CHECK (2026-07-14, this lane): data/omni/live_edge/player_attr/
scorer_possession_{2023_24,2024_25,2025_26}.parquet exist, one row per
sim2_possessions possession, columns [period, clock_start, off_is_home,
points, scorer_player_id, scorer_points, n_scorers, game_id, season,
poss_idx]. Verified `poss_idx` is EXACTLY the same key situation_grid uses
for possession_key (per-game_id row-order cumcount): joining sim2_possessions
(with poss_idx = groupby(game_id).cumcount()) to scorer_possession on
(game_id, poss_idx) reproduces period/clock_start/off_is_home/points 1:1 for
all 263,003 2023-24 rows. Attribution rate on scoring possessions: 96.1%
(2023-24), 99.97% (2024-25), 99.8% (2025-26) -- matches the "~99.97%" claim
for 2024-25 exactly; 2023-24 is somewhat lower but still near-complete.

ON-FLOOR DENOMINATOR: scorer_possession has no per-possession roster, only
who scored. To get a real "player was on the floor" denominator (required
to test a player's scoring RATE, not just scoring-event size) this module
reuses situation_grid.attach_lineups, which covers 2024-25 + 2025-26 ONLY
(2023-24 has no stint store -- same DATA_ABSENT already documented in
situation_grid.py). Consequence: player-grid discovery mining in this lane
uses 2024-25 ONLY (2023-24 is dropped for lack of an on-floor roster), and
OOS validation uses the full 2025-26 reserve (also lineup-covered). This is
a real cut versus B1's team-grain discovery (which needs no roster), traded
for a well-defined per-player rate; noted honestly, not hidden.
(ponytail: no archetype-pooling layer here -- thin cells are floored to
INSUFFICIENT_DATA same as B1; add pooling if floor-skip rate is too high.)

Observable: for each on-floor offensive possession, `scored` = the player's
OWN scorer_points if they were the recorded scorer that possession, else 0.
Per (player, situation-cell) this is exactly the B1 pattern (cell mean vs
complement) except the complement is that SAME PLAYER's other on-floor
possessions -- never other players' rows -- per program task ("vs that
player's baseline").
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge import situation_grid as sg

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
SCORER_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "player_attr"
SEASON_FILE = {
    "2023-24": "scorer_possession_2023_24.parquet",
    "2024-25": "scorer_possession_2024_25.parquet",
    "2025-26": "scorer_possession_2025_26.parquet",
}

# Marginal (single-axis) passes -- thinner per-player cells than B1's full
# 6-way cross need higher power per axis; mirrors B1's rest_marginal pattern.
PLAYER_CELL_PASSES = {
    "player_margin": ["margin_bucket"],
    "player_period": ["period_band"],
    "player_blowout": ["blowout_flag"],
    "player_close_late": ["close_late_flag"],
    "player_rest": ["rest_bucket"],  # pregame-knowable
}
IN_GAME_ONLY = {
    "player_margin": True, "player_period": True, "player_blowout": True,
    "player_close_late": True, "player_rest": False,
}


def load_scorer_possessions(season: str, scorer_dir=None, source=None) -> pd.DataFrame:
    cols = ["game_id", "poss_idx", "scorer_player_id", "scorer_points"]
    if isinstance(source, dict):
        return source[season][cols].copy()
    base = pathlib.Path(scorer_dir) if scorer_dir is not None else SCORER_DIR
    return pd.read_parquet(base / SEASON_FILE[season], columns=cols)


def attach_scorer(tagged_df: pd.DataFrame, scorer_dir=None, scorer_source=None) -> pd.DataFrame:
    """Join scorer_player_id/scorer_points via (game_id, poss_idx==per-game
    cumcount) -- exact-match join, see module docstring premise check."""
    out = tagged_df.copy()
    out["poss_idx"] = out.groupby("game_id").cumcount()
    parts = []
    for season in out["season"].unique():
        scorer = load_scorer_possessions(season, scorer_dir, scorer_source)
        sub = out[out["season"] == season].merge(scorer, on=["game_id", "poss_idx"], how="left")
        parts.append(sub)
    return pd.concat(parts, ignore_index=True)


def explode_on_floor(df: pd.DataFrame) -> pd.DataFrame:
    """Long format: one row per (possession, on-floor offensive player),
    restricted to lineup_available rows. `scored` = that player's own
    scorer_points if they were the recorded scorer this possession, else 0."""
    lu = df[df["lineup_available"]].copy()
    lu["player_id"] = lu["off_lineup_ids"].str.split(",")
    long = lu.explode("player_id")
    long["player_id"] = long["player_id"].astype(str)
    scorer_id_str = long["scorer_player_id"].apply(lambda v: "" if pd.isna(v) else str(int(v)))
    long["scored"] = np.where(long["player_id"] == scorer_id_str, long["scorer_points"], 0).astype(float)
    return long.drop(columns=["off_lineup_ids", "def_lineup_ids", "scorer_player_id"], errors="ignore")


def build_player_frame(slice: str = "discovery", possessions_source=None, box_source=None,
                        scorer_dir=None, scorer_source=None) -> pd.DataFrame:
    """slice='discovery' -> 2023-24+2024-25 possessions (only 2024-25 rows
    survive explode_on_floor's lineup_available filter); slice='reserve' ->
    2025-26 only. Never mixes the two."""
    poss = sg.load_possessions(possessions_source)
    box_df = sg.load_box_rate(box_source)
    discovery, reserve = sg.split_discovery_reserve(poss)
    poss = discovery if slice == "discovery" else reserve
    tagged = sg.tag_situations(poss, box_df, with_lineups=True)
    scored = attach_scorer(tagged, scorer_dir, scorer_source)
    return explode_on_floor(scored)


__all__ = [
    "REPO_ROOT", "SCORER_DIR", "SEASON_FILE", "PLAYER_CELL_PASSES", "IN_GAME_ONLY",
    "load_scorer_possessions", "attach_scorer", "explode_on_floor", "build_player_frame",
]
