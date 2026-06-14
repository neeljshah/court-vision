"""domains.mlb.asof_park_eval — Validation CLI for the park factor module.

Compares two total-runs predictors on the real corpus:
  baseline  — leak-free expanding LEAGUE mean total runs (park-agnostic)
  adjusted  — baseline * park_factor (park-adjusted)

Prints RMSE and MAE before/after.

HONEST FRAMING:
  This measures accuracy/calibration only.  Markets remain efficient; NO edge
  is claimed.  The scout measured ~-1.1% RMSE improvement from the park factor.

Usage:
    python -m domains.mlb.asof_park_eval [--games PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from domains.mlb.asof_park import build_park_features, PARK_MIN_GAMES
from domains.mlb.config import GAMES_PARQUET

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _rmse(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - pred) ** 2)))


def _mae(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - pred)))


def run_eval(
    games_path: Optional[str] = None,
    out_path: Optional[str] = None,
    min_games: int = PARK_MIN_GAMES,
) -> dict:
    """Run the validation and return a results dict.

    Builds park features in-memory (no side-effect parquet write by default).
    Returns dict with keys: n, rmse_base, rmse_adj, mae_base, mae_adj,
                            rmse_delta_pct, mae_delta_pct, park_corr.
    """
    games_p = games_path or str(_REPO_ROOT / GAMES_PARQUET)
    gf = pd.read_parquet(games_p)

    # Build park features (writes to out_path or default; we use a temp path
    # if out_path is None to avoid polluting the data dir during pure eval).
    import tempfile, os
    tmp = tempfile.mktemp(suffix=".parquet") if out_path is None else out_path
    try:
        built_path = build_park_features(games=gf, out_path=tmp, min_games=min_games)
        pf = pd.read_parquet(str(built_path))
    finally:
        if out_path is None and os.path.exists(tmp):
            os.remove(tmp)

    # Merge on event_id; keep only rows with non-NaN park_factor
    gf["total_runs"] = gf["home_runs"] + gf["away_runs"]
    merged = gf[["event_id", "total_runs"]].merge(pf, on="event_id", how="inner")

    # Build leak-free expanding league mean (snapshot-before-update) on merged
    # (already in chronological order because build_park_features sorted it).
    running_sum = 0.0
    running_n = 0
    league_means = []
    for total in merged["total_runs"].values:
        if running_n >= min_games:
            league_means.append(running_sum / running_n)
        else:
            league_means.append(float("nan"))
        running_sum += total
        running_n += 1
    merged["league_mean_asof"] = league_means

    # Rows where both baseline and park_factor are valid
    mask = (
        merged["park_factor"].notna()
        & merged["league_mean_asof"].notna()
    )
    ev = merged[mask].copy()
    n = len(ev)

    actual = ev["total_runs"].values.astype(float)
    baseline_pred = ev["league_mean_asof"].values.astype(float)
    adj_pred = baseline_pred * ev["park_factor"].values.astype(float)

    rmse_base = _rmse(actual, baseline_pred)
    rmse_adj = _rmse(actual, adj_pred)
    mae_base = _mae(actual, baseline_pred)
    mae_adj = _mae(actual, adj_pred)
    rmse_delta_pct = (rmse_adj - rmse_base) / rmse_base * 100.0
    mae_delta_pct = (mae_adj - mae_base) / mae_base * 100.0
    park_corr = float(np.corrcoef(ev["park_factor"].values, actual)[0, 1])

    return {
        "n": n,
        "rmse_base": rmse_base,
        "rmse_adj": rmse_adj,
        "mae_base": mae_base,
        "mae_adj": mae_adj,
        "rmse_delta_pct": rmse_delta_pct,
        "mae_delta_pct": mae_delta_pct,
        "park_corr": park_corr,
    }


def main() -> None:
    """CLI: python -m domains.mlb.asof_park_eval [--games PATH] [--out PATH]"""
    ap = argparse.ArgumentParser(
        description="Validate MLB park factor: RMSE before/after on real corpus"
    )
    ap.add_argument("--games", default=None, help="override games.parquet path")
    ap.add_argument(
        "--out", default=None, help="save park parquet to this path instead of temp"
    )
    ap.add_argument(
        "--min-games", type=int, default=PARK_MIN_GAMES,
        help=f"min prior home games before non-NaN (default {PARK_MIN_GAMES})"
    )
    args = ap.parse_args()

    res = run_eval(games_path=args.games, out_path=args.out, min_games=args.min_games)

    print("=" * 60)
    print("MLB Park Factor — Validation")
    print(f"  Evaluable rows (both predictors valid): {res['n']:,}")
    print(f"  Park factor corr with actual total runs: {res['park_corr']:+.4f}")
    print()
    print("  Total-runs prediction comparison (lower = better):")
    print(f"    RMSE  baseline (league mean): {res['rmse_base']:.4f}")
    print(f"    RMSE  park-adjusted:          {res['rmse_adj']:.4f}  "
          f"({res['rmse_delta_pct']:+.2f}%)")
    print(f"    MAE   baseline (league mean): {res['mae_base']:.4f}")
    print(f"    MAE   park-adjusted:          {res['mae_adj']:.4f}  "
          f"({res['mae_delta_pct']:+.2f}%)")
    print()
    print("  HONEST VERDICT: accuracy/calibration lever only.")
    print("  Markets remain efficient; NO edge is claimed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
