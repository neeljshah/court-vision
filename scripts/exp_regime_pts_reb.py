"""exp_regime_pts_reb.py — Approach A4: minutes-REGIME mixture-of-experts.

Train a separate LightGBM expert per projected-minutes regime so each
specialises on the tails the flat model over-shrinks.  Tests two forms:
  - hard split: serve each ho row from its regime expert
  - residual expert: serve global + regime-specific residual correction

Also compares 4-bin (R1<18, R2 18-26, R3 26-34, R4 34+) vs
3-bin (<22, 22-32, 32+) by OOF MAE.

Run:
    python scripts/exp_regime_pts_reb.py

Writes: docs/_audits/PTS_REB_EXP_REGIME.md
"""
from __future__ import annotations

import os
import sys
import json
import warnings
from typing import List, Tuple, Dict, Optional

warnings.filterwarnings("ignore")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False
    print("WARNING: lightgbm not found — falling back to Ridge regression")
    from sklearn.linear_model import Ridge

from scripts._pts_oof_harness import (
    build_folds, feature_matrix, col_array, targets,
    recency_weights, load_base,
)
# score_and_report joins on (game_id, player_id, fold) but game_id is always ""
# in the base parquet. We use a local wrapper that patches game_id = game_date.
from scripts._pts_oof_harness import score_and_report as _score_and_report_orig


def score_and_report(recs, base, rows, label):
    """Wrapper: patches base.game_id = base.game_date so the join is unique."""
    import pandas as pd
    base_patched = base.copy()
    base_patched["game_id"] = base_patched["game_date"].astype(str)
    return _score_and_report_orig(recs, base_patched, rows, label)

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
FALLBACK_THRESHOLD = 800          # min tr rows per regime; below → global fallback
EARLY_STOP_ROUNDS = 50
MIN_FEATURES_MINUTES = [          # features for the minutes head
    "l5_min", "l10_min", "std_min", "ewma_min", "prev_min",
    "rest_days", "is_b2b", "is_b3b", "days_since_last_game",
    "games_since_long_absence", "games_played", "is_home",
]

BINS_4 = [0.0, 18.0, 26.0, 34.0, 9999.0]
BINS_3 = [0.0, 22.0, 32.0, 9999.0]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def assign_regime(proj_min: np.ndarray, bins: List[float]) -> np.ndarray:
    """0-indexed regime assignment given projected minutes and bin edges."""
    regime = np.full(len(proj_min), len(bins) - 2, dtype=int)
    for i in range(len(bins) - 2, -1, -1):
        regime[proj_min < bins[i + 1]] = i
    return regime


def _lgb_train(X_tr, y_tr, X_va, y_va,
               n_estimators=500, lr=0.05, max_depth=5,
               sample_weight=None) -> "lgb.Booster":
    dtrain = lgb.Dataset(X_tr, y_tr, weight=sample_weight, free_raw_data=False)
    dval   = lgb.Dataset(X_va, y_va, reference=dtrain, free_raw_data=False)
    params = dict(
        objective="regression_l1",
        metric="mae",
        learning_rate=lr,
        max_depth=max_depth,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.7,
        verbose=-1,
        n_jobs=-1,
    )
    cb = lgb.early_stopping(EARLY_STOP_ROUNDS, verbose=False)
    model = lgb.train(
        params, dtrain,
        num_boost_round=n_estimators,
        valid_sets=[dval],
        callbacks=[cb],
    )
    return model


def _fallback_predict(X, model) -> np.ndarray:
    if HAS_LGB and isinstance(model, lgb.Booster):
        return model.predict(X)
    return model.predict(X)


# ---------------------------------------------------------------------------
# minutes head: train on rows[:tr_end], project ALL of tr + ho
# ---------------------------------------------------------------------------

def train_minutes_head(rows_tr: list, rows_va: list) -> object:
    """Train a LightGBM (or Ridge) minutes projection head."""
    MIN_COLS = [c for c in MIN_FEATURES_MINUTES if any(r.get(c) is not None for r in rows_tr)]
    X_tr = col_array(rows_tr, MIN_COLS)
    y_tr = targets(rows_tr, "target_min")
    X_va = col_array(rows_va, MIN_COLS)
    y_va = targets(rows_va, "target_min")

    if HAS_LGB:
        model = _lgb_train(X_tr, y_tr, X_va, y_va, n_estimators=300, lr=0.05, max_depth=4)
    else:
        model = Ridge(alpha=1.0).fit(X_tr, y_tr)
    return model, MIN_COLS


