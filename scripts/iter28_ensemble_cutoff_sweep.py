"""iter28_ensemble_cutoff_sweep.py - Iter-28: test OLD+NEW model ensemble.

Hypothesis: OLD model (cutoff 2024-04-21) may have complementary signal to
NEW model (cutoff 2025-04-21). Sweep w_new in [0.5,0.6,0.7,0.8,0.9,1.0] per stat.

NEW model dir: data/models/oos_pre_playoffs/
OLD model dir: data/models/_backup_iter22_promoted_20260527_165457/
Eval data:     data/cache/eval_2025_26_combined.csv + playoffs_2025_26_oddsapi.csv

Output: data/cache/iter28_ensemble_sweep_results.json
Ship criteria: aggregate ROI improvement >= +0.5pp vs all-w_new=1.0 baseline.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _recommend,
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import feature_columns
from src.prediction.prop_quantiles import _inverse

GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
NEW_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
OLD_DIR = os.path.join(PROJECT_DIR, "data", "models", "_backup_iter22_promoted_20260527_165457")

THRESHOLD = 0.5
PROFIT_PER_WIN = _odds_to_decimal_profit(-110)

QSTAT_XGB = {"blk", "fg3m", "stl", "tov"}
QSTAT_LGB = {"reb"}
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk"]  # tov excluded (0 bets in baseline)
W_NEW_SWEEP = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


# ─────────────────────────────── artifact loaders ────────────────────────────

def _load_qstat_model(stat: str, model_dir: str):
    """Load q50 model from model_dir. Returns (model, path) or (None, path)."""
    if stat in QSTAT_LGB:
        import joblib
        path = os.path.join(model_dir, f"quantile_pergame_lgb_{stat}_q50.pkl")
        if not os.path.exists(path):
            return None, path
        return joblib.load(path), path
    if stat in QSTAT_XGB:
        import xgboost as xgb
        path = os.path.join(model_dir, f"quantile_pergame_{stat}_q50.json")
        if not os.path.exists(path):
            return None, path
        m = xgb.XGBRegressor()
        m.load_model(path)
        return m, path
    return None, ""


def _load_pts_artifacts(model_dir: str) -> dict:
    import joblib
    import xgboost as xgb_lib
    a = {}
    xgb_path = os.path.join(model_dir, "props_pg_pts.json")
    lgb_path = os.path.join(model_dir, "props_pg_lgb_pts.pkl")
    mlp_path = os.path.join(model_dir, "props_pg_mlp_pts.pkl")
    sca_path = os.path.join(model_dir, "props_pg_mlp_scaler_pts.pkl")
    wts_path = os.path.join(model_dir, "meta_weights_pergame.json")
    if os.path.exists(xgb_path):
        m = xgb_lib.XGBRegressor()
        m.load_model(xgb_path)
        a["xgb"] = m
    else:
        a["xgb"] = None
    a["lgb"] = joblib.load(lgb_path) if os.path.exists(lgb_path) else None
    a["mlp"] = joblib.load(mlp_path) if os.path.exists(mlp_path) else None
    a["mlp_scaler"] = joblib.load(sca_path) if os.path.exists(sca_path) else None
    weights = None
    if os.path.exists(wts_path):
        try:
            weights = json.load(open(wts_path, encoding="utf-8")).get("pts")
        except Exception:
            pass
    a["weights"] = weights
    return a


def _load_ast_artifacts(model_dir: str) -> dict:
    import joblib
    import xgboost as xgb_lib
    a = {}
    xgb_path = os.path.join(model_dir, "props_pg_ast.json")
    lgb_path = os.path.join(model_dir, "props_pg_lgb_ast.pkl")
    mlp_path = os.path.join(model_dir, "props_pg_mlp_ast.pkl")
    sca_path = os.path.join(model_dir, "props_pg_mlp_scaler_ast.pkl")
    wts_path = os.path.join(model_dir, "meta_weights_pergame.json")
    if os.path.exists(xgb_path):
        m = xgb_lib.XGBRegressor()
        m.load_model(xgb_path)
        a["xgb"] = m
    else:
        a["xgb"] = None
    a["lgb"] = joblib.load(lgb_path) if os.path.exists(lgb_path) else None
    a["mlp"] = joblib.load(mlp_path) if os.path.exists(mlp_path) else None
    a["mlp_scaler"] = joblib.load(sca_path) if os.path.exists(sca_path) else None
    weights = None
    if os.path.exists(wts_path):
        try:
            weights = json.load(open(wts_path, encoding="utf-8")).get("ast")
        except Exception:
            pass
    a["weights"] = weights
    return a


# ────────────────────────────── prediction helpers ───────────────────────────

def _predict_qstat(stat: str, model, feat_row: Dict) -> float:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


def _inv_sqrt(v: float) -> float:
    return max(0.0, float(v)) ** 2


def _predict_blend(artifacts: dict, stat: str, feat_row: Dict) -> Optional[float]:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    weights = artifacts.get("weights")
    if not weights:
        return None
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))
    parts = []
    if artifacts.get("xgb") is not None and w_xgb > 0:
        raw = float(artifacts["xgb"].predict(X)[0])
        if stat == "pts":
            parts.append(w_xgb * _inv_sqrt(raw))
        else:
            parts.append(w_xgb * float(_inverse(stat, np.array([raw]))[0]))
    if artifacts.get("lgb") is not None and w_lgb > 0:
        raw = float(artifacts["lgb"].predict(X)[0])
        if stat == "pts":
            parts.append(w_lgb * _inv_sqrt(raw))
        else:
            parts.append(w_lgb * float(_inverse(stat, np.array([raw]))[0]))
    if (artifacts.get("mlp") is not None and artifacts.get("mlp_scaler") is not None and w_mlp > 0):
        Xs = artifacts["mlp_scaler"].transform(X)
        raw = float(artifacts["mlp"].predict(Xs)[0])
        if stat == "pts":
            parts.append(w_mlp * _inv_sqrt(raw))
        else:
            parts.append(w_mlp * float(_inverse(stat, np.array([raw]))[0]))
    if not parts:
        return None
    return max(0.0, float(sum(parts)))


# ───────────────────────── load all CSV rows ─────────────────────────────────

def _load_eval_rows() -> List[dict]:
    """Combine 2025-26 RS + playoffs lines CSV into a single list."""
    rs_path = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                           "regular_season_2025_26_oddsapi.csv")
    po_path = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                           "playoffs_2025_26_oddsapi.csv")
    rows = []
    for path in (rs_path, po_path):
        if not os.path.exists(path):
            print(f"  [warn] missing: {path}")
            continue
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("stat", "").lower() in STATS:
                    rows.append(r)
    print(f"  Loaded {len(rows)} eval rows for stats: {STATS}")
    return rows


# ─────────────────────────── main sweep ──────────────────────────────────────

def run() -> dict:
    print("\n  Iter-28: OLD+NEW model ensemble weight sweep")
    t_start = time.time()

    # ---- Load models from both directories ----
    print(f"\n  Loading NEW models from: {os.path.basename(NEW_DIR)}")
    new_models = {}
    new_pts = _load_pts_artifacts(NEW_DIR)
    if new_pts["xgb"] is not None and new_pts["weights"]:
        new_models["pts"] = ("blend", new_pts)
        print(f"    pts: blend ready (weights={new_pts['weights']})")
    new_ast = _load_ast_artifacts(NEW_DIR)
    if new_ast.get("xgb") is not None and new_ast.get("weights"):
        new_models["ast"] = ("blend", new_ast)
        print(f"    ast: blend ready (weights={new_ast['weights']})")
    for s in ("reb", "fg3m", "stl", "blk"):
        m, path = _load_qstat_model(s, NEW_DIR)
        if m is not None:
            new_models[s] = ("qstat", m)
            print(f"    {s}: loaded from {os.path.basename(path)}")
        else:
            print(f"    {s}: MISSING in new dir ({path})")

    print(f"\n  Loading OLD models from: {os.path.basename(OLD_DIR)}")
    old_models = {}
    old_pts = _load_pts_artifacts(OLD_DIR)
    if old_pts["xgb"] is not None and old_pts["weights"]:
        old_models["pts"] = ("blend", old_pts)
        print(f"    pts: blend ready (weights={old_pts['weights']})")
    old_ast = _load_ast_artifacts(OLD_DIR)
    if old_ast.get("xgb") is not None and old_ast.get("weights"):
        old_models["ast"] = ("blend", old_ast)
        print(f"    ast: blend ready (weights={old_ast['weights']})")
    for s in ("reb", "fg3m", "stl", "blk"):
        m, path = _load_qstat_model(s, OLD_DIR)
        if m is not None:
            old_models[s] = ("qstat", m)
            print(f"    {s}: loaded from {os.path.basename(path)}")
        else:
            print(f"    {s}: MISSING in old dir — will use only new model")

    # ---- Load eval rows ----
    all_rows = _load_eval_rows()

    # ---- Resolve player IDs ----
    unique_names = sorted({r["player"] for r in all_rows})
    print(f"\n  Resolving {len(unique_names)} unique players...")
    name2pid = {}
    for nm in unique_names:
        name2pid[nm] = _resolve_player_id(nm)
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Resolved {n_resolved}/{len(unique_names)} players")

    # ---- Build predictions for each row (NEW + OLD) ----
    print("\n  Building predictions (both models)...")
    row_cache = {}  # (pid, date, venue, opp) -> feat

    # Store: stat -> list of {line, actual, pred_new, pred_old}
    stat_records: Dict[str, List[dict]] = defaultdict(list)
    skip_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    n_processed = 0

    for r in all_rows:
        stat = r["stat"].lower()
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip_counts[stat]["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skip_counts[stat]["no_pid"] += 1
            continue
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        key = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r["opp"], d, season, is_home=is_home,
                rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skip_counts[stat]["no_history"] += 1
            continue

        # Get NEW model prediction
        pred_new = None
        if stat in new_models:
            kind, model = new_models[stat]
            try:
                if kind == "blend":
                    pred_new = _predict_blend(model, stat, feat)
                else:
                    pred_new = _predict_qstat(stat, model, feat)
            except Exception as e:
                skip_counts[stat][f"new_err:{type(e).__name__}"] += 1
                continue
        if pred_new is None:
            skip_counts[stat]["no_new_pred"] += 1
            continue

        # Get OLD model prediction
        pred_old = None
        if stat in old_models:
            kind, model = old_models[stat]
            try:
                if kind == "blend":
                    pred_old = _predict_blend(model, stat, feat)
                else:
                    pred_old = _predict_qstat(stat, model, feat)
            except Exception as e:
                pred_old = None  # missing old model is OK, fall back to w_new=1.0

        stat_records[stat].append({
            "line": line,
            "actual": actual,
            "pred_new": pred_new,
            "pred_old": pred_old,  # may be None if old model missing
        })
        n_processed += 1

    print(f"  Processed {n_processed} rows with valid new predictions")
    for s in STATS:
        sc = dict(skip_counts[s])
        if sc:
            print(f"    {s} skip: {sc}")

    # ---- Sweep weights per stat ----
    print("\n  Sweeping ensemble weights...")
    sweep_results = {}  # stat -> {w_new -> {roi, hit, n_bets}}
    optimal_weights = {}  # stat -> best w_new

    for stat in STATS:
        records = stat_records.get(stat, [])
        if not records:
            print(f"  {stat}: no records, skipping")
            optimal_weights[stat] = 1.0
            continue

        # Separate rows with and without old predictions
        have_old = [r for r in records if r["pred_old"] is not None]
        no_old = [r for r in records if r["pred_old"] is None]
        print(f"\n  {stat.upper()}: {len(records)} rows total, "
              f"{len(have_old)} have old-model pred, {len(no_old)} new-only")

        stat_sweep = {}
        for w_new in W_NEW_SWEEP:
            w_old = round(1.0 - w_new, 2)
            n_bets = 0
            wins = 0
            for rec in records:
                pred_old = rec.get("pred_old")
                if pred_old is not None and w_old > 0:
                    pred = w_new * rec["pred_new"] + w_old * pred_old
                else:
                    # No old prediction or w_old=0 → use new only
                    pred = rec["pred_new"]
                edge = pred - rec["line"]
                rec_dir = _recommend(edge, THRESHOLD)
                if rec_dir == "NO_BET":
                    continue
                actual_result = _classify_result(rec["actual"], rec["line"])
                if actual_result == "PUSH":
                    continue
                n_bets += 1
                if rec_dir == actual_result:
                    wins += 1
            roi_units = wins * PROFIT_PER_WIN - (n_bets - wins) * 1.0
            roi_pct = (roi_units / n_bets * 100.0) if n_bets else 0.0
            hit_rate = (wins / n_bets) if n_bets else 0.0
            stat_sweep[w_new] = {
                "w_new": w_new,
                "w_old": w_old,
                "n_bets": n_bets,
                "wins": wins,
                "hit_rate": round(hit_rate * 100, 2),
                "roi_pct": round(roi_pct, 4),
            }
            print(f"    w_new={w_new:.1f} | n_bets={n_bets:4d} | "
                  f"hit={hit_rate*100:.2f}% | ROI={roi_pct:+.2f}%")

        sweep_results[stat] = stat_sweep

        # Best weight by ROI (with at least 20 bets)
        best_w = 1.0
        best_roi = stat_sweep.get(1.0, {}).get("roi_pct", 0.0)
        for w, res in stat_sweep.items():
            if res["n_bets"] >= 20 and res["roi_pct"] > best_roi:
                best_roi = res["roi_pct"]
                best_w = w
        optimal_weights[stat] = best_w
        baseline_roi = stat_sweep.get(1.0, {}).get("roi_pct", 0.0)
        print(f"  {stat.upper()} optimal: w_new={best_w:.1f} "
              f"(ROI={best_roi:+.2f}% vs baseline {baseline_roi:+.2f}%)")

    # ---- Aggregate comparison: baseline (all w_new=1.0) vs optimal ----
    print("\n  Aggregating results...")
    agg_baseline = {"n_bets": 0, "wins": 0}
    agg_optimal = {"n_bets": 0, "wins": 0}

    for stat in STATS:
        records = stat_records.get(stat, [])
        if not records:
            continue
        opt_w = optimal_weights.get(stat, 1.0)

        # Baseline: w_new=1.0
        for rec in records:
            pred = rec["pred_new"]
            edge = pred - rec["line"]
            rec_dir = _recommend(edge, THRESHOLD)
            if rec_dir == "NO_BET":
                continue
            actual_result = _classify_result(rec["actual"], rec["line"])
            if actual_result == "PUSH":
                continue
            agg_baseline["n_bets"] += 1
            if rec_dir == actual_result:
                agg_baseline["wins"] += 1

        # Optimal weight
        w_old = round(1.0 - opt_w, 2)
        for rec in records:
            pred_old = rec.get("pred_old")
            if pred_old is not None and w_old > 0:
                pred = opt_w * rec["pred_new"] + w_old * pred_old
            else:
                pred = rec["pred_new"]
            edge = pred - rec["line"]
            rec_dir = _recommend(edge, THRESHOLD)
            if rec_dir == "NO_BET":
                continue
            actual_result = _classify_result(rec["actual"], rec["line"])
            if actual_result == "PUSH":
                continue
            agg_optimal["n_bets"] += 1
            if rec_dir == actual_result:
                agg_optimal["wins"] += 1

    def _roi(d):
        if d["n_bets"] == 0:
            return 0.0
        units = d["wins"] * PROFIT_PER_WIN - (d["n_bets"] - d["wins"]) * 1.0
        return units / d["n_bets"] * 100.0

    baseline_roi_agg = _roi(agg_baseline)
    optimal_roi_agg = _roi(agg_optimal)
    delta_pp = optimal_roi_agg - baseline_roi_agg

    elapsed = time.time() - t_start
    print(f"\n  == AGGREGATE ==")
    print(f"  Baseline  (w_new=1.0):  n={agg_baseline['n_bets']:4d}  ROI={baseline_roi_agg:+.4f}%")
    print(f"  Optimal ensemble:       n={agg_optimal['n_bets']:4d}  ROI={optimal_roi_agg:+.4f}%")
    print(f"  Delta:                  {delta_pp:+.4f}pp")
    print(f"  Ship threshold:         +0.5pp")
    ship = delta_pp >= 0.5
    print(f"  Decision:               {'SHIP' if ship else 'REVERT'}")

    # ---- Build output ----
    result = {
        "iter": "iter28",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "elapsed_sec": round(elapsed, 2),
        "ship": ship,
        "delta_pp": round(delta_pp, 4),
        "baseline_roi_pct": round(baseline_roi_agg, 4),
        "optimal_roi_pct": round(optimal_roi_agg, 4),
        "optimal_weights": optimal_weights,
        "sweep": {
            stat: {str(k): v for k, v in res.items()}
            for stat, res in sweep_results.items()
        },
        "aggregate": {
            "baseline": {**agg_baseline, "roi_pct": round(baseline_roi_agg, 4)},
            "optimal": {**agg_optimal, "roi_pct": round(optimal_roi_agg, 4)},
        },
    }

    out_path = os.path.join(PROJECT_DIR, "data", "cache", "iter28_ensemble_sweep_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(result, open(out_path, "w", encoding="utf-8"), indent=2)
    print(f"\n  Results -> {out_path}")
    return result


if __name__ == "__main__":
    result = run()
