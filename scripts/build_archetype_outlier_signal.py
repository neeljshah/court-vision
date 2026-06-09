"""
build_archetype_outlier_signal.py — INT-54: Archetype Outlier Signal

Produces a continuous L2-distance-in-scaler-space signal per (player_id, game_id).
Uses the same atlas KMeans + scaler as INT-38 (build_archetype_drift.py) — DO NOT REFIT.

For each game date, computes:
  - all-time centroid vs last-5-games centroid in scaler space
  - L2 distance d_last5 between them
  - outlier_z = (d_last5 - d_hist_mean) / max(d_hist_std, 1.0)
  - direction_top3: top-3 per-feature deltas (feature names, not cluster IDs)
  - flag_strong_outlier = (|outlier_z| >= 2.0) AND (n_hist_games >= 5)

Output: data/intelligence/archetype_outlier_signals.parquet

Run:
    python scripts/build_archetype_outlier_signal.py
"""
from __future__ import annotations

import glob
import json
import os
import pickle
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

# ── Portable root (works on Windows + RunPod Linux) ─────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_CANDIDATES = [
    ROOT / "data" / "nba_ai.db",
    ROOT / "data" / "nba.db",
    ROOT / "data" / "runpod_mirror.db",
    ROOT / "data" / "local.db",
]
DB_PATH = next((str(p) for p in DB_CANDIDATES if p.exists()), None)
if DB_PATH is None:
    raise FileNotFoundError("No cv_features database found.")

MODELS_DIR  = ROOT / "data" / "models"
INTEL_DIR   = ROOT / "data" / "intelligence"
VAULT_DIR   = ROOT / "vault" / "Intelligence"
OUT_PATH    = INTEL_DIR / "archetype_outlier_signals.parquet"

os.makedirs(str(INTEL_DIR), exist_ok=True)
os.makedirs(str(VAULT_DIR), exist_ok=True)

MIN_HIST_GAMES = 5   # minimum history to emit outlier_z


# ── Step 1: Load atlas (mirrors build_archetype_drift.py lines 74-88) ────────
def load_atlas() -> tuple:
    """Load INT-1 KMeans + scaler. DO NOT REFIT."""
    kmeans_path  = MODELS_DIR / "player_atlas_kmeans.pkl"
    scaler_path  = MODELS_DIR / "player_atlas_scaler.pkl"
    feats_path   = INTEL_DIR  / "player_atlas_feature_list.json"

    if kmeans_path.exists() and scaler_path.exists() and feats_path.exists():
        with open(kmeans_path, "rb") as f:
            kmeans = pickle.load(f)
        with open(scaler_path, "rb") as f:
            scaler = pickle.load(f)
        with open(feats_path) as f:
            feat_data = json.load(f)
        features: List[str] = feat_data["features"]   # raw names, no _mean suffix
        print(f"  [INT-54] Loaded atlas KMeans (K={kmeans.n_clusters}) + scaler")
        print(f"  Features ({len(features)}): {features}")
    else:
        # Legacy fallback
        print("  [WARN] Atlas pkl not found; falling back to player_archetypes.pkl")
        with open(MODELS_DIR / "player_archetypes.pkl", "rb") as f:
            state = pickle.load(f)
        scaler   = state["scaler"]
        kmeans   = state["kmeans"]
        features = state["features"]
        print(f"  Fallback: K={kmeans.n_clusters}, features={features}")

    return scaler, kmeans, features


