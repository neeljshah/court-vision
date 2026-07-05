"""fit_validity_gate_report -- verdict-JSON writer + CLI entry point for the
V2 fit-validity gate. Split out of fit_validity_gate_impl.py purely to keep
that file under the 300-LOC cap; this module is pure I/O (serialize a
GateRunResult, run the CLI) and imports the compute logic rather than
duplicating it.

CLI:
    python -m scripts.platformkit.intel_validation.fit_validity_gate_report --run
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.intel_validation.fit_validity_gate_impl import (
    GateRunResult,
    VERDICT_OUT_PATH,
    run_gate,
)


def write_verdict(result: GateRunResult, out_path: Path = VERDICT_OUT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "component": "fit_validity_gate",
        "spec_version": "v2",
        "v2_spec_sha16": result.v2_spec_sha16,
        "n_moves": result.n_moves,
        "folds": result.n_folds,
        "per_fold_delta": [
            {"fold": f.fold_name, "n": f.n, "rmse_h0": f.rmse_h0, "rmse_h1": f.rmse_h1,
             "corr_h1": f.corr_h1, "delta_rmse": f.delta_rmse, "beta_selected": f.beta_selected}
            for f in result.per_fold
        ],
        "pooled_delta": result.pooled_delta,
        "sign_holds": f"{result.sign_holds_count}/{result.n_folds}",
        "off_init_moved": result.off_init_moved,
        "null1_result": result.null1_result,
        "null2_result": result.null2_result,
        "verdict": result.verdict,
        "verdict_reason": result.verdict_reason,
        "edge_claimed": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        json.dump(payload, f, indent=2)
    return out_path


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Fit-validity gate V2 -- actual run (authorized)")
    parser.add_argument("--run", action="store_true", help="execute the gate and write the verdict json")
    args = parser.parse_args(argv)
    if not args.run:
        print("pass --run to execute (measurement-only, writes data/domains/nba/fit_validity_gate_verdict.json)")
        return 0
    result = run_gate(explicit_run_requested=True)
    out = write_verdict(result)
    print(f"verdict={result.verdict} pooled_delta={result.pooled_delta:.4f} written to {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
