"""probe_R12_batch13_hybrid_winners.py — combine R12 best-per-target winners.

Per-target canonical winners after B12:
  total:      B9 interactions_only  (B5 base + 5 interaction feats)         141 feats
  spread:     B11 opp_full          (B5 base + interact + opp_l5_allowed*)  163 feats
  home_score: B9 all                (B5 base + interact + halflife2)        154 feats
  away_score: B9 halflife2_only     (B5 base − halflife4 + halflife2)       131 feats
  O230:       B11 opp_full                                                  163 feats
  AH3:        B11 opp_pts_pace      (B5 base + interact + opp_pts + pace)   157 feats

Variants:
  - union_all     : kitchen-sink — all features that appear in ANY canonical
                    (tests whether adding more features hurts via overfit/noise)
  - intersection  : only features that appear in ≥3 canonical winners
                    (tests "agreement = signal" hypothesis)
  - avg_blend     : per-target, train the 2 best canonical models on their
                    respective feature sets and average their final predictions 50/50.
                    Tests prediction-level ensembling across feature subsets.

Records beat_canonical vs the per-target single-canonical baseline.
"""
from __future__ import annotations
import importlib.util, json, os, time
from collections import Counter
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
add_recency_features = _b5.add_recency_features
add_quality_features = _b5.add_quality_features

_B6_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch6_bagging_variance.py")
_spec6 = importlib.util.spec_from_file_location("probe_R12_batch6_bagging_variance", _B6_PATH)
_b6 = importlib.util.module_from_spec(_spec6)
_spec6.loader.exec_module(_b6)
_build_b5_feature_columns = _b6._build_b5_feature_columns

_B9_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch9_rest_travel_halflife2.py")
_spec9 = importlib.util.spec_from_file_location("probe_R12_batch9_rest_travel_halflife2", _B9_PATH)
_b9 = importlib.util.module_from_spec(_spec9)
_spec9.loader.exec_module(_b9)
add_interactions = _b9.add_interactions
add_recency_h2 = _b9.add_recency_h2

_B11_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "probe_R12_batch11_opp_allowed_stat_specific.py")
_spec11 = importlib.util.spec_from_file_location("probe_R12_batch11_opp_allowed_stat_specific", _B11_PATH)
_b11 = importlib.util.module_from_spec(_spec11)
_spec11.loader.exec_module(_b11)
add_opp_allowed_features = _b11.add_opp_allowed_features


CANONICAL_BASELINE = {
    "total_pts_box":   {"pooled_delta_pct": -16.27, "src": "B9 interactions_only"},
    "score_diff":      {"pooled_delta_pct": -17.44, "src": "B11 opp_full"},
    "home_score":      {"pooled_delta_pct": -16.10, "src": "B9 all"},
    "away_score":      {"pooled_delta_pct": -14.35, "src": "B9 halflife2_only"},
    "over_230":        {"pooled_lgb_brier": 0.2383, "pooled_lgb_auc": 0.6804, "src": "B11 opp_full"},
    "home_cover_AH3":  {"pooled_lgb_brier": 0.2294, "pooled_lgb_auc": 0.7058, "src": "B11 opp_pts_pace"},
}


# Models (mirror B6/B9/B11)
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
    """One outer fold's B6-style OOF stack prediction. Returns y_pred for ti."""
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


def run_single_feat_set(merged, label, naive_pred, fc, kind):
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        y_pred = _oof_stack_pred(merged, fc, label, kind, tr, ti)
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti]})
    return folds


def run_avg_blend(merged, label, naive_pred, fc_a, fc_b, kind):
    """Train two models on different feature sets, average predictions 50/50."""
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        pred_a = _oof_stack_pred(merged, fc_a, label, kind, tr, ti)
        pred_b = _oof_stack_pred(merged, fc_b, label, kind, tr, ti)
        y_pred = 0.5 * pred_a + 0.5 * pred_b
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred,
                      "y_naive": naive_pred[ti]})
    return folds


def _summarize_reg(folds, name, label, n_features):
    if not folds:
        return {"probe": name, "kind": "regression", "label": label,
                "status": "REJECT", "n_features": n_features, "beat_canonical": False}
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
    can = CANONICAL_BASELINE.get(label, {})
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
            "vs_canonical_pp": round(dp - can.get("pooled_delta_pct", 0.0), 2) if "pooled_delta_pct" in can else None}


