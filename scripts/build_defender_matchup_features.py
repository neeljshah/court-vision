"""Build player-level defender matchup features from raw per-game JSON files.

Reads every data/defender_matchups/raw_*.json, joins game metadata from
data/rest_travel.parquet, enriches with defender height from
data/cache/playerinfo/<id>.json, then computes rolling/last-10 features keyed
on (off_player_id, game_date).

Output: data/cache/defender_matchup_features.parquet
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
RAW_DIR = REPO / "data" / "defender_matchups"
OUT_PATH = REPO / "data" / "cache" / "defender_matchup_features.parquet"
PLAYERINFO_DIR = REPO / "data" / "cache" / "playerinfo"

# Ordered list of candidate parquets that supply (game_id, game_date).
# rest_travel covers all seasons (2021-22 through 2025-26), so it is preferred.
# season_games / games would be ideal if they exist.
GAME_META_CANDIDATES = [
    REPO / "data" / "season_games.parquet",
    REPO / "data" / "games.parquet",
    REPO / "data" / "rest_travel.parquet",
    REPO / "data" / "defender_matchups_2024-25.parquet",
]

REQUIRED_COLS = {"game_id", "game_date"}


# ── helpers ───────────────────────────────────────────────────────────────────

def height_to_inches(height_str: Optional[str]) -> Optional[float]:
    """Convert 'feet-inches' string (e.g. '6-9') to total inches."""
    if not height_str or "-" not in str(height_str):
        return None
    parts = str(height_str).split("-")
    try:
        return float(parts[0]) * 12 + float(parts[1])
    except (ValueError, IndexError):
        return None


def load_playerinfo_heights() -> Dict[int, float]:
    """Return {player_id: height_in_inches} for all cached playerinfo files."""
    heights: Dict[int, float] = {}
    for path in PLAYERINFO_DIR.glob("*.json"):
        try:
            with open(path) as fh:
                d = json.load(fh)
            info = d["common_player_info"][0]
            pid = int(info["PERSON_ID"])
            h = height_to_inches(info.get("HEIGHT"))
            if h is not None:
                heights[pid] = h
        except Exception:
            pass
    return heights


def derive_season(game_id: str) -> str:
    """Derive NBA season string like '2024-25' from a game_id like '0022400001'."""
    yy = int(game_id[3:5])
    return f"20{yy}-{str(yy + 1).zfill(2)}"


def load_game_meta() -> pd.DataFrame:
    """Load game_id → game_date mapping from the first available parquet.

    Falls back to deriving dates from rest_travel.parquet (which covers
    all but one game).  Season is derived from the game_id format.
    """
    for candidate in GAME_META_CANDIDATES:
        if not candidate.exists():
            continue
        df = pd.read_parquet(candidate, columns=list(REQUIRED_COLS & set(
            pd.read_parquet(candidate, columns=[]).columns
        )) or None)
        # reload properly
        df = pd.read_parquet(candidate)
        if REQUIRED_COLS.issubset(df.columns):
            meta = (
                df[["game_id", "game_date"]]
                .drop_duplicates("game_id")
                .copy()
            )
            meta["game_id"] = meta["game_id"].astype(str)
            meta["game_date"] = pd.to_datetime(meta["game_date"]).dt.normalize()
            meta["season"] = meta["game_id"].map(derive_season)
            print(f"  game meta loaded from: {candidate.name} ({len(meta)} games)")
            return meta
    raise FileNotFoundError(
        f"No suitable game metadata parquet found among: "
        + ", ".join(str(c) for c in GAME_META_CANDIDATES)
    )


def load_raw_matchups() -> pd.DataFrame:
    """Read all raw_*.json files and return a single concatenated DataFrame."""
    files = sorted(glob.glob(str(RAW_DIR / "raw_*.json")))
    if not files:
        raise FileNotFoundError(f"No raw_*.json files found in {RAW_DIR}")
    print(f"  Loading {len(files)} raw JSON files …")
    frames = []
    for path in files:
        try:
            with open(path) as fh:
                rows = json.load(fh)
            if rows:
                frames.append(pd.DataFrame(rows))
        except Exception as exc:
            print(f"  WARN: skipping {os.path.basename(path)}: {exc}")
    df = pd.concat(frames, ignore_index=True)
    df["game_id"] = df["game_id"].astype(str)
    numeric_cols = [
        "partial_possessions", "switches_on", "player_points",
        "matchup_fg_made", "matchup_fg_attempted", "matchup_fg_pct",
        "matchup_3pm", "matchup_3pa", "matchup_3p_pct",
        "help_blocks", "matchup_minutes_float",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    print(f"  Total matchup rows: {len(df):,}")
    return df


def game_level_agg(df: pd.DataFrame, heights: Dict[int, float]) -> pd.DataFrame:
    """Aggregate matchup rows to (off_player_id, game_id) level.

    Returns one row per offender per game with the per-game features
    needed for rolling calculations.
    """
    # Per-game, per-offender totals for FG% and 3P%
    game_off = (
        df.groupby(["game_id", "off_player_id", "off_player_name"], as_index=False)
        .agg(
            total_fg_made=("matchup_fg_made", "sum"),
            total_fg_att=("matchup_fg_attempted", "sum"),
            total_3pm=("matchup_3pm", "sum"),
            total_3pa=("matchup_3pa", "sum"),
            total_poss=("partial_possessions", "sum"),
            total_switches=("switches_on", "sum"),
            total_help_blocks=("help_blocks", "sum"),
        )
    )
    game_off["fg_pct_game"] = np.where(
        game_off["total_fg_att"] > 0,
        game_off["total_fg_made"] / game_off["total_fg_att"],
        np.nan,
    )
    game_off["3p_pct_game"] = np.where(
        game_off["total_3pa"] > 0,
        game_off["total_3pm"] / game_off["total_3pa"],
        np.nan,
    )
    # partial_poss_share proxy: mean partial_poss / 100 across all defenders
    n_defenders = (
        df.groupby(["game_id", "off_player_id"])["def_player_id"]
        .count()
        .reset_index(name="n_defenders")
    )
    game_off = game_off.merge(n_defenders, on=["game_id", "off_player_id"], how="left")
    game_off["matchup_partial_poss_share"] = np.where(
        game_off["n_defenders"] > 0,
        game_off["total_poss"] / game_off["n_defenders"] / 100.0,
        np.nan,
    )
    game_off["switches_per_poss"] = np.where(
        game_off["total_poss"] > 0,
        game_off["total_switches"] / game_off["total_poss"],
        np.nan,
    )

    # Primary defender = the one with most partial_possessions vs this offender
    primary = (
        df.sort_values("partial_possessions", ascending=False)
        .groupby(["game_id", "off_player_id"], as_index=False)
        .first()[["game_id", "off_player_id", "def_player_id"]]
        .rename(columns={"def_player_id": "primary_def_id"})
    )
    game_off = game_off.merge(primary, on=["game_id", "off_player_id"], how="left")

    # Defender height from playerinfo cache
    game_off["primary_def_height_in"] = (
        game_off["primary_def_id"].map(heights).astype(float)
    )

    # Offender height (if available) for height_advantage
    # Key off by off_player_id (same cache)
    off_height_map: Dict[int, float] = {
        pid: h for pid, h in heights.items()
    }
    game_off["off_height_in"] = game_off["off_player_id"].map(off_height_map).astype(float)
    game_off["height_advantage_in"] = game_off["off_height_in"] - game_off["primary_def_height_in"]

    return game_off


def rolling_features(game_off: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """Compute shift(1).rolling(10) features per offender and return final parquet rows."""
    # Join game date + season
    merged = game_off.merge(meta, on="game_id", how="left")
    merged = merged.sort_values(["off_player_id", "game_date"])

    # Rolling (no leakage — shift 1 before rolling)
    def roll10(series: pd.Series) -> pd.Series:
        return series.shift(1).rolling(10, min_periods=1).mean()

    result_rows = []
    for off_id, grp in merged.groupby("off_player_id", sort=False):
        grp = grp.sort_values("game_date").copy()
        grp["matchup_fg_pct_l10"] = roll10(grp["fg_pct_game"])
        grp["matchup_3p_pct_l10"] = roll10(grp["3p_pct_game"])
        grp["help_blocks_per_game"] = roll10(grp["total_help_blocks"])
        result_rows.append(grp)

    if not result_rows:
        return pd.DataFrame()

    out = pd.concat(result_rows, ignore_index=True)

    # Stable placeholder column (Wave 2 will fill)
    out["primary_def_def_rating"] = np.nan

    keep = [
        "game_id", "game_date", "season",
        "off_player_id", "off_player_name",
        "matchup_fg_pct_l10",
        "matchup_partial_poss_share",
        "switches_per_poss",
        "primary_def_height_in",
        "primary_def_def_rating",
        "height_advantage_in",
        "help_blocks_per_game",
        "matchup_3p_pct_l10",
    ]
    # Ensure all columns present
    for col in keep:
        if col not in out.columns:
            out[col] = np.nan

    return out[keep].copy()


def null_rate_summary(df: pd.DataFrame) -> None:
    """Print null-rate per feature column."""
    feature_cols = [c for c in df.columns if c not in {
        "game_id", "game_date", "season", "off_player_id", "off_player_name"
    }]
    print(f"\nNull-rate summary ({len(df):,} rows):")
    for col in feature_cols:
        rate = df[col].isna().mean()
        print(f"  {col:<35s} {rate:.1%}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point: build and write defender_matchup_features.parquet."""
    print("=== build_defender_matchup_features ===")

    print("\n[1] Loading player height cache …")
    heights = load_playerinfo_heights()
    print(f"  Heights loaded for {len(heights):,} players")

    print("\n[2] Loading game metadata …")
    meta = load_game_meta()

    print("\n[3] Loading raw matchup JSONs …")
    raw = load_raw_matchups()

    print("\n[4] Game-level aggregation …")
    game_off = game_level_agg(raw, heights)
    print(f"  Game-offender rows: {len(game_off):,}")

    print("\n[5] Computing rolling features …")
    features = rolling_features(game_off, meta)
    print(f"  Feature rows: {len(features):,}")

    # Idempotent: sort for stable output
    features = features.sort_values(
        ["off_player_id", "game_date", "game_id"]
    ).reset_index(drop=True)

    print("\n[6] Writing parquet …")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(OUT_PATH, index=False)
    print(f"  Written → {OUT_PATH}")

    null_rate_summary(features)
    print(f"\nDone. Rows written: {len(features):,}")


if __name__ == "__main__":
    main()
