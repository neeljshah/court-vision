"""
test_xast.py — A3 channel: 4-fold WF test for AST, comparing baseline vs baseline + cv_xast_pred.

For each prop_pergame row, we compute a temporally-safe last-5 aggregate of the
player's PRIOR cv_xast_pred values from cv_features.  Where no prior exists,
the feature defaults to 0.0 and n_prior_xast=0.

We run two variants per fold:
  baseline: standard XGB+LGB blend on feature_columns('ast')
  + cv_xast_pred: same blend with one additional column (cv_xast_pred_l5)

Comparison: fold MAE baseline vs +cv, mean delta, folds_cv_better.

Usage:
    conda activate basketball_ai
    python scripts/test_xast.py
"""
from __future__ import annotations

import glob
import json
import logging
import os
import sqlite3
import sys
import time
import warnings
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_PATH      = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
SCHEDULE_DIR = os.path.join(PROJECT_DIR, "data", "nba", "schedule")


# ── schedule helpers (copied from build_xast for standalone operation) ────────

def _build_game_date_map() -> Dict[str, str]:
    game_date_map: Dict[str, str] = {}
    for f in glob.glob(os.path.join(SCHEDULE_DIR, "*.json")):
        try:
            with open(f) as fp:
                games = json.load(fp)
            for g in games:
                gid = g.get("game_id")
                date = g.get("date")
                if gid and date:
                    game_date_map[gid] = date
        except Exception:
            pass

    # Fill gaps via nearest neighbor
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT game_id FROM cv_features")
    cv_game_ids = [r[0] for r in c.fetchall()]
    conn.close()

    known_2526 = sorted(
        [(int(k), v) for k, v in game_date_map.items() if k.startswith("00225")],
        key=lambda x: x[0],
    )
    known_2425 = sorted(
        [(int(k), v) for k, v in game_date_map.items() if k.startswith("00224")],
        key=lambda x: x[0],
    )
    for gid in cv_game_ids:
        if gid in game_date_map:
            continue
        gid_int = int(gid)
        pool = known_2526 if gid.startswith("00225") else known_2425
        if pool:
            closest = min(pool, key=lambda x: abs(x[0] - gid_int))
            game_date_map[gid] = closest[1]

    return game_date_map


# ── cv_xast_pred loader ───────────────────────────────────────────────────────

