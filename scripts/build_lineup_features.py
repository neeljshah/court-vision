"""
build_lineup_features.py
Extract per-player lineup statistics from data/nba/lineups/ JSON files.

Output: data/cache/lineup_features.parquet
Grain:  (player_id, season)
"""
import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
LINEUP_DIR = REPO_ROOT / "data" / "nba" / "lineups"
OUT_PATH   = REPO_ROOT / "data" / "cache" / "lineup_features.parquet"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MIN_LINEUP_MINUTES = 10.0   # noise floor
FILENAME_RE = re.compile(r"lineup_splits_[A-Z]+_(\d{4}-\d{2})\.json$")


def parse_player_ids(group_id: str) -> list[int]:
    """'-203991-1627749-...-' → [203991, 1627749, ...]"""
    parts = [p for p in group_id.split("-") if p.strip()]
    ids = []
    for p in parts:
        try:
            ids.append(int(p))
        except ValueError:
            pass
    return ids


def load_lineups(lineup_dir: Path) -> pd.DataFrame:
    """Load all JSON files → flat DataFrame with (player_id, season, lineup_id, minutes, net_rating, pace)."""
    records = []
    skipped_files = 0
    skipped_rows  = 0

    for fname in sorted(os.listdir(lineup_dir)):
        m = FILENAME_RE.match(fname)
        if not m:
            continue
        season = m.group(1)          # e.g. "2023-24"
        fpath  = lineup_dir / fname

        try:
            with open(fpath, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as e:
            print(f"  WARN skip {fname}: {e}", file=sys.stderr)
            skipped_files += 1
            continue

        if not isinstance(raw, list):
            print(f"  WARN skip {fname}: not a list", file=sys.stderr)
            skipped_files += 1
            continue

        for row in raw:
            # Prefer 'minutes', fall back to 'min'
            mins = row.get("minutes") or row.get("min")
            try:
                mins = float(mins)
            except (TypeError, ValueError):
                skipped_rows += 1
                continue

            if mins < MIN_LINEUP_MINUTES:
                skipped_rows += 1
                continue

            gid = row.get("group_id", "")
            player_ids = parse_player_ids(gid)
            if len(player_ids) != 5:
                skipped_rows += 1
                continue

            net_rating = row.get("net_rating")
            pace       = row.get("pace")

            try:
                net_rating = float(net_rating) if net_rating is not None else float("nan")
                pace       = float(pace)       if pace is not None       else float("nan")
            except (TypeError, ValueError):
                net_rating = float("nan")
                pace       = float("nan")

            lineup_id = gid   # keep original string as lineup key

            for pid in player_ids:
                records.append({
                    "player_id": pid,
                    "season":    season,
                    "lineup_id": lineup_id,
                    "minutes":   mins,
                    "net_rating": net_rating,
                    "pace":       pace,
                })

    if skipped_files:
        print(f"  WARN: skipped {skipped_files} files")
    if skipped_rows:
        print(f"  INFO: filtered {skipped_rows} rows (< {MIN_LINEUP_MINUTES} min or malformed)")

    return pd.DataFrame(records)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per (player_id, season) → lineup feature columns."""
    rows = []

    for (player_id, season), grp in df.groupby(["player_id", "season"], sort=False):
        # Sort lineups by minutes descending
        grp_sorted = grp.sort_values("minutes", ascending=False).reset_index(drop=True)

        total_player_min = grp_sorted["minutes"].sum()

        # ── lineup_top1 ──────────────────────────────────────────────────────
        top1           = grp_sorted.iloc[0]
        top1_net       = top1["net_rating"]
        top1_mins      = top1["minutes"]
        top1_min_share = top1_mins / total_player_min if total_player_min > 0 else float("nan")

        # ── lineup_top3 ──────────────────────────────────────────────────────
        top3       = grp_sorted.head(3)
        top3_net   = top3["net_rating"].mean()   # simple average; all are "most played"

        # ── unique 5-man lineups ──────────────────────────────────────────────
        n_unique = grp_sorted["lineup_id"].nunique()

        # ── minutes-weighted pace ─────────────────────────────────────────────
        valid_pace = grp_sorted.dropna(subset=["pace"])
        if len(valid_pace) > 0 and valid_pace["minutes"].sum() > 0:
            avg_pace = (valid_pace["pace"] * valid_pace["minutes"]).sum() / valid_pace["minutes"].sum()
        else:
            avg_pace = float("nan")

        rows.append({
            "player_id":              int(player_id),
            "season":                 season,
            "lineup_top3_net_rating": round(float(top3_net), 4),
            "lineup_top1_net_rating": round(float(top1_net), 4),
            "lineup_top1_min_share":  round(float(top1_min_share), 4),
            "lineup_unique_5mans":    int(n_unique),
            "lineup_avg_pace_on":     round(float(avg_pace), 4),
        })

    return pd.DataFrame(rows)


def print_diagnostics(feat: pd.DataFrame) -> None:
    print(f"\n{'='*60}")
    print(f"Rows:    {len(feat):,}")
    print(f"Seasons: {sorted(feat['season'].unique())}")
    print(f"\nNull rates:")
    for col in feat.columns:
        n = feat[col].isna().sum()
        if n > 0:
            print(f"  {col}: {n/len(feat)*100:.1f}%")
        else:
            print(f"  {col}: 0.0%")

    print(f"\nSample — Jokic (203999) latest season:")
    jokic = feat[feat["player_id"] == 203999].sort_values("season", ascending=False).head(3)
    print(jokic.to_string(index=False))

    print(f"\nSample — Bones Hyland (1630560):")
    bones = feat[feat["player_id"] == 1630560].sort_values("season", ascending=False).head(3)
    if bones.empty:
        print("  Not found")
    else:
        print(bones.to_string(index=False))
    print('='*60)


def main() -> None:
    print(f"Loading lineup JSONs from {LINEUP_DIR} ...")
    df = load_lineups(LINEUP_DIR)
    print(f"Loaded {len(df):,} player-lineup rows (after {MIN_LINEUP_MINUTES}-min filter)")

    if df.empty:
        print("ERROR: no data loaded. Exiting.", file=sys.stderr)
        sys.exit(1)

    print("Aggregating per (player_id, season) ...")
    feat = build_features(df)

    print(f"Writing -> {OUT_PATH}")
    feat.to_parquet(OUT_PATH, index=False, engine="pyarrow")

    print_diagnostics(feat)
    print(f"\nDone. Parquet saved: {str(OUT_PATH)}")


if __name__ == "__main__":
    main()
