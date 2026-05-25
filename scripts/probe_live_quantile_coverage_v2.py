"""probe_live_quantile_coverage_v2.py -- Cycle 107a (loop 5).

Validates calibrated live quantile bands against LIVE ENGINE projections
(period-specific heads + stratified residuals) rather than cycle-88 linear
extrapolation used by probe_live_quantile_coverage.py (v1).

WHY: calibrate_live_quantiles_v2.py fitted sigma/scale against
live_engine.project_from_snapshot.  The v1 probe used
predict_in_game.project_snapshot (linear), so the probe and calibrator
were mismatched.  This script uses the same projection source as the
calibrator so coverage estimates are valid.

Ship gate: >=5/7 stats per snapshot_point in [0.75, 0.85].

Run:
    python scripts/probe_live_quantile_coverage_v2.py
    python scripts/probe_live_quantile_coverage_v2.py --max-games 200
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from src.prediction.live_quantile_bands import (  # noqa: E402
    bands_for, load_calibration, reset_cache,
)
from src.prediction.live_engine import project_from_snapshot  # noqa: E402
import retro_inplay_mae as rim  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ2", "endQ3")
_COVERAGE_LO = 0.75
_COVERAGE_HI = 0.85
_SHIP_MIN_OK = 5


def _collect_pairs(max_games: int = 0) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Collect (projected_final, actual) pairs using live_engine projections."""
    from collections import defaultdict

    qstats = rim.load_quarter_stats()
    game_ids = list(qstats["game_id"].unique())
    if max_games:
        game_ids = game_ids[:max_games]

    out: Dict = {p: defaultdict(list) for p in SNAPSHOT_POINTS}
    for gid in game_ids:
        actuals = rim.actuals_for_game(gid, qstats)
        if not actuals:
            continue
        for point in SNAPSHOT_POINTS:
            snap = rim.build_snapshot(gid, point, qstats)
            if snap is None:
                continue
            try:
                rows = project_from_snapshot(snap)
            except Exception:
                continue
            for r in rows:
                pid = r.get("player_id")
                stat = r.get("stat")
                if pid is None or stat not in STATS:
                    continue
                try:
                    proj = float(r.get("projected_final", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                actual = actuals.get((int(pid), stat))
                if actual is None:
                    continue
                out[point][stat].append((proj, float(actual)))
    return out


def probe(max_games: int = 0, val_frac: float = 0.5) -> dict:
    reset_cache()
    cal = load_calibration()
    if not cal:
        print("[fail] no calibration — run calibrate_live_quantiles_v2.py first")
        return {}

    print(f"[probe-v2] collecting pairs via live_engine "
          f"(max_games={max_games or 'ALL'})...", flush=True)
    pairs = _collect_pairs(max_games=max_games)

    results: dict = {}
    for point in SNAPSHOT_POINTS:
        results[point] = {}
        n_ok = 0
        for stat in STATS:
            pts = pairs[point].get(stat) or []
            if len(pts) < 30:
                print(f"  [skip] {point}/{stat}: n={len(pts)}", flush=True)
                continue
            arr = np.asarray(pts, dtype=float)
            n = len(arr)
            # Odd-index slice (probe half, matching calibrator's even-index val split).
            held = arr[1::2] if val_frac == 0.5 else arr[int(n * val_frac):]
            if len(held) == 0:
                continue
            covered = 0
            for proj, actual in held:
                b = bands_for(stat, proj, point, calibration=cal)
                if b["q10"] <= actual <= b["q90"]:
                    covered += 1
            cov = covered / len(held)
            ok = _COVERAGE_LO <= cov <= _COVERAGE_HI
            if ok:
                n_ok += 1
            results[point][stat] = {"n_held": len(held), "coverage": round(cov, 4), "ok": ok}
            print(f"  {point}/{stat:4s}  n={len(held):4d}  "
                  f"cov={cov:.3f}  {'OK' if ok else 'OUT'}", flush=True)
        results[point]["_n_ok"] = n_ok
        results[point]["_ship"] = n_ok >= _SHIP_MIN_OK
        verdict = "SHIP" if n_ok >= _SHIP_MIN_OK else "REJECT"
        print(f"  {point}: {n_ok}/7 in [{_COVERAGE_LO}, {_COVERAGE_HI}] -- {verdict}",
              flush=True)

    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=0)
    ap.add_argument("--val-frac", type=float, default=0.5)
    args = ap.parse_args()
    import warnings
    warnings.filterwarnings("ignore")
    probe(max_games=args.max_games, val_frac=args.val_frac)
    return 0


if __name__ == "__main__":
    sys.exit(main())
