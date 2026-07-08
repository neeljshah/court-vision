"""player_team_agg -- minutes-weighted player->team aggregation (design (a)).

Prior-season (e.g. 2024-25) player_id claim values get rolled up to the TEAM
the player actually played for in that SAME prior season, weighted by the
minutes he logged for that team. Both the claim value and the roster/minutes
weights are season N-1 numbers, known before the eval season (N) starts --
so the aggregation stays leak-free just like the team-keyed path.

ponytail: prior-season roster only -- blind to trades/rookies entering the
eval season. Upgrade path (design (b), NOT implemented here): eval-season
opening-roster games (first-N games) minutes instead -- still leak-free
(uses only games played so far) but reflects the eval-season team. Swap in
if trades/rookie churn are shown to bias verdicts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
BOXSCORES = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
MIN_COVERAGE = 0.60


def prior_season(eval_season: str) -> str:
    """'2025-26' -> '2024-25' (same convention as claim_features.prior_season_metrics)."""
    start = int(eval_season.split("-")[0])
    return f"{start - 1:04d}-{start % 100:02d}"


def _season_team_minutes(season: str, boxscores: Optional[Path] = None) -> pd.DataFrame:
    """(team, player_id) -> summed minutes for one season. A traded player gets
    one row per team he actually logged minutes for that season."""
    path = boxscores or BOXSCORES
    df = pd.read_parquet(path, columns=["season", "team", "player_id", "min"])
    df = df[df["season"].astype(str) == season]
    return (df.groupby(["team", "player_id"], as_index=False)["min"].sum()
              .rename(columns={"min": "minutes"}))


def aggregate_to_team(player_values: Dict[str, float], season: str,
                       min_coverage: float = MIN_COVERAGE,
                       boxscores: Optional[Path] = None) -> Tuple[Dict[str, float], List[str]]:
    """Minutes-weighted mean of a {player_id: value} claim metric, rolled up to
    {team: value} for `season` (the SAME season the claim values and the
    minutes weights both come from -- design (a), fully leak-free).

    Coverage floor: a team is dropped (excluded from the result, listed in
    dropped_teams) unless players carrying a claim value cover >= min_coverage
    of that team's total season minutes -- guards against extrapolating a
    team average from a handful of bench players.
    """
    tm = _season_team_minutes(season, boxscores)
    if tm.empty or not player_values:
        return {}, []
    tm = tm.copy()
    tm["player_id"] = tm["player_id"].astype(str)
    tm["value"] = tm["player_id"].map(player_values)
    tm["has_value"] = tm["value"].notna()

    team_values: Dict[str, float] = {}
    dropped: List[str] = []
    for team, grp in tm.groupby("team"):
        total_min = grp["minutes"].sum()
        cov = grp.loc[grp["has_value"]]
        covered_min = cov["minutes"].sum()
        if total_min <= 0 or covered_min / total_min < min_coverage:
            dropped.append(str(team))
            continue
        team_values[str(team)] = float((cov["value"] * cov["minutes"]).sum() / covered_min)
    return team_values, sorted(dropped)


if __name__ == "__main__":  # tiny self-check
    fake = pd.DataFrame({
        "season": ["2024-25"] * 4,
        "team": ["A", "A", "B", "B"],
        "player_id": [1, 2, 3, 4],
        "min": [30.0, 10.0, 5.0, 1.0],
    })
    tmp = REPO_ROOT / "data" / "cache" / "_selfcheck_player_team_agg.parquet"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    fake.to_parquet(tmp)
    try:
        vals = {"1": 10.0, "2": 2.0}   # team A fully covered (40/40 min); team B uncovered
        tv, dropped = aggregate_to_team(vals, "2024-25", boxscores=tmp)
        assert abs(tv["A"] - 8.0) < 1e-9, tv          # (10*30 + 2*10) / 40 = 8.0
        assert "B" in dropped and "A" not in dropped, (tv, dropped)
        assert prior_season("2025-26") == "2024-25"
        print(f"OK team_values={tv} dropped={dropped}")
    finally:
        tmp.unlink()
