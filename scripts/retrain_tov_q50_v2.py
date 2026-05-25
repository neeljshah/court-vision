"""retrain_tov_q50_v2.py — cycle 101f (loop 5).

TOV LGB-q50 retrain. TOV currently dispatches to XGB-q50 (cycle 27 anchor
0.8932 holdout MAE). q1_tov_l5 was 0% covered in cycle 99 era — the spec
notes it is now ~85% covered after the cycle df36c17f per-quarter daemon
backfill. This cycle retries the wider feature set:

Candidate additive features (~7 keys; 85 base -> ~92 wide):
  q1_tov_l5             — rolling-5 Q1 TOV from data/player_quarter_stats.parquet
                          (cycle 91a wrapper; coverage check at runtime).
  opp_team_pace_l5      — opp pace L5 (more possessions => more TOV exposure)
  opp_team_tov_ratio_l5 — opp team TOV ratio L5 (style/turnover-forcing context)
  opp_def_tov_l5        — opp raw L5 TOV ALLOWED (defensive ball-pressure proxy)
  opp_def_stl_l5        — opp raw L5 STL — opp steals literally CAUSE TOV
  position_{C,F,G}      — multi-bit one-hot (guards turn it over more than bigs)

Each candidate is INDIVIDUALLY gated at 30% holdout coverage (matches cycle
99b/100b/c). Features below the floor drop from the wide set rather than
rejecting the whole cycle.

Cycle 27 baseline (XGB-q50 on the global 85-col feature set):
    TOV holdout MAE = 0.8932.

Ship gate (BOTH required):
  * single-split TOV MAE strictly DOWN (< 0.8932)
  * walk-forward 4/4 folds MAE improved vs the 85-col LGB-q50 baseline

When passing: save the wider model to data/models/tov_q50_v2.pkl AND wire
production dispatch — TOV currently uses XGB on disk; v2 ships as an LGB
quantile head, so the prod path needs the v2 artifact to be loaded by a
small predict_pergame extension or by adding TOV to _Q50_LGB_BACKEND_STATS
+ overwriting the LGB-q50 v1 with the v2 (the v1 was trained on 85 cols
and would n_features_in_-mismatch).

Coordination notes:
  * Cycles 101a/b/c/d/e are not yet present on the branch (git log clean) —
    no conflict on shared CANDIDATE_FEATURES tuples.
  * Does NOT include the cycle-100b opp_team_def_rtg_l5 / oreb_pct_l5 keys
    that were tested for BLK — those are reb/blk-oriented; TOV-relevant
    additions are pace + tov_ratio + opp_def_tov + opp_def_stl.
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
    _LOG_TRANSFORM_STATS, _MODEL_DIR, _RECENCY_DECAY,
    build_pergame_dataset, feature_columns,
)


BASELINE_MAE = 0.8932          # cycle 27 (XGB-q50) reference anchor for TOV
COVERAGE_FLOOR_PCT = 30.0      # per-feature holdout coverage gate (matches 99b)
# Candidate additive features (each individually gated at COVERAGE_FLOOR_PCT).
CANDIDATE_FEATURES: Tuple[str, ...] = (
    "q1_tov_l5",
    "opp_team_pace_l5",
    "opp_team_tov_ratio_l5",
    "opp_def_tov_l5",
    "opp_def_stl_l5",
    "position_C",
    "position_F",
    "position_G",
)
# The "position_*" features share a single source key ("position") — the
# coverage report uses one bucket for the triplet.
COVERAGE_KEY = {
    "q1_tov_l5":             "q1_tov_l5_pct",
    "opp_team_pace_l5":      "opp_team_pace_l5_pct",
    "opp_team_tov_ratio_l5": "opp_team_tov_ratio_l5_pct",
    "opp_def_tov_l5":        "opp_def_tov_l5_pct",
    "opp_def_stl_l5":        "opp_def_stl_l5_pct",
    "position_C":            "position_pct",
    "position_F":            "position_pct",
    "position_G":            "position_pct",
}


def _position_onehot(pos: object) -> Tuple[float, float, float]:
    """Multi-bit one-hot for (Center, Forward, Guard).

    Multi-position strings like 'Guard-Forward' set BOTH bits, so a
    Guard-Forward player carries position_F=1 AND position_G=1. Unknown /
    None positions produce (0, 0, 0) — same all-zero bucket players get
    when the positions parquet is absent.
    """
    if pos is None:
        return 0.0, 0.0, 0.0
    s = str(pos)
    c = 1.0 if "Center" in s else 0.0
    f = 1.0 if "Forward" in s else 0.0
    g = 1.0 if "Guard" in s else 0.0
    return c, f, g


def _safe_float(v) -> float:
    """Coerce v to float, collapsing None / NaN / non-numeric to 0.0."""
    try:
        f = float(v) if v is not None else 0.0
        if f != f:  # NaN
            f = 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _augment_row(row: dict) -> dict:
    """Return a shallow-copied row with the 8 new features filled in.

    All numeric features default to 0.0 when missing (pure additive
    extension of the base feature vector). Position one-hots default to
    (0, 0, 0) when the position string is absent.
    """
    new = dict(row)
    # Numeric features.
    for k in ("q1_tov_l5", "opp_team_pace_l5", "opp_team_tov_ratio_l5",
              "opp_def_tov_l5", "opp_def_stl_l5"):
        new[k] = _safe_float(row.get(k))
    # Position one-hot triplet.
    c, f, g = _position_onehot(row.get("position"))
    new["position_C"] = c
    new["position_F"] = f
    new["position_G"] = g
    return new


def _coverage_report(rows: List[dict]) -> dict:
    """Holdout-style coverage stats for each candidate feature.

    A row "has coverage" for a numeric feature when the SOURCE field on
    the row dict was non-None before _augment_row collapsed to 0.0.
    Position counts as covered when the source string is non-empty.
    """
    n = len(rows)
    if n == 0:
        return {"n_rows": 0}
    out: Dict[str, float] = {"n_rows": n}
    for feat in ("q1_tov_l5", "opp_team_pace_l5", "opp_team_tov_ratio_l5",
                 "opp_def_tov_l5", "opp_def_stl_l5"):
        c = sum(1 for r in rows if r.get(feat) is not None)
        out[f"{feat}_pct"] = round(100.0 * c / n, 2)
    p = sum(1 for r in rows if r.get("position"))
    out["position_pct"] = round(100.0 * p / n, 2)
    return out


def _tov_params() -> dict:
    """Match prop_quantiles._per_stat_xgb_params('tov') overrides — the LGB
    quantile head shares them via min_child_samples = max(20, mcw*2). DO NOT
    tune here per spec — only the feature set changes."""
    return dict(n_estimators=700, max_depth=3, learning_rate=0.025,
                subsample=0.8, colsample_bytree=0.8,
                min_child_weight=30, reg_lambda=6.0, reg_alpha=0.5,
                gamma=0.4, random_state=42)


def _build_X(rows: List[dict], cols: List[str]) -> np.ndarray:
    return np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in rows],
                    dtype=float)


def _train_lgb_q50(X_tr, yt_tr, X_val, yt_val, sw):
    import lightgbm as lgb
    p = _tov_params()
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

    y = np.array([r["target_tov"] for r in rows_aug], dtype=float)
    assert "tov" in _LOG_TRANSFORM_STATS, "TOV must use log1p transform"
    yt = np.log1p(y)
    y_ho = y[val_end:]
    yt_tr, yt_val = yt[:train_end], yt[train_end:val_end]

    train_dates = [datetime.fromisoformat(rows_aug[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-_RECENCY_DECAY * age) if _RECENCY_DECAY > 0 else None

    # Baseline (85 cols) — same LGB-q50 recipe as the wide model so the delta
    # is purely the feature-set effect.
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
    """4-fold walk-forward — per-fold TOV MAE delta vs the 85-col LGB-q50."""
    from sklearn.metrics import mean_absolute_error

    rows_aug.sort(key=lambda r: r["date"])
    n = len(rows_aug)
    y = np.array([r["target_tov"] for r in rows_aug], dtype=float)
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
    print("[cycle 101f] TOV q50 retrain v2 with q1_tov_l5 + opp + position",
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

    selected: List[str] = []
    dropped: List[Tuple[str, float]] = []
    for feat in CANDIDATE_FEATURES:
        pct = float(cov.get(COVERAGE_KEY[feat], 0.0))
        if pct >= COVERAGE_FLOOR_PCT:
            selected.append(feat)
        else:
            dropped.append((feat, pct))
    if dropped:
        print(f"  dropped (cov<{COVERAGE_FLOOR_PCT}%): {dropped}", flush=True)
    if not selected:
        out = {
            "cycle": "101f", "ship": False,
            "reason": "all_features_below_coverage_floor",
            "coverage_holdout": cov, "dropped": dropped,
        }
        path = os.path.join(_MODEL_DIR, "tov_q50_v2_metrics.json")
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
            "cycle": "101f",
            "ship": False,
            "reason": "single_split_failed",
            "coverage_holdout": cov,
            "selected_features": selected,
            "dropped_features": dropped,
            "single_split": {k: v for k, v in ss.items() if k != "wide_model"},
            "baseline_cycle27": BASELINE_MAE,
        }
        path = os.path.join(_MODEL_DIR, "tov_q50_v2_metrics.json")
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
        "cycle": "101f",
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
        path = os.path.join(_MODEL_DIR, "tov_q50_v2.pkl")
        joblib.dump(ss["wide_model"], path)
        out["artifact"] = path
        print(f"SHIP MAE={ss['mae_wide']:.4f}: wrote {path}", flush=True)
        print("Next step: production dispatch wire-in — add TOV to "
              "_Q50_LGB_BACKEND_STATS and point _load_q50_model at "
              "tov_q50_v2.pkl OR add a v2 fallback path. Other stats "
              "unchanged (this script touched no other artifact).", flush=True)
    else:
        out["reason"] = "wf_failed"
        print(f"REJECT (walk-forward): n_neg={wf.get('n_folds_negative')}/4",
              flush=True)

    path = os.path.join(_MODEL_DIR, "tov_q50_v2_metrics.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {path}  wall={time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
