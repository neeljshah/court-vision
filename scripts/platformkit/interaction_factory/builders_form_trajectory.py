"""scripts.platformkit.interaction_factory.builders_form_trajectory -- Sonnet
build-lane follow-on to 149870ff (salvaged as-of form_trajectory rebuild):
registers the 2 form_trajectory_asof.parquet templates (nba_form_self_cross,
nba_form_state_conditioner), split out per the builders_carryover.py /
builders_ingame_state.py / builders_state_conditioner.py convention (keeps
runner.py under its LOC budget). Same contract as any other runner builder:
`builder(attrs, tpl) -> {"frame", "cluster", "corpus", "kind", ...} | None` --
registered into runner._BUILDERS by runner.py itself.

SOURCE: data/cache/signals/form_trajectory_asof.parquet (149870ff -- keyed
player_id/season/game_id/game_date, leak-free strictly-prior l5/l10 pts/min/
ts_pct + trend_pts_slope10 + dev_pts_vs_baseline; first-game-of-season rows
are honestly NaN, never faked). No outcome column of its own, so `y` is
sourced from data/cache/team_system/composition/player_offense_events_
<season>.parquet the SAME way runner.build_nba_offense_frame computes it for
nba_player_offense_asof -- THIS game's real eFG. That formula is duplicated
here (2 lines, _game_efg) rather than imported from runner.py: runner.py
imports every sibling builder module at load time (see its _BUILDERS block),
so a reverse import (this module importing FROM runner) would be circular;
every existing sibling builder module (builders_carryover, builders_ingame_
state, builders_state_conditioner, builders_statcast_fatigue) avoids
importing runner.py for the identical reason.

ATOMIC UNIT / OUTCOME: player_game / efg -- REUSED verbatim from nba_
player_offense_asof / nba_offense_state_asof (both player_game-grain, same
source parquet), not invented: form_trajectory_asof's own grain (player_id,
game_id) already matches theirs exactly.

TEMPLATES:
 * nba_form_self_cross -- self-cross over the 8-attr nba_form_asof STATIC_POOL
   (generator.STATIC_POOLS; not domains/basketball_nba/profiles/attribute_
   registry.py, outside this lane's OWNS, same STATIC_POOL seam builders_
   statcast_fatigue.py / builders_statcast_batquality.py use for pools not in
   a per-sport registry). n_prior_games and baseline_pts are DELIBERATELY
   excluded from the pool (10 source cols -> 8): n_prior_games is a sample-
   size/coverage counter used by the SOURCE builder to gate when the other
   features leave NaN (149870ff), not itself a form signal; baseline_pts is
   an exact linear function of 2 already-included columns (dev_pts_vs_
   baseline = l5_pts - baseline_pts, per build_form_trajectory_asof.py:109)
   so it carries no information the pool doesn't already have.
 * nba_form_state_conditioner -- the nba_state_conditioner pattern (85a8ee80/
   a0c6da5f: cross a PRIOR pool against a REALIZED "state" pool). Right_pool
   is {"attributes": ["late_clock_efg", "clutch_efg"]} -- nba_shot_attr_x_
   state's own right_pool, the exact pool commit a0c6da5f's own message calls
   "state" pool ("late_clock_efg, clutch_efg... same zone/situational eFG
   split family") -- REUSED verbatim, not reinvented, and the SAME player_
   game grain as form_trajectory_asof (its asof__ cols are computed here with
   the identical strictly-prior cumsum-shift formula runner._NBA_ATTR_COLS/
   build_nba_offense_frame uses, duplicated for the same import-cycle reason
   as _game_efg above). The TEAM-grain ingame_state_asof family 85a8ee80
   itself crosses (q1_margin_asof etc) is NOT used here: it has no team_id-
   <->abbr crosswalk on disk within this lane's OWNS scope (linescores.parquet/
   asof_quarter_shape.parquet/carryover_asof.parquet carry only home_abbr/
   away_abbr or pre-diffed home-minus-away columns, no team_id to bridge
   against player_offense_events' own team_id column) -- pairing form against
   a genuinely unbridgeable pool would be invented plumbing, not a builder
   shim, so the codebase's OWN literal "state" pool is used instead.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_form_trajectory.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
_FORM_SOURCE = REPO / "data" / "cache" / "signals" / "form_trajectory_asof.parquet"
_POE_DIR = REPO / "data" / "cache" / "team_system" / "composition"
_FORM_CORPUS = "form_trajectory_asof"
MIN_GAME_FGA = 4       # matches runner.MIN_GAME_FGA -- min current-game FGA for a stable outcome efg
MIN_PRIOR_ATT = 20     # matches runner.MIN_PRIOR_ATT -- min strictly-prior attempts for a state-pool asof col

# The 8 informative form_trajectory_asof.parquet columns (n_prior_games and
# baseline_pts excluded -- see module docstring).
FORM_FEATURE_COLS = [
    "l5_pts", "l10_pts", "l5_min", "l10_min",
    "l5_ts_pct", "l10_ts_pct", "trend_pts_slope10", "dev_pts_vs_baseline",
]

# nba_shot_attr_x_state's own "state" pool (a0c6da5f) -- (fgm_col, fga_col,
# fg3m_col), identical entries to runner._NBA_ATTR_COLS, duplicated (see
# module docstring for why this isn't an import).
_STATE_ATTR_COLS: Dict[str, Tuple[str, str, str]] = {
    "late_clock_efg": ("late_clock_fgm", "late_clock_fga", "late_clock_fg3m"),
    "clutch_efg": ("clutch_fgm", "clutch_fga", "clutch_fg3m"),
}


def _poe_source_for_season(season_hyphen: str) -> Path:
    """form_trajectory_asof's season string ('2023-24') -> player_offense_
    events_<season>.parquet's own underscore convention ('2023_24')."""
    return _POE_DIR / ("player_offense_events_%s.parquet" % season_hyphen.replace("-", "_"))


