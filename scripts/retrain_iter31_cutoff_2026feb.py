"""retrain_iter31_cutoff_2026feb.py — Iter-31: probe later training cutoff (2026-02-01).

GOAL: train candidate models with cutoff 2026-02-01 (includes 2025-26 RS through
Jan 2026) and validate ONLY on the late-2026 window (post 2026-02-01):
  - RS rows with date >= 2026-02-01 (Feb–Apr 2026)
  - All playoffs rows (Apr–May 2026)

Compare per-stat ROI vs production on the SAME late-2026 window.

SHIP CRITERIA (per task spec):
  - 4+/6 stats improve >= +1pp ROI
  - Each shipping stat must have >= 30 bets in the eval window

Usage:
    python scripts/retrain_iter31_cutoff_2026feb.py [--skip-train] [--skip-prod-backtest]

Outputs:
    data/models/oos_pre_playoffs/_candidate_iter31_cutoff2026feb/
    data/cache/iter31_comparison.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import unicodedata

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

import src.prediction.prop_pergame as pg
from src.prediction.prop_pergame import feature_columns
from src.prediction.prop_quantiles import _inverse, _transform, _per_stat_xgb_params

# ─── player resolver (local fallback) ────────────────────────────────────────

def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


_LOCAL_PLAYER_INDEX: Optional[Dict[str, int]] = None


def _build_local_player_index() -> Dict[str, int]:
    global _LOCAL_PLAYER_INDEX
    if _LOCAL_PLAYER_INDEX is not None:
        return _LOCAL_PLAYER_INDEX
    idx: Dict[str, int] = {}
    pi_dir = os.path.join(PROJECT_DIR, "data", "cache", "playerinfo")
    if not os.path.isdir(pi_dir):
        _LOCAL_PLAYER_INDEX = idx
        return idx
    for fname in os.listdir(pi_dir):
        if not fname.endswith(".json"):
            continue
        try:
            pid = int(fname.replace(".json", ""))
            with open(os.path.join(pi_dir, fname), encoding="utf-8") as f:
                d = json.load(f)
            cpi = d.get("common_player_info", [])
            if cpi:
                full = cpi[0].get("DISPLAY_FIRST_LAST", "")
                if full:
                    idx[_strip_accents(full).lower()] = pid
        except Exception:
            pass
    _LOCAL_PLAYER_INDEX = idx
    return idx


def _local_resolve_player_id(name: str) -> Optional[int]:
    idx = _build_local_player_index()
    if not idx:
        return None
    needle = _strip_accents(name).lower().strip()
    if needle in idx:
        return idx[needle]
    for stored, pid in idx.items():
        if needle in stored or stored in needle:
            return pid
    last = needle.split()[-1] if needle else ""
    for stored, pid in idx.items():
        if stored.split()[-1] == last:
            return pid
    return None


# ─── constants ────────────────────────────────────────────────────────────────

NEW_CUTOFF_DATE = "2026-02-01"   # Iter-31 candidate
PROD_CUTOFF_DATE = "2025-04-21"  # Current production (Iter-22)

# Eval window: only rows >= this date (excludes candidate training data)
EVAL_WINDOW_START = "2026-02-01"

OOS_PROD_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
CANDIDATE_DIR = os.path.join(OOS_PROD_DIR, "_candidate_iter31_cutoff2026feb")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")

Q50_STATS_LGB = {"reb"}
Q50_STATS_XGB = {"blk", "fg3m", "stl", "tov"}
BLEND_STATS = {"pts", "ast"}

SHIP_THRESHOLD_PP = 1.0   # improve >= 1pp ROI
SHIP_MIN_STATS = 4        # need 4+/6 stats (tov typically 0 bets excluded)
SHIP_MIN_BETS = 30        # minimum bets for shipping stat to count
THRESHOLD = 0.5           # betting edge threshold

# Late-2026 eval slices (post EVAL_WINDOW_START only)
RS_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                      "regular_season_2025_26_oddsapi.csv")
PL_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                      "playoffs_2025_26_oddsapi.csv")


# ─── dataset cache ────────────────────────────────────────────────────────────

_DATASET_CACHE = None


def _get_dataset_at_cutoff(cutoff_date: str):
    """Return (pre_rows, fcols, n_all) filtered to rows strictly before cutoff_date."""
    global _DATASET_CACHE
    if _DATASET_CACHE is not None and _DATASET_CACHE[0] == cutoff_date:
        return _DATASET_CACHE[1:]

    print(f"  Building dataset (cutoff < {cutoff_date})...")
    t0 = time.time()
    rows, fcols = pg.build_pergame_dataset()
    n_all = len(rows)
    cutoff = datetime.fromisoformat(cutoff_date)
    pre_rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre_rows.sort(key=lambda r: r["date"])
    elapsed = time.time() - t0
    print(f"  n_all={n_all}  n_pre_cutoff={len(pre_rows)}  n_fcols={len(fcols)}  {elapsed:.1f}s")
    assert len(fcols) == 129, f"Expected 129 feature cols, got {len(fcols)}"
    _DATASET_CACHE = (cutoff_date, pre_rows, fcols, n_all)
    return pre_rows, fcols, n_all


def _recency_weights(dates, n_train: int) -> np.ndarray:
    max_d = max(dates[:n_train])
    age = np.array([(max_d - d).days / 365.0 for d in dates[:n_train]], dtype=float)
    return np.exp(-0.5 * age)


# ─── per-stat trainers ────────────────────────────────────────────────────────

def train_q50(stat: str, cutoff_date: str, out_dir: str) -> dict:
    """Train XGB/LGB q50 model for blk/fg3m/stl/tov/reb."""
    from sklearn.metrics import mean_absolute_error
    pre_rows, fcols, n_all = _get_dataset_at_cutoff(cutoff_date)
    method = "lgb" if stat in Q50_STATS_LGB else "xgb"
    print(f"\n  [{stat}] method={method}  cutoff={cutoff_date}  n_pre={len(pre_rows)}")
    t0 = time.time()

    n_pre = len(pre_rows)
    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = np.array([[r[c] for c in fcols] for r in pre_rows], dtype=float)
    _nan_mask = ~np.isfinite(X_all)
    if _nan_mask.any():
        _col_med = np.nanmedian(X_all[:train_end], axis=0)
        _col_med = np.where(np.isfinite(_col_med), _col_med, 0.0)
        for _ci in range(X_all.shape[1]):
            _cm = _nan_mask[:, _ci]
            if _cm.any():
                X_all[_cm, _ci] = _col_med[_ci]

    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    dates = [datetime.fromisoformat(pre_rows[i]["date"]) for i in range(n_pre)]
    sw = _recency_weights(dates, train_end)
    y = np.array([r[f"target_{stat}"] for r in pre_rows], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(stat, y_tr)
    yt_val = _transform(stat, y_val)
    params = _per_stat_xgb_params(stat)

    if method == "lgb":
        import lightgbm as lgb
        m = lgb.LGBMRegressor(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            learning_rate=params["learning_rate"],
            subsample=params["subsample"], subsample_freq=1,
            colsample_bytree=params["colsample_bytree"],
            min_child_samples=max(20, params["min_child_weight"] * 2),
            reg_lambda=params["reg_lambda"], reg_alpha=params["reg_alpha"],
            random_state=42, objective="quantile", alpha=0.5,
            n_jobs=-1, verbosity=-1,
        )
        m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])
        best_iter = int(getattr(m, "best_iteration_", -1) or -1)
        import joblib
        fname = f"quantile_pergame_lgb_{stat}_q50.pkl"
        joblib.dump(m, os.path.join(out_dir, fname))
    else:
        import xgboost as xgb
        m = xgb.XGBRegressor(
            **{k: v for k, v in params.items() if k != "random_state"},
            random_state=42, objective="reg:quantileerror", quantile_alpha=0.5,
            early_stopping_rounds=40, eval_metric="mae",
        )
        m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
        best_iter = int(getattr(m, "best_iteration", -1) or -1)
        fname = f"quantile_pergame_{stat}_q50.json"
        m.save_model(os.path.join(out_dir, fname))

    pred_val_raw = _inverse(stat, m.predict(X_val))
    val_pinball = float(np.mean(np.maximum(0.5 * (y_val - pred_val_raw),
                                           -0.5 * (y_val - pred_val_raw))))
    val_mae = float(mean_absolute_error(y_val, pred_val_raw))
    fit_secs = time.time() - t0
    print(f"  [{stat}] val_pinball={val_pinball:.4f}  val_mae={val_mae:.4f}  "
          f"fit={fit_secs:.1f}s  best_iter={best_iter}")

    return {
        "cutoff_date": cutoff_date, "stat": stat, "method": method,
        "n_train": train_end, "n_val": n_pre - train_end,
        "val_pinball_q50": val_pinball, "val_mae": val_mae,
        "model_filename": fname,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_secs, "best_iteration": best_iter,
        "n_features": len(fcols),
        "n_total_rows": n_all, "n_pre_cutoff_rows": n_pre,
    }


def train_blend(stat: str, cutoff_date: str, out_dir: str) -> dict:
    """Train pts/ast blend model via prop_pergame.train_pergame_models."""
    pre_rows, fcols, n_all = _get_dataset_at_cutoff(cutoff_date)
    print(f"\n  [{stat}] blend retrain  cutoff={cutoff_date}  n_pre={len(pre_rows)}")
    t0 = time.time()
    original_build = pg.build_pergame_dataset
    cutoff = datetime.fromisoformat(cutoff_date)
    n_holders = {"n_all": n_all, "n_pre": len(pre_rows)}

    def _filtered_build(gamelog_dir=None, **kw):
        rows, fcols2 = original_build(gamelog_dir, **kw)
        n_holders["n_all"] = len(rows)
        filtered = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
        n_holders["n_pre"] = len(filtered)
        return filtered, fcols2

    pg.build_pergame_dataset = _filtered_build
    try:
        metrics = pg.train_pergame_models(model_dir=out_dir, stats=[stat])
    finally:
        pg.build_pergame_dataset = original_build

    sm = (metrics.get("stats") or {}).get(stat, {})
    fit_secs = time.time() - t0
    val_mae = float(sm.get("holdout_mae") or sm.get("val_mae") or 0.0)
    print(f"  [{stat}] holdout_mae={val_mae:.4f}  fit={fit_secs:.1f}s")

    method_map = {"pts": "sqrt_huber_blend", "ast": "log1p_multitask_mlp_blend"}
    return {
        "cutoff_date": cutoff_date, "stat": stat,
        "method": method_map.get(stat, "blend"),
        "n_train": metrics.get("n_train", 0),
        "n_val": metrics.get("n_val", 0),
        "n_holdout": metrics.get("n_holdout", 0),
        "val_mae": val_mae,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_secs,
        "n_features": len(fcols),
        "n_total_rows": n_holders["n_all"],
        "n_pre_cutoff_rows": n_holders["n_pre"],
        "holdout_r2": float(sm.get("holdout_r2") or 0.0),
    }


# ─── backtest engine ──────────────────────────────────────────────────────────

def _load_q50_model_from_dir(stat: str, model_dir: str):
    if stat in Q50_STATS_LGB:
        import joblib
        path = os.path.join(model_dir, f"quantile_pergame_lgb_{stat}_q50.pkl")
        if not os.path.exists(path):
            return None, path
        return joblib.load(path), path
    elif stat in Q50_STATS_XGB:
        import xgboost as xgb
        path = os.path.join(model_dir, f"quantile_pergame_{stat}_q50.json")
        if not os.path.exists(path):
            return None, path
        m = xgb.XGBRegressor()
        m.load_model(path)
        return m, path
    return None, ""


def _load_blend_artifacts(stat: str, model_dir: str) -> dict:
    import joblib
    import xgboost as xgb_lib
    a = {}
    xgb_path = os.path.join(model_dir, f"props_pg_{stat}.json")
    lgb_path = os.path.join(model_dir, f"props_pg_lgb_{stat}.pkl")
    mlp_path = os.path.join(model_dir, f"props_pg_mlp_{stat}.pkl")
    sca_path = os.path.join(model_dir, f"props_pg_mlp_scaler_{stat}.pkl")
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
            weights_all = json.load(open(wts_path, encoding="utf-8"))
            weights = weights_all.get(stat)
        except Exception:
            pass
    a["weights"] = weights
    return a


def _predict_q50(stat: str, model, feat_row: dict) -> float:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    return max(0.0, float(_inverse(stat, np.array([pred_t]))[0]))


def _inv_sqrt(v: float) -> float:
    return max(0.0, float(v)) ** 2


def _predict_pts_blend(artifacts: dict, feat_row: dict) -> Optional[float]:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    weights = artifacts.get("weights")
    if not weights:
        return None
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))
    parts: List[float] = []
    if artifacts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * _inv_sqrt(float(artifacts["xgb"].predict(X)[0])))
    if artifacts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * _inv_sqrt(float(artifacts["lgb"].predict(X)[0])))
    if (artifacts.get("mlp") is not None
            and artifacts.get("mlp_scaler") is not None
            and w_mlp > 0):
        Xs = artifacts["mlp_scaler"].transform(X)
        parts.append(w_mlp * _inv_sqrt(float(artifacts["mlp"].predict(Xs)[0])))
    return max(0.0, float(sum(parts))) if parts else None


def _predict_ast_blend(artifacts: dict, feat_row: dict) -> Optional[float]:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    weights = artifacts.get("weights")
    if not weights:
        return None
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))
    parts: List[float] = []

    def _inv_log1p(v: float) -> float:
        return max(0.0, float(np.expm1(max(0.0, v))))

    if artifacts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * _inv_log1p(float(artifacts["xgb"].predict(X)[0])))
    if artifacts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * _inv_log1p(float(artifacts["lgb"].predict(X)[0])))
    if (artifacts.get("mlp") is not None
            and artifacts.get("mlp_scaler") is not None
            and w_mlp > 0):
        Xs = artifacts["mlp_scaler"].transform(X)
        parts.append(w_mlp * _inv_log1p(float(artifacts["mlp"].predict(Xs)[0])))
    return max(0.0, float(sum(parts))) if parts else None


from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row,
    _resolve_player_id as _nba_api_resolve_player_id,
    _season_for_date,
    _classify_result,
    _recommend,
    _odds_to_decimal_profit,
)


def _resolve_player_id(name: str) -> Optional[int]:
    pid = _nba_api_resolve_player_id(name)
    if pid is None:
        pid = _local_resolve_player_id(name)
    return pid


def _load_eval_rows(eval_start: str) -> List[dict]:
    """Load CSV rows for the late-2026 eval window only."""
    cutoff_dt = datetime.fromisoformat(eval_start)
    all_rows: List[dict] = []
    # RS: only rows >= eval_start
    if os.path.exists(RS_CSV):
        with open(RS_CSV, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    d = datetime.fromisoformat(r["date"])
                except Exception:
                    continue
                if d >= cutoff_dt:
                    r["_slice"] = "regular_season_late_2026"
                    all_rows.append(r)
    else:
        print(f"  WARN: {RS_CSV} not found")
    # Playoffs: all rows (playoffs are post-Feb by definition)
    if os.path.exists(PL_CSV):
        with open(PL_CSV, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                r["_slice"] = "playoffs_2025_26"
                all_rows.append(r)
    else:
        print(f"  WARN: {PL_CSV} not found")
    print(f"  Late-2026 eval rows loaded: {len(all_rows)} "
          f"(RS>={eval_start}: {sum(1 for r in all_rows if r['_slice']=='regular_season_late_2026')}, "
          f"PL: {sum(1 for r in all_rows if r['_slice']=='playoffs_2025_26')})")
    return all_rows


def run_backtest_late_2026(model_dir: str, label: str, eval_start: str) -> dict:
    """Run backtest on ONLY the late-2026 eval window (post eval_start)."""
    print(f"\n{'='*65}")
    print(f"  BACKTEST [{label}] — Late-2026 window (>= {eval_start})")
    print(f"  model_dir: {model_dir}")
    print(f"{'='*65}")

    all_stats = Q50_STATS_XGB | Q50_STATS_LGB | BLEND_STATS

    # Load models
    models = {}
    for stat in Q50_STATS_XGB | Q50_STATS_LGB:
        m, path = _load_q50_model_from_dir(stat, model_dir)
        if m is not None:
            models[stat] = ("q50", m)
            print(f"  loaded {stat:<5} q50 from {os.path.basename(path)}")
        else:
            print(f"  MISSING {stat:<5} ({path})")

    for stat in BLEND_STATS:
        art = _load_blend_artifacts(stat, model_dir)
        have = (art.get("xgb") is not None or art.get("lgb") is not None)
        if have and art.get("weights"):
            models[stat] = ("blend", art)
            print(f"  loaded {stat:<5} blend")
        else:
            print(f"  MISSING {stat:<5} blend artifacts")

    eval_rows = _load_eval_rows(eval_start)
    # Filter to only stats with loaded models
    eval_rows = [r for r in eval_rows if r.get("stat", "").lower() in models]
    print(f"  Eval rows after model filter: {len(eval_rows)}")
    if not eval_rows:
        return {"label": label, "per_stat": {}, "total_bets": 0, "total_roi_pct": 0.0}

    # Resolve players
    unique_names = sorted({r["player"] for r in eval_rows})
    name2pid = {nm: _resolve_player_id(nm) for nm in unique_names}
    resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Resolved {resolved}/{len(unique_names)} players")

    # Accumulate per stat
    per_stat: Dict[str, dict] = {
        s: {"n_pred": 0, "n_bets": 0, "wins": 0, "losses": 0, "pushes": 0,
            "mae_actual": [], "skip": defaultdict(int)}
        for s in models
    }

    row_cache = {}
    t0 = time.time()
    for i, r in enumerate(eval_rows):
        stat = r["stat"].lower()
        acc = per_stat[stat]
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            acc["skip"]["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            acc["skip"]["no_pid"] += 1
            continue
        season = _season_for_date(d)
        is_home = (r.get("venue", "") == "home")
        key = (pid, r["date"], r.get("venue", ""), r.get("opp", ""))
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r.get("opp", ""), d, season,
                is_home=is_home, rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            acc["skip"]["no_history"] += 1
            continue

        try:
            model_kind, model_obj = models[stat]
            if model_kind == "q50":
                pred = _predict_q50(stat, model_obj, feat)
            elif model_kind == "blend" and stat == "pts":
                pred = _predict_pts_blend(model_obj, feat)
                if pred is None:
                    acc["skip"]["model_missing"] += 1
                    continue
            elif model_kind == "blend" and stat == "ast":
                pred = _predict_ast_blend(model_obj, feat)
                if pred is None:
                    acc["skip"]["model_missing"] += 1
                    continue
            else:
                acc["skip"]["unknown_kind"] += 1
                continue
        except Exception as e:
            acc["skip"][f"err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)

        acc["n_pred"] += 1
        acc["mae_actual"].append(abs(pred - actual))
        if rec != "NO_BET":
            if actual_result == "PUSH":
                acc["pushes"] += 1
            else:
                acc["n_bets"] += 1
                if rec == actual_result:
                    acc["wins"] += 1
                else:
                    acc["losses"] += 1

        if (i + 1) % 2000 == 0:
            print(f"   ...{i+1}/{len(eval_rows)} ({time.time()-t0:.1f}s)")

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")

    profit_per_win = _odds_to_decimal_profit(-110)
    per_stat_summary = {}
    total_bets = total_wins = 0
    for s, acc in per_stat.items():
        bets = acc["n_bets"]
        wins = acc["wins"]
        roi_u = wins * profit_per_win - (bets - wins) * 1.0
        hit = (wins / bets) if bets else 0.0
        roi_pct = (roi_u / bets * 100.0) if bets else 0.0
        per_stat_summary[s] = {
            "n_pred": acc["n_pred"],
            "n_bets": bets,
            "wins": wins,
            "losses": acc["losses"],
            "pushes": acc["pushes"],
            "hit_rate": hit,
            "roi_pct": roi_pct,
            "roi_units": roi_u,
            "mae_actual": (sum(acc["mae_actual"]) / len(acc["mae_actual"])
                           if acc["mae_actual"] else 0.0),
            "skip": dict(acc["skip"]),
        }
        total_bets += bets
        total_wins += wins
        print(f"  {s.upper():<5} bets={bets}  hit={hit*100:.2f}%  ROI={roi_pct:+.2f}%")

    total_roi_u = total_wins * profit_per_win - (total_bets - total_wins) * 1.0
    total_hit = (total_wins / total_bets) if total_bets else 0.0
    total_roi_pct = (total_roi_u / total_bets * 100.0) if total_bets else 0.0
    print(f"  TOTAL bets={total_bets}  hit={total_hit*100:.2f}%  ROI={total_roi_pct:+.2f}%")

    return {
        "label": label,
        "per_stat": per_stat_summary,
        "total_bets": total_bets,
        "total_wins": total_wins,
        "total_roi_pct": total_roi_pct,
        "total_hit": total_hit,
        "elapsed_sec": elapsed,
        "eval_window_start": eval_start,
    }


# ─── comparison + ship logic ──────────────────────────────────────────────────

def compare_and_decide(prod_results: dict, cand_results: dict) -> dict:
    stats_order = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    improvements = []
    regressions = []
    rows = []

    for s in stats_order:
        prod_s = prod_results["per_stat"].get(s, {})
        cand_s = cand_results["per_stat"].get(s, {})
        p_roi = prod_s.get("roi_pct", 0.0)
        c_roi = cand_s.get("roi_pct", 0.0)
        p_n = prod_s.get("n_bets", 0)
        c_n = cand_s.get("n_bets", 0)
        delta = c_roi - p_roi
        # Stat counts as improved only if candidate has >= SHIP_MIN_BETS AND delta >= threshold
        improved = (c_n >= SHIP_MIN_BETS and delta >= SHIP_THRESHOLD_PP)
        rows.append({
            "stat": s,
            "prod_roi": p_roi,
            "cand_roi": c_roi,
            "delta_pp": delta,
            "prod_n_bets": p_n,
            "cand_n_bets": c_n,
            "improved": improved,
        })
        if improved:
            improvements.append(s)
        else:
            regressions.append(s)

    ship = len(improvements) >= SHIP_MIN_STATS
    decision = "SHIP" if ship else "REVERT"

    print(f"\n{'='*72}")
    print(f"  ITER-31 COMPARISON — Production (cutoff {PROD_CUTOFF_DATE}) "
          f"vs Candidate (cutoff {NEW_CUTOFF_DATE})")
    print(f"  Eval window: late-2026 (RS >= {EVAL_WINDOW_START} + all Playoffs)")
    print(f"{'='*72}")
    print(f"  {'Stat':<8}{'Prod ROI':>12}{'Cand ROI':>12}{'Delta':>10}{'P Bets':>8}{'C Bets':>8}  Decision")
    print(f"  {'-'*70}")
    for row in rows:
        tag = "IMPROVE" if row["improved"] else "-"
        c_note = " (insuf)" if row["cand_n_bets"] < SHIP_MIN_BETS and row["cand_n_bets"] > 0 else ""
        print(f"  {row['stat'].upper():<8}{row['prod_roi']:>+11.2f}%{row['cand_roi']:>+11.2f}%"
              f"{row['delta_pp']:>+9.2f}pp{row['prod_n_bets']:>8}{row['cand_n_bets']:>8}  {tag}{c_note}")
    print(f"  {'-'*70}")
    print(f"\n  Improvements: {len(improvements)}/7 stats (+{SHIP_THRESHOLD_PP}pp threshold, "
          f"need {SHIP_MIN_STATS}+, min {SHIP_MIN_BETS} bets): {improvements}")
    print(f"  Regressions:  {regressions}")
    print(f"\n  *** DECISION: {decision} ***")
    if ship:
        print(f"  -> Promote candidate (cutoff {NEW_CUTOFF_DATE}) to production")
    else:
        print(f"  -> Keep production models (cutoff {PROD_CUTOFF_DATE})")

    return {
        "decision": decision,
        "n_improvements": len(improvements),
        "improvements": improvements,
        "regressions": regressions,
        "rows": rows,
        "prod_total_roi": prod_results.get("total_roi_pct", 0.0),
        "cand_total_roi": cand_results.get("total_roi_pct", 0.0),
        "prod_total_bets": prod_results.get("total_bets", 0),
        "cand_total_bets": cand_results.get("total_bets", 0),
    }


def promote_candidate(candidate_dir: str, prod_dir: str) -> None:
    """Promote candidate artifacts to production directory."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    old_backup = os.path.join(os.path.dirname(prod_dir),
                              f"_backup_iter31_promoted_{ts}")
    print(f"\n  Promoting candidate to production...")
    print(f"  Backup old prod -> {old_backup}")
    os.makedirs(old_backup, exist_ok=True)
    for fname in os.listdir(prod_dir):
        if fname.startswith("_"):
            continue
        src = os.path.join(prod_dir, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(old_backup, fname))
    for fname in os.listdir(candidate_dir):
        src = os.path.join(candidate_dir, fname)
        dst = os.path.join(prod_dir, fname)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"    promoted: {fname}")


