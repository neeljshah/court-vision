"""scripts.platformkit.live_edge.replay.harden -- B4-HARDEN: upgraded scorer.

Replaces validate_claims' bootstrap-CI-on-one-slice with (1) a Diebold-Mariano
test on the squared-error loss differential, CLUSTERED BY GAME_ID, and (2) a
>=2-corpora agreement gate. Backward-compatible: same score design (squared
error vs a fixed baseline predictor), same MIN_ACTIVE floor, same cell/entity
matching -- imports tick_replay.active_mask_for_cell and player_grid's frame
builder rather than re-deriving them (DONT-REBUILD).

RESERVE RECONCILE (closes the open B1 season-vs-trailing gate): no 2026-27
season exists yet (today is 2026-07-14, mid-summer, 2025-26 just finished),
so a truly independent second SEASON is not available. This module keeps
the season-grain reserve split exactly as B1/B4/player_grid already use it
(situation_grid.RESERVE_SEASON, never re-derived) and additionally
partitions that one reserve into two DISJOINT TRAILING-DATE HALVES (a
median-date cutoff over unique game dates, not row count) as the >=2-corpora
agreement test the program asks for. This is a real TRAILING-DATE reserve,
consistent with the rails ("not season-label") -- the two halves are the
two corpora a claim must win on independently.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
from scipy import stats

from scripts.platformkit.live_edge.situation_grid import load_box_rate

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MIN_ACTIVE = 30  # same floor validate_claims used
MIN_GAMES = 10   # DM test needs enough clusters to trust the t-distribution
ALPHA = 0.05


def attach_dates(df: pd.DataFrame, box_source=None) -> pd.DataFrame:
    """Adds a 'game_date' column via a game_id -> box_rate date lookup.
    Additive-only join (new column); never mutates situation_grid's frame."""
    box = load_box_rate(box_source)
    dates = box.drop_duplicates("game_id")[["game_id", "date"]].rename(columns={"date": "game_date"})
    return df.merge(dates, on="game_id", how="left")


def split_trailing_corpora(df: pd.DataFrame, date_col: str = "game_date") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Disjoint trailing-date halves of one reserve slice: corpus_a = the
    earlier half by date, corpus_b = the later half. Cutoff is the median of
    UNIQUE game dates (a real date split), not a row-count split (which
    would be possession-volume-biased toward high-pace/OT games)."""
    dates = np.sort(df[date_col].dropna().unique())
    if len(dates) < 2:
        return df.iloc[0:0].copy(), df.iloc[0:0].copy()
    cutoff = dates[len(dates) // 2]
    return df[df[date_col] < cutoff].copy(), df[df[date_col] >= cutoff].copy()


def dm_test_clustered(actual: np.ndarray, baseline_pred, conditioned_pred, game_ids: np.ndarray) -> dict:
    """Diebold-Mariano test on the loss differential (squared-error proxy),
    CLUSTERED BY GAME_ID: aggregate the per-possession loss differential to
    one per-GAME mean first, then a one-sample t-test across those game
    means. This is the standard cluster-means simplification of a
    cluster-robust SE (Cameron & Miller 2015 sec 8): correct when clusters
    (games) are the true independent unit, and far cheaper than the 2000-
    draw bootstrap it replaces -- O(n) instead of O(n * n_boot)."""
    baseline_err = (actual - baseline_pred) ** 2
    conditioned_err = (actual - conditioned_pred) ** 2
    diffs = baseline_err - conditioned_err  # positive => conditioned wins
    cluster_means = pd.Series(diffs).groupby(pd.Series(game_ids)).mean().to_numpy()
    n_games = len(cluster_means)
    if n_games < 2 or cluster_means.std(ddof=1) == 0.0:
        return {"mean_diff": float(cluster_means.mean()) if n_games else None,
                "t_stat": None, "p_value": None, "n_games": int(n_games), "n_obs": int(len(diffs))}
    t_stat, p_value = stats.ttest_1samp(cluster_means, popmean=0.0)
    return {"mean_diff": float(cluster_means.mean()), "t_stat": float(t_stat),
            "p_value": float(p_value), "n_games": int(n_games), "n_obs": int(len(diffs))}


def dm_verdict(dm: dict, min_games: int = MIN_GAMES, alpha: float = ALPHA) -> str:
    if dm["n_games"] < min_games or dm["p_value"] is None:
        return "INSUFFICIENT_DATA"
    if dm["p_value"] < alpha:
        return "IMPROVES" if dm["mean_diff"] > 0 else "WORSE"
    return "NULL"


def validate_one_corpus(corpus_df: pd.DataFrame, mask: pd.Series, actual_col: str,
                         baseline_val: float, delta: float) -> dict:
    """One claim scored on one corpus: DM-clustered verdict. actual_col is
    'points' for team-grain (vs baseline_ppp) or 'scored' for player-grain
    (vs baseline_rate) -- same squared-error design either grain."""
    active = corpus_df.loc[mask]
    n = len(active)
    if n < MIN_ACTIVE:
        return {"n_active": int(n), "n_games": 0, "mean_diff": None,
                "p_value": None, "verdict": "INSUFFICIENT_DATA"}
    dm = dm_test_clustered(active[actual_col].to_numpy(dtype=float), baseline_val,
                            baseline_val + delta, active["game_id"].to_numpy())
    return {"n_active": int(n), "n_games": dm["n_games"], "mean_diff": dm["mean_diff"],
            "p_value": dm["p_value"], "verdict": dm_verdict(dm)}


def combine_two_corpora(result_a: dict, result_b: dict) -> str:
    """The keystone gate: a claim only survives as a live-pricer candidate if
    BOTH disjoint trailing-date corpora independently IMPROVE (same
    direction, DM p<0.05 each). One corpus improving is not enough --
    matches the program's >=2-corpora-agreement requirement."""
    va, vb = result_a["verdict"], result_b["verdict"]
    if va == "IMPROVES" and vb == "IMPROVES":
        return "IMPROVES_BOTH_CORPORA"
    if va == "WORSE" or vb == "WORSE":
        return "WORSE"  # any WORSE (even against an IMPROVES elsewhere) is a contradiction, not a candidate
    if va == "IMPROVES" or vb == "IMPROVES":
        return "IMPROVES_SINGLE_CORPUS"
    if va == "INSUFFICIENT_DATA" or vb == "INSUFFICIENT_DATA":
        return "INSUFFICIENT_DATA"
    return "NULL"


__all__ = [
    "MIN_ACTIVE", "MIN_GAMES", "ALPHA", "attach_dates", "split_trailing_corpora",
    "dm_test_clustered", "dm_verdict", "validate_one_corpus", "combine_two_corpora",
]
