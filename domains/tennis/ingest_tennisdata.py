"""domains.tennis.ingest_tennisdata — tennis-data.co.uk season files → odds.parquet.

Pulls per-season ATP/WTA workbooks (B365/Pinnacle/Max/Avg decimal odds) and joins
them to the Sackmann matches frame to produce `data/domains/tennis/odds.parquet`
with p1/p2-ORIENTED prices (anti-leak orientation — see §Anti-Leak below).

PRIVATE: outputs are price-bearing or license-restricted; `data/domains/tennis/`
is never tracked. Tennis-data.co.uk prices are price-bearing; gitignored by the
nested `data/domains/tennis/.gitignore`.

§Anti-Leak orientation
----------------------
tennis-data.co.uk ships prices keyed to Winner (W) and Loser (L) — an EX-POST
label that encodes the outcome.  Any downstream consumer that ingests W-prices as
"my model predicts this side" is leaking the outcome through which column it reads.

This module maps prices to `b365_p1 / b365_p2 / ps_p1 / ps_p2` where
  p1 = the player with the lower Sackmann player_id (same orientation as
       matches.parquet `p1_id = min(winner_id, loser_id)`)
The W/L columns are retained as `b365w, b365l, psw, psl` for auditability but
downstream consumers MUST use the p1/p2 columns, NEVER the w/l columns.

Module structure (BUILD-SEPARABLE per §5 network policy)
---------------------------------------------------------
fetch_raw(out_dir, tours, years, force)  — downloads to _raw/tennisdata/; DEFERRED
build_odds(raw, matches_df, out)         — pure transform; called by tests + CLI
join_odds(td_df, matches_df)             — inner join logic; returns JoinResult

CLI: python -m domains.tennis.ingest_tennisdata [--fetch] [--build]
     (no args = build-only; --fetch is a no-op skeleton in this task).
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import pathlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import NamedTuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.tennis.name_aliases import normalize_td, normalize_sackmann, ALIASES


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TENNIS_DIR = _REPO_ROOT / "data" / "domains" / "tennis"
_RAW_DIR = _TENNIS_DIR / "_raw" / "tennisdata"

ODDS_PARQUET = _TENNIS_DIR / "odds.parquet"
BUILD_REPORT = _TENNIS_DIR / "build_report.json"

# ---------------------------------------------------------------------------
# tennis-data.co.uk URL templates (fetch deferred — for reference)
# ---------------------------------------------------------------------------

_TD_ATP_URL = "http://www.tennis-data.co.uk/{year}/{year}.xlsx"
_TD_WTA_URL = "http://www.tennis-data.co.uk/{year}w/{year}.xlsx"

# ---------------------------------------------------------------------------
# Column mapping (varies slightly year-by-year; tolerate missing → NA)
# ---------------------------------------------------------------------------

_REQUIRED_COLS = ["Date", "Winner", "Loser"]
_PRICE_COLS = ["B365W", "B365L", "PSW", "PSL", "MaxW", "MaxL", "AvgW", "AvgL"]
_OPTIONAL_COLS = [
    "Tournament", "Surface", "Round", "Best of", "WRank", "LRank", "Comment",
]

# Round label → Sackmann round code (best-effort; unmapped → None)
_ROUND_MAP: dict[str, str] = {
    "the final": "F",
    "final": "F",
    "semifinals": "SF",
    "semifinal": "SF",
    "quarterfinals": "QF",
    "quarterfinal": "QF",
    "3rd round": "R16",
    "round of 16": "R16",
    "4th round": "R16",
    "3rd round qualifying": "Q3",
    "2nd round qualifying": "Q2",
    "1st round qualifying": "Q1",
    "2nd round": "R32",
    "1st round": "R64",
    "round of 32": "R32",
    "round of 64": "R64",
    "round of 128": "R128",
    "robin round": "RR",
    "round robin": "RR",
}


def _norm_round(r: str | None) -> str | None:
    if not r:
        return None
    return _ROUND_MAP.get(str(r).strip().lower())


# ---------------------------------------------------------------------------
# JoinResult — the output of join_odds()
# ---------------------------------------------------------------------------

class JoinResult(NamedTuple):
    """Bucketed output of the odds-join operation.

    Attributes
    ----------
    joined_df:
        Rows that matched a Sackmann event_id; contains the odds.parquet contract.
    unjoined_df:
        Completed rows that did not find a Sackmann match.
    excluded_df:
        Rows excluded because Comment != "Completed" (retirements, walkovers, etc.).
    join_rate:
        joined / (joined + unjoined) for Completed rows only.
    """
    joined_df: pd.DataFrame
    unjoined_df: pd.DataFrame
    excluded_df: pd.DataFrame
    join_rate: float


# ---------------------------------------------------------------------------
# CSV / XLSX loading
# ---------------------------------------------------------------------------

def _read_season_file(path: pathlib.Path) -> pd.DataFrame:
    """Read a single tennis-data season file (.xlsx or .csv) into a raw DataFrame.

    Missing optional columns are filled with NA.  Raises on missing required cols.
    """
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        raw = pd.read_excel(path, engine="openpyxl")
    elif suffix == ".csv":
        raw = pd.read_csv(path, low_memory=False)
    else:
        raise ValueError(f"Unsupported file type: {path}")

    # Drop completely empty rows (some workbooks have trailing blank rows)
    raw = raw.dropna(how="all").reset_index(drop=True)

    # Ensure optional cols exist (fill NA if absent)
    for col in _OPTIONAL_COLS + _PRICE_COLS:
        if col not in raw.columns:
            raw[col] = pd.NA

    missing_req = [c for c in _REQUIRED_COLS if c not in raw.columns]
    if missing_req:
        raise ValueError(f"Required columns missing in {path.name}: {missing_req}")

    return raw


def load_raw_season_files(
    paths: list[pathlib.Path],
    tour: str,
    year: int,
) -> pd.DataFrame:
    """Load one or more season files and tag with tour/year metadata."""
    frames = [_read_season_file(p) for p in paths]
    df = pd.concat(frames, ignore_index=True)
    df["_tour"] = tour
    df["_year"] = year
    return df


# ---------------------------------------------------------------------------
# Name normalisation key column
# ---------------------------------------------------------------------------

def _add_norm_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Add _norm_winner and _norm_loser columns (alias-resolved canonical keys)."""
    df = df.copy()
    df["_norm_winner"] = df["Winner"].fillna("").apply(
        lambda n: ALIASES.get(normalize_td(n), normalize_td(n))
    )
    df["_norm_loser"] = df["Loser"].fillna("").apply(
        lambda n: ALIASES.get(normalize_td(n), normalize_td(n))
    )
    return df


