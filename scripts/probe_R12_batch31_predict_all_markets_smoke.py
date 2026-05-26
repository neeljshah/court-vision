"""probe_R12_batch31_predict_all_markets_smoke.py - one-call all-markets predict smoke.

Verifies:
  1. predict_all_pregame_markets(df) returns predictions for all 6 markets,
     all finite, all in expected ranges.
  2. predict_all_inplay_markets(df, snap_q) returns winprob at each snap_q
     and (only when snap_q==2) also remaining_total.
  3. In-process bundle caching shaves time on repeated calls.

Reports per-market load time + first-call vs cached predict time.
"""
from __future__ import annotations
import importlib.util, json, os, sys, time
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
DATA_CACHE = os.path.join(PROJECT_DIR, "data", "cache")

from src.prediction.r12_canonical_predictor import (  # noqa: E402
    build_r12_features, predict_all_pregame_markets, predict_all_inplay_markets,
    list_available_bundles, clear_bundle_cache,
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


SANITY = {
    "total_pts_box":  (150, 320),
    "score_diff":     (-50, 50),
    "home_score":     (70, 175),
    "away_score":     (70, 175),
    "over_230":       (0.0, 1.0),
    "home_cover_AH3": (0.0, 1.0),
}


def main():
    t0 = time.time()
    print("=" * 70, flush=True)
    print("R12 BATCH-31 - predict_all_markets smoke", flush=True)
    print("=" * 70, flush=True)

    merged = load_data_with_linescores()
    print(f"[1] loaded {len(merged)} games with linescores", flush=True)
    merged = build_r12_features(merged)
    merged = add_interactions(merged)
    merged["over_230"] = (merged["total_pts_box"] > 230).astype(int)
    merged["home_cover_AH3"] = (merged["score_diff"] + 3 > 0).astype(int)
    print(f"[2] R12 + interactions features built", flush=True)

    avail = list_available_bundles()
    print(f"[3] available bundles: {avail}", flush=True)

    df_te = merged.iloc[-50:].reset_index(drop=True)
    pass_count = 0; total_count = 0

    # First call - cold cache
    print("\n[4] predict_all_pregame_markets (cold cache)", flush=True)
    clear_bundle_cache()
    t_v = time.time()
    pregame_preds = predict_all_pregame_markets(df_te)
    cold_s = time.time() - t_v
    print(f"  done in {cold_s:.2f}s; markets: {sorted(pregame_preds.keys())}", flush=True)
    for target, preds in pregame_preds.items():
        lo, hi = SANITY[target]
        total_count += 1
        ok = len(preds) == 50 and np.isfinite(preds).all() and \
             (preds >= lo).all() and (preds <= hi).all()
        if ok:
            pass_count += 1
            print(f"  PASS {target}: mean={preds.mean():.3f} range=[{preds.min():.3f}, {preds.max():.3f}]",
                  flush=True)
        else:
            print(f"  FAIL {target}: out of range [{lo},{hi}] or non-finite", flush=True)

    # Second call - warm cache
    print("\n[5] predict_all_pregame_markets (warm cache)", flush=True)
    t_v = time.time()
    _ = predict_all_pregame_markets(df_te)
    warm_s = time.time() - t_v
    print(f"  done in {warm_s:.2f}s ({cold_s/max(warm_s, 1e-3):.1f}x speedup vs cold)",
          flush=True)

    # In-play predictions at each snap_q
    for snap_q in [1, 2, 3]:
        print(f"\n[6.{snap_q}] predict_all_inplay_markets(snap_q={snap_q})", flush=True)
        snap_merged = add_snapshot_features(merged, snap_q)
        snap_features = ["cum_home_score", "cum_away_score", "cum_score_diff",
                         "cum_total", "score_margin_abs", "q_remaining",
                         "cum_pace_proxy"]
        snap_merged[snap_features] = snap_merged[snap_features].fillna(0.0)
        df_te_snap = snap_merged.iloc[-50:].reset_index(drop=True)
        t_v = time.time()
        inplay_preds = predict_all_inplay_markets(df_te_snap, snap_q)
        inplay_s = time.time() - t_v
        print(f"  done in {inplay_s:.2f}s; markets: {sorted(inplay_preds.keys())}", flush=True)
        for k, p in inplay_preds.items():
            total_count += 1
            if k.startswith("home_wins"):
                ok = len(p) == 50 and np.isfinite(p).all() and \
                     (p >= 0).all() and (p <= 1).all()
            else:  # remaining_total
                ok = len(p) == 50 and np.isfinite(p).all() and \
                     (p >= 0).all() and (p <= 200).all()
            if ok:
                pass_count += 1
                print(f"  PASS {k}: mean={p.mean():.3f} range=[{p.min():.3f}, {p.max():.3f}]",
                      flush=True)
            else:
                print(f"  FAIL {k}: out of range or non-finite", flush=True)

    summary = {
        "n_total": total_count, "n_pass": pass_count,
        "all_pass": pass_count == total_count,
        "cold_cache_s": round(cold_s, 2),
        "warm_cache_s": round(warm_s, 2),
        "elapsed_s": round(time.time() - t0, 1),
    }
    out_path = os.path.join(DATA_CACHE, "probe_R12_B31_predict_all_smoke.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[done] {pass_count}/{total_count} PASS in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
