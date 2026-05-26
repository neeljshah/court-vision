"""probe_R12_batch7_stacked_meta.py — cross-target OOF stacking + NNLS blend.

Base = 136-feature R12 B5 best + B6 OOF-stack architecture.

Variants per target:
  - cross_oof_stack : outer 4-fold WF; for each outer fold, generate B6-style
    OOF preds for ALL 6 targets on outer-train via 5-fold inner CV.
    Augment base features with all 6 OOF preds (incl. target's own OOF).
    Level-2 LGB+XGB on (base + 6 cross-target OOF features).
    Does knowing "what total_pts OOF thinks" help "home_score predict"?
  - blend_nnls : on outer-train, compute B5-style preds (single LGB+XGB) AND
    B6-style preds (OOF-stack). Use NNLS to fit blend weights against y_tr,
    apply to test set. Does architecture-blending beat either alone?

Targets: total_pts_box, score_diff, home_score, away_score (reg);
         over_230, home_cover_AH3 (bin).
"""
from __future__ import annotations
import importlib.util, json, os, time, sys
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

# Import B5 feature engineering
_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_b5)
load_data = _b5.load_data
add_b3_features = _b5.add_b3_features
add_recency_features = _b5.add_recency_features
add_quality_features = _b5.add_quality_features
FEAT_COLS_BASE = _b5.FEAT_COLS_BASE

# Import B6 feature column builder
_B6_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch6_bagging_variance.py")
_spec6 = importlib.util.spec_from_file_location("probe_R12_batch6_bagging_variance", _B6_PATH)
_b6 = importlib.util.module_from_spec(_spec6)
_spec6.loader.exec_module(_b6)
_build_b5_feature_columns = _b6._build_b5_feature_columns


# ---------- model builders (mirror B6) ----------
def _lgb_reg(seed=42):
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=seed, n_jobs=2, verbose=-1)


def _lgb_clf(seed=42):
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=seed, n_jobs=2, verbose=-1)


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


# ---------- helpers ----------
def _wf_indices(n, k):
    fs = n // k
    out = []
    for fi in range(k):
        ts = fi * fs
        te = (fi + 1) * fs if fi < k - 1 else n
        out.append((fi, list(range(0, ts)), list(range(ts, te))))
    return out


def _gen_oof_and_test_l1(X_tr, y_tr, X_te, kind, inner_k=5):
    """5-fold inner OOF on training set; full-train fit for test predictions.
    Returns (oof_preds_train, l1_preds_test)."""
    n_tr = len(y_tr)
    oof = np.zeros(n_tr, dtype=float)
    inner_fs = n_tr // inner_k
    for ki in range(inner_k):
        its = ki * inner_fs
        ite = (ki + 1) * inner_fs if ki < inner_k - 1 else n_tr
        itr = list(range(0, its)) + list(range(ite, n_tr))
        iti = list(range(its, ite))
        if len(itr) < 50 or len(iti) < 5:
            continue
        if kind == "reg":
            m = _lgb_reg()
            m.fit(X_tr[itr], y_tr[itr])
            oof[iti] = m.predict(X_tr[iti])
        else:
            m = _lgb_clf()
            m.fit(X_tr[itr], y_tr[itr])
            oof[iti] = m.predict_proba(X_tr[iti])[:, 1]
    # Full retrain for test predictions
    if kind == "reg":
        mf = _lgb_reg(); mf.fit(X_tr, y_tr)
        l1_test = mf.predict(X_te)
    else:
        mf = _lgb_clf(); mf.fit(X_tr, y_tr)
        l1_test = mf.predict_proba(X_te)[:, 1]
    return oof, l1_test


def _gen_b5_pred(X_tr, y_tr, X_te, kind):
    """B5-style single LGB+XGB 50/50 ensemble."""
    if kind == "reg":
        l = _lgb_reg(); l.fit(X_tr, y_tr)
        x = _xgb_reg(); x.fit(X_tr, y_tr)
        return 0.5 * l.predict(X_te) + 0.5 * x.predict(X_te)
    else:
        l = _lgb_clf(); l.fit(X_tr, y_tr)
        x = _xgb_clf(); x.fit(X_tr, y_tr)
        return 0.5 * l.predict_proba(X_te)[:, 1] + 0.5 * x.predict_proba(X_te)[:, 1]


