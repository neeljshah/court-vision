"""Predictive-validity artifact writer.

write_predictive_validity_artifact(): one JSON per (family, metric) at
data/cache/predictive_validity/<family>__<metric>.json, in the
quality_claim_builders.write_verdict() doc shape (component/hypothesis/
verdict/.../honest_note/edge_claimed:false).

stamp_validation(): read-modify-write merge of a compact per-metric summary
into data/cache/intel_claims/<family>_validation.json under a top-level
"predictive_validity" key -- atomic (tmp+replace), additive (never clobbers
whatever the claims-side validator already wrote there), and NEVER touches
the claims .jsonl itself.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARTIFACT_DIR = "data/cache/predictive_validity"
VALIDATION_DIR = "data/cache/intel_claims"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="ascii")
    tmp.replace(path)


def write_predictive_validity_artifact(result: dict[str, Any], out_dir: str = ARTIFACT_DIR) -> str:
    """result is run_metric_test()'s return dict. Returns the path written."""
    doc = {
        "component": f"predictive_validity__{result['family']}__{result['metric_name']}",
        "sport": result["sport"],
        "hypothesis": (
            f"{result['metric_name']} predicts the forward outcome better than the "
            f"declared naive baseline {result['baseline_name']} (walk-forward, "
            f"forward_games={result['forward_games']}, natural grain -- not vs the market close)"
        ),
        "verdict": result["verdict"],
        "mean_rho_metric": result["mean_rho_metric"],
        "mean_rho_baseline": result["mean_rho_baseline"],
        "rho_metric_bootstrap": result["rho_metric_bootstrap"],
        "bootstrap_delta_ci": result["bootstrap_delta_ci"],
        "sign_holds_folds": result["sign_holds_folds"],
        "n_folds": result["n_folds"],
        "per_cutoff": result["per_cutoff"],
        "caveat": result.get("caveat", ""),
        "generated_at": _now_iso(),
        "honest_note": (
            "predictive-validity comparison only, against a declared naive baseline at the "
            "metric's natural grain, NOT vs the market close; DESCRIPTIVE_ONLY/UNDERPOWERED "
            "is a recorded honest outcome, not a failure"
        ),
        "edge_claimed": False,
    }
    path = Path(out_dir) / f"{result['family']}__{result['metric_name']}.json"
    _atomic_write(path, doc)
    return str(path)


def stamp_validation(family: str, metric_name: str, verdict: str, rho_metric_mean: float,
                      delta_ci: dict[str, Any], n_folds: int,
                      validation_dir: str = VALIDATION_DIR) -> str:
    """Merge {metric_name: {verdict, rho_metric_mean, delta_ci, n_folds, as_of}}
    into the family's REAL validation sidecar's top-level "predictive_validity"
    key. Store naming varies (mlb_batter_rate.jsonl vs shooter_composite_v2_
    claims.jsonl), so the sidecar is resolved off whichever claims store
    actually exists: <family>.jsonl -> <family>_validation.json, else
    <family>_claims.jsonl -> <family>_claims_validation.json. Read-modify-
    write; creates the file (with only that key) if the claims-side validator
    hasn't produced one yet -- never touches the claims .jsonl."""
    d = Path(validation_dir)
    stem = family if (d / f"{family}.jsonl").exists() else (
        f"{family}_claims" if (d / f"{family}_claims.jsonl").exists() else family)
    path = d / f"{stem}_validation.json"
    doc: dict[str, Any] = {}
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="ascii"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            doc = {}
    predictive_validity = dict(doc.get("predictive_validity") or {})
    predictive_validity[metric_name] = {
        "verdict": verdict,
        "rho_metric_mean": rho_metric_mean,
        "delta_ci": delta_ci,
        "n_folds": n_folds,
        "as_of": _now_iso(),
    }
    doc["predictive_validity"] = predictive_validity
    _atomic_write(path, doc)
    return str(path)
