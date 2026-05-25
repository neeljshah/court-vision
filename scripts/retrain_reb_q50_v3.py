"""retrain_reb_q50_v3.py — cycle 101d (loop 5).

REB LGB-q50 retrain with the cycle-99e opp-context features PLUS q1_reb_l5
(unlocked by cycle df36c17f — per-quarter daemon brought coverage from 0% to
~85% on the current 2025-26 holdout slice) PLUS position_C/F/G one-hots
(rebound is heavily position-dependent — centers grab ~3x more REB than
guards per cycle 96e probe).

Why we retry: cycle 100d (retrain_reb_q50_v2.py) shipped the 4 opp features
alone but rejected at WF 2/4 (mean delta +0.0004). The hypothesis was that
opp context alone is too weak a signal for REB — REB is dominated by PLAYER
role (position) and CONTEXT IN GAME (Q1 rebound rate proxies effort/scheme).
With q1_reb_l5 now covered AND position one-hots added, the feature stack is
materially wider than 100d.

Candidate features (additive on row dict; not in feature_columns()):
  opp_team_oreb_pct_l5  — opp's last-5 OREB% (rebound chances available)
  opp_team_dreb_pct_l5  — opp's last-5 DREB% (rebound chances available)
  opp_team_pace_l5      — opp's last-5 pace (more poss -> more boards)
  opp_def_reb_l5        — opp's last-5 raw REB allowed
  q1_reb_l5             — player's last-5 prior Q1 REB (effort/scheme proxy)
  position_C            — center bucket (1 if "Center" in position string)
  position_F            — forward bucket
  position_G            — guard bucket

Per-feature 30% holdout coverage gate matches cycle 100d — features below
the floor are dropped from the wide set without killing the cycle.

Ship gate (BOTH required):
  1. Single-split REB holdout MAE strictly DOWN (< 1.9023 cycle-29 anchor)
  2. Walk-forward (4 folds) REB MAE 4/4 folds negative (improvement)
  3. Other stats unchanged — this script never overwrites any other head.

When passing: persist data/models/reb_q50_v3.pkl + metrics + emit a
production-dispatch hint. Failing: REJECT cleanly, write metrics, leave the
cycle-29 quantile_pergame_lgb_reb_q50.pkl in production.

Coordination notes:
  * cycles 101a/b/c/e/f may also be in flight — this script only writes the
    REB v3 artifact + its own metrics file. No other heads are touched.
  * The 4 opp features are SHARED with cycle 100d but the script uses a
    fresh CANDIDATE_FEATURES tuple to allow independent gating.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _LOG_TRANSFORM_STATS, _MODEL_DIR, _RECENCY_DECAY,
    build_pergame_dataset, feature_columns,
)


BASELINE_MAE = 1.9023            # cycle-29 LGB-q50 REB anchor (from
                                  # quantile_pergame_metrics.json '0.5'.mae_q_lgb)
COVERAGE_FLOOR_PCT = 30.0        # per-feature holdout coverage gate

# Opp-context features (4) — populated on the row dict by build_pergame_dataset
# (cycle 99e block). These were tested alone in cycle 100d (WF 2/4 fail).
_OPP_FEATURES: Tuple[str, ...] = (
    "opp_team_oreb_pct_l5",
    "opp_team_dreb_pct_l5",
    "opp_team_pace_l5",
    "opp_def_reb_l5",
)

# Q1 rolling-5 REB. Source: data/player_quarter_stats.parquet via
# _PlayerQuarterStats.rolling_q1_prior; the field name on the row dict is
# "q1_reb_l5". Cycle df36c17f brought holdout coverage from 0% -> ~85%.
_Q1_FEATURE = "q1_reb_l5"

# Position one-hots (3). Source: data/player_positions.parquet -> row["position"]
# (string like "Center" / "Guard-Forward" / None). Multi-position strings light
# up multiple buckets via substring match — same convention as
# scripts/retrain_blk_q50_v2.py and scripts/retrain_fg3m_q50_v2.py.
_POSITION_BUCKETS: Tuple[str, ...] = ("position_C", "position_F", "position_G")

# Full candidate set the script considers (each individually gated).
CANDIDATE_FEATURES: Tuple[str, ...] = _OPP_FEATURES + (_Q1_FEATURE,) + _POSITION_BUCKETS

# Map a candidate to the coverage-report key.
COVERAGE_KEY = {f: f"{f}_pct" for f in CANDIDATE_FEATURES}


# ── helpers ─────────────────────────────────────────────────────────────────

def _position_one_hot(pos: Optional[str]) -> dict:
    """Substring-match {Center, Forward, Guard} -> {position_C, position_F,
    position_G}. Hybrid positions light up multiple buckets; None/empty -> all
    zeros (implicit unknown bucket). Matches the BLK v2 / FG3M v2 convention."""
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


def _coverage_report(rows: List[dict]) -> dict:
    """Per-feature non-None coverage stats over `rows`. NaN counts as missing.

    Position buckets count as covered when row["position"] is a truthy string
    (so the bucket either fires or sits at 0.0 deliberately). The 4 opp_*
    features + q1_reb_l5 count as covered when the source field is non-None
    AND finite.
    """
    n = len(rows)
    if n == 0:
        return {"n_rows": 0}
    out: dict = {"n_rows": n}

    # opp_* + q1_reb_l5 — direct source-field coverage
    for feat in _OPP_FEATURES + (_Q1_FEATURE,):
        c = 0
        for r in rows:
            v = r.get(feat)
            if v is None:
                continue
            try:
                fv = float(v)
                if fv != fv:  # NaN
                    continue
                c += 1
            except (TypeError, ValueError):
                continue
        out[COVERAGE_KEY[feat]] = round(100.0 * c / n, 2)

    # position_* one-hots share a single source field — report once per bucket
    # so individual gating still works (e.g. if Centers are missing from a
    # holdout slice, only position_C drops).
    for bucket in _POSITION_BUCKETS:
        c = 0
        for r in rows:
            pos = r.get("position")
            if not pos:
                continue
            oh = _position_one_hot(pos)
            if oh.get(bucket, 0.0) > 0.5:
                c += 1
        out[COVERAGE_KEY[bucket]] = round(100.0 * c / n, 2)
    return out


def _augment_row(row: dict) -> dict:
    """Return a shallow-copied row with the candidate features collapsed to
    finite floats (None / NaN -> 0.0). LGB never sees NaN from this path."""
    new = dict(row)
    # opp_* + q1_reb_l5
    for feat in _OPP_FEATURES + (_Q1_FEATURE,):
        v = row.get(feat)
        try:
            fv = float(v) if v is not None else 0.0
            if fv != fv:
                fv = 0.0
        except (TypeError, ValueError):
            fv = 0.0
        new[feat] = fv
    # position one-hots
    oh = _position_one_hot(row.get("position"))
    for bucket in _POSITION_BUCKETS:
        new[bucket] = float(oh.get(bucket, 0.0))
    return new


def _reb_params() -> dict:
    """Match prop_quantiles._per_stat_xgb_params('reb') overrides so the
    baseline arm of the eval is comparable to cycle-29's persisted model."""
    return dict(n_estimators=800, max_depth=3, learning_rate=0.025,
                subsample=0.7, colsample_bytree=0.9,
                min_child_weight=30, reg_lambda=4.0, reg_alpha=0.5,
                gamma=0.3, random_state=42)


