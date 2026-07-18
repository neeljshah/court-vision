"""domains.basketball_wnba.profiles.ingredients_home_away -- WNBA player
home/away split off data/domains/wnba/player_boxscores.parquet's own
`is_home` bool column (2364 home / 2333 away rows, verified) -- no join,
same box source every other player attribute in this package already reads.
DNP rows (played=False) are excluded first -- a scoreless bench DNP is not a
home/away performance observation.

Compound floor: home_games>=8 AND away_games>=8 (task-declared), expressed
as n = min(home_games, away_games) against the registry's single-int floor
column -- same idiom as ingredients_defzone.py's min(min_on, min_off).

Metrics: home_pts_per36, away_pts_per36, home_efg, away_efg, and the two
_diff deltas (home minus away). DESCRIPTIVE season split, no predictive claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/profiles/test_home_away.py -q
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

MIN_GAMES_PER_SIDE = 8  # task-declared: home_games>=8 AND away_games>=8


def _pts_per36(g: pd.DataFrame) -> float:
    return 36.0 * g["pts"].sum() / g["minutes"].sum()


def _efg(g: pd.DataFrame) -> float:
    return (g["fgm"].sum() + 0.5 * g["fg3m"].sum()) / g["fga"].sum()


_METRIC_FN = {"pts_per36": _pts_per36, "efg": _efg}


def _split_table(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    fn = _METRIC_FN[metric]
    played = df[df["played"]]
    names = played.drop_duplicates("player_id", keep="last").set_index("player_id")["player_name"]
    rows = []
    for pid, g in played.groupby("player_id"):
        home = g[g["is_home"]]
        away = g[~g["is_home"]]
        n_home, n_away = len(home), len(away)
        if n_home == 0 or n_away == 0:
            continue
        rows.append({
            "player_id": pid, "player_name": names.get(pid, str(pid)),
            "home_value": fn(home), "away_value": fn(away),
            "n_home": n_home, "n_away": n_away,
        })
    return pd.DataFrame(rows)


def _home_away_builder(metric: str, which: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """which: 'home' | 'away' | 'diff' (home - away)."""
    def _builder(df: pd.DataFrame) -> pd.DataFrame:
        table = _split_table(df, metric)
        if table.empty:
            return pd.DataFrame(columns=["entity_id", "entity_name", "raw_value", "n", "ingredients"])
        out = table.copy()
        out["entity_id"] = out["player_id"].astype(str)
        out["entity_name"] = out["player_name"]
        if which == "home":
            out["raw_value"] = out["home_value"]
        elif which == "away":
            out["raw_value"] = out["away_value"]
        else:
            out["raw_value"] = out["home_value"] - out["away_value"]
        out["n"] = out[["n_home", "n_away"]].min(axis=1)
        out["ingredients"] = out.apply(lambda r: {
            f"home_{metric}": round(float(r.home_value), 4), f"away_{metric}": round(float(r.away_value), 4),
            "n_home": int(r.n_home), "n_away": int(r.n_away),
        }, axis=1)
        return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]
    return _builder


BUILDERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "home_pts_per36": _home_away_builder("pts_per36", "home"),
    "away_pts_per36": _home_away_builder("pts_per36", "away"),
    "home_efg": _home_away_builder("efg", "home"),
    "away_efg": _home_away_builder("efg", "away"),
    "home_away_pts_per36_diff": _home_away_builder("pts_per36", "diff"),
    "home_away_efg_diff": _home_away_builder("efg", "diff"),
}