# ---------------------------------------------------------------------------
# Matches-DataFrame normalisation (needs norm keys for join)
# ---------------------------------------------------------------------------

def _add_match_norm_keys(matches: pd.DataFrame) -> pd.DataFrame:
    """Add _norm_p1 and _norm_p2 (Sackmann canonical keys) to matches frame."""
    matches = matches.copy()
    matches["_norm_p1"] = matches["p1_name"].fillna("").apply(
        lambda n: ALIASES.get(normalize_sackmann(n), normalize_sackmann(n))
    )
    matches["_norm_p2"] = matches["p2_name"].fillna("").apply(
        lambda n: ALIASES.get(normalize_sackmann(n), normalize_sackmann(n))
    )
    return matches


# ---------------------------------------------------------------------------
# Join algorithm (§3.2 spec)
# ---------------------------------------------------------------------------

_DATE_WINDOW_DAYS = 20  # tourney_date ≤ td_date ≤ tourney_date + 20d


def _parse_date(val: object) -> dt.date | None:
    """Coerce a raw date value to a Python date; return None on failure."""
    if pd.isna(val):
        return None
    if isinstance(val, (dt.date, dt.datetime)):
        return val.date() if isinstance(val, dt.datetime) else val
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


def join_odds(
    td_df: pd.DataFrame,
    matches_df: pd.DataFrame,
) -> JoinResult:
    """Join a tennis-data season frame to the Sackmann matches frame.

    Parameters
    ----------
    td_df:
        Raw tennis-data rows (from load_raw_season_files or a test fixture).
        Must have columns: Date, Winner, Loser, _tour, _norm_winner, _norm_loser.
    matches_df:
        Sackmann matches frame (contract per §3.1).
        Must have columns: event_id, date, tour, tourney_id, p1_id, p2_id,
        p1_name, p2_name, p1_rank, p2_rank, winner, _norm_p1, _norm_p2.

    Returns
    -------
    JoinResult
    """
    td_df = _add_norm_keys(td_df)
    matches_df = _add_match_norm_keys(matches_df)

    # Parse td dates
    td_df = td_df.copy()
    td_df["_date"] = td_df["Date"].apply(_parse_date)

    # Split td into completed vs excluded
    is_completed = td_df["Comment"].fillna("Completed").str.strip().str.lower() == "completed"
    excluded_df = td_df[~is_completed].copy()
    completed_df = td_df[is_completed].copy()

    joined_rows: list[dict] = []
    unjoined_rows: list[pd.Series] = []

    # Convert matches to a structure we can search quickly
    # Index on (tour, norm_pair_frozenset) for fast candidate lookup
    # norm_pair = frozenset of (_norm_p1, _norm_p2)
    from collections import defaultdict
    match_index: dict[tuple[str, frozenset], list[pd.Series]] = defaultdict(list)
    for _, m in matches_df.iterrows():
        key = (str(m.get("tour", "")), frozenset([m["_norm_p1"], m["_norm_p2"]]))
        match_index[key].append(m)

    for _, td_row in completed_df.iterrows():
        td_date = td_row.get("_date")
        tour = str(td_row.get("_tour", ""))
        nw = td_row["_norm_winner"]
        nl = td_row["_norm_loser"]
        pair_key = frozenset([nw, nl])

        candidates = match_index.get((tour, pair_key), [])

        # Filter by date window
        if td_date is not None:
            windowed = [
                m for m in candidates
                if _in_date_window(m.get("date"), td_date)
            ]
        else:
            windowed = candidates

        if not windowed:
            unjoined_rows.append(td_row)
            continue

        # Tiebreak: round match → nearest date → rank proximity → lexical event_id
        best = _tiebreak(windowed, td_row)

        joined_rows.append(_build_joined_row(td_row, best))

    # Build DataFrames
    joined_df = pd.DataFrame(joined_rows) if joined_rows else _empty_joined_df()
    unjoined_df = pd.DataFrame(unjoined_rows) if unjoined_rows else pd.DataFrame()

    total = len(joined_rows) + len(unjoined_rows)
    join_rate = len(joined_rows) / total if total > 0 else 0.0

    return JoinResult(
        joined_df=joined_df,
        unjoined_df=unjoined_df,
        excluded_df=excluded_df,
        join_rate=join_rate,
    )


