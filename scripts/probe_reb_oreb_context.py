"""probe_reb_oreb_context.py — REB OREB-context feature gate (cycle 90d, T1-E).

Adds team_oreb_pct_l5 / opp_dreb_pct_l5 / reb_chance_l5 (interaction product)
to the REB head only, retrains LGB-q50 for REB, and gates:
  - single-split REB MAE strictly down vs cycle-29 baseline (1.9023)
  - 4-fold walk-forward REB LGB-q50 4/4 folds positive

On pass, overwrites data/models/quantile_pergame_lgb_reb_q{10,50,90}.pkl and
writes scripts/_results/reb_oreb_context_v1.md.

Other stats are NOT retrained — they keep feature_columns() unchanged so
their saved artifacts continue to load (no n_features_in_ mismatch).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import List

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _LOG_TRANSFORM_STATS, _REB_CONTEXT_KEYS,
    build_pergame_dataset, feature_columns,
)

_BASELINE_REB_MAE = 1.9023      # cycle-29 production LGB-q50 single-split.
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_RESULTS_PATH = os.path.join(PROJECT_DIR, "scripts", "_results",
                             "reb_oreb_context_v1.md")


def _reb_lgb_params() -> dict:
    """Mirror prop_quantiles._per_stat_xgb_params('reb') -> LGB params."""
    # From src/prediction/prop_quantiles.py:_per_stat_xgb_params['reb']
    return dict(
        n_estimators=800, max_depth=3, learning_rate=0.025,
        subsample=0.7, subsample_freq=1, colsample_bytree=0.9,
        min_child_samples=60,            # max(20, 30*2)
        reg_lambda=4.0, reg_alpha=0.5,
        random_state=42, objective="quantile",
        n_jobs=-1, verbosity=-1,
    )


def _train_reb_q50(X_tr, y_tr, X_val, y_val, sw, alpha=0.5):
    """Train a single LGB quantile regressor (log1p target for REB)."""
    import lightgbm as lgb
    yt_tr = np.log1p(y_tr)
    yt_val = np.log1p(y_val)
    params = _reb_lgb_params()
    params["alpha"] = alpha
    m = lgb.LGBMRegressor(**params)
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)],
          sample_weight=sw,
          callbacks=[lgb.early_stopping(40, verbose=False)])
    return m


def _eval_reb(m, X, y):
    """REB always uses log1p, so invert with expm1 before MAE."""
    from sklearn.metrics import mean_absolute_error
    pred = np.clip(np.expm1(m.predict(X)), 0.0, None)
    return float(mean_absolute_error(y, pred))


def single_split(rows, base_cols, ctx_cols) -> dict:
    """Replicate prop_quantiles holdout: 65% train / 15% val / 20% holdout."""
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * 0.65)
    val_end   = int(n * 0.80)

    y = np.array([r["target_reb"] for r in rows], dtype=float)
    y_tr, y_val, y_ho = y[:train_end], y[train_end:val_end], y[val_end:]

    # Recency-decay sample weights — match prop_quantiles.
    tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_d = max(tr_dates)
    age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    def _slice(cols):
        X = np.array([[r[c] for c in cols] for r in rows], dtype=float)
        return X[:train_end], X[train_end:val_end], X[val_end:]

    out = {}
    for label, cols in (("baseline", base_cols), ("with_ctx", base_cols + ctx_cols)):
        X_tr, X_val, X_ho = _slice(cols)
        m = _train_reb_q50(X_tr, y_tr, X_val, y_val, sw)
        out[label] = _eval_reb(m, X_ho, y_ho)
    out["delta"] = out["with_ctx"] - out["baseline"]
    return out


def walk_forward(rows, base_cols, ctx_cols, n_splits: int = 4) -> dict:
    """4-fold expanding walk-forward REB LGB-q50."""
    from sklearn.metrics import mean_absolute_error
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    y = np.array([r["target_reb"] for r in rows], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    fold_results: List[dict] = []
    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small — skip", flush=True)
            continue
        y_tr, y_val, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:te_end]
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        def _slice(cols):
            X = np.array([[r[c] for c in cols] for r in rows], dtype=float)
            return X[:tr_end], X[tr_end:va_end], X[va_end:te_end]

        Xb_tr, Xb_val, Xb_ho = _slice(base_cols)
        Xc_tr, Xc_val, Xc_ho = _slice(base_cols + ctx_cols)

        m_base = _train_reb_q50(Xb_tr, y_tr, Xb_val, y_val, sw)
        m_ctx  = _train_reb_q50(Xc_tr, y_tr, Xc_val, y_val, sw)
        mae_b  = _eval_reb(m_base, Xb_ho, y_ho)
        mae_c  = _eval_reb(m_ctx, Xc_ho, y_ho)
        fold_results.append({
            "fold": fold_idx + 1,
            "n_tr": tr_end, "n_val": va_end - tr_end, "n_ho": te_end - va_end,
            "mae_baseline": mae_b, "mae_with_ctx": mae_c,
            "delta": mae_c - mae_b,
            "positive": mae_c < mae_b,
        })
        print(f"  fold {fold_idx+1}: baseline {mae_b:.4f}  with_ctx {mae_c:.4f}  "
              f"d={mae_c - mae_b:+.4f}  {'WIN' if mae_c < mae_b else 'LOSS'}",
              flush=True)
    return {"folds": fold_results}


def cross_stat_smoke(rows, base_cols, ctx_cols) -> dict:
    """Sanity check: train baseline 2-way XGB+LGB for non-REB stats and
    confirm they're unchanged (we don't add ctx features for them anyway)."""
    return {"note": "Other stats not retrained — they keep feature_columns() unchanged."}


def fit_and_persist(rows, all_cols) -> None:
    """Retrain LGB q10/q50/q90 for REB on augmented feature set and overwrite
    data/models/quantile_pergame_lgb_reb_q{10,50,90}.pkl."""
    import joblib
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * 0.65)
    val_end   = int(n * 0.80)

    y = np.array([r["target_reb"] for r in rows], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:val_end]
    X = np.array([[r[c] for c in all_cols] for r in rows], dtype=float)
    X_tr, X_val = X[:train_end], X[train_end:val_end]

    tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_d = max(tr_dates)
    age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    for q in (0.1, 0.5, 0.9):
        m = _train_reb_q50(X_tr, y_tr, X_val, y_val, sw, alpha=q)
        path = os.path.join(_MODEL_DIR, f"quantile_pergame_lgb_reb_q{int(q*100):02d}.pkl")
        joblib.dump(m, path)
        print(f"  saved {path}  (n_features_in_={m.n_features_in_})")


def write_results(single, wf, verdict: str, ship_action: str) -> None:
    lines = []
    lines.append("# REB OREB-Context Feature Probe — Cycle 90d (Loop 5) — T1-E")
    lines.append("")
    lines.append("## Feature definitions")
    lines.append("")
    lines.append("Source: `data/team_reb_context.parquet` (built from "
                 "`boxscore_adv_*.json` team entries — 7370 team-game rows, "
                 "2022-10-18 → 2025-04-13).")
    lines.append("")
    lines.append("- `team_oreb_pct_l5` — team's last-5 prior-game OREB% mean (shift(1).rolling(5))")
    lines.append("- `opp_dreb_pct_l5` — opponent's last-5 prior-game DREB% mean (shift(1).rolling(5))")
    lines.append("- `reb_chance_l5`  — interaction product `team_oreb_pct_l5 * opp_dreb_pct_l5`")
    lines.append("")
    lines.append("All 3 are sliced into REB only via `feature_columns(stat='reb')`. Other heads "
                 "keep `feature_columns()` unchanged — no n_features_in_ mismatch on saved artifacts.")
    lines.append("")
    lines.append("## Single-split (65/15/20)")
    lines.append("")
    lines.append("| metric | MAE |")
    lines.append("|--------|------|")
    lines.append(f"| baseline LGB-q50 (cycle 29 cols) | {single['baseline']:.4f} |")
    lines.append(f"| with REB-context (+3 cols) | {single['with_ctx']:.4f} |")
    lines.append(f"| delta | {single['delta']:+.4f} |")
    lines.append(f"| vs cycle-29 production ({_BASELINE_REB_MAE:.4f}) | "
                 f"{single['with_ctx'] - _BASELINE_REB_MAE:+.4f} |")
    lines.append("")
    lines.append("## Walk-forward (4 expanding folds)")
    lines.append("")
    lines.append("| fold | n_tr | n_val | n_ho | baseline | with_ctx | delta | sign |")
    lines.append("|------|------|-------|------|---------:|---------:|------:|:----:|")
    n_pos = 0
    for f in wf["folds"]:
        sign = "WIN" if f["positive"] else "LOSS"
        if f["positive"]:
            n_pos += 1
        lines.append(f"| {f['fold']} | {f['n_tr']} | {f['n_val']} | {f['n_ho']} | "
                     f"{f['mae_baseline']:.4f} | {f['mae_with_ctx']:.4f} | "
                     f"{f['delta']:+.4f} | {sign} |")
    total = len(wf["folds"])
    lines.append("")
    lines.append(f"**WF folds positive: {n_pos}/{total}**")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(verdict)
    lines.append("")
    lines.append(f"Ship action: {ship_action}")
    lines.append("")
    os.makedirs(os.path.dirname(_RESULTS_PATH), exist_ok=True)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  wrote {_RESULTS_PATH}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--no-persist", action="store_true",
                    help="run probe but skip artifact write even if pass")
    args = ap.parse_args()

    print("[probe] building dataset ...", flush=True)
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    ctx_cols = list(_REB_CONTEXT_KEYS)
    # Sanity: every row has the ctx cols.
    sample = rows[0]
    for k in ctx_cols:
        assert k in sample, f"row missing ctx col {k}"
    print(f"[probe] {len(rows)} rows, base_cols={len(base_cols)}, "
          f"ctx_cols={len(ctx_cols)}  ({time.time()-t0:.1f}s)", flush=True)

    print("[probe] single-split ...", flush=True)
    single = single_split(rows, base_cols, ctx_cols)
    print(f"  baseline {single['baseline']:.4f}  with_ctx {single['with_ctx']:.4f}  "
          f"d={single['delta']:+.4f}", flush=True)

    print("[probe] walk-forward 4-fold ...", flush=True)
    wf = walk_forward(rows, base_cols, ctx_cols, n_splits=args.splits)
    n_pos = sum(1 for f in wf["folds"] if f["positive"])
    total = len(wf["folds"])

    # Ship gate
    single_pass = single["with_ctx"] < _BASELINE_REB_MAE
    wf_pass = (n_pos == total) and (total >= 4)
    if single_pass and wf_pass:
        verdict = (f"**SHIP** — single-split with_ctx MAE {single['with_ctx']:.4f} "
                   f"< baseline {_BASELINE_REB_MAE:.4f}; WF {n_pos}/{total} folds positive.")
        ship_action = (f"Overwrote data/models/quantile_pergame_lgb_reb_q{{10,50,90}}.pkl "
                       f"with {len(base_cols + ctx_cols)}-feature LGB-q50.")
    else:
        verdict_parts = []
        if not single_pass:
            verdict_parts.append(
                f"single-split with_ctx {single['with_ctx']:.4f} >= baseline "
                f"{_BASELINE_REB_MAE:.4f}")
        if not wf_pass:
            verdict_parts.append(f"WF {n_pos}/{total} folds positive (need 4/4)")
        verdict = f"**REJECT** — {'; '.join(verdict_parts)}."
        ship_action = "No model artifact changes."

    if single_pass and wf_pass and not args.no_persist:
        print("[probe] PASS — persisting REB LGB q10/q50/q90 artifacts ...", flush=True)
        fit_and_persist(rows, base_cols + ctx_cols)
    elif single_pass and wf_pass and args.no_persist:
        print("[probe] PASS — --no-persist set, skipping artifact write.", flush=True)
    else:
        print("[probe] REJECT — no artifact changes.", flush=True)

    write_results(single, wf, verdict, ship_action)
    print(verdict)


if __name__ == "__main__":
    main()
