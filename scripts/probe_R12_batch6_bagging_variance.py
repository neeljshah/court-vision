"""probe_R12_batch6_bagging_variance.py — bagging variance + OOF stacking + 5-fold WF.

Base = 136-feature R12 B5 best (B3 + Z + B4 + B5 features).

Variants per target:
  - bag5_lgb    : 5-bag LGB (5 seeds + bootstrap) mean blended 50/50 with XGB; bag_std diagnostic.
  - oof_stack   : outer 4-fold WF; inner 5-fold OOF generates level-1 LGB preds; level-2 LGB+XGB on base + oof_pred.
  - fivefold_wf : 5-fold WF (same single-LGB+XGB template as B5) — variance comparison vs 4-fold.

Targets: total_pts_box, score_diff, home_score, away_score (reg) + over_230, home_cover_AH3 (bin).

Ship gates: reg pooled_delta_pct <= -5% AND folds_positive == n_valid_folds (>=3 valid);
            bin Brier <= naive*0.95 OR AUC >= 0.60.
"""
from __future__ import annotations
import importlib.util, json, os, time, sys, math
from collections import defaultdict
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

# Load B5 feature-engineering functions by importing the script as a module
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


# ---------- model builders ----------
def _lgb_reg(seed, subsample=0.8, colsample=0.8):
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=subsample, colsample_bytree=colsample, reg_alpha=0.1, reg_lambda=0.1,
        min_child_samples=20, random_state=seed, n_jobs=2, verbose=-1)


def _lgb_clf(seed, subsample=0.8, colsample=0.8):
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
        subsample=subsample, colsample_bytree=colsample, reg_alpha=0.1, reg_lambda=0.1,
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


# Bagged LGB: 5 different seeds, deterministic bootstrap via subsample/colsample/seed
_BAG_SEEDS = [42, 1337, 2024, 7, 91]


def _bag_predict_reg(X_tr, y_tr, X_te):
    """Train 5 LGB regressors with varied seeds; return mean + std vector for X_te."""
    preds = []
    for s in _BAG_SEEDS:
        m = _lgb_reg(seed=s, subsample=0.75, colsample=0.85)
        m.fit(X_tr, y_tr)
        preds.append(m.predict(X_te))
    P = np.vstack(preds)
    return P.mean(axis=0), P.std(axis=0)


def _bag_predict_clf(X_tr, y_tr, X_te):
    """Train 5 LGB classifiers; return mean prob + std vector."""
    probs = []
    for s in _BAG_SEEDS:
        m = _lgb_clf(seed=s, subsample=0.75, colsample=0.85)
        m.fit(X_tr, y_tr)
        probs.append(m.predict_proba(X_te)[:, 1])
    P = np.vstack(probs)
    return P.mean(axis=0), P.std(axis=0)


# ---------- variant runners ----------
def _wf_indices(n, k):
    fs = n // k
    out = []
    for fi in range(k):
        ts = fi * fs
        te = (fi + 1) * fs if fi < k - 1 else n
        tr = list(range(0, ts))
        ti = list(range(ts, te))
        out.append((fi, tr, ti))
    return out


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
    # Per-fold std for variance signal
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


def run_variant_bag5(merged, label, naive_pred, fc, name, kind, desc=None):
    """4-fold WF, replace LGB with 5-bag LGB mean blended 50/50 with single XGB."""
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    bag_stds_pooled = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 50 or len(ti) < 20:
            continue
        X_tr = merged[fc].iloc[tr].values
        X_te = merged[fc].iloc[ti].values
        y_tr = y_all[tr]
        if kind == "reg":
            bag_mean, bag_std = _bag_predict_reg(X_tr, y_tr, X_te)
            xgbr = _xgb_reg(); xgbr.fit(X_tr, y_tr)
            xpred = xgbr.predict(X_te)
            y_pred = 0.5 * bag_mean + 0.5 * xpred
        else:
            bag_mean, bag_std = _bag_predict_clf(X_tr, y_tr, X_te)
            xgbc = _xgb_clf(); xgbc.fit(X_tr, y_tr)
            xpred = xgbc.predict_proba(X_te)[:, 1]
            y_pred = 0.5 * bag_mean + 0.5 * xpred
        bag_stds_pooled.append(float(np.mean(bag_std)))
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti]})
    meta = {"variant": "bag5_lgb", "n_bag": len(_BAG_SEEDS),
            "mean_bag_std_per_fold": [round(s, 4) for s in bag_stds_pooled]}
    if kind == "reg":
        return _summarize_reg(folds, name, label, len(fc), meta)
    else:
        return _summarize_bin(folds, name, label, desc, len(fc), n,
                              float(np.mean(y_all)), meta)


