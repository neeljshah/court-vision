"""Sport-blind reprocess-comparison harness (mission spine 2).

The standing machinery that lets every intelligence change be re-validated
against old+new games: feed it PRE-SCORED rows for a base variant and a
challenger variant, get back a leak-free-respecting, provenance-separated
Brier/Diebold-Mariano verdict.

This harness NEVER imports producer code -- same invariant as
scripts/platformkit/intel_validation/claims_validator.py. Callers score their
own variant with their own module, persist the rows, and hand this harness a
parquet/JSONL of already-scored predictions.

INPUT SHAPE (parquet or JSONL), one row per scored prediction:
    corpus_id   str    -- provenance tag; corpora are NEVER pooled for the
                          verdict (pooled numbers are a diagnostic only)
    fold_id     str    -- walk-forward fold within a corpus
    event_id    str    -- unique id of the scored event/state
    p_variant   float  -- challenger's predicted probability, in [0, 1]
    p_base      float  -- base/incumbent's predicted probability, in [0, 1]
    outcome     int    -- realized binary outcome, 0 or 1
    p_close     float  -- OPTIONAL devigged close probability. When present,
                          the verdict also reports variant-vs-close as a
                          CALIBRATION comparison, never an edge.

OUTPUT: verdict JSON -- per-corpus and a pooled-diagnostic Brier/DM comparison
of variant vs base (and vs close, if p_close is present). Fails closed on any
missing required column. edge_claimed is always stamped false.

CLI:
    python -m scripts.platformkit.reprocess.reprocess_harness --input X --out Y
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

REQUIRED_COLS = ["corpus_id", "fold_id", "event_id", "p_variant", "p_base", "outcome"]
OPTIONAL_CLOSE_COL = "p_close"


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


def run_harness(df: pd.DataFrame) -> ReprocessVerdict:
    """Corpora are NEVER pooled for the verdict -- only shown pooled as a
    diagnostic. Fails closed (raises SchemaError) on missing required cols;
    caller (load_rows) already enforces this, but re-check defensively since
    run_harness may be called directly with a caller-built DataFrame."""
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise SchemaError(f"input missing required columns: {missing}")

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
        per_corpus=per_corpus,
        pooled_diagnostic=pooled_diagnostic,
        has_close=has_close,
        generated_at=datetime.now(timezone.utc).isoformat(),
        edge_claimed=False,
    )


def verdict_to_dict(v: ReprocessVerdict) -> dict[str, Any]:
    return {
        "component": "reprocess_harness",
        "generated_at": v.generated_at,
        "per_corpus": v.per_corpus,
        "pooled_diagnostic": v.pooled_diagnostic,
        "has_close": v.has_close,
        "honest_note": (
            "leak-free walk-forward comparison of pre-scored variant vs base "
            "Brier loss; corpora are provenance-separated and never pooled for "
            "the verdict (pooled block is a diagnostic only); vs_close block, "
            "when present, is a calibration comparison, never an edge"
        ),
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
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    try:
        df = load_rows(input_path)
        verdict = run_harness(df)
    except (FileNotFoundError, SchemaError) as e:
        print(f"BLOCKED: {e}")
        return 1

    write_verdict(verdict, Path(args.out))
    print(f"n_corpora={len(verdict.per_corpus)} pooled_n={verdict.pooled_diagnostic['n']}")
    for corpus_id, block in verdict.per_corpus.items():
        vb = block["vs_base"]
        print(f"  {corpus_id}: n={block['n']} delta={vb['delta']:.6f} dm_p={vb['dm_p']:.4f}")
    print(f"wrote verdict to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
