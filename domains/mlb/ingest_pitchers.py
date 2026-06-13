"""domains.mlb.ingest_pitchers — capture starting pitchers + line scores → pitchers.parquet.

PURE TRANSFORM of the ALREADY-CACHED SBR CSVs (zero network). The single biggest
MLB predictor — the STARTING PITCHER — is present in the raw SBR ``Pitcher`` column
(~100% coverage 2010-2021) plus inning-by-inning line scores (``1st``..``9th``), but
``ingest_sbro.build_games`` drops both. This sidecar captures them, keyed 1:1 to the
SAME ``event_id`` as ``games.parquet`` so it joins directly onto the existing corpus.

It REUSES ``ingest_sbro._iter_pairs`` / ``_parse_date`` / ``_eid`` and replicates the
``build_games`` per-(date,home,away) ``game_seq`` doubleheader counter EXACTLY (seq is
incremented only on valid, date-parseable, finals-parseable, NON-tied pairs) — so every
emitted ``event_id`` matches a games.parquet row and vice versa.

LEAK NOTE: the starting-pitcher *identity* is published pre-game (announced rotations),
so capturing the NAME is leak-free by nature. The line-score innings ARE outcome data
(post-game) and are stored only as descriptive context — NEVER feed innings into a
pre-game feature. Any pitcher RATING/FORM signal must be built by a DOWNSTREAM
walk-forward feature builder (NOT here) using only the pitcher's PRIOR starts. This
module only CAPTURES identity (+ optional descriptive line scores); it derives nothing.

PRIVATE: sits beside price-bearing artifacts; never tracked on the public repo.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.mlb.config import RAW_DIR_REL, YEARS, resolve_league  # noqa: F401 (resolve via games join)
from domains.mlb.ingest_sbro import _eid, _iter_pairs, _parse_date

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INNING_COLS: Tuple[str, ...] = ("1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th")
# Tokens that mean "no real starter listed".
_BLANK_TOKENS = frozenset({"", "-", "--", "NAN", "NA", "NONE", "NULL", "UNDECIDED", "TBD", "TBA"})

PITCHERS_COLS: Tuple[str, ...] = (
    "event_id", "date", "season", "home_team", "away_team",
    "home_sp_name", "away_sp_name",
    "home_sp_present", "away_sp_present",
    "home_innings", "away_innings",
)
FrameTuple = Tuple[int, pd.DataFrame]


def _norm_pitcher(val) -> Tuple[Optional[str], bool]:
    """Normalize a raw Pitcher cell → (name_or_None, present).

    Strip whitespace; map blanks / 'Undecided' / '-' / 'TBD' (case-insensitive)
    → (None, False). Otherwise → (stripped_name, True).
    """
    if val is None:
        return None, False
    s = str(val).strip()
    if s.upper() in _BLANK_TOKENS:
        return None, False
    return s, True


def _innings_str(row: pd.Series) -> Optional[str]:
    """Comma-joined ``1st``..``9th`` line score for one team (descriptive only).

    Empty / all-missing cells → None. Preserves source tokens (incl. ``x`` for an
    un-batted bottom-9th) verbatim; this is post-game context, not a feature.
    """
    vals: List[str] = []
    any_real = False
    for c in _INNING_COLS:
        cell = row.get(c)
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            vals.append("")
            continue
        s = str(cell).strip()
        vals.append(s)
        if s != "":
            any_real = True
    if not any_real:
        return None
    return ",".join(vals)


def build_pitchers(frames: Iterable[FrameTuple]) -> pd.DataFrame:
    """Pure: (season, raw_df) frames → pitchers.parquet contract.

    One row per game, keyed by the SAME ``event_id`` as ``ingest_sbro.build_games``.
    ``game_seq`` doubleheader counter is replicated EXACTLY: incremented only on a
    valid V/H pair whose date and both finals parse and whose finals are NOT tied —
    matching build_games row-for-row, so the join is 1:1.
    """
    parts: List[pd.DataFrame] = []
    for season, raw in frames:
        seq: Dict[Tuple, int] = {}
        rows: List[dict] = []
        for vr, hr, ok in _iter_pairs(raw):
            if not ok:
                continue
            try:
                gd = _parse_date(int(vr["Date"]), season)
            except (ValueError, TypeError):
                continue
            home, away = str(hr["Team"]).strip().upper(), str(vr["Team"]).strip().upper()
            try:
                hr_runs, ar_runs = int(hr["Final"]), int(vr["Final"])
            except (ValueError, TypeError):
                continue
            if hr_runs == ar_runs:  # tied finals dropped (NO seq increment) — match build_games
                continue
            seq[(gd, home, away)] = seq.get((gd, home, away), 0) + 1
            s = seq[(gd, home, away)]
            h_name, h_present = _norm_pitcher(hr.get("Pitcher"))
            a_name, a_present = _norm_pitcher(vr.get("Pitcher"))
            rows.append({
                "event_id": _eid(gd, home, away, s), "date": pd.Timestamp(gd),
                "season": season, "home_team": home, "away_team": away,
                "home_sp_name": h_name, "away_sp_name": a_name,
                "home_sp_present": h_present, "away_sp_present": a_present,
                "home_innings": _innings_str(hr), "away_innings": _innings_str(vr),
            })
        if rows:
            parts.append(pd.DataFrame(rows))
    if not parts:
        return pd.DataFrame(columns=list(PITCHERS_COLS))
    out = pd.concat(parts, ignore_index=True)
    out["home_sp_present"] = out["home_sp_present"].astype(bool)
    out["away_sp_present"] = out["away_sp_present"].astype(bool)
    return (out[list(PITCHERS_COLS)]
            .sort_values(["date", "home_team", "away_team", "event_id"], kind="mergesort")
            .reset_index(drop=True))


def _load_frames(raw_root: Path, years: Iterable[int]) -> List[FrameTuple]:
    """Read cached ``mlb-odds-{y}.csv`` files into (season, df) frames (no network)."""
    frames: List[FrameTuple] = []
    for y in years:
        fp = raw_root / f"mlb-odds-{y}.csv"
        if fp.exists():
            try:
                frames.append((y, pd.read_csv(str(fp), low_memory=False)))
            except Exception as exc:  # malformed file: skip loudly, don't crash
                print(f"[warn] {fp.name}: {exc}")
    return frames


def build_pitchers_parquet(raw_dir: Optional[str] = None,
                           out_path: Optional[str] = None,
                           years: Optional[List[int]] = None) -> Path:
    """Re-read cached SBR CSVs → write ``data/domains/mlb/pitchers.parquet``; return its Path.

    ``raw_dir`` points the loader at a fixture dir (tests pass tmp_path) so it never
    touches the real corpus. Network: NONE.
    """
    raw_root = Path(raw_dir) if raw_dir else (_REPO_ROOT / RAW_DIR_REL)
    out = Path(out_path) if out_path else (_REPO_ROOT / "data/domains/mlb/pitchers.parquet")
    yrs = list(years) if years else list(YEARS)
    frames = _load_frames(raw_root, yrs)
    df = build_pitchers(iter(frames))
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(out))
    return out


def _report(df: pd.DataFrame) -> str:
    """Coverage summary string for the CLI."""
    n = len(df)
    if n == 0:
        return "0 rows written"
    pres = ((df["home_sp_present"] & df["away_sp_present"]).sum() / n) * 100.0
    names = pd.unique(pd.concat([
        df.loc[df["home_sp_present"], "home_sp_name"],
        df.loc[df["away_sp_present"], "away_sp_name"],
    ], ignore_index=True))
    return (f"{n} rows | both-SP-present {pres:.1f}% | "
            f"unique pitchers {len(names)}")


def main() -> None:
    """Entry: ``python -m domains.mlb.ingest_pitchers [--raw-dir D] [--out PATH] [--years Y,Y]``."""
    ap = argparse.ArgumentParser(description="Capture MLB starting pitchers + line scores → parquet")
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--years", default=None)
    args = ap.parse_args()
    yrs = [int(y.strip()) for y in args.years.split(",")] if args.years else None
    raw_root = Path(args.raw_dir) if args.raw_dir else (_REPO_ROOT / RAW_DIR_REL)
    frames = _load_frames(raw_root, yrs or list(YEARS))
    if not frames:
        print("No raw CSVs found; run domains.mlb.ingest_sbro --fetch first.")
        return
    df = build_pitchers(iter(frames))
    out = build_pitchers_parquet(raw_dir=args.raw_dir, out_path=args.out, years=yrs)
    print(f"wrote {out}")
    print(_report(df))
    if len(df):
        cols = ["event_id", "home_sp_name", "away_sp_name", "home_sp_present", "away_sp_present"]
        print(df[cols].head(3).to_string(index=False))


if __name__ == "__main__":
    main()