# ── Step 2: Load cv_features (mirrors build_archetype_drift.py lines 104-134) ─
def load_cv_vectors(features: List[str]) -> pd.DataFrame:
    """Pivot cv_features into (player_id, game_id) × features. NaN → 0."""
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join(f"'{f}'" for f in features)
    df = pd.read_sql(
        f"SELECT player_id, game_id, feature_name, feature_value "
        f"FROM cv_features WHERE feature_name IN ({placeholders})",
        conn,
    )
    conn.close()

    pivot = df.pivot_table(
        index=["player_id", "game_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="mean",
    )

    # Ensure all atlas features present; fill missing with 0 (same as drift script)
    for feat in features:
        if feat not in pivot.columns:
            pivot[feat] = 0.0
    pivot = pivot[features].fillna(0.0).reset_index()

    print(f"  cv_features pivot: {len(pivot)} (player, game) rows")
    return pivot


# ── Step 3: Resolve game_date (mirrors build_archetype_drift.py lines 144-172) ─
def load_game_dates() -> Dict[str, str]:
    """game_id → YYYY-MM-DD from season_games_*.json files."""
    game_dates: Dict[str, str] = {}
    season_dir = ROOT / "data" / "nba"
    for fpath in sorted(glob.glob(str(season_dir / "season_games_*.json"))):
        with open(fpath) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            gid   = row.get("game_id", "")
            gdate = row.get("game_date", "")
            if gid and gdate:
                game_dates[gid] = gdate

    print(f"  game_dates resolved: {len(game_dates)} entries")
    return game_dates


# ── Step 4: Load player names for reporting ───────────────────────────────────
def load_player_names() -> Dict[int, str]:
    fp_path = INTEL_DIR / "player_fingerprints.parquet"
    if not fp_path.exists():
        return {}
    fp = pd.read_parquet(str(fp_path))
    if "player_name" in fp.columns:
        return fp["player_name"].to_dict()
    return {}


# ── Step 5: Core per-player signal computation ────────────────────────────────
def compute_outlier_signals(
    pivot: pd.DataFrame,
    scaler,
    features: List[str],
    game_dates: Dict[str, str],
) -> pd.DataFrame:
    """
    For each (player_id, game_date) pair compute:
      - d_last5: L2 distance in scaler-space between last-5-game centroid
                 and all-time centroid (STRICTLY historical, shift(1).expanding)
      - outlier_z, direction_top3, flag_strong_outlier
    """
    scale_arr = scaler.scale_  # shape (n_features,)

    # Project all rows into scaler space once
    raw_vals = pivot[features].values
    scaled_vals = scaler.transform(raw_vals)   # shape (n_rows, n_features)

    pivot = pivot.copy()
    pivot["game_date"] = pivot["game_id"].map(game_dates)
    # Fall back to lexicographic sort if date missing
    pivot["_sort_key"] = pivot["game_date"].fillna(pivot["game_id"])
    pivot["_scaled"] = list(scaled_vals)

    records = []

    for player_id, grp in pivot.groupby("player_id"):
        grp = grp.sort_values("_sort_key").reset_index(drop=True)
        n = len(grp)
        if n < 2:
            continue  # need at least 2 games (1 history + 1 current)

        scaled_matrix = np.stack(grp["_scaled"].values)  # shape (n, n_features)

        for i in range(1, n):
            # History = games [0 .. i-1] (strict shift-1 expanding)
            hist = scaled_matrix[:i]           # shape (i, n_features)
            n_hist = i

            alltime_centroid = hist.mean(axis=0)

            # last-5 within history
            last5 = hist[-5:]
            last5_centroid = last5.mean(axis=0)

            d_last5 = float(np.linalg.norm(last5_centroid - alltime_centroid))

            records.append({
                "player_id":   int(player_id),
                "game_id":     grp["game_id"].iloc[i],
                "game_date":   grp["game_date"].iloc[i] if grp["game_date"].iloc[i] else None,
                "n_hist_games": n_hist,
                "d_last5":     d_last5,
                "_alltime":    alltime_centroid,
                "_last5":      last5_centroid,
                "_raw_delta":  last5_centroid - alltime_centroid,
            })

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # ── Compute player-level historical mean + std of d_last5 ─────────────────
    # We need expanding mean/std per player BEFORE current row (already done
    # above; now compute across the running records per player).
    # Since records are already ordered by game within player, we compute
    # expanding stats on d_last5 per player and use SHIFT(1) to avoid leakage.

    df = df.sort_values(["player_id", "game_date", "game_id"]).reset_index(drop=True)

    df["d_hist_mean"] = (
        df.groupby("player_id")["d_last5"]
        .transform(lambda s: s.shift(1).expanding().mean())
    )
    df["d_hist_std"] = (
        df.groupby("player_id")["d_last5"]
        .transform(lambda s: s.shift(1).expanding().std())
    )

    # outlier_z: only valid when n_hist_games >= MIN_HIST_GAMES
    def _z(row):
        if row["n_hist_games"] < MIN_HIST_GAMES or pd.isna(row["d_hist_mean"]):
            return float("nan")
        std = row["d_hist_std"] if (not pd.isna(row["d_hist_std"]) and row["d_hist_std"] > 0) else 1.0
        std = max(std, 1.0)
        return (row["d_last5"] - row["d_hist_mean"]) / std

    df["outlier_z"] = df.apply(_z, axis=1)

    # ── direction_top3: per-feature delta normalised by scaler.scale_ ─────────
    def _dir_top3(raw_delta: np.ndarray) -> str:
        deltas = raw_delta / scale_arr          # normalised direction in scaler space
        top3_idx = np.argsort(np.abs(deltas))[-3:][::-1]
        result = {features[j]: round(float(deltas[j]), 4) for j in top3_idx}
        return json.dumps(result)

    df["direction_top3"] = df["_raw_delta"].apply(_dir_top3)

    # flag_strong_outlier
    df["flag_strong_outlier"] = (
        (df["outlier_z"].abs() >= 2.0) & (df["n_hist_games"] >= MIN_HIST_GAMES)
    ).fillna(False)

    # Drop internal columns
    df = df.drop(columns=["_alltime", "_last5", "_raw_delta"])

    return df


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=== INT-54: Archetype Outlier Signal ===")

    scaler, kmeans, features = load_atlas()
    pivot      = load_cv_vectors(features)
    game_dates = load_game_dates()
    names      = load_player_names()

    print("  Computing outlier signals …")
    df = compute_outlier_signals(pivot, scaler, features, game_dates)

    if df.empty:
        print("  ERROR: no rows generated — check cv_features coverage.")
        sys.exit(1)

    # Final schema
    out_cols = [
        "player_id", "game_id", "game_date",
        "n_hist_games", "d_last5", "d_hist_mean", "d_hist_std",
        "outlier_z", "direction_top3", "flag_strong_outlier",
    ]
    df = df[out_cols]

    df.to_parquet(str(OUT_PATH), index=False)
    print(f"\n  Wrote {len(df)} rows to {OUT_PATH}")

    # ── Sanity print ──────────────────────────────────────────────────────────
    flagged = df[df["flag_strong_outlier"] == True]
    total_valid = df[df["n_hist_games"] >= MIN_HIST_GAMES]
    pct_flagged = 100.0 * len(flagged) / max(len(total_valid), 1)

    print(f"\n  n_players_with_signal : {df['player_id'].nunique()}")
    print(f"  total rows            : {len(df)}")
    print(f"  rows with n_hist >= 5 : {len(total_valid)}")
    print(f"  flag_strong_outlier   : {len(flagged)} ({pct_flagged:.1f}%)")

    top10 = (
        flagged.groupby("player_id")
        .size()
        .sort_values(ascending=False)
        .head(10)
        .reset_index(name="n_flagged")
    )
    top10["player_name"] = top10["player_id"].map(names).fillna("Unknown")
    print("\n  Top-10 by flag_strong_outlier count:")
    print(top10.to_string(index=False))

    # ── Cross-check with archetype_drift if available ─────────────────────────
    # archetype_drift is player-level (no game_id), join on player_id only
    drift_path = INTEL_DIR / "archetype_drift.parquet"
    if drift_path.exists():
        drift = pd.read_parquet(str(drift_path))
        if "drift_tag" in drift.columns:
            merged = df.merge(
                drift[["player_id", "drift_tag"]].drop_duplicates("player_id"),
                on="player_id", how="left"
            )
            cross = merged[merged["flag_strong_outlier"] == True]["drift_tag"].value_counts()
            print("\n  Cross-tab flag_strong_outlier vs drift_tag:")
            print(cross.to_string())
            agree = cross.get("DRIFTING", 0) + cross.get("TRANSITIONING", 0)
            total_flagged = len(flagged)
            if total_flagged > 0:
                print(f"  Agreement (DRIFTING+TRANSITIONING): {agree}/{total_flagged} = {100.*agree/total_flagged:.1f}%")
        else:
            print("\n  [INFO] drift_tag column not in archetype_drift.parquet")
    else:
        print("\n  [INFO] archetype_drift.parquet not found -- skipping cross-tab")

    print("\n  Done.")
    return df, top10, names


if __name__ == "__main__":
    main()
