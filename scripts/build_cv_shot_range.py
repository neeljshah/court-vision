"""build_cv_shot_range.py — INT-121: Per-game shot-range distribution per player.

Reads data/tracking/*/shot_log.csv, prefers shot_distance column (NBA feet, basket-frame),
falls back to pixel-coordinate computation when missing.

Output: data/intelligence/cv_shot_range_per_game.parquet
  Columns: player_id, player_name, game_id, game_date,
           mean_shot_distance, p75_shot_distance,
           short_rate, long_rate, n_shots
  (short = <=6 ft, long = >=22 ft)
"""
from __future__ import annotations

import os
import sys
import glob
import json
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

TRACKING_DIR = os.path.join(PROJECT_DIR, "data", "tracking")
DB_PATH      = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
OUT_PATH     = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_range_per_game.parquet")

SHORT_FT = 6.0
LONG_FT  = 22.0

# Court dimensions in NBA feet
COURT_WIDTH_FT  = 94.0
COURT_HEIGHT_FT = 50.0


def _pixel_to_feet(x_pix: np.ndarray, y_pix: np.ndarray, map_w: float, map_h: float):
    """Convert pixel coords to half-court-flipped distance from nearest basket."""
    ft_x = (x_pix / map_w) * COURT_WIDTH_FT
    ft_y = (y_pix / map_h) * COURT_HEIGHT_FT
    # left basket: (5.25, 25)  right basket: (88.75, 25)
    dist_left  = np.hypot(ft_x - 5.25,  ft_y - 25.0)
    dist_right = np.hypot(ft_x - 88.75, ft_y - 25.0)
    return np.minimum(dist_left, dist_right)


def process_shot_log(path: str, game_date_map: dict | None = None) -> pd.DataFrame | None:
    """Process one shot_log.csv; return per-player rows or None if empty/invalid."""
    try:
        df = pd.read_csv(path)
    except Exception:
        return None

    if len(df) == 0:
        return None

    # --- resolve shot_distance ---
    if "shot_distance" in df.columns:
        df["dist_ft"] = pd.to_numeric(df["shot_distance"], errors="coerce")
    elif "x_position" in df.columns and "y_position" in df.columns:
        # pixel fallback
        x = pd.to_numeric(df["x_position"], errors="coerce").values
        y = pd.to_numeric(df["y_position"], errors="coerce").values
        # infer map dimensions — try manifest.json in parent dir
        game_dir = os.path.dirname(path)
        manifest = os.path.join(game_dir, "manifest.json")
        map_w, map_h = None, None
        if os.path.exists(manifest):
            try:
                with open(manifest) as f:
                    meta = json.load(f)
                map_w = meta.get("frame_width") or meta.get("width")
                map_h = meta.get("frame_height") or meta.get("height")
            except Exception:
                pass
        if map_w is None:
            nz = x[~np.isnan(x)]
            map_w = float(np.max(nz)) if len(nz) > 0 else 1.0
        if map_h is None:
            nz = y[~np.isnan(y)]
            map_h = float(np.max(nz)) if len(nz) > 0 else 1.0
        df["dist_ft"] = _pixel_to_feet(x, y, map_w, map_h)
    else:
        return None  # no usable coord column

    # Kill switch: >30% NaN distance
    nan_frac = df["dist_ft"].isna().mean()
    if nan_frac > 0.30:
        print(f"  [SKIP] {path}: {nan_frac:.0%} NaN dist_ft — exceeds 30% kill switch")
        return None

    # Sanity check: if median dist > 100 ft, shot_distance is likely in pixel units — skip
    valid = df["dist_ft"].dropna()
    if len(valid) > 0 and float(valid.median()) > 100.0:
        return None  # pixel-unit contamination, skip silently

    # Kill switch: all same x/y
    if "x_position" in df.columns and not ("shot_distance" in df.columns):
        if df["x_position"].nunique() <= 1:
            print(f"  [HALT] {path}: all shots same x_position — homography triage needed")
            return None

    # Extract game metadata
    game_id = None
    if "game_id" in df.columns:
        vals = df["game_id"].dropna()
        if len(vals) > 0:
            raw = str(vals.iloc[0])
            # Handle float-like strings e.g. '22500002.0' — strip decimal part
            game_id = raw.split(".")[0]
    if game_id is None:
        game_id = os.path.basename(os.path.dirname(path))
    # Normalize: ensure 10-char zero-padded (NBA format)
    try:
        game_id = str(int(game_id)).zfill(10)
    except ValueError:
        # Keep folder name as-is if parsing fails
        game_id = os.path.basename(os.path.dirname(path))

    game_date = None
    if "game_date" in df.columns:
        vals = df["game_date"].dropna()
        game_date = str(vals.iloc[0])[:10] if len(vals) > 0 else None
    if game_date is None and game_date_map:
        game_date = game_date_map.get(str(game_id), None)

    if game_date is None:
        # try to infer from manifest (key is "date")
        game_dir = os.path.dirname(path)
        manifest = os.path.join(game_dir, "manifest.json")
        if os.path.exists(manifest):
            try:
                with open(manifest) as f:
                    meta = json.load(f)
                # manifest uses "date" not "game_date"
                game_date = str(meta.get("date") or meta.get("game_date") or "")[:10] or None
            except Exception:
                pass

    if not game_date or game_date in ("N", ""):
        return None  # can't build strict-as-of without date

    # per-player aggregation
    player_col = "player_id" if "player_id" in df.columns else None
    if player_col is None:
        return None

    df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")
    df = df.dropna(subset=["player_id", "dist_ft"])
    df["player_id"] = df["player_id"].astype(int)

    records = []
    for pid, grp in df.groupby("player_id"):
        dists = grp["dist_ft"].values
        n = len(dists)
        if n == 0:
            continue

        pname = ""
        if "player_name" in grp.columns:
            nn = grp["player_name"].dropna()
            pname = str(nn.iloc[0]) if len(nn) > 0 else ""

        records.append({
            "player_id":           int(pid),
            "player_name":         pname,
            "game_id":             game_id,
            "game_date":           game_date,
            "mean_shot_distance":  float(np.mean(dists)),
            "p75_shot_distance":   float(np.percentile(dists, 75)),
            "short_rate":          float(np.mean(dists <= SHORT_FT)),
            "long_rate":           float(np.mean(dists >= LONG_FT)),
            "n_shots":             int(n),
        })

    return pd.DataFrame(records) if records else None


