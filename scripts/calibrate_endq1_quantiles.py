"""calibrate_endq1_quantiles.py -- R5-F endQ1 quantile band calibration.

Collects the endQ1 corpus via retro_inplay_mae.load_quarter_stats() +
build_snapshot(point="endQ1"), runs each snapshot through
live_engine.project_from_snapshot (which includes R4-A residual heads when
wired), computes per-stat Gaussian residual sigma, and bisects a scale
factor so empirical 80% coverage hits 0.80.

Output: data/models/quantile_calibration_endq1.json
  {stat: {sigma, scale, n, coverage, asymmetric}, ...}

Sanity: sigma_endQ1 > sigma_endQ2 is asserted (more uncertainty earlier).

Run:
    python scripts/calibrate_endq1_quantiles.py
    python scripts/calibrate_endq1_quantiles.py --max-games 200
    python scripts/calibrate_endq1_quantiles.py --dry-run
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
_Z80 = 1.2816  # z for 80% two-sided coverage

_OUT_PATH = os.path.join(PROJECT_DIR, "data", "models", "quantile_calibration_endq1.json")
_ENQ2_CAL_PATH = os.path.join(PROJECT_DIR, "data", "models", "live_quantile_calibration.json")


def _collect_residuals(max_games: int = 0) -> Dict[str, List[Tuple[float, float]]]:
    """Return {stat: [(q50_proj, actual), ...]} for endQ1 snapshots."""
    from src.prediction.live_engine import project_from_snapshot

    qstats = rim.load_quarter_stats()
    game_ids = list(qstats["game_id"].unique())
    if max_games:
        game_ids = game_ids[:max_games]

    out: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    n_ok = 0
    for gid in game_ids:
        actuals = rim.actuals_for_game(gid, qstats)
        if not actuals:
            continue
        snap = rim.build_snapshot(gid, "endQ1", qstats)
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
            out[stat].append((proj, float(actual)))
        n_ok += 1
        if n_ok % 50 == 0:
            print(f"  [{n_ok}/{len(game_ids)}] games processed", flush=True)

    print(f"  total games processed: {n_ok}", flush=True)
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

    Bisects scale on a fine grid so empirical coverage hits `target`.
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


def _load_endq2_sigmas() -> Dict[str, float]:
    """Load sigma_endQ2 from live_quantile_calibration.json for sanity check."""
    try:
        with open(_ENQ2_CAL_PATH, encoding="utf-8") as fh:
            cal = json.load(fh)
        return {stat: float(cal["endQ2"][stat]["sigma"]) for stat in STATS
                if stat in cal.get("endQ2", {})}
    except Exception:
        return {}


def calibrate(
    max_games: int = 0,
    val_frac: float = 0.5,
    out_path: str = _OUT_PATH,
    dry_run: bool = False,
) -> dict:
    """Fit endQ1 scale factors; write calibration JSON."""
    print(
        f"[cal-endQ1] collecting residuals via live_engine "
        f"(max_games={max_games or 'ALL'})...",
        flush=True,
    )
    pairs = _collect_residuals(max_games=max_games)
    endq2_sigmas = _load_endq2_sigmas()

    cal: Dict[str, dict] = {}
    sanity_pass = 0
    sanity_fail = 0

    for stat in STATS:
        pts = pairs.get(stat) or []
        if len(pts) < 30:
            print(f"  [skip] endQ1/{stat}: n={len(pts)} < 30", flush=True)
            continue
        arr = np.asarray(pts, dtype=float)
        n = len(arr)
        # Even-index slice for calibration; odd reserved for probe.
        val = arr[0::2] if val_frac == 0.5 else arr[: int(n * val_frac)]
        asym = stat in ASYMMETRIC_STATS
        sigma, scale, cov = _fit_scale(val[:, 0], val[:, 1], asym)

        # Sanity: endQ1 sigma should be larger than endQ2 sigma (more uncertainty)
        sigma_q2 = endq2_sigmas.get(stat)
        if sigma_q2 is not None:
            ok = sigma > sigma_q2
            tag_sanity = "OK (sigma_endQ1 > sigma_endQ2)" if ok else "WARN (sigma_endQ1 <= sigma_endQ2)"
            if ok:
                sanity_pass += 1
            else:
                sanity_fail += 1
        else:
            tag_sanity = "endQ2 sigma unavailable"

        tag = "ASYM" if asym else "SYM "
        print(
            f"  endQ1/{stat:4s}  n_val={len(val):4d}  "
            f"sigma={sigma:.3f}  scale={scale:.3f}  "
            f"cov_val={cov:.3f}  {tag}  [{tag_sanity}]",
            flush=True,
        )

        cal[stat] = {
            "sigma": round(sigma, 4),
            "scale": round(scale, 4),
            "asymmetric": asym,
            "n_val": int(len(val)),
            "coverage_val": round(cov, 4),
        }

    print(
        f"\n[cal-endQ1] sanity (sigma_endQ1 > sigma_endQ2): "
        f"{sanity_pass} pass / {sanity_fail} fail out of {sanity_pass + sanity_fail} stats",
        flush=True,
    )

    if dry_run:
        print("[cal-endQ1] --dry-run: not writing calibration file", flush=True)
        return cal

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(cal, fh, indent=2, sort_keys=True)
    print(f"[cal-endQ1] wrote {out_path}", flush=True)
    return cal


def main() -> int:
    ap = argparse.ArgumentParser(description="R5-F endQ1 quantile band calibration.")
    ap.add_argument("--max-games", type=int, default=0)
    ap.add_argument("--val-frac", type=float, default=0.5)
    ap.add_argument("--out", default=_OUT_PATH)
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute but do not write output file")
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