def run_variant_oof_stack(merged, label, naive_pred, fc, name, kind, desc=None):
    """Outer 4-fold WF. Within each outer training set, do 5-fold inner OOF
    using LGB to produce out-of-fold predictions; level-2 model = LGB+XGB 50/50
    on (base_features + oof_pred). For test set, level-1 retrained on full
    outer-train and predicted, then level-2 predicts."""
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue  # need enough rows for 5-fold inner
        X_tr_base = merged[fc].iloc[tr].values
        X_te_base = merged[fc].iloc[ti].values
        y_tr = y_all[tr]
        n_tr = len(tr)
        oof = np.zeros(n_tr, dtype=float)
        inner_k = 5
        inner_fs = n_tr // inner_k
        for ki in range(inner_k):
            its = ki * inner_fs
            ite = (ki + 1) * inner_fs if ki < inner_k - 1 else n_tr
            itr = list(range(0, its)) + list(range(ite, n_tr))
            iti = list(range(its, ite))
            if len(itr) < 50 or len(iti) < 10:
                continue
            if kind == "reg":
                m = _lgb_reg(seed=42)
                m.fit(X_tr_base[itr], y_tr[itr])
                oof[iti] = m.predict(X_tr_base[iti])
            else:
                m = _lgb_clf(seed=42)
                m.fit(X_tr_base[itr], y_tr[itr])
                oof[iti] = m.predict_proba(X_tr_base[iti])[:, 1]
        # Level-1 retrain on full outer-train for test predictions
        if kind == "reg":
            m_full = _lgb_reg(seed=42)
            m_full.fit(X_tr_base, y_tr)
            test_l1 = m_full.predict(X_te_base)
        else:
            m_full = _lgb_clf(seed=42)
            m_full.fit(X_tr_base, y_tr)
            test_l1 = m_full.predict_proba(X_te_base)[:, 1]
        # Augment with l1 oof feature
        X_tr_aug = np.hstack([X_tr_base, oof.reshape(-1, 1)])
        X_te_aug = np.hstack([X_te_base, test_l1.reshape(-1, 1)])
        if kind == "reg":
            l2_lgb = _lgb_reg(seed=42); l2_lgb.fit(X_tr_aug, y_tr)
            l2_xgb = _xgb_reg();      l2_xgb.fit(X_tr_aug, y_tr)
            y_pred = 0.5 * l2_lgb.predict(X_te_aug) + 0.5 * l2_xgb.predict(X_te_aug)
        else:
            l2_lgb = _lgb_clf(seed=42); l2_lgb.fit(X_tr_aug, y_tr)
            l2_xgb = _xgb_clf();      l2_xgb.fit(X_tr_aug, y_tr)
            y_pred = 0.5 * l2_lgb.predict_proba(X_te_aug)[:, 1] + \
                     0.5 * l2_xgb.predict_proba(X_te_aug)[:, 1]
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti]})
    meta = {"variant": "oof_stack", "inner_k": 5, "outer_k": 4,
            "level2_n_features": len(fc) + 1}
    if kind == "reg":
        return _summarize_reg(folds, name, label, len(fc) + 1, meta)
    else:
        return _summarize_bin(folds, name, label, desc, len(fc) + 1, n,
                              float(np.mean(y_all)), meta)


def run_variant_fivefold(merged, label, naive_pred, fc, name, kind, desc=None):
    """5-fold WF with the SAME single-LGB+XGB 50/50 template as B5 — variance check."""
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    for fi, tr, ti in _wf_indices(n, 5):
        if len(tr) < 50 or len(ti) < 20:
            continue
        X_tr = merged[fc].iloc[tr].values
        X_te = merged[fc].iloc[ti].values
        y_tr = y_all[tr]
        if kind == "reg":
            l = _lgb_reg(seed=42); l.fit(X_tr, y_tr)
            x = _xgb_reg();        x.fit(X_tr, y_tr)
            y_pred = 0.5 * l.predict(X_te) + 0.5 * x.predict(X_te)
        else:
            l = _lgb_clf(seed=42); l.fit(X_tr, y_tr)
            x = _xgb_clf();        x.fit(X_tr, y_tr)
            y_pred = 0.5 * l.predict_proba(X_te)[:, 1] + 0.5 * x.predict_proba(X_te)[:, 1]
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti]})
    meta = {"variant": "fivefold_wf", "outer_k": 5}
    if kind == "reg":
        return _summarize_reg(folds, name, label, len(fc), meta)
    else:
        return _summarize_bin(folds, name, label, desc, len(fc), n,
                              float(np.mean(y_all)), meta)


