"""build_cv_shot_types.py — INT-115: Classify CV shot types and write per-game parquet.

Two-path approach:
  PATH A (preferred): cv_features table already has catch_shoot_pct per (game_id, nba_player_id).
  PATH B (extended): shot_log_enriched shot_creation labels for pull_up / drive / step_back,
         joined to nba_player_id via player_name lookup where available.

Final output merges both paths into one parquet with per-player per-game shot type rates
using real NBA player_ids.

Output: data/intelligence/cv_shot_types_per_game.parquet
  Columns: player_id (NBA), game_id, game_date,
           shot_type_cs_rate, shot_type_pu_rate, shot_type_drive_rate,
           shot_type_sb_rate, shot_type_other_rate, n_shots,
           cv_shot_type_source
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import sys
import warnings
from typing import Optional

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

OUT_PATH = os.path.join(PROJECT_DIR, "data", "intelligence", "cv_shot_types_per_game.parquet")
TRACKING_ROOT = os.path.join(PROJECT_DIR, "data", "tracking")
DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")

# Velocity threshold for drive finish
DRIVE_VEL_THRESHOLD = 4.0
STEPBACK_EARLY_WINDOW = slice(-7, -2)
STEPBACK_LATE_WINDOW  = slice(-2, None)
PULLUP_VEL_WINDOW     = 5


# ---------------------------------------------------------------------------
# Step 1: Load cv_features catch_shoot_pct (PATH A — real NBA player_ids)
# ---------------------------------------------------------------------------

def load_cv_features_shot_types(conn: sqlite3.Connection,
                                 game_date_map: dict) -> pd.DataFrame:
    """Pull catch_shoot_pct + game dates from cv_features."""
    df = pd.read_sql("""
        SELECT game_id, player_id, feature_name, feature_value
        FROM cv_features
        WHERE feature_name IN ('catch_shoot_pct', 'n_shots_tracked', 'play_type_drive_pct')
    """, conn)

    if df.empty:
        return pd.DataFrame()

    # Pivot wide
    piv = df.pivot_table(
        index=["game_id", "player_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()
    piv.columns.name = None

    # Normalize
    for c in ["catch_shoot_pct", "n_shots_tracked", "play_type_drive_pct"]:
        if c not in piv.columns:
            piv[c] = np.nan

    piv = piv.rename(columns={
        "catch_shoot_pct": "shot_type_cs_rate",
        "play_type_drive_pct": "shot_type_drive_rate",
        "n_shots_tracked": "n_shots",
    })

    # Attach game_date from external map
    piv["game_id"] = piv["game_id"].astype(str)
    piv["game_date"] = piv["game_id"].map(game_date_map)

    piv["cv_shot_type_source"] = "cv_features"
    piv["player_id"] = pd.to_numeric(piv["player_id"], errors="coerce").astype("Int64")
    piv = piv.drop_duplicates(subset=["game_id", "player_id"])

    print(f"PATH A: {len(piv)} player-game rows from cv_features")
    print(f"  game_date fill: {piv['game_date'].notna().mean():.1%}")
    return piv


# ---------------------------------------------------------------------------
# Step 2: Build player_name -> nba_player_id lookup
# ---------------------------------------------------------------------------

def build_name_lookup(conn: sqlite3.Connection) -> dict:
    """Build fuzzy name → NBA player_id lookup from box_scores + cv_features."""
    # Try to get player names from news_items or injuries
    lookup = {}
    try:
        # Use cv_features game_id + player_id, and cross-reference box_scores on game_id
        # to infer name mappings via box_score player_ids on same game
        bs = pd.read_sql("SELECT DISTINCT player_id FROM box_scores", conn)
        for pid in bs["player_id"].dropna().unique():
            lookup[int(pid)] = int(pid)  # placeholder
    except Exception:
        pass
    return lookup


def normalize_name(name: str) -> str:
    """Normalize player name for fuzzy matching."""
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    name = re.sub(r"[^a-z ]", "", name)
    return " ".join(name.split())


# ---------------------------------------------------------------------------
# Step 3: Per-game shot classification from shot_log_enriched (PATH B)
# ---------------------------------------------------------------------------

def classify_shot_creation(shot_creation: str, dribble_count: int,
                            court_zone: str, catch_and_shoot: int,
                            tracking_row: Optional[pd.Series] = None) -> str:
    """Classify a single shot using enricher labels + fallback kinematic rules."""
    sc = str(shot_creation or "").lower().strip()
    cz = str(court_zone or "").lower()
    zone_mid_or_3 = cz in {"mid_range", "3pt_arc"}

    # 1. Catch and shoot
    if catch_and_shoot == 1 or sc == "catch_and_shoot":
        return "catch_and_shoot"

    # 2. Step-back
    if sc in {"step_back", "stepback"}:
        return "step_back"
    # Kinematic step-back fallback handled at window level

    # 3. Drive finish
    if sc in {"drive", "drive_finish", "driving", "drive_layup", "transition"}:
        return "drive_finish"

    # 4. Pull-up / isolation / PnR → pull_up bucket
    if sc in {"pull_up", "pullup", "pull-up", "isolation", "pick_and_roll"}:
        return "pull_up"

    # 5. Post-up → pull_up
    if sc in {"post_up", "post"}:
        return "pull_up"

    # 6. Dribble-based fallback
    dc = int(dribble_count or 0)
    if dc >= 2 and zone_mid_or_3:
        return "pull_up"
    if dc >= 1 and cz == "paint":
        return "drive_finish"

    return "other"


def process_game_dir_path_b(game_dir: str,
                             name_to_nba_id: dict,
                             game_date_map: dict) -> Optional[pd.DataFrame]:
    """Process one game dir using shot_log_enriched; returns (game_id, player_name, shot_type) rows."""
    game_id = os.path.basename(game_dir)

    enriched_path = os.path.join(game_dir, "shot_log_enriched.csv")
    raw_path = os.path.join(game_dir, "shot_log.csv")

    if os.path.exists(enriched_path):
        try:
            shot_df = pd.read_csv(enriched_path, low_memory=False)
        except Exception:
            return None
    elif os.path.exists(raw_path):
        try:
            shot_df = pd.read_csv(raw_path, low_memory=False)
        except Exception:
            return None
    else:
        return None

    if shot_df.empty:
        return None

    # Ensure numeric player_id
    shot_df["player_id"] = pd.to_numeric(shot_df["player_id"], errors="coerce")
    shot_df = shot_df.dropna(subset=["player_id"])
    shot_df["player_id"] = shot_df["player_id"].astype(int)

    game_date = game_date_map.get(game_id, "")

    records = []
    for _, row in shot_df.iterrows():
        dc = int(pd.to_numeric(row.get("dribble_count", 0), errors="coerce") or 0)
        cas = int(pd.to_numeric(row.get("catch_and_shoot", 0), errors="coerce") or 0)
        sc = str(row.get("shot_creation", "") or "")
        cz = str(row.get("court_zone", "") or "")
        pname = str(row.get("player_name", "") or "")
        slot_id = int(row["player_id"])

        shot_type = classify_shot_creation(sc, dc, cz, cas)

        records.append({
            "game_id": game_id,
            "slot_player_id": slot_id,
            "player_name": pname,
            "shot_type": shot_type,
            "game_date": game_date,
        })

    if not records:
        return None

    df = pd.DataFrame(records)

    # Try to resolve nba_player_id from player_name
    def resolve_nba_id(name: str) -> Optional[int]:
        if not name or "#?" in name or name.upper() in {"UNK", ""}:
            return None
        norm = normalize_name(name)
        return name_to_nba_id.get(norm)

    df["nba_player_id"] = df["player_name"].map(resolve_nba_id)
    return df


# ---------------------------------------------------------------------------
# Step 4: Aggregate PATH B to per-(game_id, nba_player_id) rates
# ---------------------------------------------------------------------------

def aggregate_path_b(all_shots: pd.DataFrame) -> pd.DataFrame:
    """Aggregate shot-type rows to per-(game_id, player_id) rates."""
    # Only keep rows with resolved nba_player_id
    resolved = all_shots.dropna(subset=["nba_player_id"]).copy()
    resolved["nba_player_id"] = resolved["nba_player_id"].astype(int)

    print(f"PATH B: {len(resolved)} shots with resolved nba_player_id "
          f"({len(all_shots)} total)")

    if resolved.empty:
        return pd.DataFrame()

    def _agg(grp):
        n = len(grp)
        return pd.Series({
            "shot_type_cs_rate":    (grp["shot_type"] == "catch_and_shoot").sum() / n,
            "shot_type_pu_rate":    (grp["shot_type"] == "pull_up").sum() / n,
            "shot_type_drive_rate": (grp["shot_type"] == "drive_finish").sum() / n,
            "shot_type_sb_rate":    (grp["shot_type"] == "step_back").sum() / n,
            "shot_type_other_rate": (grp["shot_type"] == "other").sum() / n,
            "n_shots": n,
            "game_date": grp["game_date"].iloc[0],
        })

    per_game = resolved.groupby(["game_id", "nba_player_id"]).apply(_agg).reset_index()
    per_game = per_game.rename(columns={"nba_player_id": "player_id"})
    per_game["cv_shot_type_source"] = "derived_shot_creation"
    per_game["player_id"] = per_game["player_id"].astype("Int64")
    return per_game


# ---------------------------------------------------------------------------
# Step 5: Merge PATH A + PATH B
# ---------------------------------------------------------------------------

def merge_paths(path_a: pd.DataFrame, path_b: pd.DataFrame) -> pd.DataFrame:
    """Merge cv_features (A) and derived (B) shot type data.

    For rows in A: use catch_shoot_pct as cs_rate; fill pu/drive/sb from B where available.
    For rows in B only: use derived rates.
    """
    if path_a.empty and path_b.empty:
        return pd.DataFrame()

    # Fill pull_up/step_back columns that PATH A doesn't have
    if not path_a.empty:
        for c in ["shot_type_pu_rate", "shot_type_sb_rate"]:
            if c not in path_a.columns:
                path_a[c] = np.nan
        if "shot_type_other_rate" not in path_a.columns:
            path_a["shot_type_other_rate"] = np.nan

    if path_b.empty:
        print("PATH B empty — using PATH A only")
        return path_a

    if path_a.empty:
        print("PATH A empty — using PATH B only")
        return path_b

    # Merge: PATH A as base; update with PATH B enrichment for matching (game_id, player_id)
    path_a = path_a.copy()
    path_b = path_b.copy()

    path_a["player_id"] = path_a["player_id"].astype("Int64")
    path_b["player_id"] = path_b["player_id"].astype("Int64")

    # PATH B fills pu/sb columns in PATH A rows
    b_lookup = path_b.set_index(["game_id", "player_id"])
    for idx, row in path_a.iterrows():
        key = (row["game_id"], row["player_id"])
        if key in b_lookup.index:
            b_row = b_lookup.loc[key]
            for c in ["shot_type_pu_rate", "shot_type_sb_rate",
                       "shot_type_drive_rate", "shot_type_other_rate"]:
                if pd.isna(row.get(c)) and c in b_row.index:
                    path_a.at[idx, c] = b_row[c]

    # Append PATH B-only rows (not in PATH A)
    a_keys = set(zip(path_a["game_id"].astype(str), path_a["player_id"].astype(str)))
    b_only = path_b[~path_b.apply(
        lambda r: (str(r["game_id"]), str(r["player_id"])) in a_keys, axis=1
    )]
    if len(b_only) > 0:
        print(f"PATH B-only rows appended: {len(b_only)}")
        merged = pd.concat([path_a, b_only], ignore_index=True)
    else:
        merged = path_a

    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Connecting to {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)

    # Build game_date lookup from multiple sources (rest_travel is most comprehensive)
    print("Building game_date lookup ...")
    game_date_map: dict = {}
    date_sources = [
        ("rest_travel", os.path.join(PROJECT_DIR, "data", "rest_travel.parquet"), "game_id", "game_date"),
        ("player_pf",   os.path.join(PROJECT_DIR, "data", "player_pf.parquet"),   "game_id", "game_date"),
        ("box_scores_db", None, None, None),  # sentinel for SQL
    ]
    for sname, path, gcol, dcol in date_sources:
        if path and os.path.exists(path):
            try:
                df = pd.read_parquet(path)
                for _, row in df[[gcol, dcol]].drop_duplicates().dropna().iterrows():
                    gid = str(row[gcol])
                    gdate = str(row[dcol])[:10]
                    if gid not in game_date_map:
                        game_date_map[gid] = gdate
                print(f"  {sname}: now {len(game_date_map)} dates")
            except Exception as e:
                print(f"  {sname} skipped: {e}")
        elif sname == "box_scores_db":
            try:
                date_df = pd.read_sql("SELECT DISTINCT game_id, game_date FROM box_scores", conn)
                for _, row in date_df.dropna().iterrows():
                    gid = str(row["game_id"])
                    if gid not in game_date_map:
                        game_date_map[gid] = str(row["game_date"])[:10]
                print(f"  box_scores_db: now {len(game_date_map)} dates")
            except Exception as e:
                print(f"  box_scores_db skipped: {e}")

    print(f"  Total game dates: {len(game_date_map)}")

    # PATH A: cv_features
    print("\n--- PATH A: cv_features ---")
    path_a = load_cv_features_shot_types(conn, game_date_map)

    # PATH B: shot_log_enriched with name resolution
    print("\n--- PATH B: shot_log_enriched ---")

    # Build name -> nba_id lookup from player stats parquets
    name_to_nba_id: dict = {}

    # Build from nba_api static players (5103 players, no network call)
    try:
        from nba_api.stats.static import players as nba_players
        for p in nba_players.get_players():
            nn = normalize_name(p["full_name"])
            if nn:
                name_to_nba_id[nn] = int(p["id"])
        print(f"  Loaded {len(name_to_nba_id)} names from nba_api.stats.static.players")
    except Exception as e:
        print(f"  nba_api player lookup skipped: {e}")

    print(f"Total name->nba_id entries: {len(name_to_nba_id)}")

    # Process all game dirs for PATH B
    game_dirs = sorted(glob.glob(os.path.join(TRACKING_ROOT, "*")))
    print(f"Processing {len(game_dirs)} game dirs ...")

    all_shots_b: list[pd.DataFrame] = []
    skipped = 0
    for i, gd in enumerate(game_dirs):
        df = process_game_dir_path_b(gd, name_to_nba_id, game_date_map)
        if df is None:
            skipped += 1
        else:
            all_shots_b.append(df)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(game_dirs)} dirs processed")

    # PATH B aggregation
    if all_shots_b:
        shots_b_all = pd.concat(all_shots_b, ignore_index=True)
        print(f"\nPATH B total shot rows: {len(shots_b_all)}")

        # Distribution check
        dist = shots_b_all["shot_type"].value_counts(normalize=True)
        print("\n--- Shot type distribution (PATH B raw) ---")
        for st, pct in dist.items():
            print(f"  {st}: {pct:.1%}")

        path_b_agg = aggregate_path_b(shots_b_all)
    else:
        print("No PATH B shots found")
        path_b_agg = pd.DataFrame()

    # Merge
    print("\n--- Merging PATH A + PATH B ---")
    merged = merge_paths(path_a, path_b_agg)

    if merged.empty:
        print("ERROR: No data in merged result. Aborting.")
        conn.close()
        sys.exit(1)

    # Ensure all required columns exist
    for c in ["shot_type_cs_rate", "shot_type_pu_rate",
               "shot_type_drive_rate", "shot_type_sb_rate", "shot_type_other_rate"]:
        if c not in merged.columns:
            merged[c] = np.nan

    # Fill game_date where missing via game_date_map
    if "game_date" not in merged.columns:
        merged["game_date"] = ""
    merged["game_id"] = merged["game_id"].astype(str)
    mask = merged["game_date"].isna() | merged["game_date"].eq("")
    merged.loc[mask, "game_date"] = merged.loc[mask, "game_id"].map(game_date_map)

    print(f"\n=== FINAL MERGED STATS ===")
    print(f"Total rows: {len(merged)}")
    print(f"Unique players: {merged['player_id'].nunique()}")
    print(f"Unique games: {merged['game_id'].nunique()}")
    print(f"game_date fill rate: {merged['game_date'].notna().mean():.1%}")

    # Distribution
    print("\n--- cs_rate distribution (PATH A) ---")
    valid = merged["shot_type_cs_rate"].dropna()
    print(f"  n={len(valid)}, mean={valid.mean():.3f}, "
          f"0.0={( valid==0).mean():.1%}, 1.0={(valid==1).mean():.1%}")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    merged.to_parquet(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
