"""probe_R12_batch9_rest_travel_halflife2.py — halflife=2 recency + interactions.

Base = 136-feature R12 B5 best + B6 OOF-stack architecture.

NEW:
  - halflife=2 recency features (replaces or augments halflife=4 from B4)
    exp_ortg_h2, exp_drtg_h2 per team via λ = ln(2)/2 (sharper than B4 λ = ln(2)/4)
  - rest_days × travel_miles interaction per team
  - b2b_diff × pace_diff interaction
  - rest_diff × elo_differential interaction

Variants:
  - halflife2_only        : halflife=2 features REPLACE halflife=4 (same count, sharper)
  - both_halflives        : halflife=4 + halflife=2 (additive, +12 feats)
  - interactions_only     : add 4 interaction features on top of B5+B6
  - all                   : halflife=2 + interactions, ADDITIVE on halflife=4

Records beat_b6: true/false per result, compared to canonical B6 OOF-stack baseline.
"""
from __future__ import annotations
import importlib.util, json, math, os, time
from collections import defaultdict
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_b5)
load_data = _b5.load_data
add_b3_features = _b5.add_b3_features
add_recency_features = _b5.add_recency_features  # halflife=4
add_quality_features = _b5.add_quality_features

_B6_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch6_bagging_variance.py")
_spec6 = importlib.util.spec_from_file_location("probe_R12_batch6_bagging_variance", _B6_PATH)
_b6 = importlib.util.module_from_spec(_spec6)
_spec6.loader.exec_module(_b6)
_build_b5_feature_columns = _b6._build_b5_feature_columns


# B6 baselines (production canonical) — for beat_b6 reporting
B6_BASELINE = {
    "total_pts_box":   {"pooled_delta_pct": -15.09},
    "score_diff":      {"pooled_delta_pct": -16.90},
    "home_score":      {"pooled_delta_pct": -15.90},
    "away_score":      {"pooled_delta_pct": -14.18},
    "over_230":        {"pooled_lgb_brier": 0.2383, "pooled_lgb_auc": 0.6737},
    "home_cover_AH3":  {"pooled_lgb_brier": 0.2313, "pooled_lgb_auc": 0.6987},
}


def add_recency_h2(merged: pd.DataFrame) -> pd.DataFrame:
    """B4-style recency but with halflife=2 (vs halflife=4)."""
    merged = merged.reset_index(drop=True).copy()
    th = defaultdict(list)
    n = len(merged)
    HALFLIFE = 2.0
    LAMBDA = math.log(2) / HALFLIFE

    out_keys = ["exp_ortg_h2", "exp_drtg_h2", "l3_pts_for_h2", "l3_pts_against_h2"]
    home_arrs = {k: np.zeros(n) for k in out_keys}
    away_arrs = {k: np.zeros(n) for k in out_keys}

    def _f(hist):
        if not hist:
            return None
        n_h = len(hist)
        pts_for = np.array([h[1] for h in hist])
        pts_aga = np.array([h[2] for h in hist])
        w = np.exp(-LAMBDA * np.arange(n_h)[::-1]); w /= w.sum()
        exp_for = float(np.sum(w * pts_for))
        exp_aga = float(np.sum(w * pts_aga))
        l3_for = float(np.mean(pts_for[-3:])) if n_h >= 3 else exp_for
        l3_aga = float(np.mean(pts_aga[-3:])) if n_h >= 3 else exp_aga
        return {"exp_ortg_h2": exp_for, "exp_drtg_h2": exp_aga,
                "l3_pts_for_h2": l3_for, "l3_pts_against_h2": l3_aga}

    for idx in range(n):
        row = merged.iloc[idx]
        h, a = str(row["home_team"]), str(row["away_team"])
        hf, af = _f(th[h]), _f(th[a])
        if hf:
            for k, v in hf.items(): home_arrs[k][idx] = v
        if af:
            for k, v in af.items(): away_arrs[k][idx] = v
        th[h].append((row["game_date"], row["home_score"], row["away_score"]))
        th[a].append((row["game_date"], row["away_score"], row["home_score"]))

    for k in out_keys:
        merged[f"home_{k}"] = home_arrs[k]
        merged[f"away_{k}"] = away_arrs[k]
        merged[f"{k}_diff"] = home_arrs[k] - away_arrs[k]
    return merged


