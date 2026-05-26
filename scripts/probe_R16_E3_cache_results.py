"""probe_R16_E3_cache_results.py — measure cache stats + latency for R16_E3.

Produces data/cache/probe_R16_E3_cache_results.json with the four metrics
the spec requires:

    cache_n_rows                — total rows in the parquet
    p50_lookup_ms               — median latency across 200 hot calls
    p99_lookup_ms               — 99th-percentile latency across 200 calls
    refresh_triggered_correctly — bool, smoke-tested via injury bump

Run:
    python scripts/probe_R16_E3_cache_results.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date as _date

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Bypass live scraping for the probe — we want pure cache-lookup latency.
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")


def main() -> None:
    from scripts import serve_prediction as sp

    sp.reset_for_tests()
    sp.refresh(force=True)
    stats = sp.cache_stats()

    cache_path = stats.get("cache_path")
    n_rows = int(stats.get("n_rows", 0))
    if not cache_path or n_rows == 0:
        out = {
            "cache_n_rows": 0,
            "p50_lookup_ms": None,
            "p99_lookup_ms": None,
            "refresh_triggered_correctly": False,
            "error": "no cache available — run build_prediction_cache.py first",
            "computed_at": stats.get("computed_at"),
        }
        out_path = os.path.join(PROJECT_DIR, "data", "cache",
                                "probe_R16_E3_cache_results.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=str)
        print(json.dumps(out, indent=2, default=str))
        return

    # Build the candidate list of (player_id, stat) keys.
    df = pd.read_parquet(cache_path)
    pids = df["player_id"].astype(int).unique().tolist()
    stats_list = df["stat"].astype(str).unique().tolist()
    rng = np.random.default_rng(11)

    # Warmup — read 5 entries to settle any disk cache.
    for _ in range(5):
        pid = int(rng.choice(pids))
        sp.get_prediction(pid, "pts", apply_injury=True)

    # Hot loop — 200 calls.
    n = 200
    latencies_ms = []
    miss = 0
    for _ in range(n):
        pid = int(rng.choice(pids))
        stat = str(rng.choice(stats_list))
        t0 = time.perf_counter()
        rec = sp.get_prediction(pid, stat, apply_injury=True)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        if rec is None:
            miss += 1

    p50 = float(np.percentile(latencies_ms, 50))
    p99 = float(np.percentile(latencies_ms, 99))
    mean_ms = float(np.mean(latencies_ms))

    # Refresh-trigger smoke test — write a fresh injury file and verify
    # _needs_refresh reports it.
    cache_dir = os.path.join(PROJECT_DIR, "data", "cache")
    today = _date.today().isoformat()
    inj_path = os.path.join(cache_dir, f"injury_status_{today}.json")
    refresh_ok = False
    try:
        if os.path.exists(inj_path):
            # Bump mtime forward by 60s.
            future = time.time() + 60.0
            os.utime(inj_path, (future, future))
            need, reason = sp._needs_refresh()
            refresh_ok = bool(need and "injury" in reason)
    except Exception as exc:
        print(f"[probe] refresh check failed: {exc}")

    out = {
        "cache_n_rows":                n_rows,
        "n_players":                   int(stats.get("n_players", 0)),
        "p50_lookup_ms":               round(p50, 3),
        "p99_lookup_ms":               round(p99, 3),
        "mean_lookup_ms":              round(mean_ms, 3),
        "n_lookups":                   n,
        "misses":                      miss,
        "refresh_triggered_correctly": refresh_ok,
        "cache_path":                  cache_path,
        "computed_at":                 stats.get("computed_at"),
        "p99_gate_pass":               p99 < 100.0,
    }
    out_path = os.path.join(PROJECT_DIR, "data", "cache",
                            "probe_R16_E3_cache_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
