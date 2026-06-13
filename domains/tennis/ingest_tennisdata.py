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
import json
import pathlib

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Sub-module imports — re-exported to keep all existing import paths working
# ---------------------------------------------------------------------------

from domains.tennis.ingest_tennisdata_load import (  # noqa: F401
    _TD_ATP_URL,
    _TD_WTA_URL,
    _REQUIRED_COLS,
    _PRICE_COLS,
    _OPTIONAL_COLS,
    _ROUND_MAP,
    _norm_round,
    _read_season_file,
    load_raw_season_files,
    _add_norm_keys,
    _add_match_norm_keys,
)
from domains.tennis.ingest_tennisdata_join import (  # noqa: F401
    JoinResult,
    _DATE_WINDOW_DAYS,
    _parse_date,
    _in_date_window,
    _norm_round_td,
    _tiebreak,
    _orient_prices,
    _build_joined_row,
    _empty_joined_df,
    join_odds,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TENNIS_DIR = _REPO_ROOT / "data" / "domains" / "tennis"
_RAW_DIR = _TENNIS_DIR / "_raw" / "tennisdata"

ODDS_PARQUET = _TENNIS_DIR / "odds.parquet"
BUILD_REPORT = _TENNIS_DIR / "build_report.json"


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