def project_minutes(model, rows: list, min_cols: List[str]) -> np.ndarray:
    X = col_array(rows, min_cols)
    p = _fallback_predict(X, model)
    return np.clip(p, 0.0, 48.0)


# ---------------------------------------------------------------------------
# global expert: standard production-feature LightGBM
# ---------------------------------------------------------------------------

def train_global_expert(rows_tr: list, rows_va: list,
                        stat: str, w_tr=None) -> object:
    X_tr, _ = feature_matrix(rows_tr, stat)
    y_tr     = targets(rows_tr, f"target_{stat}")
    X_va, _  = feature_matrix(rows_va, stat)
    y_va     = targets(rows_va, f"target_{stat}")

    if HAS_LGB:
        model = _lgb_train(X_tr, y_tr, X_va, y_va, sample_weight=w_tr)
    else:
        model = Ridge(alpha=1.0).fit(X_tr, y_tr)
    return model


def predict_global(model, rows: list, stat: str) -> np.ndarray:
    X, _ = feature_matrix(rows, stat)
    return _fallback_predict(X, model)


# ---------------------------------------------------------------------------
# per-regime expert (hard split)
# ---------------------------------------------------------------------------

def train_regime_experts(rows_tr: list, rows_va: list,
                         proj_min_tr: np.ndarray,
                         stat: str,
                         bins: List[float],
                         global_model) -> Dict[int, object]:
    """Train one expert per regime on regime-filtered tr rows.
    Falls back to global_model if regime has < FALLBACK_THRESHOLD rows."""
    n_regimes = len(bins) - 1
    regime_tr = assign_regime(proj_min_tr, bins)
    experts: Dict[int, object] = {}

    X_va, _  = feature_matrix(rows_va, stat)
    y_va     = targets(rows_va, f"target_{stat}")

    for r in range(n_regimes):
        idx = np.where(regime_tr == r)[0]
        if len(idx) < FALLBACK_THRESHOLD:
            experts[r] = global_model   # fallback
            print(f"      regime {r}: n={len(idx)} < {FALLBACK_THRESHOLD} → fallback to global")
            continue
        r_rows = [rows_tr[i] for i in idx]
        X_r, _ = feature_matrix(r_rows, stat)
        y_r    = targets(r_rows, f"target_{stat}")
        if HAS_LGB:
            model = _lgb_train(X_r, y_r, X_va, y_va, n_estimators=400, lr=0.05)
        else:
            model = Ridge(alpha=1.0).fit(X_r, y_r)
        experts[r] = model
        print(f"      regime {r}: n={len(idx)} rows trained")
    return experts


def predict_hard(experts: Dict[int, object],
                 rows_ho: list,
                 proj_min_ho: np.ndarray,
                 stat: str,
                 bins: List[float]) -> np.ndarray:
    regime_ho = assign_regime(proj_min_ho, bins)
    preds = np.zeros(len(rows_ho))
    for r, model in experts.items():
        idx = np.where(regime_ho == r)[0]
        if len(idx) == 0:
            continue
        r_rows = [rows_ho[i] for i in idx]
        X_r, _ = feature_matrix(r_rows, stat)
        preds[idx] = _fallback_predict(X_r, model)
    return preds


# ---------------------------------------------------------------------------
# residual expert (soft additive)
# ---------------------------------------------------------------------------

def train_residual_experts(rows_tr: list, rows_va: list,
                           proj_min_tr: np.ndarray,
                           global_preds_tr: np.ndarray,
                           stat: str,
                           bins: List[float]) -> Dict[int, object]:
    """Train regime experts on residual (actual - global_pred)."""
    n_regimes = len(bins) - 1
    regime_tr = assign_regime(proj_min_tr, bins)
    y_tr = targets(rows_tr, f"target_{stat}")
    resid_tr = y_tr - global_preds_tr

    X_va, _  = feature_matrix(rows_va, stat)
    y_va     = targets(rows_va, f"target_{stat}")
    global_preds_va = np.zeros(len(rows_va))  # residual target for va = 0 is fine for early-stop

    resid_experts: Dict[int, Optional[object]] = {}
    for r in range(n_regimes):
        idx = np.where(regime_tr == r)[0]
        if len(idx) < FALLBACK_THRESHOLD:
            resid_experts[r] = None   # no correction
            print(f"      residual regime {r}: n={len(idx)} < {FALLBACK_THRESHOLD} → no correction")
            continue
        r_rows = [rows_tr[i] for i in idx]
        X_r, _ = feature_matrix(r_rows, stat)
        y_r    = resid_tr[idx]
        if HAS_LGB:
            model = _lgb_train(X_r, y_r, X_va, y_va, n_estimators=300, lr=0.03)
        else:
            model = Ridge(alpha=0.1).fit(X_r, y_r)
        resid_experts[r] = model
        print(f"      residual regime {r}: n={len(idx)} rows trained")
    return resid_experts


