"""asof_coverage_receipt.py — per-table, per-season row/game coverage receipt.

Reads every parquet under data/domains/basketball_nba/ plus
data/player_adv_stats.parquet, data/team_advanced_stats.parquet,
data/cache/player_tracking_features.parquet, data/cache/hustle_features*.parquet.

Maps each table's rows to a season via (in priority order): the table's own
`season` column, a `game_id` column joined against games.parquet, or a
date/game_date column bucketed into the season's [min_date, max_date] range
taken from games.parquet. Tables with none of these are reported as
"unknown".

Writes data/cache/asof_coverage.json:
    {table: {season: {rows, games, max_date}}, generated_at, rule,
     season_game_counts}
and prints the same as a flat table.

CLI:
    python -m scripts.platformkit.asof_coverage_receipt
    python -m scripts.platformkit.asof_coverage_receipt --check asof_features --season 2025-26
        exits 3 when that table's 2025-26 coverage is < 95% of the season's
        game count in games.parquet (a "challenger may not train on a table
        with < 0.95 * season games" gate).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(_HERE))
_NBA_DOMAIN = os.path.join(PROJECT_DIR, "data", "domains", "basketball_nba")
_GAMES = os.path.join(_NBA_DOMAIN, "games.parquet")
_OUT = os.path.join(PROJECT_DIR, "data", "cache", "asof_coverage.json")
RULE = "challenger may not train on a table with < 0.95 * season games"


def _table_paths():
    paths = sorted(glob.glob(os.path.join(_NBA_DOMAIN, "*.parquet")))
    paths += [
        os.path.join(PROJECT_DIR, "data", "player_adv_stats.parquet"),
        os.path.join(PROJECT_DIR, "data", "team_advanced_stats.parquet"),
        os.path.join(PROJECT_DIR, "data", "cache", "player_tracking_features.parquet"),
    ]
    paths += sorted(glob.glob(os.path.join(PROJECT_DIR, "data", "cache", "hustle_features*.parquet")))
    return [p for p in paths if os.path.exists(p)]


def load_games(games_path=None):
    """Return (game_id -> season) map, season -> (min_date, max_date) ranges,
    and season -> distinct game count, all from games.parquet."""
    df = pd.read_parquet(games_path or _GAMES)
    df["game_id"] = df["game_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"])
    gid_season = dict(zip(df["game_id"], df["season"].astype(str)))
    ranges = {s: (g["date"].min(), g["date"].max()) for s, g in df.groupby("season")}
    season_game_counts = df.groupby("season")["game_id"].nunique().to_dict()
    return gid_season, ranges, season_game_counts


def _season_for_dates(dates: pd.Series, ranges: dict) -> pd.Series:
    """Bucket a date series into the season whose [min,max] range contains it."""
    out = pd.Series(["unknown"] * len(dates), index=dates.index, dtype=object)
    for season, (lo, hi) in ranges.items():
        out[(dates >= lo) & (dates <= hi)] = season
    return out


def table_coverage(path: str, gid_season: dict, ranges: dict) -> dict:
    """Return {season: {rows, games, max_date}} for one parquet table."""
    df = pd.read_parquet(path)
    cols = set(df.columns)
    date_col = next((c for c in ("date", "game_date") if c in cols), None)

    if "season" in cols:
        season = df["season"].astype(str)
    elif "game_id" in cols:
        season = df["game_id"].astype(str).map(gid_season).fillna("unknown")
    elif date_col:
        season = _season_for_dates(pd.to_datetime(df[date_col]), ranges)
    else:
        season = pd.Series(["unknown"] * len(df), index=df.index)

    out = {}
    for s, sub in df.groupby(season):
        entry = {"rows": int(len(sub))}
        entry["games"] = int(sub["game_id"].astype(str).nunique()) if "game_id" in cols else None
        entry["max_date"] = str(pd.to_datetime(sub[date_col]).max().date()) if date_col else None
        out[str(s)] = entry
    return out


def build_receipt() -> dict:
    gid_season, ranges, season_game_counts = load_games()
    tables = {}
    for path in _table_paths():
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            tables[name] = table_coverage(path, gid_season, ranges)
        except Exception as e:  # noqa: BLE001 — one bad table must not sink the receipt
            tables[name] = {"error": str(e)}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rule": RULE,
        "season_game_counts": season_game_counts,
        "tables": tables,
    }


def print_table(receipt: dict) -> None:
    print(f"{'table':38s} {'season':9s} {'rows':>8s} {'games':>8s} {'max_date':>12s}")
    for table, seasons in receipt["tables"].items():
        if "error" in seasons:
            print(f"{table:38s} ERROR: {seasons['error']}")
            continue
        for season, entry in sorted(seasons.items()):
            games = entry["games"] if entry["games"] is not None else "-"
            print(f"{table:38s} {season:9s} {entry['rows']:8d} {str(games):>8s} {str(entry['max_date']):>12s}")


def check_coverage(receipt: dict, table: str, season: str) -> float:
    """Return coverage fraction (games, or rows if the table has no game_id) for table/season."""
    entry = receipt["tables"].get(table, {})
    season_games = receipt["season_game_counts"].get(season, 0)
    if not season_games or "error" in entry or season not in entry:
        return 0.0
    se = entry[season]
    have = se["games"] if se.get("games") is not None else se["rows"]
    return have / season_games


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", default=None, help="table name (parquet stem) to gate-check")
    ap.add_argument("--season", default=None, help="season string, e.g. 2025-26")
    ap.add_argument("--out", default=_OUT)
    args = ap.parse_args()

    receipt = build_receipt()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, default=str)
    print(f"wrote {args.out}")
    print_table(receipt)

    if args.check:
        if not args.season:
            print("--check requires --season", file=sys.stderr)
            sys.exit(2)
        pct = check_coverage(receipt, args.check, args.season)
        print(f"[check] {args.check} {args.season}: {pct:.1%} of season game count")
        if pct < 0.95:
            sys.exit(3)


if __name__ == "__main__":
    main()
