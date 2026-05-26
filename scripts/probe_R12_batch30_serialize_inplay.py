"""probe_R12_batch30_serialize_inplay.py - serialize B14 in-play models.

Trains B6 OOF-stack models per quarter snapshot + fits Platt calibrator on
inner-3-fold OOF predictions from outer-train. Saves bundles:

  r12_inplay_winprob_endQ1.joblib   Brier 0.2042 AUC 0.7500 (B14 ref)
  r12_inplay_winprob_endQ2.joblib   Brier 0.1736 AUC 0.8212
  r12_inplay_winprob_endQ3.joblib   Brier 0.1277 AUC 0.9012
  r12_inplay_remaining_total_endQ2.joblib  delta -25.65% (isotonic-calibrated)

Bundle format (in-play):
  {
    "model": {l1_full, l2_lgb, l2_xgb},
    "feature_columns": [...],   # includes 7 snapshot features at the end
    "snap_q": int,
    "calibrator": {"type": "platt", "lr_coef_": [...], "lr_intercept_": float}
                  or {"type": "isotonic", "x": [...], "y": [...]},
    "recipe": {target, kind, snap_q, source_probe},
    "training_meta": {...},
  }
"""
from __future__ import annotations
import importlib.util, json, os, sys, time
from datetime import datetime
import joblib
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models", "m2_family")
os.makedirs(MODELS_DIR, exist_ok=True)

from src.prediction.r12_canonical_predictor import (  # noqa: E402
    build_r12_features, _all_feature_sets, train_canonical_model, predict_canonical,
)

_B10_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "probe_R12_batch10_inplay_winprob.py")
_spec10 = importlib.util.spec_from_file_location("probe_R12_batch10_inplay_winprob", _B10_PATH)
_b10 = importlib.util.module_from_spec(_spec10); _spec10.loader.exec_module(_b10)
load_data_with_linescores = _b10.load_data_with_linescores
add_snapshot_features = _b10.add_snapshot_features

_B9_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch9_rest_travel_halflife2.py")
_spec9 = importlib.util.spec_from_file_location("probe_R12_batch9_rest_travel_halflife2", _B9_PATH)
_b9 = importlib.util.module_from_spec(_spec9); _spec9.loader.exec_module(_b9)
add_interactions = _b9.add_interactions


SNAP_FEATURES = ["cum_home_score", "cum_away_score", "cum_score_diff",
                 "cum_total", "score_margin_abs", "q_remaining", "cum_pace_proxy"]


def _fit_platt_calibrator(df_full, fc, label, kind="bin", inner_k=3):
    """Train Platt sigmoid on inner-CV OOF probs. Returns serializable params."""
    from sklearn.linear_model import LogisticRegression
    n = len(df_full); fs = n // inner_k
    oof = np.zeros(n); y = df_full[label].astype(int).values
    for ki in range(inner_k):
        a = ki * fs; b = (ki + 1) * fs if ki < inner_k - 1 else n
        tr = list(range(0, a)) + list(range(b, n))
        te = list(range(a, b))
        if len(tr) < 50 or len(te) < 5:
            continue
        df_tr_inner = df_full.iloc[tr].reset_index(drop=True)
        m = train_canonical_model(df_tr_inner, label, fc=fc, kind=kind)
        oof[te] = predict_canonical(m, df_full[fc].iloc[te].fillna(0.0).values)
    O = np.clip(oof, 1e-6, 1 - 1e-6).reshape(-1, 1)
    lo = np.log(O / (1 - O))
    lr = LogisticRegression(C=1.0); lr.fit(lo, y)
    return {"type": "platt",
            "lr_coef": float(lr.coef_[0, 0]),
            "lr_intercept": float(lr.intercept_[0])}


