"""scripts.platformkit.interaction_factory.builders_nba_lineup -- B7 lane
(OMNI_BUILD_PLAN Phase 1, 2026-07-13): registers 2 templates for a NEW
leak-free as-of player on/off-court family, player_game grain, matching the
builders_form_trajectory.py convention (same repo, read first).

STEP 0 PREMISE (what's on disk, decided the rung): domains/basketball_nba/
lineups/pbp_lineups.py already reconstructs 5-man on-court STINTS from raw
PBP substitution events -> data/cache/team_system/lineups/stints_<season>.
parquet (2023_24: 56432 rows/1230 games, 2024_25: 57897/1230, 2025_26:
59828/1192 -- verified via read). domains/basketball_nba/lineups/on_off.py
ALREADY aggregates these into on/off splits, but SEASON-WIDE (one row per
player-team, no game axis) -- the exact NOT-AS-OF caveat the lane brief
flags for lineup_5man/lineup_pair_trio. No as-of, per-game version existed.
This module builds that: rung (a) ("on-court lineup reconstruction -> player
on/off as-of attrs (prior-games on-court net rating proxy) at player_game
grain"), reusing the pbp reconstruction already on disk rather than
reinventing it.

METHOD: build_onoff_game_rows explodes each CLEAN (n_on_court==5) stint's
comma-joined lineup_key to one row per (player_id, team_id, game_id) --
THIS game's realized on-court seconds/pts_for/pts_against, plus the team's
game total (for off-court = team total minus on-court, same subtraction
on_off.py itself uses). build_onoff_asof then sorts by player_id/date and
applies a strictly-prior cumsum().shift(1) (same pattern as every sibling
builder's _NBA_ATTR_COLS-style as-of column) to get 3 leak-free player_game
attrs: onoff_net_on_asof (on-court net rating per48), onoff_net_off_asof
(off-court net rating per48, the team-without-this-player baseline),
onoff_min_share_asof (on-court seconds share of team's accounted time, a
rotation-depth proxy). A player's first games (insufficient prior seconds)
are honestly NaN, never fabricated -- same MIN_PRIOR_SECONDS gate pattern
as MIN_PRIOR_ATT elsewhere.

OUTCOME: player_game / efg, REUSED verbatim from nba_player_offense_asof /
nba_form_self_cross (same source parquet, same _game_efg formula, duplicated
here per the no-circular-import convention builders_form_trajectory.py's own
docstring explains -- every sibling builder module avoids importing
runner.py or each other).

TEMPLATES:
 * nba_onoff_self_cross -- self-cross over the 3-attr nba_onoff_asof
   STATIC_POOL (mirrors nba_form_self_cross's shape exactly).
 * nba_onoff_state_conditioner -- crosses the onoff pool (PRIOR) against
   nba_shot_attr_x_state's own "state" pool (late_clock_efg, clutch_efg,
   REALIZED-this-game situational split) -- same nba_state_conditioner
   pattern nba_form_state_conditioner already uses, right_pool reused
   verbatim, _state_asof_cols duplicated for the same reason as above.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_nba_lineup.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
_STINTS_DIR = REPO / "data" / "cache" / "team_system" / "lineups"
_POE_DIR = REPO / "data" / "cache" / "team_system" / "composition"
_GAMES_PATH = REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
_ONOFF_CORPUS = "onoff_asof"

# Seasons where BOTH stints_<s>.parquet and player_offense_events_<s>.parquet
# exist on disk (STEP0 premise read, 2026-07-13) -- a season missing either
# file is honestly skipped, never invented.
_SEASON_SUFFIXES = ["2023_24", "2024_25", "2025_26"]

MIN_GAME_FGA = 4          # matches runner.MIN_GAME_FGA -- min current-game FGA for a stable outcome efg
MIN_PRIOR_ATT = 20        # matches runner.MIN_PRIOR_ATT -- min strictly-prior attempts for a state-pool asof col
MIN_PRIOR_SECONDS = 600   # min strictly-prior on/off/team-accounted seconds (10 realized minutes) before an onoff asof attr is defined

ONOFF_FEATURE_COLS = ["onoff_net_on_asof", "onoff_net_off_asof", "onoff_min_share_asof"]

# nba_shot_attr_x_state's own "state" pool (a0c6da5f) -- identical entries to
# runner._NBA_ATTR_COLS / builders_form_trajectory._STATE_ATTR_COLS, duplicated
# (see module docstring for why this isn't an import).
_STATE_ATTR_COLS: Dict[str, Tuple[str, str, str]] = {
    "late_clock_efg": ("late_clock_fgm", "late_clock_fga", "late_clock_fg3m"),
    "clutch_efg": ("clutch_fgm", "clutch_fga", "clutch_fg3m"),
}


def build_onoff_game_rows(stints: pd.DataFrame) -> pd.DataFrame:
    """One row per (player_id, team_id, game_id): THIS game's realized
    on-court and off-court seconds/pts_for/pts_against, derived by exploding
    each CLEAN (n_on_court==5) stint's comma-joined lineup_key. Not yet
    as-of -- build_onoff_asof turns this into a strictly-prior feature."""
    cols = ["player_id", "team_id", "game_id", "on_secs", "on_pts_for", "on_pts_against",
            "off_secs", "off_pts_for", "off_pts_against", "team_secs"]
    clean = stints[stints["n_on_court"] == 5].copy()
    if clean.empty:
        return pd.DataFrame(columns=cols)
    clean["players"] = clean["lineup_key"].str.split(",")
    long = clean.explode("players").rename(columns={"players": "player_id"})
    # int64, not the bare python `int` alias -- on Windows numpy maps astype(int)
    # to the 32-bit C `long`, which overflows on the negative placeholder
    # personIds a handful of ESPN-backfilled players carry (pbp_lineups.py's
    # own docstring: a cross-source ID mismatch, still a stable identifier).
    long["player_id"] = long["player_id"].astype("int64")

    on = long.groupby(["player_id", "team_id", "game_id"], as_index=False).agg(
        on_secs=("elapsed_s", "sum"), on_pts_for=("pts_for", "sum"), on_pts_against=("pts_against", "sum"))
    team_tot = clean.groupby(["team_id", "game_id"], as_index=False).agg(
        team_secs=("elapsed_s", "sum"), team_pts_for=("pts_for", "sum"), team_pts_against=("pts_against", "sum"))

    merged = on.merge(team_tot, on=["team_id", "game_id"], how="left")
    merged["off_secs"] = merged["team_secs"] - merged["on_secs"]
    merged["off_pts_for"] = merged["team_pts_for"] - merged["on_pts_for"]
    merged["off_pts_against"] = merged["team_pts_against"] - merged["on_pts_against"]
    return merged[cols]


def build_onoff_asof(stints: pd.DataFrame, games: pd.DataFrame,
                      min_prior_seconds: int = MIN_PRIOR_SECONDS) -> pd.DataFrame:
    """Per-(player_id, game_id) STRICTLY-PRIOR (chronological sort then
    cumsum().shift(1) -- this game's own on/off numbers are never in its own
    feature) on-court net rating, off-court net rating, and on-court
    minutes-share. Games with no games.parquet date match are honestly
    dropped (never a made-up chronological order)."""
    out_cols = ["player_id", "game_id"] + ONOFF_FEATURE_COLS
    rows = build_onoff_game_rows(stints)
    if rows.empty:
        return pd.DataFrame(columns=out_cols)
    rows = rows.merge(games, on="game_id", how="inner")
    rows = rows.sort_values(["player_id", "date", "game_id"]).reset_index(drop=True)
    grp = rows.groupby("player_id", sort=False)

    def _cum_shift(col: str) -> pd.Series:
        return grp[col].transform(lambda s: s.cumsum().shift(1))

    cum_on_secs, cum_on_pf, cum_on_pa = _cum_shift("on_secs"), _cum_shift("on_pts_for"), _cum_shift("on_pts_against")
    cum_off_secs, cum_off_pf, cum_off_pa = _cum_shift("off_secs"), _cum_shift("off_pts_for"), _cum_shift("off_pts_against")
    cum_team_secs = _cum_shift("team_secs")

    out = rows[["player_id", "game_id"]].copy()
    out["onoff_net_on_asof"] = ((cum_on_pf - cum_on_pa) / cum_on_secs * 2880.0).where(cum_on_secs >= min_prior_seconds)
    out["onoff_net_off_asof"] = ((cum_off_pf - cum_off_pa) / cum_off_secs * 2880.0).where(cum_off_secs >= min_prior_seconds)
    out["onoff_min_share_asof"] = (cum_on_secs / cum_team_secs).where(cum_team_secs >= min_prior_seconds)
    return out


def _game_efg(poe: pd.DataFrame) -> pd.Series:
    """THIS game's REAL (not as-of) eFG -- identical formula to runner.build_
    nba_offense_frame's own `y` (duplicated -- module docstring)."""
    three = poe.get("above_break_3_fgm", 0).fillna(0) + poe.get("corner3_fgm", 0).fillna(0)
    return (poe["total_fgm"] + 0.5 * three) / poe["total_fga"].where(poe["total_fga"] > 0)


