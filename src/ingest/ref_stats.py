"""
Ingest: referee foul-rate stats from BoxScoreOfficials.

Fetches official crew for each game, computes:
  - total_fouls_called, home_foul_rate, away_foul_rate, foul_diff
  - crew_avg_fouls (season average across all games for this crew)

Caches to data/refs.parquet. Safe to call repeatedly — skips cached game_ids.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)

_CACHE_PATH = Path("data/refs.parquet")
_SLEEP_S    = 0.6   # NBA API rate limit


def _fetch_officials(game_id: str) -> Optional[dict]:
    """Call BoxScoreOfficialsSummary for one game. Returns raw dict or None."""
    try:
        from nba_api.stats.endpoints import BoxScoreOfficialsSummary  # type: ignore
        resp = BoxScoreOfficialsSummary(game_id=game_id)
        d = resp.get_dict()
        return d
    except Exception as exc:
        log.warning("BoxScoreOfficials fetch failed for %s: %s", game_id, exc)
        return None


def _parse_officials(raw: dict) -> List[dict]:
    """Parse official rows from API response dict."""
    officials = []
    try:
        for rs in raw.get("resultSets", []):
            if rs["name"] == "Officials":
                hdrs = rs["headers"]
                idx  = {h: i for i, h in enumerate(hdrs)}
                for row in rs["rowSet"]:
                    officials.append({
                        "official_id":   int(row[idx["OFFICIAL_ID"]]),
                        "official_name": str(row[idx["OFFICIAL_FIRST_NAME"]])
                                        + " " + str(row[idx["OFFICIAL_LAST_NAME"]]),
                        "jersey_number": row[idx.get("JERSEY_NUM", -1)],
                    })
    except Exception as exc:
        log.debug("_parse_officials error: %s", exc)
    return officials


def _fetch_boxscore_foul_counts(game_id: str) -> Optional[Dict[str, float]]:
    """Get per-team foul totals from BoxScoreTraditionalV2."""
    try:
        from nba_api.stats.endpoints import BoxScoreTraditionalV2  # type: ignore
        resp = BoxScoreTraditionalV2(game_id=game_id)
        d    = resp.get_dict()
        for rs in d.get("resultSets", []):
            if rs["name"] == "TeamStats":
                hdrs = rs["headers"]
                idx  = {h: i for i, h in enumerate(hdrs)}
                rows = rs["rowSet"]
                if len(rows) < 2:
                    return None
                # rows[0] = away, rows[1] = home (NBA API convention)
                return {
                    "away_fouls": float(rows[0][idx["PF"]]),
                    "home_fouls": float(rows[1][idx["PF"]]),
                }
    except Exception as exc:
        log.warning("BoxScoreTraditionalV2 foul fetch failed %s: %s", game_id, exc)
    return None


def ingest_ref_stats(
    game_ids: List[str],
    cache_path: Path = _CACHE_PATH,
    sleep_s: float = _SLEEP_S,
) -> pd.DataFrame:
    """
    Fetch referee stats for a list of game IDs.

    Args:
        game_ids:   NBA game ID strings.
        cache_path: Parquet file to read/append.
        sleep_s:    Seconds to sleep between API calls.

    Returns:
        DataFrame with columns: game_id, officials (list), away_fouls,
        home_fouls, total_fouls, foul_diff.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing cache
    cached_ids: set = set()
    rows: List[dict] = []
    if cache_path.exists():
        try:
            cached_df  = pd.read_parquet(cache_path)
            cached_ids = set(cached_df["game_id"].astype(str))
            rows       = cached_df.to_dict("records")
            log.info("ref_stats: %d games already cached", len(cached_ids))
        except Exception as exc:
            log.warning("ref_stats cache read failed: %s", exc)

    new_ids = [g for g in game_ids if str(g) not in cached_ids]
    log.info("ref_stats: fetching %d new games", len(new_ids))

    for game_id in new_ids:
        row: dict = {"game_id": str(game_id)}

        raw_officials = _fetch_officials(game_id)
        if raw_officials:
            officials = _parse_officials(raw_officials)
            row["official_ids"]   = [o["official_id"]   for o in officials]
            row["official_names"] = [o["official_name"] for o in officials]
        else:
            row["official_ids"]   = []
            row["official_names"] = []

        time.sleep(sleep_s)

        fouls = _fetch_boxscore_foul_counts(game_id)
        if fouls:
            row["away_fouls"]   = fouls["away_fouls"]
            row["home_fouls"]   = fouls["home_fouls"]
            row["total_fouls"]  = fouls["away_fouls"] + fouls["home_fouls"]
            row["foul_diff"]    = fouls["home_fouls"] - fouls["away_fouls"]
        else:
            row.update({"away_fouls": None, "home_fouls": None,
                        "total_fouls": None, "foul_diff": None})

        rows.append(row)
        time.sleep(sleep_s)

    df = pd.DataFrame(rows)

    # Compute crew_avg_fouls across games
    if "total_fouls" in df.columns and df["total_fouls"].notna().any():
        crew_rows = []
        for _, r in df.iterrows():
            for oid in (r.get("official_ids") or []):
                crew_rows.append({"official_id": oid, "total_fouls": r["total_fouls"]})
        if crew_rows:
            crew_df = pd.DataFrame(crew_rows)
            crew_avg = crew_df.groupby("official_id")["total_fouls"].mean().to_dict()
            df["crew_avg_fouls"] = df["official_ids"].apply(
                lambda ids: (
                    sum(crew_avg.get(i, float("nan")) for i in (ids or []))
                    / len(ids) if ids else None
                )
            )

    # Persist
    try:
        df.to_parquet(cache_path, index=False)
        log.info("ref_stats: saved %d rows to %s", len(df), cache_path)
    except Exception as exc:
        log.error("ref_stats cache write failed: %s", exc)

    return df
