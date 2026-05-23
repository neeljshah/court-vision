"""
Ingest: Synergy play-type rates per player-season.

Endpoint: SynergyPlayTypes (nba_api). Fetches isolation, P&R ball-handler,
spot-up, transition, post-up, cut, off-screen, handoff rates.

Caches to data/playtypes.parquet. Logs + continues on failure.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd

log = logging.getLogger(__name__)

_CACHE_PATH  = Path("data/playtypes.parquet")
_SLEEP_S     = 0.6
_PLAY_TYPES  = [
    "Isolation", "PRBallHandler", "PRRollman", "Postup",
    "Spotup", "Handoff", "Cut", "OffScreen", "Transition",
]
_SEASON      = "2024-25"


def _fetch_synergy(play_type: str, season: str) -> Optional[pd.DataFrame]:
    """Fetch one Synergy play-type slice. Param names per current nba_api (2026):
    `per_mode_simple` (not _nullable), `season` (not season_year_nullable)."""
    try:
        from nba_api.stats.endpoints import SynergyPlayTypes  # type: ignore
        resp = SynergyPlayTypes(
            play_type_nullable=play_type,
            type_grouping_nullable="offensive",
            per_mode_simple="PerGame",
            season=season,
        )
        dfs = resp.get_data_frames()
        if dfs:
            df = dfs[0].copy()
            df["play_type"] = play_type
            return df
    except Exception as exc:
        log.warning("SynergyPlayTypes(%s) failed: %s", play_type, exc)
    return None


def ingest_playtype_rates(
    season: str = _SEASON,
    cache_path: Path = _CACHE_PATH,
    sleep_s: float = _SLEEP_S,
) -> pd.DataFrame:
    """
    Fetch Synergy play-type rates for all players in `season`.

    Returns long-form DataFrame: player_id, play_type, poss_pct, pts_per_poss, freq_pct, etc.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        try:
            cached = pd.read_parquet(cache_path)
            if "season" in cached.columns and season in cached["season"].values:
                log.info("playtype_rates: season %s already cached (%d rows)", season, len(cached))
                return cached[cached["season"] == season]
        except Exception as exc:
            log.warning("playtype_rates cache read failed: %s", exc)

    frames: List[pd.DataFrame] = []
    for pt in _PLAY_TYPES:
        df = _fetch_synergy(pt, season)
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            df["season"] = season
            frames.append(df)
            log.debug("playtype_rates: fetched %s (%d rows)", pt, len(df))
        time.sleep(sleep_s)

    if not frames:
        log.error("playtype_rates: no data fetched for season %s", season)
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    # Merge with existing cache if present
    if cache_path.exists():
        try:
            existing = pd.read_parquet(cache_path)
            result = pd.concat([existing, result]).drop_duplicates(
                subset=["player_id", "play_type", "season"] if "player_id" in result.columns else None
            )
        except Exception:
            pass

    try:
        result.to_parquet(cache_path, index=False)
        log.info("playtype_rates: saved %d rows to %s", len(result), cache_path)
    except Exception as exc:
        log.error("playtype_rates cache write failed: %s", exc)

    return result
