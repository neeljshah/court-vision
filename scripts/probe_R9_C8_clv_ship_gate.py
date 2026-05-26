"""probe_R9_C8_clv_ship_gate.py -- R9 C8 integration probe.

Goal: prove the new CLV ship gate doesn't break the existing MAE-based
adjudication on R0-R8 historical probes. We replay the R8_M22 sharper-bands
result through ``check_clv_gate + compose_with_mae`` and assert it still
produces REJECT (its historical verdict).

Also exercises:
- A synthetic "model-change passes" path (full SHIP).
- A synthetic "sizing_timing fails on weak mean_pct" path.

Outputs ``data/cache/probe_R9_C8_clv_ship_gate_results.json``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.improve_loop.clv_gate import (  # noqa: E402
    check_clv_gate,
    compose_with_mae,
)

OUTPUT_PATH = PROJECT_DIR / "data" / "cache" / "probe_R9_C8_clv_ship_gate_results.json"
R8_M22_RESULTS = PROJECT_DIR / "data" / "cache" / "probe_R8_M22_sharper_bands_results.json"


def _run_unit_tests() -> dict:
    """Run pytest on tests/test_clv_gate.py and return summary."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_clv_gate.py", "-q",
         "--tb=short"],
        cwd=str(PROJECT_DIR),
        capture_output=True, text=True,
        timeout=180,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    tail = "\n".join((stdout + stderr).splitlines()[-25:])
    return {
        "returncode":   proc.returncode,
        "passed":       proc.returncode == 0,
        "tail":         tail,
    }


def _replay_r8_m22() -> dict:
    """Replay R8_M22's historical result through the new gate as a legacy probe.

    R8_M22 is a band-sharpening probe -- it failed its OWN ship gate
    (ship_gate_passed=False in the result JSON). When the improve_loop
    scaffold runs probes like this, MAE adjudication produces REJECT.
    Our CLV gate must be a strict passthrough here (no clv_metrics ->
    "CLV unavailable -- legacy probe" -> True -> composition returns
    whatever the MAE verdict says).

    We test: simulating a legacy-style call (no clv_metrics), the gate must
    return True with the legacy reason, and compose_with_mae(False, _, True, _,
    "model") must still return False (preserving the historical REJECT).
    """
    # Load historical result for context (but probe doesn't carry clv_metrics).
    try:
        hist = json.loads(R8_M22_RESULTS.read_text(encoding="utf-8"))
    except Exception:
        hist = {}
    historical_ship = bool(hist.get("summary", {}).get("ship_gate_passed", False))

    # Step 1: CLV gate on a probe-results dict with NO clv_metrics.
    clv_ok, clv_reason = check_clv_gate({}, change_type="model")
    legacy_pass = (clv_ok is True
                    and ("legacy" in clv_reason.lower()
                         or "unavailable" in clv_reason.lower()))

    # Step 2: Compose the historical MAE verdict (REJECT) with the CLV passthrough.
    # R8_M22 failed MAE (ship=False) -> composition must still be False.
    final_ship_after_gate, final_reason = compose_with_mae(
        mae_passed=historical_ship,  # historically False
        mae_reason="historical MAE verdict",
        clv_passed=clv_ok,
        clv_reason=clv_reason,
        change_type="model",
    )
    regression_ok = (final_ship_after_gate == historical_ship)

    return {
        "historical_mae_ship":   historical_ship,
        "clv_legacy_passthrough": legacy_pass,
        "clv_reason":            clv_reason,
        "post_gate_ship":        final_ship_after_gate,
        "post_gate_reason":      final_reason,
        "regression_passed":     bool(regression_ok and legacy_pass),
    }


def _synthetic_scenarios() -> dict:
    """Spot-check a few representative gate paths beyond the R8 replay."""
    # Path A: a hypothetical R9+ model probe with strong CLV metrics + MAE win.
    metrics_a = {
        "beat_rate": 0.56,
        "mean_pct":  0.014,
        "n_bets":    320,
        "wf_folds":  [0.012, 0.014, 0.010, 0.020],
    }
    a_ok, a_reason = check_clv_gate({"clv_metrics": metrics_a}, "model")
    a_ship, a_compose = compose_with_mae(True, "MAE ok", a_ok, a_reason, "model")

    # Path B: sizing_timing tweak that falls below the +1% floor -> REJECT.
    metrics_b = {
        "beat_rate": 0.58,
        "mean_pct":  0.004,
        "n_bets":    400,
        "wf_folds":  [0.004, 0.005, 0.003, 0.006],
    }
    b_ok, b_reason = check_clv_gate({"clv_metrics": metrics_b}, "sizing_timing")
    b_ship, b_compose = compose_with_mae(True, "MAE bypassed", b_ok, b_reason,
                                          "sizing_timing")

    return {
        "model_strong_clv_path": {
            "clv_ok":    a_ok,
            "ship":      a_ship,
            "reason":    a_compose,
        },
        "sizing_weak_clv_path": {
            "clv_ok":    b_ok,
            "ship":      b_ship,
            "reason":    b_compose,
        },
    }


def run_probe() -> dict:
    print("=== R9_C8 CLV ship-gate probe ===", flush=True)
    print("[1/3] running unit tests...", flush=True)
    tests = _run_unit_tests()
    print(tests["tail"], flush=True)
    print(f"  tests passed: {tests['passed']}", flush=True)

    print("\n[2/3] replaying R8_M22 through new gate...", flush=True)
    regression = _replay_r8_m22()
    print(f"  historical MAE ship:    {regression['historical_mae_ship']}")
    print(f"  CLV legacy passthrough: {regression['clv_legacy_passthrough']}")
    print(f"  CLV reason:             {regression['clv_reason']}")
    print(f"  post-gate ship:         {regression['post_gate_ship']}")
    print(f"  regression OK:          {regression['regression_passed']}", flush=True)

    print("\n[3/3] spot-checking synthetic gate paths...", flush=True)
    synthetic = _synthetic_scenarios()
    for k, v in synthetic.items():
        print(f"  {k}: ship={v['ship']} clv_ok={v['clv_ok']}")

    files_modified = [
        "scripts/improve_loop/clv_gate.py",
        "scripts/improve_loop/scaffold.py",  # wired 5-line gate call
        "scripts/clv_weekly_report.py",
        "tests/test_clv_gate.py",
        "scripts/probe_R9_C8_clv_ship_gate.py",
    ]

    overall_ship = tests["passed"] and regression["regression_passed"]
    ship_reason = (
        "SHIP: 5+ unit tests pass + R8_M22 regression preserved"
        if overall_ship else
        f"REJECT: tests_passed={tests['passed']} regression_passed={regression['regression_passed']}"
    )

    result = {
        "probe":                       "R9_C8_clv_ship_gate",
        "status":                      "SHIP" if overall_ship else "REJECT",
        "tests_passed":                tests["passed"],
        "tests_returncode":            tests["returncode"],
        "integration_regression_passed": regression["regression_passed"],
        "files_modified":              files_modified,
        "ship_reason":                 ship_reason,
        "regression_detail":           regression,
        "synthetic_scenarios":         synthetic,
        "tests_tail":                  tests["tail"],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nResults -> {OUTPUT_PATH}")
    print(f"FINAL: {result['status']} ({ship_reason})", flush=True)
    return result


if __name__ == "__main__":
    run_probe()
