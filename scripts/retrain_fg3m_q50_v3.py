"""retrain_fg3m_q50_v3.py — cycle 100c (loop 5).

FG3M LGB-q50 retrain with cycle-99e opp-context rolling-5 features.

Cycle 99b (v2) REJECT'd because q1_fg3m_l5 had 0% holdout coverage and the
remaining position + home_spread additions netted +0.0005 MAE.

Cycle 99e SHIPPED the opp-context wrappers (oppdef.l5_allowed + team_adv_l5)
and now lands these per-row keys with ~100% holdout coverage. v3 picks the
4 most FG3M-relevant ones:

  opp_team_def_rtg_l5  — opp defensive rating L5 (overall defensive quality)
  opp_team_pace_l5     — opp pace L5 (more possessions => more 3pt attempts)
  opp_team_ts_pct_l5   — opp true shooting allowed L5 (proxy for perimeter D)
  opp_def_fg3m_l5      — opp raw FG3M allowed L5 (direct defensive against 3s)

Excluded: q1_fg3m_l5 (failed v2 coverage gate, parquet still 2024-Oct/Nov/Dec
only). Excluded: position one-hots (already tested in v2 — net wash).
Excluded: home_spread (v2 single-split regression).

Cycle 27 baseline (XGB-q50 on the global 85-col feature set):
    FG3M holdout MAE = 0.8941.

Ship gate (BOTH required):
  * single-split FG3M MAE strictly DOWN (< 0.8941)
  * walk-forward 4/4 folds MAE improved vs the 85-col LGB-q50 baseline
  * "Other stats unchanged" — automatically satisfied: this script only
    retrains FG3M; other heads keep their persisted artifacts.

When passing: save the wider model to data/models/fg3m_q50_v3.pkl. Production
dispatch wire-in updates _load_q50_model to prefer fg3m_q50_v3.pkl over the
default quantile_pergame_fg3m_q50.json when present, and feature_columns()
gets a global extension (NOT stat-specific — coordinating with cycles 100a/b/d/e).

Coverage gate: 30% holdout (matches v2). Below 30% → drop that feature only.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _LOG_TRANSFORM_STATS, _MODEL_DIR, _RECENCY_DECAY,
    build_pergame_dataset, feature_columns,
)


BASELINE_MAE = 0.8941          # cycle 27 (XGB-q50) reference
COVERAGE_FLOOR_PCT = 30.0      # per-feature holdout coverage gate

# Cycle 99e additive opp-context features (most FG3M-relevant subset).
# Each is rolling-5 over OPPONENT's last 5 games strictly BEFORE the row's date.
# Source: oppdef.l5_allowed() + team_adv_l5.features() in build_pergame_dataset.
CANDIDATE_FEATURES = (
    "opp_team_def_rtg_l5",   # team_adv_l5
    "opp_team_pace_l5",      # team_adv_l5
    "opp_team_ts_pct_l5",    # team_adv_l5
    "opp_def_fg3m_l5",       # oppdef.l5_allowed
)


def _augment_row(row: dict) -> dict:
    """Return a shallow-copied row with the 4 candidate features coerced to float.

    Each source key is None on rows with insufficient opp prior history (early
    season, fresh franchises). Collapsed to 0.0 here so the LGB never sees None.
    NaNs (rare — coerce-via-float-on-the-wrapper already guards) also collapse.
    """
    new = dict(row)
    for k in CANDIDATE_FEATURES:
        v = row.get(k)
        try:
            f = float(v) if v is not None else 0.0
            if f != f:  # NaN
                f = 0.0
        except (TypeError, ValueError):
            f = 0.0
        new[k] = f
    return new


def _coverage_report(rows: List[dict]) -> dict:
    """Holdout coverage per feature — counts rows where the SOURCE was non-None."""
    n = len(rows)
    if n == 0:
        return {"n_rows": 0}
    out: Dict[str, float] = {"n_rows": n}
    for k in CANDIDATE_FEATURES:
        present = sum(1 for r in rows if r.get(k) is not None)
        out[f"{k}_pct"] = round(100.0 * present / n, 2)
    return out


def _fg3m_params() -> dict:
    """Match prop_quantiles._per_stat_xgb_params('fg3m') overrides — the LGB
    quantile head shares them via min_child_samples = max(20, mcw*2)."""
    return dict(n_estimators=600, max_depth=4, learning_rate=0.025,
                subsample=0.7, colsample_bytree=0.8,
                min_child_weight=15, reg_lambda=8.0, reg_alpha=0.5,
                gamma=0.0, random_state=42)


def _build_X(rows: List[dict], cols: List[str]) -> np.ndarray:
    return np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in rows],
                    dtype=float)


def _train_lgb_q50(X_tr, yt_tr, X_val, yt_val, sw):
    import lightgbm as lgb
    p = _fg3m_params()
    m = lgb.LGBMRegressor(
        n_estimators=p["n_estimators"], max_depth=p["max_depth"],
        learning_rate=p["learning_rate"],
        subsample=p["subsample"], subsample_freq=1,
        colsample_bytree=p["colsample_bytree"],
        min_child_samples=max(20, p["min_child_weight"] * 2),
        reg_lambda=p["reg_lambda"], reg_alpha=p["reg_alpha"],
        random_state=42, objective="quantile", alpha=0.5,
        n_jobs=-1, verbosity=-1,
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)],
          sample_weight=sw,
          callbacks=[lgb.early_stopping(40, verbose=False)])
    return m


def single_split_eval(rows_aug: List[dict],
                      base_cols: List[str],
                      wide_cols: List[str],
                      holdout_frac: float = 0.2,
                      val_frac: float = 0.15) -> dict:
    """65/15/20 chronological. Train baseline (85-col) + wide ((85+k)-col)
    on the same split with the same LGB-q50 recipe; compare holdout MAE."""
    from sklearn.metrics import mean_absolute_error

    rows_aug.sort(key=lambda r: r["date"])
    n = len(rows_aug)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end = int(n * (1.0 - holdout_frac))

    y = np.array([r["target_fg3m"] for r in rows_aug], dtype=float)
    assert "fg3m" in _LOG_TRANSFORM_STATS, "FG3M must use log1p transform"
    yt = np.log1p(y)
    y_ho = y[val_end:]
    yt_tr, yt_val = yt[:train_end], yt[train_end:val_end]

    train_dates = [datetime.fromisoformat(rows_aug[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-_RECENCY_DECAY * age) if _RECENCY_DECAY > 0 else None

    X_base = _build_X(rows_aug, base_cols)
    m_base = _train_lgb_q50(X_base[:train_end], yt_tr,
                            X_base[train_end:val_end], yt_val, sw)
    base_pred = np.clip(np.expm1(m_base.predict(X_base[val_end:])), 0.0, None)
    mae_base = float(mean_absolute_error(y_ho, base_pred))

    X_wide = _build_X(rows_aug, wide_cols)
    m_wide = _train_lgb_q50(X_wide[:train_end], yt_tr,
                            X_wide[train_end:val_end], yt_val, sw)
    wide_pred = np.clip(np.expm1(m_wide.predict(X_wide[val_end:])), 0.0, None)
    mae_wide = float(mean_absolute_error(y_ho, wide_pred))

    return {
        "n_rows": n, "n_train": train_end, "n_val": val_end - train_end,
        "n_holdout": n - val_end,
        "mae_baseline_85": mae_base,
        "mae_wide":        mae_wide,
        "delta_mae":       mae_wide - mae_base,
        "mae_vs_cycle27":  mae_wide - BASELINE_MAE,
        "wide_model":      m_wide,
    }


def walk_forward_eval(rows_aug: List[dict],
                      base_cols: List[str],
                      wide_cols: List[str],
                      n_splits: int = 4) -> dict:
    """4-fold walk-forward. Per-fold FG3M MAE delta (wide - base)."""
    from sklearn.metrics import mean_absolute_error

    rows_aug.sort(key=lambda r: r["date"])
    n = len(rows_aug)
    y = np.array([r["target_fg3m"] for r in rows_aug], dtype=float)
    yt = np.log1p(y)
    X_base = _build_X(rows_aug, base_cols)
    X_wide = _build_X(rows_aug, wide_cols)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    folds_metrics = []
    for fi, frac in enumerate(fold_ends):
        tr_end = int(n * frac)
        te_end = n if fi == n_splits - 1 else int(n * fold_ends[fi + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fi+1}: too small (tr={tr_end}, ho={te_end-va_end}) — skip",
                  flush=True)
            continue
        train_dates = [datetime.fromisoformat(rows_aug[i]["date"]) for i in range(tr_end)]
        max_d = max(train_dates)
        age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
        sw = np.exp(-_RECENCY_DECAY * age) if _RECENCY_DECAY > 0 else None
        yt_tr, yt_val = yt[:tr_end], yt[tr_end:va_end]
        y_ho = y[va_end:te_end]

        m_b = _train_lgb_q50(X_base[:tr_end], yt_tr,
                             X_base[tr_end:va_end], yt_val, sw)
        m_w = _train_lgb_q50(X_wide[:tr_end], yt_tr,
                             X_wide[tr_end:va_end], yt_val, sw)
        pb = np.clip(np.expm1(m_b.predict(X_base[va_end:te_end])), 0.0, None)
        pw = np.clip(np.expm1(m_w.predict(X_wide[va_end:te_end])), 0.0, None)
        mae_b = float(mean_absolute_error(y_ho, pb))
        mae_w = float(mean_absolute_error(y_ho, pw))
        d = mae_w - mae_b
        folds_metrics.append({"fold": fi + 1, "mae_base": mae_b,
                              "mae_wide": mae_w, "delta_mae": d})
        print(f"  fold {fi+1}: base={mae_b:.4f}  wide={mae_w:.4f}  d={d:+.4f}",
              flush=True)
    if not folds_metrics:
        return {"folds": [], "wf_4_of_4_negative": False}
    deltas = [f["delta_mae"] for f in folds_metrics]
    n_neg = int(sum(1 for d in deltas if d < 0))
    return {
        "folds": folds_metrics,
        "n_folds": len(folds_metrics),
        "n_folds_negative": n_neg,
        "wf_4_of_4_negative": (n_neg == len(folds_metrics) == 4),
        "delta_mae_mean": float(np.mean(deltas)),
        "delta_mae_std":  float(np.std(deltas)),
    }


def main() -> int:
    t0 = time.time()
    print("[cycle 100c] FG3M q50 retrain v3 with cycle-99e opp_l5 features",
          flush=True)
    print("=" * 72, flush=True)

    print("Building per-game dataset ...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    print(f"  rows={len(rows)} wall={time.time()-t0:.0f}s", flush=True)

    # Holdout-only coverage report (most recent 20% of rows).
    n = len(rows)
    holdout_rows = rows[int(n * 0.8):]
    cov = _coverage_report(holdout_rows)
    print(f"  holdout coverage: {cov}", flush=True)

    # Per-feature coverage gate.
    selected: List[str] = []
    dropped: List[Tuple[str, float]] = []
    for feat in CANDIDATE_FEATURES:
        pct = float(cov.get(f"{feat}_pct", 0.0))
        if pct >= COVERAGE_FLOOR_PCT:
            selected.append(feat)
        else:
            dropped.append((feat, pct))
    if dropped:
        print(f"  dropped (cov<{COVERAGE_FLOOR_PCT}%): {dropped}", flush=True)
    if not selected:
        out = {
            "cycle": "100c", "ship": False,
            "reason": "all_features_below_coverage_floor",
            "coverage_holdout": cov, "dropped": dropped,
        }
        path = os.path.join(_MODEL_DIR, "fg3m_q50_v3_metrics.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"REJECT: no candidate cleared {COVERAGE_FLOOR_PCT}% coverage",
              flush=True)
        return 0
    print(f"  selected features: {selected}", flush=True)

    rows_aug = [_augment_row(r) for r in rows]
    base_cols = feature_columns()
    wide_cols = base_cols + selected
    print(f"  base_cols={len(base_cols)}  wide_cols={len(wide_cols)}",
          flush=True)

    print("\nSingle-split eval ...", flush=True)
    ss = single_split_eval(rows_aug, base_cols, wide_cols)
    print(f"  baseline (85 LGB-q50): MAE={ss['mae_baseline_85']:.4f}", flush=True)
    print(f"  wide     (89 LGB-q50): MAE={ss['mae_wide']:.4f}", flush=True)
    print(f"  delta_mae (wide - base) = {ss['delta_mae']:+.4f}", flush=True)
    print(f"  delta_mae vs cycle27 0.8941 = {ss['mae_vs_cycle27']:+.4f}",
          flush=True)

    single_split_pass = ss["mae_wide"] < BASELINE_MAE
    print(f"  single_split_gate (MAE < {BASELINE_MAE}): "
          f"{'PASS' if single_split_pass else 'FAIL'}", flush=True)

    if not single_split_pass:
        out = {
            "cycle": "100c", "ship": False,
            "reason": "single_split_failed",
            "coverage_holdout": cov,
            "selected_features": selected,
            "dropped_features": dropped,
            "single_split": {k: v for k, v in ss.items() if k != "wide_model"},
            "baseline_cycle27": BASELINE_MAE,
        }
        path = os.path.join(_MODEL_DIR, "fg3m_q50_v3_metrics.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"REJECT (single-split): wrote {path}", flush=True)
        return 0

    print("\nWalk-forward 4-fold ...", flush=True)
    wf = walk_forward_eval(rows_aug, base_cols, wide_cols, n_splits=4)
    wf_pass = wf.get("wf_4_of_4_negative", False)
    print(f"  WF folds_negative={wf.get('n_folds_negative')}/{wf.get('n_folds')}  "
          f"d_mae={wf.get('delta_mae_mean'):+.4f}+-{wf.get('delta_mae_std'):.4f}",
          flush=True)
    print(f"  wf_gate (4/4 folds negative): {'PASS' if wf_pass else 'FAIL'}",
          flush=True)

    out = {
        "cycle": "100c",
        "ship": bool(single_split_pass and wf_pass),
        "coverage_holdout": cov,
        "candidate_features": list(CANDIDATE_FEATURES),
        "selected_features": selected,
        "dropped_features": dropped,
        "single_split": {k: v for k, v in ss.items() if k != "wide_model"},
        "walk_forward": wf,
        "baseline_cycle27": BASELINE_MAE,
    }

    if single_split_pass and wf_pass:
        import joblib
        path = os.path.join(_MODEL_DIR, "fg3m_q50_v3.pkl")
        joblib.dump(ss["wide_model"], path)
        out["artifact"] = path
        print(f"\nSHIP MAE={ss['mae_wide']:.4f}: wrote {path}", flush=True)
    else:
        out["reason"] = "wf_failed"
        print(f"\nREJECT (walk-forward): n_neg={wf.get('n_folds_negative')}/4",
              flush=True)

    path = os.path.join(_MODEL_DIR, "fg3m_q50_v3_metrics.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {path}  wall={time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
