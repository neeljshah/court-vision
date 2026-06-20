"""scripts.platformkit.ingame.possession_layer_gate_nba -- run the EXISTING
detail_layer_gate on the NBA POSSESSION / PACE / SCORING-RUN detail layer, REPLICATED
cross-corpus (season A <-> season B) in BOTH directions.

This file adds NO scoring math. It only:
  * loads the two possession_states_<season>.parquet corpora produced by
    domains.basketball_nba.ingest_possession_states (each carries the FROZEN base
    schema game_id/asof_idx/state_diff/frac_elapsed/outcome PLUS the additive as-of
    detail cols possessions_elapsed / pace_so_far / run_diff / poss_since_lead_change);
  * for each requested detail column, hands (base, detail) for BOTH corpora to
    detail_layer_gate.gate_detail_layer -- which merges detail onto base on
    (game_id, asof_idx) and runs the inherited cross-corpus gate (BASE fit on TRAIN
    only, DM clustered by game_id, degenerate-base + graceful-degrade negative control).

Because the ingest writes base + detail in ONE parquet, the SAME dataframe is passed as
both the base and the detail source: the gate's inner-merge re-keys on (game_id,
asof_idx) and selects only the named detail column for the p0 slot. The base itself is
always (state_diff, frac_elapsed) -- the proven (margin, time) model.

HONEST: a column SHIPS only if it beats the (margin,time) BASE on held-out Brier in
BOTH directions with DM p<eps; otherwise it is an honest REJECT (kept as scouting). No
in-play odds -> CALIBRATION only, never a market edge. No $ anywhere.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
CLI: python -m scripts.platformkit.ingame.possession_layer_gate_nba \
        --a 2024_25 --b 2025_26
"""
from __future__ import annotations

import argparse
import os
from typing import Dict, List, Optional

import pandas as pd

from scripts.platformkit.ingame.detail_layer_gate import gate_detail_layer

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DIR = os.path.join(_REPO, "data", "cache", "ingame")

DETAIL_COLS = (
    "possessions_elapsed",
    "pace_so_far",
    "run_diff",
    "poss_since_lead_change",
)


def _path(season: str) -> str:
    return os.path.join(_DIR, f"possession_states_{season}.parquet")


def load_corpus(season: str) -> pd.DataFrame:
    """Load one season's possession-states parquet (raises if absent -- fail honest)."""
    p = _path(season)
    if not os.path.exists(p):
        raise FileNotFoundError(
            f"missing {p} -- run "
            f"`python -m domains.basketball_nba.ingest_possession_states "
            f"--season {season}` first")
    return pd.read_parquet(p)


_BASE_KEEP = ["game_id", "asof_idx", "state_diff", "frac_elapsed", "outcome"]


def _base_view(df: pd.DataFrame) -> pd.DataFrame:
    """The pure (margin,time) BASE frame -- only the frozen base columns, so the gate's
    inner-merge with the detail frame never collides on a detail column name."""
    return df[_BASE_KEEP].copy()


def _detail_view(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Just the join keys + the one detail column (the gate selects `col` from here)."""
    return df[["game_id", "asof_idx", col]].copy()


def gate_column(df_a: pd.DataFrame, df_b: pd.DataFrame, col: str,
                *, min_ticks: int = 200, eps: float = 0.05):
    """Gate ONE detail column cross-corpus A<->B via the inherited detail_layer_gate.

    BASE frame = frozen (state_diff, frac_elapsed) view; DETAIL frame = keys + `col`.
    Splitting the views avoids a merge-suffix collision on the detail column name.
    """
    return gate_detail_layer(_base_view(df_a), _detail_view(df_a, col),
                             _base_view(df_b), _detail_view(df_b, col),
                             col=col, sport="nba_possession",
                             min_ticks=min_ticks, eps=eps)


def run(season_a: str = "2024_25", season_b: str = "2025_26",
        cols: Optional[List[str]] = None, *, min_ticks: int = 200,
        eps: float = 0.05) -> Dict[str, object]:
    """Run every detail column cross-corpus and return an honest per-column report dict."""
    cols = list(cols or DETAIL_COLS)
    df_a, df_b = load_corpus(season_a), load_corpus(season_b)
    results: Dict[str, object] = {
        "season_a": season_a, "season_b": season_b,
        "a_games": int(df_a["game_id"].nunique()), "a_states": int(len(df_a)),
        "b_games": int(df_b["game_id"].nunique()), "b_states": int(len(df_b)),
        "vs_close": "UNPROVEN -- no in-play odds; CALIBRATION (held-out Brier) only",
        "columns": {},
    }
    for col in cols:
        v = gate_column(df_a, df_b, col, min_ticks=min_ticks, eps=eps)
        results["columns"][col] = {
            "verdict": v.verdict,
            "a_to_b": v.a_to_b,
            "b_to_a": v.b_to_a,
        }
    return results


def _fmt_dir(d: dict) -> str:
    if not d:
        return "(none)"
    return (f"BASE {d.get('brier_base')} -> +detail {d.get('brier_prior')} "
            f"(delta {d.get('brier_delta')}) DM p {d.get('dm_p')} "
            f"beats={d.get('prior_beats_base')} degenerate={d.get('base_degenerate')}")


def _report(res: Dict[str, object]) -> str:
    lines = ["=" * 72,
             "NBA POSSESSION/PACE/RUN DETAIL-LAYER GATE (cross-corpus A<->B)",
             "=" * 72,
             f"A={res['season_a']} ({res['a_games']} games / {res['a_states']} states)  "
             f"B={res['season_b']} ({res['b_games']} games / {res['b_states']} states)",
             f"vs_close: {res['vs_close']}", "-" * 72]
    for col, c in res["columns"].items():  # type: ignore[index]
        lines.append(f"[{col}]  VERDICT={c['verdict']}")
        lines.append(f"   A->B: {_fmt_dir(c['a_to_b'])}")
        lines.append(f"   B->A: {_fmt_dir(c['b_to_a'])}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Gate NBA possession/pace/run detail layer.")
    ap.add_argument("--a", default="2024_25")
    ap.add_argument("--b", default="2025_26")
    ap.add_argument("--col", default=None, help="single column (default: all)")
    ap.add_argument("--min-ticks", type=int, default=200)
    ap.add_argument("--eps", type=float, default=0.05)
    a = ap.parse_args(argv)
    cols = [a.col] if a.col else None
    res = run(a.a, a.b, cols=cols, min_ticks=a.min_ticks, eps=a.eps)
    print(_report(res))


if __name__ == "__main__":
    main()
