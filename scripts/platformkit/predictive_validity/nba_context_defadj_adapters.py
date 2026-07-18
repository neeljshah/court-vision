"""NBA predictive-validity MetricTest for context-shooting axis 1: does
defense-adjusted TS% (nba_context_shooting_defadj family) predict FORWARD
shooting better than naive trailing TS%?

Reuses the SAME cutoffs/forward-window/floors and the SAME baseline/outcome
adapters as nba_adapters.py (imported directly -- those functions only read
named columns, so passing them the wider team/opp-carrying frame this family
needs is harmless). The candidate metric itself is computed here via
scripts.platformkit.intel_validation.nba_context_defadj_asof's leak-free
opponent-strength machinery, restricted at each cutoff to rows with
date < cutoff (so both the player's own history AND the opponent-strength
reads it depends on are strictly pre-cutoff -- doubly leak-free).

CAVEAT (declared before any fold is run): opponent defensive-strength history
is NOT reset at season boundaries (see nba_context_defadj_asof module
docstring) -- this affects only the opponent-side reading, never the target
player's own forward outcome, but is stated plainly per the no-edge-claims
discipline of never hiding an approximation.

CLI: scripts.platformkit.predictive_validity.run_nba_context_defadj
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation.nba_context_defadj_asof import build_player_game_rows
from scripts.platformkit.predictive_validity.harness import MetricTest
from scripts.platformkit.predictive_validity.nba_adapters import (
    CUTOFFS,
    MIN_ENTITIES_PER_FOLD,
    _forward_ts_outcome,
    _min_forward_games,
    _trailing_ts_baseline_asof,
)

FORWARD_GAMES = 20

DEFADJ_CAVEAT = (
    "def_adj_ts_pct_asof: opponent defensive-strength history is NOT reset at season "
    "boundaries (a team's D identity carries over from the prior season's tail); this "
    "affects only the opponent-side reading, never the target player's own forward "
    "outcome, but is stated here rather than silently assumed."
)


def _defadj_ts_metric_asof(box: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    """Strictly pre-cutoff defense-adjusted TS%: filter to date<cutoff BEFORE
    computing opponent strength (so the opponent-strength read itself cannot
    see cutoff-or-later games either), then possession-weight the expected
    TS% against each player's own pre-cutoff opponents faced."""
    t0 = pd.Timestamp(cutoff)
    pre = box[box["date"] < t0]
    rows = build_player_game_rows(pre)
    valid = rows.dropna(subset=["opp_def_strength_asof"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=["entity_id", "value"])
    valid["poss"] = valid["fga"] + 0.44 * valid["fta"]
    valid["w_num"] = valid["opp_def_strength_asof"] * valid["poss"]
    exp = valid.groupby("player_id", as_index=False).agg(w_num=("w_num", "sum"), w_den=("poss", "sum"))
    exp["expected_ts_pct"] = exp["w_num"] / exp["w_den"].replace(0, pd.NA)

    actual = valid.groupby("player_id", as_index=False).agg(
        fga=("fga", "sum"), fta=("fta", "sum"), pts=("pts", "sum"),
    )
    actual["ts_pct"] = actual["pts"] / (2 * (actual["fga"] + 0.44 * actual["fta"])).replace(0, pd.NA)
    merged = actual.merge(exp[["player_id", "expected_ts_pct"]], on="player_id", how="inner")
    merged["value"] = merged["ts_pct"] - merged["expected_ts_pct"]
    out = merged.dropna(subset=["value"])
    return out[["player_id", "value"]].rename(columns={"player_id": "entity_id"})


def defadj_ts_test(box: pd.DataFrame, forward_games: int = FORWARD_GAMES) -> MetricTest:
    return MetricTest(
        family="nba_context_shooting_defadj", sport="nba", metric_name="def_adj_ts_pct_asof",
        baseline_name="trailing_ts_pct", cutoffs=list(CUTOFFS), forward_games=forward_games,
        min_forward_games=_min_forward_games(forward_games), min_entities_per_fold=MIN_ENTITIES_PER_FOLD,
        metric_asof=lambda c: _defadj_ts_metric_asof(box, c),
        baseline_asof=lambda c: _trailing_ts_baseline_asof(box, c),
        forward_outcome=lambda c: _forward_ts_outcome(box, c, forward_games),
        caveat=DEFADJ_CAVEAT,
    )
