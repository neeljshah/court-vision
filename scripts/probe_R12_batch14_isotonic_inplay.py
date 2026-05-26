"""probe_R12_batch14_isotonic_inplay.py — isotonic/Platt calibration of B10 in-play.

Base = B10 in-play model at endQ1/Q2/Q3 (149 feats = 141 pregame + 7 snapshot + 1 OOF).

NEW: for each outer fold, generate raw predictions via the B6 OOF-stack pipeline,
then fit a CALIBRATOR (isotonic or Platt sigmoid) on outer-train OOF predictions
mapping raw → actual frequency, and apply to test predictions.

Ship gates (strict):
  - Binary: pooled Brier STRICTLY LOWER than uncalibrated B10 baseline.
  - Regression (remaining_total endQ2): pooled MAE STRICTLY LOWER than raw.

B10 uncalibrated baselines for beat_b10 reporting:
  endQ1: Brier 0.2191 AUC 0.7498
  endQ2: Brier 0.1846 AUC 0.8211
  endQ3: Brier 0.1359 AUC 0.9010
  remaining_total endQ2: pooled_delta_pct -25.38% (pooled_lgb_mae ~ from naive baseline)
"""
from __future__ import annotations
import importlib.util, json, os, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_b5)
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

_B10_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "probe_R12_batch10_inplay_winprob.py")
_spec10 = importlib.util.spec_from_file_location("probe_R12_batch10_inplay_winprob", _B10_PATH)
_b10 = importlib.util.module_from_spec(_spec10)
_spec10.loader.exec_module(_b10)
load_data_with_linescores = _b10.load_data_with_linescores
add_snapshot_features = _b10.add_snapshot_features
naive_winprob_from_margin = _b10.naive_winprob_from_margin
naive_remaining_total = _b10.naive_remaining_total


B10_RAW_BASELINE = {
    ("home_wins", 1):       {"brier": 0.2191, "auc": 0.7498},
    ("home_wins", 2):       {"brier": 0.1846, "auc": 0.8211},
    ("home_wins", 3):       {"brier": 0.1359, "auc": 0.9010},
    ("remaining_total", 2): {"pooled_delta_pct": -25.38},
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


def _b6_oof_stack(merged, fc, label, kind, tr, ti):
    """Return (test_pred, oof_preds_train, y_tr) for one outer fold's B6 OOF-stack."""
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
        # ALSO get level-2 OOF on outer-train via 3-fold inner-inner OOF for calibration
        n_tr2 = len(tr)
        oof_l2 = np.zeros(n_tr2, dtype=float)
        kk = 3; kf = n_tr2 // kk
        for kki in range(kk):
            a = kki * kf; b = (kki + 1) * kf if kki < kk - 1 else n_tr2
            ttr = list(range(0, a)) + list(range(b, n_tr2))
            tte = list(range(a, b))
            if len(ttr) < 50 or len(tte) < 5:
                continue
            ml = _lgb_reg(); ml.fit(X_tr_aug[ttr], y_tr[ttr])
            mx = _xgb_reg(); mx.fit(X_tr_aug[ttr], y_tr[ttr])
            oof_l2[tte] = 0.5 * ml.predict(X_tr_aug[tte]) + 0.5 * mx.predict(X_tr_aug[tte])
        return test_pred, oof_l2, y_tr
    else:
        l2_l = _lgb_clf(); l2_l.fit(X_tr_aug, y_tr)
        l2_x = _xgb_clf(); l2_x.fit(X_tr_aug, y_tr)
        test_pred = 0.5 * l2_l.predict_proba(X_te_aug)[:, 1] + \
                    0.5 * l2_x.predict_proba(X_te_aug)[:, 1]
        # Level-2 OOF on outer-train for calibration
        n_tr2 = len(tr)
        oof_l2 = np.zeros(n_tr2, dtype=float)
        kk = 3; kf = n_tr2 // kk
        for kki in range(kk):
            a = kki * kf; b = (kki + 1) * kf if kki < kk - 1 else n_tr2
            ttr = list(range(0, a)) + list(range(b, n_tr2))
            tte = list(range(a, b))
            if len(ttr) < 50 or len(tte) < 5:
                continue
            ml = _lgb_clf(); ml.fit(X_tr_aug[ttr], y_tr[ttr])
            mx = _xgb_clf(); mx.fit(X_tr_aug[ttr], y_tr[ttr])
            oof_l2[tte] = 0.5 * ml.predict_proba(X_tr_aug[tte])[:, 1] + \
                          0.5 * mx.predict_proba(X_tr_aug[tte])[:, 1]
        return test_pred, oof_l2, y_tr


def _calibrate_iso(oof_pred, y_oof, test_pred):
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(oof_pred, y_oof)
    return iso.predict(test_pred)


def _calibrate_platt(oof_pred, y_oof, test_pred):
    """Logistic regression on a single feature (the raw prob)."""
    from sklearn.linear_model import LogisticRegression
    X = np.clip(oof_pred, 1e-6, 1 - 1e-6).reshape(-1, 1)
    # Use log-odds as feature for monotonic fit
    logodds = np.log(X / (1 - X))
    lr = LogisticRegression(C=1.0)
    lr.fit(logodds, y_oof.astype(int))
    Xt = np.clip(test_pred, 1e-6, 1 - 1e-6).reshape(-1, 1)
    lo_t = np.log(Xt / (1 - Xt))
    return lr.predict_proba(lo_t)[:, 1]


def _calibrate_iso_reg(oof_pred, y_oof, test_pred):
    """For regression: isotonic monotonic mapping from raw_pred → actual."""
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(oof_pred, y_oof)
    return iso.predict(test_pred)


def run_calibrated(merged, label, naive_pred, fc, kind, calibrator_name):
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        test_pred, oof_l2, y_tr_ret = _b6_oof_stack(merged, fc, label, kind, tr, ti)
        if calibrator_name == "raw":
            cal_pred = test_pred
        elif calibrator_name == "isotonic":
            cal_pred = _calibrate_iso_reg(oof_l2, y_tr_ret, test_pred) if kind == "reg" \
                       else _calibrate_iso(oof_l2, y_tr_ret, test_pred)
        elif calibrator_name == "platt":
            cal_pred = _calibrate_platt(oof_l2, y_tr_ret, test_pred)
        else:
            raise ValueError(calibrator_name)
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": cal_pred,
                      "y_naive": naive_pred[ti]})
    return folds


