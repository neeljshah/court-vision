"""probe_R12_batch23_perm_inner_cv_sweep.py — extend perm_inner_cv to remaining targets.

After B22 showed perm_inner_cv is the best honest trim strategy (won score_diff
-1.59pp), sweep it across the rest:
  - away_score (regression, never honestly baselined since B15 frozen)
  - over_230 (binary)
  - home_cover_AH3 (binary)
  - home_score (regression, missed by +0.06pp in B22 — retest)

Records beat_live vs B21 LIVE (regression) or B15 frozen (binary, no LIVE baseline yet).
"""
from __future__ import annotations
import importlib.util, json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.r12_canonical_predictor import (  # noqa: E402
    build_r12_features, _all_feature_sets,
)

# Import trim_perm_inner_cv from B22
_B22_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "probe_R12_batch22_stable_feat_select.py")
_spec22 = importlib.util.spec_from_file_location("probe_R12_batch22_stable_feat_select", _B22_PATH)
_b22 = importlib.util.module_from_spec(_spec22); _spec22.loader.exec_module(_b22)
trim_perm_inner_cv = _b22.trim_perm_inner_cv

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_b5)
load_data = _b5.load_data


# Baselines: B21 LIVE for regression, B15 frozen for binary (no LIVE yet)
BASELINE = {
    "home_score":     {"pooled_delta_pct": -14.49, "src": "B21 LIVE (regression)"},
    "away_score":     {"pooled_delta_pct": -14.51, "src": "B15 frozen (no LIVE)"},
    "over_230":       {"pooled_brier": 0.2418, "pooled_auc": 0.6722,
                       "src": "B21 LIVE (binary)"},
    "home_cover_AH3": {"pooled_brier": 0.2271, "pooled_auc": 0.7115,
                       "src": "B15 frozen ensemble (no LIVE)"},
}

