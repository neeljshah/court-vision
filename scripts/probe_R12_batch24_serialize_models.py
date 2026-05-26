"""probe_R12_batch24_serialize_models.py — joblib serialization of R12 canonicals.

Trains each per-target canonical on the FULL current dataset using
src/prediction/r12_canonical_predictor.py, then saves the trained model bundle
to data/models/m2_family/r12_{target}_canonical.joblib.

Each bundle: {model_dict, feature_columns, recipe_meta, training_meta}.

Verifies end-to-end by reloading each .joblib and predicting on the last
50 games as a smoke check.

Single-model / top50 targets serialized here (4):
  total_pts_box  - full interactions_only set
  score_diff     - top-50 perm_inner_cv (stable trim) of opp_full
  home_score     - full all_b9 set
  over_230       - full opp_full set (B23 showed top50 regresses on this target)

Ensemble targets (away_score nnls_top3, AH3 top4_avg) NOT serialized here.
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
    CANONICAL_RECIPES, get_canonical_feature_set_stable,
)

_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_b5)
load_data = _b5.load_data


SERIALIZE_TARGETS = [
    {"target": "total_pts_box", "kind": "reg", "fc_name": "interactions_only", "trim": None},
    {"target": "score_diff",    "kind": "reg", "fc_name": "opp_full",        "trim": "perm_inner_cv_top50"},
    {"target": "home_score",    "kind": "reg", "fc_name": "all_b9",          "trim": None},
    {"target": "over_230",      "kind": "bin", "fc_name": "opp_full",        "trim": None},
]


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-24 - serialize canonical models to joblib", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = build_r12_features(merged)
    feature_sets = _all_feature_sets(merged)
    print(f"[2] R12 features built; {sum(1 for _ in feature_sets)} feature sets", flush=True)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)

    results = []
    n_smoke_pass = 0
    for spec in SERIALIZE_TARGETS:
        target = spec["target"]; kind = spec["kind"]
        fc_name = spec["fc_name"]; trim = spec["trim"]
        t_v = time.time()
        print(f"\n[{target}] kind={kind} fc={fc_name} trim={trim}", flush=True)

        df_train = merged.copy()
        df_train[feature_sets[fc_name]] = df_train[feature_sets[fc_name]].fillna(0.0)
        if trim == "perm_inner_cv_top50":
            fc = get_canonical_feature_set_stable(target, df_train, feature_sets, top_k=50)
        else:
            fc = feature_sets[fc_name]
        print(f"  trained feature count: {len(fc)}", flush=True)

        model = train_canonical_model(df_train, target, fc=fc, kind=kind)

        bundle = {
            "model": model,
            "feature_columns": fc,
            "recipe": {
                "target": target, "kind": kind, "fc_name": fc_name, "trim": trim,
                "source_probe": ("R12_B22 perm_inner_cv (score_diff)" if trim
                                 else "R12_B21 LIVE (full feature set)"),
            },
            "training_meta": {
                "n_train_games": len(df_train),
                "training_date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "module_version": "r12_canonical_predictor v1 (B20)",
            },
        }

        out_path = os.path.join(MODELS_DIR, f"r12_{target}_canonical.joblib")
        joblib.dump(bundle, out_path)
        bundle_size = os.path.getsize(out_path) / 1024.0
        print(f"  saved -> {out_path} ({bundle_size:.1f} KB)", flush=True)

        reloaded = joblib.load(out_path)
        df_te = merged.iloc[-50:].reset_index(drop=True)
        df_te[reloaded["feature_columns"]] = df_te[reloaded["feature_columns"]].fillna(0.0)
        X_te = df_te[reloaded["feature_columns"]].values
        try:
            preds = predict_canonical(reloaded["model"], X_te)
            assert len(preds) == 50, f"expected 50 preds, got {len(preds)}"
            assert np.isfinite(preds).all(), "non-finite predictions"
            smoke_pass = True
            n_smoke_pass += 1
            print(f"  smoke PASS - predicted 50 games; mean={preds.mean():.3f} "
                  f"range=[{preds.min():.3f}, {preds.max():.3f}]", flush=True)
        except Exception as e:
            smoke_pass = False
            print(f"  smoke FAIL - {type(e).__name__}: {e}", flush=True)

        results.append({
            "target": target, "out_path": out_path,
            "n_features": len(fc), "n_train": len(df_train),
            "smoke_pass": smoke_pass,
            "elapsed_s": round(time.time() - t_v, 1),
        })

    summary_path = os.path.join(DATA_CACHE, "probe_R12_B24_serialize_summary.json")
    with open(summary_path, "w") as f:
        json.dump({"n_serialized": len(SERIALIZE_TARGETS),
                   "n_smoke_pass": n_smoke_pass,
                   "results": results,
                   "models_dir": MODELS_DIR}, f, indent=2)

    print(f"\n[done] {n_smoke_pass}/{len(SERIALIZE_TARGETS)} smoke PASS in {time.time()-t0:.1f}s", flush=True)
    print(f"  summary: {summary_path}", flush=True)


if __name__ == "__main__":
    main()
