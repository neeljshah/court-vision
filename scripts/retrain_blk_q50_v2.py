"""retrain_blk_q50_v2.py — Cycle 99a (loop 5): BLK q50 retrain with new features.

The cycle-29 BLK q50 head (XGB-q50, anchor MAE 0.4398) is saturated against
all POST-prediction corrections (cycles 97b/98b/98c rejected scale/conditional/
outlier-uplift adjustments). The unexplored angle: ADD NEW FEATURES + RETRAIN.

Candidate additive features (additive vs the 85-col baseline):
  * q1_blk_l5    — rolling prior Q1 BLK (cycle 91a, _PlayerQuarterStats)
  * position_*   — one-hot position {C, F, G} (cycle 90e, _PlayerPositions)
  * opp_def_blk  — ALREADY in baseline (no-op for this cycle)

Coverage gate per spec ("Don't add features that have < 30% holdout coverage"):
  * q1_blk_l5    — 0% holdout coverage (parquet only covers 2024-10/11/12,
                    holdout is 2025-10 to 2026-04) — REJECT this feature
  * position_*   — 100% holdout coverage — KEEP
  * opp_def_blk  — already wired, skipped

Ship gate (BOTH):
  1. Single-split BLK holdout MAE strictly DOWN vs cycle-29 anchor 0.4398
  2. Walk-forward (4 folds) BLK MAE sign 4/4 negative (improvement)

If both gates pass: persist as data/models/blk_q50_v2.pkl, update
prop_pergame._USE_Q50_LGB_BLK_V2 flag + production loader.
If either gate fails: REJECT, leave cycle-29 v1 in production.

Run:
    python scripts/retrain_blk_q50_v2.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime
from typing import List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _LOG_TRANSFORM_STATS,
    _MODEL_DIR,
    _RECENCY_DECAY,
    build_pergame_dataset,
    feature_columns,
)
from src.prediction.prop_quantiles import _per_stat_xgb_params  # noqa: E402


# ── feature additions ───────────────────────────────────────────────────────

# One-hot bucketing for the position string. NBA commonplayerinfo returns
# compound positions like "Guard-Forward" / "Forward-Center". We bucket via
# substring match (any "Guard" → position_G=1, etc.), so hybrids light up
# multiple buckets. Players with no position string get all-zero one-hots
# (a separate implicit bucket, no need for an explicit "position_unknown"
# since the q50 LGB will just see a row where none of the new columns fire).
_POSITION_BUCKETS = ("position_C", "position_F", "position_G")


def _position_one_hot(pos: Optional[str]) -> dict:
    """Map a raw position string to one-hot {position_C, position_F, position_G}.
    Hybrid positions light up multiple buckets; None/empty → all zeros."""
    out = {k: 0.0 for k in _POSITION_BUCKETS}
    if not pos:
        return out
    p = str(pos)
    if "Center" in p:
        out["position_C"] = 1.0
    if "Forward" in p:
        out["position_F"] = 1.0
    if "Guard" in p:
        out["position_G"] = 1.0
    return out


def blk_v2_feature_columns() -> List[str]:
    """BLK v2 feature columns: baseline + 3 position one-hot columns.
    q1_blk_l5 EXCLUDED because holdout coverage is 0% (see header docstring)."""
    return list(feature_columns()) + list(_POSITION_BUCKETS)


def _build_X(rows: List[dict], cols: List[str], extra_cols: List[str]) -> np.ndarray:
    base_n = len(cols)
    extra_n = len(extra_cols)
    X = np.zeros((len(rows), base_n + extra_n), dtype=float)
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            X[i, j] = float(r.get(c, 0.0) or 0.0)
        oh = _position_one_hot(r.get("position"))
        for j, c in enumerate(extra_cols):
            X[i, base_n + j] = float(oh.get(c, 0.0))
    return X


# ── coverage check ──────────────────────────────────────────────────────────

def _coverage_check(rows: List[dict]) -> dict:
    """Return per-feature train/holdout coverage. Rejects feature additions
    that fail the 30% holdout-coverage gate from the spec."""
    n = len(rows)
    train = rows[:int(n * 0.80)]
    holdout = rows[int(n * 0.80):]
    q1_ho = sum(1 for r in holdout if r.get("q1_blk_l5") is not None)
    pos_ho = sum(1 for r in holdout if r.get("position"))
    q1_tr = sum(1 for r in train if r.get("q1_blk_l5") is not None)
    pos_tr = sum(1 for r in train if r.get("position"))
    return {
        "n_train": len(train),
        "n_holdout": len(holdout),
        "q1_blk_l5_train_cov":   q1_tr / max(1, len(train)),
        "q1_blk_l5_holdout_cov": q1_ho / max(1, len(holdout)),
        "position_train_cov":    pos_tr / max(1, len(train)),
        "position_holdout_cov":  pos_ho / max(1, len(holdout)),
    }


# ── training ────────────────────────────────────────────────────────────────

def _train_lgb_q50(X_tr, y_tr_t, X_val, y_val_t, sw):
    """Train an LGB-q50 model with cycle-29 hyperparameters for BLK."""
    import lightgbm as lgb
    params = _per_stat_xgb_params("blk")
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
    m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
          sample_weight=sw,
          callbacks=[lgb.early_stopping(40, verbose=False)])
    return m


def _inv_log(v: np.ndarray) -> np.ndarray:
    return np.clip(np.expm1(v), 0.0, None)


def single_split_eval(rows: List[dict], holdout_frac: float = 0.20,
                      val_frac: float = 0.15) -> Tuple[float, float, object]:
    """Train LGB-q50 BLK on 65/15/20 chrono split with NEW features.
    Returns (baseline_mae_v1_recompute, new_mae_v2, fitted_v2_model)."""
    from sklearn.metrics import mean_absolute_error

    cols = feature_columns()
    extra = list(_POSITION_BUCKETS)

    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end   = int(n * (1.0 - holdout_frac))

    X_all_new = _build_X(rows, cols, extra)
    X_all_old = X_all_new[:, : len(cols)]   # baseline view
    y_all = np.array([float(r["target_blk"]) for r in rows], dtype=float)

    X_tr_new, X_val_new, X_ho_new = (X_all_new[:train_end],
                                     X_all_new[train_end:val_end],
                                     X_all_new[val_end:])
    X_tr_old, X_val_old, X_ho_old = (X_all_old[:train_end],
                                     X_all_old[train_end:val_end],
                                     X_all_old[val_end:])
    y_tr, y_val, y_ho = y_all[:train_end], y_all[train_end:val_end], y_all[val_end:]

    # log1p target transform (BLK is in _LOG_TRANSFORM_STATS).
    assert "blk" in _LOG_TRANSFORM_STATS, "BLK must use log1p transform"
    y_tr_t, y_val_t = np.log1p(y_tr), np.log1p(y_val)

    # Recency-decay sample weights (match production training).
    train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_train_date = max(train_dates)
    age_years = np.array([(max_train_date - d).days / 365.0 for d in train_dates],
                         dtype=float)
    sw = np.exp(-_RECENCY_DECAY * age_years) if _RECENCY_DECAY > 0 else None

    # v1 recomputed baseline (sanity — should match the on-disk LGB-q50 BLK
    # MAE of ~0.4391 from quantile_pergame_metrics.json).
    v1 = _train_lgb_q50(X_tr_old, y_tr_t, X_val_old, y_val_t, sw)
    pred_v1 = _inv_log(v1.predict(X_ho_old))
    mae_v1 = float(mean_absolute_error(y_ho, pred_v1))

    # v2 with the new features.
    v2 = _train_lgb_q50(X_tr_new, y_tr_t, X_val_new, y_val_t, sw)
    pred_v2 = _inv_log(v2.predict(X_ho_new))
    mae_v2 = float(mean_absolute_error(y_ho, pred_v2))

    return mae_v1, mae_v2, v2


def walk_forward_eval(rows: List[dict], n_splits: int = 4) -> List[dict]:
    """Walk-forward 4-fold MAE delta (v2 - v1) for BLK."""
    from sklearn.metrics import mean_absolute_error

    cols = feature_columns()
    extra = list(_POSITION_BUCKETS)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)

    X_all_new = _build_X(rows, cols, extra)
    X_all_old = X_all_new[:, : len(cols)]
    y_all = np.array([float(r["target_blk"]) for r in rows], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    folds = []
    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            continue
        y_tr, y_val, y_ho = y_all[:tr_end], y_all[tr_end:va_end], y_all[va_end:te_end]
        y_tr_t, y_val_t = np.log1p(y_tr), np.log1p(y_val)
        train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(train_dates)
        age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
        sw = np.exp(-_RECENCY_DECAY * age) if _RECENCY_DECAY > 0 else None

        # v1
        v1 = _train_lgb_q50(X_all_old[:tr_end], y_tr_t,
                            X_all_old[tr_end:va_end], y_val_t, sw)
        pred_v1 = _inv_log(v1.predict(X_all_old[va_end:te_end]))
        mae_v1 = float(mean_absolute_error(y_ho, pred_v1))

        # v2
        v2 = _train_lgb_q50(X_all_new[:tr_end], y_tr_t,
                            X_all_new[tr_end:va_end], y_val_t, sw)
        pred_v2 = _inv_log(v2.predict(X_all_new[va_end:te_end]))
        mae_v2 = float(mean_absolute_error(y_ho, pred_v2))

        folds.append({
            "fold": fold_idx + 1,
            "n_tr": tr_end, "n_val": va_end - tr_end, "n_ho": te_end - va_end,
            "mae_v1": mae_v1, "mae_v2": mae_v2, "delta": mae_v2 - mae_v1,
        })
    return folds


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--write-anyway", action="store_true",
                    help="Persist v2 even if ship gate fails (for inspection).")
    args = ap.parse_args()

    print("[cycle 99a] BLK q50 retrain v2 — position one-hot features", flush=True)
    print("=" * 72, flush=True)
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    if not rows:
        print("REJECT: no rows built — gamelog cache empty.")
        return 1
    print(f"  rows={len(rows)}", flush=True)

    print("\nCoverage check:")
    cov = _coverage_check(rows)
    for k, v in cov.items():
        if isinstance(v, float):
            print(f"  {k:32s} {v:.4f}")
        else:
            print(f"  {k:32s} {v}")
    if cov["q1_blk_l5_holdout_cov"] < 0.30:
        print(f"\n  -> q1_blk_l5 holdout coverage "
              f"{cov['q1_blk_l5_holdout_cov']:.1%} below 30% gate "
              f"(parquet only spans 2024-10/11/12; holdout is 2025-10+).",
              flush=True)
        print("     EXCLUDING q1_blk_l5 from v2 feature set. New feature stays\n"
              "     available for future cycles once the parquet is backfilled.",
              flush=True)
    if cov["position_holdout_cov"] < 0.30:
        print(f"\nREJECT: position holdout coverage "
              f"{cov['position_holdout_cov']:.1%} below 30% gate. "
              f"No new features pass coverage; nothing to retrain.")
        return 1

    print("\nSingle-split eval (65/15/20 chronological)...", flush=True)
    mae_v1, mae_v2, model_v2 = single_split_eval(rows)
    delta_single = mae_v2 - mae_v1
    print(f"  v1 (baseline LGB-q50 recompute) holdout MAE = {mae_v1:.4f}")
    print(f"  v2 (+ position_{{C,F,G}} one-hot) MAE       = {mae_v2:.4f}")
    print(f"  single-split delta = {delta_single:+.4f}")
    anchor = 0.4398
    print(f"  vs cycle-29 anchor {anchor:.4f}: delta_vs_anchor = "
          f"{mae_v2 - anchor:+.4f}")

    print(f"\nWalk-forward eval ({args.splits} folds)...", flush=True)
    folds = walk_forward_eval(rows, n_splits=args.splits)
    if not folds:
        print("REJECT: no walk-forward folds produced (dataset too small).")
        return 1
    for f in folds:
        print(f"  fold {f['fold']}: tr={f['n_tr']} val={f['n_val']} ho={f['n_ho']}  "
              f"v1={f['mae_v1']:.4f}  v2={f['mae_v2']:.4f}  d={f['delta']:+.4f}")
    n_neg = sum(1 for f in folds if f["delta"] < 0.0)
    wf_mean = float(np.mean([f["delta"] for f in folds]))
    wf_std = float(np.std([f["delta"] for f in folds]))
    print(f"  WF mean delta = {wf_mean:+.4f} ± {wf_std:.4f}   "
          f"folds_negative = {n_neg}/{len(folds)}")

    # Ship gate (BOTH).
    single_ok = mae_v2 < anchor
    wf_ok = (n_neg == len(folds))
    print("\n" + "=" * 72)
    print(f"  single-split MAE < anchor ({anchor:.4f}) ?  {single_ok}  "
          f"({mae_v2:.4f} vs {anchor:.4f})")
    print(f"  walk-forward {len(folds)}/{len(folds)} folds negative ?  {wf_ok}  "
          f"({n_neg}/{len(folds)})")
    print("=" * 72)

    out_path = os.path.join(_MODEL_DIR, "blk_q50_v2.pkl")
    meta_path = os.path.join(_MODEL_DIR, "blk_q50_v2_metrics.json")
    metrics = {
        "cycle": "99a",
        "feature_set": "baseline_85 + position_{C,F,G} one-hot",
        "n_features": int(len(feature_columns()) + len(_POSITION_BUCKETS)),
        "coverage": cov,
        "single_split": {
            "mae_v1_recompute": mae_v1,
            "mae_v2_new":       mae_v2,
            "delta":            delta_single,
            "anchor_v1":        anchor,
            "delta_vs_anchor":  mae_v2 - anchor,
        },
        "walk_forward": {
            "folds": folds,
            "mean_delta": wf_mean,
            "std_delta":  wf_std,
            "n_negative": n_neg,
            "n_folds":    len(folds),
        },
        "ship_gate": {
            "single_split_ok": single_ok,
            "walk_forward_ok": wf_ok,
            "shipped":         (single_ok and wf_ok),
        },
    }
    with open(meta_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"Wrote metrics -> {meta_path}", flush=True)

    if single_ok and wf_ok:
        import joblib  # noqa: PLC0415
        joblib.dump(model_v2, out_path)
        print(f"SHIP: wrote v2 artifact -> {out_path}")
        print(f"\nNext: update prop_pergame._load_q50_model to dispatch BLK -> "
              f"blk_q50_v2.pkl, and update anchor in test_production_mae_anchor.py "
              f"from {anchor:.4f} to {mae_v2:.4f}.")
        return 0

    if args.write_anyway:
        import joblib  # noqa: PLC0415
        joblib.dump(model_v2, out_path)
        print(f"(--write-anyway) wrote v2 artifact -> {out_path}")
    reason_bits = []
    if not single_ok:
        reason_bits.append(f"single +{delta_single:.4f}")
    if not wf_ok:
        reason_bits.append(f"WF {n_neg}/{len(folds)} (mean {wf_mean:+.4f})")
    print(f"REJECT cycle 99a: {' | '.join(reason_bits)}. Cycle-29 v1 stays in "
          f"production. New features remain available for future cycles.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
