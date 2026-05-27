"""retrain_iter26_gamelog_full_on_iter22.py — Iter-26 re-probe.

Re-test gamelog_full box-stat rolling features (14 cols) against the Iter-22
shifted-cutoff model (cutoff 2025-04-21, baseline +19.37% ROI on 1337 bets).

Hypothesis: gamelog_full REVERTed on the old pre-Iter-22 model (cutoff 2024-04-21)
because the OOS slice (2024 playoffs) was high-variance. With the new 2025-04-21
cutoff (2024-25 season in training) the signal may generalise on 2025-26.

Usage:
    python scripts/retrain_iter26_gamelog_full_on_iter22.py [--skip-train]

Outputs:
    data/models/oos_pre_playoffs/_candidate_iter26_gamelog_full/<artifacts>
    data/cache/iter26_gamelog_full_comparison.json

Ship gate: 4+/6 stats improve >=+0.5pp OOS ROI on 2025-26 (tov excluded — no baseline).

Strategy
--------
To include gamelog_full features in training, we temporarily edit prop_pergame.py
to uncomment the three disabled gamelog_full lines, rebuild the module, train, then
revert the edit before exiting — regardless of SHIP/REVERT outcome.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import re
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
CANDIDATE_DIR = os.path.join(OOS_PROD_DIR, "_candidate_iter26_gamelog_full")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")

Q50_STATS_LGB = {"reb"}
Q50_STATS_XGB = {"blk", "fg3m", "stl", "tov"}
BLEND_STATS = {"pts", "ast"}

SHIP_THRESHOLD_PP = 0.5   # >=+0.5pp ROI improvement per stat
SHIP_MIN_STATS = 4         # need 4+ of 6 gated stats (tov has no baseline)
THRESHOLD = 0.5            # betting edge cutoff

SLICES_2025_26 = [
    os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                 "regular_season_2025_26_oddsapi.csv"),
    os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                 "playoffs_2025_26_oddsapi.csv"),
]
BASELINE_PATH = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
PROP_PERGAME_PATH = os.path.join(PROJECT_DIR, "src", "prediction", "prop_pergame.py")


# ─── source-level enable/disable helpers ─────────────────────────────────────

def _read_src() -> str:
    return open(PROP_PERGAME_PATH, encoding="utf-8").read()


def _write_src(src: str) -> None:
    with open(PROP_PERGAME_PATH, "w", encoding="utf-8") as fh:
        fh.write(src)


def _enable_gamelog_full(src: str) -> str:
    """Uncomment the three gamelog_full lines in prop_pergame.py.

    Uses .find() + slice-replace to avoid em-dash encoding issues in
    string literals. Matches on the distinctive non-comment portions.
    """
    changes = 0

    # 1. feature_columns(): uncomment 'cols += list(_GAMELOG_FULL_FEATURE_KEYS)'
    # Match on the unique prefix "    # cols += list(_GAMELOG_FULL_FEATURE_KEYS)"
    MARKER1 = "    # cols += list(_GAMELOG_FULL_FEATURE_KEYS)"
    ENABLED1 = "    cols += list(_GAMELOG_FULL_FEATURE_KEYS)  # iter26-re-probe ENABLED"
    idx = src.find(MARKER1)
    if idx >= 0 and "iter26-re-probe ENABLED" not in src:
        # Find end of this line
        eol = src.find("\n", idx)
        src = src[:idx] + ENABLED1 + src[eol:]
        changes += 1
    elif "iter26-re-probe ENABLED" in src:
        pass  # idempotent
    else:
        print("  WARN: could not find feature_columns gamelog_full line to enable")

    # 2. build_pergame_dataset() loader
    MARKER2 = "    # gl_full_rolling = build_gamelog_full_rolling(gamelog_dir)"
    ENABLED2 = "    gl_full_rolling = build_gamelog_full_rolling(gamelog_dir)  # iter26"
    if MARKER2 in src:
        src = src.replace(MARKER2, ENABLED2, 1)
        changes += 1
    elif ENABLED2 in src:
        pass  # idempotent
    else:
        print("  WARN: could not find gamelog_full loader line to enable")

    # 3. build_pergame_dataset() usage
    MARKER3 = "                # feats.update(gl_full_rolling.features(file_player_id, gdate))"
    ENABLED3 = "                feats.update(gl_full_rolling.features(file_player_id, gdate))  # iter26"
    if MARKER3 in src:
        src = src.replace(MARKER3, ENABLED3, 1)
        changes += 1
    elif ENABLED3 in src:
        pass  # idempotent
    else:
        print("  WARN: could not find gamelog_full usage line to enable")

    # 4. _inject_iter23_features: add gamelog_full injection after linescore block
    INJECT_MARKER = "    # Iter-19: linescore blowout/pace context (7 ls_* keys).\n    try:\n        row.update(_get_linescore_context().features("
    INJECT_ADDITION = (
        "    # Iter-26 re-probe: gamelog_full rolling injection\n"
        "    try:\n"
        "        row.update(_get_gamelog_full_rolling().features(int(player_id), (\n"
        "            game_date.isoformat() if hasattr(game_date, 'isoformat') else str(game_date))))\n"
        "    except Exception:\n"
        "        row.update(_GAMELOG_FULL_DEFAULTS)\n"
        "    "
    )
    if INJECT_MARKER in src and "Iter-26 re-probe: gamelog_full" not in src:
        src = src.replace(INJECT_MARKER, INJECT_ADDITION + INJECT_MARKER, 1)
        changes += 1

    print(f"  _enable_gamelog_full: {changes} substitutions applied")
    return src


def _disable_gamelog_full(src: str) -> str:
    """Re-comment the gamelog_full lines — exact inverse of _enable."""
    changes = 0

    # 1. feature_columns()
    ENABLED1 = "    cols += list(_GAMELOG_FULL_FEATURE_KEYS)  # iter26-re-probe ENABLED"
    MARKER1 = "    # cols += list(_GAMELOG_FULL_FEATURE_KEYS)"
    if ENABLED1 in src:
        # Find end of this enabled line, replace with original
        idx = src.find(ENABLED1)
        eol = src.find("\n", idx)
        src = src[:idx] + MARKER1 + "  # 14 cols — DISABLED pending re-probe" + src[eol:]
        changes += 1

    # 2. loader
    ENABLED2 = "    gl_full_rolling = build_gamelog_full_rolling(gamelog_dir)  # iter26"
    MARKER2 = "    # gl_full_rolling = build_gamelog_full_rolling(gamelog_dir)"
    if ENABLED2 in src:
        src = src.replace(ENABLED2, MARKER2, 1)
        changes += 1

    # 3. usage
    ENABLED3 = "                feats.update(gl_full_rolling.features(file_player_id, gdate))  # iter26"
    MARKER3 = "                # feats.update(gl_full_rolling.features(file_player_id, gdate))"
    if ENABLED3 in src:
        src = src.replace(ENABLED3, MARKER3, 1)
        changes += 1

    # 4. injection block
    INJECT_ADDITION = (
        "    # Iter-26 re-probe: gamelog_full rolling injection\n"
        "    try:\n"
        "        row.update(_get_gamelog_full_rolling().features(int(player_id), (\n"
        "            game_date.isoformat() if hasattr(game_date, 'isoformat') else str(game_date))))\n"
        "    except Exception:\n"
        "        row.update(_GAMELOG_FULL_DEFAULTS)\n"
        "    "
    )
    if INJECT_ADDITION in src:
        src = src.replace(INJECT_ADDITION, "", 1)
        changes += 1

    print(f"  _disable_gamelog_full: {changes} reversals applied")
    return src


def _verify_enable(src: str) -> bool:
    """Return True if gamelog_full is visibly enabled."""
    has_feat = "iter26-re-probe ENABLED" in src
    has_loader = "build_gamelog_full_rolling(gamelog_dir)  # iter26" in src
    has_usage = "features(file_player_id, gdate))  # iter26" in src
    return has_feat and has_loader and has_usage


def _reload_pg():
    """Force reload of prop_pergame after source edit."""
    if "src.prediction.prop_pergame" in sys.modules:
        del sys.modules["src.prediction.prop_pergame"]
    # Also clear any cached submodules
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
    print(f"  Building dataset (cutoff < {CUTOFF_DATE})...")
    t0 = time.time()
    rows, fcols = pg.build_pergame_dataset()
    n_all = len(rows)
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre_rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre_rows.sort(key=lambda r: r["date"])
    elapsed = time.time() - t0
    print(f"  n_all={n_all}  n_pre_cutoff={len(pre_rows)}  n_fcols={len(fcols)}  {elapsed:.1f}s")
    if len(fcols) != 143:
        print(f"  WARN: expected 143 cols, got {len(fcols)}")
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
        "iter": "iter26_gamelog_full",
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
        "iter": "iter26_gamelog_full",
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
    def _pkl(name):
        p = os.path.join(model_dir, name)
        return joblib.load(p) if os.path.exists(p) else None
    def _json_m(name):
        p = os.path.join(model_dir, name)
        if not os.path.exists(p): return None
        m = xgb.XGBRegressor(); m.load_model(p); return m
    a["xgb"] = _json_m(f"props_pg_{stat}.json")
    a["lgb"] = _pkl(f"props_pg_lgb_{stat}.pkl")
    a["mlp"] = _pkl(f"props_pg_mlp_{stat}.pkl")
    a["mlp_scaler"] = _pkl(f"props_pg_mlp_scaler_{stat}.pkl")
    wts_path = os.path.join(model_dir, "meta_weights_pergame.json")
    a["weights"] = None
    if os.path.exists(wts_path):
        try:
            a["weights"] = json.load(open(wts_path, encoding="utf-8")).get(stat)
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
    for key, model in [("w_xgb", art.get("xgb")), ("w_lgb", art.get("lgb"))]:
        if model and float(w.get(key, 0)):
            parts.append(float(w[key]) * inv(float(model.predict(X)[0])))
    if art.get("mlp") and art.get("mlp_scaler") and float(w.get("w_mlp", 0)):
        Xs = art["mlp_scaler"].transform(X)
        parts.append(float(w["w_mlp"]) * inv(float(art["mlp"].predict(Xs)[0])))
    return max(0.0, sum(parts)) if parts else None


def _odds_profit(american=-110):
    return (american / 100.0) if american > 0 else (100.0 / abs(american))


def _classify(actual, line):
    return "OVER" if actual > line else ("UNDER" if actual < line else "PUSH")


def _recommend(edge, th):
    return "OVER" if edge > th else ("UNDER" if edge < -th else "NO_BET")


from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
)


def run_backtest(model_dir: str, label: str, fcols: List[str], pg) -> dict:
    print(f"\n{'='*65}")
    print(f"  BACKTEST [{label}]")
    print(f"  model_dir={os.path.basename(model_dir)}  fcols={len(fcols)}")
    print(f"{'='*65}")

    models: dict = {}
    for stat in sorted(Q50_STATS_XGB | Q50_STATS_LGB):
        m, p = _load_q50(stat, model_dir)
        if m is not None:
            models[stat] = ("q50", m)
            print(f"  loaded {stat:<5} q50")
        else:
            print(f"  MISSING {stat} ({p})")
    for stat in sorted(BLEND_STATS):
        art = _load_blend(stat, model_dir)
        if (art.get("xgb") or art.get("lgb")) and art.get("weights"):
            models[stat] = ("blend", art)
            print(f"  loaded {stat:<5} blend")
        else:
            print(f"  MISSING {stat} blend")

    all_rows = []
    for csv_path in SLICES_2025_26:
        if not os.path.exists(csv_path):
            print(f"  WARN: no CSV at {csv_path}")
            continue
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
        if a is None:
            continue
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
            if feat is not None:
                # Inject gamelog_full features
                try:
                    gl = pg._get_gamelog_full_rolling()
                    feat.update(gl.features(int(pid), d.isoformat()))
                except Exception:
                    feat.update(pg._GAMELOG_FULL_DEFAULTS)
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
                if rec == result:
                    a["wins"] += 1
                else:
                    a["losses"] += 1
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
            "mae_actual": (sum(a["mae"]) / len(a["mae"]) if a["mae"] else 0.0),
            "skip": dict(a["skip"]),
        }
        total_bets += bets; total_wins += wins
        print(f"  {s.upper():<5} bets={bets}  hit={hit*100:.1f}%  ROI={roi_pct:+.2f}%")

    total_roi_u = total_wins * profit_pw - (total_bets - total_wins)
    total_hit = (total_wins / total_bets) if total_bets else 0.0
    total_roi = (total_roi_u / total_bets * 100.0) if total_bets else 0.0
    print(f"  TOTAL bets={total_bets}  hit={total_hit*100:.1f}%  ROI={total_roi:+.2f}%")
    print(f"  Done in {time.time()-t0:.1f}s")

    return {
        "label": label, "per_stat": per_stat,
        "total_bets": total_bets, "total_wins": total_wins,
        "total_roi_pct": total_roi, "total_hit": total_hit,
    }


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
        if improved:
            improvements.append(s)
        elif has_base:
            regressions.append(s)

    gated = [r for r in rows if r["has_base"]]
    ship = len(improvements) >= SHIP_MIN_STATS

    print(f"\n{'='*72}")
    print(f"  ITER-26 DECISION — Iter-22 baseline vs Iter-26 (gamelog_full 14 cols)")
    print(f"  Validation: 2025-26 RS + Playoffs  |  Gate: {SHIP_MIN_STATS}+ of {len(gated)} "
          f"stats >= +{SHIP_THRESHOLD_PP}pp ROI (N>=30)")
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
    return {
        "decision": decision, "improvements": improvements,
        "regressions": regressions, "n_improvements": len(improvements),
        "n_gated": len(gated), "rows": rows,
        "cand_total_roi": cand_res.get("total_roi_pct", 0.0),
    }


def _load_baseline() -> dict:
    if not os.path.exists(BASELINE_PATH):
        return {}
    try:
        return json.load(open(BASELINE_PATH, encoding="utf-8")).get("__global__", {})
    except Exception:
        return {}


def promote(cand_dir, prod_dir):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bkp = os.path.join(os.path.dirname(prod_dir), f"_backup_iter26_promoted_{ts}")
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
    decision = "REVERT"  # default — overwritten on success
    comparison: dict = {}
    cand_res: dict = {"per_stat": {}, "total_bets": 0, "total_roi_pct": 0.0}
    baseline: dict = {}
    n_cols = 129
    bkp = ""
    orig_src = ""
    print(f"\n=== ITER-26: gamelog_full re-probe on Iter-22 (cutoff {CUTOFF_DATE}) ===")

    # Step 1: Backup
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    bkp = os.path.join(PROJECT_DIR, "data", "models", f"_backup_iter26_{ts_str}")
    os.makedirs(bkp, exist_ok=True)
    for f in os.listdir(OOS_PROD_DIR):
        if not f.startswith("_"):
            src = os.path.join(OOS_PROD_DIR, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(bkp, f))
    print(f"\n[1] Backed up {len(os.listdir(bkp))} prod files -> {os.path.basename(bkp)}")

    # Step 2: Read original source, enable gamelog_full, reload module
    print(f"\n[2] Enabling gamelog_full in prop_pergame.py")
    orig_src = _read_src()
    new_src = _enable_gamelog_full(orig_src)
    if not _verify_enable(new_src):
        print("  WARN: enable verification incomplete — some substitutions may have missed")
    _write_src(new_src)

    pg = None
    try:
        pg = _reload_pg()
        import src.prediction.prop_pergame as _pg_check
        n_cols = len(_pg_check.feature_columns())
        print(f"  feature_columns() = {n_cols} cols (expected 143)")

        # Step 3: Train or skip
        os.makedirs(CANDIDATE_DIR, exist_ok=True)
        meta: dict = {"stats": {}}
        results: dict = {}

        if not args.skip_train:
            print(f"\n[3] Training candidate models  (cutoff < {CUTOFF_DATE})")

            for stat in ["reb", "fg3m", "stl", "blk", "tov"]:
                try:
                    r = train_q50(stat, _pg_check, CANDIDATE_DIR)
                    meta["stats"][stat] = r; results[stat] = r
                except Exception as exc:
                    print(f"  [WARN] {stat} train FAILED: {exc}")
                    import traceback; traceback.print_exc()

            for stat in ["pts", "ast"]:
                try:
                    r = train_blend(stat, _pg_check, CANDIDATE_DIR)
                    meta["stats"][stat] = r; results[stat] = r
                except Exception as exc:
                    print(f"  [WARN] {stat} blend FAILED: {exc}")
                    import traceback; traceback.print_exc()

            meta.update({
                "iter": "iter26_gamelog_full",
                "n_features": n_cols,
                "cutoff": CUTOFF_DATE,
                "gamelog_full_keys": list(_pg_check._GAMELOG_FULL_FEATURE_KEYS),
            })
            with open(os.path.join(CANDIDATE_DIR, "_meta.json"), "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2)

            # Print MAE summary
            iter22_mae = {"pts": 4.5911, "reb": 1.9563, "ast": 1.3399,
                          "fg3m": 0.8690, "stl": 0.6676, "blk": 0.4054, "tov": 0.8395}
            print(f"\n  {'Stat':<7}{'Iter26':>12}{'Iter22':>12}{'Delta':>12}")
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
            meta_path = os.path.join(CANDIDATE_DIR, "_meta.json")
            if os.path.exists(meta_path):
                meta = json.load(open(meta_path, encoding="utf-8"))
            n_cols_meta = meta.get("n_features", n_cols)
            print(f"  Using existing candidate artifacts ({n_cols_meta} cols)")

        # Step 4: Backtest
        print(f"\n[4] Backtest candidate on 2025-26")
        fcols = _pg_check.feature_columns()
        cand_res = run_backtest(CANDIDATE_DIR, "iter26_gamelog_full", fcols, _pg_check)

        # Step 5: Decide
        print(f"\n[5] Compare vs Iter-22 baseline")
        baseline = _load_baseline()
        comparison = decide(baseline, cand_res)
        decision = comparison["decision"]

        # Step 6: Ship / Revert
        if decision == "SHIP":
            print(f"\n[6] SHIP — promoting to oos_pre_playoffs")
            promote(CANDIDATE_DIR, OOS_PROD_DIR)
            # Update meta
            meta_path = os.path.join(OOS_PROD_DIR, "_meta.json")
            try:
                ex = json.load(open(meta_path, encoding="utf-8"))
            except Exception:
                ex = {}
            ex.update({"iter": "iter26_gamelog_full", "n_features": n_cols,
                       "cutoff": CUTOFF_DATE,
                       "gamelog_full_keys": list(_pg_check._GAMELOG_FULL_FEATURE_KEYS),
                       "shipped_at": datetime.now().isoformat()})
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump(ex, fh, indent=2)
            # Keep the gamelog_full edit in prop_pergame.py (don't revert)
            print("\n  prop_pergame.py remains patched with gamelog_full ENABLED")
            print("  (gamelog_full lines are now permanently active)")
        else:
            print(f"\n[6] REVERT — restoring original prop_pergame.py")
            # Revert the source edit
            _write_src(orig_src)
            print("  prop_pergame.py restored to Iter-22 state (gamelog_full disabled)")

    except Exception as exc:
        print(f"\n[ERROR] Unexpected failure: {exc}")
        import traceback; traceback.print_exc()
        if orig_src:
            print("  SAFETY REVERT: restoring original prop_pergame.py")
            _write_src(orig_src)
        decision = "REVERT"

    # Always clean up module cache when not shipping
    if decision != "SHIP":
        for key in list(sys.modules.keys()):
            if "prop_pergame" in key:
                del sys.modules[key]

    # Step 7: Save results
    cache_dir = os.path.join(PROJECT_DIR, "data", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    results_path = os.path.join(cache_dir, "iter26_gamelog_full_comparison.json")
    try:
        gl_keys = list(
            sys.modules.get("src.prediction.prop_pergame",
                            __import__("src.prediction.prop_pergame",
                                        fromlist=["_GAMELOG_FULL_FEATURE_KEYS"],
                                        level=0))
            ._GAMELOG_FULL_FEATURE_KEYS
        )
    except Exception:
        gl_keys = []
    out = {
        "iter": "iter26_gamelog_full", "cutoff": CUTOFF_DATE,
        "n_features": n_cols,
        "gamelog_full_keys": gl_keys,
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
    print(f"\n=== ITER-26 COMPLETE: {decision} ({elapsed:.1f}s) ===")
    print(f"  Backup: {bkp}")
    if decision == "SHIP":
        print("  VAULT: vault/Models/Model Performance.md — update Iter-26 gamelog_full shipped")
        print("  VAULT: vault/Features/Signal Inventory.md — add 14 gl_* cols")
    else:
        print("  VAULT: vault/Improvements/Engineering Knowledge.md")
        print("    Iter-26: gamelog_full REVERTED again on Iter-22 cutoff")
        print("    Pattern confirmed: gamelog_full OOS drag persists regardless of training cutoff")

    return decision


if __name__ == "__main__":
    # Ensure `decision` is always defined for the finally block
    decision = "REVERT"
    main()
