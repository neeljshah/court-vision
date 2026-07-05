"""Sport-blind reprocess-comparison harness (mission spine 2).

Feed it PRE-SCORED rows for a base variant and a challenger variant, get
back a leak-free-respecting, provenance-separated Brier/Diebold-Mariano
verdict (binary outcomes), a Spearman-rho verdict, or an RMSE verdict
(continuous outcomes -- see reprocess_harness_rho.py / _rmse.py). NEVER
imports producer code -- callers score their own variant, persist the rows,
hand this harness a parquet/JSONL.

INPUT (parquet/JSONL), one row per scored prediction: corpus_id (provenance,
never pooled for the verdict), fold_id, event_id, p_variant, p_base,
outcome (binary 0/1 for brier; continuous prediction/target for rho/rmse),
p_close (OPTIONAL, brier-only calibration-vs-close, never an edge).

METRIC is declared explicitly via --metric {brier,rho,rmse}, NEVER inferred
from outcome cardinality -- a mismatch is a fail-closed SchemaError. rho
requires a declared cluster_col (default "cluster_id") for its paired
cluster bootstrap, fails closed if missing. rmse's cluster bootstrap is
OPTIONAL -- pass --no-cluster-col to omit it (CI reported as nan). See
reprocess_harness_rho.py (rho + shared validator) / _rmse.py (rmse).

CLI:
    python -m scripts.platformkit.reprocess.reprocess_harness --input X --out Y --metric brier
    python -m scripts.platformkit.reprocess.reprocess_harness --input X --out Y --metric rmse --cluster-col hp_umpire_id
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano

from scripts.platformkit.reprocess.reprocess_harness_rho import METRICS

REQUIRED_COLS = ["corpus_id", "fold_id", "event_id", "p_variant", "p_base", "outcome"]
OPTIONAL_CLOSE_COL = "p_close"
DEFAULT_CLUSTER_COL = "cluster_id"


class SchemaError(ValueError):
    """Raised when the input rows do not satisfy the shared contract shape."""


def load_rows(path: Path) -> pd.DataFrame:
    """Load the pre-scored rows from parquet or JSONL. Fails closed (raises)
    on a missing file or a missing required column -- never silently drops."""
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix in (".jsonl", ".json"):
        rows = []
        with open(path, "r", encoding="ascii", errors="strict") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        df = pd.DataFrame(rows)
    else:
        raise SchemaError(f"unsupported input extension: {path.suffix!r}")

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise SchemaError(f"input missing required columns: {missing}")
    return df


def _brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per-row squared error (Brier loss contribution)."""
    return (p - y) ** 2


def validate_metric_matches_outcome(df: pd.DataFrame, metric: str) -> None:
    """Fail-closed: declared metric must match outcome dtype, never inferred.
    Thin wrapper -- check lives in reprocess_harness_rho (300-LOC cap)."""
    from scripts.platformkit.reprocess.reprocess_harness_rho import (
        validate_metric_matches_outcome as _validate,
    )
    _validate(df, metric, SchemaError)


@dataclass
class ComparisonBlock:
    """One base-vs-challenger comparison (variant-vs-base, or variant-vs-close)."""
    brier_base: float
    brier_variant: float
    delta: float  # brier_base - brier_variant; positive => variant improves
    dm_stat: float
    dm_p: float
    dm_ci95: tuple
    n: int
    n_clusters: int


def _compare(df: pd.DataFrame, base_col: str) -> ComparisonBlock:
    """d_t = loss_base(t) - loss_variant(t); positive mean => variant better.
    Clustered by fold_id (mirrors dm_test's game_id clustering convention --
    states within one fold are correlated)."""
    y = df["outcome"].to_numpy(dtype=float)
    p_variant = df["p_variant"].to_numpy(dtype=float)
    p_base = df[base_col].to_numpy(dtype=float)
    loss_variant = _brier(p_variant, y)
    loss_base = _brier(p_base, y)
    d = loss_base - loss_variant
    dm = diebold_mariano(d, df["fold_id"].tolist())
    return ComparisonBlock(
        brier_base=float(loss_base.mean()),
        brier_variant=float(loss_variant.mean()),
        delta=float(loss_base.mean() - loss_variant.mean()),
        dm_stat=dm.dm_stat,
        dm_p=dm.p_value,
        dm_ci95=dm.ci95,
        n=dm.n,
        n_clusters=dm.n_clusters,
    )


