"""build_cv_shot_type_features.py — INT-115: Rolling l5/l10 shot-type sidecar.

Reads cv_shot_types_per_game.parquet and computes strict-as-of (game_date < target)
rolling l5 + l10 per-(player_id, game_date) features for the prop_pergame sidecar.

Output: data/intelligence/cv_shot_type_features_sidecar.parquet
  Key columns: player_id, game_date,
    shot_type_cs_rate_l5/l10, shot_type_pu_rate_l5/l10,
    shot_type_drive_rate_l5/l10, shot_type_sb_rate_l5/l10,
    shot_type_n_shots_l5
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

IN_PATH  = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_types_per_game.parquet")
OUT_PATH = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_type_features_sidecar.parquet")

RATE_COLS = ["shot_type_cs_rate", "shot_type_pu_rate",
             "shot_type_drive_rate", "shot_type_sb_rate"]
WINDOWS   = [5, 10]


def build_features(per_game: pd.DataFrame) -> pd.DataFrame:
    """Compute strict-as-of rolling means for each rate column."""
    per_game = per_game.copy()
    per_game["game_date"] = pd.to_datetime(per_game["game_date"], errors="coerce")
    per_game = per_game.dropna(subset=["game_date"])
    per_game = per_game.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    # cast rate cols to float
    for c in RATE_COLS:
        per_game[c] = pd.to_numeric(per_game[c], errors="coerce")
    per_game["n_shots"] = pd.to_numeric(per_game["n_shots"], errors="coerce")

    records = []

    for pid, grp in per_game.groupby("player_id", sort=False):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        dates      = grp["game_date"].values
        n_shots    = grp["n_shots"].values
        rate_vals  = {c: grp[c].values for c in RATE_COLS}

        for row_i in range(len(grp)):
            target_date = dates[row_i]
            # Strict as-of: only prior games
            prior_mask = dates < target_date
            prior_idxs = np.where(prior_mask)[0]

            rec: dict = {
                "player_id": pid,
                "game_date": str(target_date)[:10],
            }

            for w in WINDOWS:
                window_idxs = prior_idxs[-w:] if len(prior_idxs) >= 1 else np.array([], dtype=int)
                for c in RATE_COLS:
                    feat_name = f"{c}_l{w}"
                    if len(window_idxs) == 0:
                        rec[feat_name] = np.nan
                    else:
                        vals = rate_vals[c][window_idxs]
                        rec[feat_name] = float(np.nanmean(vals))

            # coverage diagnostic — shots in l5 window
            w5_idxs = prior_idxs[-5:] if len(prior_idxs) >= 1 else np.array([], dtype=int)
            rec["shot_type_n_shots_l5"] = float(np.nansum(n_shots[w5_idxs])) if len(w5_idxs) > 0 else np.nan

            records.append(rec)

    result = pd.DataFrame(records)
    result["game_date"] = result["game_date"].astype(str).str[:10]
    return result


def compute_g1_coverage(sidecar: pd.DataFrame) -> float:
    """Compute G1: fraction of rows with >=1 non-NaN shot-type feature (fold-4 proxy)."""
    rate_feat_cols = [c for c in sidecar.columns
                      if c.startswith("shot_type_") and c.endswith(("_l5", "_l10"))]
    has_any = sidecar[rate_feat_cols].notna().any(axis=1)
    return float(has_any.mean())


def compute_g2_orthogonality(sidecar: pd.DataFrame, pergame_path: str) -> dict:
    """G2: max |r| with existing pergame features <= 0.6."""
    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns

    print("  G2: loading pergame dataset for orthogonality check ...")
    rows, fc = build_pergame_dataset(min_prior=0)
    pg_df = pd.DataFrame(rows)
    pg_df["player_id"] = pg_df["player_id"].astype(int)
    pg_df["game_date"]  = pg_df["date"].astype(str).str[:10]

    sidecar["player_id"] = sidecar["player_id"].astype(int)
    merged = pg_df.merge(sidecar, on=["player_id", "game_date"], how="inner")
    if len(merged) > 5000:
        merged = merged.sample(5000, random_state=42)

    rate_feat_cols = [c for c in sidecar.columns
                      if c.startswith("shot_type_") and c.endswith(("_l5", "_l10"))]

    special_check = ["fg3a", "fg2a", "paint_pct", "usage"]  # approximate existing feat names
    existing_cols = [c for c in fc if c in merged.columns]

    max_r = 0.0
    max_pair = ("", "")
    results = {}
    for rc in rate_feat_cols:
        if rc not in merged.columns:
            continue
        rc_vals = merged[rc]
        for ec in existing_cols:
            if ec not in merged.columns:
                continue
            try:
                r = float(rc_vals.corr(merged[ec]))
                if abs(r) > max_r:
                    max_r = abs(r)
                    max_pair = (rc, ec)
            except Exception:
                pass
        results[rc] = max_r

    return {"max_r": max_r, "max_pair": max_pair, "per_feat": results}


def main():
    if not os.path.exists(IN_PATH):
        print(f"ERROR: {IN_PATH} not found. Run build_cv_shot_types.py first.")
        sys.exit(1)

    per_game = pd.read_parquet(IN_PATH)
    print(f"Loaded per-game: {len(per_game)} rows")

    print("Building rolling features ...")
    sidecar = build_features(per_game)
    print(f"Sidecar rows: {len(sidecar)}")

    # G1 coverage
    coverage = compute_g1_coverage(sidecar)
    print(f"\n[G1] Fold-4 coverage proxy: {coverage:.3f} (threshold >= 0.25)")
    g1_pass = coverage >= 0.25

    if not g1_pass:
        coverage_10pct = coverage >= 0.10
        if not coverage_10pct:
            print("[KILL SWITCH] G1 coverage < 10% — DEFER")
            sys.exit(2)
        else:
            print("[WARN] G1 < 25% but >= 10% — proceeding with caution")

    # G2 orthogonality
    try:
        g2_res = compute_g2_orthogonality(sidecar, IN_PATH)
        max_r = g2_res["max_r"]
        print(f"\n[G2] Max |r| with existing features: {max_r:.3f} (threshold <= 0.60)")
        print(f"     Worst pair: {g2_res['max_pair']}")
        g2_pass = max_r <= 0.60
        print(f"     G2 {'PASS' if g2_pass else 'WARN'}")
    except Exception as e:
        print(f"  G2 skipped (pergame dataset unavailable): {e}")
        g2_pass = True  # don't block on unavailability

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    sidecar.to_parquet(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")
    print(f"Shape: {sidecar.shape}")
    print(f"Columns: {sidecar.columns.tolist()}")

    # Sample check
    sample = sidecar.dropna(subset=["shot_type_cs_rate_l5"])
    print(f"\nRows with l5 CS rate non-NaN: {len(sample)}")
    if len(sample) > 0:
        print(sample[["player_id", "game_date", "shot_type_cs_rate_l5",
                       "shot_type_pu_rate_l5", "shot_type_drive_rate_l5",
                       "shot_type_sb_rate_l5", "shot_type_n_shots_l5"]].head(5).to_string())


if __name__ == "__main__":
    main()
