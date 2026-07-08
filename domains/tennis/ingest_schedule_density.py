"""Schedule-density PREP step (claims-scale lane, rank-9 census family:
tennis_fatigue_schedule_density) -- descriptive port of the same rest-day/
appearance-cadence family shape used elsewhere in this lane
(domains/mlb/ingest_bullpen_relief_chains.py's rest_days/is_b2b/rolling-count
pattern), applied to tennis's per-match corpus.

Derives a claims-grid-ready parquet from matches.parquet (30,616 matches,
wide p1_id/p2_id columns) so the family can ride the existing pure-data GRID
+ claims_factory path once this prep step materializes its derived columns.
Cannot be a bare grid entry over matches.parquet directly (spec sec 1: grid
config is pure data, zero row-level/temporal logic) because:
  1. matches.parquet is WIDE (one row per match, p1_id and p2_id as separate
     columns) -- schedule density needs a player's FULL match history
     regardless of which side of the match they were on, so this module
     MELTS p1/p2 into one long per-player-appearance table first. The
     existing domains/tennis/claims_grid.py's p1/p2-perspective families are
     fine leaving this split (their dims are per-side, order-dependent stats
     like rank_at_match); rest-days-since-last-match is NOT order-dependent,
     so splitting by side there would silently under-count a player's true
     match cadence (missing every match where they were the OTHER column).
  2. Rest-day / density features (days since a player's last match, count of
     matches in the trailing 7/14 days) are temporal diff/rolling
     computations over each player's own sorted history -- safe_formula's
     aggregate grammar (sum/mean/count/count_distinct) has no lag/rolling
     primitive, so these must be precomputed here, once, per row.

Output columns (one row per PLAYER-MATCH appearance, both sides melted):
event_id, player_id, player_name, date, year, surface, rest_days (NaN for a
player's first match in this corpus), matches_last_7d, matches_last_14d
(count of this player's OTHER matches in the trailing 7/14 days, excluding
the current one).

NETWORK: zero. Pure pandas over an already-materialized parquet.
DESCRIPTIVE ONLY -- no forecasting/market claim, no gate, no $ edge.

CLI: python -m domains.tennis.ingest_schedule_density
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa

from scripts.platformkit.intel_validation.basketball_claims_io import atomic_write_parquet

REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet"
_OUT = REPO_ROOT / "data" / "domains" / "tennis" / "schedule_density.parquet"

_KEEP_COLS = [
    "event_id", "player_id", "player_name", "date", "year", "surface",
    "rest_days", "matches_last_7d", "matches_last_14d",
]


def _rolling_prior_count(group: pd.DataFrame, window: str) -> pd.Series:
    """Count of a player's OTHER match rows within the trailing `window`
    (inclusive of the current row via pandas' time-offset rolling, minus 1
    to exclude it)."""
    return group["event_id"].rolling(window).count() - 1.0


def build(src: Path = _SRC, out: Path = _OUT) -> pd.DataFrame:
    df = pd.read_parquet(src)
    df["date"] = pd.to_datetime(df["date"])

    p1 = df[["event_id", "date", "surface", "p1_id", "p1_name"]].rename(
        columns={"p1_id": "player_id", "p1_name": "player_name"}
    )
    p2 = df[["event_id", "date", "surface", "p2_id", "p2_name"]].rename(
        columns={"p2_id": "player_id", "p2_name": "player_name"}
    )
    long_df = pd.concat([p1, p2], ignore_index=True)
    long_df = long_df.dropna(subset=["player_id"]).copy()
    long_df["year"] = long_df["date"].dt.year.astype(int)
    long_df = long_df.sort_values(["player_id", "date"])

    long_df["rest_days"] = long_df.groupby("player_id")["date"].diff().dt.days.astype(float)

    long_df = long_df.set_index("date")
    long_df["matches_last_7d"] = long_df.groupby("player_id", group_keys=False).apply(
        lambda g: _rolling_prior_count(g, "7D"), include_groups=False
    )
    long_df["matches_last_14d"] = long_df.groupby("player_id", group_keys=False).apply(
        lambda g: _rolling_prior_count(g, "14D"), include_groups=False
    )
    long_df = long_df.reset_index()

    out_df = long_df[_KEEP_COLS].reset_index(drop=True)
    atomic_write_parquet(pa.Table.from_pandas(out_df, preserve_index=False), out)
    return out_df


def main() -> int:
    out_df = build()
    print(
        f"schedule_density: {len(out_df)} player-match rows, "
        f"{out_df['player_id'].nunique()} distinct players -> {_OUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