def update_holdout_baseline(cand_results: dict, eval_start: str) -> None:
    path = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
    existing = {}
    if os.path.exists(path):
        try:
            existing = json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    if "__global__" not in existing:
        existing["__global__"] = {}
    for s, d in cand_results["per_stat"].items():
        if d["n_bets"] > 0:
            existing["__global__"][s] = {
                "roi_pct": d["roi_pct"],
                "hit_rate": d["hit_rate"] * 100,
                "mae_actual": d.get("mae_actual", 0.0),
                "roi_units": d.get("roi_units", 0.0),
                "n_bets": d["n_bets"],
            }
    existing["__updated_at__"] = datetime.utcnow().isoformat() + "+00:00"
    existing["__source__"] = {
        "iter": "iter31",
        "note": f"cutoff shifted to {NEW_CUTOFF_DATE} (includes 2025-26 RS through Jan)",
        "eval_window": f">= {eval_start}",
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)
    print(f"  holdout_baseline.json updated: {path}")


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-train", action="store_true",
                    help="Skip training (use existing candidate artifacts)")
    ap.add_argument("--skip-prod-backtest", action="store_true",
                    help="Skip production backtest (load from cache)")
    args = ap.parse_args()

    t_global = time.time()

    print(f"\n=== ITER-31: Probe Later Cutoff (2026-02-01) ===")
    print(f"  New cutoff:   {NEW_CUTOFF_DATE}")
    print(f"  Prod cutoff:  {PROD_CUTOFF_DATE}")
    print(f"  Eval window:  >= {EVAL_WINDOW_START} (RS late + all playoffs)")
    print(f"  Ship gate:    {SHIP_MIN_STATS}+ stats improve >= {SHIP_THRESHOLD_PP}pp "
          f"(min {SHIP_MIN_BETS} bets each)")

    # Step 1: Backup is already done before launching this script.
    # Confirm backup exists.
    backups = [d for d in os.listdir(os.path.join(PROJECT_DIR, "data", "models"))
               if d.startswith("_backup_iter31_")]
    print(f"\n  Backup(s) confirmed: {backups}")

    # Step 2: Train candidate models
    os.makedirs(CANDIDATE_DIR, exist_ok=True)

    if args.skip_train:
        print(f"\n  [SKIP TRAIN] Using existing artifacts in {CANDIDATE_DIR}")
    else:
        print(f"\n=== TRAINING CANDIDATE MODELS (cutoff {NEW_CUTOFF_DATE}) ===")
        cand_meta = {"stats": {}, "cutoff": NEW_CUTOFF_DATE, "iter": "iter31"}

        for stat in sorted(Q50_STATS_LGB | Q50_STATS_XGB):
            try:
                r = train_q50(stat, NEW_CUTOFF_DATE, CANDIDATE_DIR)
                cand_meta["stats"][stat] = r
            except Exception as exc:
                print(f"  [WARN] {stat} train failed: {exc}")
                import traceback; traceback.print_exc()

        for stat in sorted(BLEND_STATS):
            try:
                r = train_blend(stat, NEW_CUTOFF_DATE, CANDIDATE_DIR)
                cand_meta["stats"][stat] = r
            except Exception as exc:
                print(f"  [WARN] {stat} train failed: {exc}")
                import traceback; traceback.print_exc()

        meta_path = os.path.join(CANDIDATE_DIR, "_meta.json")
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(cand_meta, fh, indent=2)
        print(f"\n  Candidate meta written -> {meta_path}")

    # Step 3: Production backtest on late-2026 window
    prod_cache_path = os.path.join(PROJECT_DIR, "data", "cache",
                                   "iter31_prod_late2026.json")
    if args.skip_prod_backtest and os.path.exists(prod_cache_path):
        print(f"\n  [SKIP PROD BACKTEST] Loading from {prod_cache_path}")
        prod_results = json.load(open(prod_cache_path, encoding="utf-8"))
    else:
        print(f"\n=== PRODUCTION BACKTEST (late-2026 window only) ===")
        prod_results = run_backtest_late_2026(
            OOS_PROD_DIR,
            f"PRODUCTION (cutoff {PROD_CUTOFF_DATE})",
            EVAL_WINDOW_START,
        )
        with open(prod_cache_path, "w", encoding="utf-8") as fh:
            json.dump(prod_results, fh, indent=2)
        print(f"  Production results cached -> {prod_cache_path}")

    # Step 4: Candidate backtest on late-2026 window
    print(f"\n=== CANDIDATE BACKTEST (late-2026 window only) ===")
    cand_results = run_backtest_late_2026(
        CANDIDATE_DIR,
        f"CANDIDATE (cutoff {NEW_CUTOFF_DATE})",
        EVAL_WINDOW_START,
    )

    # Step 5: Compare and decide
    comparison = compare_and_decide(prod_results, cand_results)

    # Step 6: Save comparison
    comparison_path = os.path.join(PROJECT_DIR, "data", "cache",
                                   "iter31_comparison.json")
    comparison["generated_at"] = datetime.utcnow().isoformat() + "Z"
    comparison["prod_cutoff"] = PROD_CUTOFF_DATE
    comparison["cand_cutoff"] = NEW_CUTOFF_DATE
    comparison["eval_window_start"] = EVAL_WINDOW_START
    comparison["prod_results"] = prod_results
    comparison["cand_results"] = cand_results
    with open(comparison_path, "w", encoding="utf-8") as fh:
        json.dump(comparison, fh, indent=2)
    print(f"\n  Comparison saved -> {comparison_path}")

    # Step 7: Ship or revert
    decision = comparison["decision"]
    if decision == "SHIP":
        print(f"\n=== SHIPPING: Promoting candidate to production ===")
        promote_candidate(CANDIDATE_DIR, OOS_PROD_DIR)
        update_holdout_baseline(cand_results, EVAL_WINDOW_START)
        print("\n  SHIP complete.")
        print("  NOTE: Iter-28 ensemble weights may need re-tuning in a follow-up "
              "(Iter 32). The ensemble loads OLD from _backup_iter22_promoted_* "
              "and NEW from oos_pre_playoffs; NEW just changed so re-sweep recommended.")
    else:
        print(f"\n  REVERT: Production models unchanged.")

    elapsed = time.time() - t_global
    print(f"\n=== TOTAL ELAPSED: {elapsed:.1f}s ===\n")
    return comparison


if __name__ == "__main__":
    main()