def _build_X(rows: List[dict], cols: List[str]) -> np.ndarray:
    return np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in rows],
                    dtype=float)


def _train_lgb_q50(X_tr, yt_tr, X_val, yt_val, sw):
    """LGB-q50 with cycle-29 REB hyperparameters."""
    import lightgbm as lgb
    p = _reb_params()
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


def _inv_log(v: np.ndarray) -> np.ndarray:
    return np.clip(np.expm1(v), 0.0, None)


# ── single-split eval ───────────────────────────────────────────────────────

def single_split_eval(rows_aug: List[dict],
                      base_cols: List[str],
                      wide_cols: List[str],
                      holdout_frac: float = 0.20,
                      val_frac: float = 0.15) -> dict:
    """Train BOTH the 85-col baseline and the wide-col model on the same
    chronological split; compare REB holdout MAE."""
    from sklearn.metrics import mean_absolute_error

    rows_aug.sort(key=lambda r: r["date"])
    n = len(rows_aug)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end = int(n * (1.0 - holdout_frac))

    assert "reb" in _LOG_TRANSFORM_STATS, "REB must use log1p transform"
    y = np.array([r["target_reb"] for r in rows_aug], dtype=float)
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
    base_pred = _inv_log(m_base.predict(X_base[val_end:]))
    mae_base = float(mean_absolute_error(y_ho, base_pred))

    X_wide = _build_X(rows_aug, wide_cols)
    m_wide = _train_lgb_q50(X_wide[:train_end], yt_tr,
                            X_wide[train_end:val_end], yt_val, sw)
    wide_pred = _inv_log(m_wide.predict(X_wide[val_end:]))
    mae_wide = float(mean_absolute_error(y_ho, wide_pred))

    return {
        "n_rows": n, "n_train": train_end, "n_val": val_end - train_end,
        "n_holdout": n - val_end,
        "mae_baseline_85": mae_base,
        "mae_wide":        mae_wide,
        "delta_mae":       mae_wide - mae_base,
        "mae_vs_cycle29":  mae_wide - BASELINE_MAE,
        "wide_model":      m_wide,
        "wide_pred_sample": wide_pred[:25].tolist(),
    }


# ── walk-forward eval ───────────────────────────────────────────────────────

