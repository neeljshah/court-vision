"""scripts.platformkit.interaction_factory.builders_ingame_state -- the M10
in-match nba_ingame_state_asof builder (nba_ingame_state_self_cross template),
split out to keep runner.py under its LOC budget (same convention as
builders_carryover.py / builders_task39b.py). Same contract as any other
runner builder: `builder(attrs, tpl) -> {"frame", "cluster", "corpus", "kind",
...} | None` -- registered into runner._BUILDERS by runner.py itself.

FEATURES: domains.basketball_nba.asof_quarter_shape's diff_*_asof columns
(the ingame_state_asof family -- already leak-free, strictly-prior
season-to-date trailing means; see attribute_registry.py's
_INGAME_STATE_SPECS). These are PREGAME trailing priors, not a mid-game
live read.

OUTCOME: rest_of_game_margin, computed directly from linescores.parquet's own
realized Q2+Q3+Q4 quarter points (home minus away) for THIS game -- a real,
current-game label, same "prior-only feature x real current outcome" shape as
box_detail_asof's home_win (labels are never as-of, only features are).

No Elo covariate -- none exists for this atomic_unit; the interaction alone
is the test, same as the tennis/soccer match templates. Cluster key is
event_id (one row per game, same one-row-per-unit shape box_detail_asof
clusters on its own game_id).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
_NBA_QSHAPE_SOURCE = REPO / "data" / "domains" / "basketball_nba" / "asof_quarter_shape.parquet"
_NBA_LINESCORES_SOURCE = REPO / "data" / "domains" / "basketball_nba" / "linescores.parquet"
_NBA_INGAME_STATE_CORPUS = "ingame_state_asof"


def _ingame_state_diff_col(attr: str) -> str:
    """Registry attr name ('q1_margin_asof') -> asof_quarter_shape.parquet's
    diff column ('diff_q1_margin_asof') -- PREFIX convention (matches that
    builder's own diff_{metric}_asof naming, see asof_quarter_shape.py). NOT
    the box_detail/carryover families' SUFFIX convention (<metric>_diff_asof)
    -- the two families' source files disagree on naming, do not conflate."""
    base = attr[: -len("_asof")] if attr.endswith("_asof") else attr
    return "diff_" + base + "_asof"


def _rest_of_game_margin(linescores: pd.DataFrame) -> pd.DataFrame:
    """Real (not as-of) per-game outcome: home-minus-away margin over
    Q2+Q3+Q4 only (the portion of the game AFTER the Q1 state the asof priors
    condition on) -- computed straight from linescores' own raw per-quarter
    columns. Only FEATURES need to be leak-free/as-of; this is the label."""
    def _num(s: pd.Series) -> pd.Series:
        return pd.to_numeric(s, errors="coerce")
    home = sum(_num(linescores[f"home_{q}"]) for q in ("q2", "q3", "q4"))
    away = sum(_num(linescores[f"away_{q}"]) for q in ("q2", "q3", "q4"))
    return pd.DataFrame({"event_id": linescores["event_id"].to_numpy(),
                          "rest_of_game_margin": (home - away).to_numpy()})


def build_nba_ingame_state_frame(attrs: List[str], asof: pd.DataFrame,
                                  linescores: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Per-game frame for the in-game-state self-cross template: y =
    rest_of_game_margin (real, current game), asof__<attr> = asof_quarter_
    shape.parquet's own diff_*_asof column (strictly-prior, leak-free).
    Inner-merges on event_id, invents nothing."""
    if linescores is None:
        linescores = pd.read_parquet(_NBA_LINESCORES_SOURCE)
    target = _rest_of_game_margin(linescores)
    diff_cols = sorted({_ingame_state_diff_col(a) for a in attrs})
    keep = ["event_id"] + [c for c in diff_cols if c in asof.columns]
    out = asof[keep].merge(target, on="event_id", how="inner")
    out = out.rename(columns={_ingame_state_diff_col(a): "asof__" + a for a in attrs
                               if _ingame_state_diff_col(a) in out.columns})
    out["y"] = out["rest_of_game_margin"]
    return out


def _nba_ingame_state_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (_NBA_QSHAPE_SOURCE.exists() and _NBA_LINESCORES_SOURCE.exists()):
        return None
    asof = pd.read_parquet(_NBA_QSHAPE_SOURCE)
    frame = build_nba_ingame_state_frame(attrs, asof)
    return {"frame": frame, "cluster": "event_id", "corpus": _NBA_INGAME_STATE_CORPUS, "kind": "ols"}


# --------------------------------------------------------------------------
# NBA ASSIST-RATE x BOX-DETAIL cross builder (unlock lane follow-on -- closes
# the last-inch gap b418cde6/f94a0373 left open for nba_assist_x_boxdetail_
# cross's feature_builder="nba_assist_boxdetail_asof"). Placed here (not
# builders_task39b.py, where nba_boxdetail_asof itself lives) purely for LOC
# budget -- that file is already at 279/300 lines. Merges TWO already-on-disk
# leak-free diff_*_asof sources: asof_features.parquet's ast_rate_diff_asof
# (assist_asof family) + boxdetail_asof.parquet's 5 box-detail diff cols
# (box_detail_asof family) -- both use the identical <metric>_diff_asof SUFFIX
# naming (builders_task39b._nba_boxdetail_diff_col's string transform works
# unchanged for ast_rate_asof -> ast_rate_diff_asof), so it is reused rather
# than reimplemented.
from scripts.platformkit.interaction_factory.builders_task39b import (  # noqa: E402
    _nba_boxdetail_diff_col as _assist_bd_diff_col,
    _NBA_BOXDETAIL_SOURCE as _NBA_BOXDETAIL_SOURCE_2,
)

_NBA_ASSIST_SOURCE = REPO / "data" / "domains" / "basketball_nba" / "asof_features.parquet"
_NBA_ASSIST_BOXDETAIL_CORPUS = "assist_boxdetail_asof"


def build_nba_assist_boxdetail_frame(attrs: List[str], assist: pd.DataFrame, boxdetail: pd.DataFrame,
                                      games: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Per-game frame for the assist x box-detail CROSS template: y=home_win,
    asof__<attr> pulled from whichever source parquet actually carries that
    attr's own diff column. Seeds Elo p_base + coverage (asof_ast_rate_eval.
    build_candidate_frame, reused) off whichever source carries the sorted-
    first diff col -- same pattern build_nba_boxdetail_frame uses for its own
    single-source case. Merges, invents nothing."""
    from domains.basketball_nba import asof_ast_rate_eval as _eval
    diff_cols = sorted({_assist_bd_diff_col(a) for a in attrs})
    src = {"assist": assist, "boxdetail": boxdetail}
    owner = {dc: ("assist" if dc in assist.columns else "boxdetail") for dc in diff_cols}
    out = _eval.build_candidate_frame(games=games, asof=src[owner[diff_cols[0]]], feat_col=diff_cols[0])
    out = out[["game_id", "home_win", "p_base", diff_cols[0]]].copy()
    for dc in diff_cols[1:]:
        extra = src[owner[dc]][["game_id", dc]].copy()
        extra["game_id"] = extra["game_id"].astype(str)
        out = out.merge(extra, on="game_id", how="left")
    out = out.rename(columns={_assist_bd_diff_col(a): "asof__" + a for a in attrs})
    out["y"] = out["home_win"]
    return out


def _nba_assist_boxdetail_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (_NBA_ASSIST_SOURCE.exists() and _NBA_BOXDETAIL_SOURCE_2.exists()):
        return None
    assist = pd.read_parquet(_NBA_ASSIST_SOURCE)
    boxdetail = pd.read_parquet(_NBA_BOXDETAIL_SOURCE_2)
    frame = build_nba_assist_boxdetail_frame(attrs, assist, boxdetail)
    return {"frame": frame, "cluster": "game_id", "corpus": _NBA_ASSIST_BOXDETAIL_CORPUS,
            "kind": "logit", "covariate": "p_base"}


__all__ = ["build_nba_ingame_state_frame", "_nba_ingame_state_builder", "_ingame_state_diff_col",
           "build_nba_assist_boxdetail_frame", "_nba_assist_boxdetail_builder"]
