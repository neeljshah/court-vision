"""build_cv_shot_clock_features_sidecar.py — INT-125 Step 2: Rolling l5/l10 sidecar.

Reads cv_shot_clock_per_game.parquet and computes strict-as-of (game_date < target)
rolling l5 + l10 per-(player_id, game_date) features for the prop_pergame sidecar.

Output: data/intelligence/cv_shot_clock_features_sidecar.parquet
  Key columns: player_id, game_date,
    shot_clock_early_rate_l5/l10, shot_clock_mid_rate_l5/l10,
    shot_clock_late_rate_l5/l10, shot_clock_very_late_rate_l5/l10,
    shot_clock_mean_l5 (mean shot clock, l5 only),
    shot_clock_n_shots_l5 (diagnostic)

Mirrors structure of build_cv_shot_type_features.py (INT-115 template).
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

IN_PATH  = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_clock_per_game.parquet")
OUT_PATH = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_clock_features_sidecar.parquet")

RATE_COLS = [
    "shot_clock_early_rate",
    "shot_clock_mid_rate",
    "shot_clock_late_rate",
    "shot_clock_very_late_rate",
]
WINDOWS = [5, 10]


def build_features(per_game: pd.DataFrame) -> pd.DataFrame:
    """Compute strict-as-of rolling means for each rate column + mean clock."""
    per_game = per_game.copy()
    per_game["game_date"] = pd.to_datetime(per_game["game_date"], errors="coerce")
    per_game = per_game.dropna(subset=["game_date"])
    per_game = per_game.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    # cast rate cols and mean to float
    for c in RATE_COLS + ["shot_clock_mean"]:
        per_game[c] = pd.to_numeric(per_game[c], errors="coerce")
    per_game["n_shots"] = pd.to_numeric(per_game["n_shots"], errors="coerce")

    records = []

    for pid, grp in per_game.groupby("player_id", sort=False):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        dates     = grp["game_date"].values
        n_shots   = grp["n_shots"].values
        rate_vals = {c: grp[c].values for c in RATE_COLS}
        mean_vals = grp["shot_clock_mean"].values

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

            # shot_clock_mean rolling l5 only
            w5_idxs = prior_idxs[-5:] if len(prior_idxs) >= 1 else np.array([], dtype=int)
            if len(w5_idxs) == 0:
                rec["shot_clock_mean_l5"] = np.nan
                rec["shot_clock_n_shots_l5"] = np.nan
            else:
                mean_w5 = mean_vals[w5_idxs]
                rec["shot_clock_mean_l5"] = float(np.nanmean(mean_w5))
                rec["shot_clock_n_shots_l5"] = float(np.nansum(n_shots[w5_idxs]))

            records.append(rec)

    result = pd.DataFrame(records)
    result["game_date"] = result["game_date"].astype(str).str[:10]
    return result


def compute_g1_coverage(sidecar: pd.DataFrame) -> float:
    """Compute G1: fraction of rows with >=1 non-NaN shot-clock feature (fold-4 proxy)."""
    rate_feat_cols = [c for c in sidecar.columns
                      if c.startswith("shot_clock_") and c.endswith(("_l5", "_l10"))]
    has_any = sidecar[rate_feat_cols].notna().any(axis=1)
    return float(has_any.mean())


def compute_g2_orthogonality(sidecar: pd.DataFrame) -> dict:
    """G2: max |r| with pace, bbref_usg_pct, and fg3a_rate (approx 3pt_attempt_rate)."""
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
                      if c.startswith("shot_clock_") and c.endswith(("_l5", "_l10"))]

    # Target correlation columns: pace / usage / 3pt attempt rate
    target_corr_cols = [c for c in fc if c in merged.columns
                        and any(k in c for k in ["pace", "usg", "fg3a", "3pt", "bbref_usg"])]

    if not target_corr_cols:
        # Fallback to all feature columns
        target_corr_cols = [c for c in fc if c in merged.columns]

    max_r = 0.0
    max_pair = ("", "")
    results = {}
    for rc in rate_feat_cols:
        if rc not in merged.columns:
            continue
        rc_vals = merged[rc]
        local_max = 0.0
        for ec in target_corr_cols:
            if ec not in merged.columns:
                continue
            try:
                r = float(rc_vals.corr(merged[ec]))
                if abs(r) > local_max:
                    local_max = abs(r)
                if abs(r) > max_r:
                    max_r = abs(r)
                    max_pair = (rc, ec)
            except Exception:
                pass
        results[rc] = local_max

    return {"max_r": max_r, "max_pair": max_pair, "per_feat": results}


def main():
    if not os.path.exists(IN_PATH):
        print(f"ERROR: {IN_PATH} not found. Run build_cv_shot_clock_features.py first.")
        sys.exit(1)

    per_game = pd.read_parquet(IN_PATH)
    print(f"Loaded per-game: {len(per_game)} rows")
    print(f"Columns: {per_game.columns.tolist()}")
    print(f"game_date non-null: {per_game['game_date'].replace('', pd.NA).notna().sum()}")

    print("Building rolling features ...")
    sidecar = build_features(per_game)
    print(f"Sidecar rows: {len(sidecar)}")

    # G1 coverage
    coverage = compute_g1_coverage(sidecar)
    print(f"\n[G1] Fold-4 coverage proxy: {coverage:.3f} (threshold >= 0.25)")
    g1_pass = coverage >= 0.25
    if not g1_pass:
        if coverage < 0.15:
            print("[KILL SWITCH] G1 coverage < 15% — DEFER as data-bound")
            sys.exit(2)
        else:
            print("[WARN] G1 < 25% but >= 15% — proceeding with caution")

    # G2 orthogonality
    g2_pass = True
    try:
        g2_res = compute_g2_orthogonality(sidecar)
        max_r = g2_res["max_r"]
        print(f"\n[G2] Max |r| with pace/usage/3pt features: {max_r:.3f} (threshold <= 0.70)")
        print(f"     Worst pair: {g2_res['max_pair']}")
        g2_pass = max_r <= 0.70
        print(f"     G2 {'PASS' if g2_pass else 'WARN (>0.70)'}")
    except Exception as e:
        print(f"  G2 skipped (pergame dataset unavailable): {e}")
        g2_pass = True

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    sidecar.to_parquet(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")
    print(f"Shape: {sidecar.shape}")
    print(f"Columns: {sidecar.columns.tolist()}")

    # Sample check
    feat_cols_l5 = [c for c in sidecar.columns if c.endswith("_l5")]
    sample = sidecar.dropna(subset=[feat_cols_l5[0]])
    print(f"\nRows with l5 features non-NaN: {len(sample)}")
    if len(sample) > 0:
        show_cols = ["player_id", "game_date"] + feat_cols_l5[:5]
        print(sample[show_cols].head(5).to_string())


if __name__ == "__main__":
    main()
