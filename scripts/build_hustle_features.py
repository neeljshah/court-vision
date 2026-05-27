"""
build_hustle_features.py — Build hustle-stat season features from NBA hustle JSON files.

GRAIN: Per-season, per-player averages (NBA API leaguehustlestatsplayer endpoint).
       One row per (player_id, season). No game-level dates are available in the
       source data, so features are season-cumulative per-game averages — no rolling
       L5 window is possible. The output is keyed on (player_id, season) and intended
       for use as prior-season or same-season lookups in prop_pergame feature joins.

       There is NO leak risk because all values are per-game averages for that season
       (not end-of-season totals that would embed future games).

SOURCE: data/nba/hustle_stats_*.json (6 seasons: 2018-19 through 2024-25)
OUTPUT: data/cache/hustle_features.parquet

Features exported:
    hustle_deflections        — deflections per game
    hustle_contested_shots    — contested shots per game (2pt + 3pt combined)
    hustle_screen_assists     — screen assists per game
    hustle_box_outs           — box outs per game
    hustle_loose_balls        — loose balls recovered per game
    hustle_charges_drawn      — charges drawn per game
    hustle_games_played       — games played that season (used as weight / coverage signal)
"""

import json
import pathlib
import re
import sys
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "data" / "nba"
OUT_PATH = ROOT / "data" / "cache" / "hustle_features.parquet"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Season-to-year mapping helpers
# ---------------------------------------------------------------------------
SEASON_PATTERN = re.compile(r"hustle_stats_(\d{4}-\d{2})\.json$")

# Map '2024-25' -> '2024-25' (keep as-is for join keys)
def _parse_season(path: pathlib.Path) -> str:
    m = SEASON_PATTERN.search(path.name)
    return m.group(1) if m else "unknown"


# ---------------------------------------------------------------------------
# Schema normalization — handle two different NBA API response shapes
# ---------------------------------------------------------------------------
def _normalize_row(row: dict, season: str) -> dict | None:
    """Return a normalized dict with canonical field names, or None if invalid."""
    try:
        player_id = int(float(row.get("player_id", 0)))
        if player_id == 0:
            return None

        player_name = str(row.get("player_name", "")).strip()

        # Games played: older files use 'g', newer use 'games_played'
        games_played = float(row.get("g") or row.get("games_played") or 0)

        # Deflections — consistent across all schemas
        deflections = float(row.get("deflections") or 0)

        # Contested shots — older: 'contested_shots', newer: same key
        contested_shots = float(row.get("contested_shots") or 0)

        # Screen assists — older: 'screen_assists', same in newer
        screen_assists = float(row.get("screen_assists") or 0)

        # Box outs — older: 'box_outs', newer: 'box_outs'
        box_outs = float(row.get("box_outs") or 0)

        # Loose balls recovered — older: 'loose_balls_recovered', newer: same
        loose_balls = float(row.get("loose_balls_recovered") or 0)

        # Charges drawn — consistent
        charges_drawn = float(row.get("charges_drawn") or 0)

        return {
            "player_id": player_id,
            "player_name": player_name,
            "season": season,
            "hustle_games_played": games_played,
            "hustle_deflections": deflections,
            "hustle_contested_shots": contested_shots,
            "hustle_screen_assists": screen_assists,
            "hustle_box_outs": box_outs,
            "hustle_loose_balls": loose_balls,
            "hustle_charges_drawn": charges_drawn,
        }
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    files = sorted(SRC_DIR.glob("hustle_stats_*.json"))
    if not files:
        print(f"ERROR: No hustle_stats_*.json files found in {SRC_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} hustle stat files:")
    for f in files:
        print(f"  {f.name}")

    records = []
    for fpath in files:
        season = _parse_season(fpath)
        try:
            with open(fpath, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARN: skipping {fpath.name} — {exc}", file=sys.stderr)
            continue

        if not isinstance(raw, list):
            print(f"  WARN: {fpath.name} is not a list, skipping", file=sys.stderr)
            continue

        season_rows = 0
        for row in raw:
            normed = _normalize_row(row, season)
            if normed is not None:
                records.append(normed)
                season_rows += 1

        print(f"  {fpath.name}: {season_rows} valid rows")

    if not records:
        print("ERROR: No valid records parsed.", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(records)

    # Deduplicate: if a player appears twice in a season (traded), keep the row
    # with more games played (likely the season-total entry).
    df = (
        df.sort_values("hustle_games_played", ascending=False)
        .drop_duplicates(subset=["player_id", "season"])
        .sort_values(["player_id", "season"])
        .reset_index(drop=True)
    )

    # Cast types
    feature_cols = [
        "hustle_deflections",
        "hustle_contested_shots",
        "hustle_screen_assists",
        "hustle_box_outs",
        "hustle_loose_balls",
        "hustle_charges_drawn",
    ]
    for col in feature_cols + ["hustle_games_played"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ---------------------------------------------------------------------------
    # Write parquet
    # ---------------------------------------------------------------------------
    df.to_parquet(OUT_PATH, index=False)
    print(f"\nWrote {len(df)} rows -> {OUT_PATH}")

    # ---------------------------------------------------------------------------
    # Diagnostics
    # ---------------------------------------------------------------------------
    print(f"\nGRAIN: per-season, per-player (no game-level dates in source)")
    print(f"Seasons covered: {sorted(df['season'].unique())}")
    print(f"Total rows: {len(df)}")
    print(f"Unique players: {df['player_id'].nunique()}")

    print("\nNull rates:")
    for col in feature_cols:
        null_pct = df[col].isna().mean() * 100
        print(f"  {col:35s}: {null_pct:.2f}%")

    print("\nSample rows (known hustlers):")
    hustlers = ["Marcus Smart", "Draymond Green", "Alex Caruso"]
    sample = df[df["player_name"].isin(hustlers) & (df["season"] == "2023-24")]
    if not sample.empty:
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 200)
        print(sample[["player_name", "season"] + feature_cols].to_string(index=False))
    else:
        print("  (no 2023-24 rows found for sample hustlers)")


if __name__ == "__main__":
    main()
