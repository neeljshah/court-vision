"""domains.soccer.ingest_footballdata_matchstats — deep match-stats sidecar.

The main ingest (``ingest_footballdata.py``) keeps only ~11 columns and DISCARDS
the rich per-match descriptive stats that football-data.co.uk already ships in the
ALREADY-CACHED CSVs: half-time scores, shots, shots-on-target (a free xG proxy),
corners, fouls, and cards.  This module re-reads those SAME cached CSVs and emits
ONE sidecar row per match, keyed by the IDENTICAL ``event_id`` used by
``build_matches`` so it joins 1:1 onto ``matches.parquet``.

PURE TRANSFORM of cached CSVs — ZERO network.  This module only CAPTURES the raw
per-match facts.

LEAK-NOTE: every column here is a DESCRIPTIVE fact about a SETTLED match (shots
taken, cards shown, half-time score).  They are post-match observations and MUST
NOT be fed as same-match features.  Downstream feature builders may consume them
ONLY as PRIOR-match rolling aggregates (a team's trailing shots/SoT/corners rate
before kickoff).  This module performs no such aggregation — it deepens the data
substrate; no edge is claimed.

PRIVATE: lives under data/domains/soccer/ which is never tracked.
football-data.co.uk data is free for personal/research use only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.soccer.config import (
    DATA_DIR_REL, LEAGUES, RAW_DIR_REL, season_code,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Output schema (column order is the parquet contract).
MATCH_STATS_COLS: Tuple[str, ...] = (
    "event_id", "div", "date", "home_team", "away_team",
    "hthg", "htag", "htr",
    "home_shots", "away_shots",
    "home_sot", "away_sot",
    "home_corners", "away_corners",
    "home_fouls", "away_fouls",
    "home_yellow", "away_yellow",
    "home_red", "away_red",
    "referee",
    # derived safe ratios / totals
    "home_sot_ratio", "away_sot_ratio", "total_shots", "total_sot",
)

# raw football-data.co.uk column -> sidecar column.
_NUMERIC_MAP: Tuple[Tuple[str, str], ...] = (
    ("HTHG", "hthg"), ("HTAG", "htag"),
    ("HS", "home_shots"), ("AS", "away_shots"),
    ("HST", "home_sot"), ("AST", "away_sot"),
    ("HC", "home_corners"), ("AC", "away_corners"),
    ("HF", "home_fouls"), ("AF", "away_fouls"),
    ("HY", "home_yellow"), ("AY", "away_yellow"),
    ("HR", "home_red"), ("AR", "away_red"),
)

FrameTuple = Tuple[str, int, pd.DataFrame]  # (div, season_start_year, raw_df)


def _slug(name: str) -> str:
    """Lowercase *name*, replace every non-alphanumeric character with ``_``.

    IDENTICAL to ingest_footballdata._slug (replicated for a 1:1 event_id join).
    """
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def _make_event_id(date: "dt.date | pd.Timestamp", div: str, home: str, away: str) -> str:
    """Deterministic pre-match event identifier.

    IDENTICAL to ingest_footballdata._make_event_id so this sidecar joins 1:1
    onto matches.parquet.
    """
    if isinstance(date, pd.Timestamp):
        date = date.date()
    return f"{date:%Y%m%d}-{div}-{_slug(home)}-{_slug(away)}"


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    """Numeric-coerce *col* to float (NaN-safe). Missing column -> all-NaN."""
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").astype("float64")
    return pd.Series(np.nan, index=df.index, dtype="float64")


def _safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """Elementwise num/den; NaN where den is 0 or either operand is NaN."""
    den_ok = den.where(den != 0.0, other=np.nan)
    return num / den_ok


def build_match_stats_frame(frames: Iterable[FrameTuple]) -> pd.DataFrame:
    """(div, season_start_year, raw_df) iterable -> match_stats contract DataFrame.

    Pure transform (no I/O) — the fixture-tested core.  One row per match keyed by
    the SAME event_id as build_matches.  Numeric stat columns are float (NaN-safe);
    missing source columns become all-NaN (never a crash).  Rows with an
    unparseable Date are dropped (no valid key).
    """
    parts: List[pd.DataFrame] = []
    for div, _season_yr, raw in frames:
        df = raw.copy()
        df["_div"] = str(div)
        df["date"] = pd.to_datetime(df.get("Date"), dayfirst=True, errors="coerce")
        # P4: make silent date-parse loss visible. df.get("Date") returns all-None
        # when the Date column is absent, so the whole frame's rows would vanish at
        # the dropna below WITHOUT any signal (build_matches KeyErrors loudly in the
        # same situation). Warn per-frame when an input contributes 0 valid-date
        # rows, or loses a large fraction of its rows to date-parse failures.
        n_in = len(df)
        n_valid = int(df["date"].notna().sum())
        if n_in > 0 and n_valid == 0:
            print(f"[warn] {div} ({_season_yr}): 0 of {n_in} rows have a parseable "
                  f"Date (column missing or unparseable) -- frame contributes "
                  f"NOTHING; this would silently desync from matches.parquet")
        elif n_valid < n_in:
            print(f"[warn] {div} ({_season_yr}): dropped {n_in - n_valid} of {n_in} "
                  f"rows with an unparseable Date")
        parts.append(df)
    if not parts:
        return pd.DataFrame(columns=list(MATCH_STATS_COLS))

    combined = pd.concat(parts, ignore_index=True)
    combined = combined.dropna(subset=["date"]).copy()
    if combined.empty:
        return pd.DataFrame(columns=list(MATCH_STATS_COLS))

    out = pd.DataFrame(index=combined.index)
    out["div"] = combined["_div"].astype(str)
    out["date"] = combined["date"]
    out["home_team"] = combined.get(
        "HomeTeam", pd.Series("", index=combined.index)).astype(str)
    out["away_team"] = combined.get(
        "AwayTeam", pd.Series("", index=combined.index)).astype(str)
    out["event_id"] = [
        _make_event_id(d, dv, h, a)
        for d, dv, h, a in zip(out["date"], out["div"], out["home_team"], out["away_team"])
    ]

    # half-time result (categorical: H/D/A) — string, "" when absent.
    out["htr"] = combined.get(
        "HTR", pd.Series("", index=combined.index)).fillna("").astype(str)
    out["referee"] = combined.get(
        "Referee", pd.Series("", index=combined.index)).fillna("").astype(str)

    for raw_col, out_col in _NUMERIC_MAP:
        out[out_col] = _num(combined, raw_col)

    # derived safe ratios / totals (NaN-safe; NaN when denom 0 or operand NaN).
    out["home_sot_ratio"] = _safe_ratio(out["home_sot"], out["home_shots"])
    out["away_sot_ratio"] = _safe_ratio(out["away_sot"], out["away_shots"])
    out["total_shots"] = out["home_shots"] + out["away_shots"]
    out["total_sot"] = out["home_sot"] + out["away_sot"]

    # P5: a fixture cached under two overlapping season codes (e.g. it appears in
    # both the 2425 and 2526 files near a season boundary) emits the SAME event_id
    # twice. Duplicate keys would fan out the 1:1 as-of join onto matches.parquet.
    # Dedupe on event_id (keep last) before the final ordering so the key is unique.
    return (out[list(MATCH_STATS_COLS)]
            .drop_duplicates(subset=["event_id"], keep="last")
            .sort_values(["date", "div", "home_team", "away_team"], kind="mergesort")
            .reset_index(drop=True))


def _load_frames(raw_root: Path) -> List[FrameTuple]:
    """Read every cached ``{season_code}_{div}.csv`` under *raw_root*.

    Iterates all 6 leagues across a generous season span; silently skips files
    that are absent.  ZERO network.
    """
    frames: List[FrameTuple] = []
    current_yr = dt.date.today().year
    for yr in range(2000, current_yr + 1):
        sc = season_code(yr)
        for div in LEAGUES.keys():
            fpath = raw_root / f"{sc}_{div}.csv"
            if not fpath.exists() or fpath.stat().st_size == 0:
                continue
            try:
                frames.append((div, yr, pd.read_csv(fpath, low_memory=False)))
            except Exception as exc:  # corrupt CSV — skip, never crash the build
                print(f"[warn] {fpath.name}: {exc}")
    return frames


def build_match_stats(
    raw_dir: Optional[str] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Re-read cached CSVs and write the match_stats sidecar parquet.

    raw_dir  : cache dir (default data/domains/soccer/_raw/footballdata).
    out_path : output parquet (default data/domains/soccer/match_stats.parquet).
    Returns the written Path.  ZERO network.  Delegates the row transform to
    build_match_stats_frame so tests can exercise the contract from fixtures.
    """
    raw_root = Path(raw_dir) if raw_dir else (_REPO_ROOT / RAW_DIR_REL)
    out_file = (Path(out_path) if out_path
                else (_REPO_ROOT / DATA_DIR_REL / "match_stats.parquet"))
    out_file.parent.mkdir(parents=True, exist_ok=True)
    df = build_match_stats_frame(iter(_load_frames(raw_root)))
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out_file)
    return out_file


def main() -> None:
    """CLI: build the sidecar, print rows written + a 3-row sample."""
    parser = argparse.ArgumentParser(
        description="football-data.co.uk deep match-stats sidecar (cached CSVs only)")
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--out-path", default=None)
    args = parser.parse_args()
    out_file = build_match_stats(raw_dir=args.raw_dir, out_path=args.out_path)
    df = pq.read_table(out_file).to_pandas()
    print(f"match_stats: wrote {len(df)} rows -> {out_file}")
    sample_cols = ["event_id", "home_shots", "away_shots",
                   "home_sot", "away_sot", "home_sot_ratio"]
    print(df[sample_cols].head(3).to_string(index=False))


if __name__ == "__main__":
    main()
