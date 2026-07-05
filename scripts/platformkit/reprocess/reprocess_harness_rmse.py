"""scripts.platformkit.reprocess.reprocess_harness_rmse -- RMSE metric
companion for reprocess_harness.py (metric=rmse path for continuous
PREDICTIONS scored against a continuous target), split out to keep
reprocess_harness.py under the 300-LOC cap.

Closes the wave-47 client-registration gap: some shipped gates (e.g.
domains.mlb.umpire_totals_gate) score a continuous prediction (predicted
total runs) against a continuous target (actual total runs) with RMSE, not
a probability against a binary outcome. metric=rmse reuses the SAME column
contract as brier/rho (corpus_id, fold_id, event_id, p_variant, p_base,
outcome) -- p_variant/p_base are the candidate/baseline continuous
PREDICTIONS (not probabilities) and outcome is the continuous TARGET. This
keeps one input shape across all three metrics; callers/clients relabel
their own columns into this contract, the harness never renames or infers.

Same sport-blind, no-producer-import invariant as reprocess_harness.py and
reprocess_harness_rho.py. Imported lazily by run_harness() to match the
existing lazy-import pattern used for the rho path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

N_BOOT_RMSE = 2000
BOOT_SEED_RMSE = 20260706


def is_binary_outcome(y: np.ndarray) -> bool:
    """True iff every value is exactly 0 or 1 (allows a single-class corpus).
    Duplicated (not imported) from reprocess_harness_rho to avoid a circular
    import back into this module from the shared validator; kept identical."""
    uniq = np.unique(y[~np.isnan(y)])
    return len(uniq) > 0 and set(uniq.tolist()).issubset({0.0, 1.0})


def _rmse(pred: np.ndarray, y: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - y) ** 2)))


@dataclass
class RmseComparisonBlock:
    """rmse(p_base, outcome) vs rmse(p_variant, outcome); delta = rmse_base -
    rmse_variant (positive => variant/candidate improves, mirrors the Brier
    delta sign convention). Optional paired-cluster bootstrap CI on the delta
    when a cluster_col is declared and present -- fails closed (raises) if a
    cluster_col is explicitly declared but the column is missing, same as the
    rho path; if no cluster_col is declared at all, the CI is omitted (nan)
    rather than silently falling back to an ungrouped/per-row bootstrap."""
    rmse_base: float
    rmse_variant: float
    delta: float
    n: int
    ci_lo: float
    ci_hi: float
    n_clusters: int
    n_boot_effective: int


def _paired_cluster_bootstrap(y: np.ndarray, p_base: np.ndarray, p_variant: np.ndarray,
                               clusters: np.ndarray, n_boot: int, seed: int) -> tuple:
    uniq_clusters = np.unique(clusters)
    n_clusters = len(uniq_clusters)
    rng = np.random.default_rng(seed)
    cluster_row_idx = {c: np.where(clusters == c)[0] for c in uniq_clusters}

    deltas: list[float] = []
    for _ in range(n_boot):
        sampled = rng.choice(uniq_clusters, size=n_clusters, replace=True)
        idx = np.concatenate([cluster_row_idx[c] for c in sampled])
        yb, bb, vb = y[idx], p_base[idx], p_variant[idx]
        d = _rmse(bb, yb) - _rmse(vb, yb)
        if np.isfinite(d):
            deltas.append(d)

    n_eff = len(deltas)
    if n_eff >= 10:
        ci_lo, ci_hi = float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))
    else:
        ci_lo, ci_hi = float("nan"), float("nan")
    return ci_lo, ci_hi, n_clusters, n_eff


def rmse_compare(df: pd.DataFrame, base_col: str, cluster_col: Optional[str],
                  n_boot: int = N_BOOT_RMSE, seed: int = BOOT_SEED_RMSE) -> RmseComparisonBlock:
    y = df["outcome"].to_numpy(dtype=float)
    p_variant = df["p_variant"].to_numpy(dtype=float)
    p_base = df[base_col].to_numpy(dtype=float)
    rmse_base = _rmse(p_base, y)
    rmse_variant = _rmse(p_variant, y)
    delta = rmse_base - rmse_variant

    if cluster_col is not None:
        clusters = df[cluster_col].to_numpy()
        ci_lo, ci_hi, n_clusters, n_eff = _paired_cluster_bootstrap(
            y, p_base, p_variant, clusters, n_boot, seed)
    else:
        ci_lo, ci_hi, n_clusters, n_eff = float("nan"), float("nan"), 0, 0

    return RmseComparisonBlock(
        rmse_base=rmse_base, rmse_variant=rmse_variant, delta=delta, n=int(len(df)),
        ci_lo=ci_lo, ci_hi=ci_hi, n_clusters=n_clusters, n_boot_effective=n_eff,
    )


def rmse_block_to_dict(b: RmseComparisonBlock) -> dict[str, Any]:
    return {
        "rmse_base": b.rmse_base, "rmse_variant": b.rmse_variant, "delta": b.delta,
        "n": b.n, "ci_lo": b.ci_lo, "ci_hi": b.ci_hi,
        "n_clusters": b.n_clusters, "n_boot_effective": b.n_boot_effective,
    }


def rmse_fold_signs(df: pd.DataFrame, base_col: str) -> list[dict[str, Any]]:
    """Per-fold sign of (rmse_base - rmse_variant); positive => variant/
    candidate wins that fold. Reported so a pooled win driven by one fold is
    visible (mirrors _fold_signs in reprocess_harness.py and rho_fold_signs
    in reprocess_harness_rho.py)."""
    out = []
    for fold_id, g in df.groupby("fold_id", sort=True):
        y = g["outcome"].to_numpy(dtype=float)
        d = _rmse(g[base_col].to_numpy(dtype=float), y) - _rmse(g["p_variant"].to_numpy(dtype=float), y)
        out.append({"fold_id": str(fold_id), "n": int(len(g)), "mean_delta": float(d),
                     "sign": "variant" if d > 0 else ("base" if d < 0 else "tie")})
    return out


def run_harness_rmse(df: pd.DataFrame, cluster_col: Optional[str], schema_error_cls: type) -> dict[str, Any]:
    """Returns the metric='rmse' portion of a ReprocessVerdict as plain kwargs
    (per_corpus, pooled_diagnostic, has_close, generated_at, edge_claimed,
    metric) -- reprocess_harness.py wraps this in its own ReprocessVerdict
    dataclass, same pattern as run_harness_rho.

    cluster_col: if declared (not None) it MUST be present in df -- fails
    closed rather than silently skipping the paired bootstrap. If cluster_col
    is None (not declared by the caller), the bootstrap CI is simply omitted
    (nan) -- this is the RMSE-specific relaxation the task calls for ("paired
    bootstrap on the delta where cluster col declared"), never a silent
    fallback to a different column."""
    if cluster_col is not None and cluster_col not in df.columns:
        raise schema_error_cls(
            f"metric=rmse declared cluster column {cluster_col!r} but it is not "
            f"present in the input -- fails closed rather than silently skipping "
            f"the paired bootstrap or falling back to another column"
        )

    per_corpus: dict[str, Any] = {}
    for corpus_id, g in df.groupby("corpus_id", sort=True):
        per_corpus[str(corpus_id)] = {
            "n": int(len(g)),
            "vs_base": rmse_block_to_dict(rmse_compare(g, "p_base", cluster_col)),
            "per_fold_signs_vs_base": rmse_fold_signs(g, "p_base"),
        }

    pooled_diagnostic: dict[str, Any] = {
        "n": int(len(df)),
        "vs_base": rmse_block_to_dict(rmse_compare(df, "p_base", cluster_col)),
        "note": "DIAGNOSTIC ONLY -- corpora pooled across provenance; never the verdict basis",
    }

    return dict(
        per_corpus=per_corpus, pooled_diagnostic=pooled_diagnostic,
        has_close=False, generated_at=datetime.now(timezone.utc).isoformat(),
        edge_claimed=False, metric="rmse",
    )


__all__ = ["rmse_compare", "RmseComparisonBlock", "rmse_block_to_dict", "rmse_fold_signs",
           "run_harness_rmse", "N_BOOT_RMSE", "BOOT_SEED_RMSE", "is_binary_outcome"]
