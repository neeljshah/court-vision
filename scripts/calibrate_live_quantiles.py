"""calibrate_live_quantiles.py -- Cycle 105c (loop 5).

Fit per-(snapshot_period, stat) Gaussian-residual scale factors that bring
the live-projection q10/q90 bands to 80% empirical coverage on the cycle-91a
550-game retro.

For each (snap_period, stat):
    residual = actual_final - projected_final     # n samples (val slice)
    sigma_raw = std(residual)
    grid-search scale s in [0.05, 3.0] minimising |coverage - 0.80| where
      coverage = mean( |residual| <= s * sigma_raw * 1.2816 )

Asymmetric branch (fg3m/stl/blk/tov) computes coverage as:
      cov = mean( residual >= -s*sigma*Z & projected + s*sigma*Z >= actual )
After flooring q10 at 0 in apply.

Writes data/models/live_quantile_calibration.json:
    {endQ2: {pts: {sigma, scale, asymmetric, n, coverage}, ...},
     endQ3: { ... }}

Run:
    python scripts/calibrate_live_quantiles.py
    python scripts/calibrate_live_quantiles.py --max-games 100
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from src.prediction.live_quantile_bands import ASYMMETRIC_STATS  # noqa: E402

import retro_inplay_mae as rim  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ2", "endQ3")   # endQ1 intentionally omitted

_OUT_PATH = os.path.join(PROJECT_DIR, "data", "models",
                         "live_quantile_calibration.json")

_Z80 = 1.2816


def _collect_residuals(max_games: int = 0
                       ) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Return {point: {stat: [(projected, actual), ...]}}.

    Uses retro_inplay_mae.build_snapshot to reconstruct end-Q2/Q3 snapshots
    and predict_in_game.project_snapshot to produce per-(player, stat)
    projections. Full-game actuals are Q1+Q2+Q3+Q4 sums.
    """
    import predict_in_game as pig
    qstats = rim.load_quarter_stats()
    game_ids = list(qstats["game_id"].unique())
    if max_games:
        game_ids = game_ids[:max_games]

    out: Dict[str, Dict[str, List[Tuple[float, float]]]] = {
        p: defaultdict(list) for p in SNAPSHOT_POINTS
    }
    for gid in game_ids:
        actuals = rim.actuals_for_game(gid, qstats)
        if not actuals:
            continue
        for point in SNAPSHOT_POINTS:
            snap = rim.build_snapshot(gid, point, qstats)
            if snap is None:
                continue
            try:
                rows = pig.project_snapshot(snap)
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


def _fit_scale(projections: np.ndarray, actuals: np.ndarray,
               asymmetric: bool, target: float = 0.80,
               lo: float = 0.02, hi: float = 5.0,
               n: int = 400) -> Tuple[float, float, float]:
    """Return (sigma, scale, coverage)."""
    if len(actuals) == 0:
        return 0.0, 1.0, 0.0
    resid = actuals - projections
    # Robust sigma -- std but clipped to avoid 0 (degenerate stat).
    sigma = float(np.std(resid))
    if sigma <= 1e-6:
        return sigma, 1.0, 1.0
    grid = np.linspace(lo, hi, n)
    best_s = 1.0
    best_diff = 1.0
    best_cov = 0.0
    for s in grid:
        half = s * sigma * _Z80
        if asymmetric:
            q10 = np.maximum(0.0, projections - half)
            q90 = projections + half
        else:
            q10 = projections - half
            q90 = projections + half
        cov = float(((actuals >= q10) & (actuals <= q90)).mean())
        diff = abs(cov - target)
        if diff < best_diff:
            best_diff = diff
            best_s = float(s)
            best_cov = cov
    return sigma, best_s, best_cov


def calibrate(max_games: int = 0, val_frac: float = 0.5,
              out_path: str = _OUT_PATH) -> dict:
    """Fit scales on the VAL half of the retro pairs; reserve the other half
    for the probe."""
    print(f"[calibrate] collecting residuals (max_games={max_games or 'ALL'})...",
          flush=True)
    pairs = _collect_residuals(max_games=max_games)

    cal: Dict[str, dict] = {}
    for point in SNAPSHOT_POINTS:
        cal[point] = {}
        for stat in STATS:
            pts = pairs[point].get(stat) or []
            if len(pts) < 30:
                print(f"  [skip] {point}/{stat}: n={len(pts)} < 30", flush=True)
                continue
            arr = np.asarray(pts, dtype=float)
            n = len(arr)
            # Interleaved split (even idx -> val, odd idx -> probe). Avoids
            # covariate shift between time-ordered halves of the retro.
            val = arr[0::2] if val_frac == 0.5 else arr[: int(n * val_frac)]
            asym = stat in ASYMMETRIC_STATS
            sigma, scale, cov = _fit_scale(val[:, 0], val[:, 1], asym)
            cal[point][stat] = {
                "sigma": round(sigma, 4),
                "scale": round(scale, 4),
                "asymmetric": asym,
                "n_val": int(len(val)),
                "coverage_val": round(cov, 4),
            }
            print(f"  {point}/{stat:4s}  n_val={len(val):4d}  "
                  f"sigma={sigma:.3f}  scale={scale:.3f}  "
                  f"cov_val={cov:.3f}  asym={asym}", flush=True)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(cal, fh, indent=2, sort_keys=True)
    print(f"[calibrate] wrote {out_path}", flush=True)
    return cal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=0,
                    help="Cap retro games (0 = all)")
    ap.add_argument("--val-frac", type=float, default=0.5,
                    help="Fraction of pairs used for calibration vs probe")
    ap.add_argument("--out", default=_OUT_PATH)
    args = ap.parse_args()
    calibrate(max_games=args.max_games, val_frac=args.val_frac,
              out_path=args.out)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