def _block_to_dict(b: ComparisonBlock) -> dict[str, Any]:
    return {
        "brier_base": b.brier_base,
        "brier_variant": b.brier_variant,
        "delta": b.delta,
        "dm_stat": b.dm_stat,
        "dm_p": b.dm_p,
        "dm_ci95": list(b.dm_ci95),
        "n": b.n,
        "n_clusters": b.n_clusters,
    }


def _fold_signs(df: pd.DataFrame, base_col: str) -> list[dict[str, Any]]:
    """Per-fold sign of (brier_base - brier_variant); positive => variant wins
    that fold. Reported so a pooled win driven by one fold is visible."""
    out = []
    for fold_id, g in df.groupby("fold_id", sort=True):
        y = g["outcome"].to_numpy(dtype=float)
        d = _brier(g[base_col].to_numpy(dtype=float), y) - _brier(g["p_variant"].to_numpy(dtype=float), y)
        out.append({"fold_id": str(fold_id), "n": int(len(g)), "mean_delta": float(d.mean()),
                     "sign": "variant" if d.mean() > 0 else ("base" if d.mean() < 0 else "tie")})
    return out


@dataclass
class ReprocessVerdict:
    per_corpus: dict[str, Any] = field(default_factory=dict)
    pooled_diagnostic: dict[str, Any] = field(default_factory=dict)
    has_close: bool = False
    generated_at: str = ""
    edge_claimed: bool = False
    metric: str = "brier"


def _run_harness_brier(df: pd.DataFrame) -> ReprocessVerdict:
    has_close = OPTIONAL_CLOSE_COL in df.columns

    per_corpus: dict[str, Any] = {}
    for corpus_id, g in df.groupby("corpus_id", sort=True):
        block: dict[str, Any] = {
            "n": int(len(g)),
            "vs_base": _block_to_dict(_compare(g, "p_base")),
            "per_fold_signs_vs_base": _fold_signs(g, "p_base"),
        }
        if has_close:
            g_close = g.dropna(subset=[OPTIONAL_CLOSE_COL])
            if len(g_close) > 0:
                block["vs_close_calibration"] = {
                    **_block_to_dict(_compare(g_close, OPTIONAL_CLOSE_COL)),
                    "label": "CALIBRATION-vs-close, never an edge",
                    "n_scored": int(len(g_close)),
                }
        per_corpus[str(corpus_id)] = block

    pooled_diagnostic: dict[str, Any] = {
        "n": int(len(df)),
        "vs_base": _block_to_dict(_compare(df, "p_base")),
        "note": "DIAGNOSTIC ONLY -- corpora pooled across provenance; never the verdict basis",
    }
    if has_close:
        df_close = df.dropna(subset=[OPTIONAL_CLOSE_COL])
        if len(df_close) > 0:
            pooled_diagnostic["vs_close_calibration"] = {
                **_block_to_dict(_compare(df_close, OPTIONAL_CLOSE_COL)),
                "label": "CALIBRATION-vs-close, never an edge",
                "n_scored": int(len(df_close)),
            }

    return ReprocessVerdict(
        per_corpus=per_corpus, pooled_diagnostic=pooled_diagnostic,
        has_close=has_close, generated_at=datetime.now(timezone.utc).isoformat(),
        edge_claimed=False, metric="brier",
    )


def _run_harness_rho(df: pd.DataFrame, cluster_col: str) -> ReprocessVerdict:
    """Delegates to reprocess_harness_rho (300-LOC cap split)."""
    from scripts.platformkit.reprocess.reprocess_harness_rho import run_harness_rho
    return ReprocessVerdict(**run_harness_rho(df, cluster_col, SchemaError))


def _run_harness_rmse(df: pd.DataFrame, cluster_col: str | None) -> ReprocessVerdict:
    """Delegates to reprocess_harness_rmse (300-LOC cap split)."""
    from scripts.platformkit.reprocess.reprocess_harness_rmse import run_harness_rmse
    return ReprocessVerdict(**run_harness_rmse(df, cluster_col, SchemaError))