def _in_date_window(match_date: object, td_date: dt.date) -> bool:
    md = _parse_date(match_date)
    if md is None:
        return False
    delta = (td_date - md).days
    return 0 <= delta <= _DATE_WINDOW_DAYS


def _norm_round_td(r: object) -> str | None:
    return _norm_round(str(r) if r and not (isinstance(r, float)) else None)


def _tiebreak(candidates: list[pd.Series], td_row: pd.Series) -> pd.Series:
    """Pick best candidate from windowed matches."""
    td_round = _norm_round_td(td_row.get("Round"))
    td_date = td_row.get("_date")

    def score(m: pd.Series) -> tuple:
        # 1. Round match (0 = match, 1 = no match)
        round_ok = 0 if (td_round and m.get("round") == td_round) else 1
        # 2. Date proximity
        md = _parse_date(m.get("date"))
        date_dist = abs((td_date - md).days) if (td_date and md) else 999
        # 3. Rank proximity (WRank vs p_rank)
        wrank = td_row.get("WRank")
        p1_rank = m.get("p1_rank")
        rank_dist = abs(float(wrank) - float(p1_rank)) if (
            wrank and p1_rank and not pd.isna(wrank) and not pd.isna(p1_rank)
        ) else 999
        # 4. Lexical event_id
        eid = str(m.get("event_id", ""))
        return (round_ok, date_dist, rank_dist, eid)

    return min(candidates, key=score)