CANON_FC = {
    "home_score":     "all_b9",
    "away_score":     "halflife2_only",
    "over_230":       "opp_full",
    "home_cover_AH3": "intersection",
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
        return 0.5 * l2_l.predict(X_te_aug) + 0.5 * l2_x.predict(X_te_aug)
    else:
        l2_l = _lgb_clf(); l2_l.fit(X_tr_aug, y_tr)
        l2_x = _xgb_clf(); l2_x.fit(X_tr_aug, y_tr)
        return 0.5 * l2_l.predict_proba(X_te_aug)[:, 1] + \
               0.5 * l2_x.predict_proba(X_te_aug)[:, 1]


def trim_perm_inner_cv_clf(df_tr, fc, target, top_k=50, inner_k=3, n_repeats=5):
    """Classifier variant of perm_inner_cv using neg_brier_score."""
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
        y = df_tr[target].astype(int).values
        m = _lgb_clf(); m.fit(X_tr, y[tr])
        r = permutation_importance(m, X_te, y[te], n_repeats=n_repeats,
                                    random_state=42, n_jobs=1,
                                    scoring="neg_brier_score")
        for i, c in enumerate(fc):
            importances_acc[c] += float(r.importances_mean[i])
        n_acc += 1
    if n_acc > 0:
        for c in importances_acc:
            importances_acc[c] /= n_acc
    ranked = sorted(fc, key=lambda c: importances_acc.get(c, 0.0), reverse=True)
    return ranked[:top_k]


def _summarize_reg(folds, name, label):
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
    can = BASELINE.get(label, {})
    beat = (dp < can.get("pooled_delta_pct", 0.0))
    return {"probe": name, "kind": "regression", "label": label,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {np_}/{nv}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(pn, 4), "pooled_lgb_mae": round(pl, 4),
            "pooled_delta_pct": round(dp, 2),
            "n_folds_positive": np_, "n_valid_folds": nv,
            "fold_results": fold_results,
            "beat_live": bool(beat),
            "baseline_src": can.get("src"),
            "vs_baseline_pp": round(dp - can.get("pooled_delta_pct", 0.0), 2)}


def _summarize_bin(folds, name, label, desc, n_games, pos_rate):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    an = np.concatenate([f["y_naive"] for f in folds])
    pnb = float(brier_score_loss(aa, an))
    plb = float(brier_score_loss(aa, al))
    try:
        plu = float(roc_auc_score(aa, al))
    except Exception:
        plu = float("nan")
    bdp = (plb - pnb) / pnb * 100.0
    nv_ = len(folds)
    ship = ((plb <= pnb * 0.95) or (plu >= 0.60)) and nv_ >= 3
    can = BASELINE.get(label, {})
    beat = (plb < can.get("pooled_brier", 1.0)) or (plu > can.get("pooled_auc", 0.0))
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "n_games": int(n_games), "pos_rate": float(pos_rate),
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {plb:.4f} ({bdp:+.2f}%); AUC {plu:.4f}",
            "pooled_lgb_brier": round(plb, 5), "pooled_naive_brier": round(pnb, 5),
            "pooled_lgb_auc": round(plu, 5), "brier_delta_pct": round(bdp, 3),
            "n_valid_folds": nv_,
            "beat_live": bool(beat),
            "baseline_src": can.get("src"),
            "baseline_brier": can.get("pooled_brier"),
            "baseline_auc": can.get("pooled_auc")}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-23 — perm_inner_cv sweep on remaining targets", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = build_r12_features(merged)
    feature_sets = _all_feature_sets(merged)
    print(f"[2] feature sets built", flush=True)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    targets = [
        ("reg", "home_score", None),
        ("reg", "away_score", None),
        ("bin", "over_230", "P(total > 230)"),
        ("bin", "home_cover_AH3", "P(home covers -3)"),
    ]

    results = {}; n_beat = 0; n_total = 0
    for kind, label, desc in targets:
        fc_name = CANON_FC[label]
        naive = naive_l5_mean(label) if kind == "reg" else naive_l5_prop(label)
        t_v = time.time()
        name = f"R12_B23_perm_inner_cv_{label}"
        print(f"\n[{label}] kind={kind} fc={fc_name} — per-fold perm_inner_cv trim ...", flush=True)
        n = len(merged)
        y_all = merged[label].astype(int if kind == "bin" else float).values
        folds = []
        for fi, tr, ti in _wf_indices(n, 4):
            if len(tr) < 250 or len(ti) < 20:
                continue
            df_tr = merged.iloc[tr].reset_index(drop=True)
            fc_full = feature_sets[fc_name]
            df_tr[fc_full] = df_tr[fc_full].fillna(0.0)
            if kind == "reg":
                fc_trim = trim_perm_inner_cv(df_tr, fc_full, label, top_k=50)
            else:
                fc_trim = trim_perm_inner_cv_clf(df_tr, fc_full, label, top_k=50)
            y_pred = _oof_stack_pred(merged, fc_trim, label, kind, tr, ti)
            folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                          "y_naive": naive[ti], "fc_len": len(fc_trim)})
        if kind == "reg":
            out = _summarize_reg(folds, name, label)
        else:
            out = _summarize_bin(folds, name, label, desc, len(merged),
                                  float(np.mean(y_all)))
        out["elapsed_s"] = round(time.time() - t_v, 1)
        out["fc_len_per_fold"] = [f["fc_len"] for f in folds]
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]; n_total += 1
        beat_str = ""
        if out.get("beat_live") is True:
            n_beat += 1; beat_str = " BEAT_LIVE"
        elif out.get("beat_live") is False:
            beat_str = f" (canon {out.get('baseline_src','?')[:25]} wins)"
        if out["kind"] == "regression":
            print(f"  {name}: {out['status']} delta {out['pooled_delta_pct']:+.2f}% "
                  f"vs_canon={out.get('vs_baseline_pp', 0):+.2f}pp{beat_str} [{out['elapsed_s']}s]",
                  flush=True)
        else:
            print(f"  {name}: {out['status']} Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f}{beat_str} [{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS, {n_beat}/{n_total} BEAT_LIVE in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
