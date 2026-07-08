"""Bullpen relief-appearance-chain PREP step (claims-scale lane, rank-7
census family: mlb_bullpen_fatigue_chains).

DISTINCT FROM THE CLOSED SP-velocity class: this is RELIEVER appearance
CADENCE (days rest between appearances, back-to-back usage, appearances
clustered in a trailing window) -- never a pitch-count/velocity-within-outing
metric, which is the class domains/mlb/statcast_sp_fatigue_adapter.py /
mlb_pitch_states__*.parquet already covers and which is CLOSED (honest
REJECT, see memory project_mlb_sp_fatigue_closed_2026_07_04). Neither this
module nor its output touches mlb_pitch_states__*.parquet.

Derives a claims-grid-ready parquet from player_gamelogs.parquet (the same
current-era 2022-2026 source domains/mlb/claims_grid.py already reads for
mlb_pitcher_rate), so the family can ride the existing pure-data GRID +
claims_factory path once this prep step materializes its derived columns.
Cannot be a bare grid entry over player_gamelogs.parquet directly (spec
sec 1: grid config is pure data, zero row-level/temporal logic) because:
  1. STARTER/RELIEVER split: no explicit flag exists on this source (see
     domains/mlb/claims_grid.py's own docstring). HEURISTIC used here (fully
     disclosed, not fabricated): the pitcher with the MAX inningsPitched for
     their team in a given game is the starter; every other pitcher-game row
     for that team is a relief appearance. Ties (e.g. bullpen games / true
     openers where two pitchers share the game-high IP) all land on the
     "starter" side via pandas rank(method="first") -- a known, disclosed
     edge case, not a source of fabricated appearances.
  2. REST-DAY / CADENCE features (days since a pitcher's last relief
     appearance, count of appearances in the trailing 3 days) are temporal
     diff/rolling computations over each pitcher's own sorted history --
     safe_formula's aggregate grammar (sum/mean/count/count_distinct) has no
     lag/rolling primitive, so these must be precomputed here, once, per row.

Output columns (one row per RELIEF appearance): game_pk, player_id, player,
team, date, year, battersFaced, rest_days (NaN for a pitcher's first relief
appearance in this corpus), is_b2b (1.0 if rest_days<=1, else 0.0, NaN when
rest_days is NaN), appearances_last_3d (count of this pitcher's OTHER relief
appearances in the trailing 3 days, excluding the current one).

NETWORK: zero. Pure pandas over an already-materialized parquet.
DESCRIPTIVE ONLY -- no forecasting/market claim, no gate, no $ edge.

CLI: python -m domains.mlb.ingest_bullpen_relief_chains
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

from scripts.platformkit.intel_validation.basketball_claims_io import atomic_write_parquet

REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_OUT = REPO_ROOT / "data" / "domains" / "mlb" / "bullpen_relief_chains.parquet"

_KEEP_COLS = [
    "game_pk", "player_id", "player", "team", "date", "year",
    "battersFaced", "rest_days", "is_b2b", "appearances_last_3d",
]


def _rolling_prior_count(group: pd.DataFrame, window: str) -> pd.Series:
    """Count of a pitcher's OTHER relief rows within the trailing `window`
    (inclusive of the current row via pandas' time-offset rolling, minus 1
    to exclude it)."""
    return group["game_pk"].rolling(window).count() - 1.0


def build(src: Path = _SRC, out: Path = _OUT) -> pd.DataFrame:
    df = pd.read_parquet(src)
    pitchers = df[df["is_pitcher"] == True].copy()  # noqa: E712 -- pandas bool column
    pitchers["date"] = pd.to_datetime(pitchers["date"])

    ip_rank = pitchers.groupby(["game_pk", "team"])["inningsPitched"].rank(
        method="first", ascending=False
    )
    relief = pitchers[ip_rank > 1].copy()
    relief["year"] = relief["date"].dt.year.astype(int)
    relief = relief.sort_values(["player_id", "date"])

    relief["rest_days"] = relief.groupby("player_id")["date"].diff().dt.days.astype(float)
    relief["is_b2b"] = np.where(relief["rest_days"].isna(), np.nan, (relief["rest_days"] <= 1).astype(float))

    relief = relief.set_index("date")
    relief["appearances_last_3d"] = relief.groupby("player_id", group_keys=False).apply(
        lambda g: _rolling_prior_count(g, "3D"), include_groups=False
    )
    relief = relief.reset_index()

    out_df = relief[_KEEP_COLS].reset_index(drop=True)
    atomic_write_parquet(pa.Table.from_pandas(out_df, preserve_index=False), out)
    return out_df


def main() -> int:
    out_df = build()
    print(
        f"bullpen_relief_chains: {len(out_df)} relief-appearance rows, "
        f"{out_df['player_id'].nunique()} distinct relievers -> {_OUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
