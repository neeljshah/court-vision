"""scripts/improve_loop/probe_R23_P4_pin_latency.py -- R23_P4 latency probe.

Diagnoses the Pinnacle scraper p99 regression (L6: 886ms -> 2389ms, +170%)
by measuring cold-vs-warm `_http_get_json` latency against the live
guest.api.arcadia.pinnacle.com endpoint.

Cold path  : each call uses a fresh Session (mimics the pre-R23_P4 code,
             which built a new curl_cffi request per call).
Warm path  : Session is reused (new post-R23_P4 behaviour).

If Pinnacle is unreachable from this host (firewall / DNS / etc.) the
probe skips cleanly with a diagnostic, never crashing.

Output: data/cache/probe_R23_P4_results.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import pinnacle_scraper as ps  # noqa: E402


_RESULTS_PATH = os.path.join(PROJECT_DIR, "data", "cache", "probe_R23_P4_results.json")
_TARGET_URL = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/487/matchups"
_N_CALLS = 30


# ── helpers ───────────────────────────────────────────────────────────────────

def _percentile(values: List[float], pct: float) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    return s[min(n - 1, int(round(pct / 100.0 * (n - 1))))]


def _percentiles(values: List[float]) -> Dict[str, float]:
    return {
        "n": len(values),
        "min_ms": round(min(values), 2) if values else 0.0,
        "p50_ms": round(_percentile(values, 50), 2),
        "p95_ms": round(_percentile(values, 95), 2),
        "p99_ms": round(_percentile(values, 99), 2),
        "max_ms": round(max(values), 2) if values else 0.0,
        "mean_ms": round(sum(values) / len(values), 2) if values else 0.0,
    }


def _probe_reachable() -> Tuple[bool, str]:
    """Single GET to verify endpoint reachability without committing to a
    full measurement loop."""
    try:
        ps._reset_sessions()
        code, _ = ps._http_get_json(_TARGET_URL, timeout=8.0)
        ps._reset_sessions()
        if code == 200:
            return True, ""
        return False, f"endpoint returned status {code}"
    except Exception as e:                                          # noqa: BLE001
        return False, f"exception: {e!r}"


# ── core measurement ──────────────────────────────────────────────────────────

def measure_cold(n: int = _N_CALLS) -> Dict[str, Any]:
    """Each call resets the session -- mimics the pre-R23_P4 per-call build."""
    timings: List[float] = []
    errors = 0
    for _ in range(n):
        ps._reset_sessions()  # force fresh TLS / connection
        t = time.perf_counter()
        code, _ = ps._http_get_json(_TARGET_URL, timeout=15.0)
        dt = (time.perf_counter() - t) * 1000.0
        if code != 200:
            errors += 1
        timings.append(dt)
    out = _percentiles(timings)
    out["errors"] = errors
    out["mode"] = "cold (no session reuse)"
    return out


def measure_warm(n: int = _N_CALLS) -> Dict[str, Any]:
    """One initial warmup, then N calls share the cached session."""
    ps._reset_sessions()
    # Warmup (cost is reported separately so it doesn't dominate p99).
    t = time.perf_counter()
    code, _ = ps._http_get_json(_TARGET_URL, timeout=15.0)
    warmup_ms = (time.perf_counter() - t) * 1000.0
    warmup_err = 0 if code == 200 else 1

    timings: List[float] = []
    errors = 0
    for _ in range(n):
        t = time.perf_counter()
        code, _ = ps._http_get_json(_TARGET_URL, timeout=15.0)
        dt = (time.perf_counter() - t) * 1000.0
        if code != 200:
            errors += 1
        timings.append(dt)
    out = _percentiles(timings)
    out["errors"] = errors
    out["warmup_ms"] = round(warmup_ms, 2)
    out["warmup_error"] = warmup_err
    out["mode"] = "warm (persistent session)"
    return out


# ── orchestrator ──────────────────────────────────────────────────────────────

def run() -> Dict[str, Any]:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    reachable, reason = _probe_reachable()
    result: Dict[str, Any] = {
        "probe": "R23_P4_pin_latency",
        "started_at": started_at,
        "target_url": _TARGET_URL,
        "n_calls_per_mode": _N_CALLS,
        "reachable": reachable,
        "reason": reason,
    }

    if not reachable:
        result["status"] = "BLOCKED"
        result["note"] = ("Pinnacle endpoint unreachable from this host; "
                          "cannot measure live latency. "
                          "Synthetic-mock tests in tests/test_R23_P4_pin_scraper_latency.py "
                          "still guard the code path.")
    else:
        cold = measure_cold()
        warm = measure_warm()
        delta_p99 = cold["p99_ms"] - warm["p99_ms"]
        pct_p99 = (delta_p99 / cold["p99_ms"] * 100.0) if cold["p99_ms"] > 0 else 0.0
        delta_p50 = cold["p50_ms"] - warm["p50_ms"]
        pct_p50 = (delta_p50 / cold["p50_ms"] * 100.0) if cold["p50_ms"] > 0 else 0.0
        result["cold"] = cold
        result["warm"] = warm
        result["improvement"] = {
            "p50_delta_ms": round(delta_p50, 2),
            "p50_pct_reduction": round(pct_p50, 1),
            "p99_delta_ms": round(delta_p99, 2),
            "p99_pct_reduction": round(pct_p99, 1),
        }
        # SHIP if p99 reduced by >=30% (the R23_P4 ship gate).
        result["status"] = "SHIP" if pct_p99 >= 30.0 else "REJECT"

    os.makedirs(os.path.dirname(_RESULTS_PATH), exist_ok=True)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


def main() -> int:
    result = run()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
