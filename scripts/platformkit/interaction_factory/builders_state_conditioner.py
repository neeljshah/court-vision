"""scripts.platformkit.interaction_factory.builders_state_conditioner -- A22a
(.planning/WEEKEND_PLAN_2026-07-10.md Q7, slice a): the nba_state_conditioner
CROSS builder (generator.TEMPLATES["nba_state_conditioner"]), split out per
the builders_carryover.py / builders_ingame_state.py convention (keeps
runner.py under its LOC budget). Same contract as any other runner builder:
`builder(attrs, tpl) -> {"frame", "cluster", "corpus", "kind", ...} | None` --
registered into runner._BUILDERS by runner.py itself.

WHAT THIS TESTS (.planning/PROVEN_EDGE_ROADMAP.md section 5.1's "state-
conditioned distribution" growth item, replicating the MLB in-game-moat
pattern to NBA): does a team's PREGAME carryover prior (rest_days_asof /
heavy_min_load_asof -- carryover_asof family, domains/basketball_nba/
knowledge/mechanisms.md #14 b2b_rest_penalty, CONFIRMED avg margin -1.73
pregame, p=0.0056, n=4,732) interact with a REALIZED early-game state read
(q1_margin_asof etc -- ingame_state_asof family, mechanisms.md #34
q1_slow_start_persists_split_half) to predict the REST of the current game's
margin better than either alone -- "condition a pregame prior on a
realized-state attribute", the factory's declared state-conditioning shape.
This module builds CANDIDATES only; the real leak-free gate (runner.
run_batch) decides SURVIVES/NULL, never this module.

SOURCES (both already leak-free as-of files on disk, invents nothing):
 * carryover_asof.parquet (domains.basketball_nba.carryover_asof) -- keyed
   game_id, SUFFIX diff-col convention (<metric>_diff_asof, same as
   box_detail_asof -- reuses builders_task39b._nba_boxdetail_diff_col
   verbatim, same string transform).
 * asof_quarter_shape.parquet (domains.basketball_nba.asof_quarter_shape) --
   keyed game_id AND event_id (the only of the two sources carrying event_id,
   so it doubles as the game_id<->event_id BRIDGE), PREFIX diff-col
   convention (diff_<metric>_asof -- reuses builders_ingame_state.
   _ingame_state_diff_col verbatim).
 * linescores.parquet, via builders_ingame_state._rest_of_game_margin
   (reused verbatim) -- the REAL (not as-of) Q2+Q3+Q4 outcome margin.

OUTCOME / cluster / kind: identical shape to nba_ingame_state_self_cross
(rest_of_game_margin, cluster=event_id, kind=ols, no Elo covariate) -- this
template differs from that one only in WHERE its two pool attrs come from
(cross between two families, not a self_cross within one family).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.interaction_factory.builders_carryover import _NBA_CARRYOVER_SOURCE
from scripts.platformkit.interaction_factory.builders_ingame_state import (
    _ingame_state_diff_col, _rest_of_game_margin,
    _NBA_LINESCORES_SOURCE, _NBA_QSHAPE_SOURCE,
)
from scripts.platformkit.interaction_factory.builders_task39b import _nba_boxdetail_diff_col

_NBA_STATE_CONDITIONER_CORPUS = "state_conditioner_asof"


def build_nba_state_conditioner_frame(attrs: List[str], carryover: pd.DataFrame,
                                       qshape: pd.DataFrame,
                                       linescores: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Per-game frame for the state-conditioner CROSS template: y =
    rest_of_game_margin (real, current game, via _rest_of_game_margin),
    asof__<attr> resolved PER ATTR from whichever source actually carries its
    diff column -- carryover_asof's SUFFIX name first, else asof_quarter_
    shape's PREFIX name (same "ask each source" pattern build_nba_assist_
    boxdetail_frame uses for its own two-source cross, just two DIFFERENT
    naming conventions here instead of one shared one). An attr in neither
    source is honestly dropped (no asof__ column for it), never invented --
    the caller (runner._fit_candidate) already treats a missing asof__ column
    as NOT_TESTABLE, so a bad/renamed attr name fails closed, not silently."""
    if linescores is None:
        linescores = pd.read_parquet(_NBA_LINESCORES_SOURCE)
    target = _rest_of_game_margin(linescores)
    bridge = qshape[["game_id", "event_id"]].drop_duplicates()
    carryover_bridged = carryover.merge(bridge, on="game_id", how="inner")

    out: Optional[pd.DataFrame] = None
    for a in sorted(set(attrs)):
        suf, pre = _nba_boxdetail_diff_col(a), _ingame_state_diff_col(a)
        if suf in carryover_bridged.columns:
            col = carryover_bridged[["event_id", suf]].rename(columns={suf: "asof__" + a})
        elif pre in qshape.columns:
            col = qshape[["event_id", pre]].rename(columns={pre: "asof__" + a})
        else:
            continue
        out = col if out is None else out.merge(col, on="event_id", how="outer")
    if out is None:
        return pd.DataFrame(columns=["event_id", "y"])
    out = out.merge(target, on="event_id", how="inner")
    out["y"] = out["rest_of_game_margin"]
    return out


def _nba_state_conditioner_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (_NBA_CARRYOVER_SOURCE.exists() and _NBA_QSHAPE_SOURCE.exists() and _NBA_LINESCORES_SOURCE.exists()):
        return None
    carryover = pd.read_parquet(_NBA_CARRYOVER_SOURCE)
    qshape = pd.read_parquet(_NBA_QSHAPE_SOURCE)
    frame = build_nba_state_conditioner_frame(attrs, carryover, qshape)
    return {"frame": frame, "cluster": "event_id", "corpus": _NBA_STATE_CONDITIONER_CORPUS, "kind": "ols"}


__all__ = ["build_nba_state_conditioner_frame", "_nba_state_conditioner_builder",
           "_NBA_STATE_CONDITIONER_CORPUS"]
