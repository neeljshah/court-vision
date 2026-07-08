"""player_team_agg -- minutes/innings-weighted player->team aggregation (design (a)).

Prior-season (e.g. 2024-25 / 2025) player_id claim values get rolled up to the
TEAM the player actually played for in that SAME prior season, weighted by his
playing-time share for that team (NBA: minutes; MLB: outs recorded, a pitcher
innings proxy that is always populated, unlike inningsPitched which has NaN
rows for non-pitchers). Both the claim value and the playing-time weights are
season N-1 numbers, known before the eval season (N) starts -- so the
aggregation stays leak-free just like the team-keyed path.

ponytail: prior-season roster only -- blind to trades/rookies entering the
eval season. Upgrade path (design (b), NOT implemented here): eval-season
opening-roster games (first-N games) playing time instead -- still leak-free
(uses only games played so far) but reflects the eval-season team. Swap in
if trades/rookie churn are shown to bias verdicts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
MIN_COVERAGE = 0.60

# Per-sport playing-time source: season_col=None means derive season=year(date)
# (MLB gamelogs carry no season column). filter_col restricts to the relevant
# role (MLB bullpen-fatigue claims are pitcher-keyed; non-pitcher rows would
# just dilute the weighted mean with irrelevant playing time).
_BOX_SOURCES: Dict[str, dict] = {
    "nba": {"path": REPO_ROOT / "data/domains/basketball_nba/player_boxscores.parquet",
            "weight_col": "min", "season_col": "season", "filter_col": None},
    "mlb": {"path": REPO_ROOT / "data/domains/mlb/player_gamelogs.parquet",
            "weight_col": "outs", "season_col": None, "filter_col": "is_pitcher"},
}
# MLB gamelogs use standard team codes (SD/SF/KC/TB/CHC.../WSH/AZ/ATH); the
# eval games table (games_current.parquet) uses the ESPN-style codes this repo
# already crosswalks in scripts/platformkit/ingame/statcast_winprob_join.py's
# _XW -- mirrored here (ESPN -> standard) so aggregated team keys land on the
# SAME codes run_gate will look up in games_df.home_team/away_team.
_MLB_ESPN_TO_STD = {"ARI": "AZ", "CUB": "CHC", "KAN": "KC", "OAK": "ATH", "SDG": "SD",
                     "SFO": "SF", "TAM": "TB", "WAS": "WSH"}
_MLB_STD_TO_ESPN = {v: k for k, v in _MLB_ESPN_TO_STD.items()}


def prior_season(eval_season: str, style: str = "split") -> str:
    """'2025-26' -> '2024-25' (style='split', NBA); '2026' -> '2025'
    (style='plain', MLB -- same convention as claim_features.prior_season_metrics)."""
    if style == "plain":
        return str(int(eval_season) - 1)
    start = int(eval_season.split("-")[0])
    return f"{start - 1:04d}-{start % 100:02d}"


def _season_team_minutes(season: str, sport: str = "nba",
                          boxscores: Optional[Path] = None) -> pd.DataFrame:
    """(team, player_id) -> summed playing-time weight for one season. A
    traded player gets one row per team he actually played for that season."""
    src = _BOX_SOURCES[sport]
    path = boxscores or src["path"]
    time_col = src["season_col"] or "date"
    cols = ["team", "player_id", src["weight_col"], time_col]
    if src["filter_col"]:
        cols.append(src["filter_col"])
    df = pd.read_parquet(path, columns=cols)
    if src["filter_col"]:
        df = df[df[src["filter_col"]].astype(bool)]
    if src["season_col"]:
        df = df[df[src["season_col"]].astype(str) == season]
    else:
        df = df[pd.to_datetime(df[time_col]).dt.year.astype(str) == season]
    tm = (df.groupby(["team", "player_id"], as_index=False)[src["weight_col"]].sum()
            .rename(columns={src["weight_col"]: "minutes"}))
    if sport == "mlb":
        tm["team"] = tm["team"].map(lambda t: _MLB_STD_TO_ESPN.get(str(t), str(t)))
    return tm


def aggregate_to_team(player_values: Dict[str, float], season: str,
                       sport: str = "nba", min_coverage: float = MIN_COVERAGE,
                       boxscores: Optional[Path] = None) -> Tuple[Dict[str, float], List[str]]:
    """Playing-time-weighted mean of a {player_id: value} claim metric, rolled
    up to {team: value} for `season` (the SAME season the claim values and the
    playing-time weights both come from -- design (a), fully leak-free).

    Coverage floor: a team is dropped (excluded from the result, listed in
    dropped_teams) unless players carrying a claim value cover >= min_coverage
    of that team's total season playing time -- guards against extrapolating a
    team average from a handful of bench/mop-up appearances.
    """
    tm = _season_team_minutes(season, sport, boxscores)
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
