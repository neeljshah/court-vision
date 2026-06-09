"""diag_pts_reb_residuals.py — WHERE do the PTS/REB OOF errors concentrate?

Aggregate MAE hides structure. This buckets the walk-forward OOF absolute error
by the things most likely to drive it, to target which signals to add:
  * minutes surprise   |actual_min - l10_min|  (minutes mis-projection)
  * actual minutes played (bench vs starter regime)
  * recent-form volatility (std of recent stat)
  * blowout proxy (we don't have final margin here -> use minutes surprise as proxy)

Reads pregame_oof.parquet + the same gamelogs the model trains on. 2025-26 only
(the eval window). No model touched; pure diagnosis.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import _load_gamelog_combined  # noqa: E402

OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"


def _rolling_before(rows, gdate, col, k=10):
    """mean of `col` over up to k games strictly before gdate."""
    hist = []
    for d, r in rows:
        if d.date() >= gdate.date():
            break
        v = r.get(col)
        try:
            hist.append(float(v))
        except (TypeError, ValueError):
            continue
    if not hist:
        return None
    return float(np.mean(hist[-k:]))


def main():
    df = pd.read_parquet(OOF)
    df = df[df["game_date"].astype(str) >= "2025-10-01"]
    df["abs_err"] = (df["oof_pred"] - df["actual"]).abs()
    glcache = {}

    for stat in ("pts", "reb"):
        sub = df[df["stat"] == stat].copy()
        recs = []
        for r in sub.itertuples(index=False):
            pid = int(r.player_id)
            if pid not in glcache:
                glcache[pid] = _load_gamelog_combined(pid)
            rows = glcache[pid]
            gdate = pd.to_datetime(r.game_date)
            actual_min = None
            for d, g in rows:
                if d.date() == gdate.date():
                    try:
                        actual_min = float(g.get("MIN"))
                    except (TypeError, ValueError):
                        actual_min = None
                    break
            if actual_min is None:
                continue
            l10_min = _rolling_before(rows, gdate, "MIN", 10)
            l10_std = _rolling_before(rows, gdate, stat.upper(), 10)
            recs.append({
                "abs_err": float(r.abs_err),
                "actual": float(r.actual),
                "pred": float(r.oof_pred),
                "actual_min": actual_min,
                "l10_min": l10_min,
                "min_surprise": abs(actual_min - l10_min) if l10_min is not None else None,
            })
        d2 = pd.DataFrame(recs)
        print("\n" + "=" * 64)
        print(f"{stat.upper()}  n={len(d2):,}  overall MAE={d2['abs_err'].mean():.3f}")
        print("=" * 64)

        # 1) error vs minutes surprise
        d2m = d2.dropna(subset=["min_surprise"])
        d2m["surprise_bucket"] = pd.cut(d2m["min_surprise"],
                                        [-0.1, 3, 6, 10, 15, 100],
                                        labels=["0-3", "3-6", "6-10", "10-15", "15+"])
        print("\n  MAE by |actual_min - l10_min| (minutes surprise):")
        g = d2m.groupby("surprise_bucket", observed=True)["abs_err"].agg(["mean", "count"])
        for b, row in g.iterrows():
            print(f"    {str(b):<7} MAE={row['mean']:.3f}  n={int(row['count']):,}")
        share_hi = (d2m["min_surprise"] >= 6).mean() * 100
        mae_hi = d2m.loc[d2m["min_surprise"] >= 6, "abs_err"].mean()
        mae_lo = d2m.loc[d2m["min_surprise"] < 6, "abs_err"].mean()
        print(f"    >>> {share_hi:.0f}% of games have min_surprise>=6; their MAE={mae_hi:.3f} "
              f"vs {mae_lo:.3f} for stable-minutes games "
              f"(delta {mae_hi - mae_lo:+.3f})")

        # 2) error vs actual minutes regime
        d2["min_bucket"] = pd.cut(d2["actual_min"], [-0.1, 12, 24, 32, 60],
                                  labels=["<12", "12-24", "24-32", "32+"])
        print("\n  MAE by actual minutes played:")
        g2 = d2.groupby("min_bucket", observed=True)["abs_err"].agg(["mean", "count"])
        for b, row in g2.iterrows():
            print(f"    {str(b):<7} MAE={row['mean']:.3f}  n={int(row['count']):,}")

        # 3) directional bias
        bias = (d2["pred"] - d2["actual"]).mean()
        print(f"\n  mean(pred-actual) bias = {bias:+.3f} "
              f"({'OVER' if bias > 0 else 'UNDER'}-predicts on average)")


if __name__ == "__main__":
    sys.exit(main())
