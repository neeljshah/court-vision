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


__all__ = ["build_nba_ingame_state_frame", "_nba_ingame_state_builder", "_ingame_state_diff_col"]
