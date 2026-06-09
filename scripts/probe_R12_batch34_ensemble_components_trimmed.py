"""probe_R12_batch34_ensemble_components_trimmed.py - leak-free trim INSIDE ensembles.

B25/B26 found:
  - AH3 top4_avg (equal weight): Brier 0.2221 AUC 0.7182 LIVE - stable winner
  - away_score nnls_top3: -13.47% LIVE regressed (NNLS weights swing per fold)

This batch applies B22's perm_inner_cv top-50 trim to EACH COMPONENT before
blending. Hypothesis: trimmed components have less noise -> more stable NNLS
weights -> better away_score; AH3 might also benefit if any of its 4 components
have noise.

Variants:
  - away_trimmed_avg   : 3 perm_inner_cv-trimmed components, equal weight
  - away_trimmed_nnls  : 3 perm_inner_cv-trimmed components, NNLS-weighted
  - AH3_trimmed_avg    : 4 perm_inner_cv-trimmed components, equal weight

Compares to B25/B26 LIVE ensemble numbers.
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
    build_r12_features, _all_feature_sets, train_canonical_model, predict_canonical,
)

# Reuse trim_perm_inner_cv from B22
_B22_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "probe_R12_batch22_stable_feat_select.py")
_spec22 = importlib.util.spec_from_file_location("probe_R12_batch22_stable_feat_select", _B22_PATH)
_b22 = importlib.util.module_from_spec(_spec22); _spec22.loader.exec_module(_b22)
trim_perm_inner_cv = _b22.trim_perm_inner_cv

# Classifier trim from B23
_B23_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "probe_R12_batch23_perm_inner_cv_sweep.py")
_spec23 = importlib.util.spec_from_file_location("probe_R12_batch23_perm_inner_cv_sweep", _B23_PATH)
_b23 = importlib.util.module_from_spec(_spec23); _spec23.loader.exec_module(_b23)
trim_perm_inner_cv_clf = _b23.trim_perm_inner_cv_clf

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_b5)
load_data = _b5.load_data


LIVE_BASELINE = {
    "away_score":     {"pooled_delta_pct": -13.47, "src": "B25 nnls_top3 LIVE"},
    "home_cover_AH3": {"pooled_brier": 0.2221, "pooled_auc": 0.7182, "src": "B25 top4_avg LIVE"},
}


def _wf_indices(n, k):
    fs = n // k
    out = []
    for fi in range(k):
        ts = fi * fs
        te = (fi + 1) * fs if fi < k - 1 else n
        out.append((fi, list(range(0, ts)), list(range(ts, te))))
    return out


def _train_predict_with_inner_oof(df, fc, label, kind, tr, ti):
    """Train canonical on outer-train + inner-3-fold OOF for blender fitting.
    Returns (test_pred, oof_l2_on_outer_train, y_tr)."""
    df_tr = df.iloc[tr].reset_index(drop=True)
    df_tr[fc] = df_tr[fc].fillna(0.0)
    y_all = df[label].astype(int if kind == "bin" else float).values
    y_tr = y_all[tr]
    full_model = train_canonical_model(df_tr, label, fc=fc, kind=kind)
    df_te = df.iloc[ti].reset_index(drop=True)
    df_te[fc] = df_te[fc].fillna(0.0)
    test_pred = predict_canonical(full_model, df_te[fc].values)
    n_tr = len(tr); kk = 3; kf = n_tr // kk
    oof = np.zeros(n_tr)
    for kki in range(kk):
        a = kki * kf; b = (kki + 1) * kf if kki < kk - 1 else n_tr
        ttr = list(range(0, a)) + list(range(b, n_tr))
        tte = list(range(a, b))
        if len(ttr) < 50 or len(tte) < 5:
            continue
        df_ttr = df_tr.iloc[ttr].reset_index(drop=True)
        m = train_canonical_model(df_ttr, label, fc=fc, kind=kind)
        oof[tte] = predict_canonical(m, df_tr[fc].iloc[tte].values)
    return test_pred, oof, y_tr


def _nnls_weights(P_oof, y_tr):
    from scipy.optimize import nnls
    w, _ = nnls(P_oof, y_tr.astype(float))
    s = w.sum()
    return w / s if s > 0 else np.full(P_oof.shape[1], 1.0 / P_oof.shape[1])


def run_trimmed_ensemble(merged, label, kind, fc_names, feature_sets, blend_type):
    """4-fold WF; per outer fold trim each component's feature set leak-free via
    perm_inner_cv top-50; train + blend."""
    y_all = merged[label].astype(int if kind == "bin" else float).values
    n = len(merged)
    folds = []; weights_per_fold = []
    for fi, tr, ti in _wf_indices(n, 4):
        if len(tr) < 250 or len(ti) < 20:
            continue
        df_tr_full = merged.iloc[tr].reset_index(drop=True)
        preds = []; oofs = []
        for fc_name in fc_names:
            fc_full = feature_sets[fc_name]
            df_tr_full[fc_full] = df_tr_full[fc_full].fillna(0.0)
            if kind == "reg":
                fc_trim = trim_perm_inner_cv(df_tr_full, fc_full, label, top_k=50)
            else:
                fc_trim = trim_perm_inner_cv_clf(df_tr_full, fc_full, label, top_k=50)
            test_pred, oof, y_tr = _train_predict_with_inner_oof(
                merged, fc_trim, label, kind, tr, ti)
            preds.append(test_pred); oofs.append(oof)
        P = np.column_stack(preds); O = np.column_stack(oofs)
        y_tr_arr = y_all[tr]
        if blend_type == "nnls":
            w = _nnls_weights(O, y_tr_arr)
        else:
            w = np.full(P.shape[1], 1.0 / P.shape[1])
        y_pred = P @ w
        weights_per_fold.append(w.tolist())
        folds.append({"fold": fi, "y_true": y_all[ti], "y_pred": y_pred})
    return folds, weights_per_fold


def _summarize_reg(folds, name, label, meta):
    if not folds:
        return {"probe": name, "kind": "regression", "label": label,
                "status": "REJECT", "beat_live": False, "variant": meta}
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    naive = pd.Series(aa).shift(1).rolling(5, min_periods=1).mean().fillna(aa.mean()).values
    pn = float(np.mean(np.abs(naive - aa))); pl = float(np.mean(np.abs(al - aa)))
    dp = (pl - pn) / pn * 100.0
    can = LIVE_BASELINE.get(label, {})
    live_dp = can.get("pooled_delta_pct")
    beat = (dp < live_dp) if live_dp is not None else None
    return {"probe": name, "kind": "regression", "label": label,
            "n_folds": len(folds),
            "live_pooled_delta_pct": round(dp, 2),
            "baseline_delta_pct": live_dp,
            "drift_pp": round(dp - live_dp, 2) if live_dp is not None else None,
            "status": "SHIP" if (beat is True) else "REJECT",
            "beat_live": bool(beat) if beat is not None else None,
            "variant": meta}


def _summarize_bin(folds, name, label, desc, n_games, pos_rate, meta):
    from sklearn.metrics import brier_score_loss, roc_auc_score
    if not folds:
        return {"probe": name, "kind": "binary", "label": label,
                "status": "REJECT", "beat_live": False, "variant": meta}
    aa = np.concatenate([f["y_true"] for f in folds])
    al = np.concatenate([f["y_pred"] for f in folds])
    plb = float(brier_score_loss(aa, al))
    try:
        plu = float(roc_auc_score(aa, al))
    except Exception:
        plu = float("nan")
    can = LIVE_BASELINE.get(label, {})
    fb = can.get("pooled_brier"); fa = can.get("pooled_auc")
    beat = (plb < fb) or (plu > fa) if fb is not None else None
    return {"probe": name, "kind": "binary", "label": label, "label_desc": desc,
            "n_games": int(n_games), "pos_rate": float(pos_rate),
            "n_folds": len(folds),
            "live_pooled_brier": round(plb, 5),
            "live_pooled_auc": round(plu, 5),
            "baseline_brier": fb, "baseline_auc": fa,
            "drift_brier": round(plb - fb, 5) if fb else None,
            "drift_auc": round(plu - fa, 5) if fa else None,
            "status": "SHIP" if (beat is True) else "REJECT",
            "beat_live": bool(beat) if beat is not None else None,
            "variant": meta}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-34 - leak-free trim applied to ensemble components", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = build_r12_features(merged)
    feature_sets = _all_feature_sets(merged)
    for fc in feature_sets.values():
        merged[fc] = merged[fc].fillna(0.0)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)
    print(f"[2] R12 features built", flush=True)

    # ----- away_score: trimmed equal_weight + trimmed NNLS -----
    AWAY_FCS = ["halflife2_only", "all_b9", "interactions_only"]
    print(f"\n[away_score] trimmed components equal-weight avg ...", flush=True)
    t_v = time.time()
    folds_a, weights_a = run_trimmed_ensemble(
        merged, "away_score", "reg", AWAY_FCS, feature_sets, "avg")
    out_a = _summarize_reg(folds_a, "R12_B34_away_trimmed_avg", "away_score",
                            {"variant": "trimmed_equal_weight_avg",
                             "components": AWAY_FCS, "trim": "perm_inner_cv_top50"})
    out_a["elapsed_s"] = round(time.time() - t_v, 1)
    print(f"  LIVE delta {out_a['live_pooled_delta_pct']:+.2f}% "
          f"(baseline {out_a['baseline_delta_pct']:+.2f}%, "
          f"drift {out_a['drift_pp']:+.2f}pp) "
          f"{'BEAT_LIVE' if out_a['beat_live'] else '(B25 LIVE wins)'} "
          f"[{out_a['elapsed_s']}s]", flush=True)
    with open(os.path.join(DATA_CACHE, "probe_R12_B34_away_trimmed_avg_results.json"), "w") as f:
        json.dump(out_a, f, indent=2)

    print(f"\n[away_score] trimmed components NNLS-weighted ...", flush=True)
    t_v = time.time()
    folds_b, weights_b = run_trimmed_ensemble(
        merged, "away_score", "reg", AWAY_FCS, feature_sets, "nnls")
    out_b = _summarize_reg(folds_b, "R12_B34_away_trimmed_nnls", "away_score",
                            {"variant": "trimmed_nnls", "components": AWAY_FCS,
                             "trim": "perm_inner_cv_top50",
                             "weights_per_fold": weights_b})
    out_b["elapsed_s"] = round(time.time() - t_v, 1)
    print(f"  LIVE delta {out_b['live_pooled_delta_pct']:+.2f}% "
          f"(baseline {out_b['baseline_delta_pct']:+.2f}%, "
          f"drift {out_b['drift_pp']:+.2f}pp) "
          f"{'BEAT_LIVE' if out_b['beat_live'] else '(B25 LIVE wins)'} "
          f"[{out_b['elapsed_s']}s]", flush=True)
    print(f"  weights per fold: {[[round(x,3) for x in w] for w in weights_b]}", flush=True)
    with open(os.path.join(DATA_CACHE, "probe_R12_B34_away_trimmed_nnls_results.json"), "w") as f:
        json.dump(out_b, f, indent=2)

    # ----- AH3: trimmed equal_weight avg -----
    AH3_FCS = ["intersection", "opp_pts_pace", "opp_full", "all_b9"]
    print(f"\n[home_cover_AH3] trimmed components equal-weight avg ...", flush=True)
    t_v = time.time()
    folds_c, weights_c = run_trimmed_ensemble(
        merged, "home_cover_AH3", "bin", AH3_FCS, feature_sets, "avg")
    out_c = _summarize_bin(folds_c, "R12_B34_AH3_trimmed_avg", "home_cover_AH3",
                            "P(home covers -3)", len(merged),
                            float(merged["home_cover_AH3"].mean()),
                            {"variant": "trimmed_equal_weight_avg",
                             "components": AH3_FCS, "trim": "perm_inner_cv_top50_clf"})
    out_c["elapsed_s"] = round(time.time() - t_v, 1)
    print(f"  LIVE Brier {out_c['live_pooled_brier']:.4f} "
          f"(baseline {out_c['baseline_brier']:.4f}, "
          f"drift {out_c['drift_brier']:+.5f})", flush=True)
    print(f"  LIVE AUC {out_c['live_pooled_auc']:.4f} "
          f"(baseline {out_c['baseline_auc']:.4f}, "
          f"drift {out_c['drift_auc']:+.5f}) "
          f"{'BEAT_LIVE' if out_c['beat_live'] else '(B25 LIVE wins)'} "
          f"[{out_c['elapsed_s']}s]", flush=True)
    with open(os.path.join(DATA_CACHE, "probe_R12_B34_AH3_trimmed_avg_results.json"), "w") as f:
        json.dump(out_c, f, indent=2)

    n_beat = sum(1 for o in [out_a, out_b, out_c] if o.get("beat_live"))
    print(f"\n[done] {n_beat}/3 BEAT_LIVE in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
