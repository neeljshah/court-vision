"""Build leak-free player load and fatigue state from tracking game data.

Run with ``python scripts/platformkit/tracking_load_state.py``. Input and
output paths are rooted at ``NBA_DATA_ROOT`` (or ``./data`` when it is unset).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from scripts.platformkit.tracking_features import _game_key, _minutes_as_float, load_game_dates


def _prior_calendar_sum(
    dates: pd.Series, values: pd.Series, window_days: int
) -> pd.Series:
    """Sum prior observations in the inclusive calendar-day lookback window."""
    prior_dates = dates.shift(1)
    prior_values = values.shift(1)
    sums = []
    window = pd.Timedelta(days=window_days)
    for position, game_date in enumerate(dates):
        history_dates = prior_dates.iloc[: position + 1]
        history_values = prior_values.iloc[: position + 1]
        in_window = (history_dates >= game_date - window) & (history_dates < game_date)
        total = history_values.loc[in_window].sum(min_count=1)
        sums.append(np.nan if pd.isna(total) else float(total))
    return pd.Series(sums, index=dates.index, dtype="float64")


def build_tracking_load_state(
    tracking: pd.DataFrame, game_dates: Mapping[str, str]
) -> pd.DataFrame:
    """Return player-game load state calculated strictly before each game.

    Calendar windows use only observations shifted one game earlier, preventing
    a game's realised tracking values from affecting its own state.
    """
    required = {"gameId", "personId", "minutes", "speed", "distance"}
    missing = sorted(required.difference(tracking.columns))
    if missing:
        raise ValueError("Missing tracking columns: %s" % ", ".join(missing))

    result = tracking.copy()
    result["gameDate"] = result["gameId"].map(
        lambda game_id: game_dates.get(_game_key(game_id))
    )
    missing_dates = int(result["gameDate"].isna().sum())
    if missing_dates:
        raise ValueError("No schedule date for %d tracking rows" % missing_dates)
    result["gameDate"] = pd.to_datetime(result["gameDate"], errors="raise")
    result["_minutes_float"] = _minutes_as_float(result["minutes"])
    result["_distance"] = pd.to_numeric(result["distance"], errors="coerce")
    result["_speed"] = pd.to_numeric(result["speed"], errors="coerce")
    result = result.sort_values(["personId", "gameDate"], kind="mergesort").reset_index(
        drop=True
    )

    states = []
    for _, player_games in result.groupby("personId", sort=False):
        player_state = player_games.copy()
        player_state["cum_distance_7d"] = _prior_calendar_sum(
            player_state["gameDate"], player_state["_distance"], 7
        )
        player_state["cum_distance_14d"] = _prior_calendar_sum(
            player_state["gameDate"], player_state["_distance"], 14
        )
        player_state["minutes_7d"] = _prior_calendar_sum(
            player_state["gameDate"], player_state["_minutes_float"], 7
        )
        player_state["days_rest"] = player_state["gameDate"].diff().dt.days
        prior_speed = player_state["_speed"].shift(1)
        speed_l3 = prior_speed.rolling(3, min_periods=1).mean()
        speed_l10 = prior_speed.rolling(10, min_periods=1).mean()
        player_state["speed_decline_ratio"] = speed_l3.div(speed_l10.replace(0, np.nan))
        player_state["b2b"] = player_state["days_rest"].eq(1)
        states.append(player_state)

    return pd.concat(states, ignore_index=True).drop(
        columns=["_minutes_float", "_distance", "_speed"]
    )


def main() -> None:
    """Build and write the production player load-state parquet."""
    data_root = Path(os.environ.get("NBA_DATA_ROOT", "data"))
    nba_dir = data_root / "nba"
    tracking = pd.read_parquet(nba_dir / "player_tracking_games.parquet")
    state = build_tracking_load_state(tracking, load_game_dates(nba_dir / "schedule"))
    output = nba_dir / "player_load_state_asof.parquet"
    state.to_parquet(output, index=False)
    print("Wrote %d rows to %s" % (len(state), output))


if __name__ == "__main__":
    main()
