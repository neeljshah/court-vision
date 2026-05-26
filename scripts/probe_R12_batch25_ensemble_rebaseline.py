"""probe_R12_batch25_ensemble_rebaseline.py - honest re-baseline of B15 ensembles.

B15 introduced:
  - nnls_top3 for away_score: 3-model ensemble (halflife2_only + all_b9 + interactions_only)
    blended with NNLS weights learned on outer-train OOF.
  - top4_avg for AH3:         4-model ensemble (intersection + opp_pts_pace + opp_full + all_b9)
    with simple equal-weight average.

These were honest by construction at B15 time, but the dataset has grown
(2865 -> 3045 games). Re-run on current data to lock in HONEST LIVE numbers
for production reporting and downstream serialization (B26).

Comparison: B15 frozen numbers
  away_score nnls_top3: -14.51%
  home_cover_AH3 top4_avg: Brier 0.2271 AUC 0.7115

Output: live numbers per ensemble + drift analysis (live vs frozen).
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


B15_FROZEN = {
    "away_score":     {"pooled_delta_pct": -14.51, "src": "B15 nnls_top3 frozen (2839 games)"},
    "home_cover_AH3": {"pooled_brier": 0.2271, "pooled_auc": 0.7115,
                       "src": "B15 top4_avg frozen (2839 games)"},
}


def _lgb_reg():
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)


def _lgb_clf():
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=42, n_jobs=2, verbose=-1)


def _xgb_reg():
    import xgboost as xgb
    return xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=2, verbosity=0)


def _xgb_clf():
    import xgboost as xgb
    return xgb.XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=2, verbosity=0, eval_metric="logloss")


def _wf_indices(n, k):
    fs = n // k
    out = []
    for fi in range(k):
        ts = fi * fs
        te = (fi + 1) * fs if fi < k - 1 else n
        out.append((fi, list(range(0, ts)), list(range(ts, te))))
    return out


def _oof_stack_pred(merged, fc, label, kind, tr, ti):
    """B6 OOF-stack final pred for one outer fold using given fc."""
    X_tr_base = merged[fc].iloc[tr].values
    X_te_base = merged[fc].iloc[ti].values
    y_all = merged[label].astype(int if kind == "bin" else float).values
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
        if kind == "reg":
            m = _lgb_reg(); m.fit(X_tr_base[itr], y_tr[itr])
            oof[iti] = m.predict(X_tr_base[iti])
        else:
            m = _lgb_clf(); m.fit(X_tr_base[itr], y_tr[itr])
            oof[iti] = m.predict_proba(X_tr_base[iti])[:, 1]
    if kind == "reg":
        mf = _lgb_reg(); mf.fit(X_tr_base, y_tr)
        test_l1 = mf.predict(X_te_base)
    else:
        mf = _lgb_clf(); mf.fit(X_tr_base, y_tr)
        test_l1 = mf.predict_proba(X_te_base)[:, 1]
    X_tr_aug = np.hstack([X_tr_base, oof.reshape(-1, 1)])
    X_te_aug = np.hstack([X_te_base, test_l1.reshape(-1, 1)])
    if kind == "reg":
        l2_l = _lgb_reg(); l2_l.fit(X_tr_aug, y_tr)
        l2_x = _xgb_reg(); l2_x.fit(X_tr_aug, y_tr)
        test_pred = 0.5 * l2_l.predict(X_te_aug) + 0.5 * l2_x.predict(X_te_aug)
        # Inner-inner 3-fold OOF on outer-train for NNLS blender fitting
        oof_l2 = np.zeros(n_tr)
        kk = 3; kf = n_tr // kk
        for kki in range(kk):
            a = kki * kf; b = (kki + 1) * kf if kki < kk - 1 else n_tr
            ttr = list(range(0, a)) + list(range(b, n_tr))
            tte = list(range(a, b))
            if len(ttr) < 50 or len(tte) < 5:
                continue
            ml = _lgb_reg(); ml.fit(X_tr_aug[ttr], y_tr[ttr])
            mx = _xgb_reg(); mx.fit(X_tr_aug[ttr], y_tr[ttr])
            oof_l2[tte] = 0.5 * ml.predict(X_tr_aug[tte]) + 0.5 * mx.predict(X_tr_aug[tte])
        return test_pred, oof_l2
    else:
        l2_l = _lgb_clf(); l2_l.fit(X_tr_aug, y_tr)
        l2_x = _xgb_clf(); l2_x.fit(X_tr_aug, y_tr)
        test_pred = 0.5 * l2_l.predict_proba(X_te_aug)[:, 1] + \
                    0.5 * l2_x.predict_proba(X_te_aug)[:, 1]
        oof_l2 = np.zeros(n_tr)
        kk = 3; kf = n_tr // kk
        for kki in range(kk):
            a = kki * kf; b = (kki + 1) * kf if kki < kk - 1 else n_tr
            ttr = list(range(0, a)) + list(range(b, n_tr))
            tte = list(range(a, b))
            if len(ttr) < 50 or len(tte) < 5:
                continue
            ml = _lgb_clf(); ml.fit(X_tr_aug[ttr], y_tr[ttr])
            mx = _xgb_clf(); mx.fit(X_tr_aug[ttr], y_tr[ttr])
            oof_l2[tte] = 0.5 * ml.predict_proba(X_tr_aug[tte])[:, 1] + \
                          0.5 * mx.predict_proba(X_tr_aug[tte])[:, 1]
        return test_pred, oof_l2


def _nnls_weights(P_oof, y_tr):
    from scipy.optimize import nnls
    w, _ = nnls(P_oof, y_tr.astype(float))
    s = w.sum()
    return w / s if s > 0 else np.full(P_oof.shape[1], 1.0 / P_oof.shape[1])


def run_ensemble(merged, label, kind, fc_names, feature_sets, blend_type):
    """4-fold WF; per fold, train each fc's B6 OOF-stack, then blend per blend_type.
    blend_type in {'nnls', 'avg'}.
    """
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    weights_per_fold = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        preds = []; oofs = []
        for fn in fc_names:
            fc = feature_sets[fn]
            test_pred, oof_l2 = _oof_stack_pred(merged, fc, label, kind, tr, ti)
            preds.append(test_pred); oofs.append(oof_l2)
        P = np.column_stack(preds); O = np.column_stack(oofs)
        y_tr = y_all[tr]
        if blend_type == "nnls":
            w = _nnls_weights(O, y_tr)
        else:
            w = np.full(P.shape[1], 1.0 / P.shape[1])
        y_pred = P @ w
        weights_per_fold.append(w.tolist())
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred})
    return folds, weights_per_fold


def _summarize_reg(folds, name, label):
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    pl = float(np.mean(np.abs(al - aa)))
    naive = pd.Series(aa).shift(1).rolling(5, min_periods=1).mean().fillna(aa.mean()).values
    pn = float(np.mean(np.abs(naive - aa)))
    dp = (pl - pn) / pn * 100.0
    fold_results = [{"fold": f["fold"],
                     "fold_mae": round(float(np.mean(np.abs(f["y_pred"] - f["y_true"]))), 4)}
                    for f in folds]
    can = B15_FROZEN.get(label, {})
    frozen_dp = can.get("pooled_delta_pct")
    return {"probe": name, "kind": "regression", "label": label,
            "live_pooled_mae": round(pl, 4),
            "live_pooled_naive_mae": round(pn, 4),
            "live_pooled_delta_pct": round(dp, 2),
            "frozen_delta_pct": frozen_dp,
            "drift_pp": round(dp - frozen_dp, 2) if frozen_dp else None,
            "n_folds": len(folds),
            "fold_results": fold_results,
            "frozen_src": can.get("src")}


def _summarize_bin(folds, name, label, desc, n_games, pos_rate):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    plb = float(brier_score_loss(aa, al))
    try:
        plu = float(roc_auc_score(aa, al))
    except Exception:
        plu = float("nan")
    can = B15_FROZEN.get(label, {})
    frozen_brier = can.get("pooled_brier"); frozen_auc = can.get("pooled_auc")
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "n_games": int(n_games), "pos_rate": float(pos_rate),
            "live_pooled_brier": round(plb, 5),
            "live_pooled_auc": round(plu, 5),
            "frozen_brier": frozen_brier, "frozen_auc": frozen_auc,
            "drift_brier": round(plb - frozen_brier, 5) if frozen_brier else None,
            "drift_auc": round(plu - frozen_auc, 5) if frozen_auc else None,
            "n_folds": len(folds),
            "frozen_src": can.get("src")}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-25 - honest re-baseline of B15 ensembles (away_score + AH3)", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games (B15 saw 2839)", flush=True)
    merged = build_r12_features(merged)
    feature_sets = _all_feature_sets(merged)
    print(f"[2] R12 features built", flush=True)
    for fc in feature_sets.values():
        merged[fc] = merged[fc].fillna(0.0)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    # B15 nnls_top3 for away_score: halflife2_only + all_b9 + interactions_only
    print(f"\n[away_score / nnls_top3] running ...", flush=True)
    t_a = time.time()
    folds_a, weights_a = run_ensemble(merged, "away_score", "reg",
        ["halflife2_only", "all_b9", "interactions_only"], feature_sets, "nnls")
    out_a = _summarize_reg(folds_a, "R12_B25_nnls_top3_away_score", "away_score")
    out_a["elapsed_s"] = round(time.time() - t_a, 1)
    out_a["weights_per_fold"] = weights_a
    out_a["fc_names"] = ["halflife2_only", "all_b9", "interactions_only"]
    print(f"  LIVE delta {out_a['live_pooled_delta_pct']:+.2f}% "
          f"(frozen {out_a['frozen_delta_pct']:+.2f}%, drift {out_a['drift_pp']:+.2f}pp) "
          f"[{out_a['elapsed_s']}s]", flush=True)
    print(f"  weights per fold: {[[round(x, 3) for x in w] for w in weights_a]}", flush=True)
    with open(os.path.join(DATA_CACHE, "probe_R12_B25_nnls_top3_away_score_results.json"), "w") as f:
        json.dump(out_a, f, indent=2)

    # B15 top4_avg for AH3: intersection + opp_pts_pace + opp_full + all_b9
    print(f"\n[home_cover_AH3 / top4_avg] running ...", flush=True)
    t_b = time.time()
    folds_b, weights_b = run_ensemble(merged, "home_cover_AH3", "bin",
        ["intersection", "opp_pts_pace", "opp_full", "all_b9"], feature_sets, "avg")
    out_b = _summarize_bin(folds_b, "R12_B25_top4_avg_AH3", "home_cover_AH3",
                            "P(home covers -3)", len(merged),
                            float(merged["home_cover_AH3"].mean()))
    out_b["elapsed_s"] = round(time.time() - t_b, 1)
    out_b["fc_names"] = ["intersection", "opp_pts_pace", "opp_full", "all_b9"]
    print(f"  LIVE Brier {out_b['live_pooled_brier']:.4f} "
          f"(frozen {out_b['frozen_brier']:.4f}, drift {out_b['drift_brier']:+.5f})", flush=True)
    print(f"  LIVE AUC {out_b['live_pooled_auc']:.4f} "
          f"(frozen {out_b['frozen_auc']:.4f}, drift {out_b['drift_auc']:+.5f}) "
          f"[{out_b['elapsed_s']}s]", flush=True)
    with open(os.path.join(DATA_CACHE, "probe_R12_B25_top4_avg_AH3_results.json"), "w") as f:
        json.dump(out_b, f, indent=2)

    print(f"\n[done] re-baseline complete in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
