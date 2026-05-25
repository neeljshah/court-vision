"""retrain_blk_q50_v3.py — cycle 100b (loop 5).

BLK LGB-q50 retrain with cycle-99e opp-context rolling-5 features that were
ADDITIVE-ONLY on the row dict pre-99e (NOT in feature_columns()):

  opp_team_pace_l5      — opponent's rolling-5 team PACE (more possessions ->
                          more shot attempts -> more BLK opportunities)
  opp_team_def_rtg_l5   — opponent's rolling-5 team defensive rating (worse
                          defence -> more shot attempts the team gives up)
  opp_team_oreb_pct_l5  — opponent's rolling-5 OREB% (second-chance volume
                          impacts BLK opportunity)
  opp_def_blk_l5        — opponent's last-5 raw allowed BLK mean (sibling of
                          opp_def_blk which is the EXPANDING-to-date ratio)

Cycle 99a (loop 5) REJECTED a BLK retrain that included q1_blk_l5 because
that feature had 0% holdout coverage (parquet only spans 2024-10/11/12). All
four cycle-100b features have ~100% coverage per cycle-99e probe.

Cycle 27 baseline (XGB-q50 on the global 85-col feature set):
    BLK holdout MAE = 0.4398.

Production today dispatches BLK -> XGB-q50 (quantile_pergame_blk_q50.json).
This cycle trains an LGB-q50 with the 4 new features; if both ship gates pass
we ALSO need to flip BLK into _Q50_LGB_BACKEND_STATS so predict_pergame loads
the new artifact (blk_q50_v3.pkl) via the LGB branch.

Ship gate (BOTH required):
  * single-split BLK MAE strictly DOWN (< 0.4398)
  * walk-forward 4/4 folds MAE improved vs the 85-col LGB-q50 baseline

When passing: save the wider model to data/models/blk_q50_v3.pkl. Production
dispatch wire-in is a follow-up edit (this script ships ONLY the artifact +
metrics so the result is reviewable before any predict_pergame change).

Coordination notes:
  * cycles 100a/c/d/e may also extend the opp-context feature set. To avoid
    name collisions, this script registers the new keys via a module-level
    constant (CANDIDATE_FEATURES) — future cycles should SHARE this set
    instead of stat-specific gating.
  * Does NOT include q1_blk_l5 (cycle 99a coverage failure).
  * Does NOT change LGB-q50 hyperparameters — only the feature set.
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
    _LOG_TRANSFORM_STATS, build_pergame_dataset, feature_columns,
)


MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
BASELINE_MAE = 0.4398          # cycle 27 (XGB-q50) reference anchor
COVERAGE_FLOOR_PCT = 30.0      # per-feature holdout coverage gate (matches 99b)
# Candidate opp-context features (additive ON TOP OF the 85-col baseline).
# Each is INDIVIDUALLY gated at COVERAGE_FLOOR_PCT — features below the floor
# get dropped from the wide set (rather than rejecting the whole cycle). All
# four are sourced from cycle-99e wrappers in prop_pergame.py:
#   opp_team_*_l5 -> _TeamAdvancedL5 (data/team_advanced_stats.parquet)
#   opp_def_blk_l5 -> _OpponentDefense.l5_allowed (already in gamelog)
CANDIDATE_FEATURES = (
    "opp_team_pace_l5",
    "opp_team_def_rtg_l5",
    "opp_team_oreb_pct_l5",
    "opp_def_blk_l5",
)


def _augment_row(row: dict) -> dict:
    """Return a shallow-copied row with the 4 new features filled in.

    Each feature defaults to 0.0 when missing (so the row is a pure additive
    extension of the base feature vector). Non-finite values (NaN) also
    collapse to 0.0 — keeps LGB happy without dropping rows.
    """
    new = dict(row)
    for feat in CANDIDATE_FEATURES:
        v = row.get(feat)
        try:
            fv = float(v) if v is not None else 0.0
            if fv != fv:  # NaN
                fv = 0.0
        except (TypeError, ValueError):
            fv = 0.0
        new[feat] = fv
    return new


def _coverage_report(rows: List[dict]) -> dict:
    """Holdout-style coverage stats for each candidate feature.

    A row "has coverage" for a feature when the SOURCE field on the row dict
    was non-None before _augment_row collapsed to 0.0.
    """
    n = len(rows)
    if n == 0:
        return {"n_rows": 0}
    out: Dict[str, float] = {"n_rows": n}
    for feat in CANDIDATE_FEATURES:
        c = sum(1 for r in rows if r.get(feat) is not None)
        out[f"{feat}_pct"] = round(100.0 * c / n, 2)
    return out


def _blk_params() -> dict:
    """Match prop_quantiles._per_stat_xgb_params('blk') overrides — the LGB
    quantile head shares them via min_child_samples = max(20, mcw*2). DO NOT
    tune here per spec — only the feature set changes."""
    return dict(n_estimators=800, max_depth=3, learning_rate=0.06,
                subsample=0.8, colsample_bytree=1.0,
                min_child_weight=25, reg_lambda=4.0, reg_alpha=0.5,
                gamma=0.4, random_state=42)


def _build_X(rows: List[dict], cols: List[str]) -> np.ndarray:
    return np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in rows],
                    dtype=float)


def _train_lgb_q50(X_tr, yt_tr, X_val, yt_val, sw):
    import lightgbm as lgb
    p = _blk_params()
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
    """Train BOTH 85-col baseline LGB-q50 and (85+k)-col wide LGB-q50 on the
    same chronological split; compare holdout MAE for BLK."""
    from sklearn.metrics import mean_absolute_error

    rows_aug.sort(key=lambda r: r["date"])
    n = len(rows_aug)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end = int(n * (1.0 - holdout_frac))

    y = np.array([r["target_blk"] for r in rows_aug], dtype=float)
    assert "blk" in _LOG_TRANSFORM_STATS, "BLK must use log1p transform"
    yt = np.log1p(y)
    y_ho = y[val_end:]
    yt_tr, yt_val = yt[:train_end], yt[train_end:val_end]

    # Recency weights match production train_quantile_models.
    train_dates = [datetime.fromisoformat(rows_aug[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    # Baseline (85 cols) — same LGB-q50 recipe as the wide model so the delta
    # is purely the feature-set effect.
    X_base = _build_X(rows_aug, base_cols)
    m_base = _train_lgb_q50(X_base[:train_end], yt_tr,
                            X_base[train_end:val_end], yt_val, sw)
    base_pred = np.clip(np.expm1(m_base.predict(X_base[val_end:])), 0.0, None)
    mae_base = float(mean_absolute_error(y_ho, base_pred))

    # Wide (85+k cols)
    X_wide = _build_X(rows_aug, wide_cols)
    m_wide = _train_lgb_q50(X_wide[:train_end], yt_tr,
                            X_wide[train_end:val_end], yt_val, sw)
    wide_pred = np.clip(np.expm1(m_wide.predict(X_wide[val_end:])), 0.0, None)
    mae_wide = float(mean_absolute_error(y_ho, wide_pred))

    return {
        "n_rows": n, "n_train": train_end, "n_val": val_end - train_end,
        "n_holdout": n - val_end,
        "mae_baseline_85":  mae_base,
        "mae_wide":         mae_wide,
        "delta_mae":        mae_wide - mae_base,
        "mae_vs_cycle27":   mae_wide - BASELINE_MAE,
        "wide_model":       m_wide,
        "wide_pred_sample": wide_pred[:25].tolist(),
    }


def walk_forward_eval(rows_aug: List[dict],
                      base_cols: List[str],
                      wide_cols: List[str],
                      n_splits: int = 4) -> dict:
    """4-fold walk-forward — per-fold BLK MAE delta vs the 85-col LGB-q50."""
    from sklearn.metrics import mean_absolute_error

    rows_aug.sort(key=lambda r: r["date"])
    n = len(rows_aug)
    y = np.array([r["target_blk"] for r in rows_aug], dtype=float)
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
        sw = np.exp(-0.5 * age)
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
    print("[cycle 100b] BLK q50 retrain v3 with opp_l5 features (99e unlock)",
          flush=True)

    print("Building per-game dataset ...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    print(f"  rows={len(rows)} wall={time.time()-t0:.0f}s", flush=True)

    # Holdout-only coverage report (most recent 20% of rows).
    n = len(rows)
    holdout_rows = rows[int(n * 0.8):]
    cov = _coverage_report(holdout_rows)
    print(f"  holdout coverage: {cov}", flush=True)

    # Per-feature 30% coverage gate. Each candidate is included only when its
    # source field crosses the floor — preserves the rest of the cycle when
    # one feature has thin coverage. If EVERYTHING drops, reject outright.
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
            "cycle": "100b", "ship": False,
            "reason": "all_features_below_coverage_floor",
            "coverage_holdout": cov, "dropped": dropped,
        }
        path = os.path.join(MODEL_DIR, "blk_q50_v3_metrics.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"REJECT: no candidate cleared {COVERAGE_FLOOR_PCT}% coverage",
              flush=True)
        return 0
    print(f"  selected features: {selected}", flush=True)

    rows_aug = [_augment_row(r) for r in rows]
    base_cols = feature_columns()
    wide_cols = base_cols + selected
    print(f"  base_cols={len(base_cols)}  wide_cols={len(wide_cols)}", flush=True)

    print("Single-split eval ...", flush=True)
    ss = single_split_eval(rows_aug, base_cols, wide_cols)
    print(f"  baseline (85 LGB-q50): MAE={ss['mae_baseline_85']:.4f}", flush=True)
    print(f"  wide     ({len(wide_cols)} LGB-q50): MAE={ss['mae_wide']:.4f}",
          flush=True)
    print(f"  delta_mae (wide - base) = {ss['delta_mae']:+.4f}", flush=True)
    print(f"  delta_mae vs cycle27 anchor {BASELINE_MAE} = {ss['mae_vs_cycle27']:+.4f}",
          flush=True)

    single_split_pass = ss["mae_wide"] < BASELINE_MAE
    print(f"  single_split_gate (MAE < {BASELINE_MAE}): "
          f"{'PASS' if single_split_pass else 'FAIL'}", flush=True)

    if not single_split_pass:
        out = {
            "cycle": "100b",
            "ship": False,
            "reason": "single_split_failed",
            "coverage_holdout": cov,
            "selected_features": selected,
            "dropped_features": dropped,
            "single_split": {k: v for k, v in ss.items() if k != "wide_model"},
            "baseline_cycle27": BASELINE_MAE,
        }
        path = os.path.join(MODEL_DIR, "blk_q50_v3_metrics.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"REJECT (single-split): wrote {path}", flush=True)
        return 0

    print("Walk-forward 4-fold ...", flush=True)
    wf = walk_forward_eval(rows_aug, base_cols, wide_cols, n_splits=4)
    wf_pass = wf.get("wf_4_of_4_negative", False)
    print(f"  WF folds_negative={wf.get('n_folds_negative')}/{wf.get('n_folds')}  "
          f"d_mae={wf.get('delta_mae_mean'):+.4f}+-{wf.get('delta_mae_std'):.4f}",
          flush=True)
    print(f"  wf_gate (4/4 folds negative): {'PASS' if wf_pass else 'FAIL'}",
          flush=True)

    out = {
        "cycle": "100b",
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
        path = os.path.join(MODEL_DIR, "blk_q50_v3.pkl")
        joblib.dump(ss["wide_model"], path)
        out["artifact"] = path
        print(f"SHIP MAE={ss['mae_wide']:.4f}: wrote {path}", flush=True)
        print("Next step: add BLK to _Q50_LGB_BACKEND_STATS and update the "
              "loader to point at blk_q50_v3.pkl.", flush=True)
    else:
        out["reason"] = "wf_failed"
        print(f"REJECT (walk-forward): n_neg={wf.get('n_folds_negative')}/4",
              flush=True)

    path = os.path.join(MODEL_DIR, "blk_q50_v3_metrics.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {path}  wall={time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
