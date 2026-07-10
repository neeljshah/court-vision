"""scripts.platformkit.interaction_factory.builders_carryover -- the 2
cross-game CARRYOVER builders (nba_carryover_asof, mlb_carryover_asof) C4
lane registers, split out of runner.py to keep that module under its LOC
budget (same convention as builders_task39b.py). Same contract as any other
runner builder: `builder(attrs, tpl) -> {"frame", "cluster", "corpus", "kind",
...} | None` -- registered into runner._BUILDERS by runner.py itself.

NBA: reuses builders_task39b.build_nba_boxdetail_frame VERBATIM -- that
function is already generic (any `<attr>_diff_asof`-shaped as-of DataFrame +
Elo covariate merge via asof_ast_rate_eval.build_candidate_frame), not
box-detail-specific, so no reimplementation is needed for the carryover_asof
family.

MLB: no existing MLB team_game x Elo self-cross builder to reuse (the two
on-disk MLB Elo gates -- asof_ra_diff_eval / pregame_gate -- key on games.parquet,
2010-2021, which has ZERO date overlap with the Statcast-derived
carryover_asof__<year>.parquet, 2022+). This builder instead merges
carryover_asof directly onto games_current.parquet's own Elo (domains.mlb.
ratings.walk_forward_elo) + target_home_win, keyed on the real event_id the
domain builder already bridged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.interaction_factory.builders_task39b import build_nba_boxdetail_frame

REPO = Path(__file__).resolve().parents[3]

# --------------------------------------------------------------------------
# NBA cross-game carryover (C4 lane). Source: domains.basketball_nba.
# carryover_asof.build_carryover_asof -- LAG-1 heavy_min_load + rest_days,
# reset per team-season (see that module's docstring).
_NBA_CARRYOVER_SOURCE = REPO / "data" / "domains" / "basketball_nba" / "carryover_asof.parquet"
_NBA_CARRYOVER_CORPUS = "carryover_asof"


def _nba_carryover_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _NBA_CARRYOVER_SOURCE.exists():
        return None
    asof = pd.read_parquet(_NBA_CARRYOVER_SOURCE)
    frame = build_nba_boxdetail_frame(attrs, asof)   # generic diff-asof + Elo merge, reused verbatim
    return {"frame": frame, "cluster": "game_id", "corpus": _NBA_CARRYOVER_CORPUS,
            "kind": "logit", "covariate": "p_base"}


# --------------------------------------------------------------------------
# MLB cross-game carryover (C4 lane). Source: domains.mlb.carryover_asof.
# build_carryover_asof(year) -- LAG-1 SP prior-start pitch count + rest days,
# already bridged to a real games_current.parquet event_id (outcome-free).
_MLB_CARRYOVER_YEAR_DEFAULT = "2024"
_MLB_GAMES_CURRENT = REPO / "data" / "domains" / "mlb" / "games_current.parquet"


def mlb_carryover_source_for_year(year: str) -> Path:
    return REPO / "data" / "domains" / "mlb" / f"carryover_asof__{year}.parquet"


def _mlb_diff_col(attr: str) -> str:
    """Registry attr name ('sp_prior_pitch_count_asof') -> carryover_asof's
    diff column ('sp_prior_pitch_count_diff_asof') -- same _asof-suffix-strip
    the NBA box-detail builder's own helper uses."""
    base = attr[: -len("_asof")] if attr.endswith("_asof") else attr
    return base + "_diff_asof"


def build_mlb_carryover_frame(attrs: List[str], asof: pd.DataFrame,
                              games_current: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Per-game frame for the MLB carryover self-cross template: y=target_home_win,
    asof__<attr> = carryover_asof__<year>.parquet's own diff column (already
    leak-free, event_id-keyed), p_base = walk-forward Elo over games_current."""
    from domains.mlb.ratings import walk_forward_elo

    gc = games_current.copy() if isinstance(games_current, pd.DataFrame) else pd.read_parquet(_MLB_GAMES_CURRENT)
    gc = gc[gc["target_home_win"].notna()].reset_index(drop=True)
    elo = walk_forward_elo(gc)[["event_id", "p_home_elo"]].rename(columns={"p_home_elo": "p_base"})

    diff_cols = sorted({_mlb_diff_col(a) for a in attrs})
    keep = ["event_id"] + [c for c in diff_cols if c in asof.columns]
    out = asof[keep].merge(gc[["event_id", "target_home_win"]], on="event_id", how="inner")
    out = out.merge(elo, on="event_id", how="left")
    out = out.rename(columns={_mlb_diff_col(a): "asof__" + a for a in attrs if _mlb_diff_col(a) in out.columns})
    out["y"] = out["target_home_win"].astype(float)
    return out


def _mlb_carryover_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source = mlb_carryover_source_for_year(_MLB_CARRYOVER_YEAR_DEFAULT)
    if not source.exists():
        return None
    asof = pd.read_parquet(source)
    frame = build_mlb_carryover_frame(attrs, asof)
    return {"frame": frame, "cluster": "event_id", "corpus": "carryover_asof_%s" % _MLB_CARRYOVER_YEAR_DEFAULT,
            "kind": "logit", "covariate": "p_base"}


__all__ = [
    "_nba_carryover_builder", "_mlb_carryover_builder",
    "mlb_carryover_source_for_year", "build_mlb_carryover_frame",
]