# ---------------------------------------------------------------------------
# §Anti-Leak: orient prices to p1/p2 (outcome-blind)
# ---------------------------------------------------------------------------

def _orient_prices(row: pd.Series, match: pd.Series) -> dict:
    """Map winner/loser prices → p1/p2-oriented prices.

    winner column in matches is int8 (1 = p1 won, 2 = p2 won).
    If winner == 1: W-prices belong to p1, L-prices to p2.
    If winner == 2: W-prices belong to p2, L-prices to p1.
    """
    w = int(match.get("winner", 1))

    def _f32(v: object) -> float | None:
        try:
            f = float(v)
            return f if pd.notna(f) else None
        except (TypeError, ValueError):
            return None

    b365w = _f32(row.get("B365W"))
    b365l = _f32(row.get("B365L"))
    psw = _f32(row.get("PSW"))
    psl = _f32(row.get("PSL"))

    if w == 1:
        b365_p1, b365_p2 = b365w, b365l
        ps_p1, ps_p2 = psw, psl
    else:
        b365_p1, b365_p2 = b365l, b365w
        ps_p1, ps_p2 = psl, psw

    return {
        "b365_p1": b365_p1, "b365_p2": b365_p2,
        "ps_p1": ps_p1, "ps_p2": ps_p2,
    }


def _build_joined_row(td_row: pd.Series, match: pd.Series) -> dict:
    """Assemble one output row for odds.parquet."""
    def _s(v: object) -> str | None:
        return None if pd.isna(v) else str(v)

    def _f32(v: object) -> float | None:
        try:
            f = float(v)
            return f if pd.notna(f) else None
        except (TypeError, ValueError):
            return None

    oriented = _orient_prices(td_row, match)

    return {
        "event_id": _s(match.get("event_id")),
        "date_td": td_row.get("_date"),
        "tour": _s(match.get("tour")),
        "tournament_td": _s(td_row.get("Tournament")),
        "round_td": _s(td_row.get("Round")),
        "comment": _s(td_row.get("Comment")),
        # Raw W/L prices (retained for audit; do NOT use for modelling — leak risk)
        "b365w": _f32(td_row.get("B365W")),
        "b365l": _f32(td_row.get("B365L")),
        "psw": _f32(td_row.get("PSW")),
        "psl": _f32(td_row.get("PSL")),
        "maxw": _f32(td_row.get("MaxW")),
        "maxl": _f32(td_row.get("MaxL")),
        "avgw": _f32(td_row.get("AvgW")),
        "avgl": _f32(td_row.get("AvgL")),
        # P1/P2-oriented prices (use these downstream)
        **oriented,
    }


def _empty_joined_df() -> pd.DataFrame:
    cols = [
        "event_id", "date_td", "tour", "tournament_td", "round_td", "comment",
        "b365w", "b365l", "psw", "psl", "maxw", "maxl", "avgw", "avgl",
        "b365_p1", "b365_p2", "ps_p1", "ps_p2",
    ]
    return pd.DataFrame(columns=cols)


# ---------------------------------------------------------------------------
# build_odds — full transform pipeline
# ---------------------------------------------------------------------------