def predict_residual(resid_experts: Dict[int, Optional[object]],
                     rows_ho: list,
                     proj_min_ho: np.ndarray,
                     global_preds_ho: np.ndarray,
                     stat: str,
                     bins: List[float]) -> np.ndarray:
    regime_ho = assign_regime(proj_min_ho, bins)
    correction = np.zeros(len(rows_ho))
    for r, model in resid_experts.items():
        if model is None:
            continue
        idx = np.where(regime_ho == r)[0]
        if len(idx) == 0:
            continue
        r_rows = [rows_ho[i] for i in idx]
        X_r, _ = feature_matrix(r_rows, stat)
        correction[idx] = _fallback_predict(X_r, model)
    return global_preds_ho + correction


# ---------------------------------------------------------------------------
# main per-stat loop
# ---------------------------------------------------------------------------

def run_stat(stat: str) -> dict:
    print(f"\n{'='*70}")
    print(f"  STAT: {stat.upper()}")
    print(f"{'='*70}")

    rows, folds = build_folds(stat)
    base = load_base(stat)

    recs_global: List[dict] = []
    recs_hard4:  List[dict] = []
    recs_hard3:  List[dict] = []
    recs_res4:   List[dict] = []
    recs_res3:   List[dict] = []

    for fi, tr_end, va_end, te_end in folds:
        print(f"\n  -- fold {fi}: tr[:{ tr_end}], va[{tr_end}:{va_end}], ho[{va_end}:{te_end}] --")
        rows_tr  = rows[:tr_end]
        rows_va  = rows[tr_end:va_end]    # validation slice for early-stop
        rows_ho  = rows[va_end:te_end]

        # 1. train minutes head on tr, project tr + ho
        print("    [1] training minutes head ...")
        min_model, min_cols = train_minutes_head(rows_tr, rows_va)
        proj_min_tr = project_minutes(min_model, rows_tr, min_cols)
        proj_min_ho = project_minutes(min_model, rows_ho, min_cols)
        print(f"        proj_min_ho: mean={proj_min_ho.mean():.1f}  std={proj_min_ho.std():.1f}")

        # 2. global expert
        print("    [2] training global expert ...")
        global_model  = train_global_expert(rows_tr, rows_va, stat)
        global_preds_ho = predict_global(global_model, rows_ho, stat)
        global_preds_tr = predict_global(global_model, rows_tr, stat)

        # record global
        for row, pred in zip(rows_ho, global_preds_ho):
            recs_global.append({
                "game_id":   str(row.get("date", ""))[:10],
                "player_id": int(row.get("player_id", 0)),
                "fold": fi, "pred": float(pred),
            })

        # 3. HARD SPLIT — 4 bins
        print("    [3] training hard-split experts (4-bin) ...")
        experts4 = train_regime_experts(rows_tr, rows_va, proj_min_tr, stat, BINS_4, global_model)
        hard4_preds = predict_hard(experts4, rows_ho, proj_min_ho, stat, BINS_4)
        for row, pred in zip(rows_ho, hard4_preds):
            recs_hard4.append({"game_id": str(row.get("date", ""))[:10],
                                "player_id": int(row.get("player_id",0)),
                                "fold": fi, "pred": float(pred)})

        # 4. HARD SPLIT — 3 bins
        print("    [4] training hard-split experts (3-bin) ...")
        experts3 = train_regime_experts(rows_tr, rows_va, proj_min_tr, stat, BINS_3, global_model)
        hard3_preds = predict_hard(experts3, rows_ho, proj_min_ho, stat, BINS_3)
        for row, pred in zip(rows_ho, hard3_preds):
            recs_hard3.append({"game_id": str(row.get("date", ""))[:10],
                                "player_id": int(row.get("player_id",0)),
                                "fold": fi, "pred": float(pred)})

        # 5. RESIDUAL EXPERT — 4 bins
        print("    [5] training residual experts (4-bin) ...")
        resid4 = train_residual_experts(rows_tr, rows_va, proj_min_tr,
                                        global_preds_tr, stat, BINS_4)
        res4_preds = predict_residual(resid4, rows_ho, proj_min_ho, global_preds_ho, stat, BINS_4)
        for row, pred in zip(rows_ho, res4_preds):
            recs_res4.append({"game_id": str(row.get("date", ""))[:10],
                               "player_id": int(row.get("player_id",0)),
                               "fold": fi, "pred": float(pred)})

        # 6. RESIDUAL EXPERT — 3 bins
        print("    [6] training residual experts (3-bin) ...")
        resid3 = train_residual_experts(rows_tr, rows_va, proj_min_tr,
                                        global_preds_tr, stat, BINS_3)
        res3_preds = predict_residual(resid3, rows_ho, proj_min_ho, global_preds_ho, stat, BINS_3)
        for row, pred in zip(rows_ho, res3_preds):
            recs_res3.append({"game_id": str(row.get("date", ""))[:10],
                               "player_id": int(row.get("player_id",0)),
                               "fold": fi, "pred": float(pred)})

    print(f"\n{'='*70}")
    print(f"  SCORES: {stat.upper()}")
    print(f"{'='*70}")

    r_global = score_and_report(recs_global, base, rows, label=f"global-{stat}")
    r_hard4  = score_and_report(recs_hard4,  base, rows, label=f"hard4-{stat}")
    r_hard3  = score_and_report(recs_hard3,  base, rows, label=f"hard3-{stat}")
    r_res4   = score_and_report(recs_res4,   base, rows, label=f"residual4-{stat}")
    r_res3   = score_and_report(recs_res3,   base, rows, label=f"residual3-{stat}")

    return {
        "stat": stat,
        "global":    r_global,
        "hard4":     r_hard4,
        "hard3":     r_hard3,
        "residual4": r_res4,
        "residual3": r_res3,
    }