def add_interactions(merged: pd.DataFrame) -> pd.DataFrame:
    """rest*travel, b2b*pace, rest_diff*elo_diff interactions."""
    m = merged.copy()
    m["home_rest_x_travel"] = m["home_rest_days"].fillna(0) * m["home_travel_miles"].fillna(0)
    m["away_rest_x_travel"] = m["away_rest_days"].fillna(0) * m["away_travel_miles"].fillna(0)
    m["rest_x_travel_diff"] = m["home_rest_x_travel"] - m["away_rest_x_travel"]
    if "b2b_diff" in m.columns and "pace_diff" in m.columns:
        m["b2b_x_pace_diff"] = m["b2b_diff"].fillna(0) * m["pace_diff"].fillna(0)
    if "elo_differential" in m.columns:
        rest_diff = m["home_rest_days"].fillna(0) - m["away_rest_days"].fillna(0)
        m["rest_diff_x_elo_diff"] = rest_diff * m["elo_differential"].fillna(0)
    return m


# Model builders (mirror B6)
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


def run_oof_stack(merged, label, naive_pred, fc, name, kind, desc=None):
    """B6-style OOF stack with given feature column list."""
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
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
            y_pred = 0.5 * l2_l.predict(X_te_aug) + 0.5 * l2_x.predict(X_te_aug)
        else:
            l2_l = _lgb_clf(); l2_l.fit(X_tr_aug, y_tr)
            l2_x = _xgb_clf(); l2_x.fit(X_tr_aug, y_tr)
            y_pred = 0.5 * l2_l.predict_proba(X_te_aug)[:, 1] + \
                     0.5 * l2_x.predict_proba(X_te_aug)[:, 1]
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti]})
    if kind == "reg":
        return _summarize_reg(folds, name, label, len(fc) + 1)
    else:
        return _summarize_bin(folds, name, label, desc, len(fc) + 1, n,
                              float(np.mean(y_all)))


def _summarize_reg(folds, name, label, n_features):
    if not folds:
        return {"probe": name, "kind": "regression", "label": label,
                "status": "REJECT", "ship_reason": "no valid folds",
                "n_features": n_features, "beat_b6": False}
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
    b6 = B6_BASELINE.get(label, {})
    beat = (dp < b6.get("pooled_delta_pct", 0.0)) if "pooled_delta_pct" in b6 else None
    return {"probe": name, "kind": "regression", "label": label,
            "n_features": n_features,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"WF {np_}/{nv}, delta {dp:+.2f}%",
            "pooled_naive_mae": round(pn, 4), "pooled_lgb_mae": round(pl, 4),
            "pooled_delta_pct": round(dp, 2),
            "n_folds_positive": np_, "n_valid_folds": nv,
            "fold_results": fold_results,
            "beat_b6": bool(beat) if beat is not None else None,
            "b6_baseline_delta_pct": b6.get("pooled_delta_pct"),
            "vs_b6_pp": round(dp - b6.get("pooled_delta_pct", 0.0), 2) if "pooled_delta_pct" in b6 else None}


