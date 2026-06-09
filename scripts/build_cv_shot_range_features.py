"""build_cv_shot_range_features.py — INT-121: Rolling l5/l10 shot-range sidecar.

Reads cv_shot_range_per_game.parquet and computes strict-as-of (game_date < target)
rolling l5 + l10 per-(player_id, game_date) features for the prop_pergame sidecar.

Features per window:
  shot_range_mean_l{w}, shot_range_p75_l{w},
  shot_range_short_rate_l{w}, shot_range_long_rate_l{w}
Diagnostic:
  shot_range_n_shots_l5

G1 coverage gate, G2 orthogonality against player_fingerprints, printed here.
Output: data/intelligence/cv_shot_range_features_sidecar.parquet
"""
from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

IN_PATH  = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_range_per_game.parquet")
FP_PATH  = os.path.join(PROJECT_DIR, "data", "intelligence", "player_fingerprints.parquet")
OUT_PATH = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_range_features_sidecar.parquet")

# Source metric columns from per-game parquet
METRIC_COLS = ["mean_shot_distance", "p75_shot_distance", "short_rate", "long_rate"]
# Corresponding feature prefix map
FEAT_PREFIX = {
    "mean_shot_distance": "shot_range_mean",
    "p75_shot_distance":  "shot_range_p75",
    "short_rate":         "shot_range_short_rate",
    "long_rate":          "shot_range_long_rate",
}
WINDOWS = [5, 10]

# G2 orthogonality baseline columns from player_fingerprints
FP_COMPARE_COLS = ["avg_shot_distance", "shot_zone_paint_pct", "shot_zone_3pt_pct"]
G2_THRESHOLD = 0.7


def build_features(per_game: pd.DataFrame) -> pd.DataFrame:
    """Compute strict-as-of rolling means for each metric column."""
    per_game = per_game.copy()
    per_game["game_date"] = pd.to_datetime(per_game["game_date"], errors="coerce")
    per_game = per_game.dropna(subset=["game_date"])
    per_game = per_game.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    for c in METRIC_COLS:
        per_game[c] = pd.to_numeric(per_game[c], errors="coerce")
    per_game["n_shots"] = pd.to_numeric(per_game["n_shots"], errors="coerce")

    records = []

    for pid, grp in per_game.groupby("player_id", sort=False):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        dates   = grp["game_date"].values
        n_shots = grp["n_shots"].values
        metric_vals = {c: grp[c].values for c in METRIC_COLS}

        for row_i in range(len(grp)):
            target_date = dates[row_i]
            prior_mask = dates < target_date
            prior_idxs = np.where(prior_mask)[0]

            rec: dict = {
                "player_id": int(pid),
                "game_date": str(target_date)[:10],
            }

            for w in WINDOWS:
                window_idxs = prior_idxs[-w:] if len(prior_idxs) >= 1 else np.array([], dtype=int)
                for mc in METRIC_COLS:
                    feat_name = f"{FEAT_PREFIX[mc]}_l{w}"
                    if len(window_idxs) == 0:
                        rec[feat_name] = np.nan
                    else:
                        vals = metric_vals[mc][window_idxs]
                        rec[feat_name] = float(np.nanmean(vals))

            # diagnostic: total shots in l5 window
            w5_idxs = prior_idxs[-5:] if len(prior_idxs) >= 1 else np.array([], dtype=int)
            rec["shot_range_n_shots_l5"] = (
                float(np.nansum(n_shots[w5_idxs])) if len(w5_idxs) > 0 else np.nan
            )
            records.append(rec)

    result = pd.DataFrame(records)
    result["game_date"] = result["game_date"].astype(str).str[:10]
    return result


def compute_g1(sidecar: pd.DataFrame) -> float:
    """G1: fraction of rows with >=1 non-NaN sidecar feature."""
    feat_cols = [c for c in sidecar.columns
                 if c.startswith("shot_range_") and c.endswith(("_l5", "_l10"))]
    has_any = sidecar[feat_cols].notna().any(axis=1)
    return float(has_any.mean())