# ---------------------------------------------------------------------------
# report writer
# ---------------------------------------------------------------------------

def write_audit(results: List[dict], output_path: str) -> None:
    lines = []
    lines.append("# PTS/REB Regime Mixture-of-Experts (Approach A4)")
    lines.append("")
    lines.append("**Approach:** train a LightGBM minutes-projection head per fold,")
    lines.append("assign rows to minutes regimes (4-bin: R1<18, R2 18-26, R3 26-34, R4 34+;")
    lines.append("3-bin: <22, 22-32, 32+), then compare:")
    lines.append("- **global**: single model on all production features")
    lines.append("- **hard-split**: separate expert per regime (soft fallback to global if < 800 rows)")
    lines.append("- **residual-expert**: global + regime-specific residual correction (additive)")
    lines.append("")
    lines.append("Baselines: PTS 4.4454 / REB 1.8461 (cached production OOF)")
    lines.append("")

    for r in results:
        stat = r["stat"].upper()
        base_mae = r["global"]["mae_base"]

        variants = [
            ("global",     r["global"]),
            ("hard-4bin",  r["hard4"]),
            ("hard-3bin",  r["hard3"]),
            ("resid-4bin", r["residual4"]),
            ("resid-3bin", r["residual3"]),
        ]

        lines.append(f"## {stat}")
        lines.append("")
        lines.append("### Variant Table")
        lines.append("")
        lines.append(f"| Variant     | MAE    | vs base | delta% | verdict |")
        lines.append(f"|-------------|--------|---------|--------|---------|")

        best_delta = float("inf")
        best_name  = "global"
        for name, rv in variants:
            if not rv:
                continue
            mae_new  = rv["mae_new"]
            delta    = rv["delta"]
            pct      = rv["pct"]
            verdict  = "PASS" if delta < 0 else "fail"
            lines.append(f"| {name:<11} | {mae_new:.4f} | {base_mae:.4f}  | {pct:+.2f}% | {verdict} |")
            if delta < best_delta:
                best_delta = delta
                best_name  = name

        lines.append("")
        winner = next(rv for nm, rv in variants if nm.replace("-4bin","4").replace("-3bin","3") == best_name.replace("-","") or nm == best_name)
        # find winner dict properly
        winner_rv = None
        for nm, rv in variants:
            if rv and rv["delta"] == best_delta:
                winner_rv = rv
                winner_name = nm
                break

        if winner_rv:
            lines.append(f"**Winner: {winner_name}**  MAE={winner_rv['mae_new']:.4f}  "
                         f"delta={best_delta:+.4f} ({winner_rv['pct']:+.2f}%)")
            lines.append("")
            # per-fold from global (as reference) — score_and_report already printed full fold table
            lines.append(f"**GATE: {'PASS (winner beats base)' if best_delta < 0 else 'FAIL'}**")
            lines.append("")
            lines.append(f"**RECOMMENDATION: {'SHIP' if best_delta < 0 else 'REJECT'}**")
            lines.append("")
            lines.append("*Note: hard-split often loses due to fewer rows per expert → "
                         "higher variance; residual-expert is usually the safer form.*")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by scripts/exp_regime_pts_reb.py*")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nAudit written to: {output_path}")


