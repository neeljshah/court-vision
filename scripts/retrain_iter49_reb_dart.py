"""retrain_iter49_reb_dart.py — Iter-49 DART booster for REB LGB-q50.

DART (Dropouts meet Multiple Additive Regression Trees) randomly drops trees
during boosting — a regularization mechanism that can improve generalization.
This iter tests DART on the REB LGB-q50 model (the only LGB-q50 stat).

Steps:
1. Load same data/features as iter-46 retrain (cutoff 2025-04-21).
2. Train DART candidate in  data/models/oos_pre_playoffs/_candidate_iter49_reb_dart/
3. Compare val_MAE vs production gbdt model.
4. Run OOS backtest on 2024-playoffs CSV for both models.
5. SHIP if REB ROI improves >=+1pp AND val_MAE doesn't regress >+0.05.
6. If shipped, promote + update _meta.json.

DART params tested:
    drop_rate=0.1, max_drop=50, skip_drop=0.5 (LGB defaults for DART)

Usage:
    python scripts/retrain_iter49_reb_dart.py [--force-ship] [--force-revert]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

import lightgbm as lgb
import joblib
from sklearn.metrics import mean_absolute_error

from src.prediction.prop_pergame import (
    build_pergame_dataset,
    feature_columns,
    _RECENCY_DECAY,
)
from src.prediction.prop_quantiles import _transform, _inverse, _per_stat_xgb_params
from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row, _resolve_player_id, _season_for_date,
    _classify_result, _recommend, _odds_to_decimal_profit,
)
from src.prediction.bet_thresholds import edge_threshold_for

# ── constants ──────────────────────────────────────────────────────────────────

STAT = "reb"
CUTOFF_DATE = "2025-04-21"
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
CANDIDATE_DIR = os.path.join(OOS_DIR, "_candidate_iter49_reb_dart")
BASELINE_DIR = os.path.join(OOS_DIR, "_candidate_iter49_reb_gbdt_baseline")
BACKUP_DIR = os.path.join(OOS_DIR, "_backup_pre_iter49")
PROD_MODEL_PATH = os.path.join(OOS_DIR, "quantile_pergame_lgb_reb_q50.pkl")
CANDIDATE_MODEL_PATH = os.path.join(CANDIDATE_DIR, "quantile_pergame_lgb_reb_q50.pkl")
BASELINE_MODEL_PATH = os.path.join(BASELINE_DIR, "quantile_pergame_lgb_reb_q50.pkl")
META_PATH = os.path.join(OOS_DIR, "_meta.json")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines", "playoffs_2024_canonical.csv")

# DART hyperparameters (LGB-specific)
DART_PARAMS = {
    "boosting_type": "dart",
    "drop_rate": 0.1,
    "max_drop": 50,
    "skip_drop": 0.5,
    "uniform_drop": False,
    "drop_seed": 42,
}

# Ship gate: ROI delta >= +1pp AND val_MAE delta <= +0.05
ROI_DELTA_THRESHOLD = 1.0   # pp
MAE_REGRESSION_CAP = 0.05   # abs units


# ── helpers ────────────────────────────────────────────────────────────────────

def _filter_and_sort(rows: List[dict], cutoff: datetime) -> List[dict]:
    pre = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre.sort(key=lambda r: r["date"])
    return pre


def _build_X(rows: List[dict], fcols: List[str]) -> np.ndarray:
    out = np.zeros((len(rows), len(fcols)), dtype=float)
    for i, r in enumerate(rows):
        for j, c in enumerate(fcols):
            v = r.get(c)
            if v is None:
                out[i, j] = float("nan")
            else:
                try:
                    out[i, j] = float(v)
                except (TypeError, ValueError):
                    out[i, j] = 0.0
    return out


def _sample_weights(rows: List[dict], train_end: int,
                    decay: float = _RECENCY_DECAY) -> np.ndarray:
    train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    return np.exp(-decay * age) if decay > 0 else np.ones(train_end)


def _top10(model: lgb.LGBMRegressor, fcols: List[str]) -> List[Tuple[str, float]]:
    try:
        imps = model.feature_importances_
    except AttributeError:
        return []
    return sorted(zip(fcols, imps), key=lambda x: x[1], reverse=True)[:10]


# ── training ───────────────────────────────────────────────────────────────────

def train_candidate(rows: List[dict]) -> dict:
    """Train DART candidate and save to CANDIDATE_DIR."""
    import csv as _csv

    fcols = feature_columns(STAT)
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all, n_pre = len(rows), len(pre)
    print(f"\n  [iter-49 DART] reb: {len(fcols)} features, n_pre={n_pre}", flush=True)

    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = _build_X(pre, fcols)
    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    sw = _sample_weights(pre, train_end)

    y = np.array([r[f"target_{STAT}"] for r in pre], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(STAT, y_tr)
    yt_val = _transform(STAT, y_val)

    params = _per_stat_xgb_params(STAT)

    # DART model
    t0 = time.time()
    dart_m = lgb.LGBMRegressor(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"],
        subsample_freq=1,
        colsample_bytree=params["colsample_bytree"],
        min_child_samples=max(20, params["min_child_weight"] * 2),
        reg_lambda=params["reg_lambda"],
        reg_alpha=params.get("reg_alpha", 0.5),
        random_state=42,
        objective="quantile",
        alpha=0.5,
        n_jobs=-1,
        verbosity=-1,
        # DART-specific
        boosting_type=DART_PARAMS["boosting_type"],
        drop_rate=DART_PARAMS["drop_rate"],
        max_drop=DART_PARAMS["max_drop"],
        skip_drop=DART_PARAMS["skip_drop"],
        uniform_drop=DART_PARAMS["uniform_drop"],
    )
    # NOTE: DART does not support early_stopping (tree dropping changes semantics),
    # so we train for fixed n_estimators. For safety we use the same n_estimators
    # as gbdt but could increase. LGB docs recommend no early stopping for DART.
    dart_m.fit(X_tr, yt_tr, sample_weight=sw,
               callbacks=[lgb.log_evaluation(period=-1)])
    fit_secs = time.time() - t0

    pred_val = _inverse(STAT, np.array(dart_m.predict(X_val), dtype=float))
    val_mae = float(mean_absolute_error(y_val, pred_val))
    err = y_val - pred_val
    val_pinball = float(np.mean(np.maximum(0.5 * err, -0.5 * err)))
    print(f"  DART: val_mae={val_mae:.4f}  val_pinball={val_pinball:.4f}  ({fit_secs:.1f}s)",
          flush=True)

    top10 = _top10(dart_m, fcols)
    for rank, (name, imp) in enumerate(top10, 1):
        print(f"    #{rank:2d}  {name:<40}  {imp:.1f}", flush=True)

    os.makedirs(CANDIDATE_DIR, exist_ok=True)
    joblib.dump(dart_m, CANDIDATE_MODEL_PATH)
    # Write candidate _meta.json for feature_columns_for() in backtest
    cand_meta = {
        "stats": {
            STAT: {
                "iter": "iter49_dart_candidate",
                "cutoff_date": CUTOFF_DATE,
                "n_train": train_end,
                "n_total_rows": n_all,
                "n_pre_cutoff_rows": n_pre,
                "n_features": len(fcols),
                "feature_columns": fcols,
                "training_timestamp": datetime.now().isoformat(),
                "fit_seconds": fit_secs,
                "method": "lgb_dart_q50",
                "val_pinball": val_pinball,
                "val_mae": val_mae,
                "dart_params": DART_PARAMS,
                "top10": [(n, float(v)) for n, v in top10],
            }
        },
        "cutoff": CUTOFF_DATE,
        "iter": "iter49_dart_candidate",
        "updated_at": datetime.now().isoformat(),
    }
    with open(os.path.join(CANDIDATE_DIR, "_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(cand_meta, fh, indent=2)

    return {
        "val_mae": val_mae,
        "val_pinball": val_pinball,
        "fit_secs": fit_secs,
        "fcols": fcols,
        "top10": [(n, float(v)) for n, v in top10],
        "n_train": train_end,
        "n_pre": n_pre,
        "n_all": n_all,
    }


def train_gbdt_baseline(rows: List[dict]) -> dict:
    """Retrain gbdt baseline at 133 features for fair comparison.

    The pkl on disk was trained at 85 features (older iter). We need a fresh
    gbdt model at the same 133-feature schema used by the DART candidate.
    Saved to BASELINE_DIR — does NOT touch the production slot.
    """
    fcols = feature_columns(STAT)
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all, n_pre = len(rows), len(pre)
    print(f"\n  [iter-49 gbdt baseline] reb: {len(fcols)} features, n_pre={n_pre}", flush=True)

    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = _build_X(pre, fcols)
    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    sw = _sample_weights(pre, train_end)

    y = np.array([r[f"target_{STAT}"] for r in pre], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(STAT, y_tr)
    yt_val = _transform(STAT, y_val)

    params = _per_stat_xgb_params(STAT)
    t0 = time.time()
    gbdt_m = lgb.LGBMRegressor(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"],
        subsample_freq=1,
        colsample_bytree=params["colsample_bytree"],
        min_child_samples=max(20, params["min_child_weight"] * 2),
        reg_lambda=params["reg_lambda"],
        reg_alpha=params.get("reg_alpha", 0.5),
        random_state=42,
        objective="quantile",
        alpha=0.5,
        n_jobs=-1,
        verbosity=-1,
        boosting_type="gbdt",  # default, explicit for clarity
    )
    gbdt_m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw,
               callbacks=[lgb.early_stopping(40, verbose=False)])
    fit_secs = time.time() - t0

    pred_val = _inverse(STAT, np.array(gbdt_m.predict(X_val), dtype=float))
    val_mae = float(mean_absolute_error(y_val, pred_val))
    err = y_val - pred_val
    val_pinball = float(np.mean(np.maximum(0.5 * err, -0.5 * err)))
    print(f"  gbdt: val_mae={val_mae:.4f}  val_pinball={val_pinball:.4f}  ({fit_secs:.1f}s)",
          flush=True)

    os.makedirs(BASELINE_DIR, exist_ok=True)
    joblib.dump(gbdt_m, BASELINE_MODEL_PATH)

    return {
        "val_mae": val_mae,
        "val_pinball": val_pinball,
        "fit_secs": fit_secs,
        "fcols": fcols,
        "n_train": train_end,
        "n_pre": n_pre,
        "n_all": n_all,
    }


def get_prod_val_mae() -> float:
    """Extract production val_MAE from _meta.json."""
    try:
        meta = json.load(open(META_PATH, encoding="utf-8"))
        return float(meta["stats"][STAT].get("val_mae", float("nan")))
    except Exception as e:
        print(f"  [warn] Could not read prod val_mae from _meta.json: {e}")
        return float("nan")


# ── OOS backtest ───────────────────────────────────────────────────────────────

def _predict_with_model(model, fcols: List[str], feat_row: dict) -> float:
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in fcols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(STAT, np.array([pred_t]))[0])
    return max(0.0, pred)


def run_backtest(model, fcols: List[str], label: str) -> dict:
    """Run OOS backtest against 2024-playoffs CSV. Returns roi_pct, n_bets, hit."""
    import csv as _csv

    if not os.path.exists(CSV_PATH):
        print(f"  [skip backtest] CSV not found: {CSV_PATH}")
        return {"roi_pct": 0.0, "n_bets": 0, "hit_rate": 0.0, "mae_actual": 0.0}

    all_rows = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in _csv.DictReader(fh):
            if r.get("stat", "").lower() == STAT:
                all_rows.append(r)

    print(f"\n  Backtest [{label}]: {len(all_rows)} CSV rows for {STAT.upper()}", flush=True)
    if not all_rows:
        return {"roi_pct": 0.0, "n_bets": 0, "hit_rate": 0.0, "mae_actual": 0.0}

    name2pid = {nm: _resolve_player_id(nm)
                for nm in sorted({r["player"] for r in all_rows})}
    row_cache: dict = {}
    skip = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    mae_a: List[float] = []
    t0 = time.time()

    for r in all_rows:
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skip["no_pid"] += 1
            continue
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        key = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r["opp"], d, season, is_home=is_home, rest_days=2.0,
                gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skip["no_history"] += 1
            continue
        try:
            pred = _predict_with_model(model, fcols, feat)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, edge_threshold_for(STAT))
        n_pred += 1
        mae_a.append(abs(pred - actual))
        if rec != "NO_BET":
            if actual_result == "PUSH":
                pushes += 1
            else:
                n_bets += 1
                if rec == actual_result:
                    wins += 1
                else:
                    losses += 1

    elapsed = time.time() - t0
    profit = _odds_to_decimal_profit(-110)
    roi_u = wins * profit - (n_bets - wins) * 1.0
    hit = (wins / n_bets) if n_bets else 0.0
    roi_pct = (roi_u / n_bets * 100.0) if n_bets else 0.0
    mae_actual = sum(mae_a) / len(mae_a) if mae_a else 0.0

    print(f"  [{label}] n_pred={n_pred}  n_bets={n_bets}  "
          f"hit={hit*100:.2f}%  ROI={roi_pct:+.2f}%  MAE={mae_actual:.4f}  "
          f"({elapsed:.1f}s)", flush=True)
    if skip:
        print(f"  [{label}] skip={dict(skip)}", flush=True)

    return {
        "roi_pct": roi_pct, "n_bets": n_bets, "hit_rate": hit,
        "mae_actual": mae_actual, "wins": wins, "losses": losses,
        "pushes": pushes, "n_pred": n_pred,
    }


# ── backup / promote ───────────────────────────────────────────────────────────

def backup_production() -> None:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, "quantile_pergame_lgb_reb_q50.pkl")
    if os.path.exists(PROD_MODEL_PATH):
        shutil.copy2(PROD_MODEL_PATH, dst)
        print(f"  Backed up production model -> {dst}", flush=True)
    # also backup _meta.json
    dst_meta = os.path.join(BACKUP_DIR, "_meta.json")
    if os.path.exists(META_PATH):
        shutil.copy2(META_PATH, dst_meta)
        print(f"  Backed up _meta.json -> {dst_meta}", flush=True)


def promote_candidate(cand_result: dict) -> None:
    """Copy candidate model to production slot and update _meta.json."""
    shutil.copy2(CANDIDATE_MODEL_PATH, PROD_MODEL_PATH)
    print(f"  Promoted candidate -> {PROD_MODEL_PATH}", flush=True)

    # Update _meta.json
    all_meta: dict = {}
    if os.path.exists(META_PATH):
        try:
            all_meta = json.load(open(META_PATH, encoding="utf-8"))
        except Exception:
            all_meta = {}
    if "stats" not in all_meta:
        all_meta["stats"] = {}

    all_meta["stats"][STAT] = {
        "iter": "iter49",
        "cutoff_date": CUTOFF_DATE,
        "n_train": cand_result["n_train"],
        "n_total_rows": cand_result["n_all"],
        "n_pre_cutoff_rows": cand_result["n_pre"],
        "n_features": len(cand_result["fcols"]),
        "feature_columns": cand_result["fcols"],
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": cand_result["fit_secs"],
        "new_feature": "dart_booster",
        "method": "lgb_dart_q50",
        "val_pinball": cand_result["val_pinball"],
        "val_mae": cand_result["val_mae"],
        "dart_params": DART_PARAMS,
        "top10": cand_result["top10"],
    }
    all_meta["iter"] = "iter49"
    all_meta["cutoff"] = CUTOFF_DATE
    all_meta["updated_at"] = datetime.now().isoformat()

    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, indent=2)
    print(f"  _meta.json updated -> {META_PATH}", flush=True)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Iter-49: DART booster for REB LGB-q50")
    ap.add_argument("--force-ship", action="store_true",
                    help="Force ship regardless of gate")
    ap.add_argument("--force-revert", action="store_true",
                    help="Force revert regardless of gate")
    args = ap.parse_args()

    print("=" * 70)
    print(" iter-49: DART booster test for REB LGB-q50")
    print(f" DART params: drop_rate={DART_PARAMS['drop_rate']}  "
          f"max_drop={DART_PARAMS['max_drop']}  skip_drop={DART_PARAMS['skip_drop']}")
    print("=" * 70, flush=True)

    # 1. Backup production
    backup_production()

    # 2. Load dataset
    print("\n  Loading dataset...", flush=True)
    rows, _ = build_pergame_dataset(None)
    print(f"  Total rows: {len(rows)}", flush=True)

    # 3. Train DART candidate
    cand_result = train_candidate(rows)

    # 4. Train gbdt baseline at 133 features for fair comparison
    # (production pkl is stale at 85 features — can't run backtest against 133-col rows)
    print("\n  Training gbdt baseline at current feature schema (133 cols)...", flush=True)
    gbdt_result = train_gbdt_baseline(rows)

    mae_delta = cand_result["val_mae"] - gbdt_result["val_mae"]
    prod_meta_mae = get_prod_val_mae()
    print(f"\n  val_MAE comparison:")
    print(f"    gbdt baseline (fresh, 133 col): {gbdt_result['val_mae']:.4f}")
    print(f"    DART (candidate,  133 col):     {cand_result['val_mae']:.4f}")
    print(f"    delta (DART - gbdt):            {mae_delta:+.4f}")
    print(f"    (prod _meta.json val_mae was:   {prod_meta_mae:.4f})", flush=True)

    # 5. OOS backtest — gbdt baseline
    print("\n  Running OOS backtest on gbdt baseline...", flush=True)
    gbdt_model = joblib.load(BASELINE_MODEL_PATH)
    fcols = feature_columns(STAT)
    prod_bt = run_backtest(gbdt_model, fcols, "gbdt-baseline")

    # 6. OOS backtest — DART candidate
    print("\n  Running OOS backtest on DART candidate...", flush=True)
    dart_model = joblib.load(CANDIDATE_MODEL_PATH)
    dart_bt = run_backtest(dart_model, fcols, "DART-cand")

    roi_delta = dart_bt["roi_pct"] - prod_bt["roi_pct"]
    print(f"\n  ROI comparison:")
    print(f"    gbdt (production): {prod_bt['roi_pct']:+.2f}%  ({prod_bt['n_bets']} bets)")
    print(f"    DART (candidate):  {dart_bt['roi_pct']:+.2f}%  ({dart_bt['n_bets']} bets)")
    print(f"    delta_ROI:         {roi_delta:+.2f}pp", flush=True)

    # 7. Ship/revert decision
    mae_ok = (mae_delta <= MAE_REGRESSION_CAP)
    roi_ok = (roi_delta >= ROI_DELTA_THRESHOLD)

    print(f"\n  Gate check:")
    print(f"    ROI delta >= +{ROI_DELTA_THRESHOLD}pp:  {'PASS' if roi_ok else 'FAIL'} ({roi_delta:+.2f}pp)")
    print(f"    MAE delta <= +{MAE_REGRESSION_CAP}:    {'PASS' if mae_ok else 'FAIL'} ({mae_delta:+.4f})")

    if args.force_ship:
        decision = "SHIP"
    elif args.force_revert:
        decision = "REVERT"
    else:
        decision = "SHIP" if (roi_ok and mae_ok) else "REVERT"

    print(f"\n  DECISION: {decision}", flush=True)

    if decision == "SHIP":
        promote_candidate(cand_result)
        print("\n  SHIPPED: DART candidate promoted to production.", flush=True)
    else:
        print("\n  REVERTED: candidate stays in _candidate_iter49_reb_dart/", flush=True)
        print(f"  DART params tested: drop_rate={DART_PARAMS['drop_rate']}, "
              f"max_drop={DART_PARAMS['max_drop']}, skip_drop={DART_PARAMS['skip_drop']}")
        # Write vault note
        vault_dir = os.path.join(PROJECT_DIR, "vault", "Improvements")
        os.makedirs(vault_dir, exist_ok=True)
        note_path = os.path.join(vault_dir, "iter49_reb_dart_revert.md")
        with open(note_path, "w", encoding="utf-8") as fh:
            fh.write(f"""# Iter-49 DART booster — REVERT

