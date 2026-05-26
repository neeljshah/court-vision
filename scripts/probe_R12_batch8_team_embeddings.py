"""probe_R12_batch8_team_embeddings.py — 30-team identity embeddings via SVD.

Base = 136-feature R12 B5 best + B6 OOF-stack architecture.

NEW: replace opp_def_rtg / opp_off_rtg SCALARS with 8-dim team embeddings.
Embeddings derived per outer-fold via SVD of the 30x30 team-vs-team performance
matrix M[h,a] = avg(score_diff_home_vs_away). Each team gets a "home identity"
(left singular vector row) and an "away identity" (right singular vector row).
No test-side leakage — embeddings re-fit on outer-train only.

Variants:
  - emb_svd_scorediff : 16-dim emb (8 home + 8 away) from score-diff matrix
  - emb_svd_combined  : 32-dim emb (16 from score-diff + 16 from total-pts matrix)

OOF-stack architecture preserved (4-fold outer + 5-fold inner OOF level-1 LGB
+ level-2 LGB+XGB on base+emb+oof_pred).
"""
from __future__ import annotations
import importlib.util, json, os, time
from collections import defaultdict
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_b5)
load_data = _b5.load_data
add_b3_features = _b5.add_b3_features
add_recency_features = _b5.add_recency_features
add_quality_features = _b5.add_quality_features

_B6_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch6_bagging_variance.py")
_spec6 = importlib.util.spec_from_file_location("probe_R12_batch6_bagging_variance", _B6_PATH)
_b6 = importlib.util.module_from_spec(_spec6)
_spec6.loader.exec_module(_b6)
_build_b5_feature_columns = _b6._build_b5_feature_columns


# ---------- models ----------
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


# ---------- team embeddings ----------
def _build_team_embeddings(train_df: pd.DataFrame, target_col: str,
                            k_dim: int = 8) -> dict:
    """Build 30-team SVD embeddings from the average target value per home/away pair
    over the training set. Returns {'home_emb': {team_id: vec}, 'away_emb': {team_id: vec},
    'k_dim': k}."""
    teams = sorted(set(train_df['home_team'].astype(str).unique()) |
                   set(train_df['away_team'].astype(str).unique()))
    n = len(teams)
    if n < 2:
        return {"home_emb": {}, "away_emb": {}, "k_dim": k_dim, "teams": teams}
    idx = {t: i for i, t in enumerate(teams)}
    # Sum + count matrices
    S = np.zeros((n, n))
    C = np.zeros((n, n))
    h_arr = train_df['home_team'].astype(str).values
    a_arr = train_df['away_team'].astype(str).values
    t_arr = train_df[target_col].astype(float).values
    for hi, ai, vi in zip(h_arr, a_arr, t_arr):
        ih, ia = idx[hi], idx[ai]
        S[ih, ia] += vi
        C[ih, ia] += 1
    # Avoid div-by-zero. Empty cells → row-mean (or global mean as fallback)
    row_means = np.where(C.sum(axis=1) > 0,
                         S.sum(axis=1) / np.maximum(C.sum(axis=1), 1), 0)
    global_mean = float(t_arr.mean()) if len(t_arr) else 0.0
    M = np.full((n, n), global_mean)
    mask = C > 0
    M[mask] = S[mask] / C[mask]
    # Fill empty cells with the corresponding row's mean
    for i in range(n):
        for j in range(n):
            if not mask[i, j]:
                M[i, j] = row_means[i] if row_means[i] != 0 else global_mean
    # Center the matrix
    M = M - M.mean()
    # SVD
    k = min(k_dim, n - 1)
    U, sv, Vt = np.linalg.svd(M, full_matrices=False)
    home_emb_mat = U[:, :k] * np.sqrt(sv[:k])
    away_emb_mat = Vt.T[:, :k] * np.sqrt(sv[:k])
    return {
        "home_emb": {t: home_emb_mat[idx[t]].copy() for t in teams},
        "away_emb": {t: away_emb_mat[idx[t]].copy() for t in teams},
        "k_dim": k,
        "teams": teams,
        "global_zero": np.zeros(k),
    }


def _apply_embeddings(df: pd.DataFrame, emb_dict: dict, prefix: str) -> np.ndarray:
    """Return matrix [n_rows, 2 * k_dim] = [home_emb | away_emb]."""
    k = emb_dict["k_dim"]
    zero = emb_dict.get("global_zero", np.zeros(k))
    h_arr = df['home_team'].astype(str).values
    a_arr = df['away_team'].astype(str).values
    out = np.zeros((len(df), 2 * k))
    for i, (h, a) in enumerate(zip(h_arr, a_arr)):
        out[i, :k] = emb_dict["home_emb"].get(h, zero)
        out[i, k:] = emb_dict["away_emb"].get(a, zero)
    return out


