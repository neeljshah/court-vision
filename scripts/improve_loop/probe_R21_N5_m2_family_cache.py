"""
probe_R21_N5_m2_family_cache.py — Benchmark the m2_family prediction cache.

Cold path: feature build + 20 model `.predict` calls (~10-15ms / call).
Warm path: JSON cache read keyed by (game_id, models_mtime) (~sub-ms).

Outputs:
  data/cache/probe_R21_N5_results.json — cold/warm ms means + speedup.

Usage:
  python scripts/improve_loop/probe_R21_N5_m2_family_cache.py
  python scripts/improve_loop/probe_R21_N5_m2_family_cache.py --clear-cache
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

# Suppress sklearn feature-name UserWarnings — known LGBM/sklearn version
# quirk, not relevant to the benchmark.
warnings.filterwarnings("ignore", category=UserWarning)

from src.prediction import game_models  # noqa: E402


_RESULTS_PATH = os.path.join(PROJECT_DIR, "data", "cache", "probe_R21_N5_results.json")
_N_GAMES = 5
_REPS = 3   # repeat each timing this many times and take the mean


def _pick_real_game_ids(n: int = _N_GAMES) -> List[dict]:
    """Pull n featured rows from any available season_games_*.json."""
    out: List[dict] = []
    for fn in ("season_games_2024-25.json", "season_games_2025-26.json",
               "season_games_2023-24.json", "season_games_2022-23.json"):
        p = os.path.join(PROJECT_DIR, "data", "nba", fn)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        rows = d.get("rows", d) if isinstance(d, dict) else d
        for r in rows:
            if (isinstance(r, dict)
                    and "home_off_rtg" in r
                    and r.get("game_id")
                    and r["game_id"] not in {x["game_id"] for x in out}):
                out.append(r)
                if len(out) >= n:
                    return out
        if len(out) >= n:
            return out
    return out


def _time_call(row: dict, reps: int) -> float:
    """Mean ms over `reps` `_predict_m2_family` calls for a single row."""
    ts: List[float] = []
    for _ in range(reps):
        t0 = time.perf_counter()
        out = game_models._predict_m2_family(row, game_id=row.get("game_id"))
        dt = (time.perf_counter() - t0) * 1000.0
        if out is None:
            return float("nan")
        ts.append(dt)
    return sum(ts) / len(ts)


def run_bench() -> Optional[dict]:
    if not game_models._try_load_m2_family():
        print("[R21_N5] m2_family artifacts not present — abort bench.", flush=True)
        return None

    rows = _pick_real_game_ids(_N_GAMES)
    if not rows:
        print("[R21_N5] no featured season_games rows available — abort bench.", flush=True)
        return None
    print(f"[R21_N5] benching {len(rows)} games x {_REPS} reps each", flush=True)

    # Cold: wipe cache then time each game once-from-scratch.
    game_models.clear_m2_pred_cache()
    cold_ms: List[float] = []
    for r in rows:
        # Wipe before each so every measurement is truly cold for that gid.
        game_models.clear_m2_pred_cache()
        t0 = time.perf_counter()
        out = game_models._predict_m2_family(r, game_id=r.get("game_id"))
        dt = (time.perf_counter() - t0) * 1000.0
        if out is None:
            print(f"[R21_N5] cold miss returned None for {r.get('game_id')}", flush=True)
            continue
        cold_ms.append(dt)
        print(f"[R21_N5]   cold  {r['game_id']}: {dt:.2f} ms  {out}", flush=True)

    # Re-seed cache by running each game once, then time warm reads.
    for r in rows:
        game_models._predict_m2_family(r, game_id=r.get("game_id"))

    warm_ms: List[float] = []
    for r in rows:
        ms = _time_call(r, reps=_REPS)
        warm_ms.append(ms)
        print(f"[R21_N5]   warm  {r['game_id']}: {ms:.4f} ms", flush=True)

    cold_mean = sum(cold_ms) / len(cold_ms) if cold_ms else float("nan")
    warm_mean = sum(warm_ms) / len(warm_ms) if warm_ms else float("nan")
    speedup = (cold_mean / warm_mean) if warm_mean and warm_mean > 0 else float("inf")

    res = {
        "probe":         "R21_N5",
        "n_games":       len(rows),
        "reps_per_warm": _REPS,
        "game_ids":      [r["game_id"] for r in rows],
        "cold_ms_mean":  round(cold_mean, 4),
        "warm_ms_mean":  round(warm_mean, 4),
        "speedup":       round(speedup, 2),
        "ship_gate_10x": speedup >= 10.0,
        "computed_at":   datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(_RESULTS_PATH), exist_ok=True)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(f"\n[R21_N5] cold_ms_mean = {res['cold_ms_mean']}", flush=True)
    print(f"[R21_N5] warm_ms_mean = {res['warm_ms_mean']}", flush=True)
    print(f"[R21_N5] speedup      = {res['speedup']}x  (gate >=10x: {res['ship_gate_10x']})", flush=True)
    print(f"[R21_N5] wrote        -> {_RESULTS_PATH}", flush=True)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clear-cache", action="store_true",
                    help="Delete the m2_family predictions cache file and exit.")
    ap.add_argument("--no-bench", action="store_true",
                    help="Skip the benchmark (only useful with --clear-cache).")
    args = ap.parse_args()

    if args.clear_cache:
        removed = game_models.clear_m2_pred_cache()
        print(f"[R21_N5] clear-cache: removed={removed}", flush=True)
        if args.no_bench:
            return 0

    run_bench()
    return 0


if __name__ == "__main__":
    sys.exit(main())