def compute_g2(sidecar: pd.DataFrame) -> dict:
    """G2: per-feature max |r| against player_fingerprints FP_COMPARE_COLS.

    Returns dict: {feat_col: max_r, ...}, plus 'max_overall' and 'dropped' list.
    Correlation is computed on 5K sampled merged rows.
    """
    if not os.path.exists(FP_PATH):
        print("  [G2] player_fingerprints.parquet not found — skipping G2")
        return {"max_overall": 0.0, "dropped": [], "per_feat": {}}

    fp = pd.read_parquet(FP_PATH)
    fp = fp.reset_index()  # player_id may be index
    if "player_id" not in fp.columns and fp.index.name == "player_id":
        fp = fp.rename_axis("player_id").reset_index()
    if "player_id" not in fp.columns:
        # fingerprints keyed without player_id as column — try index
        fp["player_id"] = fp.index

    fp["player_id"] = pd.to_numeric(fp["player_id"], errors="coerce")
    fp = fp.dropna(subset=["player_id"])
    fp["player_id"] = fp["player_id"].astype(int)

    available_fp_cols = [c for c in FP_COMPARE_COLS if c in fp.columns]

    sidecar_sample = sidecar.copy()
    sidecar_sample["player_id"] = sidecar_sample["player_id"].astype(int)
    merged = sidecar_sample.merge(fp[["player_id"] + available_fp_cols], on="player_id", how="inner")
    if len(merged) > 5000:
        merged = merged.sample(5000, random_state=42)

    feat_cols = [c for c in sidecar.columns
                 if c.startswith("shot_range_") and c.endswith(("_l5", "_l10"))]

    per_feat: dict = {}
    max_overall = 0.0
    for fc in feat_cols:
        if fc not in merged.columns:
            continue
        max_r = 0.0
        for fpc in available_fp_cols:
            if fpc not in merged.columns:
                continue
            try:
                r = float(merged[fc].corr(merged[fpc]))
                if not np.isnan(r):
                    max_r = max(max_r, abs(r))
            except Exception:
                pass
        per_feat[fc] = max_r
        max_overall = max(max_overall, max_r)

    dropped = [fc for fc, r in per_feat.items() if r > G2_THRESHOLD]
    return {"max_overall": max_overall, "dropped": dropped, "per_feat": per_feat}


def main():
    if not os.path.exists(IN_PATH):
        print(f"ERROR: {IN_PATH} not found. Run build_cv_shot_range.py first.")
        sys.exit(1)

    per_game = pd.read_parquet(IN_PATH)
    print(f"Loaded per-game: {len(per_game)} rows, {per_game['player_id'].nunique()} players")

    print("\nBuilding rolling features ...")
    sidecar = build_features(per_game)
    print(f"Sidecar rows: {len(sidecar)}")

    # --- G1 ---
    g1_cov = compute_g1(sidecar)
    g1_pass = g1_cov >= 0.25
    print(f"\n[G1] Coverage: {g1_cov:.3f} ({'PASS' if g1_pass else 'FAIL'} — threshold 0.25)")
    if g1_cov < 0.10:
        print("[KILL SWITCH] G1 < 10% — BLOCKED")
        sys.exit(2)
    if not g1_pass:
        print("[WARN] G1 < 0.25 but >= 0.10 — proceeding with caution")

    # --- G2 ---
    print("\n[G2] Orthogonality vs player_fingerprints ...")
    g2_res = compute_g2(sidecar)
    print(f"  max_overall |r|: {g2_res['max_overall']:.3f} (threshold {G2_THRESHOLD})")
    if g2_res["per_feat"]:
        for fc, r in sorted(g2_res["per_feat"].items()):
            flag = "DROP" if r > G2_THRESHOLD else "OK"
            print(f"  {fc:40s} |r|={r:.3f} [{flag}]")
    dropped = g2_res.get("dropped", [])
    if dropped:
        print(f"\n  Dropping {len(dropped)} features (|r|>{G2_THRESHOLD}): {dropped}")
    else:
        print(f"  No features dropped — all |r| <= {G2_THRESHOLD}")

    # Kill switch: ALL 8 features dropped → SHIP-DEFER
    all_feat_cols = [c for c in sidecar.columns
                     if c.startswith("shot_range_") and c.endswith(("_l5", "_l10"))]
    if len(dropped) >= len(all_feat_cols):
        print("[KILL SWITCH] All features fail G2 orthogonality — SHIP-DEFER (high redundancy)")
        sys.exit(3)

    # Drop G2-failed columns
    if dropped:
        sidecar = sidecar.drop(columns=[c for c in dropped if c in sidecar.columns])

    surviving = [c for c in sidecar.columns
                 if c.startswith("shot_range_") and c.endswith(("_l5", "_l10"))]
    print(f"\n  Surviving features ({len(surviving)}): {surviving}")

    # --- Save ---
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    sidecar.to_parquet(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")
    print(f"Shape: {sidecar.shape}")

    # Sample
    sample = sidecar.dropna(subset=["shot_range_mean_l5"] if "shot_range_mean_l5" in sidecar.columns
                             else surviving[:1])
    print(f"\nRows with l5 non-NaN: {len(sample)}")
    if len(sample) > 0 and surviving:
        print(sample[["player_id", "game_date"] + surviving[:4]].head(5).to_string())

    # Print G2 summary for vault note
    print(f"\n=== GATE RESULTS ===")
    print(f"G1 coverage: {g1_cov:.3f} ({'PASS' if g1_pass else 'FAIL'})")
    print(f"G2 max |r|: {g2_res['max_overall']:.3f} | dropped: {dropped}")
    print(f"Surviving features: {surviving}")

    return sidecar, g1_cov, g2_res, surviving


if __name__ == "__main__":
    main()
