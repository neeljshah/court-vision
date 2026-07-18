"""NBA predictive-validity MetricTest for nba_rest_context: does a player's
AS-OF b2b TS%-drop (pre-cutoff) predict his FORWARD b2b TS%-drop (post-
cutoff) better than assuming ZERO drop (the "no persistent b2b effect"
null)?

DECLARED ADAPTATION (prereg, before any fold was scored): a literal constant
"zero" baseline has NO rank variance, so Spearman rank-correlation against it
is mathematically undefined (NaN) -- feeding it through harness.run_metric_
test's two-arm paired_bootstrap_delta would crash (bootstrap_delta needs the
BASELINE arm's rho to be finite at least once per pooled sample; a fully
degenerate constant makes every resample rho_baseline NaN, so
np.percentile() on an EMPTY delta array raises IndexError -- verified this
session). The "beats zero" question is therefore recast as: is the metric's
OWN rank-skill (its Spearman rho vs the forward outcome) reliably ABOVE zero?
That is exactly harness._bootstrap_single_rho's single-arm CI -- rho=0 IS
the constant/no-information null. Reuses harness.MetricTest, harness.
_build_fold (per-cutoff fold assembly -- baseline_asof is still declared for
shape/documentation parity; its NaN rho is harmless here, never bootstrapped),
harness._bootstrap_single_rho, and harness._verdict UNCHANGED -- only the
top-level aggregation (run_nba_rest_context.py) skips the two-arm bootstrap
call that would crash.

Pre-cutoff/forward drop is the SAME b2b_ts_drop quantity as
nba_rest_context_claims.py (TS% on b2b minus TS% on 2+ days rest, season-
scoped bucketing via that module's _rest_bucket_rows -- bucket assignment for
any row depends only on that row's own date and its immediately-PRIOR date,
both <= the row's own date, so computing buckets once per season and then
splitting rows by cutoff afterward is leak-free in both directions: a
pre-cutoff row's bucket never depends on a post-cutoff row, and a forward
row's bucket may look at a pre-cutoff prior date, which is already-known
information, not a leak of the outcome itself).

PV FLOORS (declared before any fold was scored, deliberately SMALLER than
nba_rest_context_claims.py's full-season floors -- a fold's pre-cutoff window
is PARTIAL-season): metric_asof requires >=3 b2b AND >=5 rest2plus games in
the player's pre-cutoff history; forward_outcome requires >=2 b2b AND >=3
rest2plus games in the next `forward_games` rows. Thin folds/players are
DROPPED per the harness's existing floors (min_entities_per_fold,
min_forward_games) -- an UNDERPOWERED verdict is expected and honest when
few players clear both the pre-cutoff AND forward floors in the same fold.

CLI: scripts.platformkit.predictive_validity.run_nba_rest_context
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.intel_validation.nba_rest_context_claims import _rest_bucket_rows
from scripts.platformkit.predictive_validity.harness import MetricTest
from scripts.platformkit.predictive_validity.nba_adapters import CUTOFFS, MIN_ENTITIES_PER_FOLD

FORWARD_GAMES = 20
PV_PRE_FLOOR_B2B = 3
PV_PRE_FLOOR_REST = 5
PV_FWD_FLOOR_B2B = 2
PV_FWD_FLOOR_REST = 3
MIN_FORWARD_GAMES = PV_FWD_FLOOR_B2B + PV_FWD_FLOOR_REST

ZERO_BASELINE_CAVEAT = (
    "baseline_name=zero_drop is a DECLARED constant (assume no persistent b2b "
    "effect), which has zero rank variance -- Spearman correlation against it "
    "is undefined by construction. 'Beats zero' is tested instead as whether "
    "the metric's OWN rank-skill bootstrap CI excludes zero (see module "
    "docstring); rho_metric_bootstrap IS the delta-vs-zero CI here. "
    "schedule assignment is not random (opponent strength/venue correlate "
    "with schedule density); not a causal claim."
)


def _season_label(cutoff: str) -> str:
    ts = pd.Timestamp(cutoff)
    year = ts.year if ts.month >= 8 else ts.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def _bucketed_rows_by_season(box: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """One bucketed frame per season label touched by CUTOFFS (memoized --
    bucket assignment is season-scoped and computed ONCE per season, then
    split by cutoff date in the metric/outcome adapters below)."""
    # every season touched by CUTOFFS is bucketed unconditionally (even if
    # absent from `box`) -- _rest_bucket_rows on an empty season-subset still
    # returns a frame WITH the "bucket" column, so downstream code never has
    # to special-case a missing season with a raw, unbucketed empty frame.
    seasons = sorted({_season_label(c) for c in CUTOFFS})
    return {s: _rest_bucket_rows(box, s) for s in seasons}


def _ts_by_bucket(rows: pd.DataFrame, bucket: str) -> pd.DataFrame:
    sub = rows[rows["bucket"] == bucket]
    g = sub.groupby("player_id", as_index=False).agg(
        n=("game_id", "nunique"), pts=("pts", "sum"), fga=("fga", "sum"), fta=("fta", "sum"),
    )
    g["ts"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, np.nan)
    return g[["player_id", "n", "ts"]]


def _drop_asof(rows: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    pre = rows[rows["date"] < pd.Timestamp(cutoff)]
    b2b = _ts_by_bucket(pre, "b2b").rename(columns={"n": "n_b2b", "ts": "ts_b2b"})
    rest = _ts_by_bucket(pre, "rest2plus").rename(columns={"n": "n_rest", "ts": "ts_rest"})
    m = b2b.merge(rest, on="player_id", how="inner")
    m = m[(m["n_b2b"] >= PV_PRE_FLOOR_B2B) & (m["n_rest"] >= PV_PRE_FLOOR_REST)]
    m["value"] = m["ts_b2b"] - m["ts_rest"]
    out = m.dropna(subset=["value"])
    return out[["player_id", "value"]].rename(columns={"player_id": "entity_id"})


def _drop_forward(rows: pd.DataFrame, cutoff: str, forward_games: int) -> pd.DataFrame:
    t0 = pd.Timestamp(cutoff)
    post = rows[rows["date"] >= t0].sort_values(["player_id", "date", "game_id"])
    window = post.groupby("player_id", as_index=False, group_keys=False).head(forward_games)
    b2b = _ts_by_bucket(window, "b2b").rename(columns={"n": "n_b2b", "ts": "ts_b2b"})
    rest = _ts_by_bucket(window, "rest2plus").rename(columns={"n": "n_rest", "ts": "ts_rest"})
    m = b2b.merge(rest, on="player_id", how="inner")
    m = m[(m["n_b2b"] >= PV_FWD_FLOOR_B2B) & (m["n_rest"] >= PV_FWD_FLOOR_REST)]
    m["outcome"] = m["ts_b2b"] - m["ts_rest"]
    m["n_forward"] = m["n_b2b"] + m["n_rest"]
    out = m.dropna(subset=["outcome"])
    return out[["player_id", "outcome", "n_forward"]].rename(columns={"player_id": "entity_id"})


def _zero_baseline_asof(rows: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    """Constant 0.0 for every player who clears the SAME pre-cutoff floors as
    the metric arm (same entity set as _drop_asof, value replaced by the
    declared null) -- see module docstring for why this can never be
    bootstrapped as a two-arm rank-correlation delta."""
    metric = _drop_asof(rows, cutoff)
    out = metric[["entity_id"]].copy()
    out["value"] = 0.0
    return out


def rest_context_b2b_drop_test(box: pd.DataFrame, forward_games: int = FORWARD_GAMES) -> MetricTest:
    by_season = _bucketed_rows_by_season(box)

    def _rows_for(cutoff: str) -> pd.DataFrame:
        return by_season.get(_season_label(cutoff), box.iloc[0:0])

    return MetricTest(
        family="nba_rest_context", sport="nba", metric_name="b2b_ts_drop_asof",
        baseline_name="zero_drop", cutoffs=list(CUTOFFS), forward_games=forward_games,
        min_forward_games=MIN_FORWARD_GAMES, min_entities_per_fold=MIN_ENTITIES_PER_FOLD,
        metric_asof=lambda c: _drop_asof(_rows_for(c), c),
        baseline_asof=lambda c: _zero_baseline_asof(_rows_for(c), c),
        forward_outcome=lambda c: _drop_forward(_rows_for(c), c, forward_games),
        caveat=ZERO_BASELINE_CAVEAT,
    )
