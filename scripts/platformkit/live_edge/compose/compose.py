"""scripts.platformkit.live_edge.compose.compose -- COMPOSE-2 design-matrix
builder (LIVE-EDGE Track C, the general composition test).

STEP 0 PREMISE CHECK (2026-07-14, this lane): B4-HARDEN found 0/20,109
situational claims individually beat state-only OOS at any grain (team 0/41,
player 0/20k corrected) -- see .planning/omni/live_edge_STATE.md "MAJOR
INFLECTION". Program asks: does COMBINING claims with context-gating beat
baseline where individuals were null? C1 (minutes_combiner.py) already
answered this for ONE observable (minutes) with ONE claim feature and
BEAT baseline OOS. This module generalizes C1's exact pattern (entity prior
baseline + walk-forward leak-free features, discovery/reserve split) to
MANY claim-derived features for two more observables: team scoring rate
(situation.full_grid_team, 21,487 claims) and player scoring rate
(player_cell.*, ~13k claims across 5 axes).

KEY DESIGN DECISION (avoids a redundant join): claims.parquet's
situation.full_grid_team / player_cell.* rows are each keyed on a
(entity, GROUP_COLS-subset value) cell -- i.e. they are already a 1:1
fan-out of situation_grid.GROUP_COLS / player_grid.PLAYER_CELL_PASSES axis
VALUES, exploded per entity. Re-joining 21k/13k individual claim_id rows as
separate model features would just re-derive the same one-hot axis dummies
in fragmented, entity-duplicated form (DONT-REBUILD). So "claim features"
here = one-hot dummies of the exact axis columns the claims were mined over
(imported from situation_grid / player_grid, never re-derived), which IS
every claim's condition, generically, for every entity at once -- letting
the composed model learn ONE set of weights across all of them instead of
21k/13k separate single-claim tests (that is literally the difference
between B4's per-claim test and this lane's composed test).

Target/baseline match B4-HARDEN's own instrument: team target = possession
`points`; player target = on-floor possession `scored` (player_grid). Entity
baseline = a WALK-FORWARD, leak-free per-entity prior: per-entity-per-game
mean of the target, expanding + shift(1) over that entity's own game order
(exactly minutes_combiner._add_features's shift(1)-expanding pattern),
broadcast back onto every possession row of that game -- never uses the
current game's own outcome. discovery/reserve split reuses
situation_grid.split_discovery_reserve (season boundary), never re-derived.

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/ or the claims journal. No $/edge claims.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge import situation_grid as sg
from scripts.platformkit.live_edge.player_grid import player_grid as pg
from scripts.platformkit.live_edge.replay.harden import attach_dates

TEAM_AXES = ["margin_bucket", "period_band", "pace_regime", "rest_bucket",
             "blowout_flag", "close_late_flag"]
PLAYER_AXES = ["margin_bucket", "period_band", "blowout_flag", "close_late_flag", "rest_bucket"]

MIN_PRIOR_GAMES = 5  # cold-start floor, same shape as C1's BASELINE_WINDOW_MIN_PERIODS


def _walkforward_prior(df: pd.DataFrame, entity_col: str, target_col: str) -> pd.Series:
    """Per-entity expanding mean of the target, shift(1) over strictly-prior
    GAMES (never the current game, never future games) -- the leak-free
    "state-only baseline" every composed feature must beat on top of.
    Aggregates to (entity, game) first so within-game possession order can't
    leak, then broadcasts back to row grain."""
    game_agg = (df.groupby([entity_col, "game_id"], observed=True)
                .agg(game_date=("game_date", "first"), game_mean=(target_col, "mean"))
                .reset_index().sort_values([entity_col, "game_date", "game_id"]))
    g = game_agg.groupby(entity_col)["game_mean"]
    game_agg["prior"] = g.apply(lambda s: s.shift(1).expanding(min_periods=MIN_PRIOR_GAMES).mean()).reset_index(
        level=0, drop=True)
    lookup = game_agg.set_index([entity_col, "game_id"])["prior"]
    return df.set_index([entity_col, "game_id"]).index.map(lookup)


def _add_context_dummies(df: pd.DataFrame, axes: list[str], baseline_col: str) -> tuple[pd.DataFrame, list[str], list[str]]:
    """One-hot dummies for each axis value (dropping one level per axis to
    avoid a redundant column) plus baseline x dummy interaction columns (the
    "claim x context interaction" the rails ask for)."""
    dummies = pd.get_dummies(df[axes].astype(str), prefix=axes, drop_first=True)
    dummy_cols = list(dummies.columns)
    inter = dummies.mul(df[baseline_col], axis=0)
    inter.columns = [f"{c}__x_baseline" for c in dummy_cols]
    inter_cols = list(inter.columns)
    out = pd.concat([df.reset_index(drop=True), dummies.reset_index(drop=True), inter.reset_index(drop=True)], axis=1)
    return out, dummy_cols, inter_cols


def build_team_frame(possessions_source=None, box_source=None) -> dict:
    """observable = team scoring rate. Returns dict with discovery/reserve
    frames + column lists, ready for context_gate."""
    raw = sg.load_possessions(possessions_source)
    box = sg.load_box_rate(box_source)
    tagged = sg.tag_situations(raw, box, with_lineups=False)
    tagged = attach_dates(tagged, box)
    tagged["baseline_prior"] = _walkforward_prior(tagged, "off_team", "points")
    tagged, dummy_cols, inter_cols = _add_context_dummies(tagged, TEAM_AXES, "baseline_prior")
    tagged = tagged.dropna(subset=["baseline_prior", "game_date"])
    discovery, reserve = sg.split_discovery_reserve(tagged)
    return {"discovery": discovery, "reserve": reserve, "target": "points",
            "baseline_col": "baseline_prior", "dummy_cols": dummy_cols, "inter_cols": inter_cols,
            "entity_col": "off_team", "axes": TEAM_AXES}


def build_player_frame(possessions_source=None, box_source=None, scorer_dir=None, scorer_source=None) -> dict:
    """observable = player scoring rate (points per on-floor possession).
    player_grid.build_player_frame already restricts discovery to 2024-25
    (lineup-covered) and reserve to 2025-26 -- reused as-is (DONT-REBUILD)."""
    disc_long = pg.build_player_frame("discovery", possessions_source, box_source, scorer_dir, scorer_source)
    res_long = pg.build_player_frame("reserve", possessions_source, box_source, scorer_dir, scorer_source)
    box = sg.load_box_rate(box_source)
    disc_long = attach_dates(disc_long, box)
    res_long = attach_dates(res_long, box)
    both = pd.concat([disc_long, res_long], ignore_index=True)
    both["baseline_prior"] = _walkforward_prior(both, "player_id", "scored")
    both, dummy_cols, inter_cols = _add_context_dummies(both, PLAYER_AXES, "baseline_prior")
    both = both.dropna(subset=["baseline_prior", "game_date"])
    n_disc = len(disc_long)
    # first n_disc rows (pre-concat order) are discovery; re-split by season string instead (robust to any reordering)
    discovery = both[both["season"] != sg.RESERVE_SEASON].copy()
    reserve = both[both["season"] == sg.RESERVE_SEASON].copy()
    return {"discovery": discovery, "reserve": reserve, "target": "scored",
            "baseline_col": "baseline_prior", "dummy_cols": dummy_cols, "inter_cols": inter_cols,
            "entity_col": "player_id", "axes": PLAYER_AXES}


__all__ = ["TEAM_AXES", "PLAYER_AXES", "MIN_PRIOR_GAMES", "build_team_frame", "build_player_frame"]
