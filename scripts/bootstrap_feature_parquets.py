"""bootstrap_feature_parquets.py — Build data/playtypes.parquet + data/rest_travel.parquet.

Runs the existing ingest functions for each season the local gamelogs cover,
so the rest_travel + playtype features the per-game prop models reference
actually carry signal instead of defaulting to zero.

Safe to re-run — both ingests cache by season.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bootstrap")


def seasons_from_gamelogs(gamelog_dir: str) -> List[str]:
    """Scan filenames like gamelog_<pid>_<season>.json for distinct season strings."""
    seasons: set[str] = set()
    for fname in os.listdir(gamelog_dir):
        if not fname.startswith("gamelog_") or not fname.endswith(".json"):
            continue
        if fname.startswith("gamelog_full_"):
            continue
        parts = fname.removesuffix(".json").split("_")
        if len(parts) >= 3:
            season = parts[-1]
            if "-" in season:
                seasons.add(season)
    return sorted(seasons)


def fetch_season_game_ids(season: str) -> List[str]:
    """Pull every game_id played in the season via LeagueGameLog."""
    from nba_api.stats.endpoints import LeagueGameLog
    resp = LeagueGameLog(season=season, season_type_all_star="Regular Season")
    df = resp.get_data_frames()[0]
    return sorted(df["GAME_ID"].astype(str).unique().tolist())


def build_playtypes(seasons: List[str]) -> None:
    from src.ingest.playtype_rates import ingest_playtype_rates
    for s in seasons:
        log.info("playtypes: fetching season %s", s)
        try:
            df = ingest_playtype_rates(season=s)
            log.info("playtypes: season %s -> %d rows", s, len(df))
        except Exception as exc:  # noqa: BLE001
            log.warning("playtypes: season %s failed: %s", s, exc)


def build_rest_travel(seasons: List[str]) -> None:
    from src.ingest.rest_travel import ingest_rest_travel
    for s in seasons:
        log.info("rest_travel: fetching season %s game ids", s)
        try:
            gids = fetch_season_game_ids(s)
            log.info("rest_travel: %d games in %s", len(gids), s)
            t0 = time.time()
            df = ingest_rest_travel(game_ids=gids, season=s)
            log.info("rest_travel: season %s -> %d rows in %.1fs", s, len(df), time.time() - t0)
        except Exception as exc:  # noqa: BLE001
            log.warning("rest_travel: season %s failed: %s", s, exc)


if __name__ == "__main__":
    gamelog_dir = Path(PROJECT_DIR) / "data" / "nba"
    seasons = seasons_from_gamelogs(str(gamelog_dir))
    log.info("seasons detected from gamelogs: %s", seasons)
    if not seasons:
        log.error("no seasons found — nothing to ingest")
        sys.exit(1)

    build_playtypes(seasons)
    build_rest_travel(seasons)

    for path in ("data/playtypes.parquet", "data/rest_travel.parquet"):
        p = Path(PROJECT_DIR) / path
        log.info("%s: %s (%d bytes)", path,
                 "EXISTS" if p.exists() else "MISSING",
                 p.stat().st_size if p.exists() else 0)
