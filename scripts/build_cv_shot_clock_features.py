"""build_cv_shot_clock_features.py — INT-125 Step 1: Per-game shot-clock bucket rates.

Globs data/tracking/*/shot_log_enriched.csv, filters shot_clock in [0, 24],
buckets into early/mid/late/very_late, groups by (player_id, game_id),
patches game_date from nba_ai.db, writes cv_shot_clock_per_game.parquet.

Buckets (Opus spec):
  very_late : [0, 4)   — bailout / hero
  late      : [4, 8)   — set play / drive
  mid       : [8, 15)  — halfcourt
  early     : [15, 24] — transition / pass-and-shoot
"""
from __future__ import annotations

import glob
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

TRACKING_ROOT = os.path.join(PROJECT_DIR, "data", "tracking")
OUT_PATH = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_clock_per_game.parquet")
DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")

BUCKET_BINS   = [0, 4, 8, 15, 24]
BUCKET_LABELS = ["very_late", "late", "mid", "early"]


def _load_game(enriched_path: str, game_id: str) -> pd.DataFrame | None:
    """Load shot_log_enriched.csv for one game; return filtered records or None."""
    try:
        df = pd.read_csv(enriched_path)
    except Exception:
        return None

    if df.empty or "player_id" not in df.columns:
        return None
    if "shot_clock" not in df.columns:
        return None

    df = df.copy()
    df["shot_clock"] = pd.to_numeric(df["shot_clock"], errors="coerce")
    # Filter to valid [0, 24]
    df = df[df["shot_clock"].between(0, 24, inclusive="both")]
    if df.empty:
        return None

    # Drop invalid player IDs
    df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")
    df = df.dropna(subset=["player_id"])
    df["player_id"] = df["player_id"].astype(int)
    df = df[df["player_id"] >= 0]
    if df.empty:
        return None

    df["game_id"] = game_id
    return df[["game_id", "player_id", "shot_clock"]]


