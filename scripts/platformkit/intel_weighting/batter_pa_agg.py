"""batter_pa_agg -- plate-appearance-weighted batter/catcher->team
aggregation (MLB). Unblocks the 4 MLB attribute-gate rows that were
UNTESTABLE_NO_TEAM_AGG under player_team_agg.aggregate_to_team: that function
is wired pitcher-outs-weighted only (_BOX_SOURCES["mlb"] filters is_pitcher),
so a batter/catcher attribute's player_values never match any weighted row
-> every team drops below the coverage floor -> zero teams survive.

role in {"batter", "catcher"} picks a same-role PA denominator (position=="C"
for catcher, everyone else non-pitcher for batter) -- mirroring the pitcher
agg's own-role-only convention. A whole-roster denominator would starve a
catcher attribute below the coverage floor since catchers are a small share
of total team PA.

Same design (a) leak-free convention as player_team_agg.aggregate_to_team:
prior-season player attribute values roll up to the team the player actually
played for in that SAME prior season, weighted by his playing-time share for
that team -- both the claim values and the weights are season N-1 numbers,
known before the eval season (N) starts. Mirrors player_team_agg's file
(player_gamelogs.parquet), date-derived season, and team-code crosswalk
exactly so a batter-attribute gate result differs from the pitcher path ONLY
by the aggregation weighting, not by season convention or source file.

PA proxy = atBats + baseOnBalls + hitByPitch (sac bunts/flies/catcher's-
interference are not carried by player_gamelogs.parquet). An approximation,
not the official PA formula.

ponytail: a separate module instead of generalizing player_team_agg's
_BOX_SOURCES config for a derived multi-column weight + negated filter --
that generalization has exactly one caller today (this one). Fold the two
together if a 3rd role needs the same shape.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from scripts.platformkit.intel_weighting.player_team_agg import (
    MIN_COVERAGE, REPO_ROOT, _MLB_STD_TO_ESPN,
)

_GAMELOGS = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_PA_COLS = ["atBats", "baseOnBalls", "hitByPitch"]


def _role_mask(df: pd.DataFrame, role: str) -> pd.Series:
    """Same-role filter, mirroring player_team_agg's is_pitcher convention:
    the coverage denominator must be that role's OWN playing time, not the
    whole roster's -- a catcher is a small share of team PA, so denominating
    against all-batter PA would starve every team below the coverage floor."""
    if role == "catcher":
        return df["position"].astype(str) == "C"
    return (~df["is_pitcher"].astype(bool)) & (df["position"].astype(str) != "C")


def _season_team_pa(season: str, role: str, gamelogs: Optional[Path] = None) -> pd.DataFrame:
    """(team, player_id) -> summed PA weight for one season, `role`-only rows
    -- same file/date-derived-season convention as
    player_team_agg._season_team_minutes's MLB branch."""
    path = gamelogs or _GAMELOGS
    cols = ["team", "player_id", "date", "is_pitcher", "position"] + _PA_COLS
    df = pd.read_parquet(path, columns=cols)
    df = df[_role_mask(df, role)]
    df = df[pd.to_datetime(df["date"]).dt.year.astype(str) == season]
    df = df.copy()
    df["pa"] = df[_PA_COLS].fillna(0.0).sum(axis=1)
    tm = (df.groupby(["team", "player_id"], as_index=False)["pa"].sum()
            .rename(columns={"pa": "minutes"}))
    tm["team"] = tm["team"].map(lambda t: _MLB_STD_TO_ESPN.get(str(t), str(t)))
    return tm


def aggregate_to_team_batter_pa(player_values: Dict[str, float], season: str,
                                role: str = "batter", min_coverage: float = MIN_COVERAGE,
                                gamelogs: Optional[Path] = None
                                ) -> Tuple[Dict[str, float], List[str]]:
    """PA-weighted mean of a {player_id: value} batter/catcher claim, rolled
    up to {team: value} for `season`. `role` in {"batter", "catcher"} picks
    the same-role denominator (see _role_mask). Same coverage-floor semantics
    as player_team_agg.aggregate_to_team -- a team is dropped unless players
    carrying a claim value cover >= min_coverage of that role's total PA."""
    tm = _season_team_pa(season, role, gamelogs)
    if tm.empty or not player_values:
        return {}, []
    tm = tm.copy()
    tm["player_id"] = tm["player_id"].astype(str)
    tm["value"] = tm["player_id"].map(player_values)
    tm["has_value"] = tm["value"].notna()

    team_values: Dict[str, float] = {}
    dropped: List[str] = []
    for team, grp in tm.groupby("team"):
        total_pa = grp["minutes"].sum()
        cov = grp.loc[grp["has_value"]]
        covered_pa = cov["minutes"].sum()
        if total_pa <= 0 or covered_pa / total_pa < min_coverage:
            dropped.append(str(team))
            continue
        team_values[str(team)] = float((cov["value"] * cov["minutes"]).sum() / covered_pa)
    return team_values, sorted(dropped)


if __name__ == "__main__":  # tiny self-check
    fake = pd.DataFrame({
        "date": [pd.Timestamp("2024-06-01")] * 4,
        "team": ["SD", "SD", "BOS", "BOS"],
        "player_id": [1, 2, 3, 4],
        "atBats": [4.0, 3.0, 2.0, 0.0],
        "baseOnBalls": [0.0, 0.0, 0.0, 1.0],
        "hitByPitch": [0.0, 0.0, 0.0, 0.0],
        "is_pitcher": [False, False, False, False],
        "position": ["1B", "2B", "3B", "SS"],
    })
    tmp = REPO_ROOT / "data" / "cache" / "_selfcheck_batter_pa_agg.parquet"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    fake.to_parquet(tmp)
    try:
        vals = {"1": 10.0, "2": 2.0}   # SD fully covered (7/7 PA); BOS uncovered
        tv, dropped = aggregate_to_team_batter_pa(vals, "2024", gamelogs=tmp)
        assert abs(tv["SDG"] - 46 / 7) < 1e-9, tv   # (10*4+2*3)/7
        assert "BOS" in dropped and "SDG" not in dropped, (tv, dropped)
        print(f"OK team_values={tv} dropped={dropped}")
    finally:
        tmp.unlink()