def _outcome_frame(poe: pd.DataFrame, min_game_fga: int = MIN_GAME_FGA) -> pd.DataFrame:
    y = poe[["player_id", "game_id"]].copy()
    y["y"] = _game_efg(poe)
    return y[poe["total_fga"] >= min_game_fga]


def _state_asof_cols(poe: pd.DataFrame, attrs: List[str], min_prior_att: int = MIN_PRIOR_ATT) -> pd.DataFrame:
    """asof__<attr> for whichever of late_clock_efg/clutch_efg are requested
    (identical formula to runner._NBA_ATTR_COLS -- module docstring)."""
    poe = poe.sort_values(["player_id", "date", "game_id"]).reset_index(drop=True)
    grp = poe.groupby("player_id", sort=False)
    out = poe[["player_id", "game_id"]].copy()
    for attr in attrs:
        if attr not in _STATE_ATTR_COLS:
            continue
        fgm_c, fga_c, fg3_c = _STATE_ATTR_COLS[attr]
        cum_fgm = grp[fgm_c].transform(lambda s: s.fillna(0).cumsum().shift(1))
        cum_fga = grp[fga_c].transform(lambda s: s.fillna(0).cumsum().shift(1))
        cum_fg3 = grp[fg3_c].transform(lambda s: s.fillna(0).cumsum().shift(1))
        out["asof__" + attr] = (cum_fgm + 0.5 * cum_fg3) / cum_fga.where(cum_fga >= min_prior_att)
    return out


