"""probe_R12_batch32_inplay_rebaseline.py - honest re-baseline of B14 in-play models.

B14 numbers were captured on 2839 games. Current dataset is ~4910 games.
Re-run honest 4-fold WF on current data with end-to-end leak-free Platt
calibration (inner CV for calibrator fitting on outer-train only).

For each snap_q in [1, 2, 3]:
  - Compute pooled raw Brier + AUC (uncalibrated)
  - Compute pooled calibrated Brier + AUC (Platt via inner-3-fold OOF)
  - Compare to B14 frozen reference + naive logistic-margin baseline

For remaining_total at endQ2:
  - Raw + isotonic-calibrated MAE vs naive linear extrapolation

Drift analysis: live - frozen for each metric.
"""
from __future__ import annotations
import importlib.util, json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.r12_canonical_predictor import (  # noqa: E402
    build_r12_features, train_canonical_model, predict_canonical,
)

_B10_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "probe_R12_batch10_inplay_winprob.py")
_spec10 = importlib.util.spec_from_file_location("probe_R12_batch10_inplay_winprob", _B10_PATH)
_b10 = importlib.util.module_from_spec(_spec10); _spec10.loader.exec_module(_b10)
load_data_with_linescores = _b10.load_data_with_linescores
add_snapshot_features = _b10.add_snapshot_features
naive_winprob_from_margin = _b10.naive_winprob_from_margin
naive_remaining_total = _b10.naive_remaining_total

_B9_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch9_rest_travel_halflife2.py")
_spec9 = importlib.util.spec_from_file_location("probe_R12_batch9_rest_travel_halflife2", _B9_PATH)
_b9 = importlib.util.module_from_spec(_spec9); _spec9.loader.exec_module(_b9)
add_interactions = _b9.add_interactions


B14_FROZEN = {
    ("home_wins", 1):       {"brier": 0.2042, "auc": 0.7500},
    ("home_wins", 2):       {"brier": 0.1736, "auc": 0.8212},
    ("home_wins", 3):       {"brier": 0.1277, "auc": 0.9012},
    ("remaining_total", 2): {"pooled_delta_pct": -25.65},
}

SNAP_FEATURES = ["cum_home_score", "cum_away_score", "cum_score_diff",
                 "cum_total", "score_margin_abs", "q_remaining", "cum_pace_proxy"]


def _wf_indices(n, k):
    fs = n // k
    out = []
    for fi in range(k):
        ts = fi * fs
        te = (fi + 1) * fs if fi < k - 1 else n
        out.append((fi, list(range(0, ts)), list(range(ts, te))))
    return out


def _platt_calibrate(oof_pred, y_oof, test_pred):
    """Train Platt sigmoid on outer-train OOF, apply to test."""
    from sklearn.linear_model import LogisticRegression
    O = np.clip(oof_pred, 1e-6, 1 - 1e-6).reshape(-1, 1)
    lo = np.log(O / (1 - O))
    lr = LogisticRegression(C=1.0); lr.fit(lo, y_oof.astype(int))
    R = np.clip(test_pred, 1e-6, 1 - 1e-6).reshape(-1, 1)
    lo_t = np.log(R / (1 - R))
    return lr.predict_proba(lo_t)[:, 1]


def _isotonic_calibrate(oof_pred, y_oof, test_pred):
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(oof_pred, y_oof)
    return iso.predict(test_pred)