def build_odds(
    raw_season_frames: list[tuple[str, int, pd.DataFrame]],
    matches_df: pd.DataFrame,
    out: pathlib.Path = ODDS_PARQUET,
) -> JoinResult:
    """Transform raw tennis-data frames + Sackmann matches → odds.parquet.

    Parameters
    ----------
    raw_season_frames:
        List of (tour, year, raw_df) tuples from load_raw_season_files.
    matches_df:
        Sackmann matches DataFrame with the §3.1 contract columns.
    out:
        Destination parquet path (parent created if absent).

    Returns
    -------
    JoinResult
        Combined join result (all seasons, both tours).
    """
    all_td: list[pd.DataFrame] = []
    for tour, year, df in raw_season_frames:
        df = df.copy()
        df["_tour"] = tour
        df["_year"] = year
        all_td.append(df)

    if not all_td:
        result = JoinResult(
            joined_df=_empty_joined_df(),
            unjoined_df=pd.DataFrame(),
            excluded_df=pd.DataFrame(),
            join_rate=0.0,
        )
    else:
        combined_td = pd.concat(all_td, ignore_index=True)
        result = join_odds(combined_td, matches_df)

    joined = result.joined_df

    if not joined.empty:
        # Cast price columns to float32
        float_cols = [
            "b365w", "b365l", "psw", "psl", "maxw", "maxl", "avgw", "avgl",
            "b365_p1", "b365_p2", "ps_p1", "ps_p2",
        ]
        for col in float_cols:
            if col in joined.columns:
                joined[col] = pd.to_numeric(joined[col], errors="coerce").astype("float32")

        # Stable sort
        joined = joined.sort_values(
            ["tour", "date_td", "event_id"],
            kind="mergesort",
            na_position="last",
        ).reset_index(drop=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(joined, preserve_index=False)
    pq.write_table(table, out, compression="snappy")

    return result


# ---------------------------------------------------------------------------
# fetch_raw — DEFERRED (not called by tests; CLI stub only)
# ---------------------------------------------------------------------------

def fetch_raw(
    out_dir: pathlib.Path = _RAW_DIR,
    tours: tuple[str, ...] = ("atp", "wta"),
    years: tuple[int, ...] | None = None,
    force: bool = False,
) -> None:
    """Download tennis-data.co.uk season files to *out_dir*.

    DEFERRED: not called in T-B-002 tests.  Network execution happens only at
    wave T3 via the CLI (``--fetch``).  Raises NotImplementedError as a guard.
    """
    raise NotImplementedError(
        "fetch_raw is deferred to wave T3.  Run with --fetch from the CLI "
        "only after the wave-T1 .gitignore + manifest freeze are complete."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="tennis-data.co.uk ingest → odds.parquet"
    )
    parser.add_argument(
        "--fetch", action="store_true",
        help="Download raw season files (deferred — requires network)",
    )
    parser.add_argument(
        "--build", action="store_true",
        help="Build odds.parquet from cached _raw/ files",
    )
    parser.add_argument(
        "--tours", default="atp,wta",
        help="Comma-separated tours (default: atp,wta)",
    )
    parser.add_argument(
        "--start-year", type=int, default=2015,
    )
    parser.add_argument(
        "--end-year", type=int, default=2026,
    )
    parser.add_argument(
        "--matches-parquet", type=pathlib.Path,
        default=_TENNIS_DIR / "matches.parquet",
        help="Path to Sackmann matches.parquet",
    )
    parser.add_argument("--out", type=pathlib.Path, default=ODDS_PARQUET)
    args = parser.parse_args()

    if args.fetch:
        fetch_raw(force=True)

    if args.build or not args.fetch:
        if not args.matches_parquet.exists():
            raise FileNotFoundError(
                f"matches.parquet not found at {args.matches_parquet}. "
                "Run ingest_sackmann --build first."
            )
        matches_df = pd.read_parquet(args.matches_parquet)
        tours = [t.strip() for t in args.tours.split(",")]
        years = list(range(args.start_year, args.end_year + 1))

        frames: list[tuple[str, int, pd.DataFrame]] = []
        for tour in tours:
            for year in years:
                fname = f"{tour}_{year}.xlsx"
                fpath = _RAW_DIR / fname
                if fpath.exists():
                    df = load_raw_season_files([fpath], tour, year)
                    frames.append((tour, year, df))
                else:
                    print(f"[skip] {fpath.name} not found in _raw/")

        result = build_odds(frames, matches_df, args.out)
        print(
            f"odds.parquet written → {args.out}\n"
            f"  joined={len(result.joined_df)}  unjoined={len(result.unjoined_df)}"
            f"  excluded={len(result.excluded_df)}  join_rate={result.join_rate:.3f}"
        )

        report: dict = {
            "joined": len(result.joined_df),
            "unjoined": len(result.unjoined_df),
            "excluded": len(result.excluded_df),
            "join_rate": result.join_rate,
        }
        BUILD_REPORT.parent.mkdir(parents=True, exist_ok=True)
        BUILD_REPORT.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    _cli()