def _resolve_nba_player_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Replace slot player_id (1-10) with nba_player_id using player_cv_per_game.parquet.

    Only rows with a resolved nba_player_id are kept. Unresolved rows are
    dropped so the sidecar keys match prop_pergame (which uses real NBA IDs).
    """
    pg_path = os.path.join(PROJECT_DIR, "data", "player_cv_per_game.parquet")
    if not os.path.exists(pg_path):
        print(f"  [WARN] player_cv_per_game.parquet not found — slot IDs kept (merge will be empty)")
        return df

    pg = pd.read_parquet(pg_path)[["game_id", "player_id", "nba_player_id"]]
    pg = pg.dropna(subset=["nba_player_id"])
    pg["player_id"] = pg["player_id"].astype(int)
    pg["nba_player_id"] = pg["nba_player_id"].astype(int)

    merged = df.merge(pg, on=["game_id", "player_id"], how="left")
    resolved = merged["nba_player_id"].notna().sum()
    print(f"  NBA player_id resolved: {resolved}/{len(merged)} rows ({resolved/len(merged)*100:.1f}%)")

    # Keep only resolved rows and use nba_player_id as player_id
    resolved_df = merged.dropna(subset=["nba_player_id"]).copy()
    resolved_df["player_id"] = resolved_df["nba_player_id"].astype(int)
    resolved_df = resolved_df.drop(columns=["nba_player_id"])
    return resolved_df


def _build_per_game(all_shots: pd.DataFrame) -> pd.DataFrame:
    """Bucket shot_clock and aggregate per (player_id, game_id)."""
    df = all_shots.copy()
    df["bucket"] = pd.cut(
        df["shot_clock"],
        bins=BUCKET_BINS,
        labels=BUCKET_LABELS,
        right=False,
        include_lowest=True,
    )

    records = []
    for (pid, gid), grp in df.groupby(["player_id", "game_id"], sort=False):
        n = len(grp)
        counts = grp["bucket"].value_counts()
        rec = {
            "game_id": str(gid),
            "player_id": int(pid),
            "n_shots": n,
            "shot_clock_mean": float(grp["shot_clock"].mean()),
        }
        for label in BUCKET_LABELS:
            rec[f"shot_clock_{label}_rate"] = float(counts.get(label, 0)) / n
        records.append(rec)

    return pd.DataFrame(records)


def _patch_game_date(df: pd.DataFrame) -> pd.DataFrame:
    """Patch game_date from multiple sources: nba_ai.db + existing CV parquets."""
    date_map: dict[str, str] = {}

    # Source 1: nba_ai.db box_scores
    if os.path.exists(DB_PATH):
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        for tbl, gcol in [("box_scores", "game_date")]:
            try:
                dates = pd.read_sql(f"SELECT DISTINCT game_id, {gcol} FROM {tbl}", conn)
                dates["game_id"] = dates["game_id"].astype(str)
                for _, row in dates.iterrows():
                    gid = row["game_id"]
                    if gid not in date_map and pd.notna(row[gcol]):
                        date_map[gid] = str(row[gcol])[:10]
            except Exception as e:
                print(f"  [WARN] DB table {tbl}: {e}")
        conn.close()
        print(f"  From DB: {len(date_map)} game_ids")

    # Source 2: cv_shot_range_per_game.parquet (has dates for 71+ games)
    range_path = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_range_per_game.parquet")
    if os.path.exists(range_path):
        try:
            rdf = pd.read_parquet(range_path)[["game_id", "game_date"]].dropna()
            for _, row in rdf.iterrows():
                gid = str(row["game_id"])
                if gid not in date_map and pd.notna(row["game_date"]):
                    date_map[gid] = str(row["game_date"])[:10]
            print(f"  From cv_shot_range: {len(date_map)} game_ids total")
        except Exception as e:
            print(f"  [WARN] cv_shot_range fallback: {e}")

    # Source 3: derive from game_id NBA convention (0022XYYYY → season start 2024-10-22)
    # game_id format: 00 + season_code + sequence (not reliable for exact date, skip)

    df["game_date"] = df["game_id"].map(date_map).fillna("")
    mapped = (df["game_date"] != "").sum()
    print(f"  game_date patched: {mapped}/{len(df)} rows ({mapped/len(df)*100:.1f}%)")
    return df


def main():
    files = sorted(glob.glob(os.path.join(TRACKING_ROOT, "*", "shot_log_enriched.csv")))
    print(f"Found {len(files)} enriched files")

    all_dfs = []
    skipped = 0
    for f in files:
        game_id = os.path.basename(os.path.dirname(f))
        df = _load_game(f, game_id)
        if df is None:
            skipped += 1
        else:
            all_dfs.append(df)

    if not all_dfs:
        print("ERROR: No valid shot_clock data found. BLOCKED — kill switch.")
        sys.exit(1)

    all_shots = pd.concat(all_dfs, ignore_index=True)
    print(f"Total valid shots (shot_clock in [0,24]): {len(all_shots)}")
    print(f"Games with data: {all_shots['game_id'].nunique()} / skipped: {skipped}")

    # Sanity check: all shot_clock values must be in range
    assert all_shots["shot_clock"].between(0, 24).all(), "Kill switch: out-of-range shot_clock"
    assert (all_shots["shot_clock"] > 0).any() or (all_shots["shot_clock"] == 0).any(), \
        "Kill switch: all shot_clock <= 0"

    # Bucket distribution summary
    bucket_col = pd.cut(all_shots["shot_clock"], bins=BUCKET_BINS,
                        labels=BUCKET_LABELS, right=False, include_lowest=True)
    dist = bucket_col.value_counts(normalize=True).sort_index()
    print("\nBucket distribution (all shots):")
    for label in BUCKET_LABELS:
        print(f"  {label:12s}: {dist.get(label, 0)*100:.1f}%")

    # Resolve slot IDs to NBA player IDs (required for prop_pergame merge)
    all_shots = _resolve_nba_player_ids(all_shots)
    if all_shots.empty:
        print("ERROR: No rows after NBA player_id resolution. Using all data with slot IDs.")
        # Reload original data for per_game build (will have slot IDs)
        all_dfs2 = []
        for f in files:
            game_id = os.path.basename(os.path.dirname(f))
            df = _load_game(f, game_id)
            if df is not None:
                all_dfs2.append(df)
        all_shots = pd.concat(all_dfs2, ignore_index=True)

    per_game = _build_per_game(all_shots)
    print(f"\nPer-game rows (player x game, NBA IDs): {len(per_game)}")

    per_game = _patch_game_date(per_game)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    per_game.to_parquet(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")
    print(f"Shape: {per_game.shape}")
    print(f"Columns: {per_game.columns.tolist()}")
    print(per_game.head(5).to_string())


if __name__ == "__main__":
    main()