def _fit_isotonic_calibrator(df_full, fc, label, inner_k=3):
    """Train isotonic regression on inner-CV OOF preds. Returns serializable knots."""
    from sklearn.isotonic import IsotonicRegression
    n = len(df_full); fs = n // inner_k
    oof = np.zeros(n); y = df_full[label].astype(float).values
    for ki in range(inner_k):
        a = ki * fs; b = (ki + 1) * fs if ki < inner_k - 1 else n
        tr = list(range(0, a)) + list(range(b, n))
        te = list(range(a, b))
        if len(tr) < 50 or len(te) < 5:
            continue
        df_tr_inner = df_full.iloc[tr].reset_index(drop=True)
        m = train_canonical_model(df_tr_inner, label, fc=fc, kind="reg")
        oof[te] = predict_canonical(m, df_full[fc].iloc[te].fillna(0.0).values)
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(oof, y)
    return {"type": "isotonic",
            "x": iso.X_thresholds_.tolist(),
            "y": iso.y_thresholds_.tolist()}


def apply_calibrator(raw, calibrator):
    if calibrator["type"] == "platt":
        R = np.clip(raw, 1e-6, 1 - 1e-6)
        lo = np.log(R / (1 - R))
        z = calibrator["lr_coef"] * lo + calibrator["lr_intercept"]
        return 1.0 / (1.0 + np.exp(-z))
    elif calibrator["type"] == "isotonic":
        x = np.asarray(calibrator["x"]); y = np.asarray(calibrator["y"])
        return np.interp(np.asarray(raw), x, y)
    raise ValueError(calibrator["type"])


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-30 - serialize in-play models (B14)", flush=True)
    print("=" * 70, flush=True)

    merged = load_data_with_linescores()
    print(f"[1] loaded {len(merged)} games with linescores", flush=True)
    merged = build_r12_features(merged)
    merged = add_interactions(merged)
    feature_sets = _all_feature_sets(merged)
    fc_pregame = feature_sets["interactions_only"]
    print(f"[2] pregame feature cols: {len(fc_pregame)}", flush=True)

    merged["home_wins"] = (merged["score_diff"] > 0).astype(int)

    n_pass = 0; n_total = 0; summary = []

    # In-play winprob at endQ1/Q2/Q3
    for snap_q in [1, 2, 3]:
        print(f"\n[inplay_winprob_endQ{snap_q}] training + Platt calibrator ...", flush=True)
        t_v = time.time()
        snap_merged = add_snapshot_features(merged, snap_q)
        snap_merged[SNAP_FEATURES] = snap_merged[SNAP_FEATURES].fillna(0.0)
        fc_full = fc_pregame + SNAP_FEATURES
        snap_merged[fc_full] = snap_merged[fc_full].fillna(0.0)
        model = train_canonical_model(snap_merged, "home_wins", fc=fc_full, kind="bin")
        calibrator = _fit_platt_calibrator(snap_merged, fc_full, "home_wins", "bin")
        bundle = {
            "model": model, "feature_columns": fc_full, "snap_q": snap_q,
            "calibrator": calibrator,
            "recipe": {"target": "home_wins", "kind": "bin", "snap_q": snap_q,
                       "calibrator_type": "platt",
                       "source_probe": "R12_B14 Platt-calibrated"},
            "training_meta": {
                "n_train_games": len(snap_merged),
                "training_date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "module_version": "r12_canonical_predictor v2 + B30 inplay",
            },
        }
        out_path = os.path.join(MODELS_DIR, f"r12_inplay_winprob_endQ{snap_q}.joblib")
        joblib.dump(bundle, out_path)
        bundle_size = os.path.getsize(out_path) / 1024.0
        print(f"  saved -> {out_path} ({bundle_size:.1f} KB)", flush=True)

        # Smoke: reload + predict on last 50 games
        reloaded = joblib.load(out_path)
        df_te = snap_merged.iloc[-50:].reset_index(drop=True)
        df_te[reloaded["feature_columns"]] = df_te[reloaded["feature_columns"]].fillna(0.0)
        X_te = df_te[reloaded["feature_columns"]].values
        try:
            raw = predict_canonical(reloaded["model"], X_te)
            cal = apply_calibrator(raw, reloaded["calibrator"])
            assert len(cal) == 50 and np.isfinite(cal).all()
            assert (cal >= 0).all() and (cal <= 1).all()
            n_pass += 1; smoke_pass = True
            print(f"  smoke PASS - raw mean {raw.mean():.3f}, calibrated mean {cal.mean():.3f}, "
                  f"range [{cal.min():.3f}, {cal.max():.3f}]", flush=True)
        except Exception as e:
            smoke_pass = False
            print(f"  smoke FAIL - {type(e).__name__}: {e}", flush=True)
        n_total += 1
        summary.append({"target": f"home_wins_endQ{snap_q}", "path": out_path,
                         "calibrator": "platt", "n_train": len(snap_merged),
                         "smoke_pass": smoke_pass, "elapsed_s": round(time.time() - t_v, 1)})

    # remaining_total at endQ2 with isotonic calibrator
    print(f"\n[inplay_remaining_total_endQ2] training + isotonic calibrator ...", flush=True)
    t_v = time.time()
    snap_q = 2
    snap_merged = add_snapshot_features(merged, snap_q)
    snap_merged[SNAP_FEATURES] = snap_merged[SNAP_FEATURES].fillna(0.0)
    snap_merged["remaining_total"] = snap_merged["total_pts_box"] - snap_merged["cum_total"]
    fc_full = fc_pregame + SNAP_FEATURES
    snap_merged[fc_full] = snap_merged[fc_full].fillna(0.0)
    model = train_canonical_model(snap_merged, "remaining_total", fc=fc_full, kind="reg")
    calibrator = _fit_isotonic_calibrator(snap_merged, fc_full, "remaining_total")
    bundle = {
        "model": model, "feature_columns": fc_full, "snap_q": snap_q,
        "calibrator": calibrator,
        "recipe": {"target": "remaining_total", "kind": "reg", "snap_q": snap_q,
                   "calibrator_type": "isotonic",
                   "source_probe": "R12_B14 isotonic-calibrated"},
        "training_meta": {
            "n_train_games": len(snap_merged),
            "training_date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "module_version": "r12_canonical_predictor v2 + B30 inplay",
        },
    }
    out_path = os.path.join(MODELS_DIR, "r12_inplay_remaining_total_endQ2.joblib")
    joblib.dump(bundle, out_path)
    bundle_size = os.path.getsize(out_path) / 1024.0
    print(f"  saved -> {out_path} ({bundle_size:.1f} KB)", flush=True)

    reloaded = joblib.load(out_path)
    df_te = snap_merged.iloc[-50:].reset_index(drop=True)
    df_te[reloaded["feature_columns"]] = df_te[reloaded["feature_columns"]].fillna(0.0)
    X_te = df_te[reloaded["feature_columns"]].values
    try:
        raw = predict_canonical(reloaded["model"], X_te)
        cal = apply_calibrator(raw, reloaded["calibrator"])
        assert len(cal) == 50 and np.isfinite(cal).all()
        n_pass += 1; smoke_pass = True
        print(f"  smoke PASS - raw mean {raw.mean():.3f}, calibrated mean {cal.mean():.3f}, "
              f"range [{cal.min():.3f}, {cal.max():.3f}]", flush=True)
    except Exception as e:
        smoke_pass = False
        print(f"  smoke FAIL - {type(e).__name__}: {e}", flush=True)
    n_total += 1
    summary.append({"target": "remaining_total_endQ2", "path": out_path,
                     "calibrator": "isotonic", "n_train": len(snap_merged),
                     "smoke_pass": smoke_pass, "elapsed_s": round(time.time() - t_v, 1)})

    summary_path = os.path.join(DATA_CACHE, "probe_R12_B30_inplay_serialize_summary.json")
    with open(summary_path, "w") as f:
        json.dump({"n_total": n_total, "n_pass": n_pass, "results": summary,
                   "models_dir": MODELS_DIR}, f, indent=2)

    print(f"\n[done] {n_pass}/{n_total} smoke PASS in {time.time()-t0:.1f}s", flush=True)
    print(f"  summary: {summary_path}", flush=True)


if __name__ == "__main__":
    main()