def _summarize_bin(folds, name, label, desc, n_features, n_games, pos_rate):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    if not folds:
        return {"probe": name, "kind": "binary", "label": label, "status": "REJECT",
                "n_features": n_features, "beat_canonical": False}
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
    can = CANONICAL_BASELINE.get(label, {})
    beat = None
    if "pooled_lgb_brier" in can:
        beat = (plb < can["pooled_lgb_brier"]) or (plu > can["pooled_lgb_auc"])
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "n_features": n_features, "n_games": int(n_games), "pos_rate": float(pos_rate),
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {plb:.4f} ({bdp:+.2f}%); AUC {plu:.4f}",
            "pooled_lgb_brier": round(plb, 5), "pooled_naive_brier": round(pnb, 5),
            "pooled_lgb_auc": round(plu, 5), "brier_delta_pct": round(bdp, 3),
            "n_valid_folds": nv_, "fold_results": fold_results,
            "beat_canonical": bool(beat) if beat is not None else None,
            "canonical_src": can.get("src")}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-13 — hybrid winners (union / intersection / avg_blend)", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = add_b3_features(merged)
    merged = add_recency_features(merged)
    merged = add_quality_features(merged)
    merged = add_interactions(merged)
    merged = add_recency_h2(merged)
    merged = add_opp_allowed_features(merged)

    fc_b5 = _build_b5_feature_columns(merged)
    INTERACT_COLS = [c for c in ["home_rest_x_travel", "away_rest_x_travel",
                                  "rest_x_travel_diff", "b2b_x_pace_diff",
                                  "rest_diff_x_elo_diff"] if c in merged.columns]
    H4_COLS = [c for c in fc_b5 if (c.endswith("_exp_ortg") or c.endswith("_exp_drtg")
               or c.endswith("_l5_pts_for") or c.endswith("_l5_pts_against")
               or c.endswith("_l3_vs_l20_pts") or c.endswith("_l3_vs_l20_def")
               or c in ("exp_ortg_diff", "exp_drtg_diff", "l5_pts_for_diff",
                        "l5_pts_against_diff", "l3_vs_l20_pts_diff", "l3_vs_l20_def_diff"))]
    H2_COLS = []
    for prefix in ["home_", "away_"]:
        for k in ["exp_ortg_h2", "exp_drtg_h2", "l3_pts_for_h2", "l3_pts_against_h2"]:
            H2_COLS.append(f"{prefix}{k}")
    for k in ["exp_ortg_h2", "exp_drtg_h2", "l3_pts_for_h2", "l3_pts_against_h2"]:
        H2_COLS.append(f"{k}_diff")
    H2_COLS = [c for c in H2_COLS if c in merged.columns]
    OPP_PTS_COLS = []
    for prefix in ["home_", "away_"]:
        for k in ["opp_allowed_PTS_l5", "opp_allowed_PTS_home_l5",
                  "opp_allowed_PTS_away_l5", "opp_allowed_PTS_l3"]:
            OPP_PTS_COLS.append(f"{prefix}{k}")
    for k in ["opp_allowed_PTS_l5", "opp_allowed_PTS_home_l5",
              "opp_allowed_PTS_away_l5", "opp_allowed_PTS_l3"]:
        OPP_PTS_COLS.append(f"{k}_diff")
    OPP_PTS_COLS = [c for c in OPP_PTS_COLS if c in merged.columns]
    OPP_PACE_COLS = [c for c in ["home_opp_l5_pace", "away_opp_l5_pace",
                                 "opp_l5_pace_diff"] if c in merged.columns]
    OPP_RATE_COLS = [c for c in ["home_opp_l5_oreb_pct_against",
                                 "away_opp_l5_oreb_pct_against",
                                 "opp_l5_oreb_pct_against_diff",
                                 "home_opp_l5_tov_pct_against",
                                 "away_opp_l5_tov_pct_against",
                                 "opp_l5_tov_pct_against_diff"] if c in merged.columns]

    # Per-target canonical feature sets
    fc_interactions_only   = fc_b5 + INTERACT_COLS
    fc_opp_full            = fc_b5 + INTERACT_COLS + OPP_PTS_COLS + OPP_PACE_COLS + OPP_RATE_COLS
    fc_all_b9              = fc_b5 + H2_COLS + INTERACT_COLS
    fc_halflife2_only      = [c for c in fc_b5 if c not in H4_COLS] + H2_COLS
    fc_opp_pts_pace        = fc_b5 + INTERACT_COLS + OPP_PTS_COLS + OPP_PACE_COLS

    CANONICAL_FC = {
        "total_pts_box":  fc_interactions_only,
        "score_diff":     fc_opp_full,
        "home_score":     fc_all_b9,
        "away_score":     fc_halflife2_only,
        "over_230":       fc_opp_full,
        "home_cover_AH3": fc_opp_pts_pace,
    }
    # Top-2 per target for avg_blend (the canonical winner + a strong runner-up)
    TOP2_FC = {
        "total_pts_box":  (fc_interactions_only, fc_opp_full),
        "score_diff":     (fc_opp_full, fc_all_b9),
        "home_score":     (fc_all_b9, fc_interactions_only),
        "away_score":     (fc_halflife2_only, fc_all_b9),
        "over_230":       (fc_opp_full, fc_opp_pts_pace),
        "home_cover_AH3": (fc_opp_pts_pace, fc_opp_full),
    }

    # Union of ALL features across canonicals
    union_set = set()
    for fc in [fc_interactions_only, fc_opp_full, fc_all_b9, fc_halflife2_only, fc_opp_pts_pace]:
        union_set.update(fc)
    fc_union = sorted(union_set)

    # Intersection: features that appear in >=3 of the 5 canonical sets
    cnt = Counter()
    for fc in [fc_interactions_only, fc_opp_full, fc_all_b9, fc_halflife2_only, fc_opp_pts_pace]:
        cnt.update(set(fc))
    fc_intersection = sorted([c for c, k in cnt.items() if k >= 3])

    print(f"[2] feature-set sizes:", flush=True)
    print(f"    union_all:    {len(fc_union)} feats", flush=True)
    print(f"    intersection (>=3): {len(fc_intersection)} feats", flush=True)

    for fc in [fc_union, fc_intersection,
               fc_interactions_only, fc_opp_full, fc_all_b9,
               fc_halflife2_only, fc_opp_pts_pace]:
        merged[fc] = merged[fc].fillna(0.0)

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

    results = {}; n_beat = 0; n_total = 0
    for kind, label, desc in targets:
        naive = naive_l5_mean(label) if kind == "reg" else naive_l5_prop(label)

        # union_all
        for vname, fc in [("union_all", fc_union), ("intersection", fc_intersection)]:
            t_v = time.time()
            name = f"R12_B13_{vname}_{label}"
            folds = run_single_feat_set(merged, label, naive, fc, kind)
            if kind == "reg":
                out = _summarize_reg(folds, name, label, len(fc) + 1)
            else:
                y_all = merged[label].astype(int).values
                out = _summarize_bin(folds, name, label, desc, len(fc) + 1,
                                      len(merged), float(np.mean(y_all)))
            out["elapsed_s"] = round(time.time() - t_v, 1)
            outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
            with open(outp, "w") as f:
                json.dump(out, f, indent=2)
            results[name] = out["status"]; n_total += 1
            beat_str = ""
            if out.get("beat_canonical") is True:
                n_beat += 1; beat_str = " BEAT_CANONICAL"
            elif out.get("beat_canonical") is False:
                beat_str = f" (canon {out.get('canonical_src','?')} wins)"
            if out["kind"] == "regression":
                vs = out.get("vs_canonical_pp")
                print(f"  {name}: {out['status']} feats={out['n_features']} "
                      f"delta {out['pooled_delta_pct']:+.2f}% "
                      f"vs_canon={vs:+.2f}pp{beat_str} [{out['elapsed_s']}s]", flush=True)
            else:
                print(f"  {name}: {out['status']} feats={out['n_features']} "
                      f"Brier {out['pooled_lgb_brier']:.4f} "
                      f"AUC {out['pooled_lgb_auc']:.4f}{beat_str} [{out['elapsed_s']}s]", flush=True)

        # avg_blend (per-target top-2)
        fc_a, fc_b = TOP2_FC[label]
        for fc in [fc_a, fc_b]:
            merged[fc] = merged[fc].fillna(0.0)
        t_v = time.time()
        name = f"R12_B13_avg_blend_{label}"
        folds = run_avg_blend(merged, label, naive, fc_a, fc_b, kind)
        n_feats_blend = max(len(fc_a), len(fc_b)) + 1  # representative
        if kind == "reg":
            out = _summarize_reg(folds, name, label, n_feats_blend)
        else:
            y_all = merged[label].astype(int).values
            out = _summarize_bin(folds, name, label, desc, n_feats_blend,
                                  len(merged), float(np.mean(y_all)))
        out["elapsed_s"] = round(time.time() - t_v, 1)
        out["blend_fc_a_len"] = len(fc_a)
        out["blend_fc_b_len"] = len(fc_b)
        outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        results[name] = out["status"]; n_total += 1
        beat_str = ""
        if out.get("beat_canonical") is True:
            n_beat += 1; beat_str = " BEAT_CANONICAL"
        elif out.get("beat_canonical") is False:
            beat_str = f" (canon {out.get('canonical_src','?')} wins)"
        if out["kind"] == "regression":
            vs = out.get("vs_canonical_pp")
            print(f"  {name}: {out['status']} blend({out['blend_fc_a_len']}+{out['blend_fc_b_len']}) "
                  f"delta {out['pooled_delta_pct']:+.2f}% "
                  f"vs_canon={vs:+.2f}pp{beat_str} [{out['elapsed_s']}s]", flush=True)
        else:
            print(f"  {name}: {out['status']} blend({out['blend_fc_a_len']}+{out['blend_fc_b_len']}) "
                  f"Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f}{beat_str} [{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS, {n_beat}/{n_total} BEAT_CANONICAL in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