def _read_poe_seasons(seasons: List[str]) -> pd.DataFrame:
    """Concat whichever player_offense_events_<season>.parquet files exist for
    the given form_trajectory seasons; a season with no matching file (e.g.
    2022-23, never built for this source) is honestly dropped, not invented."""
    frames = [pd.read_parquet(p) for s in sorted(set(seasons))
              for p in [_poe_source_for_season(s)] if p.exists()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _game_efg(poe: pd.DataFrame) -> pd.Series:
    """THIS game's REAL (not as-of) eFG -- identical formula to runner.build_
    nba_offense_frame's own `y` (duplicated, not imported -- module docstring)."""
    three = poe.get("above_break_3_fgm", 0).fillna(0) + poe.get("corner3_fgm", 0).fillna(0)
    return (poe["total_fgm"] + 0.5 * three) / poe["total_fga"].where(poe["total_fga"] > 0)


def _state_asof_cols(poe: pd.DataFrame, attrs: List[str], min_prior_att: int = MIN_PRIOR_ATT) -> pd.DataFrame:
    """asof__<attr> for whichever of late_clock_efg/clutch_efg are requested:
    strictly-prior cumulative eFG in that situational split, identical formula
    to runner._NBA_ATTR_COLS/build_nba_offense_frame (module docstring)."""
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


def _outcome_frame(poe: pd.DataFrame, min_game_fga: int = MIN_GAME_FGA) -> pd.DataFrame:
    y = poe[["player_id", "game_id"]].copy()
    y["y"] = _game_efg(poe)
    return y[poe["total_fga"] >= min_game_fga]


def build_nba_form_self_cross_frame(form: pd.DataFrame, poe: pd.DataFrame,
                                     attrs: List[str], min_game_fga: int = MIN_GAME_FGA) -> pd.DataFrame:
    """Per-(player, game) frame for the form self-cross template: y = THIS
    game's real eFG, asof__<attr> = form_trajectory_asof's own strictly-prior
    columns verbatim (n_prior_games==0 rows are NaN by the SOURCE builder's
    own leak rule, 149870ff -- never faked here, only passed through)."""
    merged = form.merge(_outcome_frame(poe, min_game_fga), on=["player_id", "game_id"], how="inner")
    merged = merged.rename(columns={a: "asof__" + a for a in attrs if a in merged.columns})
    keep = ["player_id", "game_id", "y"] + ["asof__" + a for a in attrs if ("asof__" + a) in merged.columns]
    return merged[keep].copy()


def build_nba_form_state_conditioner_frame(form: pd.DataFrame, poe: pd.DataFrame,
                                            attrs: List[str], min_game_fga: int = MIN_GAME_FGA,
                                            min_prior_att: int = MIN_PRIOR_ATT) -> pd.DataFrame:
    """Per-(player, game) frame for the form-prior x state-pool cross: y =
    THIS game's real eFG (same as self-cross), asof__<form attr> from form_
    trajectory_asof (the PRIOR), asof__<state attr> from late_clock_efg/
    clutch_efg's own strictly-prior split (the nba_shot_attr_x_state "state"
    pool, REUSED -- module docstring). An attr in neither pool is honestly
    dropped, never invented."""
    form_attrs = [a for a in attrs if a in FORM_FEATURE_COLS]
    state_attrs = [a for a in attrs if a in _STATE_ATTR_COLS]
    merged = form.merge(_outcome_frame(poe, min_game_fga), on=["player_id", "game_id"], how="inner")
    merged = merged.rename(columns={a: "asof__" + a for a in form_attrs if a in merged.columns})
    if state_attrs:
        merged = merged.merge(_state_asof_cols(poe, state_attrs, min_prior_att),
                               on=["player_id", "game_id"], how="left")
    keep = ["player_id", "game_id", "y"] + [
        "asof__" + a for a in form_attrs + state_attrs if ("asof__" + a) in merged.columns]
    return merged[keep].copy()


def _read_form_and_poe() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    if not _FORM_SOURCE.exists():
        return None, None
    form = pd.read_parquet(_FORM_SOURCE)
    poe = _read_poe_seasons(sorted(form["season"].unique()))
    return (form, poe) if not poe.empty else (None, None)


def _nba_form_self_cross_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    form, poe = _read_form_and_poe()
    if form is None:
        return None
    frame = build_nba_form_self_cross_frame(form, poe, attrs)
    return {"frame": frame, "cluster": "player_id", "corpus": _FORM_CORPUS, "kind": "ols"}


def _nba_form_state_conditioner_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    form, poe = _read_form_and_poe()
    if form is None:
        return None
    frame = build_nba_form_state_conditioner_frame(form, poe, attrs)
    return {"frame": frame, "cluster": "player_id", "corpus": _FORM_CORPUS, "kind": "ols"}


__all__ = [
    "FORM_FEATURE_COLS", "build_nba_form_self_cross_frame", "build_nba_form_state_conditioner_frame",
    "_nba_form_self_cross_builder", "_nba_form_state_conditioner_builder",
]