def run_harness(df: pd.DataFrame, metric: str = "brier",
                cluster_col: str | None = DEFAULT_CLUSTER_COL) -> ReprocessVerdict:
    """Corpora are NEVER pooled for the verdict -- only shown pooled as a
    diagnostic. Fails closed on a missing col or metric/outcome mismatch.
    metric is ALWAYS explicit -- never inferred. metric=rmse: pass
    cluster_col=None to skip its (optional) paired bootstrap."""
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise SchemaError(f"input missing required columns: {missing}")
    validate_metric_matches_outcome(df, metric)

    if metric == "rho":
        return _run_harness_rho(df, cluster_col)
    if metric == "rmse":
        return _run_harness_rmse(df, cluster_col)
    return _run_harness_brier(df)


_HONEST_NOTES = {
    "rho": ("leak-free walk-forward comparison of pre-scored variant vs base Spearman "
            "rho vs a continuous outcome; corpora provenance-separated, never pooled "
            "for the verdict (pooled block is diagnostic only); rho deltas are "
            "descriptive/predictive-validity only, never an edge"),
    "rmse": ("leak-free walk-forward comparison of pre-scored variant vs base continuous "
             "PREDICTIONS scored by RMSE vs a continuous target; corpora provenance-"
             "separated, never pooled for the verdict (pooled block is diagnostic only); "
             "RMSE deltas are a calibration/fit comparison, never an edge"),
    "brier": ("leak-free walk-forward comparison of pre-scored variant vs base Brier "
              "loss; corpora provenance-separated, never pooled for the verdict (pooled "
              "block is diagnostic only); vs_close, when present, is calibration only, "
              "never an edge"),
}


def verdict_to_dict(v: ReprocessVerdict) -> dict[str, Any]:
    honest_note = _HONEST_NOTES[v.metric]
    return {
        "component": "reprocess_harness",
        "metric": v.metric,
        "generated_at": v.generated_at,
        "per_corpus": v.per_corpus,
        "pooled_diagnostic": v.pooled_diagnostic,
        "has_close": v.has_close,
        "honest_note": honest_note,
        "edge_claimed": v.edge_claimed,
    }


def write_verdict(v: ReprocessVerdict, out_path: Path) -> dict[str, Any]:
    payload = verdict_to_dict(v)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1), encoding="ascii")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sport-blind reprocess-comparison harness")
    parser.add_argument("--input", required=True, help="path to pre-scored rows (parquet or JSONL)")
    parser.add_argument("--out", required=True, help="path to write the verdict JSON")
    parser.add_argument("--metric", choices=METRICS, default="brier",
                        help="brier (binary), rho (continuous, cluster required), or rmse "
                             "(continuous pred vs target, cluster optional)")
    parser.add_argument("--cluster-col", default=DEFAULT_CLUSTER_COL,
                        help="cluster column for rho (required) / rmse (optional) bootstrap")
    parser.add_argument("--no-cluster-col", action="store_true",
                        help="metric=rmse only: omit the paired bootstrap (CI reported as nan)")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    cluster_col = None if (args.metric == "rmse" and args.no_cluster_col) else args.cluster_col
    try:
        df = load_rows(input_path)
        verdict = run_harness(df, metric=args.metric, cluster_col=cluster_col)
    except (FileNotFoundError, SchemaError) as e:
        print(f"BLOCKED: {e}")
        return 1

    write_verdict(verdict, Path(args.out))
    print(f"metric={verdict.metric} n_corpora={len(verdict.per_corpus)} pooled_n={verdict.pooled_diagnostic['n']}")
    tails = {"rho": lambda vb: f"ci=[{vb['ci_lo']:.4f},{vb['ci_hi']:.4f}]",
             "rmse": lambda vb: f"rmse_base={vb['rmse_base']:.6f} rmse_variant={vb['rmse_variant']:.6f}",
             "brier": lambda vb: f"dm_p={vb['dm_p']:.4f}"}
    for corpus_id, block in verdict.per_corpus.items():
        vb = block["vs_base"]
        print(f"  {corpus_id}: n={block['n']} delta={vb['delta']:.6f} {tails[verdict.metric](vb)}")
    print(f"wrote verdict to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
