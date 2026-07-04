"""Self-check: NBA positional_weight rows replayed through reprocess_harness
(metric=rho) against positional_weight_verdict.json (mission spine 2,
wave-33 gap closure PART C).

FINDING HISTORY (fixed, not just reported): the FIRST version of
positional_weight_gate.py's _export_rows built p_variant from
fit_all_group_weights (weights fit on ALL folds, the same weights reported
as fitted_weights_all_2024_25_folds_diagnostic) for every row, which did NOT
reproduce per_fold[i].overall.rho_positional for 2/3 cutoffs (a real,
traced discrepancy -- confirmed live this session, not assumed). Since the
gate's own leave_one_fold_out already computes and returns per-fold LOFO
weights (weights_per_fold, the exact weights used for sign_holds/
bootstrap_delta), _export_rows was updated to score p_variant with EACH
fold's own LOFO weights instead of the all-folds fit -- no new fitting, just
reusing data the gate already produced. positional_weight_verdict.json was
confirmed byte-identical (aside from timestamp) before/after this exporter
change. This self-check now matches exactly; see git history for the
pre-fix PARTIAL_MATCH state if the discrepancy needs to be re-examined.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from scripts.platformkit.reprocess.reprocess_harness import load_rows
from scripts.platformkit.reprocess.reprocess_harness_rho import rho as _rho

_REPO = Path(__file__).resolve().parents[3]
_VERDICT_PATH = _REPO / "data" / "domains" / "basketball_nba" / "positional_weight_verdict.json"
_ROWS_PATH = _REPO / "data" / "domains" / "basketball_nba" / "positional_weight_rows.parquet"
_SELFCHECK_OUT = _REPO / "data" / "domains" / "basketball_nba" / "reprocess_selfcheck_positional.json"

TOL = 1e-6


def run_selfcheck() -> dict[str, Any]:
    if not _VERDICT_PATH.exists() or not _ROWS_PATH.exists():
        return {
            "component": "reprocess_selfcheck_positional", "status": "BLOCKED_MISSING_INPUT",
            "reason": [f"required input missing: verdict={_VERDICT_PATH.exists()} "
                       f"rows={_ROWS_PATH.exists()}"],
            "matched": None, "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    committed = json.loads(_VERDICT_PATH.read_text(encoding="ascii"))
    df = load_rows(_ROWS_PATH)

    fields_compared: list[dict[str, Any]] = []
    max_abs_diff_naive = 0.0
    max_abs_diff_positional = 0.0
    naive_all_matched = True
    positional_all_matched = True

    for fold in committed["per_fold"]:
        cutoff = fold["cutoff"]
        g = df[df["fold_id"] == cutoff]
        y = g["outcome"].to_numpy(dtype=float)
        harness_rho_naive = _rho(g["p_base"].to_numpy(dtype=float), y)
        harness_rho_positional = _rho(g["p_variant"].to_numpy(dtype=float), y)

        d_naive = abs(harness_rho_naive - fold["overall"]["rho_naive"])
        d_pos = abs(harness_rho_positional - fold["overall"]["rho_positional"])
        max_abs_diff_naive = max(max_abs_diff_naive, d_naive)
        max_abs_diff_positional = max(max_abs_diff_positional, d_pos)
        naive_all_matched = naive_all_matched and d_naive <= TOL
        positional_all_matched = positional_all_matched and d_pos <= TOL

        fields_compared.append({
            "cutoff": cutoff, "n": int(len(g)),
            "committed_rho_naive": fold["overall"]["rho_naive"],
            "harness_rho_naive": harness_rho_naive, "abs_diff_naive": d_naive,
            "naive_matched": bool(d_naive <= TOL),
            "committed_rho_positional_lofo": fold["overall"]["rho_positional"],
            "harness_rho_positional_lofo": harness_rho_positional,
            "abs_diff_positional": d_pos,
            "positional_matched": bool(d_pos <= TOL),
        })

    payload = {
        "component": "reprocess_selfcheck_positional",
        "status": "MATCHED" if (naive_all_matched and positional_all_matched) else "PARTIAL_MATCH",
        "matched": bool(naive_all_matched and positional_all_matched),
        "naive_matched": bool(naive_all_matched),
        "positional_matched": bool(positional_all_matched),
        "tolerance": TOL,
        "max_abs_diff_naive": max_abs_diff_naive,
        "max_abs_diff_positional": max_abs_diff_positional,
        "fields_compared": fields_compared,
        "honest_finding": (
            "PARTIAL_MATCH: rho_naive matches exactly but rho_positional does "
            "not -- positional_weight_rows.parquet's p_variant was built from "
            "fit_all_group_weights on export, not the per-fold LOFO weights "
            "the committed verdict actually scored with. See this module's "
            "docstring for the fix (_export_rows now takes weights_per_fold)."
        ) if not positional_all_matched else (
            "full match: p_base==naive_pctile reproduces rho_naive exactly, "
            "and p_variant (scored with each fold's own leave-one-fold-out "
            "weights, reused verbatim from the gate's own per_fold output, "
            "not re-fit) reproduces per_fold[i].overall.rho_positional exactly"
        ),
        "target_reference": _VERDICT_PATH.relative_to(_REPO).as_posix(),
        "rows_path": _ROWS_PATH.relative_to(_REPO).as_posix(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edge_claimed": False,
    }
    return payload


def write_selfcheck(payload: dict[str, Any], dest: Path = _SELFCHECK_OUT) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=1), encoding="ascii")
    return str(dest)


def main() -> int:
    payload = run_selfcheck()
    print(f"status={payload['status']} naive_matched={payload.get('naive_matched')} "
          f"positional_matched={payload.get('positional_matched')}")
    write_selfcheck(payload)
    print(f"wrote {_SELFCHECK_OUT}")
    return 0 if payload.get("matched") else 1


if __name__ == "__main__":
    raise SystemExit(main())
