"""iter27_q50_candidates.py - Iter-27 universal-q50 hypothesis test.

Tests XGB-q50 candidates for PTS, AST, REB (currently non-q50 stats) on the
Iter-22 model (cutoff 2025-04-21).

Hypothesis: q50 is the universal winning architecture. FG3M/STL/BLK earn
+18-37% ROI on the 2025-26 eval. PTS/AST/REB earn +11-23%. Does q50 lift them?

Usage:
    python scripts/iter27_q50_candidates.py [--skip-train] [--stat pts,ast,reb]

Candidates land at:
    data/models/oos_pre_playoffs/_candidate_iter27_pts_q50/
    data/models/oos_pre_playoffs/_candidate_iter27_ast_q50/
    data/models/oos_pre_playoffs/_candidate_iter27_reb_xgb_q50/

SHIP gate (per-stat independent):
    candidate ROI > production ROI + 2.0pp  AND  candidate val_MAE <= production val_MAE + 0.1

PROMOTE: overwrites oos_pre_playoffs production artifacts for that stat.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
CUTOFF_DATE = "2025-04-21"
THRESHOLD_MAP = {"pts": 0.7, "ast": 1.0, "reb": 1.5}

# CSV priority: extended OOS first (has 2000+ rows per stat), fallback to playoffs
EVAL_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines", "extended_oos_canonical.csv")
if not os.path.exists(EVAL_CSV):
    EVAL_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines", "playoffs_2024_canonical.csv")

# Per-stat XGB-q50 HPs (from _per_stat_xgb_params + specialised for q50 regime).
# We use the same HPs as prop_quantiles._per_stat_xgb_params since those were
# validated for the q50 regime on these stats.
_Q50_HPS = {
    "pts": dict(n_estimators=800, max_depth=6, learning_rate=0.025,
                subsample=0.8, colsample_bytree=0.9,
                min_child_weight=20, reg_lambda=4.0, reg_alpha=2.0, gamma=0.2),
    "ast": dict(n_estimators=800, max_depth=5, learning_rate=0.025,
                subsample=0.7, colsample_bytree=0.8,
                min_child_weight=20, reg_lambda=5.0, reg_alpha=0.5, gamma=0.2),
    "reb": dict(n_estimators=800, max_depth=3, learning_rate=0.025,
                subsample=0.7, colsample_bytree=0.9,
                min_child_weight=30, reg_lambda=4.0, reg_alpha=0.5, gamma=0.3),
}

_CANDIDATE_DIRS = {
    "pts": os.path.join(OOS_DIR, "_candidate_iter27_pts_q50"),
    "ast": os.path.join(OOS_DIR, "_candidate_iter27_ast_q50"),
    "reb": os.path.join(OOS_DIR, "_candidate_iter27_reb_xgb_q50"),
}

# Transform / inverse from prop_quantiles
from src.prediction.prop_quantiles import _transform, _inverse  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset,
    feature_columns_for,
    apply_garbage_time_haircut,
    _safe_mlp_scaler_transform,
)
from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _odds_to_decimal_profit,
)

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction
except Exception:
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_xgb_q50(stat: str, rows, fcols: List[str]) -> Tuple[object, dict]:
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error

    rows.sort(key=lambda r: r["date"])
    pre_cutoff = [r for r in rows if r["date"] < CUTOFF_DATE]
    post_cutoff = [r for r in rows if r["date"] >= CUTOFF_DATE]
    n_pre = len(pre_cutoff)
    print(f"  [{stat}] pre-cutoff={n_pre} post-cutoff={len(post_cutoff)} total={len(rows)}")

    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = np.array([[float(r.get(c, 0.0) or 0.0) for c in fcols] for r in pre_cutoff], dtype=float)
    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    y = np.array([r[f"target_{stat}"] for r in pre_cutoff], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(stat, y_tr)
    yt_val = _transform(stat, y_val)

    train_dates = [datetime.fromisoformat(pre_cutoff[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    params = _Q50_HPS[stat]
    print(f"  [{stat}] HPs={params}")
    t0 = time.time()
    m = xgb.XGBRegressor(
        **params,
        random_state=42,
        objective="reg:quantileerror",
        quantile_alpha=0.5,
        early_stopping_rounds=40,
        eval_metric="mae",
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    fit_secs = time.time() - t0
    best_iter = int(getattr(m, "best_iteration", -1) or -1)
    print(f"  [{stat}] fit={fit_secs:.1f}s best_iter={best_iter}")

    pred_val_t = m.predict(X_val)
    pred_val = _inverse(stat, pred_val_t)
    val_mae = float(mean_absolute_error(y_val, pred_val))
    err = y_val - pred_val
    val_pinball = float(np.mean(np.maximum(0.5 * err, -0.5 * err)))
    print(f"  [{stat}] val_MAE={val_mae:.4f} val_pinball={val_pinball:.4f}")

    cand_dir = _CANDIDATE_DIRS[stat]
    os.makedirs(cand_dir, exist_ok=True)
    json_path = os.path.join(cand_dir, f"quantile_pergame_{stat}_q50.json")
    m.save_model(json_path)

    meta = {
        "stat": stat, "method": "xgb_q50", "cutoff_date": CUTOFF_DATE,
        "n_train": train_end, "n_val": n_pre - train_end,
        "n_pre_cutoff_rows": n_pre, "n_total_rows": len(rows),
        "val_mae": val_mae, "val_pinball_q50": val_pinball,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_secs, "best_iteration": best_iter,
        "n_features": len(fcols), "hps": params,
        "model_filename": f"quantile_pergame_{stat}_q50.json",
        "feature_columns": fcols,
    }
    with open(os.path.join(cand_dir, "_meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"stats": {stat: meta}}, fh, indent=2)

    return m, meta


# ---------------------------------------------------------------------------
# Backtest helpers
# ---------------------------------------------------------------------------

def _load_candidate_model(stat: str):
    import xgboost as xgb
    cand_dir = _CANDIDATE_DIRS[stat]
    path = os.path.join(cand_dir, f"quantile_pergame_{stat}_q50.json")
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m


def _predict_candidate(stat: str, model, feat_row: dict, fcols: List[str]) -> float:
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in fcols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    return max(0.0, float(_inverse(stat, np.array([pred_t]))[0]))


def _load_production_pts():
    """Load production PTS sqrt+Huber blend from oos_pre_playoffs."""
    import xgboost as xgb
    import joblib

    arts: dict = {}
    xgb_path = os.path.join(OOS_DIR, "props_pg_pts.json")
    lgb_path = os.path.join(OOS_DIR, "props_pg_lgb_pts.pkl")
    mlp_path = os.path.join(OOS_DIR, "props_pg_mlp_pts.pkl")
    scaler_path = os.path.join(OOS_DIR, "props_pg_mlp_scaler_pts.pkl")
    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    cal_path = os.path.join(OOS_DIR, "calibration_pergame_pts.joblib")

    if os.path.exists(xgb_path):
        m = xgb.XGBRegressor(); m.load_model(xgb_path)
        arts["xgb"] = m
    arts["lgb"] = joblib.load(lgb_path) if os.path.exists(lgb_path) else None
    arts["mlp"] = joblib.load(mlp_path) if os.path.exists(mlp_path) else None
    arts["mlp_scaler"] = joblib.load(scaler_path) if os.path.exists(scaler_path) else None
    arts["cal"] = joblib.load(cal_path) if os.path.exists(cal_path) else None
    if os.path.exists(weights_path):
        try:
            arts["weights"] = json.load(open(weights_path, encoding="utf-8")).get("pts")
        except Exception:
            arts["weights"] = None
    return arts


def _predict_production_pts(arts: dict, feat_row: dict, fcols: List[str]) -> Optional[float]:
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in fcols]], dtype=float)
    w = arts.get("weights") or {}
    w_xgb = float(w.get("w_xgb", 0.0))
    w_lgb = float(w.get("w_lgb", 0.0))
    w_mlp = float(w.get("w_mlp", 0.0))
    parts: List[float] = []
    if arts.get("xgb") and w_xgb > 0:
        parts.append(w_xgb * max(0.0, float(arts["xgb"].predict(X)[0])) ** 2)
    if arts.get("lgb") and w_lgb > 0:
        parts.append(w_lgb * max(0.0, float(arts["lgb"].predict(X)[0])) ** 2)
    if arts.get("mlp") and arts.get("mlp_scaler") and w_mlp > 0:
        Xs = _safe_mlp_scaler_transform(arts["mlp_scaler"], X)
        parts.append(w_mlp * max(0.0, float(arts["mlp"].predict(Xs)[0])) ** 2)
    if not parts:
        return None
    pred = sum(parts)
    if arts.get("cal") is not None:
        try:
            pred = float(arts["cal"].predict([pred])[0])
        except Exception:
            pass
    return max(0.0, pred)


def _load_production_ast():
    """Load production AST log1p multitask MLP blend."""
    import xgboost as xgb
    import joblib

    arts: dict = {}
    xgb_path = os.path.join(OOS_DIR, "props_pg_ast.json")
    lgb_path = os.path.join(OOS_DIR, "props_pg_lgb_ast.pkl")
    mlp_path = os.path.join(OOS_DIR, "props_pg_mlp_ast.pkl")
    scaler_path = os.path.join(OOS_DIR, "props_pg_mlp_scaler_ast.pkl")
    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    cal_path = os.path.join(OOS_DIR, "calibration_pergame_ast.joblib")

    if os.path.exists(xgb_path):
        m = xgb.XGBRegressor(); m.load_model(xgb_path)
        arts["xgb"] = m
    arts["lgb"] = joblib.load(lgb_path) if os.path.exists(lgb_path) else None
    arts["mlp"] = joblib.load(mlp_path) if os.path.exists(mlp_path) else None
    arts["mlp_scaler"] = joblib.load(scaler_path) if os.path.exists(scaler_path) else None
    arts["cal"] = joblib.load(cal_path) if os.path.exists(cal_path) else None
    if os.path.exists(weights_path):
        try:
            arts["weights"] = json.load(open(weights_path, encoding="utf-8")).get("ast")
        except Exception:
            arts["weights"] = None
    return arts


def _predict_production_ast(arts: dict, feat_row: dict, fcols: List[str]) -> Optional[float]:
    """Predict AST using log1p blend. Same as PTS but expm1 inverse."""
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in fcols]], dtype=float)
    w = arts.get("weights") or {}
    w_xgb = float(w.get("w_xgb", 0.0))
    w_lgb = float(w.get("w_lgb", 0.0))
    w_mlp = float(w.get("w_mlp", 0.0))
    parts: List[float] = []
    if arts.get("xgb") and w_xgb > 0:
        parts.append(w_xgb * max(0.0, float(np.expm1(arts["xgb"].predict(X)[0]))))
    if arts.get("lgb") and w_lgb > 0:
        parts.append(w_lgb * max(0.0, float(np.expm1(arts["lgb"].predict(X)[0]))))
    if arts.get("mlp") and arts.get("mlp_scaler") and w_mlp > 0:
        Xs = _safe_mlp_scaler_transform(arts["mlp_scaler"], X)
        parts.append(w_mlp * max(0.0, float(np.expm1(arts["mlp"].predict(Xs)[0]))))
    if not parts:
        return None
    pred = sum(parts)
    if arts.get("cal") is not None:
        try:
            pred = float(arts["cal"].predict([pred])[0])
        except Exception:
            pass
    return max(0.0, pred)


def _load_production_reb():
    """Load production REB LGB-q50."""
    import joblib
    path = os.path.join(OOS_DIR, "quantile_pergame_lgb_reb_q50.pkl")
    if not os.path.exists(path):
        raise FileNotFoundError(f"REB LGB-q50 not found: {path}")
    return joblib.load(path)


def _predict_production_reb(model, feat_row: dict, fcols: List[str]) -> float:
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in fcols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    return max(0.0, float(_inverse("reb", np.array([pred_t]))[0]))


# ---------------------------------------------------------------------------
# Head-to-head backtest
# ---------------------------------------------------------------------------

def _roi_from_bets(wins: int, bets: int) -> float:
    if bets == 0:
        return 0.0
    profit = _odds_to_decimal_profit(-110)
    return (wins * profit - (bets - wins) * 1.0) / bets * 100.0


def backtest_stat(
    stat: str,
    cand_model,
    prod_predict_fn,  # callable(feat_row, fcols) -> float|None
    fcols: List[str],
) -> Tuple[dict, dict]:
    threshold = THRESHOLD_MAP[stat]
    all_rows_csv = []
    with open(EVAL_CSV, encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() == stat:
                all_rows_csv.append(r)
    print(f"  [{stat}] CSV rows: {len(all_rows_csv)}")

    name2pid = {nm: _resolve_player_id(nm)
                for nm in sorted({r["player"] for r in all_rows_csv})}
    n_res = sum(1 for v in name2pid.values() if v is not None)
    print(f"  [{stat}] player resolution: {n_res}/{len(name2pid)}")

    row_cache: dict = {}
    cand_w = cand_l = cand_bets = 0
    prod_w = prod_l = prod_bets = 0
    n_pred = 0
    cand_mae_l: List[float] = []
    prod_mae_l: List[float] = []
    skip_c: dict = defaultdict(int)
    skip_p: dict = defaultdict(int)

    t0 = time.time()
    for r in all_rows_csv:
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip_c["bad_row"] += 1; skip_p["bad_row"] += 1; continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skip_c["no_pid"] += 1; skip_p["no_pid"] += 1; continue

        season = _season_for_date(d)
        is_home = (r.get("venue") == "home")
        key = (pid, r["date"], r.get("venue"), r.get("opp"))
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r.get("opp", ""), d, season, is_home=is_home,
                rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skip_c["no_history"] += 1; skip_p["no_history"] += 1; continue

        n_pred += 1
        actual_result = _classify_result(actual, line)

        # Candidate
        try:
            cp = _predict_candidate(stat, cand_model, feat, fcols)
            cand_mae_l.append(abs(cp - actual))
            if abs(cp - line) > threshold:
                rec = "OVER" if cp > line else "UNDER"
                if actual_result != "PUSH":
                    cand_bets += 1
                    if rec == actual_result:
                        cand_w += 1
                    else:
                        cand_l += 1
        except Exception as e:
            skip_c[f"err:{type(e).__name__}"] += 1

        # Production
        try:
            pp = prod_predict_fn(feat, fcols)
            if pp is not None:
                prod_mae_l.append(abs(pp - actual))
                if abs(pp - line) > threshold:
                    rec = "OVER" if pp > line else "UNDER"
                    if actual_result != "PUSH":
                        prod_bets += 1
                        if rec == actual_result:
                            prod_w += 1
                        else:
                            prod_l += 1
            else:
                skip_p["model_missing"] += 1
        except Exception as e:
            skip_p[f"err:{type(e).__name__}"] += 1

    elapsed = time.time() - t0
    cand_roi = _roi_from_bets(cand_w, cand_bets)
    prod_roi = _roi_from_bets(prod_w, prod_bets)
    cand_hit = cand_w / cand_bets if cand_bets else 0.0
    prod_hit = prod_w / prod_bets if prod_bets else 0.0

    print(f"\n  [{stat}] n_pred={n_pred} elapsed={elapsed:.1f}s")
    print(f"    CANDIDATE  bets={cand_bets} hit={cand_hit*100:.2f}% ROI={cand_roi:+.2f}%  skip={dict(skip_c)}")
    print(f"    PRODUCTION bets={prod_bets} hit={prod_hit*100:.2f}% ROI={prod_roi:+.2f}%  skip={dict(skip_p)}")

    cand_result = {
        "n_pred": n_pred, "n_bets": cand_bets, "wins": cand_w, "losses": cand_l,
        "hit_rate": cand_hit, "roi_pct": cand_roi,
        "mae": sum(cand_mae_l) / len(cand_mae_l) if cand_mae_l else 0.0,
    }
    prod_result = {
        "n_pred": n_pred, "n_bets": prod_bets, "wins": prod_w, "losses": prod_l,
        "hit_rate": prod_hit, "roi_pct": prod_roi,
        "mae": sum(prod_mae_l) / len(prod_mae_l) if prod_mae_l else 0.0,
    }
    return cand_result, prod_result


# ---------------------------------------------------------------------------
# Ship gate and promotion
# ---------------------------------------------------------------------------

SHIP_ROI_DELTA_PP = 2.0  # candidate must beat production by >= 2pp ROI
SHIP_MAE_TOLERANCE = 0.1  # candidate MAE must not exceed production MAE + 0.1


def _ship_decision(stat: str, cand: dict, prod: dict, train_meta: dict) -> Tuple[str, str]:
    delta_roi = cand["roi_pct"] - prod["roi_pct"]
    delta_mae = cand["mae"] - prod["mae"]
    prod_mae_meta = train_meta.get("val_mae", 999.0)
    cand_mae_meta = train_meta.get("val_mae", 999.0)

    if cand["n_bets"] < 30:
        return "INCONCLUSIVE", f"only {cand['n_bets']} bets < 30"
    if delta_roi >= SHIP_ROI_DELTA_PP and delta_mae <= SHIP_MAE_TOLERANCE:
        return "SHIP", (
            f"delta_roi={delta_roi:+.2f}pp >= +{SHIP_ROI_DELTA_PP}pp threshold "
            f"AND delta_mae={delta_mae:+.4f} <= {SHIP_MAE_TOLERANCE} tolerance"
        )
    reasons = []
    if delta_roi < SHIP_ROI_DELTA_PP:
        reasons.append(f"delta_roi={delta_roi:+.2f}pp < +{SHIP_ROI_DELTA_PP}pp")
    if delta_mae > SHIP_MAE_TOLERANCE:
        reasons.append(f"delta_mae={delta_mae:+.4f} > {SHIP_MAE_TOLERANCE}")
    return "REVERT", " | ".join(reasons)


def _promote(stat: str) -> None:
    """Copy candidate artifacts to oos_pre_playoffs, overwriting production."""
    cand_dir = _CANDIDATE_DIRS[stat]
    # For q50 stats, the model filename is quantile_pergame_<stat>_q50.json
    # (XGB); also update _meta.json entry
    json_src = os.path.join(cand_dir, f"quantile_pergame_{stat}_q50.json")
    json_dst = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
    shutil.copy2(json_src, json_dst)
    print(f"  [promote] {stat}: {json_src} -> {json_dst}")

    # Update oos_pre_playoffs/_meta.json with candidate meta
    cand_meta_path = os.path.join(cand_dir, "_meta.json")
    prod_meta_path = os.path.join(OOS_DIR, "_meta.json")
    cand_meta_all = json.load(open(cand_meta_path, encoding="utf-8"))
    prod_meta_all: dict = {}
    if os.path.exists(prod_meta_path):
        try:
            prod_meta_all = json.load(open(prod_meta_path, encoding="utf-8"))
        except Exception:
            prod_meta_all = {}
    if "stats" not in prod_meta_all:
        prod_meta_all["stats"] = {}
    prod_meta_all["stats"][stat] = cand_meta_all["stats"][stat]
    prod_meta_all["cutoff"] = CUTOFF_DATE
    prod_meta_all["iter"] = "iter27"
    with open(prod_meta_path, "w", encoding="utf-8") as fh:
        json.dump(prod_meta_all, fh, indent=2)
    print(f"  [promote] _meta.json updated for {stat}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-train", action="store_true", help="Reuse existing candidate models")
    ap.add_argument("--stat", default="pts,ast,reb", help="Comma-separated stats to process")
    args = ap.parse_args()

    stats = [s.strip().lower() for s in args.stat.split(",") if s.strip()]
    print(f"\n{'='*65}")
    print(f"  ITER-27: q50 universal architecture test - stats={stats}")
    print(f"  cutoff={CUTOFF_DATE}  eval_csv={os.path.basename(EVAL_CSV)}")
    print(f"  SHIP gate: delta_ROI >= +{SHIP_ROI_DELTA_PP}pp AND delta_MAE <= +{SHIP_MAE_TOLERANCE}")
    print(f"{'='*65}\n")

    # Load dataset once (shared across stats)
    print("[data] Loading pergame dataset...")
    t0 = time.time()
    rows, fcols = build_pergame_dataset(None)
    print(f"[data] {len(rows)} rows, {len(fcols)} features, {time.time()-t0:.1f}s")

    # Production loaders (keyed by stat)
    prod_loaders = {
        "pts": (_load_production_pts, _predict_production_pts),
        "ast": (_load_production_ast, _predict_production_ast),
        "reb": (_load_production_reb, lambda model, feat, cols: _predict_production_reb(model, feat, cols)),
    }

    all_results = {}
    shipped_stats = []

    for stat in stats:
        print(f"\n{'-'*55}")
        print(f"  STAT: {stat.upper()}")
        print(f"{'-'*55}")

        # 1. Train candidate
        if args.skip_train and os.path.exists(
            os.path.join(_CANDIDATE_DIRS[stat], f"quantile_pergame_{stat}_q50.json")
        ):
            print(f"  [train] skipping (--skip-train) - loading existing model")
            cand_meta_path = os.path.join(_CANDIDATE_DIRS[stat], "_meta.json")
            if os.path.exists(cand_meta_path):
                cand_meta = json.load(open(cand_meta_path, encoding="utf-8"))["stats"][stat]
            else:
                cand_meta = {}
        else:
            print(f"  [train] Training XGB-q50 for {stat}...")
            _, cand_meta = train_xgb_q50(stat, rows, fcols)

        print(f"  [train] val_MAE={cand_meta.get('val_mae', '?'):.4f} val_pinball={cand_meta.get('val_pinball_q50', '?'):.4f}")

        # 2. Load candidate
        cand_model = _load_candidate_model(stat)

        # 3. Load production
        loader_fn, pred_fn = prod_loaders[stat]
        prod_model_or_arts = loader_fn()
        if stat == "pts":
            def prod_predict(feat_row, cols, _arts=prod_model_or_arts):
                return _predict_production_pts(_arts, feat_row, cols)
        elif stat == "ast":
            def prod_predict(feat_row, cols, _arts=prod_model_or_arts):
                return _predict_production_ast(_arts, feat_row, cols)
        else:  # reb
            def prod_predict(feat_row, cols, _m=prod_model_or_arts):
                return _predict_production_reb(_m, feat_row, cols)

        # Use the FROZEN feature columns from the oos_pre_playoffs _meta.json
        # (same schema as candidate was trained on)
        eval_fcols = feature_columns_for(stat, OOS_DIR)
        print(f"  [feat] eval feature cols: {len(eval_fcols)}")

        # 4. Backtest
        print(f"\n  [backtest] Running head-to-head vs {os.path.basename(EVAL_CSV)}...")
        cand_r, prod_r = backtest_stat(stat, cand_model, prod_predict, eval_fcols)

        # 5. Decision
        decision, rationale = _ship_decision(stat, cand_r, prod_r, cand_meta)
        delta_roi = cand_r["roi_pct"] - prod_r["roi_pct"]
        delta_mae = cand_r["mae"] - prod_r["mae"]

        print(f"\n  {'-'*50}")
        print(f"  {stat.upper()} HEAD-TO-HEAD:")
        print(f"    prod ROI:  {prod_r['roi_pct']:+.2f}%  (bets={prod_r['n_bets']}, hit={prod_r['hit_rate']*100:.2f}%)")
        print(f"    cand ROI:  {cand_r['roi_pct']:+.2f}%  (bets={cand_r['n_bets']}, hit={cand_r['hit_rate']*100:.2f}%)")
        print(f"    delta_ROI: {delta_roi:+.2f}pp  |  delta_MAE: {delta_mae:+.4f}")
        print(f"    DECISION:  {decision}")
        print(f"    Rationale: {rationale}")

        all_results[stat] = {
            "candidate": cand_r,
            "production": prod_r,
            "train_meta": {k: v for k, v in cand_meta.items() if k != "feature_columns"},
            "delta_roi": round(delta_roi, 4),
            "delta_mae": round(delta_mae, 4),
            "decision": decision,
            "rationale": rationale,
        }

        if decision == "SHIP":
            shipped_stats.append(stat)

    # 6. Promote shipped stats
    print(f"\n{'='*65}")
    print(f"  ITER-27 SUMMARY")
    print(f"{'='*65}")
    print(f"  stat | prod_ROI | cand_ROI | delta | n_bets | DECISION")
    print(f"  {'-'*60}")
    for stat in stats:
        res = all_results[stat]
        c = res["candidate"]
        p = res["production"]
        print(
            f"  {stat.upper():<4} | {p['roi_pct']:>+7.2f}% | {c['roi_pct']:>+7.2f}% | "
            f"{res['delta_roi']:>+6.2f}pp | {c['n_bets']:>6} | {res['decision']}"
        )

    if shipped_stats:
        print(f"\n  SHIPPING: {shipped_stats}")
        for stat in shipped_stats:
            _promote(stat)

        # Write report to vault
        vault_path = os.path.join(PROJECT_DIR, "vault", "Models", "Iter27 q50 Candidates.md")
        os.makedirs(os.path.dirname(vault_path), exist_ok=True)
        lines = [
            "# Iter-27 q50 Universal Architecture Test",
            f"",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d')}",
            f"**Hypothesis:** q50 is the universal winning architecture for PTS/AST/REB.",
            f"**Cutoff:** {CUTOFF_DATE}  **Eval CSV:** {os.path.basename(EVAL_CSV)}",
            f"",
            "## Results",
            "",
            "| stat | prod_ROI | cand_ROI | delta | n_bets | val_MAE | decision |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for stat in stats:
            res = all_results[stat]
            c = res["candidate"]
            p = res["production"]
            vm = res["train_meta"].get("val_mae", 0.0)
            lines.append(
                f"| {stat.upper()} | {p['roi_pct']:+.2f}% | {c['roi_pct']:+.2f}% | "
                f"{res['delta_roi']:+.2f}pp | {c['n_bets']} | {vm:.4f} | **{res['decision']}** |"
            )
        lines += ["", "## Per-stat rationales"]
        for stat in stats:
            lines.append(f"- **{stat.upper()}**: {all_results[stat]['rationale']}")
        lines += ["", f"## Shipped: {shipped_stats if shipped_stats else 'none'}"]
        with open(vault_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        print(f"\n  Vault report: {vault_path}")

        # Print dispatch_routing.json change instructions
        print(f"\n  IMPORTANT: prop_pergame._USE_Q50_STATS must be updated to include: {shipped_stats}")
        print(f"  (and _USE_LGB_Q50_STATS must be updated if reb ships to XGB)")
    else:
        print(f"\n  No candidates meet the ship gate. REVERT - production unchanged.")

    # Save JSON summary
    summary_path = os.path.join(PROJECT_DIR, "data", "cache", "iter27_q50_results.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump({
            "iter": "iter27", "timestamp": datetime.now().isoformat(),
            "cutoff": CUTOFF_DATE, "eval_csv": os.path.basename(EVAL_CSV),
            "shipped": shipped_stats,
            "results": {
                s: {k: v for k, v in res.items() if k != "train_meta"}
                for s, res in all_results.items()
            },
        }, fh, indent=2)
    print(f"\n  JSON summary: {summary_path}")
    print(f"\n{'='*65}")


if __name__ == "__main__":
    main()