# ---------------------------------------------------------------------------
# quick 1-fold 1-stat smoke test
# ---------------------------------------------------------------------------

def smoke_test():
    print("=== SMOKE TEST: fold 1, PTS only ===")
    rows, folds = build_folds("pts")
    fi, tr_end, va_end, te_end = folds[0]
    rows_tr = rows[:tr_end]
    rows_va = rows[tr_end:va_end]
    rows_ho = rows[va_end:te_end]

    min_model, min_cols = train_minutes_head(rows_tr, rows_va)
    proj_min_ho = project_minutes(min_model, rows_ho, min_cols)
    global_model = train_global_expert(rows_tr, rows_va, "pts")
    global_preds_ho = predict_global(global_model, rows_ho, "pts")
    global_preds_tr = predict_global(global_model, rows_tr, "pts")
    proj_min_tr = project_minutes(min_model, rows_tr, min_cols)

    experts4 = train_regime_experts(rows_tr, rows_va, proj_min_tr, "pts", BINS_4, global_model)
    hard4 = predict_hard(experts4, rows_ho, proj_min_ho, "pts", BINS_4)

    resid4 = train_residual_experts(rows_tr, rows_va, proj_min_tr, global_preds_tr, "pts", BINS_4)
    res4 = predict_residual(resid4, rows_ho, proj_min_ho, global_preds_ho, "pts", BINS_4)

    actual = targets(rows_ho, "target_pts")
    mae_global = float(np.abs(global_preds_ho - actual).mean())
    mae_hard4  = float(np.abs(hard4 - actual).mean())
    mae_res4   = float(np.abs(res4 - actual).mean())
    print(f"  fold1 PTS MAE: global={mae_global:.4f}  hard4={mae_hard4:.4f}  res4={mae_res4:.4f}")
    print("SMOKE TEST PASSED" if not (np.isnan(mae_global) or np.isnan(mae_hard4)) else "SMOKE TEST FAILED")
    return mae_global


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Quick 1-fold PTS smoke test")
    parser.add_argument("--stat", default="both", choices=["pts", "reb", "both"],
                        help="Which stat to run (default: both)")
    args = parser.parse_args()

    if args.smoke:
        smoke_test()
        sys.exit(0)

    stats = ["pts", "reb"] if args.stat == "both" else [args.stat]
    all_results = []
    for stat in stats:
        res = run_stat(stat)
        all_results.append(res)

    audit_path = os.path.join(_ROOT, "docs", "_audits", "PTS_REB_EXP_REGIME.md")
    write_audit(all_results, audit_path)

    # print compact summary
    print("\n" + "="*70)
    print("COMPACT SUMMARY TABLE")
    print("="*70)
    hdr = f"{'stat':<4} {'variant':<12} {'MAE':>7} {'base':>7} {'delta%':>8} {'gate'}"
    print(hdr)
    print("-" * 50)
    for r in all_results:
        stat = r["stat"]
        for name, rv in [("global", r["global"]), ("hard-4bin", r["hard4"]),
                         ("hard-3bin", r["hard3"]),
                         ("resid-4bin", r["residual4"]), ("resid-3bin", r["residual3"])]:
            if not rv:
                continue
            gate = "PASS" if rv["delta"] < 0 else "fail"
            print(f"{stat:<4} {name:<12} {rv['mae_new']:>7.4f} {rv['mae_base']:>7.4f} "
                  f"{rv['pct']:>+8.2f}% {gate}")
    print("="*70)
