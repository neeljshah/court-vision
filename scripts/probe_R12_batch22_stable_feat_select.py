"""probe_R12_batch22_stable_feat_select.py — leak-free top-50 trim strategies.

Compare 3 honest feature-selection strategies (none use the held-out fold):
  - lgb_importance : LGB's built-in feature_importances_ (gain-based, model-internal)
  - perm_inner_cv  : permutation importance via INNER CV on outer-train only
  - rfecv          : sklearn RFE-like elimination via LGB importance scores

(SHAP skipped — package not installed in this env.)

Per pregame regression target, take top-50 by each method, re-run B6 OOF-stack,
compare to B21 LIVE numbers (the honest production baseline).
"""
from __future__ import annotations
import importlib.util, json, os, sys, time
from collections import Counter
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.r12_canonical_predictor import (  # noqa: E402
    build_r12_features, _all_feature_sets,
)

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_b5)
load_data = _b5.load_data


# B21 LIVE numbers (honest, per-fold leak-free trim)
LIVE_BASELINE = {
    "total_pts_box":   {"pooled_delta_pct": -14.02, "src": "B21 LIVE (interactions_only, 141 feats)"},
    "score_diff":      {"pooled_delta_pct": -13.79, "src": "B21 LIVE (top50/opp_full, per-fold)"},
    "home_score":      {"pooled_delta_pct": -14.49, "src": "B21 LIVE (top50/all_b9, per-fold)"},
    # away_score not in B21 — use B15 frozen as reference, will mark as note
    "away_score":      {"pooled_delta_pct": -14.51, "src": "B15 nnls_top3 (frozen ref, no B21)"},
}

# Per-target canonical FEATURE SET to start from
CANON_FC_PER_TARGET = {
    "total_pts_box":   "interactions_only",
    "score_diff":      "opp_full",
    "home_score":      "all_b9",
    "away_score":      "halflife2_only",
}


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


def _oof_stack_pred(merged, fc, label, tr, ti):
    """One outer fold's B6 OOF-stack final prediction (regression only)."""
    X_tr_base = merged[fc].iloc[tr].values
    X_te_base = merged[fc].iloc[ti].values
    y_all = merged[label].astype(float).values
    y_tr = y_all[tr]
    n_tr = len(tr)
    oof = np.zeros(n_tr, dtype=float)
    inner_k = 5; inner_fs = n_tr // inner_k
    for ki in range(inner_k):
        its = ki * inner_fs
        ite = (ki + 1) * inner_fs if ki < inner_k - 1 else n_tr
        itr = list(range(0, its)) + list(range(ite, n_tr))
        iti = list(range(its, ite))
        if len(itr) < 50 or len(iti) < 5:
            continue
        m = _lgb_reg(); m.fit(X_tr_base[itr], y_tr[itr])
        oof[iti] = m.predict(X_tr_base[iti])
    mf = _lgb_reg(); mf.fit(X_tr_base, y_tr)
    test_l1 = mf.predict(X_te_base)
    X_tr_aug = np.hstack([X_tr_base, oof.reshape(-1, 1)])
    X_te_aug = np.hstack([X_te_base, test_l1.reshape(-1, 1)])
    l2_l = _lgb_reg(); l2_l.fit(X_tr_aug, y_tr)
    l2_x = _xgb_reg(); l2_x.fit(X_tr_aug, y_tr)
    return 0.5 * l2_l.predict(X_te_aug) + 0.5 * l2_x.predict(X_te_aug)


# ---------- 3 leak-free trim strategies ----------
def trim_lgb_importance(df_tr, fc, target, top_k=50):
    """LGB built-in feature_importances_ (gain-based)."""
    import lightgbm as lgb
    X = df_tr[fc].values
    y = df_tr[target].astype(float).values
    m = _lgb_reg(); m.fit(X, y)
    importances = {fc[i]: float(m.feature_importances_[i]) for i in range(len(fc))}
    ranked = sorted(fc, key=lambda c: importances.get(c, 0.0), reverse=True)
    return ranked[:top_k]


def trim_perm_inner_cv(df_tr, fc, target, top_k=50, inner_k=3, n_repeats=5):
    """Permutation importance via inner CV on outer-train only (no leakage)."""
    from sklearn.inspection import permutation_importance
    n = len(df_tr)
    fs = n // inner_k
    importances_acc = {c: 0.0 for c in fc}
    n_acc = 0
    for ki in range(inner_k):
        a = ki * fs; b = (ki + 1) * fs if ki < inner_k - 1 else n
        tr = list(range(0, a)) + list(range(b, n))
        te = list(range(a, b))
        if len(tr) < 50 or len(te) < 20:
            continue
        X_tr = df_tr[fc].iloc[tr].values
        X_te = df_tr[fc].iloc[te].values
        y = df_tr[target].astype(float).values
        m = _lgb_reg(); m.fit(X_tr, y[tr])
        r = permutation_importance(m, X_te, y[te], n_repeats=n_repeats,
                                    random_state=42, n_jobs=1,
                                    scoring="neg_mean_absolute_error")
        for i, c in enumerate(fc):
            importances_acc[c] += float(r.importances_mean[i])
        n_acc += 1
    # Average over inner folds
    if n_acc > 0:
        for c in importances_acc:
            importances_acc[c] /= n_acc
    ranked = sorted(fc, key=lambda c: importances_acc.get(c, 0.0), reverse=True)
    return ranked[:top_k]


