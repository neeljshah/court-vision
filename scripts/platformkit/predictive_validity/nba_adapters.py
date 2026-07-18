"""NBA v1 menu of predictive-validity MetricTests, player grain.

Three walk-forward tests built entirely from load_boxscores()/load_atlas()
(domains.basketball_nba.quality_indices, read-only reuse -- see its module
docstring for the parquet schema). 6 monthly cutoffs spanning the 2023-24 and
2024-25 seasons; forward_games defaults to 20 (the player's next 20 games,
row-count window -- see _forward_n_games).

a. nba_gravity_proxy / gravity_score: season-level atlas spacing_gravity
   field predicting forward TS%; baseline = pre-cutoff trailing TS%. DECLARED
   CAVEAT (exactly the quality_validity_gate.py DIFFICULTY/GRAVITY-pillar
   caveat): the atlas is a season aggregate; gravity_score is used here as a
   stable style descriptor, not a leak of the TS% target -- it is not
   recomputed pre-T the way boxscore-derived metrics are.
b. nba_rest_adjusted_form / l10_ts_pct: pre-cutoff last-10-games TS%
   predicting forward TS%; baseline = pre-cutoff SEASON (to-date) TS% -- does
   recency beat the season mean?
c. shooter_composite_v2 / shooter_composite_v2_asof_approx: equal-weight
   percentile blend of pre-cutoff fg3a_per_game, fg3_pct, ft_pct (all
   recomputed pre-T from boxscores) + season-level atlas gravity_score,
   predicting forward FG3%; baseline = pre-cutoff trailing FG3%. DECLARED
   CAVEAT: this is an AS-OF APPROXIMATION of shooter_composite_v2 -- the
   pullup/unassisted-share ingredients of the full index are season-level
   atlas snapshots and are OMITTED here (no pre-T atlas variant exists), not
   silently substituted.

Leak-free by construction: every metric_asof/baseline_asof reads ONLY rows
with date < cutoff; every forward_outcome reads ONLY each player's next N
games with date >= cutoff.
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.quality_indices import load_atlas
from scripts.platformkit.predictive_validity.harness import MetricTest

CUTOFFS = ["2023-12-01", "2024-01-01", "2024-02-01",
           "2024-12-01", "2025-01-01", "2025-02-01",
           "2025-12-01", "2026-01-01", "2026-02-01"]
FORWARD_GAMES = 20
MIN_ENTITIES_PER_FOLD = 80

GRAVITY_CAVEAT = (
    "TEMPORAL LEAK CEILING, stated plainly: atlas spacing_gravity.gravity_score is a "
    "FULL-SEASON aggregate whose computation window OVERLAPS the forward-outcome window "
    "at every cutoff (no pre-T variant exists). Any forward skill it shows is therefore "
    "an UPPER BOUND, not a leak-free result -- and it still came out DESCRIPTIVE_ONLY, "
    "which is the conservative direction. Never promote this metric to "
    "PREDICTIVE_VERIFIED while the ingredient is season-level."
)
SHOOTER_COMPOSITE_CAVEAT = (
    "shooter_composite_v2_asof_approx: an AS-OF APPROXIMATION of shooter_composite_v2 "
    "blending ONLY strictly pre-cutoff boxscore ingredients (fg3a_per_game/fg3_pct/"
    "ft_pct percentiles). The full index's pullup-frequency/unassisted-share/gravity "
    "ingredients are season-level atlas snapshots whose windows overlap the forward "
    "outcome, so they are EXCLUDED here (gravity was removed 2026-07-18 after review "
    "flagged the overlap as a leak that could mint a false PREDICTIVE_VERIFIED)."
)


def _min_forward_games(forward_games: int) -> int:
    return max(1, round(0.6 * forward_games))


def _season_floor(cutoff: pd.Timestamp) -> pd.Timestamp:
    """Aug-1 boundary before `cutoff`: NBA games run roughly Oct-Jun, so Aug 1
    safely separates one season's games from the prior season's without
    needing the boxscore's own `season` label."""
    year = cutoff.year if cutoff.month >= 8 else cutoff.year - 1
    return pd.Timestamp(year=year, month=8, day=1)


