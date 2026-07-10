"""domains.mlb.oaa_asof_builder -- team-level trailing/as-of fielding-quality
feature builder (Gate Lane A4).

Sources: data/cache/statcast/leaderboards/outs_above_average_consolidated.parquet
(~790 player-season rows, 2024-2026) and .../catch_probability_consolidated.parquet
(~284 player-season rows, 2024-2026). Both are SEASON-CUMULATIVE leaderboards
(the 2026 rows are a running in-season total as of whenever they were pulled) --
using a season's own rows to condition games WITHIN that same season would LEAK
(future games contribute to the very stat predicting them). The only leak-free
use is TRAILING: build the team feature from year == target_season - 1 (a
season that finished before target_season started) and apply it to
target_season games/plays. That is the only mode this module offers.

Composite: outs_above_average (OAA, sum across a team's fielders) is the
primary, well-established defensive-runs-saved proxy. catch_probability adds a
star-tier actual-vs-expected catch-rate signal, but that file carries no team
column -- player_id is joined back to a team via the SAME trailing-year OAA
rows (both are savant leaderboard exports keyed on the same MLBAM player_id).
Rows with display_team_name == '---' (mid-season multi-team stints) are
dropped -- team is genuinely ambiguous for those, not a data bug.
fielding_quality_z is the row-wise mean of the two z-scored columns (whichever
exist -- a team with zero catch-prob rows still gets a defined value from OAA
alone).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
_LEADERBOARD_DIR = _REPO / "data/cache/statcast/leaderboards"
OAA_PATH = _LEADERBOARD_DIR / "outs_above_average_consolidated.parquet"
CATCH_PROB_PATH = _LEADERBOARD_DIR / "catch_probability_consolidated.parquet"

# display_team_name (OAA/catch-prob) -> statcast home_team/away_team code
# (savant_full__*.parquet). Stable 30-team mapping; '---' (multi-team stint)
# is intentionally absent -- those rows are dropped, not mapped.
TEAM_ABBREV = {
    "Angels": "LAA", "Astros": "HOU", "Athletics": "ATH", "Blue Jays": "TOR",
    "Braves": "ATL", "Brewers": "MIL", "Cardinals": "STL", "Cubs": "CHC",
    "D-backs": "AZ", "Dodgers": "LAD", "Giants": "SF", "Guardians": "CLE",
    "Mariners": "SEA", "Marlins": "MIA", "Mets": "NYM", "Nationals": "WSH",
    "Orioles": "BAL", "Padres": "SD", "Phillies": "PHI", "Pirates": "PIT",
    "Rangers": "TEX", "Rays": "TB", "Red Sox": "BOS", "Reds": "CIN",
    "Rockies": "COL", "Royals": "KC", "Tigers": "DET", "Twins": "MIN",
    "White Sox": "CWS", "Yankees": "NYY",
}

_CATCH_TIER_COLS = ["1stars", "2stars", "3stars", "4stars", "5stars"]


def _zscore(s: pd.Series) -> pd.Series:
    m, sd = float(np.nanmean(s.values)), float(np.nanstd(s.values))
    if sd < 1e-8:
        return pd.Series(0.0, index=s.index)
    return (s - m) / sd


def build_team_fielding_trailing(
    target_season: int,
    oaa_df: Optional[pd.DataFrame] = None,
    catch_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Team-level as-of fielding-quality feature for target_season, built
    ENTIRELY from year == target_season - 1 (trailing, leak-free) rows.
    Returns columns: team, target_season, oaa_sum, n_oaa_players, catch_rate,
    n_catch_opp, fielding_quality_z. One row per team with >=1 trailing-year
    OAA player row (typically all 30)."""
    trailing_year = target_season - 1
    oaa = oaa_df if oaa_df is not None else pd.read_parquet(OAA_PATH)
    oaa_t = oaa[(oaa["year"] == trailing_year) & (oaa["display_team_name"] != "---")].copy()

    oaa_agg = (oaa_t.groupby("display_team_name")
               .agg(oaa_sum=("outs_above_average", "sum"),
                    n_oaa_players=("player_id", "size"))
               .reset_index())
    oaa_agg["team"] = oaa_agg["display_team_name"].map(TEAM_ABBREV)
    oaa_agg = oaa_agg.dropna(subset=["team"])

    # player_id -> team for the SAME trailing year, to attribute catch-prob rows.
    id_to_team = (oaa_t.drop_duplicates("player_id")
                  .set_index("player_id")["display_team_name"].map(TEAM_ABBREV))

    catch = catch_df if catch_df is not None else pd.read_parquet(CATCH_PROB_PATH)
    catch_t = catch[catch["year"] == trailing_year].copy()
    catch_t["team"] = catch_t["player_id"].map(id_to_team)
    catch_t = catch_t.dropna(subset=["team"])

    fieldout_cols = ["n_fieldout_%s" % c for c in _CATCH_TIER_COLS]
    opp_cols = ["n_opp_%s" % c for c in _CATCH_TIER_COLS]
    catch_t["_fieldout_sum"] = catch_t[fieldout_cols].sum(axis=1)
    catch_t["_opp_sum"] = catch_t[opp_cols].sum(axis=1)
    catch_agg = (catch_t.groupby("team")
                 .agg(n_fieldout=("_fieldout_sum", "sum"), n_catch_opp=("_opp_sum", "sum"))
                 .reset_index())
    catch_agg["catch_rate"] = np.where(
        catch_agg["n_catch_opp"] > 0, catch_agg["n_fieldout"] / catch_agg["n_catch_opp"], np.nan)

    out = oaa_agg[["team", "oaa_sum", "n_oaa_players"]].merge(
        catch_agg[["team", "catch_rate", "n_catch_opp"]], on="team", how="left")
    out["oaa_z"] = _zscore(out["oaa_sum"])
    out["catch_rate_z"] = _zscore(out["catch_rate"])  # NaN teams excluded from mean/std, then...
    out["catch_rate_z"] = out["catch_rate_z"].fillna(0.0)  # ...neutral (no evidence) not penalized
    out["fielding_quality_z"] = out[["oaa_z", "catch_rate_z"]].mean(axis=1)
    out["target_season"] = target_season
    out["trailing_year"] = trailing_year
    return out[["team", "target_season", "trailing_year", "oaa_sum", "n_oaa_players",
                "catch_rate", "n_catch_opp", "fielding_quality_z"]]


def main() -> int:
    for season in (2025, 2026):
        df = build_team_fielding_trailing(season)
        print("target_season=%d trailing_year=%d teams=%d" % (season, season - 1, len(df)))
        print(df.sort_values("fielding_quality_z", ascending=False).head(5).to_string(index=False))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_team_fielding_trailing", "TEAM_ABBREV", "OAA_PATH", "CATCH_PROB_PATH"]
