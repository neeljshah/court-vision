"""retrain_iter26_linescore_on_iter22.py — Iter-26b linescore re-probe.

Re-test Iter-19 linescore features (7 ls_* cols) against the Iter-22 model
(cutoff 2025-04-21). Gamelog_full (Iter-26a) REVERTED — trying linescores next.

Features:
    ls_blowout_pct_l5, ls_avg_total_l5, ls_avg_q1_pts_l5, ls_avg_q4_pts_l5,
    ls_garbage_time_pct_l5, ls_opp_avg_total_allowed_l5, ls_opp_q1_pts_allowed_l5
    Source: data/cache/linescore_context.parquet (already loaded in build_pergame_dataset)

The injection in build_pergame_dataset is ALREADY wired — linescore values are
computed but DROPPED because feature_columns() doesn't include _LS_FEATURE_KEYS.
We only need to enable the single commented line in feature_columns() and retrain.

Usage:
    python scripts/retrain_iter26_linescore_on_iter22.py [--skip-train]

Ship gate: 4+/6 stats improve >=+0.5pp OOS ROI on 2025-26.
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

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

CUTOFF_DATE = "2025-04-21"
OOS_PROD_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
CANDIDATE_DIR = os.path.join(OOS_PROD_DIR, "_candidate_iter26_linescore")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")

Q50_STATS_LGB = {"reb"}
Q50_STATS_XGB = {"blk", "fg3m", "stl", "tov"}
BLEND_STATS = {"pts", "ast"}

SHIP_THRESHOLD_PP = 0.5
SHIP_MIN_STATS = 4
THRESHOLD = 0.5

SLICES_2025_26 = [
    os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                 "regular_season_2025_26_oddsapi.csv"),
    os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                 "playoffs_2025_26_oddsapi.csv"),
]
BASELINE_PATH = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
PROP_PERGAME_PATH = os.path.join(PROJECT_DIR, "src", "prediction", "prop_pergame.py")


# ─── source patching ─────────────────────────────────────────────────────────

def _read_src() -> str:
    return open(PROP_PERGAME_PATH, encoding="utf-8").read()


def _write_src(src: str) -> None:
    with open(PROP_PERGAME_PATH, "w", encoding="utf-8") as fh:
        fh.write(src)


def _enable_linescore(src: str) -> str:
    """Uncomment cols += list(_LS_FEATURE_KEYS) in feature_columns()."""
    changes = 0
    MARKER = "    # cols += list(_LS_FEATURE_KEYS)"
    ENABLED = "    cols += list(_LS_FEATURE_KEYS)  # iter26b-linescore ENABLED"
    idx = src.find(MARKER)
    if idx >= 0 and "iter26b-linescore ENABLED" not in src:
        eol = src.find("\n", idx)
        src = src[:idx] + ENABLED + src[eol:]
        changes += 1
    elif "iter26b-linescore ENABLED" in src:
        pass  # idempotent
    else:
        print("  WARN: could not find _LS_FEATURE_KEYS comment to enable")
    print(f"  _enable_linescore: {changes} substitutions applied")
    return src


def _verify_enable(src: str) -> bool:
    return "iter26b-linescore ENABLED" in src


def _reload_pg():
    for key in list(sys.modules.keys()):
        if "prop_pergame" in key or "prop_quantiles" in key:
            del sys.modules[key]
    import src.prediction.prop_pergame as pg
    return pg


# ─── dataset cache ────────────────────────────────────────────────────────────

_DATASET_CACHE = None


def _get_dataset(pg):
    global _DATASET_CACHE
    if _DATASET_CACHE is not None:
        return _DATASET_CACHE
    print(f"  Building dataset (cutoff < {CUTOFF_DATE}, linescore enabled)...")
    t0 = time.time()
    rows, fcols = pg.build_pergame_dataset()
    n_all = len(rows)
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre_rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre_rows.sort(key=lambda r: r["date"])
    elapsed = time.time() - t0
    print(f"  n_all={n_all}  n_pre_cutoff={len(pre_rows)}  n_fcols={len(fcols)}  {elapsed:.1f}s")
    expected = 136  # 129 + 7 linescore cols
    if len(fcols) != expected:
        print(f"  WARN: expected {expected} cols, got {len(fcols)}")
    _DATASET_CACHE = (pre_rows, fcols, n_all)
    return _DATASET_CACHE


def _recency_weights(dates, n_train: int) -> np.ndarray:
    max_d = max(dates[:n_train])
    age = np.array([(max_d - d).days / 365.0 for d in dates[:n_train]], dtype=float)
    return np.exp(-0.5 * age)


# ─── per-stat trainers ────────────────────────────────────────────────────────

def train_q50(stat: str, pg, out_dir: str) -> dict:
    from sklearn.metrics import mean_absolute_error
    from src.prediction.prop_quantiles import _transform, _inverse, _per_stat_xgb_params

    pre_rows, fcols, n_all = _get_dataset(pg)
    method = "lgb" if stat in Q50_STATS_LGB else "xgb"
    print(f"\n  [{stat}] q50/{method}  n_cols={len(fcols)}")
    t0 = time.time()

    n_pre = len(pre_rows)
    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = np.array([[float(r.get(c, 0.0) or 0.0) for c in fcols]
                       for r in pre_rows], dtype=float)
    nan_mask = ~np.isfinite(X_all)
    if nan_mask.any():
        col_med = np.nanmedian(X_all[:train_end], axis=0)
        col_med = np.where(np.isfinite(col_med), col_med, 0.0)
        for ci in range(X_all.shape[1]):
            cm = nan_mask[:, ci]
            if cm.any():
                X_all[cm, ci] = col_med[ci]

    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    dates = [datetime.fromisoformat(pre_rows[i]["date"]) for i in range(n_pre)]
    sw = _recency_weights(dates, train_end)
    y = np.array([float(r.get(f"target_{stat}", 0.0) or 0.0) for r in pre_rows])
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(stat, y_tr)
    yt_val = _transform(stat, y_val)
    params = _per_stat_xgb_params(stat)
    os.makedirs(out_dir, exist_ok=True)

    if method == "lgb":
        import lightgbm as lgb
        m = lgb.LGBMRegressor(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            learning_rate=params["learning_rate"],
            subsample=params["subsample"], subsample_freq=1,
            colsample_bytree=params["colsample_bytree"],
            min_child_samples=max(20, params.get("min_child_weight", 20) * 2),
            reg_lambda=params["reg_lambda"], reg_alpha=params.get("reg_alpha", 0.0),
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

    pred_val = _inverse(stat, m.predict(X_val))
    val_pinball = float(np.mean(np.maximum(0.5 * (y_val - pred_val),
                                            -0.5 * (y_val - pred_val))))
    val_mae = float(mean_absolute_error(y_val, pred_val))
    fit_secs = time.time() - t0
    print(f"  [{stat}] val_mae={val_mae:.4f}  pinball={val_pinball:.4f}  "
          f"fit={fit_secs:.1f}s  iter={best_iter}")

    return {
        "cutoff_date": CUTOFF_DATE, "stat": stat, "method": method,
        "n_train": train_end, "n_val": n_pre - train_end,
        "val_pinball_q50": val_pinball, "val_mae": val_mae,
        "model_filename": fname,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_secs, "best_iteration": best_iter,
        "n_features": len(fcols), "hps": params,
        "n_total_rows": n_all, "n_pre_cutoff_rows": n_pre,
        "feature_columns": list(fcols),
        "iter": "iter26_linescore",
    }


def train_blend(stat: str, pg, out_dir: str) -> dict:
    pre_rows, fcols, n_all = _get_dataset(pg)
    print(f"\n  [{stat}] blend retrain  n_cols={len(fcols)}")
    t0 = time.time()
    orig_build = pg.build_pergame_dataset
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    n_holders: dict = {"n_all": n_all, "n_pre": len(pre_rows)}

    def _filtered(gamelog_dir=None, **kw):
        rows2, fc2 = orig_build(gamelog_dir, **kw)
        n_holders["n_all"] = len(rows2)
        filtered = [r for r in rows2 if datetime.fromisoformat(r["date"]) < cutoff]
        n_holders["n_pre"] = len(filtered)
        return filtered, fc2

    pg.build_pergame_dataset = _filtered
    try:
        metrics = pg.train_pergame_models(model_dir=out_dir, stats=[stat])
    finally:
        pg.build_pergame_dataset = orig_build

    sm = (metrics.get("stats") or {}).get(stat, {})
    val_mae = float(sm.get("holdout_mae") or sm.get("val_mae") or 0.0)
    fit_secs = time.time() - t0
    print(f"  [{stat}] holdout_mae={val_mae:.4f}  fit={fit_secs:.1f}s")

    method_map = {"pts": "sqrt_huber_blend", "ast": "log1p_multitask_mlp_blend"}
    return {
        "cutoff_date": CUTOFF_DATE, "stat": stat,
        "method": method_map.get(stat, "blend"),
        "n_train": sm.get("n_train", 0), "n_val": sm.get("n_val", 0),
        "n_holdout": sm.get("n_holdout", 0), "val_mae": val_mae,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_secs,
        "n_features": len(fcols), "n_total_rows": n_holders["n_all"],
        "n_pre_cutoff_rows": n_holders["n_pre"],
        "holdout_r2": float(sm.get("holdout_r2") or 0.0),
        "holdout_mae": val_mae, "feature_columns": list(fcols),
        "iter": "iter26_linescore",
        **({"meta_w_xgb": sm.get("meta_w_xgb"),
            "meta_w_lgb": sm.get("meta_w_lgb"),
            "meta_w_mlp": sm.get("meta_w_mlp")} if stat == "pts" else {}),
    }


# ─── backtest engine ──────────────────────────────────────────────────────────

def _load_q50(stat, model_dir):
    if stat in Q50_STATS_LGB:
        import joblib
        p = os.path.join(model_dir, f"quantile_pergame_lgb_{stat}_q50.pkl")
        return (joblib.load(p), p) if os.path.exists(p) else (None, p)
    import xgboost as xgb
    p = os.path.join(model_dir, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(p):
        return None, p
    m = xgb.XGBRegressor(); m.load_model(p)
    return m, p


def _load_blend(stat, model_dir):
    import joblib, xgboost as xgb
    a: dict = {}
    def _pkl(n): p = os.path.join(model_dir, n); return joblib.load(p) if os.path.exists(p) else None
    def _jm(n):
        p = os.path.join(model_dir, n)
        if not os.path.exists(p): return None
        m = xgb.XGBRegressor(); m.load_model(p); return m
    a["xgb"] = _jm(f"props_pg_{stat}.json")
    a["lgb"] = _pkl(f"props_pg_lgb_{stat}.pkl")
    a["mlp"] = _pkl(f"props_pg_mlp_{stat}.pkl")
    a["mlp_scaler"] = _pkl(f"props_pg_mlp_scaler_{stat}.pkl")
    wts = os.path.join(model_dir, "meta_weights_pergame.json")
    a["weights"] = None
    if os.path.exists(wts):
        try:
            a["weights"] = json.load(open(wts, encoding="utf-8")).get(stat)
        except Exception:
            pass
    return a


def _pred_q50(stat, m, row, fcols):
    from src.prediction.prop_quantiles import _inverse
    X = np.array([[float(row.get(c, 0.0) or 0.0) for c in fcols]], dtype=float)
    return max(0.0, float(_inverse(stat, m.predict(X))[0]))


def _pred_blend(stat, art, row, fcols):
    inv = (lambda v: max(0.0, float(v)) ** 2) if stat == "pts" \
          else (lambda v: max(0.0, float(np.expm1(max(0.0, v)))))
    X = np.array([[float(row.get(c, 0.0) or 0.0) for c in fcols]], dtype=float)
    w = art.get("weights") or {}
    parts = []
    for k, mdl in [("w_xgb", art.get("xgb")), ("w_lgb", art.get("lgb"))]:
        if mdl and float(w.get(k, 0)):
            parts.append(float(w[k]) * inv(float(mdl.predict(X)[0])))
    if art.get("mlp") and art.get("mlp_scaler") and float(w.get("w_mlp", 0)):
        Xs = art["mlp_scaler"].transform(X)
        parts.append(float(w["w_mlp"]) * inv(float(art["mlp"].predict(Xs)[0])))
    return max(0.0, sum(parts)) if parts else None


def _odds_profit(a=-110): return a/100.0 if a > 0 else 100.0/abs(a)
def _classify(v, l): return "OVER" if v > l else ("UNDER" if v < l else "PUSH")
def _recommend(e, t): return "OVER" if e > t else ("UNDER" if e < -t else "NO_BET")


from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
)


def run_backtest(model_dir: str, label: str, fcols: List[str], pg) -> dict:
    print(f"\n{'='*65}")
    print(f"  BACKTEST [{label}]  model_dir={os.path.basename(model_dir)}  fcols={len(fcols)}")
    print(f"{'='*65}")

    models: dict = {}
    for stat in sorted(Q50_STATS_XGB | Q50_STATS_LGB):
        m, p = _load_q50(stat, model_dir)
        if m is not None:
            models[stat] = ("q50", m); print(f"  loaded {stat:<5} q50")
        else:
            print(f"  MISSING {stat} ({p})")
    for stat in sorted(BLEND_STATS):
        art = _load_blend(stat, model_dir)
        if (art.get("xgb") or art.get("lgb")) and art.get("weights"):
            models[stat] = ("blend", art); print(f"  loaded {stat:<5} blend")
        else:
            print(f"  MISSING {stat} blend")

    all_rows = []
    for csv_path in SLICES_2025_26:
        if not os.path.exists(csv_path):
            print(f"  WARN: no CSV at {csv_path}"); continue
        with open(csv_path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("stat", "").lower() in models:
                    all_rows.append(r)
    print(f"  Total CSV rows: {len(all_rows)}")
    if not all_rows:
        return {"label": label, "per_stat": {}, "total_bets": 0, "total_roi_pct": 0.0}

    unique_names = sorted({r["player"] for r in all_rows})
    name2pid = {n: _resolve_player_id(n) for n in unique_names}
    print(f"  Resolved {sum(1 for v in name2pid.values() if v)}/{len(unique_names)} players")

    acc = {s: {"n_pred": 0, "n_bets": 0, "wins": 0, "losses": 0,
               "pushes": 0, "mae": [], "skip": defaultdict(int)}
           for s in models}
    row_cache: dict = {}
    t0 = time.time()

    for i, r in enumerate(all_rows):
        stat = r["stat"].lower()
        a = acc.get(stat)
        if a is None: continue
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            a["skip"]["bad_row"] += 1; continue
        pid = name2pid.get(r["player"])
        if pid is None:
            a["skip"]["no_pid"] += 1; continue
        season = _season_for_date(d)
        is_home = (r.get("venue", "") == "home")
        key = (pid, r["date"], r.get("venue", ""), r.get("opp", ""))
        if key not in row_cache:
            feat = _build_asof_row(
                pid, r.get("opp", ""), d, season,
                is_home=is_home, rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
            # _inject_iter23_features already injects linescore via _get_linescore_context()
            # _build_asof_row calls _inject_iter23_features so ls_* are already in feat
            row_cache[key] = feat
        feat = row_cache[key]
        if feat is None:
            a["skip"]["no_history"] += 1; continue

        try:
            kind, obj = models[stat]
            if kind == "q50":
                pred = _pred_q50(stat, obj, feat, fcols)
            else:
                pred = _pred_blend(stat, obj, feat, fcols)
                if pred is None:
                    a["skip"]["model_missing"] += 1; continue
        except Exception as e:
            a["skip"][f"err:{type(e).__name__}"] += 1; continue

        edge = pred - line
        result = _classify(actual, line)
        rec = _recommend(edge, THRESHOLD)
        a["n_pred"] += 1
        a["mae"].append(abs(pred - actual))
        if rec != "NO_BET":
            if result == "PUSH":
                a["pushes"] += 1
            else:
                a["n_bets"] += 1
                if rec == result: a["wins"] += 1
                else: a["losses"] += 1
        if (i + 1) % 2000 == 0:
            print(f"   ...{i+1}/{len(all_rows)} ({time.time()-t0:.1f}s)")

    profit_pw = _odds_profit(-110)
    per_stat: dict = {}
    total_bets = total_wins = 0
    for s, a in acc.items():
        bets = a["n_bets"]; wins = a["wins"]
        roi_u = wins * profit_pw - (bets - wins)
        hit = (wins / bets) if bets else 0.0
        roi_pct = (roi_u / bets * 100.0) if bets else 0.0
        per_stat[s] = {
            "n_pred": a["n_pred"], "n_bets": bets, "wins": wins,
            "losses": a["losses"], "pushes": a["pushes"],
            "hit_rate": hit, "roi_pct": roi_pct, "roi_units": roi_u,
            "mae_actual": sum(a["mae"]) / len(a["mae"]) if a["mae"] else 0.0,
            "skip": dict(a["skip"]),
        }
        total_bets += bets; total_wins += wins
        print(f"  {s.upper():<5} bets={bets}  hit={hit*100:.1f}%  ROI={roi_pct:+.2f}%")

    total_roi_u = total_wins * profit_pw - (total_bets - total_wins)
    total_hit = (total_wins / total_bets) if total_bets else 0.0
    total_roi = (total_roi_u / total_bets * 100.0) if total_bets else 0.0
    print(f"  TOTAL bets={total_bets}  hit={total_hit*100:.1f}%  ROI={total_roi:+.2f}%")
    print(f"  Done in {time.time()-t0:.1f}s")
    return {"label": label, "per_stat": per_stat, "total_bets": total_bets,
            "total_wins": total_wins, "total_roi_pct": total_roi, "total_hit": total_hit}


# ─── decision ─────────────────────────────────────────────────────────────────

def decide(baseline: dict, cand_res: dict) -> dict:
    stats_order = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    improvements, regressions, rows = [], [], []
    for s in stats_order:
        base = baseline.get(s, {})
        cand = cand_res["per_stat"].get(s, {})
        b_roi = base.get("roi_pct", 0.0)
        c_roi = cand.get("roi_pct", 0.0)
        c_n = cand.get("n_bets", 0)
        delta = c_roi - b_roi
        has_base = bool(base)
        improved = has_base and c_n >= 30 and delta >= SHIP_THRESHOLD_PP
        rows.append({"stat": s, "baseline_roi": b_roi, "cand_roi": c_roi,
                     "delta_pp": delta, "cand_n_bets": c_n,
                     "baseline_mae": base.get("mae_actual", 0.0),
                     "cand_mae": cand.get("mae_actual", 0.0),
                     "improved": improved, "has_base": has_base})
        if improved: improvements.append(s)
        elif has_base: regressions.append(s)

    gated = [r for r in rows if r["has_base"]]
    ship = len(improvements) >= SHIP_MIN_STATS

    print(f"\n{'='*72}")
    print(f"  ITER-26b DECISION — Iter-22 baseline vs Iter-26b (linescore 7 cols)")
    print(f"  Validation: 2025-26 RS + Playoffs  |  Gate: {SHIP_MIN_STATS}+ of {len(gated)} stats")
    print(f"{'='*72}")
    print(f"  {'Stat':<7}{'Baseline':>12}{'Candidate':>12}{'Delta':>10}{'N':>7}  Decision")
    print(f"  {'-'*62}")
    for row in rows:
        tag = "IMPROVE" if row["improved"] else ("-" if row["has_base"] else "NO_BASE")
        b_s = f"{row['baseline_roi']:+.2f}%" if row["has_base"] else "N/A"
        print(f"  {row['stat'].upper():<7}{b_s:>12}{row['cand_roi']:>+11.2f}%"
              f"{row['delta_pp']:>+9.2f}pp{row['cand_n_bets']:>7}  {tag}")
    print(f"  {'-'*62}")
    print(f"\n  Improvements: {len(improvements)}/{len(gated)} gated — {improvements}")
    print(f"  Regressions:  {regressions}")
    decision = "SHIP" if ship else "REVERT"
    print(f"\n  *** DECISION: {decision} ***")
    return {"decision": decision, "improvements": improvements,
            "regressions": regressions, "n_improvements": len(improvements),
            "n_gated": len(gated), "rows": rows,
            "cand_total_roi": cand_res.get("total_roi_pct", 0.0)}


def _load_baseline() -> dict:
    if not os.path.exists(BASELINE_PATH): return {}
    try:
        return json.load(open(BASELINE_PATH, encoding="utf-8")).get("__global__", {})
    except Exception:
        return {}


def promote(cand_dir, prod_dir):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bkp = os.path.join(os.path.dirname(prod_dir), f"_backup_iter26b_promoted_{ts}")
    os.makedirs(bkp, exist_ok=True)
    for f in os.listdir(prod_dir):
        if not f.startswith("_"):
            src = os.path.join(prod_dir, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(bkp, f))
    print(f"  Old prod backed up -> {os.path.basename(bkp)}")
    for f in os.listdir(cand_dir):
        src = os.path.join(cand_dir, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(prod_dir, f))
            print(f"    promoted: {f}")


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> str:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-train", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    decision = "REVERT"
    comparison: dict = {}
    cand_res: dict = {"per_stat": {}, "total_bets": 0, "total_roi_pct": 0.0}
    baseline: dict = {}
    n_cols = 129
    bkp = ""
    orig_src = ""

    print(f"\n=== ITER-26b: linescore re-probe on Iter-22 (cutoff {CUTOFF_DATE}) ===")

    # Step 1: Backup
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    bkp = os.path.join(PROJECT_DIR, "data", "models", f"_backup_iter26b_{ts_str}")
    os.makedirs(bkp, exist_ok=True)
    for f in os.listdir(OOS_PROD_DIR):
        if not f.startswith("_"):
            src = os.path.join(OOS_PROD_DIR, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(bkp, f))
    print(f"\n[1] Backed up {len(os.listdir(bkp))} prod files -> {os.path.basename(bkp)}")

    # Step 2: Enable linescore
    print(f"\n[2] Enabling linescore in prop_pergame.py")
    orig_src = _read_src()
    new_src = _enable_linescore(orig_src)
    if not _verify_enable(new_src):
        print("  WARN: enable verification failed — proceeding anyway")
    _write_src(new_src)

    try:
        pg = _reload_pg()
        import src.prediction.prop_pergame as _pg
        n_cols = len(_pg.feature_columns())
        print(f"  feature_columns() = {n_cols} cols (expected 136)")

        # Step 3: Train
        os.makedirs(CANDIDATE_DIR, exist_ok=True)
        meta: dict = {"stats": {}}
        results: dict = {}

        if not args.skip_train:
            print(f"\n[3] Training candidate models (cutoff < {CUTOFF_DATE}, {n_cols} cols)")

            for stat in ["reb", "fg3m", "stl", "blk", "tov"]:
                try:
                    r = train_q50(stat, _pg, CANDIDATE_DIR)
                    meta["stats"][stat] = r; results[stat] = r
                except Exception as exc:
                    print(f"  [WARN] {stat} FAILED: {exc}")
                    import traceback; traceback.print_exc()

            for stat in ["pts", "ast"]:
                try:
                    r = train_blend(stat, _pg, CANDIDATE_DIR)
                    meta["stats"][stat] = r; results[stat] = r
                except Exception as exc:
                    print(f"  [WARN] {stat} blend FAILED: {exc}")
                    import traceback; traceback.print_exc()

            meta.update({
                "iter": "iter26_linescore", "n_features": n_cols,
                "cutoff": CUTOFF_DATE,
                "linescore_keys": list(_pg._LS_FEATURE_KEYS),
            })
            with open(os.path.join(CANDIDATE_DIR, "_meta.json"), "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2)

            iter22_mae = {"pts": 4.5911, "reb": 1.9563, "ast": 1.3399,
                          "fg3m": 0.8690, "stl": 0.6676, "blk": 0.4054, "tov": 0.8395}
            print(f"\n  {'Stat':<7}{'Iter26b':>12}{'Iter22':>12}{'Delta':>12}")
            print(f"  {'-'*46}")
            for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
                r = results.get(stat)
                if not r:
                    print(f"  {stat:<7}{'FAIL':>12}"); continue
                nm = r.get("val_mae") or r.get("holdout_mae") or 0.0
                bm = iter22_mae.get(stat, 0.0)
                print(f"  {stat:<7}{nm:>12.4f}{bm:>12.4f}  {nm-bm:>+9.4f}")
        else:
            print(f"\n[3] Skipping training (--skip-train)")
            mp = os.path.join(CANDIDATE_DIR, "_meta.json")
            if os.path.exists(mp):
                meta = json.load(open(mp, encoding="utf-8"))

        # Step 4: Backtest
        print(f"\n[4] Backtest candidate on 2025-26")
        fcols = _pg.feature_columns()
        cand_res = run_backtest(CANDIDATE_DIR, "iter26_linescore", fcols, _pg)

        # Step 5: Decide
        print(f"\n[5] Compare vs Iter-22 baseline")
        baseline = _load_baseline()
        comparison = decide(baseline, cand_res)
        decision = comparison["decision"]

        # Step 6: Ship or Revert
        if decision == "SHIP":
            print(f"\n[6] SHIP — promoting to oos_pre_playoffs")
            promote(CANDIDATE_DIR, OOS_PROD_DIR)
            mp = os.path.join(OOS_PROD_DIR, "_meta.json")
            try:
                ex = json.load(open(mp, encoding="utf-8"))
            except Exception:
                ex = {}
            ex.update({"iter": "iter26_linescore", "n_features": n_cols,
                       "cutoff": CUTOFF_DATE,
                       "linescore_keys": list(_pg._LS_FEATURE_KEYS),
                       "shipped_at": datetime.now().isoformat()})
            with open(mp, "w", encoding="utf-8") as fh:
                json.dump(ex, fh, indent=2)
            print("\n  prop_pergame.py remains patched with linescore ENABLED")
        else:
            print(f"\n[6] REVERT — restoring original prop_pergame.py")
            _write_src(orig_src)
            print("  prop_pergame.py restored to Iter-22 state")

    except Exception as exc:
        print(f"\n[ERROR] Unexpected failure: {exc}")
        import traceback; traceback.print_exc()
        if orig_src:
            print("  SAFETY REVERT: restoring original prop_pergame.py")
            _write_src(orig_src)
        decision = "REVERT"

    # Cleanup module cache if not shipping
    if decision != "SHIP":
        for key in list(sys.modules.keys()):
            if "prop_pergame" in key:
                del sys.modules[key]

    # Step 7: Save results
    cache_dir = os.path.join(PROJECT_DIR, "data", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    results_path = os.path.join(cache_dir, "iter26_linescore_comparison.json")
    try:
        ls_keys = list(__import__("src.prediction.prop_pergame",
                                   fromlist=["_LS_FEATURE_KEYS"])._LS_FEATURE_KEYS)
    except Exception:
        ls_keys = []
    out = {
        "iter": "iter26_linescore", "cutoff": CUTOFF_DATE,
        "n_features": n_cols, "linescore_keys": ls_keys,
        "decision": decision, "comparison": comparison,
        "cand_backtest": cand_res,
        "baseline_snapshot": {s: {"roi_pct": v.get("roi_pct"),
                                   "mae_actual": v.get("mae_actual"),
                                   "n_bets": v.get("n_bets")}
                               for s, v in baseline.items() if not s.startswith("_")},
        "timestamp": datetime.now().isoformat(),
        "backup_dir": bkp,
    }
    with open(results_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n  Results: {results_path}")

    elapsed = time.time() - t0
    print(f"\n=== ITER-26b COMPLETE: {decision} ({elapsed:.1f}s) ===")
    print(f"  Backup: {bkp}")
    if decision == "SHIP":
        print("  VAULT: vault/Models/Model Performance.md — Iter-26b linescore shipped")
        print("  VAULT: vault/Features/Signal Inventory.md — add 7 ls_* cols")
    else:
        print("  VAULT: vault/Improvements/Engineering Knowledge.md")
        print("    Iter-26b: linescore REVERTED on Iter-22 cutoff — both feature sets rejected")
        print("    Feature ceiling confirmed: gamelog_full AND linescores both fail OOS gate")

    return decision


if __name__ == "__main__":
    main()
