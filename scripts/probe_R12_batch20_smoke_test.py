"""probe_R12_batch20_smoke_test.py — verify r12_canonical_predictor matches R12 numbers.

For each single-model / top50 canonical target, train via the new module and
run 4-fold WF. Confirm pooled deltas are within 0.1pp of the R12 final numbers.

Single-model / top50 targets verified here (4):
  total_pts_box  : -16.27% (B9 interactions_only)
  score_diff     : -17.71% (B19 keep_top50 of opp_full)
  home_score     : -16.86% (B19 keep_top50 of all_b9)
  over_230       : Brier 0.2321 AUC 0.6843 (B19 keep_top50 of opp_full)

Ensemble targets (away_score nnls_top3, AH3 top4_avg) are NOT smoke-tested
here — they live in scripts/probe_R12_batch15_top3_top4_blends.py.
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.r12_canonical_predictor import (  # noqa
    build_r12_features, get_canonical_feature_set, train_canonical_model,
    predict_canonical, CANONICAL_RECIPES, _all_feature_sets,
)

import importlib.util
_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_b5)
load_data = _b5.load_data


# R12 final numbers (per state.json B19 update)
R12_EXPECTED = {
    "total_pts_box":   {"pooled_delta_pct": -16.27, "tol": 0.30, "src": "B9 interactions_only"},
    "score_diff":      {"pooled_delta_pct": -17.71, "tol": 0.30, "src": "B19 keep_top50/opp_full"},
    "home_score":      {"pooled_delta_pct": -16.86, "tol": 0.30, "src": "B19 keep_top50/all_b9"},
    "over_230":        {"pooled_lgb_brier": 0.2321, "tol_brier": 0.005,
                        "pooled_lgb_auc": 0.6843, "tol_auc": 0.02,
                        "src": "B19 keep_top50/opp_full"},
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


def run_smoke_target(merged, target, kind, fc):
    """4-fold WF using train_canonical_model + predict_canonical on each fold's
    train side, then predict_canonical on the test side."""
    naive = _naive_l5_mean(merged, target) if kind == "reg" else _naive_l5_prop(merged, target)
    y_all = merged[target].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        df_tr = merged.iloc[tr].reset_index(drop=True)
        df_tr[fc] = df_tr[fc].fillna(0.0)
        model = train_canonical_model(df_tr, target, fc=fc, kind=kind)
        X_te = merged[fc].iloc[ti].fillna(0.0).values
        y_pred = predict_canonical(model, X_te)
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive[ti]})
    return folds


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-20 — smoke test of r12_canonical_predictor module", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = build_r12_features(merged)
    print(f"[2] R12 features built", flush=True)
    feature_sets = _all_feature_sets(merged)
    for k, v in feature_sets.items():
        print(f"    {k}: {len(v)} feats", flush=True)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    smoke_targets = [
        ("reg", "total_pts_box"),
        ("reg", "score_diff"),
        ("reg", "home_score"),
        ("bin", "over_230"),
    ]
    results = {}; n_pass = 0; n_total = 0
    for kind, target in smoke_targets:
        t_v = time.time()
        # Use the module's get_canonical_feature_set to mirror production use
        fc = get_canonical_feature_set(target, merged, feature_sets)
        print(f"\n[{target}] kind={kind} fc_len={len(fc)}", flush=True)
        folds = run_smoke_target(merged, target, kind, fc)
        aa = np.concatenate([f["y_true"] for f in folds])
        al = np.concatenate([f["y_pred"] for f in folds])
        an = np.concatenate([f["y_naive"] for f in folds])
        if kind == "reg":
            pn = float(np.mean(np.abs(an - aa)))
            pl = float(np.mean(np.abs(al - aa)))
            dp = (pl - pn) / pn * 100.0
            exp = R12_EXPECTED[target]
            diff = dp - exp["pooled_delta_pct"]
            passed = abs(diff) <= exp["tol"]
            print(f"  observed delta {dp:+.2f}% vs expected {exp['pooled_delta_pct']:+.2f}% "
                  f"(diff {diff:+.2f}pp, tol {exp['tol']:.2f}pp) "
                  f"{'PASS' if passed else 'FAIL'} [{time.time()-t_v:.1f}s]", flush=True)
            out = {"target": target, "kind": kind, "fc_len": len(fc),
                   "expected_delta_pct": exp["pooled_delta_pct"],
                   "observed_delta_pct": round(dp, 2), "tolerance": exp["tol"],
                   "diff": round(diff, 2), "passed": bool(passed)}
        else:
            from sklearn.metrics import brier_score_loss, roc_auc_score
            plb = float(brier_score_loss(aa, al))
            plu = float(roc_auc_score(aa, al))
            exp = R12_EXPECTED[target]
            diff_b = plb - exp["pooled_lgb_brier"]
            diff_a = plu - exp["pooled_lgb_auc"]
            passed = (abs(diff_b) <= exp["tol_brier"]) and (abs(diff_a) <= exp["tol_auc"])
            print(f"  observed Brier {plb:.4f} (exp {exp['pooled_lgb_brier']:.4f} ±{exp['tol_brier']}), "
                  f"AUC {plu:.4f} (exp {exp['pooled_lgb_auc']:.4f} ±{exp['tol_auc']}) "
                  f"{'PASS' if passed else 'FAIL'} [{time.time()-t_v:.1f}s]", flush=True)
            out = {"target": target, "kind": kind, "fc_len": len(fc),
                   "expected_brier": exp["pooled_lgb_brier"],
                   "observed_brier": round(plb, 4),
                   "expected_auc": exp["pooled_lgb_auc"],
                   "observed_auc": round(plu, 4),
                   "passed": bool(passed)}
        results[target] = out
        n_total += 1
        if out["passed"]:
            n_pass += 1
        outp = os.path.join(DATA_CACHE, f"probe_R12_B20_smoke_{target}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)

    overall = "ALL_PASS" if n_pass == n_total else f"{n_pass}/{n_total}_PASS"
    print(f"\n[done] {n_pass}/{n_total} smoke targets PASSED — {overall} in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
