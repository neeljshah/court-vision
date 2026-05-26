"""probe_R12_batch18_player_prop_avg_blend.py — apply R12 avg_blend to PTS prop.

Test if the B13/B15 model-level avg_blend pattern transfers from game-level
to player-prop predictions. Target = PTS only (highest-volume stat).

Reuses src/prediction/prop_pergame.build_pergame_dataset for the feature/label
table, then runs 4 variants:
  - baseline_full   : single LGB+XGB ensemble on ALL features (current pattern)
  - form_only       : single LGB+XGB on form features only (L5/L10/EWMA/std/prev)
  - opp_only        : single LGB+XGB on opponent-defence + context features only
  - avg_blend_top2  : 50/50 average of (baseline_full + form_only) predictions
  - avg_blend_top3  : 1/3 average of (baseline_full + form_only + opp_only)

Compares against baseline_full as the within-probe reference. Records
beat_baseline flag for each blend.
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.prop_pergame import build_pergame_dataset, feature_columns, STATS  # noqa


# Current production reference (per memory) — beating these is a stretch goal.
PROD_PTS_MAE_REFERENCE = 4.62  # PTS sqrt+Huber blend per CLAUDE memory


# Form-pattern names: anything starting with l5_/l10_/std_/ewma_/prev_
def _form_feature_columns(all_cols):
    out = []
    for c in all_cols:
        if any(c.startswith(p) for p in ("l5_", "l10_", "std_", "ewma_", "prev_")):
            out.append(c)
    return out


# Opponent-defence + context features
def _opp_context_feature_columns(all_cols):
    out = []
    for c in all_cols:
        if (c.startswith("opp_def_") or
            c in ("rest_days", "is_home", "is_b2b", "is_b3b",
                  "miles_traveled", "altitude_ft", "days_since_last_game",
                  "games_since_long_absence", "games_played")):
            out.append(c)
    return out


def _lgb_reg():
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)


def _xgb_reg():
    import xgboost as xgb
    return xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=2, verbosity=0)


def _wf_indices(n, k):
    fs = n // k
    out = []
    for fi in range(k):
        ts = fi * fs
        te = (fi + 1) * fs if fi < k - 1 else n
        out.append((fi, list(range(0, ts)), list(range(ts, te))))
    return out


def _train_single(X_tr, y_tr, X_te):
    l = _lgb_reg(); l.fit(X_tr, y_tr)
    x = _xgb_reg(); x.fit(X_tr, y_tr)
    return 0.5 * l.predict(X_te) + 0.5 * x.predict(X_te)


def run_variant(df, fc, target_col):
    """4-fold WF, single LGB+XGB on a feature subset. Returns per-fold preds."""
    y = df[target_col].astype(float).values
    n = len(df)
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 100 or len(ti) < 20:
            continue
        X_tr = df[fc].iloc[tr].values
        X_te = df[fc].iloc[ti].values
        pred = _train_single(X_tr, y[tr], X_te)
        folds.append({"fold": fi, "y_true": y[ti], "y_pred": pred,
                      "tr_idx": tr, "ti_idx": ti})
    return folds


def _summarize(folds, name, target_col, n_features, meta, baseline_mae=None):
    if not folds:
        return {"probe": name, "kind": "regression", "label": target_col,
                "status": "REJECT", "n_features": n_features, "variant": meta}
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    pl = float(np.mean(np.abs(al - aa)))
    fold_results = [{"fold": f["fold"],
                     "fold_mae": round(float(np.mean(np.abs(f["y_pred"] - f["y_true"]))), 4)}
                    for f in folds]
    nv = len(folds)
    # Ship gate: MAE < baseline_mae (within-probe) OR <= PROD reference
    if baseline_mae is not None:
        beat_baseline = pl < baseline_mae
        beat_pp = round((pl - baseline_mae) / baseline_mae * 100.0, 2)
    else:
        beat_baseline = pl < PROD_PTS_MAE_REFERENCE
        beat_pp = round((pl - PROD_PTS_MAE_REFERENCE) / PROD_PTS_MAE_REFERENCE * 100.0, 2)
    beat_prod = pl < PROD_PTS_MAE_REFERENCE
    ship = beat_baseline and nv >= 3
    return {"probe": name, "kind": "regression", "label": target_col,
            "n_features": n_features,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"MAE {pl:.4f} (baseline {baseline_mae}, prod ref {PROD_PTS_MAE_REFERENCE})",
            "pooled_lgb_mae": round(pl, 4),
            "n_valid_folds": nv,
            "fold_results": fold_results,
            "beat_baseline": bool(beat_baseline),
            "beat_prod": bool(beat_prod),
            "vs_baseline_pct": beat_pp,
            "variant": meta}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-18 — PIVOT to player-prop avg_blend (PTS)", flush=True)
    print("=" * 70, flush=True)

    print("[1] building per-game dataset (this may take a few min) ...", flush=True)
    rows, fc_all = build_pergame_dataset(min_prior=5)
    df = pd.DataFrame(rows)
    df = df.sort_values("date").reset_index(drop=True)
    target_col = "target_pts"
    if target_col not in df.columns:
        print(f"[FATAL] {target_col} not in dataframe columns: {list(df.columns)[:20]}", flush=True)
        return
    df = df[df[target_col].notna()].reset_index(drop=True)
    print(f"  loaded {len(df)} player-game rows; {len(fc_all)} feature cols", flush=True)
    print(f"  PTS target mean={df[target_col].mean():.2f}, std={df[target_col].std():.2f}", flush=True)

    fc_form = _form_feature_columns(fc_all)
    fc_opp = _opp_context_feature_columns(fc_all)
    print(f"  fc_all: {len(fc_all)}, fc_form: {len(fc_form)}, fc_opp: {len(fc_opp)}", flush=True)

    # Fill NaN in feature cols
    df[fc_all] = df[fc_all].fillna(0.0)

    # Run 3 single-model variants
    variants_single = [
        ("baseline_full", fc_all),
        ("form_only", fc_form),
        ("opp_only", fc_opp),
    ]
    per_variant_folds = {}
    results = {}
    baseline_mae = None
    for vname, fc in variants_single:
        t_v = time.time()
        folds = run_variant(df, fc, target_col)
        per_variant_folds[vname] = folds
        meta = {"variant": vname, "n_features": len(fc)}
        name = f"R12_B18_{vname}_PTS"
        out = _summarize(folds, name, target_col, len(fc), meta, baseline_mae)
        out["elapsed_s"] = round(time.time() - t_v, 1)
        if vname == "baseline_full":
            baseline_mae = out["pooled_lgb_mae"]
            print(f"  [baseline set] MAE={baseline_mae:.4f}", flush=True)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        beat = "SHIP" if out["status"] == "SHIP" else "REJECT"
        prod_str = " BEAT_PROD" if out["beat_prod"] else ""
        print(f"  {name}: {beat} MAE {out['pooled_lgb_mae']:.4f} "
              f"vs_baseline={out['vs_baseline_pct']:+.2f}%{prod_str} [{out['elapsed_s']}s]",
              flush=True)

    # Build avg_blend variants from cached fold predictions
    def _avg_blend_folds(variant_names):
        out_folds = []
        n_folds = len(per_variant_folds[variant_names[0]])
        for fi_idx in range(n_folds):
            preds = [per_variant_folds[v][fi_idx]["y_pred"] for v in variant_names]
            avg = np.mean(np.column_stack(preds), axis=1)
            out_folds.append({
                "fold": per_variant_folds[variant_names[0]][fi_idx]["fold"],
                "y_true": per_variant_folds[variant_names[0]][fi_idx]["y_true"],
                "y_pred": avg,
            })
        return out_folds

    blends = [
        ("avg_blend_top2", ["baseline_full", "form_only"]),
        ("avg_blend_top3", ["baseline_full", "form_only", "opp_only"]),
    ]
    for bname, vs in blends:
        folds = _avg_blend_folds(vs)
        meta = {"variant": bname, "models_used": vs}
        name = f"R12_B18_{bname}_PTS"
        # n_features is representative — use baseline_full size
        out = _summarize(folds, name, target_col, len(fc_all), meta, baseline_mae)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        prod_str = " BEAT_PROD" if out["beat_prod"] else ""
        print(f"  {name}: {out['status']} MAE {out['pooled_lgb_mae']:.4f} "
              f"vs_baseline={out['vs_baseline_pct']:+.2f}%{prod_str}",
              flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
