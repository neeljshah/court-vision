"""
Ingest: 5-man lineup on/off splits from BoxScoreAdvancedV2.

Fetches per-game lineup data and computes on/off net rating for each
5-man unit. Caches to data/lineups.parquet.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd

log = logging.getLogger(__name__)

_CACHE_PATH = Path("data/lineups.parquet")
_SLEEP_S    = 0.6


def _fetch_lineup(game_id: str) -> Optional[pd.DataFrame]:
    try:
        from nba_api.stats.endpoints import BoxScoreAdvancedV2  # type: ignore
        resp = BoxScoreAdvancedV2(game_id=game_id)
        dfs  = resp.get_data_frames()
        # index 0 = PlayerStats, index 1 = TeamStats
        return dfs[0] if dfs else None
    except Exception as exc:
        log.warning("BoxScoreAdvancedV2 failed game=%s: %s", game_id, exc)
        return None


def _fetch_5man_units(game_id: str) -> Optional[pd.DataFrame]:
    """LeagueDashLineups for 5-man units (season-level, not per-game)."""
    try:
        from nba_api.stats.endpoints import LeagueDashLineups  # type: ignore
        resp = LeagueDashLineups(
            group_quantity=5,
            per_mode_simple="PerGame",
            season="2024-25",
        )
        dfs = resp.get_data_frames()
        return dfs[0] if dfs else None
    except Exception as exc:
        log.warning("LeagueDashLineups failed: %s", exc)
        return None


def ingest_lineup_data(
    game_ids: List[str],
    cache_path: Path = _CACHE_PATH,
    sleep_s: float = _SLEEP_S,
) -> pd.DataFrame:
    """
    Fetch advanced player stats (NET_RATING, USG_PCT, etc.) per game.

    Returns DataFrame with game_id + advanced box score columns.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    cached_ids: set = set()
    frames: List[pd.DataFrame] = []

    if cache_path.exists():
        try:
            cached_df  = pd.read_parquet(cache_path)
            cached_ids = set(cached_df["game_id"].astype(str))
            frames.append(cached_df)
            log.info("lineup_data: %d games cached", len(cached_ids))
        except Exception as exc:
            log.warning("lineup_data cache read failed: %s", exc)

    new_ids = [g for g in game_ids if str(g) not in cached_ids]
    log.info("lineup_data: fetching %d new games", len(new_ids))

    for game_id in new_ids:
        df = _fetch_lineup(game_id)
        if df is not None and not df.empty:
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]
            df["game_id"] = str(game_id)
            frames.append(df)
        time.sleep(sleep_s)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result = result.drop_duplicates(subset=["game_id", "player_id"] if "player_id" in result.columns else ["game_id"])

    try:
        result.to_parquet(cache_path, index=False)
        log.info("lineup_data: saved %d rows", len(result))
    except Exception as exc:
        log.error("lineup_data cache write failed: %s", exc)

    return result