def _load_xast_pred_history(
    game_date_map: Dict[str, str],
) -> Dict[int, List[Tuple[str, float]]]:
    """
    Returns {player_id: [(iso_date, pred_value), ...]} sorted oldest-first.
    Loads cv_xast_pred from cv_features DB.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT game_id, player_id, feature_value FROM cv_features "
        "WHERE feature_name='cv_xast_pred'"
    )
    rows = c.fetchall()
    conn.close()

    history: Dict[int, List[Tuple[str, float]]] = defaultdict(list)
    for game_id, player_id, pred in rows:
        date = game_date_map.get(game_id)
        if date and pred is not None:
            history[int(player_id)].append((date, float(pred)))

    for pid in history:
        history[pid].sort(key=lambda x: x[0])

    log.info("cv_xast_pred history: %d players", len(history))
    return dict(history)


def _get_xast_pred_l5(
    player_id: int,
    before_date: str,
    history: Dict[int, List[Tuple[str, float]]],
    n: int = 5,
) -> float:
    """Last-n cv_xast_pred mean for player STRICTLY before before_date. 0.0 if none."""
    entries = history.get(player_id)
    if not entries:
        return 0.0
    prior = [v for d, v in entries if d < before_date]
    if not prior:
        return 0.0
    return float(sum(prior[-n:]) / len(prior[-n:]))


# ── walk-forward test ─────────────────────────────────────────────────────────

def run_ast_wf_test(n_splits: int = 4) -> None:
    import numpy as np
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns

    # Step 1: build game_date_map and xast_pred_history
    log.info("Building game_date_map...")
    game_date_map = _build_game_date_map()

    log.info("Loading cv_xast_pred history from DB...")
    xast_history = _load_xast_pred_history(game_date_map)

    # Step 2: load prop_pergame dataset
    log.info("Loading prop_pergame dataset...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n_total = len(rows)
    log.info("  %d rows loaded, %d base features", n_total, len(fc))

    base_cols = feature_columns("ast")

    # Step 3: build feature matrices
    # Base features (baseline)
    log.info("Building base feature matrix...")
    X_base = np.array(
        [[float(r.get(c) or 0.0) for c in base_cols] for r in rows],
        dtype=np.float32,
    )

    # cv_xast_pred_l5 column (temporally safe: last 5 PRIOR predictions per player)
    log.info("Building cv_xast_pred_l5 column...")
    xast_col = np.zeros(n_total, dtype=np.float32)
    n_covered = 0
    for i, row in enumerate(rows):
        date_raw = row.get("date")
        date_iso = str(date_raw)[:10] if date_raw else None
        if "T" in (date_iso or ""):
            date_iso = date_iso[:10]  # type: ignore[index]
        pid = int(row.get("player_id") or 0)
        if pid and date_iso:
            val = _get_xast_pred_l5(pid, date_iso, xast_history)
            xast_col[i] = val
            if val > 0.0:
                n_covered += 1

    coverage_pct = 100.0 * n_covered / n_total
    log.info(
        "  cv_xast_pred_l5 coverage: %d / %d rows (%.1f%%) have at least 1 prior prediction",
        n_covered, n_total, coverage_pct,
    )

    # Combined feature matrix
    X_cv = np.column_stack([X_base, xast_col.reshape(-1, 1)])

    # Target
    y = np.array([float(r["target_ast"]) for r in rows], dtype=np.float32)

    # ── fold loop ────────────────────────────────────────────────────────────
    from datetime import datetime

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    fold_results = []

    print(f"\n{'='*70}")
    print(f"WF test: AST, 4 folds — baseline vs + cv_xast_pred_l5")
    print(f"Feature coverage: {coverage_pct:.1f}% rows have prior cv_xast_pred")
    print(f"{'='*70}\n")

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n_total * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n_total
        else:
            te_end = int(n_total * fold_ends[fold_idx + 1])

        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 5000 or (te_end - va_end) < 2000:
            log.warning("Fold %d too small — skip", fold_idx + 1)
            continue

        # Sample weights (recency decay)
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        t0 = time.time()
        print(f"[Fold {fold_idx+1}/{n_splits}]  tr={tr_end}  val={va_end-tr_end}  ho={te_end-va_end}")

        # Count coverage in holdout
        ho_covered = int(np.sum(xast_col[va_end:te_end] > 0.0))
        ho_size = te_end - va_end
        print(f"  Holdout cv_xast_pred_l5 coverage: {ho_covered}/{ho_size} ({100*ho_covered/ho_size:.1f}%)")

        def _train_eval(X_matrix: np.ndarray, tag: str) -> float:
            """Train XGB+LGB blend and return holdout MAE."""
            X_tr  = X_matrix[:tr_end].astype(np.float32)
            X_val = X_matrix[tr_end:va_end].astype(np.float32)
            X_ho  = X_matrix[va_end:te_end].astype(np.float32)
            y_tr  = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho  = y[va_end:te_end]

            xgb_m = xgb.XGBRegressor(
                n_estimators=500, max_depth=4, learning_rate=0.04,
                subsample=0.8, colsample_bytree=0.8,
                min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
                random_state=42,
                objective="reg:squarederror",
                device="cuda", tree_method="hist",
                early_stopping_rounds=40, eval_metric="mae",
                verbosity=0,
            )
            xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                      sample_weight=sw, verbose=False)

            lgb_m = lgb.LGBMRegressor(
                n_estimators=500, max_depth=4, learning_rate=0.04,
                subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                min_child_samples=20, reg_lambda=2.0, reg_alpha=0.5,
                random_state=42, objective="regression",
                n_jobs=-1, verbosity=-1,
            )
            lgb_m.fit(
                X_tr, y_tr,
                eval_set=[(X_val, y_val)],
                sample_weight=sw,
                callbacks=[lgb.early_stopping(40, verbose=False)],
            )

            # NNLS blend weights from validation
            xv = xgb_m.predict(X_val)
            lv = lgb_m.predict(X_val)
            blender = LinearRegression(positive=True, fit_intercept=False)
            blender.fit(np.column_stack([xv, lv]), y_val)
            w = blender.coef_
            if not (0.5 <= w.sum() <= 1.5):
                w = np.array([0.5, 0.5])

            # Holdout predictions
            xh = xgb_m.predict(X_ho)
            lh = lgb_m.predict(X_ho)
            pred = w[0] * xh + w[1] * lh
            mae = float(mean_absolute_error(y_ho, pred))
            return mae

        mae_base = _train_eval(X_base, "base")
        mae_cv   = _train_eval(X_cv,   "+cv")
        delta    = mae_cv - mae_base
        elapsed  = time.time() - t0

        fold_results.append({
            "fold": fold_idx + 1,
            "mae_base": round(mae_base, 4),
            "mae_cv": round(mae_cv, 4),
            "delta": round(delta, 4),
            "ho_covered_pct": round(100 * ho_covered / ho_size, 1),
        })
        print(
            f"  baseline={mae_base:.4f}  +cv={mae_cv:.4f}  delta={delta:+.4f}  "
            f"{'CV better' if delta < 0 else 'CV worse'}  ({elapsed:.0f}s)\n"
        )

    # ── summary ───────────────────────────────────────────────────────────────
    if not fold_results:
        log.error("No folds completed.")
        return

    import numpy as np
    maes_base = [f["mae_base"] for f in fold_results]
    maes_cv   = [f["mae_cv"]   for f in fold_results]
    deltas    = [f["delta"]    for f in fold_results]
    n_cv_better = sum(1 for d in deltas if d < 0)

    mean_base  = float(np.mean(maes_base))
    mean_cv    = float(np.mean(maes_cv))
    mean_delta = float(np.mean(deltas))

    verdict_data = {
        "ship": n_cv_better == len(fold_results) and mean_delta < 0,
        "n_cv_better": n_cv_better,
        "n_folds": len(fold_results),
        "mean_delta": round(mean_delta, 4),
    }

    print("\n" + "=" * 70)
    print("## A3 xAST Model - Focused WF Test (AST only, 4 folds)")
    print("=" * 70)

    print(f"\n  Feature coverage (rows with prior cv_xast_pred): {coverage_pct:.1f}%")
    print(f"  (Only {n_covered:,} of {n_total:,} rows have non-zero cv_xast_pred_l5)")

    print("\n### Focused WF test (AST only, 4 folds)")
    print(f"  {'fold':<6} {'baseline MAE':>14} {'+cv_xast_pred':>14} {'delta':>10}")
    print(f"  {'----':<6} {'------------':>14} {'-------------':>14} {'-----':>10}")
    for fr in fold_results:
        print(
            f"  {fr['fold']:<6} {fr['mae_base']:>14.4f} {fr['mae_cv']:>14.4f} {fr['delta']:>+10.4f}"
            f"   ho_cv_cov={fr['ho_covered_pct']:.1f}%"
        )
    print(f"  {'mean':<6} {mean_base:>14.4f} {mean_cv:>14.4f} {mean_delta:>+10.4f}")
    print(f"\n  Folds CV-better: {n_cv_better}/{len(fold_results)}")

    verdict = "SHIP" if verdict_data["ship"] else "REJECT"
    print(f"\n### Verdict: {verdict}")
    if verdict_data["ship"]:
        print(f"  4/4 folds CV-better AND mean delta < 0 ({mean_delta:+.4f})")
    else:
        print(f"  {n_cv_better}/{len(fold_results)} folds CV-better, mean delta = {mean_delta:+.4f}")

    # Honest read
    print("\n### Honest read")
    print(f"  cv_xast_pred_l5 coverage: {coverage_pct:.1f}% — {'SPARSE' if coverage_pct < 10 else 'OK'}")
    if coverage_pct < 10:
        print(
            "  WARNING: <10% coverage means 90%+ rows have cv_xast_pred_l5=0.0 (default).\n"
            "  The model may ignore this feature entirely (tree can't split on a constant).\n"
            "  Signal result reflects noise in the few covered rows, not real CV signal."
        )
    last_fold = fold_results[-1] if fold_results else None
    if last_fold:
        print(
            f"  Last fold (most recent data): delta={last_fold['delta']:+.4f} "
            f"({'survives' if last_fold['delta'] < 0 else 'does NOT survive'} on latest data)"
        )

    print("\n### Raw fold results")
    print(f"  {fold_results}")
    print("=" * 70 + "\n")

    # Save results
    out_path = os.path.join(PROJECT_DIR, "data", "models", "xast_wf_results.json")
    results_json = {
        "fold_results": fold_results,
        "mean_base_mae": round(mean_base, 4),
        "mean_cv_mae": round(mean_cv, 4),
        "mean_delta": round(mean_delta, 4),
        "n_cv_better": n_cv_better,
        "n_folds": len(fold_results),
        "coverage_pct": round(coverage_pct, 1),
        "verdict": verdict,
    }
    with open(out_path, "w") as f:
        json.dump(results_json, f, indent=2)
    log.info("Results saved to %s", out_path)


if __name__ == "__main__":
    run_ast_wf_test(n_splits=4)