def _pre_cutoff_agg(box: pd.DataFrame, cutoff: str, season_only: bool) -> pd.DataFrame:
    """Per-player sums over rows with date < cutoff (season_only also floors
    at that season's Aug-1 start), plus the rate columns the adapters need."""
    t0 = pd.Timestamp(cutoff)
    rows = box[box["date"] < t0]
    if season_only:
        rows = rows[rows["date"] >= _season_floor(t0)]
    g = rows.groupby("player_id", as_index=False).agg(
        games=("game_id", "nunique"),
        fgm=("fgm", "sum"), fga=("fga", "sum"),
        fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
        ftm=("ftm", "sum"), fta=("fta", "sum"),
        pts=("pts", "sum"),
    )
    g["ts_pct"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, pd.NA)
    g["fg3_pct"] = g["fg3m"] / g["fg3a"].replace(0, pd.NA)
    g["ft_pct"] = g["ftm"] / g["fta"].replace(0, pd.NA)
    g["fg3a_per_game"] = g["fg3a"] / g["games"].replace(0, pd.NA)
    return g


def _last_n_games_agg(box: pd.DataFrame, cutoff: str, n: int) -> pd.DataFrame:
    """Per-player TS% over each player's LAST n games with date < cutoff
    (trailing form, not the season-to-date mean)."""
    t0 = pd.Timestamp(cutoff)
    rows = box[box["date"] < t0].sort_values(["player_id", "date", "game_id"])
    last_n = rows.groupby("player_id", as_index=False).tail(n)
    g = last_n.groupby("player_id", as_index=False).agg(
        games=("game_id", "nunique"), fga=("fga", "sum"), fta=("fta", "sum"), pts=("pts", "sum"),
    )
    g["ts_pct"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, pd.NA)
    return g


def _forward_n_games(box: pd.DataFrame, cutoff: str, n: int) -> pd.DataFrame:
    """Per-player outcome over each player's NEXT n games with date >= cutoff
    (row-count window): realized TS%, realized FG3%, and n_forward (games
    actually available, may be < n near the end of a corpus)."""
    t0 = pd.Timestamp(cutoff)
    rows = box[box["date"] >= t0].sort_values(["player_id", "date", "game_id"])
    nxt = rows.groupby("player_id", as_index=False).head(n)
    g = nxt.groupby("player_id", as_index=False).agg(
        n_forward=("game_id", "nunique"),
        fga=("fga", "sum"), fta=("fta", "sum"), pts=("pts", "sum"),
        fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
    )
    g["realized_ts_pct"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, pd.NA)
    g["realized_fg3_pct"] = g["fg3m"] / g["fg3a"].replace(0, pd.NA)
    return g


def _percentile(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)


def _forward_ts_outcome(box: pd.DataFrame, cutoff: str, forward_games: int) -> pd.DataFrame:
    fwd = _forward_n_games(box, cutoff, forward_games).dropna(subset=["realized_ts_pct"])
    return fwd[["player_id", "realized_ts_pct", "n_forward"]].rename(
        columns={"player_id": "entity_id", "realized_ts_pct": "outcome"})


def _forward_fg3_outcome(box: pd.DataFrame, cutoff: str, forward_games: int) -> pd.DataFrame:
    fwd = _forward_n_games(box, cutoff, forward_games).dropna(subset=["realized_fg3_pct"])
    return fwd[["player_id", "realized_fg3_pct", "n_forward"]].rename(
        columns={"player_id": "entity_id", "realized_fg3_pct": "outcome"})