def _build_b5_feature_columns(merged):
    base = [c for c in FEAT_COLS_BASE if c in merged.columns]
    B3_COLS = ["home_off_to_away_def", "away_off_to_home_def", "off_def_ratio_diff",
               "home_off_L10_to_away_def_L10", "away_off_L10_to_home_def_L10",
               "home_pace_adj_score", "away_pace_adj_score", "pace_adj_total",
               "pace_adj_diff", "home_pace_adj_score_L10", "away_pace_adj_score_L10",
               "trap_home_signals", "trap_home_overconf", "trap_away_motivated", "trap_combo"]
    Z_COLS = [c for c in merged.columns if c.endswith("_zsea")]
    B4_COLS = []
    for prefix in ["home_", "away_"]:
        for k in ["exp_ortg", "exp_drtg", "l5_pts_for", "l5_pts_against",
                  "l3_vs_l20_pts", "l3_vs_l20_def"]:
            B4_COLS.append(f"{prefix}{k}")
    for k in ["exp_ortg", "exp_drtg", "l5_pts_for", "l5_pts_against",
              "l3_vs_l20_pts", "l3_vs_l20_def"]:
        B4_COLS.append(f"{k}_diff")
    B5_COLS = []
    for prefix in ["home_", "away_"]:
        for k in ["opp_def_adj_ortg", "opp_off_adj_drtg", "l10_home_ortg",
                  "l10_road_ortg", "l10_home_drtg", "l10_road_drtg",
                  "win_quality_elo", "n_wins_in_l10"]:
            B5_COLS.append(f"{prefix}{k}")
    for k in ["opp_def_adj_ortg", "opp_off_adj_drtg", "l10_home_ortg", "l10_road_ortg",
              "l10_home_drtg", "l10_road_drtg", "win_quality_elo", "n_wins_in_l10"]:
        B5_COLS.append(f"{k}_diff")
    cols = base + B3_COLS + Z_COLS + B4_COLS + B5_COLS
    cols = [c for c in cols if c in merged.columns]
    return cols


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-6 — bagging variance + OOF stacking + 5-fold WF", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    print("[2] adding B3 features ...", flush=True)
    merged = add_b3_features(merged)
    print("[3] adding B4 recency features ...", flush=True)
    merged = add_recency_features(merged)
    print("[4] adding B5 quality+opp features ...", flush=True)
    merged = add_quality_features(merged)

    fc = _build_b5_feature_columns(merged)
    merged[fc] = merged[fc].fillna(0.0)
    print(f"[5] feature columns: {len(fc)}", flush=True)

    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    def naive_l5_mean(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).values

    def naive_l5_prop(col):
        return merged[col].shift(1).rolling(5, min_periods=1).mean().fillna(
            merged[col].mean()).clip(0.01, 0.99).values

    targets = [
        ("reg", "total_pts_box", None),
        ("reg", "score_diff", None),
        ("reg", "home_score", None),
        ("reg", "away_score", None),
        ("bin", "over_230", "P(total > 230)"),
        ("bin", "home_cover_AH3", "P(home covers -3)"),
    ]

    variants = [
        ("bag5_lgb", run_variant_bag5),
        ("oof_stack", run_variant_oof_stack),
        ("fivefold_wf", run_variant_fivefold),
    ]

    results = {}
    for kind, label, desc in targets:
        if kind == "reg":
            naive = naive_l5_mean(label)
        else:
            naive = naive_l5_prop(label)
        for vname, vrun in variants:
            t_v = time.time()
            name = f"R12_B6_{vname}_{label}"
            out = vrun(merged, label, naive, fc, name, kind, desc)
            out["elapsed_s"] = round(time.time() - t_v, 1)
            outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
            with open(outp, "w") as f:
                json.dump(out, f, indent=2)
            results[name] = out["status"]
            if out["kind"] == "regression":
                print(f"  {name}: {out['status']} feats={out['n_features']} "
                      f"delta {out['pooled_delta_pct']:+.2f}% "
                      f"({out['n_folds_positive']}/{out['n_valid_folds']}) "
                      f"fold_std={out.get('fold_delta_pct_std', 0):.2f}pp "
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
