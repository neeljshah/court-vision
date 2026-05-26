"""probe_R12_batch29_player_prop_other_stats.py - extend B18 avg_blend pattern to REB/AST/FG3M.

B18 found avg_blend pattern FAILED for player-prop PTS because form features
dominated single-model strength (form_only = 4.69 vs full = 4.66; opp_only = 6.74
much worse; blends regressed).

This batch tests whether the form-dominance pattern is PTS-SPECIFIC or
UNIVERSAL across other 7-stat-lineup player props (REB / AST / FG3M).

For each of REB / AST / FG3M (3 stats):
  - baseline_full   : single LGB+XGB on ALL features
  - form_only       : L5/L10/EWMA/std/prev features only
  - opp_only        : opp_def_ + rest/travel/context features only
  - avg_blend_top2  : 50/50 of baseline_full + form_only
  - avg_blend_top3  : 1/3 of baseline_full + form_only + opp_only

5 variants × 3 stats = 15 runs. Records beat_baseline (vs within-probe full)
and beat_prod (vs CLAUDE memory references: REB 1.90, AST 1.36, FG3M 0.89).
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.prop_pergame import build_pergame_dataset, feature_columns  # noqa: E402


# Production MAE references (per CLAUDE memory + B18 PTS finding)
PROD_REFERENCE = {
    "reb":  1.90,
    "ast":  1.36,
    "fg3m": 0.89,
}


def _form_feature_columns(all_cols):
    return [c for c in all_cols
            if any(c.startswith(p) for p in ("l5_", "l10_", "std_", "ewma_", "prev_"))]


def _opp_context_feature_columns(all_cols):
    out = []
    context_cols = {"rest_days", "is_home", "is_b2b", "is_b3b",
                    "miles_traveled", "altitude_ft", "days_since_last_game",
                    "games_since_long_absence", "games_played"}
    for c in all_cols:
        if c.startswith("opp_def_") or c in context_cols:
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
                      "ti_idx": ti})
    return folds


def _summarize(folds, name, stat, target_col, n_features, meta, baseline_mae=None):
    if not folds:
        return {"probe": name, "kind": "regression", "label": target_col,
                "status": "REJECT", "n_features": n_features, "variant": meta}
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    pl = float(np.mean(np.abs(al - aa)))
    prod_ref = PROD_REFERENCE.get(stat)
    if baseline_mae is not None:
        beat_baseline = pl < baseline_mae
        vs_baseline = round((pl - baseline_mae) / baseline_mae * 100.0, 2)
    else:
        beat_baseline = False
        vs_baseline = None
    beat_prod = (prod_ref is not None) and (pl < prod_ref)
    return {"probe": name, "kind": "regression", "label": target_col,
            "stat": stat, "n_features": n_features,
            "status": "SHIP" if beat_baseline else "REJECT",
            "pooled_lgb_mae": round(pl, 4),
            "baseline_mae": baseline_mae,
            "prod_reference_mae": prod_ref,
            "beat_baseline": bool(beat_baseline),
            "beat_prod": bool(beat_prod),
            "vs_baseline_pct": vs_baseline,
            "variant": meta}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-29 - player-prop avg_blend extended to REB/AST/FG3M", flush=True)
    print("=" * 70, flush=True)

    print("[1] building per-game dataset (heavy join pipeline) ...", flush=True)
    rows, fc_all = build_pergame_dataset(min_prior=5)
    df = pd.DataFrame(rows)
    df = df.sort_values("date").reset_index(drop=True)
    print(f"  loaded {len(df)} player-game rows; {len(fc_all)} feature cols", flush=True)

    df[fc_all] = df[fc_all].fillna(0.0)
    fc_form = _form_feature_columns(fc_all)
    fc_opp = _opp_context_feature_columns(fc_all)
    print(f"  feature subsets: full={len(fc_all)} form={len(fc_form)} opp={len(fc_opp)}", flush=True)

    stats_to_run = ["reb", "ast", "fg3m"]
    results = {}
    n_ship = 0; n_beat_prod = 0; n_total = 0
    for stat in stats_to_run:
        target_col = f"target_{stat}"
        if target_col not in df.columns:
            print(f"\n[{stat}] SKIP - column {target_col} not in dataframe", flush=True)
            continue
        df_stat = df[df[target_col].notna()].reset_index(drop=True)
        print(f"\n[{stat}] {len(df_stat)} rows; target mean={df_stat[target_col].mean():.3f} "
              f"std={df_stat[target_col].std():.3f}", flush=True)

        single_variants = [
            ("baseline_full", fc_all),
            ("form_only",     fc_form),
            ("opp_only",      fc_opp),
        ]
        per_variant_folds = {}
        baseline_mae = None
        for vname, fc in single_variants:
            t_v = time.time()
            folds = run_variant(df_stat, fc, target_col)
            per_variant_folds[vname] = folds
            name = f"R12_B29_{vname}_{stat}"
            meta = {"variant": vname, "n_features": len(fc), "stat": stat}
            out = _summarize(folds, name, stat, target_col, len(fc), meta, baseline_mae)
            out["elapsed_s"] = round(time.time() - t_v, 1)
            if vname == "baseline_full":
                baseline_mae = out["pooled_lgb_mae"]
                print(f"  [baseline_full] MAE={baseline_mae:.4f} "
                      f"(prod ref {PROD_REFERENCE[stat]:.2f}) "
                      f"beat_prod={'YES' if out['beat_prod'] else 'no'}", flush=True)
            else:
                prod_str = " BEAT_PROD" if out['beat_prod'] else ""
                ship_str = " SHIP" if out['beat_baseline'] else " (baseline_full wins)"
                print(f"  {name}: MAE {out['pooled_lgb_mae']:.4f} "
                      f"vs_baseline={out['vs_baseline_pct']:+.2f}%{ship_str}{prod_str} "
                      f"[{out['elapsed_s']}s]", flush=True)
            outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
            with open(outp, "w") as f:
                json.dump(out, f, indent=2)
            results[name] = out["status"]; n_total += 1
            if out['beat_baseline']:
                n_ship += 1
            if out['beat_prod']:
                n_beat_prod += 1

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
            meta = {"variant": bname, "models_used": vs, "stat": stat}
            name = f"R12_B29_{bname}_{stat}"
            out = _summarize(folds, name, stat, target_col, len(fc_all), meta, baseline_mae)
            outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
            with open(outp, "w") as f:
                json.dump(out, f, indent=2)
            results[name] = out["status"]; n_total += 1
            if out['beat_baseline']:
                n_ship += 1
            if out['beat_prod']:
                n_beat_prod += 1
            prod_str = " BEAT_PROD" if out['beat_prod'] else ""
            ship_str = " SHIP" if out['beat_baseline'] else " (baseline_full wins)"
            print(f"  {name}: MAE {out['pooled_lgb_mae']:.4f} "
                  f"vs_baseline={out['vs_baseline_pct']:+.2f}%{ship_str}{prod_str}",
                  flush=True)

    print(f"\n[done] {n_ship}/{n_total} SHIP (beat within-probe baseline_full), "
          f"{n_beat_prod}/{n_total} BEAT_PROD memory reference in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