def _summarize_bin(folds, name, label, desc, n_features, n_games, pos_rate, snap_q):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    if not folds:
        return {"probe": name, "kind": "binary", "label": label, "status": "REJECT",
                "n_features": n_features, "beat_b10": False}
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
    # Strict ship gate vs B10 raw baseline:
    raw = B10_RAW_BASELINE.get((label, snap_q), {})
    raw_brier = raw.get("brier")
    raw_auc = raw.get("auc")
    ship = (raw_brier is not None) and (plb < raw_brier) and nv_ >= 3
    beat = ship
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "snap_q": snap_q, "n_features": n_features, "n_games": int(n_games),
            "pos_rate": float(pos_rate),
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"Brier {plb:.4f} vs raw B10 {raw_brier}; AUC {plu:.4f}",
            "pooled_lgb_brier": round(plb, 5), "pooled_naive_brier": round(pnb, 5),
            "pooled_lgb_auc": round(plu, 5), "brier_delta_pct": round(bdp, 3),
            "n_valid_folds": nv_,
            "beat_b10": bool(beat),
            "b10_baseline_brier": raw_brier, "b10_baseline_auc": raw_auc}


def _summarize_reg(folds, name, label, n_features, snap_q):
    if not folds:
        return {"probe": name, "kind": "regression", "label": label, "status": "REJECT",
                "n_features": n_features, "beat_b10": False}
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    an = np.concatenate([f["y_naive"] for f in folds])
    pn = float(np.mean(np.abs(an - aa)))
    pl = float(np.mean(np.abs(al - aa)))
    dp = (pl - pn) / pn * 100.0
    nv = len(folds)
    # Strict ship gate: must beat raw B10 baseline delta_pct
    raw_dp = B10_RAW_BASELINE.get((label, snap_q), {}).get("pooled_delta_pct")
    ship = (raw_dp is not None) and (dp < raw_dp) and nv >= 3
    return {"probe": name, "kind": "regression", "label": label,
            "snap_q": snap_q, "n_features": n_features,
            "status": "SHIP" if ship else "REJECT",
            "ship_reason": f"delta {dp:+.2f}% vs raw B10 {raw_dp}",
            "pooled_naive_mae": round(pn, 4), "pooled_lgb_mae": round(pl, 4),
            "pooled_delta_pct": round(dp, 2),
            "n_valid_folds": nv,
            "beat_b10": bool(ship),
            "b10_baseline_delta_pct": raw_dp}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-14 — isotonic + Platt calibration of B10 in-play", flush=True)
    print("=" * 70, flush=True)

    merged = load_data_with_linescores()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = add_b3_features(merged)
    merged = add_recency_features(merged)
    merged = add_quality_features(merged)
    merged = add_interactions(merged)
    fc_pregame = _build_b5_feature_columns(merged)
    INTERACT_COLS = [c for c in ["home_rest_x_travel", "away_rest_x_travel",
                                  "rest_x_travel_diff", "b2b_x_pace_diff",
                                  "rest_diff_x_elo_diff"] if c in merged.columns]
    fc_pregame = fc_pregame + INTERACT_COLS
    merged[fc_pregame] = merged[fc_pregame].fillna(0.0)
    print(f"[2] pregame cols: {len(fc_pregame)}", flush=True)

    merged["home_wins"] = (merged["score_diff"] > 0).astype(int)

    SNAP_FEATURES = ["cum_home_score", "cum_away_score", "cum_score_diff",
                     "cum_total", "score_margin_abs", "q_remaining",
                     "cum_pace_proxy"]

    results = {}
    for snap_q in [1, 2, 3]:
        snap_merged = add_snapshot_features(merged, snap_q)
        snap_merged[SNAP_FEATURES] = snap_merged[SNAP_FEATURES].fillna(0.0)
        fc_full = fc_pregame + SNAP_FEATURES
        naive_wp = _b10.naive_winprob_from_margin(
            snap_merged["cum_score_diff"].values, 4 - snap_q)

        # Three calibrators: raw (sanity), isotonic, platt
        for cal in ["raw", "isotonic", "platt"]:
            t_v = time.time()
            name = f"R12_B14_{cal}_winprob_endQ{snap_q}"
            folds = run_calibrated(snap_merged, "home_wins", naive_wp, fc_full,
                                    "bin", cal)
            out = _summarize_bin(folds, name, "home_wins",
                                  f"P(home_wins) at endQ{snap_q} via {cal}",
                                  len(fc_full) + 1, len(snap_merged),
                                  float(snap_merged["home_wins"].mean()), snap_q)
            out["elapsed_s"] = round(time.time() - t_v, 1)
            outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
            with open(outp, "w") as f:
                json.dump(out, f, indent=2)
            results[name] = out["status"]
            beat_str = " BEAT_B10" if out.get("beat_b10") else " (B10 raw wins)"
            print(f"  {name}: {out['status']} Brier {out['pooled_lgb_brier']:.4f} "
                  f"AUC {out['pooled_lgb_auc']:.4f}{beat_str} [{out['elapsed_s']}s]",
                  flush=True)

        # Regression: remaining_total at endQ2 only
        if snap_q == 2:
            snap_merged["remaining_total"] = snap_merged["total_pts_box"] - snap_merged["cum_total"]
            naive_rem = _b10.naive_remaining_total(snap_merged["cum_total"].values, snap_q)
            for cal in ["raw", "isotonic"]:
                t_v = time.time()
                name = f"R12_B14_{cal}_remaining_total_endQ{snap_q}"
                folds = run_calibrated(snap_merged, "remaining_total", naive_rem,
                                        fc_full, "reg", cal)
                out = _summarize_reg(folds, name, "remaining_total", len(fc_full) + 1, snap_q)
                out["elapsed_s"] = round(time.time() - t_v, 1)
                outp = os.path.join(DATA_CACHE, f"probe_{name}_results.json")
                with open(outp, "w") as f:
                    json.dump(out, f, indent=2)
                results[name] = out["status"]
                beat_str = " BEAT_B10" if out.get("beat_b10") else " (B10 raw wins)"
                print(f"  {name}: {out['status']} delta {out['pooled_delta_pct']:+.2f}%{beat_str} "
                      f"[{out['elapsed_s']}s]", flush=True)

    n_s = sum(1 for v in results.values() if v == "SHIP")
    n_r = sum(1 for v in results.values() if v == "REJECT")
    print(f"\n[done] {n_s} SHIPS, {n_r} REJECTS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
