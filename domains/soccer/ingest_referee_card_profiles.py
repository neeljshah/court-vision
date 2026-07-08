"""Referee card/foul profile PREP step (claims-scale lane, rank-6 census family).

Derives a claims-grid-ready parquet from the raw club-domain match_stats.parquet
(25,834 rows, one row per match, home/away-wide fouls/cards + a `referee` column)
so the family can ride the existing pure-data GRID + claims_factory path
(domains/soccer/claims_grid.py) unmodified, instead of a hand-written producer.

TWO reasons this cannot be a bare grid entry over the raw parquet directly
(spec sec 1: grid config is pure data, zero logic):
  1. `referee` has a BLANK-STRING placeholder for uncovered matches (15,583 of
     25,834 rows, verified this session) -- not NaN, so `isna()` misses it and
     an unfiltered groupby would rank a fake "" referee with a huge match count
     ahead of every real official. The factory's window filter is EXACT-EQUALITY
     only (claims_factory.py `_slice_rows`), so "not blank" is not expressible
     as a grid filter; it must be cleaned before the grid ever sees the rows.
  2. match_stats.parquet carries only `date` (no `season`/`year` column), so a
     per-year window (mirroring NBA's season_2024_25 pattern) needs a real,
     derived `year` column to filter on.

home/away totals are summed into single per-match columns (referee/cards are
match-level facts, not home/away-specific) so the grid's aggregate grammar
(sum(total_fouls)/count(event_id) etc.) can run unmodified over this output.

NETWORK: zero. Pure pandas over an already-materialized parquet.
DESCRIPTIVE ONLY -- no forecasting/market claim, no gate, no $ edge.

CLI: python -m domains.soccer.ingest_referee_card_profiles
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa

from scripts.platformkit.intel_validation.basketball_claims_io import atomic_write_parquet

REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = REPO_ROOT / "data" / "domains" / "soccer" / "match_stats.parquet"
_OUT = REPO_ROOT / "data" / "domains" / "soccer" / "referee_card_foul_profiles.parquet"

_KEEP_COLS = [
    "event_id", "referee", "div", "year",
    "total_fouls", "total_yellow", "total_red", "total_cards",
]


def build(src: Path = _SRC, out: Path = _OUT) -> pd.DataFrame:
    """Read match_stats.parquet, drop blank-referee rows, sum home+away
    fouls/cards into per-match totals, derive `year` from `date`. Writes the
    result atomically to `out` and returns it."""
    df = pd.read_parquet(src)
    df = df[df["referee"].astype(str).str.strip() != ""].copy()

    df["total_fouls"] = df["home_fouls"] + df["away_fouls"]
    df["total_yellow"] = df["home_yellow"] + df["away_yellow"]
    df["total_red"] = df["home_red"] + df["away_red"]
    df["total_cards"] = df["total_yellow"] + df["total_red"]
    df["year"] = pd.to_datetime(df["date"]).dt.year.astype(int)

    out_df = df[_KEEP_COLS].reset_index(drop=True)
    atomic_write_parquet(pa.Table.from_pandas(out_df, preserve_index=False), out)
    return out_df


def main() -> int:
    out_df = build()
    print(
        f"referee_card_foul_profiles: {len(out_df)} rows, "
        f"{out_df['referee'].nunique()} referees, "
        f"years {out_df['year'].min()}-{out_df['year'].max()} -> {_OUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