**Date:** {datetime.now().strftime('%Y-%m-%d')}
**Stat:** REB LGB-q50
**Method:** DART booster (drop_rate={DART_PARAMS['drop_rate']}, max_drop={DART_PARAMS['max_drop']}, skip_drop={DART_PARAMS['skip_drop']}, uniform_drop={DART_PARAMS['uniform_drop']})

## Results
| metric | gbdt (baseline) | DART | delta |
|---|---|---|---|
| val_MAE | {gbdt_result['val_mae']:.4f} | {cand_result['val_mae']:.4f} | {mae_delta:+.4f} |
| OOS ROI | {prod_bt['roi_pct']:+.2f}% | {dart_bt['roi_pct']:+.2f}% | {roi_delta:+.2f}pp |
| n_bets | {prod_bt['n_bets']} | {dart_bt['n_bets']} | — |

## Note
Production pkl was stale at 85 features; gbdt baseline retrained at 133 features for fair comparison.

## Ship gate
- ROI delta >= +{ROI_DELTA_THRESHOLD}pp: {'PASS' if roi_ok else 'FAIL'}
- MAE delta <= +{MAE_REGRESSION_CAP}: {'PASS' if mae_ok else 'FAIL'}

## Verdict: REVERT
DART did not clear both gates.
Candidate preserved at: `data/models/oos_pre_playoffs/_candidate_iter49_reb_dart/`
Baseline preserved at:  `data/models/oos_pre_playoffs/_candidate_iter49_reb_gbdt_baseline/`
""")
        print(f"  Vault note written -> {note_path}", flush=True)

    # Final summary
    print("\n" + "=" * 70)
    print(" ITER-49 SUMMARY")
    print("=" * 70)
    print(f"  DART params: drop_rate={DART_PARAMS['drop_rate']}, "
          f"max_drop={DART_PARAMS['max_drop']}, skip_drop={DART_PARAMS['skip_drop']}")
    print(f"  val_MAE:  gbdt={gbdt_result['val_mae']:.4f}  DART={cand_result['val_mae']:.4f}  delta={mae_delta:+.4f}")
    print(f"  OOS ROI:  gbdt={prod_bt['roi_pct']:+.2f}%  DART={dart_bt['roi_pct']:+.2f}%  delta={roi_delta:+.2f}pp")
    print(f"  n_bets:   gbdt={prod_bt['n_bets']}  DART={dart_bt['n_bets']}")
    print(f"  DECISION: {decision}")
    print("=" * 70, flush=True)

    return decision


if __name__ == "__main__":
    main()
