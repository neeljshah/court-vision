"""snapshot_lines_archive.py — nightly self-snapshot archiver for prop lines + starters.

Appends today's data/lines/<date>_<book>.csv captures and rotowire_lineups_parsed.json
into APPEND-ONLY dated parquet archives (data/cache/lines_archive/).
Idempotent: re-running the same date adds 0 rows.  Never deletes prior dates.
Every row carries snapshot_date + captured_at for leak-safe walk-forward filtering.

Usage:
    python scripts/ingest/snapshot_lines_archive.py            # today
    python scripts/ingest/snapshot_lines_archive.py --date 2026-05-30
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]  # nba-ai-system/ (script-relative, RunPod-safe)
_LINES_DIR = _ROOT / "data" / "lines"
_ROTOWIRE_PATH = _ROOT / "data" / "cache" / "rotowire_lineups_parsed.json"
_DEFAULT_OUT_DIR = _ROOT / "data" / "cache" / "lines_archive"

_PROP_COLS = [
    "snapshot_date",
    "game_date",
    "player_name",
    "player_id",
    "stat",
    "book",
    "line",
    "over_price",
    "under_price",
    "captured_at",
    "game_id",
]
_PROP_DEDUP_KEY = ["snapshot_date", "captured_at", "book", "game_id", "player_name", "stat"]
_STARTER_COLS = [
    "snapshot_date",
    "game_date",
    "team",
    "player_name",
    "position",
    "status",
    "is_starter",
    "lineup_order",
]
_STARTER_DEDUP_KEY = ["snapshot_date", "game_date", "team", "player_name"]
_MAINLINE_SUFFIXES = ("_mainline",)  # game-level spread/total files — skip
_PROP_REQUIRED = {"captured_at", "book", "player_name", "stat", "line"}


def _is_prop_file(basename: str) -> bool:
    """Return True if the file looks like a per-player prop file (not mainline)."""
    stem = basename.replace(".csv", "")
    for suf in _MAINLINE_SUFFIXES:
        if stem.endswith(suf):
            return False
    return True


def _read_prop_csv(path: str, snapshot_date: str) -> Optional[pd.DataFrame]:
    """Parse one prop CSV, returning a DataFrame with canonical columns or None."""
    try:
        df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    except Exception:
        return None

    if df.empty or not _PROP_REQUIRED.issubset(df.columns):
        return None

    # Normalise captured_at to UTC-aware timestamp
    df["captured_at"] = pd.to_datetime(
        df["captured_at"], utc=True, errors="coerce"
    )
    df = df.dropna(subset=["captured_at"])

    # Derive game_date from start_time if present, else from the filename date prefix
    filename_date = os.path.basename(path)[:10]  # "YYYY-MM-DD"
    if "start_time" in df.columns and df["start_time"].notna().any():
        df["game_date"] = (
            pd.to_datetime(df["start_time"], utc=True, errors="coerce")
            .dt.date.astype(str)
        )
        df["game_date"] = df["game_date"].fillna(filename_date)
    else:
        df["game_date"] = filename_date

    df["snapshot_date"] = snapshot_date

    # Coerce numeric columns
    for col in ("line", "over_price", "under_price"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Ensure optional columns exist with NaN if absent
    for col in ("player_id", "game_id", "over_price", "under_price"):
        if col not in df.columns:
            df[col] = pd.NA

    # Store captured_at as ISO string for parquet portability
    df["captured_at"] = df["captured_at"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Keep only canonical columns
    out = df.reindex(columns=_PROP_COLS)
    out["player_name"] = out["player_name"].astype(str).str.strip()
    out["stat"] = out["stat"].astype(str).str.strip().str.lower()
    out["book"] = out["book"].astype(str).str.strip().str.lower()
    # game_id may be int or str depending on book — normalise to string
    out["game_id"] = out["game_id"].fillna("").astype(str).str.strip()
    # player_id: keep as string too to avoid int/str mixed-type conflicts
    out["player_id"] = out["player_id"].fillna("").astype(str).str.strip()
    return out[out["player_name"].str.len() > 0]


def _load_prop_lines(snapshot_date: str, lines_dir: Path) -> pd.DataFrame:
    """Concat all prop CSVs for snapshot_date from lines_dir."""
    pattern = str(lines_dir / f"{snapshot_date}_*.csv")
    frames: list[pd.DataFrame] = []
    for path in sorted(glob.glob(pattern)):
        basename = os.path.basename(path)
        if basename.endswith(".stale"):
            continue
        if not _is_prop_file(basename):
            continue
        df = _read_prop_csv(path, snapshot_date)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=_PROP_COLS)
    return pd.concat(frames, ignore_index=True)


def _load_starters(snapshot_date: str, rotowire_path: Path) -> pd.DataFrame:
    """Parse rotowire_lineups_parsed.json into a flat starters DataFrame."""
    if not rotowire_path.exists():
        return pd.DataFrame(columns=_STARTER_COLS)

    try:
        with open(rotowire_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return pd.DataFrame(columns=_STARTER_COLS)

    # game_date stored in the JSON (as_of_date is the capture date for starters)
    game_date: str = data.get("game_date") or data.get("as_of_date") or snapshot_date
    teams: dict = data.get("teams", {})

    rows: list[dict] = []
    for team, players in teams.items():
        for p in players:
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "game_date": str(game_date),
                    "team": str(team).strip().upper(),
                    "player_name": str(p.get("player_name", "")).strip(),
                    "position": str(p.get("position", "")).strip(),
                    "status": str(p.get("status", "")).strip(),
                    "is_starter": bool(p.get("is_starter", False)),
                    "lineup_order": int(p.get("lineup_order", -1)),
                }
            )

    if not rows:
        return pd.DataFrame(columns=_STARTER_COLS)

    df = pd.DataFrame(rows, columns=_STARTER_COLS)
    return df[df["player_name"].str.len() > 0]


def _append_to_archive(
    new_rows: pd.DataFrame,
    archive_path: Path,
    dedup_key: list[str],
) -> tuple[int, int]:
    """Append-only, idempotent merge. Returns (rows_added, total_after)."""
    try:
        existing = pd.read_parquet(archive_path) if archive_path.exists() else pd.DataFrame()
    except Exception:
        existing = pd.DataFrame()

    if new_rows.empty:
        return 0, len(existing)

    combined = new_rows.copy() if existing.empty else pd.concat([existing, new_rows], ignore_index=True)
    if not existing.empty:
        avail_keys = [k for k in dedup_key if k in combined.columns]
        combined = combined.drop_duplicates(subset=avail_keys, keep="first")

    rows_added = max(len(combined) - len(existing), 0)
    combined.to_parquet(archive_path, index=False)
    return rows_added, len(combined)


def snapshot(
    as_of: Optional[str] = None,
    out_dir: Optional[Path] = None,
) -> dict:
    """Run the nightly self-snapshot for one date (defaults to today).

    Returns summary dict: snapshot_date, prop_rows_added, prop_total_rows,
    starter_rows_added, starter_total_rows, prop_date_span, starter_date_span.
    """
    snapshot_date: str = as_of or date.today().isoformat()
    archive_dir: Path = Path(out_dir) if out_dir is not None else _DEFAULT_OUT_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)

    prop_archive = archive_dir / "prop_lines_archive.parquet"
    starter_archive = archive_dir / "starters_archive.parquet"

    new_props = _load_prop_lines(snapshot_date, _LINES_DIR)
    prop_added, prop_total = _append_to_archive(new_props, prop_archive, _PROP_DEDUP_KEY)

    new_starters = _load_starters(snapshot_date, _ROTOWIRE_PATH)
    starter_added, starter_total = _append_to_archive(
        new_starters, starter_archive, _STARTER_DEDUP_KEY
    )

    def _date_span(path: Path) -> str:
        if not path.exists():
            return "none"
        try:
            df = pd.read_parquet(path, columns=["snapshot_date"])
            dates = sorted(df["snapshot_date"].dropna().unique())
            if not dates:
                return "none"
            return f"{dates[0]} to {dates[-1]} ({len(dates)} dates)"
        except Exception:
            return "unknown"

    summary = {
        "snapshot_date": snapshot_date,
        "prop_rows_added": prop_added,
        "prop_total_rows": prop_total,
        "starter_rows_added": starter_added,
        "starter_total_rows": starter_total,
        "prop_date_span": _date_span(prop_archive),
        "starter_date_span": _date_span(starter_archive),
    }
    return summary


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Nightly self-snapshot: persist today's prop lines + starters "
        "to leak-safe dated parquet archives."
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Date to snapshot (default: today).",
    )
    parser.add_argument(
        "--out-dir",
        metavar="DIR",
        default=None,
        help="Override output directory (default: data/cache/lines_archive/).",
    )
    args = parser.parse_args()

    result = snapshot(as_of=args.date, out_dir=args.out_dir)

    print(f"\n=== Snapshot complete for {result['snapshot_date']} ===")
    print(
        f"  Prop lines  : +{result['prop_rows_added']:,} rows added "
        f"| {result['prop_total_rows']:,} total | span: {result['prop_date_span']}"
    )
    print(
        f"  Starters    : +{result['starter_rows_added']:,} rows added "
        f"| {result['starter_total_rows']:,} total | span: {result['starter_date_span']}"
    )
    print(f"  Archive dir : {_DEFAULT_OUT_DIR}\n")


if __name__ == "__main__":
    _cli()