def _oof_stack_with_inner_oof(merged, fc, label, kind, tr, ti):
    """Train B6 OOF-stack + generate inner-3-fold OOF on outer-train (for calibrator).
    Returns (test_pred, oof_l2_on_outer_train).
    """
    X_tr = merged[fc].iloc[tr].values
    X_te = merged[fc].iloc[ti].values
    y_all = merged[label].astype(int if kind == "bin" else float).values
    y_tr = y_all[tr]
    # Train canonical end-to-end on outer-train
    df_tr = merged.iloc[tr].reset_index(drop=True)
    df_tr[fc] = df_tr[fc].fillna(0.0)
    model = train_canonical_model(df_tr, label, fc=fc, kind=kind)
    test_pred = predict_canonical(model, X_te)
    # Inner 3-fold OOF on outer-train (for Platt/isotonic fitting)
    n_tr = len(tr)
    oof = np.zeros(n_tr)
    kk = 3; kf = n_tr // kk
    for kki in range(kk):
        a = kki * kf; b = (kki + 1) * kf if kki < kk - 1 else n_tr
        ttr = list(range(0, a)) + list(range(b, n_tr))
        tte = list(range(a, b))
        if len(ttr) < 50 or len(tte) < 5:
            continue
        df_ttr = df_tr.iloc[ttr].reset_index(drop=True)
        m_inner = train_canonical_model(df_ttr, label, fc=fc, kind=kind)
        oof[tte] = predict_canonical(m_inner, df_tr[fc].iloc[tte].values)
    return test_pred, oof, y_tr


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-32 - honest re-baseline of B14 in-play models", flush=True)
    print("=" * 70, flush=True)

    merged = load_data_with_linescores()
    print(f"[1] loaded {len(merged)} games (B14 saw 2839)", flush=True)
    merged = build_r12_features(merged)
    merged = add_interactions(merged)
    from src.prediction.r12_canonical_predictor import _all_feature_sets
    feature_sets = _all_feature_sets(merged)
    fc_pregame = feature_sets["interactions_only"]
    print(f"[2] pregame feature cols: {len(fc_pregame)}", flush=True)

    merged["home_wins"] = (merged["score_diff"] > 0).astype(int)
    live_metrics = {}

    # In-play winprob at each snap_q
    for snap_q in [1, 2, 3]:
        print(f"\n[inplay_winprob_endQ{snap_q}] honest 4-fold WF + Platt ...", flush=True)
        t_v = time.time()
        snap_merged = add_snapshot_features(merged, snap_q)
        snap_merged[SNAP_FEATURES] = snap_merged[SNAP_FEATURES].fillna(0.0)
        fc_full = fc_pregame + SNAP_FEATURES
        snap_merged[fc_full] = snap_merged[fc_full].fillna(0.0)
        y_all = snap_merged["home_wins"].astype(int).values
        n = len(snap_merged)
        naive_wp = naive_winprob_from_margin(snap_merged["cum_score_diff"].values, 4 - snap_q)
        raw_preds_pool = []; cal_preds_pool = []; y_pool = []; naive_pool = []
        for fi, tr, ti in _wf_indices(n, 4):
            if len(tr) < 250 or len(ti) < 20:
                continue
            test_pred, oof_l2, y_tr = _oof_stack_with_inner_oof(
                snap_merged, fc_full, "home_wins", "bin", tr, ti)
            cal_pred = _platt_calibrate(oof_l2, y_tr, test_pred)
            raw_preds_pool.append(test_pred); cal_preds_pool.append(cal_pred)
            y_pool.append(y_all[ti]); naive_pool.append(naive_wp[ti])
        aa = np.concatenate(y_pool)
        raw = np.concatenate(raw_preds_pool); cal = np.concatenate(cal_preds_pool)
        nv = np.concatenate(naive_pool)
        from sklearn.metrics import brier_score_loss, roc_auc_score
        live_raw_brier = float(brier_score_loss(aa, raw))
        live_cal_brier = float(brier_score_loss(aa, cal))
        live_raw_auc = float(roc_auc_score(aa, raw))
        live_cal_auc = float(roc_auc_score(aa, cal))
        naive_brier = float(brier_score_loss(aa, nv))
        frozen = B14_FROZEN[("home_wins", snap_q)]
        drift_brier = live_cal_brier - frozen["brier"]
        drift_auc = live_cal_auc - frozen["auc"]
        out = {"target": "home_wins", "snap_q": snap_q,
               "n_games": int(n), "n_folds": len(raw_preds_pool),
               "live_raw_brier": round(live_raw_brier, 5),
               "live_cal_brier": round(live_cal_brier, 5),
               "live_raw_auc": round(live_raw_auc, 5),
               "live_cal_auc": round(live_cal_auc, 5),
               "naive_brier": round(naive_brier, 5),
               "frozen_brier": frozen["brier"], "frozen_auc": frozen["auc"],
               "drift_brier": round(drift_brier, 5),
               "drift_auc": round(drift_auc, 5),
               "elapsed_s": round(time.time() - t_v, 1)}
        live_metrics[f"home_wins_endQ{snap_q}"] = out
        outp = os.path.join(DATA_CACHE, f"probe_R12_B32_recal_winprob_endQ{snap_q}.json")
        with open(outp, "w") as f:
            json.dump(out, f, indent=2)
        print(f"  LIVE raw Brier {live_raw_brier:.4f} -> Platt {live_cal_brier:.4f} "
              f"(frozen {frozen['brier']:.4f}, drift {drift_brier:+.5f})", flush=True)
        print(f"  LIVE raw AUC {live_raw_auc:.4f} -> Platt {live_cal_auc:.4f} "
              f"(frozen {frozen['auc']:.4f}, drift {drift_auc:+.5f}) [{out['elapsed_s']}s]",
              flush=True)

    # remaining_total at endQ2
    print(f"\n[remaining_total_endQ2] honest 4-fold WF + isotonic ...", flush=True)
    t_v = time.time()
    snap_q = 2
    snap_merged = add_snapshot_features(merged, snap_q)
    snap_merged[SNAP_FEATURES] = snap_merged[SNAP_FEATURES].fillna(0.0)
    snap_merged["remaining_total"] = snap_merged["total_pts_box"] - snap_merged["cum_total"]
    fc_full = fc_pregame + SNAP_FEATURES
    snap_merged[fc_full] = snap_merged[fc_full].fillna(0.0)
    n = len(snap_merged)
    y_all = snap_merged["remaining_total"].astype(float).values
    naive_rt = naive_remaining_total(snap_merged["cum_total"].values, snap_q)
    raw_pool = []; cal_pool = []; y_pool = []; naive_pool = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        test_pred, oof_l2, y_tr = _oof_stack_with_inner_oof(
            snap_merged, fc_full, "remaining_total", "reg", tr, ti)
        cal_pred = _isotonic_calibrate(oof_l2, y_tr, test_pred)
        raw_pool.append(test_pred); cal_pool.append(cal_pred)
        y_pool.append(y_all[ti]); naive_pool.append(naive_rt[ti])
    aa = np.concatenate(y_pool); raw = np.concatenate(raw_pool); cal = np.concatenate(cal_pool)
    nv = np.concatenate(naive_pool)
    live_raw_mae = float(np.mean(np.abs(raw - aa)))
    live_cal_mae = float(np.mean(np.abs(cal - aa)))
    naive_mae = float(np.mean(np.abs(nv - aa)))
    live_raw_dp = (live_raw_mae - naive_mae) / naive_mae * 100.0
    live_cal_dp = (live_cal_mae - naive_mae) / naive_mae * 100.0
    frozen = B14_FROZEN[("remaining_total", 2)]
    drift_dp = live_cal_dp - frozen["pooled_delta_pct"]
    out = {"target": "remaining_total", "snap_q": 2, "n_games": int(n),
           "n_folds": len(raw_pool),
           "live_raw_mae": round(live_raw_mae, 4),
           "live_cal_mae": round(live_cal_mae, 4),
           "naive_mae": round(naive_mae, 4),
           "live_raw_delta_pct": round(live_raw_dp, 2),
           "live_cal_delta_pct": round(live_cal_dp, 2),
           "frozen_delta_pct": frozen["pooled_delta_pct"],
           "drift_pp": round(drift_dp, 2),
           "elapsed_s": round(time.time() - t_v, 1)}
    live_metrics["remaining_total_endQ2"] = out
    outp = os.path.join(DATA_CACHE, "probe_R12_B32_recal_remaining_total_endQ2.json")
    with open(outp, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  LIVE raw delta {live_raw_dp:+.2f}% -> isotonic {live_cal_dp:+.2f}% "
          f"(frozen {frozen['pooled_delta_pct']:+.2f}%, drift {drift_dp:+.2f}pp) "
          f"[{out['elapsed_s']}s]", flush=True)

    summary_path = os.path.join(DATA_CACHE, "probe_R12_B32_live_inplay_summary.json")
    with open(summary_path, "w") as f:
        json.dump({"dataset_size": len(merged), "reference_size": 2839,
                   "drift_games": len(merged) - 2839,
                   "live_metrics": live_metrics}, f, indent=2)
    print(f"\n[done] in-play re-baseline complete in {time.time()-t0:.1f}s", flush=True)
    print(f"  summary: {summary_path}", flush=True)


if __name__ == "__main__":
    main()
