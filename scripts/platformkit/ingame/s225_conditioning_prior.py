"""Strictly-prior S225 conditioning reconstruction."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

RAW_COLUMNS = ("game_id", "period", "seconds_remaining", "score_diff", "outcome", "team", "season")
ARCHIVED_VALUE_COLUMNS = {"hot_night": "cond_prior", "scheme_fit": "cond_val"}


def source_paths(root: Path, layer: str) -> tuple[Path, Path]:
    """Return the two S225 source stores for one conditioning family."""
    return tuple(root / ("ingame_hypothesis_%s_%s_rows.parquet" % (layer, season))
                 for season in ("2024-25", "2025-26"))


def load_raw_game_rows(root: Path, layer: str, bridge: pd.DataFrame) -> pd.DataFrame:
    """Read one source store at a time, deliberately excluding archived values."""
    parts = []
    for path in source_paths(root, layer):
        raw = pd.read_parquet(path, columns=list(RAW_COLUMNS))
        assert ARCHIVED_VALUE_COLUMNS[layer] not in raw.columns, "archived conditioning value read"
        raw["game"] = raw["game_id"].astype(str)
        raw["game_date"] = raw["game"].map(bridge["date"])
        parts.append(raw[raw["game_date"].notna()].copy())
    return pd.concat(parts, ignore_index=True)


def alignment_rows(raw: pd.DataFrame) -> pd.DataFrame:
    """Return raw clock fields for the premise alignment check."""
    return raw[["game", "season", "period", "seconds_remaining"]].copy()


def _team_game_rows(raw: pd.DataFrame) -> pd.DataFrame:
    first = raw.groupby(["game", "team"], sort=False, as_index=False).first()
    return first[["game", "team", "game_date", "outcome", "score_diff"]].copy()


def _signal(layer: str, record: dict) -> float:
    if layer == "hot_night":
        return (sum(record["wins"]) + 1.0) / (len(record["wins"]) + 2.0)
    mean_diff = float(np.mean(record["score_diffs"])) if record["score_diffs"] else 0.0
    return float(1.0 / (1.0 + np.exp(-mean_diff / 12.0)))


def rebuild_prior_conditions(raw: pd.DataFrame, bridge: pd.DataFrame, layer: str) -> pd.DataFrame:
    """Build real and planted-null values only from games before each game date."""
    game_rows = _team_game_rows(raw)
    pair = bridge[["home_nba", "away_nba"]].copy()
    games = game_rows.groupby(["game", "game_date"], sort=True).agg(
        teams=("team", list), outcomes=("outcome", list), score_diffs=("score_diff", list)
    ).reset_index()
    games["home"] = games["game"].map(pair["home_nba"])
    games["away"] = games["game"].map(pair["away_nba"])
    games = games[games["home"].notna() & games["away"].notna()].sort_values(
        ["game_date", "game"], kind="stable"
    )
    history = defaultdict(lambda: {"wins": [], "score_diffs": [], "dates": []})
    global_values: list[float] = []
    randomizer = np.random.default_rng(22504 if layer == "hot_night" else 22505)
    values = []
    for game_date, same_date in games.groupby("game_date", sort=True):
        game_date = pd.Timestamp(game_date).strftime("%Y-%m-%d")
        for item in same_date.itertuples(index=False):
            home_record, away_record = history[str(item.home)], history[str(item.away)]
            assert all(date < game_date for date in home_record["dates"] + away_record["dates"])
            home_value, away_value = _signal(layer, home_record), _signal(layer, away_record)
            if global_values:
                null_home, null_away = randomizer.choice(global_values, size=2, replace=True)
            else:
                null_home = null_away = 0.5
            prior_dates = home_record["dates"] + away_record["dates"]
            values.append({"game": str(item.game), "game_date": str(game_date),
                           "condition": float(home_value - away_value),
                           "null_condition": float(null_home - null_away),
                           "prior_last_game_date": max(prior_dates, default=None)})
        for item in same_date.itertuples(index=False):
            for team, outcome, score_diff in zip(item.teams, item.outcomes, item.score_diffs):
                record = history[str(team)]
                record["wins"].append(float(outcome)); record["score_diffs"].append(float(score_diff))
                record["dates"].append(str(game_date))
                global_values.append(_signal(layer, record))
    result = pd.DataFrame(values)
    assert (result["prior_last_game_date"].dropna() < result.loc[
        result["prior_last_game_date"].notna(), "game_date"]).all(), "prior date leak"
    return result
