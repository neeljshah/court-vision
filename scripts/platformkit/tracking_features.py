"""Build leak-free NBA player tracking features at player-game grain.

Run with ``python scripts/platformkit/tracking_features.py``.  Input and output
paths are rooted at ``NBA_DATA_ROOT`` (or ``./data`` when it is unset).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd


RATE_COLUMNS = (
    "touches",
    "passes",
    "distance",
    "reboundChancesTotal",
    "secondaryAssists",
)
WINDOWS = (5, 10)


def _game_key(value: object) -> str:
    """Normalise NBA game identifiers while preserving their ten-digit format."""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(10) if text.isdigit() else text


def load_game_dates(schedule_dir: Path) -> dict[str, str]:
    """Load the ``game_id -> date`` index from NBA schedule JSON files."""
    game_dates: dict[str, str] = {}
    for path in sorted(schedule_dir.glob("schedule_*_v2.json")):
        with path.open(encoding="utf-8") as handle:
            games = json.load(handle)
        for game in games:
            game_id = _game_key(game["game_id"])
            game_date = game["date"]
            old_date = game_dates.setdefault(game_id, game_date)
            if old_date != game_date:
                raise ValueError("Conflicting dates for gameId %s" % game_id)
    if not game_dates:
        raise FileNotFoundError("No schedule_*_v2.json files in %s" % schedule_dir)
    return game_dates


def _minutes_as_float(minutes: pd.Series) -> pd.Series:
    """Convert NBA ``MM:SS`` minutes strings to fractional minutes."""
    parts = minutes.astype("string").str.split(":", n=1, expand=True)
    if parts.shape[1] != 2:
        return pd.to_numeric(minutes, errors="coerce")
    return pd.to_numeric(parts[0], errors="coerce") + (
        pd.to_numeric(parts[1], errors="coerce") / 60.0
    )


def build_tracking_features(
    tracking: pd.DataFrame, game_dates: Mapping[str, str]
) -> pd.DataFrame:
    """Return player-game tracking data with strictly prior L5 and L10 rates.

    Each rolling mean is calculated from ``shift(1)`` values within a player,
    so a game's realized tracking observations cannot affect its own features.
    """
    required = {"gameId", "personId", "minutes", "speed", *RATE_COLUMNS}
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

    for column in RATE_COLUMNS:
        rate = pd.to_numeric(result[column], errors="coerce").div(
            result["_minutes_float"].replace(0, np.nan)
        ).mul(36.0)
        result["_%s_per36" % column] = rate

    result = result.sort_values(["personId", "gameDate"], kind="mergesort").reset_index(
        drop=True
    )
    grouped = result.groupby("personId", sort=False)
    for column in RATE_COLUMNS:
        rate_column = "_%s_per36" % column
        for window in WINDOWS:
            feature = "%s_per36_l%d" % (column, window)
            result[feature] = grouped[rate_column].transform(
                lambda values: values.shift(1).rolling(window, min_periods=1).mean()
            )

    return result.drop(columns=["_minutes_float"] + ["_%s_per36" % c for c in RATE_COLUMNS])


def main() -> None:
    """Build and write the production player tracking feature parquet."""
    data_root = Path(os.environ.get("NBA_DATA_ROOT", "data"))
    nba_dir = data_root / "nba"
    tracking = pd.read_parquet(nba_dir / "player_tracking_games.parquet")
    features = build_tracking_features(
        tracking, load_game_dates(nba_dir / "schedule")
    )
    output = nba_dir / "player_tracking_features_asof.parquet"
    features.to_parquet(output, index=False)
    print("Wrote %d rows to %s" % (len(features), output))


if __name__ == "__main__":
    main()
