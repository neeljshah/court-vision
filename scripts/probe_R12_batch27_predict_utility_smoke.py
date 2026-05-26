"""probe_R12_batch27_predict_utility_smoke.py - smoke-verify load+predict utility.

For each of the 6 canonical bundles, exercise the new production-module utility:
  bundle = load_canonical_bundle(target)
  preds = predict_canonical_bundle(bundle, df_last_50)

Records load time, predict time, prediction sanity (finite + in expected range).
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.r12_canonical_predictor import (  # noqa: E402
    build_r12_features, load_canonical_bundle, predict_canonical_bundle,
)

import importlib.util
_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_b5)
load_data = _b5.load_data


# Per-target sanity ranges (rough bounds for finite NBA values)
SANITY = {
    "total_pts_box":  {"min": 150, "max": 320, "kind": "reg"},
    "score_diff":     {"min": -50, "max": 50,  "kind": "reg"},
    "home_score":     {"min": 70,  "max": 175, "kind": "reg"},
    "away_score":     {"min": 70,  "max": 175, "kind": "reg"},
    "over_230":       {"min": 0.0, "max": 1.0, "kind": "bin"},
    "home_cover_AH3": {"min": 0.0, "max": 1.0, "kind": "bin"},
}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-27 - load_canonical_bundle + predict_canonical_bundle smoke", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = build_r12_features(merged)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)
    df_te = merged.iloc[-50:].reset_index(drop=True)
    print(f"[2] R12 features built; predict slice = last 50 games", flush=True)

    results = []
    n_pass = 0
    for target, bounds in SANITY.items():
        print(f"\n[{target}] kind={bounds['kind']}", flush=True)
        t_load = time.time()
        try:
            bundle = load_canonical_bundle(target)
        except (FileNotFoundError, KeyError) as e:
            print(f"  LOAD FAIL: {type(e).__name__}: {e}", flush=True)
            results.append({"target": target, "status": "LOAD_FAIL", "error": str(e)})
            continue
        load_s = time.time() - t_load
        recipe_type = bundle.get("recipe", {}).get("type", "?")
        bundle_shape = "single" if "model" in bundle else ("ensemble" if "models" in bundle else "unknown")
        print(f"  loaded ({load_s*1000:.1f} ms) shape={bundle_shape} recipe_type={recipe_type}",
              flush=True)

        t_pred = time.time()
        try:
            preds = predict_canonical_bundle(bundle, df_te)
            pred_s = time.time() - t_pred
            assert len(preds) == 50, f"expected 50 preds got {len(preds)}"
            assert np.isfinite(preds).all(), "non-finite predictions"
            in_range = (preds >= bounds["min"]).all() and (preds <= bounds["max"]).all()
            assert in_range, f"preds out of range [{bounds['min']}, {bounds['max']}]: " \
                              f"observed [{preds.min():.3f}, {preds.max():.3f}]"
            n_pass += 1
            status = "PASS"
            print(f"  predict PASS ({pred_s*1000:.1f} ms) "
                  f"mean={preds.mean():.4f} range=[{preds.min():.4f}, {preds.max():.4f}]",
                  flush=True)
        except Exception as e:
            pred_s = time.time() - t_pred
            status = "FAIL"
            print(f"  predict FAIL ({pred_s*1000:.1f} ms): {type(e).__name__}: {e}", flush=True)
        results.append({
            "target": target, "status": status, "shape": bundle_shape,
            "recipe_type": recipe_type, "load_ms": round(load_s * 1000, 1),
            "predict_ms": round(pred_s * 1000, 1),
        })

    summary = {"n_targets": len(SANITY), "n_pass": n_pass, "results": results,
               "elapsed_s": round(time.time() - t0, 1)}
    summary_path = os.path.join(DATA_CACHE, "probe_R12_B27_predict_utility_smoke.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[done] {n_pass}/{len(SANITY)} PASS in {time.time()-t0:.1f}s", flush=True)
    print(f"  summary: {summary_path}", flush=True)


if __name__ == "__main__":
    main()
