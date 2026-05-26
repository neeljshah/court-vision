"""probe_R12_batch28_auto_train_smoke.py - verify auto_train fallback path.

Simulates a missing joblib scenario:
  1. Move r12_home_score_canonical.joblib to a temp .bak file.
  2. Call load_canonical_bundle('home_score', auto_train=True, training_df=df).
  3. Verify the function trains + saves + returns a usable bundle.
  4. Reload via plain load_canonical_bundle (no auto_train) to confirm round-trip.
  5. Restore original bundle from .bak.

Also exercises list_available_bundles() before and after the simulated outage.
"""
from __future__ import annotations
import json, os, shutil, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.r12_canonical_predictor import (  # noqa: E402
    build_r12_features, load_canonical_bundle, predict_canonical_bundle,
    list_available_bundles, _MODELS_DIR, _BUNDLE_FILENAMES,
)

import importlib.util
_B5_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "probe_R12_batch5_quality_opp.py")
_spec = importlib.util.spec_from_file_location("probe_R12_batch5_quality_opp", _B5_PATH)
_b5 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_b5)
load_data = _b5.load_data


TARGET = "home_score"


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-28 - auto_train fallback smoke", flush=True)
    print("=" * 70, flush=True)

    merged = load_data()
    print(f"[1] loaded {len(merged)} games", flush=True)
    merged = build_r12_features(merged)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)
    print(f"[2] R12 features built", flush=True)

    bundle_path = os.path.join(_MODELS_DIR, _BUNDLE_FILENAMES[TARGET])
    bak_path = bundle_path + ".bak"

    avail_before = list_available_bundles()
    print(f"[3] list_available_bundles before: {avail_before}", flush=True)

    print(f"\n[4] simulating missing bundle: moving {bundle_path} -> {bak_path}", flush=True)
    if not os.path.isfile(bundle_path):
        print(f"  SKIP: original bundle doesn't exist; cannot simulate outage", flush=True)
        return
    shutil.move(bundle_path, bak_path)

    avail_during = list_available_bundles()
    print(f"  list_available_bundles during outage: {TARGET} = {avail_during[TARGET]}", flush=True)

    # First confirm load_canonical_bundle without auto_train raises FileNotFoundError
    print(f"\n[5] load_canonical_bundle({TARGET!r}) without auto_train (expect FileNotFoundError)",
          flush=True)
    try:
        load_canonical_bundle(TARGET)
        print(f"  UNEXPECTED: no error raised", flush=True)
        no_auto_pass = False
    except FileNotFoundError as e:
        print(f"  CORRECT: FileNotFoundError raised - {str(e)[:80]}...", flush=True)
        no_auto_pass = True

    # Now exercise auto_train=True
    print(f"\n[6] load_canonical_bundle({TARGET!r}, auto_train=True, training_df=merged)", flush=True)
    t_at = time.time()
    try:
        bundle_at = load_canonical_bundle(TARGET, auto_train=True, training_df=merged)
        at_s = time.time() - t_at
        print(f"  auto_train PASS ({at_s:.1f}s) bundle keys: {sorted(bundle_at.keys())}", flush=True)
        auto_train_pass = True
    except Exception as e:
        at_s = time.time() - t_at
        print(f"  auto_train FAIL ({at_s:.1f}s): {type(e).__name__}: {e}", flush=True)
        auto_train_pass = False

    # Verify auto-trained bundle predicts correctly on last 50 games
    print(f"\n[7] predict via auto-trained bundle on last 50 games", flush=True)
    pred_at_pass = False
    if auto_train_pass:
        try:
            df_te = merged.iloc[-50:].reset_index(drop=True)
            preds = predict_canonical_bundle(bundle_at, df_te)
            assert len(preds) == 50 and np.isfinite(preds).all()
            print(f"  predict PASS mean={preds.mean():.3f} range=[{preds.min():.3f}, {preds.max():.3f}]",
                  flush=True)
            pred_at_pass = True
        except Exception as e:
            print(f"  predict FAIL: {type(e).__name__}: {e}", flush=True)

    # Verify the auto-saved bundle reloads cleanly via the plain path
    print(f"\n[8] reload auto-saved bundle without auto_train flag", flush=True)
    reload_pass = False
    if auto_train_pass:
        try:
            bundle_reloaded = load_canonical_bundle(TARGET)
            assert isinstance(bundle_reloaded, dict)
            print(f"  reload PASS keys: {sorted(bundle_reloaded.keys())}", flush=True)
            reload_pass = True
        except Exception as e:
            print(f"  reload FAIL: {type(e).__name__}: {e}", flush=True)

    # Restore original bundle
    print(f"\n[9] restoring original bundle from {bak_path}", flush=True)
    if os.path.isfile(bak_path):
        if os.path.isfile(bundle_path):
            os.remove(bundle_path)  # remove auto-saved version
        shutil.move(bak_path, bundle_path)
        print(f"  restored", flush=True)

    summary = {
        "no_auto_correctly_errors": no_auto_pass,
        "auto_train_succeeded": auto_train_pass,
        "auto_train_seconds": round(at_s, 1),
        "predict_via_auto_trained": pred_at_pass,
        "reload_post_auto_train": reload_pass,
        "elapsed_s": round(time.time() - t0, 1),
    }
    summary["all_pass"] = all([no_auto_pass, auto_train_pass, pred_at_pass, reload_pass])
    out_path = os.path.join(DATA_CACHE, "probe_R12_B28_auto_train_smoke.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[done] all_pass={summary['all_pass']} in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