# ---------- core: B6-style OOF stack with extra emb features ----------
def _wf_indices(n, k):
    fs = n // k
    out = []
    for fi in range(k):
        ts = fi * fs
        te = (fi + 1) * fs if fi < k - 1 else n
        out.append((fi, list(range(0, ts)), list(range(ts, te))))
    return out


def run_emb_variant(merged, label, naive_pred, fc, name, kind, desc, emb_targets):
    """For each outer fold, build team embeddings on outer-train for each of
    emb_targets (list of column names), apply to all rows. Then B6 OOF-stack:
    5-fold inner OOF on (base+emb), level-2 LGB+XGB on (base+emb+oof_pred)."""
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    fc_arr = merged[fc].values
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        train_df = merged.iloc[tr]
        test_df = merged.iloc[ti]
        # Build emb for each emb target and concat
        emb_train_blocks = []
        emb_test_blocks = []
        for et in emb_targets:
            emb_dict = _build_team_embeddings(train_df, et, k_dim=8)
            emb_train_blocks.append(_apply_embeddings(train_df, emb_dict, et))
            emb_test_blocks.append(_apply_embeddings(test_df, emb_dict, et))
        emb_train = np.hstack(emb_train_blocks) if emb_train_blocks else np.zeros((len(tr), 0))
        emb_test = np.hstack(emb_test_blocks) if emb_test_blocks else np.zeros((len(ti), 0))
        X_tr_base = np.hstack([fc_arr[tr], emb_train])
        X_te_base = np.hstack([fc_arr[ti], emb_test])
        y_tr = y_all[tr]
        # B6 OOF-stack: 5-fold inner OOF on level-1 LGB
        n_tr = len(tr)
        oof = np.zeros(n_tr, dtype=float)
        inner_k = 5
        inner_fs = n_tr // inner_k
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
        # Level-1 full retrain
        if kind == "reg":
            mf = _lgb_reg(); mf.fit(X_tr_base, y_tr)
            test_l1 = mf.predict(X_te_base)
        else:
            mf = _lgb_clf(); mf.fit(X_tr_base, y_tr)
            test_l1 = mf.predict_proba(X_te_base)[:, 1]
        # Level-2
        X_tr_aug = np.hstack([X_tr_base, oof.reshape(-1, 1)])
        X_te_aug = np.hstack([X_te_base, test_l1.reshape(-1, 1)])
        if kind == "reg":
            l2_l = _lgb_reg(); l2_l.fit(X_tr_aug, y_tr)
            l2_x = _xgb_reg(); l2_x.fit(X_tr_aug, y_tr)
            y_pred = 0.5 * l2_l.predict(X_te_aug) + 0.5 * l2_x.predict(X_te_aug)
        else:
            l2_l = _lgb_clf(); l2_l.fit(X_tr_aug, y_tr)
            l2_x = _xgb_clf(); l2_x.fit(X_tr_aug, y_tr)
            y_pred = 0.5 * l2_l.predict_proba(X_te_aug)[:, 1] + \
                     0.5 * l2_x.predict_proba(X_te_aug)[:, 1]
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti]})
    n_features = len(fc) + 16 * len(emb_targets) + 1  # +1 for level-1 OOF
    meta = {"variant": name.split("R12_B7_")[-1] if "R12_B7_" in name else "emb_svd",
            "emb_targets": emb_targets, "k_dim": 8,
            "n_emb_features": 16 * len(emb_targets)}
    if kind == "reg":
        return _summarize_reg(folds, name, label, n_features, meta)
    else:
        return _summarize_bin(folds, name, label, desc, n_features, n,
                              float(np.mean(y_all)), meta)


# ---------- summarizers (mirror B6) ----------
def _summarize_reg(folds, name, label, n_features, variant_meta):
    if not folds:
        return {"probe": name, "kind": "regression", "label": label,
                "status": "REJECT", "ship_reason": "no valid folds",
                "n_features": n_features, "variant": variant_meta}
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
        return {"probe": name, "kind": "binary", "label": label,
                "status": "REJECT", "ship_reason": "no valid folds",
                "n_features": n_features, "variant": variant_meta}
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


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-8 — 30-team SVD identity embeddings (8-dim)", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = add_b3_features(merged)
    merged = add_recency_features(merged)
    merged = add_quality_features(merged)
    fc = _build_b5_feature_columns(merged)
    merged[fc] = merged[fc].fillna(0.0)
    print(f"[2] base feature columns: {len(fc)}", flush=True)

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

    # emb_targets per variant: which column(s) to SVD
    variants = [
        ("emb_svd_scorediff", ["score_diff"]),
        ("emb_svd_combined",  ["score_diff", "total_pts_box"]),
    ]

    results = {}
    for vname, emb_targets in variants:
        for kind, label, desc in targets:
            t_v = time.time()
            naive = naive_l5_mean(label) if kind == "reg" else naive_l5_prop(label)
            name = f"R12_B8_{vname}_{label}"
            out = run_emb_variant(merged, label, naive, fc, name, kind, desc,
                                   emb_targets)
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
