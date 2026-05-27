"""
build_on_off_features.py
Idempotent. Reads data/nba/on_off_*.json, computes per-(player_id, season)
on/off split features, writes data/cache/on_off_features.parquet.

Source schema per record:
  player_id, player_name, team_abbreviation,
  on_court_plus_minus, off_court_plus_minus, on_off_diff, minutes_on

Derived features
  on_off_net_rating_diff  = on_court_plus_minus - off_court_plus_minus
                            (same as on_off_diff; stored explicitly)
  on_off_orating_diff     = not available in source; set to NaN
  on_off_drating_diff     = not available in source; set to NaN
  on_off_pace_diff        = not available in source; set to NaN
  on_off_impact_z         = z-score of on_off_net_rating_diff across all
                            players in that season (standardised impact)
  on_off_min_weight       = minutes_on / max(minutes_on in season)
                            (confidence: near 1 for full-time starters)

Grain: (player_id, season) — one row per player per season file.
Season is parsed from the filename, e.g. on_off_2024-25.json -> "2024-25".
"""
import json
import sys
import pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
ON_OFF_DIR = ROOT / "data" / "nba"
OUT_PATH = ROOT / "data" / "cache" / "on_off_features.parquet"

# ── helpers ──────────────────────────────────────────────────────────────────

def season_from_path(p: pathlib.Path) -> str:
    """Extract season string from filename like on_off_2024-25.json."""
    stem = p.stem  # on_off_2024-25
    parts = stem.split("_")
    # last part is the season, e.g. "2024-25"
    return parts[-1]


def load_season(p: pathlib.Path, season: str) -> pd.DataFrame:
    with open(p, encoding="utf-8") as f:
        records = json.load(f)

    rows = []
    for r in records:
        rows.append({
            "player_id":              int(r["player_id"]),
            "player_name":            r.get("player_name", ""),
            "team_abbreviation":      r.get("team_abbreviation", ""),
            "season":                 season,
            "on_court_plus_minus":    float(r.get("on_court_plus_minus", np.nan)),
            "off_court_plus_minus":   float(r.get("off_court_plus_minus", np.nan)),
            "on_off_diff":            float(r.get("on_off_diff", np.nan)),
            "minutes_on":             float(r.get("minutes_on", np.nan)),
        })

    df = pd.DataFrame(rows)
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    # Primary target feature — net rating diff (same as on_off_diff in source)
    df["on_off_net_rating_diff"] = (
        df["on_court_plus_minus"] - df["off_court_plus_minus"]
    )

    # Placeholders for features not available in this data source
    df["on_off_orating_diff"] = np.nan
    df["on_off_drating_diff"] = np.nan
    df["on_off_pace_diff"]    = np.nan

    # Z-score impact within each season (relative elevation vs peers)
    def z_score(series: pd.Series) -> pd.Series:
        std = series.std(ddof=0)
        if std == 0 or np.isnan(std):
            return pd.Series(np.zeros(len(series)), index=series.index)
        return (series - series.mean()) / std

    df["on_off_impact_z"] = df.groupby("season")["on_off_net_rating_diff"].transform(z_score)

    # Minutes-weighted confidence (0–1 within each season)
    def min_weight(series: pd.Series) -> pd.Series:
        mx = series.max()
        if mx == 0 or np.isnan(mx):
            return pd.Series(np.zeros(len(series)), index=series.index)
        return series / mx

    df["on_off_min_weight"] = df.groupby("season")["minutes_on"].transform(min_weight)

    return df


def report(df: pd.DataFrame) -> None:
    feature_cols = [
        "on_off_net_rating_diff",
        "on_off_orating_diff",
        "on_off_drating_diff",
        "on_off_pace_diff",
        "on_off_impact_z",
        "on_off_min_weight",
    ]
    print("\n=== on_off_features.parquet ===")
    print("Grain   : (player_id, season)")
    print(f"Rows    : {len(df):,}")
    print(f"Seasons : {sorted(df['season'].unique())}")
    print(f"\nNull rates (feature cols):")
    for col in feature_cols:
        null_pct = df[col].isna().mean() * 100
        print(f"  {col:<30s} {null_pct:5.1f}%")

    # Sample row for Jokic (203999)
    jokic = df[df["player_id"] == 203999]
    if not jokic.empty:
        print("\nSample row - Nikola Jokic (203999):")
        row = jokic.iloc[0]
        for col in ["player_name", "team_abbreviation", "season", "minutes_on",
                    "on_court_plus_minus", "off_court_plus_minus",
                    "on_off_net_rating_diff", "on_off_impact_z", "on_off_min_weight"]:
            val = row[col]
            # Encode safely for narrow terminals
            val_str = str(val).encode("ascii", errors="replace").decode("ascii")
            print(f"  {col:<30s} {val_str}")
    else:
        print("\nJokic (203999) not found in dataset.")


def main() -> None:
    # Discover all on_off_*.json files
    files = sorted(ON_OFF_DIR.glob("on_off_*.json"))
    if not files:
        print(f"ERROR: no on_off_*.json files found in {ON_OFF_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} on_off file(s): {[f.name for f in files]}")

    frames = []
    for fp in files:
        season = season_from_path(fp)
        df_s = load_season(fp, season)
        print(f"  {fp.name}: {len(df_s)} rows (season={season})")
        frames.append(df_s)

    df = pd.concat(frames, ignore_index=True)

    # Deduplicate: if same player appears in same season via multiple files,
    # keep the one with most minutes_on
    df = (
        df.sort_values("minutes_on", ascending=False)
          .drop_duplicates(subset=["player_id", "season"], keep="first")
          .reset_index(drop=True)
    )

    df = compute_features(df)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    print(f"\nWritten: {OUT_PATH}")

    report(df)


if __name__ == "__main__":
    main()