def _level2_predict(X_tr_aug, y_tr, X_te_aug, kind):
    if kind == "reg":
        l = _lgb_reg(); l.fit(X_tr_aug, y_tr)
        x = _xgb_reg(); x.fit(X_tr_aug, y_tr)
        return 0.5 * l.predict(X_te_aug) + 0.5 * x.predict(X_te_aug)
    else:
        l = _lgb_clf(); l.fit(X_tr_aug, y_tr)
        x = _xgb_clf(); x.fit(X_tr_aug, y_tr)
        return 0.5 * l.predict_proba(X_te_aug)[:, 1] + 0.5 * x.predict_proba(X_te_aug)[:, 1]


def _summarize_reg(folds, name, label, n_features, variant_meta):
    if not folds:
        return {"probe": name, "kind": "regression", "label": label, "status": "REJECT",
                "ship_reason": "no valid folds", "n_features": n_features,
                "variant": variant_meta}
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
    fold_deltas = [f["delta_pct"] for f in fold_results]
    return {"probe": name, "kind": "regression", "label": label,
            "n_features": n_features,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {np_}/{nv}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(pn, 4), "pooled_lgb_mae": round(pl, 4),
            "pooled_delta_pct": round(dp, 2),
            "n_folds_positive": np_, "n_valid_folds": nv,
            "fold_results": fold_results,
            "fold_delta_pct_std": round(float(np.std(fold_deltas)), 3),
            "variant": variant_meta}


def _summarize_bin(folds, name, label, desc, n_features, n_games, pos_rate, variant_meta):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    if not folds:
        return {"probe": name, "kind": "binary", "label": label, "status": "REJECT",
                "ship_reason": "no valid folds", "n_features": n_features,
                "variant": variant_meta}
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
    fold_results = []
    for f in folds:
        fold_results.append({"fold": f["fold"],
                             "naive_brier": round(float(brier_score_loss(f["y_true"], f["y_naive"])), 5),
                             "lgb_brier": round(float(brier_score_loss(f["y_true"], f["y_pred"])), 5)})
    nv_ = len(folds)
    ship = ((plb <= pnb * 0.95) or (plu >= 0.60)) and nv_ >= 3
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "n_features": n_features, "n_games": int(n_games), "pos_rate": float(pos_rate),
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {plb:.4f} ({bdp:+.2f}%); AUC {plu:.4f}",
            "pooled_lgb_brier": round(plb, 5), "pooled_naive_brier": round(pnb, 5),
            "pooled_lgb_auc": round(plu, 5), "brier_delta_pct": round(bdp, 3),
            "n_valid_folds": nv_, "fold_results": fold_results,
            "variant": variant_meta}


# ---------- main probe ----------
def run_cross_oof_stack(merged, target_specs, fc, naive_preds, primary_target_idx):
    """For one outer fold loop, run cross-target OOF stacking for ALL targets.
    Returns dict mapping target name → list of fold-dicts (y_true, y_pred, y_naive).

    Implementation: for each outer fold, generate OOF + L1 preds for all 6 targets,
    then for each target train level-2 model on (base + all 6 OOF/L1 cross-features).
    """
    n = len(merged)
    fc_arr = merged[fc].values
    # Per-target fold results
    fold_outputs = {ts["name"]: [] for ts in target_specs}
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        X_tr = fc_arr[tr]
        X_te = fc_arr[ti]
        # Stage 1: generate OOF (train) + L1 (test) for ALL 6 targets
        all_oof = {}   # target_name → (oof_train, l1_test)
        for ts in target_specs:
            label = ts["label"]; kind = ts["kind"]
            y_full = merged[label].astype(int if kind == "bin" else float).values
            y_tr_t = y_full[tr]
            oof_t, l1_te_t = _gen_oof_and_test_l1(X_tr, y_tr_t, X_te, kind)
            all_oof[ts["name"]] = (oof_t, l1_te_t)
        # Build cross-target feature matrices (consistent column order)
        target_names = [ts["name"] for ts in target_specs]
        oof_train_mat = np.column_stack([all_oof[tn][0] for tn in target_names])
        l1_test_mat = np.column_stack([all_oof[tn][1] for tn in target_names])
        X_tr_aug = np.hstack([X_tr, oof_train_mat])
        X_te_aug = np.hstack([X_te, l1_test_mat])
        # Stage 2: per-target level-2 model on augmented features
        for ts in target_specs:
            label = ts["label"]; kind = ts["kind"]
            y_full = merged[label].astype(int if kind == "bin" else float).values
            y_tr_t = y_full[tr]
            y_te_t = y_full[ti]
            y_pred = _level2_predict(X_tr_aug, y_tr_t, X_te_aug, kind)
            fold_outputs[ts["name"]].append({
                "fold": fi, "y_true": y_te_t, "y_pred": y_pred,
                "y_naive": naive_preds[ts["name"]][ti]
            })
    return fold_outputs