def _trailing_ts_baseline_asof(box: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    pre = _pre_cutoff_agg(box, cutoff, season_only=False).dropna(subset=["ts_pct"])
    return pre[["player_id", "ts_pct"]].rename(columns={"player_id": "entity_id", "ts_pct": "value"})


def _season_ts_baseline_asof(box: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    pre = _pre_cutoff_agg(box, cutoff, season_only=True).dropna(subset=["ts_pct"])
    return pre[["player_id", "ts_pct"]].rename(columns={"player_id": "entity_id", "ts_pct": "value"})


def _l10_ts_metric_asof(box: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    g = _last_n_games_agg(box, cutoff, 10).dropna(subset=["ts_pct"])
    return g[["player_id", "ts_pct"]].rename(columns={"player_id": "entity_id", "ts_pct": "value"})


def _gravity_metric_asof(box: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    pool = _pre_cutoff_agg(box, cutoff, season_only=False)[["player_id"]]
    sg = load_atlas("spacing_gravity")[["player_id", "gravity_score"]]
    out = pool.merge(sg, on="player_id", how="inner").dropna(subset=["gravity_score"])
    return out.rename(columns={"player_id": "entity_id", "gravity_score": "value"})


def _trailing_fg3_baseline_asof(box: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    pre = _pre_cutoff_agg(box, cutoff, season_only=False).dropna(subset=["fg3_pct"])
    return pre[["player_id", "fg3_pct"]].rename(columns={"player_id": "entity_id", "fg3_pct": "value"})


def _shooter_composite_v2_asof_metric(box: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    # Strictly pre-cutoff boxscore ingredients ONLY -- the atlas gravity
    # ingredient was removed (its season window overlaps the forward outcome;
    # see SHOOTER_COMPOSITE_CAVEAT).
    pre = _pre_cutoff_agg(box, cutoff, season_only=False)
    pct = pd.DataFrame({"player_id": pre["player_id"]})
    pct["fg3a_pctile"] = _percentile(pre["fg3a_per_game"])
    pct["fg3_pctile"] = _percentile(pre["fg3_pct"])
    pct["ft_pctile"] = _percentile(pre["ft_pct"])
    comp_cols = ["fg3a_pctile", "fg3_pctile", "ft_pctile"]
    pct["value"] = pct[comp_cols].mean(axis=1, skipna=True)
    out = pct.dropna(subset=["value"])
    return out[["player_id", "value"]].rename(columns={"player_id": "entity_id"})


def gravity_proxy_test(box: pd.DataFrame, forward_games: int = FORWARD_GAMES) -> MetricTest:
    return MetricTest(
        family="nba_gravity_proxy", sport="nba", metric_name="gravity_score",
        baseline_name="trailing_ts_pct", cutoffs=list(CUTOFFS), forward_games=forward_games,
        min_forward_games=_min_forward_games(forward_games), min_entities_per_fold=MIN_ENTITIES_PER_FOLD,
        metric_asof=lambda c: _gravity_metric_asof(box, c),
        baseline_asof=lambda c: _trailing_ts_baseline_asof(box, c),
        forward_outcome=lambda c: _forward_ts_outcome(box, c, forward_games),
        caveat=GRAVITY_CAVEAT,
    )


def rest_adjusted_form_test(box: pd.DataFrame, forward_games: int = FORWARD_GAMES) -> MetricTest:
    return MetricTest(
        family="nba_rest_adjusted_form", sport="nba", metric_name="l10_ts_pct",
        baseline_name="season_ts_pct", cutoffs=list(CUTOFFS), forward_games=forward_games,
        min_forward_games=_min_forward_games(forward_games), min_entities_per_fold=MIN_ENTITIES_PER_FOLD,
        metric_asof=lambda c: _l10_ts_metric_asof(box, c),
        baseline_asof=lambda c: _season_ts_baseline_asof(box, c),
        forward_outcome=lambda c: _forward_ts_outcome(box, c, forward_games),
    )


def shooter_composite_v2_test(box: pd.DataFrame, forward_games: int = FORWARD_GAMES) -> MetricTest:
    return MetricTest(
        family="shooter_composite_v2", sport="nba", metric_name="shooter_composite_v2_asof_approx",
        baseline_name="trailing_fg3_pct", cutoffs=list(CUTOFFS), forward_games=forward_games,
        min_forward_games=_min_forward_games(forward_games), min_entities_per_fold=MIN_ENTITIES_PER_FOLD,
        metric_asof=lambda c: _shooter_composite_v2_asof_metric(box, c),
        baseline_asof=lambda c: _trailing_fg3_baseline_asof(box, c),
        forward_outcome=lambda c: _forward_fg3_outcome(box, c, forward_games),
        caveat=SHOOTER_COMPOSITE_CAVEAT,
    )