def _summarize_bin(folds, name, label, desc, n_features, n_games, pos_rate):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    if not folds:
        return {"probe": name, "kind": "binary", "label": label,
                "status": "REJECT", "ship_reason": "no valid folds",
                "n_features": n_features, "beat_b6": False}
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
    b6 = B6_BASELINE.get(label, {})
    beat = None
    if "pooled_lgb_brier" in b6:
        # Beat B6 if Brier strictly lower OR AUC strictly higher
        beat = (plb < b6["pooled_lgb_brier"]) or (plu > b6["pooled_lgb_auc"])
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "n_features": n_features, "n_games": int(n_games), "pos_rate": float(pos_rate),
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {plb:.4f} ({bdp:+.2f}%); AUC {plu:.4f}",
            "pooled_lgb_brier": round(plb, 5), "pooled_naive_brier": round(pnb, 5),
            "pooled_lgb_auc": round(plu, 5), "brier_delta_pct": round(bdp, 3),
            "n_valid_folds": nv_, "fold_results": fold_results,
            "beat_b6": bool(beat) if beat is not None else None,
            "b6_baseline_brier": b6.get("pooled_lgb_brier"),
            "b6_baseline_auc": b6.get("pooled_lgb_auc")}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-9 — halflife=2 recency + rest/travel interactions", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = add_b3_features(merged)
    merged = add_recency_features(merged)        # halflife=4
    merged = add_quality_features(merged)
    merged = add_recency_h2(merged)              # halflife=2
    merged = add_interactions(merged)            # interactions
    fc_b5 = _build_b5_feature_columns(merged)    # 136 base
    H2_COLS = []
    for prefix in ["home_", "away_"]:
        for k in ["exp_ortg_h2", "exp_drtg_h2", "l3_pts_for_h2", "l3_pts_against_h2"]:
            H2_COLS.append(f"{prefix}{k}")
    for k in ["exp_ortg_h2", "exp_drtg_h2", "l3_pts_for_h2", "l3_pts_against_h2"]:
        H2_COLS.append(f"{k}_diff")
    H4_COLS = [c for c in fc_b5 if c.endswith("_exp_ortg") or c.endswith("_exp_drtg")
               or c.endswith("_l5_pts_for") or c.endswith("_l5_pts_against")
               or c.endswith("_l3_vs_l20_pts") or c.endswith("_l3_vs_l20_def")
               or c == "exp_ortg_diff" or c == "exp_drtg_diff"
               or c == "l5_pts_for_diff" or c == "l5_pts_against_diff"
               or c == "l3_vs_l20_pts_diff" or c == "l3_vs_l20_def_diff"]
    INTERACT_COLS = ["home_rest_x_travel", "away_rest_x_travel", "rest_x_travel_diff",
                     "b2b_x_pace_diff", "rest_diff_x_elo_diff"]
    INTERACT_COLS = [c for c in INTERACT_COLS if c in merged.columns]
    H2_COLS = [c for c in H2_COLS if c in merged.columns]
    print(f"[2] base B5+B6 cols: {len(fc_b5)}", flush=True)
    print(f"    halflife=4 cols (to swap out): {len(H4_COLS)}", flush=True)
    print(f"    halflife=2 cols (new): {len(H2_COLS)}", flush=True)
    print(f"    interaction cols (new): {len(INTERACT_COLS)}", flush=True)

    fc_h2only = [c for c in fc_b5 if c not in H4_COLS] + H2_COLS
    fc_both = fc_b5 + H2_COLS
    fc_interactions = fc_b5 + INTERACT_COLS
    fc_all = fc_b5 + H2_COLS + INTERACT_COLS

    for cols in [fc_h2only, fc_both, fc_interactions, fc_all]:
        merged[cols] = merged[cols].fillna(0.0)

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
        ("halflife2_only", fc_h2only),
        ("both_halflives", fc_both),
        ("interactions_only", fc_interactions),
        ("all", fc_all),
    ]

    results = {}
    n_beat_b6 = 0
    for vname, fc in variants:
        for kind, label, desc in targets:
            t_v = time.time()
            naive = naive_l5_mean(label) if kind == "reg" else naive_l5_prop(label)
            name = f"R12_B9_{vname}_{label}"
            out = run_oof_stack(merged, label, naive, fc, name, kind, desc)
            out["elapsed_s"] = round(time.time() - t_v, 1)
            outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
            with open(outp, "w") as f:
                json.dump(out, f, indent=2)
            results[name] = out["status"]
            beat_str = ""
            if out.get("beat_b6") is True:
                n_beat_b6 += 1
                beat_str = " BEAT_B6"
            elif out.get("beat_b6") is False:
                beat_str = " (B6 wins)"
            if out["kind"] == "regression":
                vs = out.get("vs_b6_pp")
                print(f"  {name}: {out['status']} feats={out['n_features']} "
                      f"delta {out['pooled_delta_pct']:+.2f}% "
                      f"({out['n_folds_positive']}/{out['n_valid_folds']}) "
                      f"vs_B6={vs:+.2f}pp{beat_str} [{out['elapsed_s']}s]", flush=True)
            else:
                print(f"  {name}: {out['status']} feats={out['n_features']} "
                      f"Brier {out['pooled_lgb_brier']:.4f} "
                      f"AUC {out['pooled_lgb_auc']:.4f} "
                      f"({out['brier_delta_pct']:+.2f}%){beat_str} [{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS, {n_beat_b6}/{n_s+n_r} BEAT_B6 in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