def trim_rfe_lgb(df_tr, fc, target, top_k=50, step=10):
    """RFE-style: iteratively drop lowest-importance features by LGB built-in.
    Re-fits at each step until reaching top_k."""
    import lightgbm as lgb
    cur = list(fc)
    while len(cur) > top_k:
        X = df_tr[cur].values
        y = df_tr[target].astype(float).values
        m = _lgb_reg(); m.fit(X, y)
        importances = {cur[i]: float(m.feature_importances_[i]) for i in range(len(cur))}
        ranked = sorted(cur, key=lambda c: importances.get(c, 0.0), reverse=True)
        # Drop the bottom `step` (but not below top_k)
        drop_n = min(step, len(cur) - top_k)
        cur = ranked[:len(cur) - drop_n]
    return cur


def run_wf(merged, label, naive_pred, fc, fn_name):
    y_all = merged[label].astype(float).values
    n = len(merged)
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        y_pred = _oof_stack_pred(merged, fc, label, tr, ti)
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti]})
    return folds


def _summarize_reg(folds, name, label, n_features, meta):
    if not folds:
        return {"probe": name, "kind": "regression", "label": label, "status": "REJECT",
                "n_features": n_features, "beat_canonical": False, "variant": meta}
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    an = np.concatenate([f["y_naive"] for f in folds])
    pn = float(np.mean(np.abs(an - aa)))
    pl = float(np.mean(np.abs(al - aa)))
    dp = (pl - pn) / pn * 100.0
    fold_results = []
    for f in folds:
        lm = float(np.mean(np.abs(f["y_pred"] - f["y_true"])))
        nm = float(np.mean(np.abs(f["y_naive"] - f["y_true"])))
        d = lm - nm
        fold_results.append({"fold": f["fold"], "naive_mae": round(nm, 4),
                             "lgb_mae": round(lm, 4), "delta": round(d, 4),
                             "delta_pct": round(d / nm * 100, 2)})
    nv = len(folds)
    np_ = sum(1 for f in fold_results if f["delta"] < 0)
    ship = (nv >= 3) and (np_ == nv) and (dp <= -5.0)
    can = LIVE_BASELINE.get(label, {})
    beat = (dp < can.get("pooled_delta_pct", 0.0)) if "pooled_delta_pct" in can else None
    return {"probe": name, "kind": "regression", "label": label, "n_features": n_features,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {np_}/{nv}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(pn, 4), "pooled_lgb_mae": round(pl, 4),
            "pooled_delta_pct": round(dp, 2),
            "n_folds_positive": np_, "n_valid_folds": nv,
            "fold_results": fold_results,
            "beat_canonical": bool(beat) if beat is not None else None,
            "canonical_src": can.get("src"),
            "vs_canonical_pp": round(dp - can.get("pooled_delta_pct", 0.0), 2) if "pooled_delta_pct" in can else None,
            "variant": meta}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-22 — leak-free top-50 trim strategies (LGB-imp / inner-perm / RFE)", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = build_r12_features(merged)
    print(f"[2] R12 features built", flush=True)
    feature_sets = _all_feature_sets(merged)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    targets = [
        ("total_pts_box", "interactions_only"),
        ("score_diff",    "opp_full"),
        ("home_score",    "all_b9"),
        ("away_score",    "halflife2_only"),
    ]
    strategies = [
        ("lgb_importance", trim_lgb_importance),
        ("perm_inner_cv",  trim_perm_inner_cv),
        ("rfe_lgb",        trim_rfe_lgb),
    ]

    results = {}; n_beat = 0; n_total = 0
    for target, fc_name in targets:
        naive = naive_l5_mean(target)
        for sname, sfn in strategies:
            # Per-fold trim using ONLY outer-train data
            t_v = time.time()
            name = f"R12_B22_{sname}_{target}"
            print(f"\n[{target} / {sname}] computing per-fold trim ...", flush=True)
            n = len(merged)
            folds = []
            y_all = merged[target].astype(float).values
            for fi, tr, ti in _wf_indices(n, 4):
                if len(tr) < 250 or len(ti) < 20:
                    continue
                df_tr = merged.iloc[tr].reset_index(drop=True)
                fc_full = feature_sets[fc_name]
                df_tr[fc_full] = df_tr[fc_full].fillna(0.0)
                fc_trim = sfn(df_tr, fc_full, target, top_k=50)
                # Run B6 OOF-stack on the trimmed feature set
                y_pred = _oof_stack_pred(merged, fc_trim, target, tr, ti)
                folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                              "y_naive": naive[ti], "fc_len": len(fc_trim)})
            meta = {"variant": sname, "fc_canonical": fc_name,
                    "fc_len_per_fold": [f["fc_len"] for f in folds]}
            out = _summarize_reg(folds, name, target, 50, meta)
            out["elapsed_s"] = round(time.time() - t_v, 1)
            outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
            with open(outp, "w") as f:
                json.dump(out, f, indent=2)
            results[name] = out["status"]; n_total += 1
            beat_str = ""
            if out.get("beat_canonical") is True:
                n_beat += 1; beat_str = " BEAT_LIVE"
            elif out.get("beat_canonical") is False:
                beat_str = " (B21 LIVE wins)"
            vs = out.get("vs_canonical_pp")
            print(f"  {name}: {out['status']} delta {out['pooled_delta_pct']:+.2f}% "
                  f"vs_live={vs:+.2f}pp{beat_str} [{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS, {n_beat}/{n_total} BEAT_LIVE in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