def run_blend_nnls(merged, label, naive_pred, fc, name, kind, desc=None):
    """4-fold WF outer. On outer-train: generate B5-style preds (via inner 5-fold)
    + B6-style OOF-stack preds (via inner 5-fold). Fit NNLS to find weights against
    y_tr (using OOF preds as the training signal — out-of-fold for both). Apply
    learned weights to test set."""
    from scipy.optimize import nnls
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    fc_arr = merged[fc].values
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        X_tr = fc_arr[tr]
        X_te = fc_arr[ti]
        y_tr = y_all[tr]
        n_tr = len(tr)
        # Generate B5 OOF preds + B6 OOF-stack OOF preds on outer-train
        inner_k = 5
        inner_fs = n_tr // inner_k
        oof_b5 = np.zeros(n_tr)
        oof_b6 = np.zeros(n_tr)
        # B6 OOF-stack OOF: requires nested inner-inner OOF.
        # Simplified: B6 level-2 here uses pure level-1 OOF as augmentation, then trains on
        # (base + l1_oof) with hold-out validation.
        for ki in range(inner_k):
            its = ki * inner_fs
            ite = (ki + 1) * inner_fs if ki < inner_k - 1 else n_tr
            itr = list(range(0, its)) + list(range(ite, n_tr))
            iti = list(range(its, ite))
            if len(itr) < 50 or len(iti) < 5:
                continue
            # B5 inner pred
            oof_b5[iti] = _gen_b5_pred(X_tr[itr], y_tr[itr], X_tr[iti], kind)
            # B6 inner pred: need level-1 OOF on itr, then level-2 prediction on iti
            # Approximate: do 3-fold inner-inner OOF on itr for level-1, then level-2 fit on
            # (X_tr[itr] + l1_oof) and predict on (X_tr[iti] + l1_iti)
            n_itr = len(itr); inner2_k = 3; iif = n_itr // inner2_k
            l1_oof_itr = np.zeros(n_itr)
            X_itr = X_tr[itr]; y_itr = y_tr[itr]
            X_iti = X_tr[iti]
            for kk in range(inner2_k):
                a = kk * iif
                b = (kk + 1) * iif if kk < inner2_k - 1 else n_itr
                tr_ii = list(range(0, a)) + list(range(b, n_itr))
                te_ii = list(range(a, b))
                if len(tr_ii) < 30 or len(te_ii) < 5:
                    continue
                if kind == "reg":
                    m = _lgb_reg(); m.fit(X_itr[tr_ii], y_itr[tr_ii])
                    l1_oof_itr[te_ii] = m.predict(X_itr[te_ii])
                else:
                    m = _lgb_clf(); m.fit(X_itr[tr_ii], y_itr[tr_ii])
                    l1_oof_itr[te_ii] = m.predict_proba(X_itr[te_ii])[:, 1]
            # full retrain for iti L1 prediction
            if kind == "reg":
                mf = _lgb_reg(); mf.fit(X_itr, y_itr)
                l1_iti = mf.predict(X_iti)
            else:
                mf = _lgb_clf(); mf.fit(X_itr, y_itr)
                l1_iti = mf.predict_proba(X_iti)[:, 1]
            # level-2 fit on augmented itr → predict iti
            X_itr_aug = np.hstack([X_itr, l1_oof_itr.reshape(-1, 1)])
            X_iti_aug = np.hstack([X_iti, l1_iti.reshape(-1, 1)])
            oof_b6[iti] = _level2_predict(X_itr_aug, y_itr, X_iti_aug, kind)
        # Fit NNLS on (oof_b5, oof_b6) vs y_tr
        A = np.column_stack([oof_b5, oof_b6])
        # For binary, y is 0/1; NNLS still works (linear regression form).
        w, _ = nnls(A, y_tr.astype(float))
        # Renormalize if both are positive
        wsum = w.sum()
        if wsum > 0:
            w = w / wsum
        else:
            w = np.array([0.5, 0.5])
        # Apply learned weights to test set
        # Need full B5 + B6 preds on test set, trained on full outer-train
        b5_te = _gen_b5_pred(X_tr, y_tr, X_te, kind)
        # B6 on full outer-train: inner OOF + level-2 on aug
        oof_b6_full, l1_test_b6 = _gen_oof_and_test_l1(X_tr, y_tr, X_te, kind)
        X_tr_aug = np.hstack([X_tr, oof_b6_full.reshape(-1, 1)])
        X_te_aug = np.hstack([X_te, l1_test_b6.reshape(-1, 1)])
        b6_te = _level2_predict(X_tr_aug, y_tr, X_te_aug, kind)
        y_pred = w[0] * b5_te + w[1] * b6_te
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti], "nnls_w_b5": round(float(w[0]), 4),
                      "nnls_w_b6": round(float(w[1]), 4)})
    meta = {"variant": "blend_nnls", "weights_per_fold":
            [(f.get("nnls_w_b5"), f.get("nnls_w_b6")) for f in folds]}
    if kind == "reg":
        return _summarize_reg(folds, name, label, len(fc), meta)
    else:
        return _summarize_bin(folds, name, label, desc, len(fc), n,
                              float(np.mean(y_all)), meta)


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-7 — cross-target OOF stacking + NNLS blend", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = add_b3_features(merged)
    merged = add_recency_features(merged)
    merged = add_quality_features(merged)
    fc = _build_b5_feature_columns(merged)
    merged[fc] = merged[fc].fillna(0.0)
    print(f"[2] feature columns: {len(fc)}", flush=True)

    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    target_specs = [
        {"name": "total_pts_box", "label": "total_pts_box", "kind": "reg", "desc": None},
        {"name": "score_diff", "label": "score_diff", "kind": "reg", "desc": None},
        {"name": "home_score", "label": "home_score", "kind": "reg", "desc": None},
        {"name": "away_score", "label": "away_score", "kind": "reg", "desc": None},
        {"name": "over_230", "label": "over_230", "kind": "bin", "desc": "P(total > 230)"},
        {"name": "home_cover_AH3", "label": "home_cover_AH3", "kind": "bin",
         "desc": "P(home covers -3)"},
    ]
    naive_preds = {}
    for ts in target_specs:
        if ts["kind"] == "reg":
            naive_preds[ts["name"]] = naive_l5_mean(ts["label"])
        else:
            naive_preds[ts["name"]] = naive_l5_prop(ts["label"])

    # --- Variant 1: cross-target OOF stacking (one big run, results per target) ---
    print("[3] cross_oof_stack — running shared OOF generation across all 6 targets ...",
          flush=True)
    t_v = time.time()
    fold_outputs = run_cross_oof_stack(merged, target_specs, fc, naive_preds, 0)
    print(f"    cross_oof_stack done in {time.time()-t_v:.1f}s", flush=True)
    results = {}
    for ts in target_specs:
        folds = fold_outputs.get(ts["name"], [])
        name = f"R12_B7_cross_oof_stack_{ts['label']}"
        n_features = len(fc) + len(target_specs)  # +6 cross-target OOF features
        meta = {"variant": "cross_oof_stack", "n_extra_oof_features": len(target_specs),
                "outer_k": 4, "inner_k": 5}
        if ts["kind"] == "reg":
            out = _summarize_reg(folds, name, ts["label"], n_features, meta)
        else:
            y_all = merged[ts["label"]].astype(int).values
            out = _summarize_bin(folds, name, ts["label"], ts["desc"], n_features,
                                  len(merged), float(np.mean(y_all)), meta)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        if out["kind"] == "regression":
            print(f"  {name}: {out['status']} feats={out['n_features']} "
                  f"delta {out['pooled_delta_pct']:+.2f}% "
                  f"({out['n_folds_positive']}/{out['n_valid_folds']}) "
                  f"fold_std={out.get('fold_delta_pct_std', 0):.2f}pp", flush=True)
        else:
            print(f"  {name}: {out['status']} feats={out['n_features']} "
                  f"Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f} "
                  f"({out['brier_delta_pct']:+.2f}%)", flush=True)

    # --- Variant 2: blend_nnls per target ---
    print("[4] blend_nnls — per-target B5+B6 NNLS architecture blending ...", flush=True)
    for ts in target_specs:
        t_v = time.time()
        name = f"R12_B7_blend_nnls_{ts['label']}"
        out = run_blend_nnls(merged, ts["label"], naive_preds[ts["name"]], fc,
                              name, ts["kind"], ts["desc"])
        out["elapsed_s"] = round(time.time() - t_v, 1)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]
        if out["kind"] == "regression":
            print(f"  {name}: {out['status']} feats={out['n_features']} "
                  f"delta {out['pooled_delta_pct']:+.2f}% "
                  f"({out['n_folds_positive']}/{out['n_valid_folds']}) "
                  f"[{out['elapsed_s']}s]", flush=True)
        else:
            print(f"  {name}: {out['status']} feats={out['n_features']} "
                  f"Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f} "
                  f"({out['brier_delta_pct']:+.2f}%) [{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