def build_nba_onoff_self_cross_frame(onoff: pd.DataFrame, poe: pd.DataFrame,
                                      attrs: List[str], min_game_fga: int = MIN_GAME_FGA) -> pd.DataFrame:
    """Per-(player, game) frame for the onoff self-cross template: y = THIS
    game's real eFG, asof__<attr> from build_onoff_asof's own strictly-prior
    columns."""
    merged = onoff.merge(_outcome_frame(poe, min_game_fga), on=["player_id", "game_id"], how="inner")
    rename = {a: "asof__" + a for a in attrs if a in merged.columns}
    merged = merged.rename(columns=rename)
    keep = ["player_id", "game_id", "y"] + list(rename.values())
    return merged[keep].copy()


def build_nba_onoff_state_conditioner_frame(onoff: pd.DataFrame, poe: pd.DataFrame,
                                             attrs: List[str], min_game_fga: int = MIN_GAME_FGA,
                                             min_prior_att: int = MIN_PRIOR_ATT) -> pd.DataFrame:
    """Per-(player, game) frame for the onoff-prior x state-pool cross: y =
    THIS game's real eFG, asof__<onoff attr> from build_onoff_asof (the
    PRIOR), asof__<state attr> from late_clock_efg/clutch_efg's own
    strictly-prior split. An attr in neither pool is honestly dropped."""
    onoff_attrs = [a for a in attrs if a in ONOFF_FEATURE_COLS]
    state_attrs = [a for a in attrs if a in _STATE_ATTR_COLS]
    merged = onoff.merge(_outcome_frame(poe, min_game_fga), on=["player_id", "game_id"], how="inner")
    merged = merged.rename(columns={a: "asof__" + a for a in onoff_attrs if a in merged.columns})
    if state_attrs:
        merged = merged.merge(_state_asof_cols(poe, state_attrs, min_prior_att),
                               on=["player_id", "game_id"], how="left")
    keep = ["player_id", "game_id", "y"] + [
        "asof__" + a for a in onoff_attrs + state_attrs if ("asof__" + a) in merged.columns]
    return merged[keep].copy()


def _read_stints_and_poe() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    stints_frames, poe_frames = [], []
    for suf in _SEASON_SUFFIXES:
        sp, pp = _STINTS_DIR / f"stints_{suf}.parquet", _POE_DIR / f"player_offense_events_{suf}.parquet"
        if sp.exists() and pp.exists():
            stints_frames.append(pd.read_parquet(sp))
            poe_frames.append(pd.read_parquet(pp))
    if not stints_frames:
        return None, None
    return pd.concat(stints_frames, ignore_index=True), pd.concat(poe_frames, ignore_index=True)


def _read_all() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    stints, poe = _read_stints_and_poe()
    if stints is None or not _GAMES_PATH.exists():
        return None, None
    games = pd.read_parquet(_GAMES_PATH)[["game_id", "date"]]
    onoff = build_onoff_asof(stints, games)
    return (onoff, poe) if not onoff.empty else (None, None)


def _nba_onoff_self_cross_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    onoff, poe = _read_all()
    if onoff is None:
        return None
    frame = build_nba_onoff_self_cross_frame(onoff, poe, attrs)
    return {"frame": frame, "cluster": "player_id", "corpus": _ONOFF_CORPUS, "kind": "ols"}


def _nba_onoff_state_conditioner_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    onoff, poe = _read_all()
    if onoff is None:
        return None
    frame = build_nba_onoff_state_conditioner_frame(onoff, poe, attrs)
    return {"frame": frame, "cluster": "player_id", "corpus": _ONOFF_CORPUS, "kind": "ols"}


__all__ = [
    "ONOFF_FEATURE_COLS", "build_onoff_game_rows", "build_onoff_asof",
    "build_nba_onoff_self_cross_frame", "build_nba_onoff_state_conditioner_frame",
    "_nba_onoff_self_cross_builder", "_nba_onoff_state_conditioner_builder",
]
