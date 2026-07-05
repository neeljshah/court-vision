"""scripts.platformkit.reprocess.reprocess_harness_rho -- Spearman-rho metric
companion for reprocess_harness.py (metric=rho path for continuous
outcomes) PLUS the fail-closed metric/outcome-dtype validator shared by
both metrics, split out to keep reprocess_harness.py under the 300-LOC cap.

Same sport-blind, no-producer-import invariant as reprocess_harness.py.
Imported lazily by run_harness() to avoid a circular import (this module
does not import FROM reprocess_harness, so a plain top-level import would
also work, but lazy-import keeps the pattern consistent with other gate/io
splits in this repo).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

METRICS = ("brier", "rho", "rmse")
N_BOOT_RHO = 2000
BOOT_SEED_RHO = 20260704


def is_binary_outcome(y: np.ndarray) -> bool:
    """True iff every value is exactly 0 or 1 (allows a single-class corpus)."""
    uniq = np.unique(y[~np.isnan(y)])
    return len(uniq) > 0 and set(uniq.tolist()).issubset({0.0, 1.0})


def validate_metric_matches_outcome(df: pd.DataFrame, metric: str, schema_error_cls: type) -> None:
    """Fail-closed check: the declared metric must match the outcome dtype.
    metric is NEVER inferred silently from cardinality -- the caller always
    states it; this only catches a stated metric that contradicts the data."""
    if metric not in METRICS:
        raise schema_error_cls(f"unknown metric {metric!r}; must be one of {METRICS}")
    y = df["outcome"].to_numpy(dtype=float)
    binary = is_binary_outcome(y)
    if metric == "brier" and not binary:
        raise schema_error_cls(
            "metric=brier declared but outcome is not binary (0/1) -- "
            "continuous outcomes require --metric rho or --metric rmse"
        )
    if metric in ("rho", "rmse") and binary:
        raise schema_error_cls(
            f"metric={metric} declared but outcome is binary (0/1) -- "
            "binary outcomes require --metric brier"
        )


def rho(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return float("nan")
    r, _ = spearmanr(x, y)
    return float(r)


@dataclass
class RhoComparisonBlock:
    """rho(p_base, outcome) vs rho(p_variant, outcome), plus a paired cluster
    bootstrap on the delta (positive delta => variant more predictive)."""
    rho_base: float
    rho_variant: float
    delta: float
    ci_lo: float
    ci_hi: float
    n: int
    n_clusters: int
    n_boot_effective: int


def rho_compare(df: pd.DataFrame, base_col: str, cluster_col: str,
                 n_boot: int = N_BOOT_RHO, seed: int = BOOT_SEED_RHO) -> RhoComparisonBlock:
    """Paired-by-cluster bootstrap: resample cluster ids WITH replacement,
    rebuild the pooled sample from those clusters' rows, recompute both rhos,
    take the delta. Mirrors the cluster-robust intent of the Brier DM path
    (resampling units are whole clusters, not individual rows) so a rho win
    driven by one over-represented cluster (e.g. one player) is visible in a
    widened CI rather than hidden."""
    y = df["outcome"].to_numpy(dtype=float)
    p_variant = df["p_variant"].to_numpy(dtype=float)
    p_base = df[base_col].to_numpy(dtype=float)
    rho_base = rho(p_base, y)
    rho_variant = rho(p_variant, y)
    delta = rho_variant - rho_base

    clusters = df[cluster_col].to_numpy()
    uniq_clusters = np.unique(clusters)
    n_clusters = len(uniq_clusters)
    rng = np.random.default_rng(seed)
    cluster_row_idx = {c: np.where(clusters == c)[0] for c in uniq_clusters}

    deltas: list[float] = []
    for _ in range(n_boot):
        sampled = rng.choice(uniq_clusters, size=n_clusters, replace=True)
        idx = np.concatenate([cluster_row_idx[c] for c in sampled])
        yb, pb, pv = y[idx], p_base[idx], p_variant[idx]
        rb, rv = rho(pb, yb), rho(pv, yb)
        if np.isfinite(rb) and np.isfinite(rv):
            deltas.append(rv - rb)

    n_eff = len(deltas)
    if n_eff >= 10:
        ci_lo, ci_hi = float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))
    else:
        ci_lo, ci_hi = float("nan"), float("nan")

    return RhoComparisonBlock(
        rho_base=rho_base, rho_variant=rho_variant, delta=delta,
        ci_lo=ci_lo, ci_hi=ci_hi, n=int(len(df)), n_clusters=n_clusters,
        n_boot_effective=n_eff,
    )


def rho_block_to_dict(b: RhoComparisonBlock) -> dict[str, Any]:
    return {
        "rho_base": b.rho_base, "rho_variant": b.rho_variant, "delta": b.delta,
        "ci_lo": b.ci_lo, "ci_hi": b.ci_hi, "n": b.n, "n_clusters": b.n_clusters,
        "n_boot_effective": b.n_boot_effective,
    }


def rho_fold_signs(df: pd.DataFrame, base_col: str) -> list[dict[str, Any]]:
    """Per-fold sign of (rho_variant - rho_base); positive => variant wins
    that fold."""
    out = []
    for fold_id, g in df.groupby("fold_id", sort=True):
        y = g["outcome"].to_numpy(dtype=float)
        d = rho(g["p_variant"].to_numpy(dtype=float), y) - rho(g[base_col].to_numpy(dtype=float), y)
        sign = "tie"
        if np.isfinite(d):
            sign = "variant" if d > 0 else ("base" if d < 0 else "tie")
        out.append({"fold_id": str(fold_id), "n": int(len(g)),
                     "mean_delta": float(d) if np.isfinite(d) else None, "sign": sign})
    return out


def run_harness_rho(df: pd.DataFrame, cluster_col: str, schema_error_cls: type) -> dict[str, Any]:
    """Returns the metric='rho' portion of a ReprocessVerdict as plain kwargs
    (per_corpus, pooled_diagnostic, has_close, generated_at, edge_claimed,
    metric) -- reprocess_harness.py wraps this in its own ReprocessVerdict
    dataclass to avoid this module importing FROM reprocess_harness."""
    if cluster_col not in df.columns:
        raise schema_error_cls(
            f"metric=rho requires a declared cluster column {cluster_col!r} "
            f"present in the input (e.g. player_id) -- fails closed rather "
            f"than falling back to event_id"
        )

    per_corpus: dict[str, Any] = {}
    for corpus_id, g in df.groupby("corpus_id", sort=True):
        per_corpus[str(corpus_id)] = {
            "n": int(len(g)),
            "vs_base": rho_block_to_dict(rho_compare(g, "p_base", cluster_col)),
            "per_fold_signs_vs_base": rho_fold_signs(g, "p_base"),
        }

    pooled_diagnostic: dict[str, Any] = {
        "n": int(len(df)),
        "vs_base": rho_block_to_dict(rho_compare(df, "p_base", cluster_col)),
        "note": "DIAGNOSTIC ONLY -- corpora pooled across provenance; never the verdict basis",
    }

    return dict(
        per_corpus=per_corpus, pooled_diagnostic=pooled_diagnostic,
        has_close=False, generated_at=datetime.now(timezone.utc).isoformat(),
        edge_claimed=False, metric="rho",
    )


__all__ = ["rho", "RhoComparisonBlock", "rho_compare", "rho_block_to_dict",
           "rho_fold_signs", "run_harness_rho", "N_BOOT_RHO", "BOOT_SEED_RHO",
           "METRICS", "is_binary_outcome", "validate_metric_matches_outcome"]
