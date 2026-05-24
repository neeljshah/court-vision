"""quantile_calibration_rolling.py -- Cycle 90f (loop 5), T4-A.

Cycle 40's per-stat quantile scale factor is GLOBAL: a single number per stat
fit on the val slice. League-wide stats drift (3PT rate +~0.5%/season, pace
shifts post rule-changes) so a rolling 60-game window recalibration tracks
drift and keeps q10/q90 empirical coverage closer to 80% across a season.

This script reproduces the EXACT cycle-40 formula (symmetric vs asymmetric
branch, asymmetric when q10_zero_frac > 0.30) but over a rolling window:

    for each date d that we have a prediction for:
        use the most-recent 60 PRIOR games (strictly d' < d) per stat
        fit scale s minimising |empirical_80_coverage - 0.80|
        write (date, stat, scale, asymmetric) row

Outputs a time-indexed parquet at data/models/quantile_cal_rolling.parquet
with columns:
    date, stat, scale, asymmetric, n_window, coverage

Default behaviour leaves cycle-40 global scales untouched. The artifact is
consumed only when --rolling-cal is passed to compare_to_lines.py (NEW; see
patch). Zero point-prediction change. Zero production hot-path change.

Drift report: prints stats whose median rolling scale deviates >10% from the
global cycle-40 value (these are the candidates where a rolling refresh
actually matters) and writes scripts/_results/quantile_rolling_drift_v1.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    _inverse, load_quantile_models,
)


_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_ROLLING_PATH = os.path.join(_MODEL_DIR, "quantile_cal_rolling.parquet")
_GLOBAL_PATH = os.path.join(_MODEL_DIR, "quantile_calibration.json")
_DRIFT_REPORT = os.path.join(PROJECT_DIR, "scripts", "_results",
                             "quantile_rolling_drift_v1.md")

_WINDOW = 60      # prior-games window per (stat, date) calibration point
_REFRESH = 5      # only recompute every Nth date to keep parquet small
_ASYM_FLOOR = 0.30  # cycle-40 threshold: q10_zero_frac > 0.30 -> asymmetric


def _grid_search_scale(q10, q50, q90, actuals, target=0.80,
                       lo=0.05, hi=3.0, n=120) -> tuple:
    """Cycle-40 logic, identical formula. Returns (scale, asymmetric, coverage)."""
    if len(actuals) == 0:
        return 1.0, False, 0.0
    q10 = np.asarray(q10, dtype=float)
    q50 = np.asarray(q50, dtype=float)
    q90 = np.asarray(q90, dtype=float)
    actuals = np.asarray(actuals, dtype=float)
    q10_zero_frac = float((q10 <= 0.01).mean())
    asymmetric = q10_zero_frac > _ASYM_FLOOR

    grid = np.linspace(lo, hi, n)
    best_s = 1.0
    best_diff = 1.0
    best_cov = 0.0
    for s in grid:
        if asymmetric:
            cal_q10 = q10
            cal_q90 = q50 + s * (q90 - q50)
        else:
            cal_q10 = q50 - s * (q50 - q10)
            cal_q90 = q50 + s * (q90 - q50)
        cov = float(((actuals >= cal_q10) & (actuals <= cal_q90)).mean())
        diff = abs(cov - target)
        if diff < best_diff:
            best_diff = diff
            best_s = float(s)
            best_cov = cov
    return best_s, bool(asymmetric), best_cov


def _load_global_scales() -> Dict[str, dict]:
    if not os.path.exists(_GLOBAL_PATH):
        return {}
    try:
        return json.load(open(_GLOBAL_PATH, encoding="utf-8"))
    except Exception:
        return {}


def compute_rolling(window: int = _WINDOW, refresh: int = _REFRESH,
                    out_path: str = _ROLLING_PATH) -> "pd.DataFrame":
    """Build the time-indexed scale parquet.

    For each (stat, date) where we have at least `window` prior holdout rows,
    fit the cycle-40 scale on those prior rows only. To keep the parquet
    light, recompute every `refresh` dates and forward-fill in the consumer.
    """
    import pandas as pd
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    if n == 0:
        print("[fail] no rows from build_pergame_dataset")
        return pd.DataFrame()
    print(f"[rolling] {n} total rows from build_pergame_dataset", flush=True)

    # Use the same val slice that cycle 40 uses (NOT the production holdout —
    # we calibrate on val to avoid leaking into the cycle-23 production
    # metric). Cycle 40 default: holdout_frac=0.2, val_frac=0.15 -> use the
    # val slice as the canonical "rolling" sample. We further restrict to
    # rows with at least `window` prior val rows for the rolling computation.
    holdout_frac, val_frac = 0.2, 0.15
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end = int(n * (1.0 - holdout_frac))
    val_rows = rows[train_end:val_end]
    print(f"[rolling] {len(val_rows)} val-slice rows for rolling fit", flush=True)
    if len(val_rows) <= window:
        print(f"[fail] val slice ({len(val_rows)}) <= window ({window})")
        return pd.DataFrame()

    X_val = np.array([[r[c] for c in fc] for r in val_rows], dtype=float)
    dates = [r["date"] for r in val_rows]

    # Pre-compute q-predictions for every stat (one pass through models).
    qpred: Dict[str, Dict[str, np.ndarray]] = {}
    actuals: Dict[str, np.ndarray] = {}
    for stat in STATS:
        models = load_quantile_models(stat, _MODEL_DIR)
        if 0.1 not in models or 0.5 not in models or 0.9 not in models:
            print(f"  [skip] {stat}: missing q10/q50/q90 models")
            continue
        q10_t = models[0.1].predict(X_val)
        q50_t = models[0.5].predict(X_val)
        q90_t = models[0.9].predict(X_val)
        qpred[stat] = {
            "q10": _inverse(stat, q10_t),
            "q50": _inverse(stat, q50_t),
            "q90": _inverse(stat, q90_t),
        }
        actuals[stat] = np.array(
            [r[f"target_{stat}"] for r in val_rows], dtype=float)

    out_rows: List[dict] = []
    # Walk the val slice in time order; emit a calibration row every `refresh`
    # dates once enough prior history exists. Each emission uses ONLY the
    # prior `window` rows (no leakage of date d into its own scale).
    for i in range(window, len(val_rows)):
        if (i - window) % refresh != 0:
            continue
        lo = i - window
        hi = i  # exclusive — the row at i is NOT used to fit its own scale
        for stat, qp in qpred.items():
            s, asym, cov = _grid_search_scale(
                qp["q10"][lo:hi], qp["q50"][lo:hi], qp["q90"][lo:hi],
                actuals[stat][lo:hi], target=0.80,
            )
            out_rows.append({
                "date": dates[i],
                "stat": stat,
                "scale": round(s, 4),
                "asymmetric": bool(asym),
                "n_window": int(hi - lo),
                "coverage": round(cov, 4),
            })

    df = pd.DataFrame(out_rows)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"[done] wrote {out_path}  rows={len(df)}", flush=True)
    return df


def drift_report(df: "pd.DataFrame") -> str:
    """Compare rolling median scales vs cycle-40 global scales. Returns
    markdown body; also prints top-3 drift stats to console."""
    import pandas as pd  # noqa: F401
    global_scales = _load_global_scales()
    if df is None or len(df) == 0:
        return "# Rolling Quantile Calibration Drift\n\n(empty rolling df)\n"

    body: List[str] = [
        "# Rolling Quantile Calibration Drift (cycle 90f, T4-A)",
        "",
        "Compares rolling 60-game median scales vs cycle-40 global scales.",
        "`drift_pct = (rolling_median - global) / global * 100`. Stats with",
        "|drift_pct| > 10% are candidates where the rolling refresh actually",
        "matters for Kelly-stake honesty.",
        "",
        "| stat | global | rolling_med | rolling_min | rolling_max | drift_pct | n |",
        "| ---- | -----: | ----------: | ----------: | ----------: | --------: | -: |",
    ]
    summary = []
    for stat in STATS:
        sub = df[df["stat"] == stat]
        if len(sub) == 0:
            continue
        g = global_scales.get(stat, {}).get("scale", 1.0)
        med = float(sub["scale"].median())
        s_min = float(sub["scale"].min())
        s_max = float(sub["scale"].max())
        drift = (med - g) / g * 100.0 if g else 0.0
        summary.append((stat, g, med, s_min, s_max, drift, len(sub)))
        body.append(
            f"| {stat} | {g:.4f} | {med:.4f} | {s_min:.4f} | {s_max:.4f} | "
            f"{drift:+.2f}% | {len(sub)} |"
        )

    # Top-3 |drift| stats
    summary.sort(key=lambda r: abs(r[5]), reverse=True)
    body += ["", "## Top-3 drift stats", ""]
    for stat, g, med, s_min, s_max, drift, n_ in summary[:3]:
        body.append(
            f"- **{stat.upper()}** global={g:.4f} -> rolling_median={med:.4f} "
            f"({drift:+.2f}%); range [{s_min:.4f}, {s_max:.4f}] over {n_} points"
        )

    body += ["", "## Default behaviour", "",
             "- cycle-40 global scales remain default (no Kelly-stake change)",
             "- `compare_to_lines.py --rolling-cal` opts into the parquet",
             "- next refresh: re-run this script after ~5 new val-slice games"]

    print("\n  ROLLING vs GLOBAL drift (top 3 by |drift|):", flush=True)
    for stat, g, med, _, _, drift, _ in summary[:3]:
        print(f"    {stat.upper():4s}  global={g:.4f}  "
              f"rolling_med={med:.4f}  drift={drift:+.2f}%", flush=True)

    return "\n".join(body) + "\n"


def load_rolling_scale(stat: str, on_or_before: str,
                       path: str = _ROLLING_PATH) -> tuple:
    """Read the most-recent rolling (scale, asymmetric) at-or-before a date.

    Falls back to cycle-40 global (scale, asymmetric) when the parquet is
    absent or the date has no prior coverage. Public API consumed by
    compare_to_lines.py when --rolling-cal is passed.
    """
    global_scales = _load_global_scales()
    g_entry = global_scales.get(stat, {})
    g_scale = float(g_entry.get("scale", 1.0))
    g_asym = bool(g_entry.get("asymmetric", False))
    if not os.path.exists(path):
        return g_scale, g_asym
    try:
        import pandas as pd
        df = pd.read_parquet(path)
        sub = df[(df["stat"] == stat) & (df["date"] <= on_or_before)]
        if len(sub) == 0:
            return g_scale, g_asym
        last = sub.sort_values("date").iloc[-1]
        return float(last["scale"]), bool(last["asymmetric"])
    except Exception:
        return g_scale, g_asym


def apply_rolling(stat: str, q10: float, q50: float, q90: float,
                  on_or_before: str, path: str = _ROLLING_PATH) -> tuple:
    """Apply rolling-window (q10, q90) calibration for one prediction.

    Mirrors src.prediction.quantile_calibration.apply but pulls (scale,
    asymmetric) from the time-indexed parquet. Returns (cal_q10, cal_q90).
    """
    s, asym = load_rolling_scale(stat, on_or_before, path=path)
    if asym:
        return float(max(0.0, q10)), float(q50 + s * (q90 - q50))
    cal_q10 = q50 - s * (q50 - q10)
    cal_q90 = q50 + s * (q90 - q50)
    return float(max(0.0, cal_q10)), float(cal_q90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=_WINDOW,
                    help=f"Rolling window size in games (default {_WINDOW})")
    ap.add_argument("--refresh", type=int, default=_REFRESH,
                    help=f"Recompute every Nth date (default {_REFRESH})")
    ap.add_argument("--out", default=_ROLLING_PATH,
                    help="Output parquet path")
    args = ap.parse_args()

    df = compute_rolling(window=args.window, refresh=args.refresh,
                         out_path=args.out)
    md = drift_report(df)
    os.makedirs(os.path.dirname(_DRIFT_REPORT), exist_ok=True)
    with open(_DRIFT_REPORT, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"[drift] wrote {_DRIFT_REPORT}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