def walk_forward_eval(rows_aug: List[dict],
                      base_cols: List[str],
                      wide_cols: List[str],
                      n_splits: int = 4) -> dict:
    """4-fold walk-forward REB MAE delta (wide - baseline)."""
    from sklearn.metrics import mean_absolute_error

    rows_aug.sort(key=lambda r: r["date"])
    n = len(rows_aug)
    y = np.array([r["target_reb"] for r in rows_aug], dtype=float)
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
        pb = _inv_log(m_b.predict(X_base[va_end:te_end]))
        pw = _inv_log(m_w.predict(X_wide[va_end:te_end]))
        mae_b = float(mean_absolute_error(y_ho, pb))
        mae_w = float(mean_absolute_error(y_ho, pw))
        d = mae_w - mae_b
        folds_metrics.append({
            "fold": fi + 1, "n_tr": tr_end, "n_val": va_end - tr_end,
            "n_ho": te_end - va_end,
            "mae_base": mae_b, "mae_wide": mae_w, "delta_mae": d,
        })
        print(f"  fold {fi+1}: tr={tr_end} ho={te_end-va_end}  "
              f"base={mae_b:.4f}  wide={mae_w:.4f}  d={d:+.4f}",
              flush=True)
    if not folds_metrics:
        return {"folds": [], "wf_4_of_4_negative": False, "n_folds": 0}
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


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    t0 = time.time()
    print("[cycle 101d] REB q50 retrain v3 with q1_reb_l5 unlocked + opp + position",
          flush=True)
    print("=" * 72, flush=True)

    print("Building per-game dataset ...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    if not rows:
        print("REJECT: no rows built — gamelog cache empty.", flush=True)
        return 1
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
            "cycle": "101d", "ship": False,
            "reason": "all_features_below_coverage_floor",
            "coverage_holdout": cov, "dropped": dropped,
        }
        path = os.path.join(_MODEL_DIR, "reb_q50_v3_metrics.json")
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

    print("\nSingle-split eval (65/15/20 chronological) ...", flush=True)
    ss = single_split_eval(rows_aug, base_cols, wide_cols)
    print(f"  baseline ({len(base_cols)} LGB-q50): MAE={ss['mae_baseline_85']:.4f}",
          flush=True)
    print(f"  wide     ({len(wide_cols)} LGB-q50): MAE={ss['mae_wide']:.4f}",
          flush=True)
    print(f"  delta_mae (wide - base) = {ss['delta_mae']:+.4f}", flush=True)
    print(f"  delta_mae vs cycle29 {BASELINE_MAE:.4f} = {ss['mae_vs_cycle29']:+.4f}",
          flush=True)

    single_split_pass = ss["mae_wide"] < BASELINE_MAE
    print(f"  single_split_gate (MAE < {BASELINE_MAE}): "
          f"{'PASS' if single_split_pass else 'FAIL'}", flush=True)

    if not single_split_pass:
        out = {
            "cycle": "101d",
            "ship": False,
            "reason": "single_split_failed",
            "coverage_holdout": cov,
            "selected_features": selected,
            "dropped_features": dropped,
            "single_split": {k: v for k, v in ss.items() if k != "wide_model"},
            "baseline_cycle29": BASELINE_MAE,
        }
        path = os.path.join(_MODEL_DIR, "reb_q50_v3_metrics.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"REJECT (single-split): wrote {path}", flush=True)
        return 0

    print(f"\nWalk-forward 4-fold ...", flush=True)
    wf = walk_forward_eval(rows_aug, base_cols, wide_cols, n_splits=4)
    wf_pass = wf.get("wf_4_of_4_negative", False)
    print(f"  WF folds_negative={wf.get('n_folds_negative')}/{wf.get('n_folds')}  "
          f"d_mae={wf.get('delta_mae_mean'):+.4f}+-{wf.get('delta_mae_std'):.4f}",
          flush=True)
    print(f"  wf_gate (4/4 folds negative): {'PASS' if wf_pass else 'FAIL'}",
          flush=True)

    out = {
        "cycle": "101d",
        "ship": bool(single_split_pass and wf_pass),
        "coverage_holdout": cov,
        "candidate_features": list(CANDIDATE_FEATURES),
        "selected_features": selected,
        "dropped_features": dropped,
        "single_split": {k: v for k, v in ss.items() if k != "wide_model"},
        "walk_forward": wf,
        "baseline_cycle29": BASELINE_MAE,
    }

    if single_split_pass and wf_pass:
        import joblib
        path = os.path.join(_MODEL_DIR, "reb_q50_v3.pkl")
        joblib.dump(ss["wide_model"], path)
        out["artifact"] = path
        out["selected_features_order"] = selected   # column order is load-bearing
        print(f"SHIP MAE={ss['mae_wide']:.4f}: wrote {path}", flush=True)
        print(f"\nNext: wire prop_pergame._load_q50_model to dispatch REB -> "
              f"reb_q50_v3.pkl (cols = feature_columns() + {selected}) and update "
              f"the production REB anchor from {BASELINE_MAE:.4f} to "
              f"{ss['mae_wide']:.4f}.", flush=True)
    else:
        out["reason"] = "wf_failed" if single_split_pass else "single_split_failed"
        print(f"REJECT (walk-forward): n_neg={wf.get('n_folds_negative')}/"
              f"{wf.get('n_folds')}", flush=True)

    path = os.path.join(_MODEL_DIR, "reb_q50_v3_metrics.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {path}  wall={time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
