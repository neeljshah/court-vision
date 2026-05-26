"""
probe_R10_M13_tracking.py — Cycle M13 (loop 10).

TARGET: PLAYER TRACKING FEATURES (prior-season ONLY, used as residual-head features)

Cycle 14 (loop 5) failure mode: tracking was joined as CURRENT-season — role
changes within a season meant prior_season tracking was a noisy proxy.
This retry uses STRICT season S-1 lookup AND feeds tracking into an LGB
residual head (delta correction on top of the baseline q50/blend predictions)
rather than as direct XGB/LGB main-model features. Residual angle avoids the
high-dimensional main-model saturation that killed cycle 14.

DESIGN:
  1. Build full pergame dataset via build_pergame_dataset (baseline 14 form features
     + all existing joins).
  2. For each row: look up tracking features from (player_id, season S-1).
     Drop rows with no prior-season tracking (rookies / season-1 players).
  3. 4 tracking features chosen for signal-to-noise:
       trk_drv_pts        — drives-per-game scoring (→ PTS, AST, FG3M)
       trk_drv_count      — drive frequency (volume proxy)
       trk_pas_potential_ast — passing creation (→ AST)
       trk_cs_pts         — catch-and-shoot points (→ FG3M, PTS)
  4. Walk-forward 4-fold temporal CV. Each fold: train LGB residual head
     (baseline_pred + trk_features → residual target = actual - baseline_pred).
     Final prediction = baseline_pred + residual_pred.
  5. Baseline: LGB q50 model loaded from data/models/ where available,
     else train a lightweight XGB on the 14 form features.
  6. Gate: 4/4 folds positive AND mean delta <= -0.005 for >= 4/7 stats.

SHIP GATE baseline MAE (endQ3 from retro_inplay_mae run):
  pts=2.214, reb=0.8987, ast=0.5755, fg3m=0.3528, stl=0.2506, blk=0.1543, tov=0.3663

Run:
    python -u scripts/probe_R10_M13_tracking.py 2>&1 | tee scripts/_results/improve_R10_M13_run.log
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

DATA_CACHE = os.path.join(PROJECT, "data", "cache")
OUT_JSON   = os.path.join(DATA_CACHE, "probe_R11_M13v2_tracking_broader_results.json")
os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(os.path.join(PROJECT, "scripts", "_results"), exist_ok=True)

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# Baseline MAE targets (from retro_inplay_mae endQ3 benchmarks)
BASELINE_MAE = {
    "pts":  2.214,
    "reb":  0.8987,
    "ast":  0.5755,
    "fg3m": 0.3528,
    "stl":  0.2506,
    "blk":  0.1543,
    "tov":  0.3663,
}

# M13v2: BROADER tracking feature set. M13 shipped PTS at WF 4/4 -0.00736;
# AST hit WF 4/4 -0.00491 (just shy of -0.005 gate). Adding more passing-
# specific features (drv_passes, drv_ast, pas_passes_made,
# pas_ast_points_created, pas_secondary_ast) should give the LGB head more
# signal for AST and possibly FG3M (cs_fga adds spot-up volume info).
TRK_FEATURES = [
    "trk_drv_pts",
    "trk_drv_count",
    "trk_drv_passes",
    "trk_drv_ast",
    "trk_pas_passes_made",
    "trk_pas_potential_ast",
    "trk_pas_ast_points_created",
    "trk_pas_secondary_ast",
    "trk_cs_pts",
    "trk_cs_fga",
]

# Season string -> prior season string (e.g., "2024-25" -> "2023-24")
def _prior_season(season: str) -> str:
    try:
        start, end = season.split("-")
        return f"{int(start)-1}-{int(end)-1:02d}"
    except Exception:
        return ""


def _game_season(date_iso: str) -> str:
    """Infer season string ('2024-25') from ISO date like '2024-11-01'."""
    try:
        year = int(date_iso[:4])
        month = int(date_iso[5:7])
        # NBA season spans Oct-Jun: Oct-Dec belong to season starting that year
        if month >= 10:
            return f"{year}-{(year+1) % 100:02d}"
        else:
            return f"{year-1}-{year % 100:02d}"
    except Exception:
        return ""


def load_tracking_lookup() -> Dict[Tuple[int, str], Dict[str, float]]:
    """Build (player_id, season) -> tracking features dict."""
    import pandas as pd
    path = os.path.join(PROJECT, "data", "player_tracking.parquet")
    df = pd.read_parquet(path)
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    for _, row in df.iterrows():
        pid = int(row["player_id"])
        season = str(row["season"])
        vals: Dict[str, float] = {}
        for col in TRK_FEATURES:
            v = row.get(col, 0.0)
            try:
                f = float(v)
                vals[col] = 0.0 if (f != f) else f   # NaN -> 0
            except (TypeError, ValueError):
                vals[col] = 0.0
        lookup[(pid, season)] = vals
    print(f"  [tracking] loaded {len(lookup)} (player, season) rows", flush=True)
    return lookup


def build_dataset_with_tracking() -> Tuple[List[dict], List[str]]:
    """
    Call build_pergame_dataset, then attach prior-season tracking features.
    Rows with no prior-season tracking are DROPPED (strict S-1 discipline).
    Returns (rows_with_tracking, base_feature_cols).
    """
    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns
    print("  [data] calling build_pergame_dataset ...", flush=True)
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    print(f"  [data] {len(rows)} rows built in {time.time()-t0:.1f}s", flush=True)

    tracking_lookup = load_tracking_lookup()

    kept: List[dict] = []
    dropped = 0
    for row in rows:
        date_iso = str(row.get("date", ""))[:10]
        season = _game_season(date_iso)
        prior = _prior_season(season)
        if not prior:
            dropped += 1
            continue
        pid = int(row.get("player_id", 0))
        trk = tracking_lookup.get((pid, prior))
        if trk is None:
            dropped += 1
            continue
        # Attach tracking features to row
        for col in TRK_FEATURES:
            row[col] = trk[col]
        kept.append(row)

    print(f"  [tracking join] kept={len(kept)}, dropped={dropped} "
          f"(no prior-season tracking)", flush=True)
    return kept, base_cols


def walk_forward_4fold(rows: List[dict], base_cols: List[str]) -> Dict[str, list]:
    """
    4-fold temporal walk-forward CV.
    Each fold: train LGB residual head using (base_features + TRK_FEATURES).
    Residual target = actual - baseline_pred (baseline from LGB on base_cols).
    Evaluate: final_pred = baseline_pred + residual_pred.

    Returns {stat: [fold_delta, ...]} where delta = probe_mae - baseline_mae.
    """
    import lightgbm as lgb

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    n = len(rows_sorted)
    print(f"  [wf] {n} rows, 4-fold walk-forward CV", flush=True)

    # Fold boundaries: 60/70/80/90% train, 10% each test
    fold_cuts = [0.60, 0.70, 0.80, 0.90]
    fold_results: Dict[str, List[float]] = {s: [] for s in STATS}

    for fold_i, train_end_frac in enumerate(fold_cuts):
        train_end = int(n * train_end_frac)
        test_start = train_end
        test_end = min(int(n * (train_end_frac + 0.10)), n)
        if test_end <= test_start:
            print(f"  [wf] fold {fold_i+1} empty, skip", flush=True)
            continue

        train_rows = rows_sorted[:train_end]
        test_rows  = rows_sorted[test_start:test_end]
        print(f"  [wf] fold {fold_i+1}: train={len(train_rows)}, "
              f"test={len(test_rows)}", flush=True)

        # Build feature matrices
        all_cols   = base_cols + TRK_FEATURES
        X_tr = np.array([[r[c] for c in all_cols] for r in train_rows], dtype=float)
        X_te = np.array([[r[c] for c in all_cols] for r in test_rows],  dtype=float)
        X_tr_base = X_tr[:, :len(base_cols)]
        X_te_base = X_te[:, :len(base_cols)]
        X_tr_full = X_tr
        X_te_full = X_te

        for stat in STATS:
            y_tr = np.array([r[f"target_{stat}"] for r in train_rows], dtype=float)
            y_te = np.array([r[f"target_{stat}"] for r in test_rows],  dtype=float)

            # --- BASELINE: LGB trained on base_cols only ---
            lgb_params_base = {
                "objective": "quantile", "alpha": 0.5,
                "learning_rate": 0.05, "n_estimators": 300,
                "max_depth": 3, "num_leaves": 15,
                "min_child_samples": 20, "reg_lambda": 2.0,
                "subsample": 0.8, "colsample_bytree": 0.8,
                "verbose": -1, "n_jobs": 2,
            }
            base_model = lgb.LGBMRegressor(**lgb_params_base)
            base_model.fit(X_tr_base, y_tr)
            base_pred_tr = base_model.predict(X_tr_base)
            base_pred_te = base_model.predict(X_te_base)

            baseline_mae = float(np.mean(np.abs(base_pred_te - y_te)))

            # --- RESIDUAL HEAD: LGB on (base_cols + tracking) ---
            residual_tr = y_tr - base_pred_tr  # learn the error
            residual_params = {
                "objective": "regression_l1",
                "learning_rate": 0.03, "n_estimators": 200,
                "max_depth": 3, "num_leaves": 15,
                "min_child_samples": 30, "reg_lambda": 4.0,
                "subsample": 0.8, "colsample_bytree": 0.8,
                "verbose": -1, "n_jobs": 2,
            }
            res_model = lgb.LGBMRegressor(**residual_params)
            res_model.fit(X_tr_full, residual_tr)
            residual_pred_te = res_model.predict(X_te_full)

            probe_pred_te = base_pred_te + residual_pred_te
            probe_mae = float(np.mean(np.abs(probe_pred_te - y_te)))

            delta = probe_mae - baseline_mae
            fold_results[stat].append(delta)
            sign = "+" if delta >= 0 else ""
            print(f"    fold {fold_i+1} {stat:4s}: base={baseline_mae:.4f} "
                  f"probe={probe_mae:.4f} delta={sign}{delta:.4f}", flush=True)

    return fold_results


def apply_gate(fold_results: Dict[str, List[float]]) -> Tuple[bool, dict]:
    """
    Gate: 4/4 folds positive (negative delta = improvement) AND
    mean delta <= -0.005 for >= 4/7 stats.
    Returns (passed, summary_dict).
    """
    summary = {}
    stats_passing_mean = 0
    stats_4of4 = 0

    for stat in STATS:
        deltas = fold_results[stat]
        if not deltas:
            summary[stat] = {"deltas": [], "mean_delta": None, "folds_positive": 0,
                             "gate_4of4": False, "gate_mean": False}
            continue
        mean_d = float(np.mean(deltas))
        n_pos = sum(1 for d in deltas if d < 0)
        gate_4of4 = (n_pos == len(deltas))
        gate_mean  = (mean_d <= -0.005)
        summary[stat] = {
            "deltas": [round(d, 5) for d in deltas],
            "mean_delta": round(mean_d, 5),
            "folds_positive": n_pos,
            "gate_4of4": gate_4of4,
            "gate_mean": gate_mean,
        }
        if gate_4of4:
            stats_4of4 += 1
        if gate_mean:
            stats_passing_mean += 1

    # Ship gate: >= 4 stats with 4/4 AND mean <= -0.005
    # The spec says: WF 4/4 folds positive, mean delta <= -0.005, >= 4/7 stats.
    # We require both conditions on the same stat.
    stats_fully_pass = sum(
        1 for s in STATS
        if summary.get(s, {}).get("gate_4of4") and summary.get(s, {}).get("gate_mean")
    )
    ship = stats_fully_pass >= 4

    summary["_gate_summary"] = {
        "stats_4of4": stats_4of4,
        "stats_passing_mean": stats_passing_mean,
        "stats_fully_pass": stats_fully_pass,
        "ship": ship,
        "verdict": "SHIP" if ship else "REJECT",
    }
    return ship, summary


def main() -> int:
    print("=" * 60, flush=True)
    print("probe_R10_M13_tracking — prior-season tracking residual", flush=True)
    print(f"output: {OUT_JSON}", flush=True)
    print("=" * 60, flush=True)

    t_start = time.time()

    # 1. Build dataset with tracking
    rows, base_cols = build_dataset_with_tracking()

    if len(rows) < 500:
        result = {
            "error": f"Too few rows after tracking join: {len(rows)}",
            "n_rows": len(rows),
        }
        with open(OUT_JSON, "w") as f:
            json.dump(result, f, indent=2)
        print(f"ABORT: {result['error']}", flush=True)
        return 1

    # 2. Walk-forward 4-fold
    fold_results = walk_forward_4fold(rows, base_cols)

    # 3. Gate
    ship, gate_summary = apply_gate(fold_results)

    # 4. Print summary
    print("\n--- RESULTS ---", flush=True)
    for stat in STATS:
        s = gate_summary[stat]
        deltas = s.get("deltas", [])
        mean_d = s.get("mean_delta")
        n_pos  = s.get("folds_positive", 0)
        n_folds = len(deltas)
        baseline = BASELINE_MAE.get(stat, 0)
        print(
            f"  {stat:4s}: mean_delta={mean_d:+.5f}  folds_pos={n_pos}/{n_folds}  "
            f"gate_4of4={'YES' if s.get('gate_4of4') else 'no '}  "
            f"gate_mean={'YES' if s.get('gate_mean') else 'no '}  "
            f"base_ref={baseline:.4f}",
            flush=True,
        )
    gs = gate_summary["_gate_summary"]
    print(f"\n  stats_fully_pass={gs['stats_fully_pass']}/7  "
          f"VERDICT: {gs['verdict']}", flush=True)

    elapsed = time.time() - t_start
    result = {
        "probe": "R11_M13v2_tracking_broader",
        "description": "Prior-season tracking (trk_drv_pts, trk_drv_count, trk_pas_potential_ast, trk_cs_pts) as LGB residual head features",
        "n_rows_with_tracking": len(rows),
        "tracking_features": TRK_FEATURES,
        "baseline_mae": BASELINE_MAE,
        "fold_results": {s: fold_results[s] for s in STATS},
        "gate_summary": gate_summary,
        "ship": ship,
        "verdict": "SHIP" if ship else "REJECT",
        "elapsed_s": round(elapsed, 1),
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Wrote {OUT_JSON}", flush=True)
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