PF_PATH = os.path.join(PROJECT_DIR, "data", "player_pf.parquet")


def _build_game_date_map() -> dict:
    """Build game_id -> game_date mapping.

    Primary source: data/player_pf.parquet (has 500+ game entries).
    Fallback: SQLite box_scores (smaller, ~26 entries).
    """
    gmap: dict = {}

    # Primary: player_pf parquet
    if os.path.exists(PF_PATH):
        try:
            pf = pd.read_parquet(PF_PATH, columns=["game_id", "game_date"])
            for _, row in pf.drop_duplicates("game_id").iterrows():
                gmap[str(row["game_id"]).strip()] = str(row["game_date"])[:10]
            print(f"  game_date map from player_pf: {len(gmap)} entries")
            return gmap
        except Exception as e:
            print(f"  [WARN] player_pf date map failed: {e}")

    # Fallback: SQLite
    if not os.path.exists(DB_PATH):
        return gmap
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT DISTINCT game_id, game_date FROM box_scores WHERE game_date IS NOT NULL"
        ).fetchall()
        conn.close()
        for gid, gdate in rows:
            gmap[str(gid).strip()] = str(gdate)[:10]
        print(f"  game_date map from box_scores: {len(gmap)} entries")
    except Exception as e:
        print(f"  [WARN] game_date lookup failed: {e}")
    return gmap


def main():
    shot_logs = sorted(glob.glob(os.path.join(TRACKING_DIR, "*", "shot_log.csv")))
    print(f"Found {len(shot_logs)} shot_log.csv files")

    game_date_map = _build_game_date_map()
    print(f"Game-date map: {len(game_date_map)} entries from box_scores")

    all_frames = []
    skipped = 0
    for path in shot_logs:
        result = process_shot_log(path, game_date_map=game_date_map)
        if result is not None and len(result) > 0:
            all_frames.append(result)
        else:
            skipped += 1

    if not all_frames:
        print("ERROR: No valid shot data found.")
        sys.exit(1)

    out = pd.concat(all_frames, ignore_index=True)
    out = out.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)

    print(f"\nProcessed: {len(all_frames)} games, skipped: {skipped}")
    print(f"Rows: {len(out)}  Players: {out['player_id'].nunique()}  "
          f"Date range: {out['game_date'].min()} to {out['game_date'].max()}")
    print(f"Total shots (sum n_shots): {out['n_shots'].sum()}")
    print(f"Shot distance stats:")
    print(f"  mean_shot_distance: {out['mean_shot_distance'].describe().to_dict()}")
    print(f"  short_rate:  {out['short_rate'].mean():.3f}  long_rate: {out['long_rate'].mean():.3f}")
    print(f"Wrote: {OUT_PATH}")
    return out


if __name__ == "__main__":
    main()
