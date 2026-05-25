"""calibrate_live_quantiles_v2.py -- Cycle 107a (loop 5).

Re-calibrates per-(snapshot_period, stat) Gaussian-residual scale factors
against the CURRENT live engine projections (period_specific_heads + stratified
residual overrides) rather than the cycle-88 linear extrapolation used in v1.

WHY: The original calibrate_live_quantiles.py (cycle 105c) collected residuals
using predict_in_game.project_snapshot (linear extrapolation baseline).  Cycle
106a wired period-specific LightGBM heads at endQ1/endQ2 boundaries, reducing
PTS MAE at endQ2 from 4.09 → 3.46.  Smaller residuals → smaller sigma → the
old scale factors now produce bands that are too WIDE for PTS/AST/STL at endQ2
(observed coverage 0.88/0.88/0.91 vs target 0.80) and still too NARROW for BLK
(0.68).  Recalibrating against live_engine.project_from_snapshot fixes both.

Changes vs v1:
  * Uses src.prediction.live_engine.project_from_snapshot (all wired overrides)
    instead of predict_in_game.project_snapshot.
  * Output written to data/models/live_quantile_calibration.json (same path,
    replaces v1 artifact).
  * Probe re-run after calibration to confirm 5/7 endQ2 coverage.

Run:
    python scripts/calibrate_live_quantiles_v2.py
    python scripts/calibrate_live_quantiles_v2.py --max-games 200
    python scripts/calibrate_live_quantiles_v2.py --dry-run
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
SNAPSHOT_POINTS = ("endQ2", "endQ3")

_OUT_PATH = os.path.join(PROJECT_DIR, "data", "models", "live_quantile_calibration.json")
_Z80 = 1.2816  # z-score for 80% two-sided Gaussian coverage


def _collect_residuals_live_engine(
    max_games: int = 0,
) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    """Return {point: {stat: [(projected, actual), ...]}} using live_engine.

    Reconstructs end-Q2/Q3 snapshots from player_quarter_stats.parquet and
    runs them through live_engine.project_from_snapshot (which applies all
    wired overrides: period heads, foul/blowout/heat_check residuals).
    """
    from src.prediction.live_engine import project_from_snapshot

    qstats = rim.load_quarter_stats()
    game_ids = list(qstats["game_id"].unique())
    if max_games:
        game_ids = game_ids[:max_games]

    out: Dict[str, Dict[str, List[Tuple[float, float]]]] = {
        p: defaultdict(list) for p in SNAPSHOT_POINTS
    }
    n_ok = 0
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
        n_ok += 1
        if n_ok % 50 == 0:
            print(f"  [{n_ok}/{len(game_ids)}] games processed", flush=True)

    return out


def _fit_scale(
    projections: np.ndarray,
    actuals: np.ndarray,
    asymmetric: bool,
    target: float = 0.80,
    lo: float = 0.02,
    hi: float = 5.0,
    n_grid: int = 500,
) -> Tuple[float, float, float]:
    """Return (sigma, scale, achieved_coverage).

    Uses a finer grid (500 pts) vs v1 (400 pts) for tighter scale resolution.
    """
    if len(actuals) == 0:
        return 0.0, 1.0, 0.0
    resid = actuals - projections
    sigma = float(np.std(resid))
    if sigma <= 1e-6:
        return sigma, 1.0, 1.0
    grid = np.linspace(lo, hi, n_grid)
    best_s, best_diff, best_cov = 1.0, 1.0, 0.0
    for s in grid:
        half = s * sigma * _Z80
        q10 = np.maximum(0.0, projections - half) if asymmetric else projections - half
        q90 = projections + half
        cov = float(((actuals >= q10) & (actuals <= q90)).mean())
        diff = abs(cov - target)
        if diff < best_diff:
            best_diff, best_s, best_cov = diff, float(s), cov
    return sigma, best_s, best_cov


def calibrate(
    max_games: int = 0,
    val_frac: float = 0.5,
    out_path: str = _OUT_PATH,
    dry_run: bool = False,
) -> dict:
    """Fit scale factors on the VAL half; write calibration JSON."""
    print(
        f"[cal-v2] collecting residuals via live_engine "
        f"(max_games={max_games or 'ALL'})...",
        flush=True,
    )
    pairs = _collect_residuals_live_engine(max_games=max_games)

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
            # Even-index slice for calibration; odd-index reserved for probe.
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
            tag = "ASYM" if asym else "SYM "
            print(
                f"  {point}/{stat:4s}  n_val={len(val):4d}  "
                f"sigma={sigma:.3f}  scale={scale:.3f}  "
                f"cov_val={cov:.3f}  {tag}",
                flush=True,
            )

    if dry_run:
        print("[cal-v2] --dry-run: not writing calibration file", flush=True)
        return cal

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(cal, fh, indent=2, sort_keys=True)
    print(f"[cal-v2] wrote {out_path}", flush=True)
    return cal


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=0)
    ap.add_argument("--val-frac", type=float, default=0.5)
    ap.add_argument("--out", default=_OUT_PATH)
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute calibration but do not write output file")
    args = ap.parse_args()
    import warnings
    warnings.filterwarnings("ignore")
    calibrate(
        max_games=args.max_games,
        val_frac=args.val_frac,
        out_path=args.out,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
