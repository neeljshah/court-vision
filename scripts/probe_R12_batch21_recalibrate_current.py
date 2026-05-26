"""probe_R12_batch21_recalibrate_current.py — re-baseline R12 canonicals on
current dataset (2865+ games) using r12_canonical_predictor module exclusively.

B19 numbers were captured on a 2839-game dataset. R26_S2 backfilled 2025-26
linescores (+26 games), so the live numbers differ. This probe records the
LIVE per-target performance using the exact production module API.

Single-model / top50 targets (4): use train_canonical_model + 4-fold WF.
Ensemble targets (away_score nnls_top3, AH3 top4_avg): not bundled here —
documented as deferred to scripts/probe_R12_batch15_top3_top4_blends.py.

Output: live_metrics.json mapping target → observed pooled metric, plus
the same numbers logged into state.json for downstream visibility.
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.r12_canonical_predictor import (  # noqa: E402
    build_r12_features, get_canonical_feature_set,
    train_canonical_model, predict_canonical,
    CANONICAL_RECIPES, _all_feature_sets,
)

import importlib.util
_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_b5)
load_data = _b5.load_data


# R12 reference numbers (from B19) for delta reporting
R12_REFERENCE = {
    "total_pts_box":   {"reference_delta_pct": -16.27, "src": "B9 interactions_only (frozen 2839g)"},
    "score_diff":      {"reference_delta_pct": -17.71, "src": "B19 keep_top50/opp_full (frozen 2839g)"},
    "home_score":      {"reference_delta_pct": -16.86, "src": "B19 keep_top50/all_b9 (frozen 2839g)"},
    "over_230":        {"reference_brier": 0.2321, "reference_auc": 0.6843,
                        "src": "B19 keep_top50/opp_full (frozen 2839g)"},
}


def _wf_indices(n, k):
    fs = n // k
    out = []
    for fi in range(k):
        ts = fi * fs
        te = (fi + 1) * fs if fi < k - 1 else n
        out.append((fi, list(range(0, ts)), list(range(ts, te))))
    return out


def _naive_l5_mean(merged, col):
    return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
        merged[col].mean()).values


def _naive_l5_prop(merged, col):
    return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
        merged[col].mean()).clip(0.01, 0.99).values


def run_recalibrate_target(merged, target, kind, feature_sets):
    """4-fold WF using the production module's train_canonical_model + predict.
    Per-fold the feature set is re-derived from outer-train ONLY for top50 trim
    to avoid test-side leakage in the perm-importance step.
    """
    naive = _naive_l5_mean(merged, target) if kind == "reg" else _naive_l5_prop(merged, target)
    y_all = merged[target].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    recipe = CANONICAL_RECIPES[target]
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        df_tr = merged.iloc[tr].reset_index(drop=True)
        # Derive fc from outer-train side to keep top50 trim leak-free
        fc = get_canonical_feature_set(target, df_tr,
                                         feature_sets=_all_feature_sets(df_tr))
        df_tr[fc] = df_tr[fc].fillna(0.0)
        model = train_canonical_model(df_tr, target, fc=fc, kind=kind)
        X_te = merged[fc].iloc[ti].fillna(0.0).values
        y_pred = predict_canonical(model, X_te)
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive[ti], "fc_len": len(fc)})
    return folds


def _summarize(folds, target, kind):
    if not folds:
        return {"target": target, "status": "FAIL_NO_FOLDS"}
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    an = np.concatenate([f["y_naive"] for f in folds])
    if kind == "reg":
        pn = float(np.mean(np.abs(an - aa)))
        pl = float(np.mean(np.abs(al - aa)))
        dp = (pl - pn) / pn * 100.0
        fold_pcts = []
        for f in folds:
            lm = float(np.mean(np.abs(f["y_pred"] - f["y_true"])))
            nm = float(np.mean(np.abs(f["y_naive"] - f["y_true"])))
            fold_pcts.append((lm - nm) / nm * 100.0)
        ref = R12_REFERENCE.get(target, {})
        ref_dp = ref.get("reference_delta_pct")
        return {"target": target, "kind": kind,
                "live_pooled_delta_pct": round(dp, 2),
                "live_pooled_naive_mae": round(pn, 4),
                "live_pooled_lgb_mae": round(pl, 4),
                "reference_delta_pct": ref_dp,
                "reference_src": ref.get("src"),
                "delta_vs_reference_pp": round(dp - ref_dp, 2) if ref_dp else None,
                "fold_delta_pcts": [round(p, 2) for p in fold_pcts],
                "n_folds": len(folds),
                "fc_len_per_fold": [f["fc_len"] for f in folds]}
    from sklearn.metrics import brier_score_loss, roc_auc_score
    pnb = float(brier_score_loss(aa, an))
    plb = float(brier_score_loss(aa, al))
    try:
        plu = float(roc_auc_score(aa, al))
    except Exception:
        plu = float("nan")
    ref = R12_REFERENCE.get(target, {})
    return {"target": target, "kind": kind,
            "live_pooled_brier": round(plb, 5), "live_pooled_naive_brier": round(pnb, 5),
            "live_pooled_auc": round(plu, 5),
            "reference_brier": ref.get("reference_brier"),
            "reference_auc": ref.get("reference_auc"),
            "reference_src": ref.get("src"),
            "n_folds": len(folds),
            "fc_len_per_fold": [f["fc_len"] for f in folds]}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-21 — re-baseline canonicals on current dataset", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games (was 2839 at B19)", flush=True)
    merged = build_r12_features(merged)
    print(f"[2] R12 features built", flush=True)
    feature_sets = _all_feature_sets(merged)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    targets = [
        ("reg", "total_pts_box"),
        ("reg", "score_diff"),
        ("reg", "home_score"),
        ("bin", "over_230"),
    ]
    live_metrics = {}
    for kind, target in targets:
        t_v = time.time()
        print(f"\n[{target}] kind={kind} ...", flush=True)
        folds = run_recalibrate_target(merged, target, kind, feature_sets)
        summary = _summarize(folds, target, kind)
        summary["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"probe_R12_B21_recal_{target}_results.json")
        with open(outp, "w") as f:
            json.dump(summary, f, indent=2)
        live_metrics[target] = summary
        if kind == "reg":
            ref_dp = summary.get("reference_delta_pct")
            live = summary.get("live_pooled_delta_pct")
            d_vs = summary.get("delta_vs_reference_pp")
            print(f"  LIVE delta {live:+.2f}% (ref {ref_dp:+.2f}%, "
                  f"drift {d_vs:+.2f}pp) "
                  f"fc_len_per_fold={summary['fc_len_per_fold']} "
                  f"[{summary['elapsed_s']}s]", flush=True)
        else:
            print(f"  LIVE Brier {summary['live_pooled_brier']:.4f} "
                  f"(ref {summary['reference_brier']:.4f}), "
                  f"AUC {summary['live_pooled_auc']:.4f} "
                  f"(ref {summary['reference_auc']:.4f}) "
                  f"fc_len_per_fold={summary['fc_len_per_fold']} "
                  f"[{summary['elapsed_s']}s]", flush=True)

    # Aggregated summary
    out_all = os.path.join(DATA_CACHE, "probe_R12_B21_live_metrics_summary.json")
    with open(out_all, "w") as f:
        json.dump({
            "dataset_size": len(merged),
            "reference_dataset_size": 2839,
            "drift_games": len(merged) - 2839,
            "live_metrics": live_metrics,
        }, f, indent=2)
    print(f"\n[done] re-baseline complete in {time.time()-t0:.1f}s", flush=True)
    print(f"  full summary written to {out_all}", flush=True)


if __name__ == "__main__":
    main()
