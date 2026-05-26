"""probe_R12_batch26_serialize_ensembles.py - serialize ensemble + away_score winner.

For AH3 (B25 confirmed top4_avg wins): train all 4 component models on full
data, save r12_AH3_canonical_top4_avg.joblib with blend recipe.

For away_score (B25 showed nnls_top3 regressed live -13.47%): probe BOTH
single-model interactions_only AND nnls_top3 ensemble on full dataset; pick
the one with lower MAE on the last-200-game held-out tail; save winner.

Bundle format (ensemble):
  {
    "models": [list of {l1_full, l2_lgb, l2_xgb}],
    "feature_columns_per_model": [list of fc lists],
    "recipe": {"type": "equal_weight_avg" | "single" | "nnls", "components": [...]},
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
    build_r12_features, _all_feature_sets,
    train_canonical_model, predict_canonical,
)

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_b5)
load_data = _b5.load_data


def predict_ensemble(bundle, X_per_model):
    """Apply ensemble bundle to per-model X matrices.
    X_per_model: list of np.ndarray, one per component model.
    Recipe types: 'equal_weight_avg', 'nnls' (with weights), 'single'.
    """
    recipe = bundle["recipe"]
    preds = []
    for i, model in enumerate(bundle["models"]):
        preds.append(predict_canonical(model, X_per_model[i]))
    P = np.column_stack(preds)
    if recipe["type"] == "equal_weight_avg":
        return P.mean(axis=1)
    elif recipe["type"] == "nnls":
        w = np.asarray(recipe["weights"])
        return P @ w
    elif recipe["type"] == "single":
        return preds[0]
    raise ValueError(recipe["type"])


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-26 - serialize ensemble canonicals (AH3 + away_score)", flush=True)
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

    n_pass = 0
    summary_entries = []

    # ----- AH3 ensemble: train all 4 components on full data -----
    print(f"\n[AH3 top4_avg] training 4 component models ...", flush=True)
    t_v = time.time()
    AH3_FCS = ["intersection", "opp_pts_pace", "opp_full", "all_b9"]
    AH3_models = []
    AH3_fcs_used = []
    for fc_name in AH3_FCS:
        fc = feature_sets[fc_name]
        model = train_canonical_model(merged, "home_cover_AH3", fc=fc, kind="bin")
        AH3_models.append(model)
        AH3_fcs_used.append(fc)
        print(f"  trained AH3 component: {fc_name} ({len(fc)} feats)", flush=True)

    AH3_bundle = {
        "models": AH3_models,
        "feature_columns_per_model": AH3_fcs_used,
        "recipe": {"type": "equal_weight_avg", "components": AH3_FCS,
                   "target": "home_cover_AH3", "kind": "bin"},
        "training_meta": {
            "n_train_games": len(merged),
            "training_date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_probe": "R12_B25 LIVE Brier 0.2221 AUC 0.7182",
            "module_version": "r12_canonical_predictor v1 (B20) + B26 ensemble",
        },
    }
    AH3_path = os.path.join(MODELS_DIR, "r12_AH3_canonical_top4_avg.joblib")
    joblib.dump(AH3_bundle, AH3_path)
    bundle_size = os.path.getsize(AH3_path) / 1024.0
    print(f"  saved -> {AH3_path} ({bundle_size:.1f} KB)", flush=True)

    # Smoke verify
    reloaded = joblib.load(AH3_path)
    df_te = merged.iloc[-50:].reset_index(drop=True)
    X_per_model = []
    for fc in reloaded["feature_columns_per_model"]:
        df_te[fc] = df_te[fc].fillna(0.0)
        X_per_model.append(df_te[fc].values)
    try:
        preds = predict_ensemble(reloaded, X_per_model)
        assert len(preds) == 50 and np.isfinite(preds).all()
        n_pass += 1
        ah3_pass = True
        print(f"  smoke PASS - 50 preds, mean prob {preds.mean():.3f} "
              f"range [{preds.min():.3f}, {preds.max():.3f}]", flush=True)
    except Exception as e:
        ah3_pass = False
        print(f"  smoke FAIL - {type(e).__name__}: {e}", flush=True)
    summary_entries.append({"target": "home_cover_AH3", "path": AH3_path,
                            "recipe": "equal_weight_avg of 4 components",
                            "n_train": len(merged), "smoke_pass": ah3_pass,
                            "elapsed_s": round(time.time() - t_v, 1)})

    # ----- away_score: pick winner between single-model and ensemble -----
    print(f"\n[away_score] picking winner via tail-200 holdout MAE ...", flush=True)
    t_w = time.time()
    tail = 200
    df_tr = merged.iloc[:-tail].reset_index(drop=True)
    df_te = merged.iloc[-tail:].reset_index(drop=True)
    for fc in feature_sets.values():
        df_tr[fc] = df_tr[fc].fillna(0.0)
        df_te[fc] = df_te[fc].fillna(0.0)
    y_te = df_te["away_score"].astype(float).values

    # Single-model: interactions_only
    fc_single = feature_sets["interactions_only"]
    m_single = train_canonical_model(df_tr, "away_score", fc=fc_single, kind="reg")
    pred_single = predict_canonical(m_single, df_te[fc_single].values)
    mae_single = float(np.mean(np.abs(pred_single - y_te)))
    print(f"  single-model interactions_only ({len(fc_single)} feats): tail MAE {mae_single:.4f}",
          flush=True)

    # Ensemble: nnls_top3 (halflife2_only + all_b9 + interactions_only)
    AWAY_FCS = ["halflife2_only", "all_b9", "interactions_only"]
    away_models = []; away_fcs_used = []
    inner_preds = []
    inner_oofs = []
    # Train each component on full df_tr; also generate inner OOF for NNLS fitting
    n_tr = len(df_tr); inner_k = 3; inner_fs = n_tr // inner_k
    for fc_name in AWAY_FCS:
        fc = feature_sets[fc_name]
        m = train_canonical_model(df_tr, "away_score", fc=fc, kind="reg")
        away_models.append(m); away_fcs_used.append(fc)
        # Inner OOF on df_tr (3-fold) for NNLS weight fitting
        oof = np.zeros(n_tr)
        y_tr_arr = df_tr["away_score"].astype(float).values
        for ki in range(inner_k):
            a = ki * inner_fs; b = (ki + 1) * inner_fs if ki < inner_k - 1 else n_tr
            itr = list(range(0, a)) + list(range(b, n_tr))
            iti = list(range(a, b))
            if len(itr) < 50 or len(iti) < 5:
                continue
            m_inner = train_canonical_model(df_tr.iloc[itr].reset_index(drop=True),
                                              "away_score", fc=fc, kind="reg")
            oof[iti] = predict_canonical(m_inner, df_tr[fc].iloc[iti].values)
        inner_oofs.append(oof)
        # Test predictions on df_te
        inner_preds.append(predict_canonical(m, df_te[fc].values))
    P_te = np.column_stack(inner_preds); O_tr = np.column_stack(inner_oofs)
    y_tr_arr = df_tr["away_score"].astype(float).values
    from scipy.optimize import nnls
    w, _ = nnls(O_tr, y_tr_arr)
    s = w.sum(); w = w / s if s > 0 else np.full(3, 1.0/3)
    pred_ensemble = P_te @ w
    mae_ensemble = float(np.mean(np.abs(pred_ensemble - y_te)))
    print(f"  nnls_top3 ensemble: weights={[round(x,3) for x in w]} tail MAE {mae_ensemble:.4f}",
          flush=True)

    # Winner
    if mae_single < mae_ensemble:
        winner_bundle = {
            "models": [m_single], "feature_columns_per_model": [fc_single],
            "recipe": {"type": "single", "components": ["interactions_only"],
                       "target": "away_score", "kind": "reg",
                       "selected_via": f"tail-{tail} MAE: single {mae_single:.4f} < ensemble {mae_ensemble:.4f}"},
            "training_meta": {
                "n_train_games": len(df_tr),
                "training_date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_probe": "R12_B26 winner via tail-holdout selection",
                "module_version": "r12_canonical_predictor v1 + B26 ensemble",
            },
        }
        winner_kind = "single-model interactions_only"
    else:
        winner_bundle = {
            "models": away_models, "feature_columns_per_model": away_fcs_used,
            "recipe": {"type": "nnls", "components": AWAY_FCS, "weights": w.tolist(),
                       "target": "away_score", "kind": "reg",
                       "selected_via": f"tail-{tail} MAE: ensemble {mae_ensemble:.4f} <= single {mae_single:.4f}"},
            "training_meta": {
                "n_train_games": len(df_tr),
                "training_date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_probe": "R12_B26 winner via tail-holdout selection",
                "module_version": "r12_canonical_predictor v1 + B26 ensemble",
            },
        }
        winner_kind = "nnls_top3 ensemble"

    # Retrain winner on FULL data before saving
    print(f"  winner: {winner_kind}; retraining on full {len(merged)} games ...", flush=True)
    if winner_bundle["recipe"]["type"] == "single":
        full_model = train_canonical_model(merged, "away_score", fc=fc_single, kind="reg")
        winner_bundle["models"] = [full_model]
    else:
        full_models = []
        for fc_name in AWAY_FCS:
            fc = feature_sets[fc_name]
            full_models.append(train_canonical_model(merged, "away_score", fc=fc, kind="reg"))
        winner_bundle["models"] = full_models
    winner_bundle["training_meta"]["n_train_games"] = len(merged)

    away_path = os.path.join(MODELS_DIR, "r12_away_score_canonical.joblib")
    joblib.dump(winner_bundle, away_path)
    bundle_size = os.path.getsize(away_path) / 1024.0
    print(f"  saved -> {away_path} ({bundle_size:.1f} KB)", flush=True)

    reloaded = joblib.load(away_path)
    df_te2 = merged.iloc[-50:].reset_index(drop=True)
    X_per_model = []
    for fc in reloaded["feature_columns_per_model"]:
        df_te2[fc] = df_te2[fc].fillna(0.0)
        X_per_model.append(df_te2[fc].values)
    try:
        preds2 = predict_ensemble(reloaded, X_per_model)
        assert len(preds2) == 50 and np.isfinite(preds2).all()
        n_pass += 1
        away_pass = True
        print(f"  smoke PASS - 50 preds, mean {preds2.mean():.3f} "
              f"range [{preds2.min():.3f}, {preds2.max():.3f}]", flush=True)
    except Exception as e:
        away_pass = False
        print(f"  smoke FAIL - {type(e).__name__}: {e}", flush=True)

    summary_entries.append({"target": "away_score", "path": away_path,
                            "recipe": winner_kind,
                            "tail_mae_single": round(mae_single, 4),
                            "tail_mae_ensemble": round(mae_ensemble, 4),
                            "n_train": len(merged), "smoke_pass": away_pass,
                            "elapsed_s": round(time.time() - t_w, 1)})

    summary_path = os.path.join(DATA_CACHE, "probe_R12_B26_ensemble_serialize_summary.json")
    with open(summary_path, "w") as f:
        json.dump({"n_serialized": 2, "n_smoke_pass": n_pass,
                   "entries": summary_entries, "models_dir": MODELS_DIR}, f, indent=2)

    print(f"\n[done] {n_pass}/2 smoke PASS in {time.time()-t0:.1f}s", flush=True)
    print(f"  summary: {summary_path}", flush=True)


if __name__ == "__main__":
    main()
