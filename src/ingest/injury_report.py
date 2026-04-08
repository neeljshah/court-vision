"""
Ingest: NBA official injury report (pre-game PDF).

Fetches the official NBA injury PDF or JSON from the NBA CDN, parses player
status (Out / Doubtful / Questionable / Available), caches to
data/injury_reports.parquet.

Falls back to data/external/nba_official_injury.json if network is blocked.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

log = logging.getLogger(__name__)

_CACHE_PATH    = Path("data/injury_reports.parquet")
_FALLBACK_JSON = Path("data/external/nba_official_injury.json")
# NBA CDN injury JSON (updated daily)
_NBA_INJURY_URL = "https://cdn.nba.com/static/json/liveData/injuryReport/injuryreport.json"

_STATUS_SEVERITY: dict[str, int] = {
    "out":           4,
    "doubtful":      3,
    "questionable":  2,
    "probable":      1,
    "available":     0,
    "":              0,
}


def _severity(status: str) -> int:
    return _STATUS_SEVERITY.get(status.lower().strip(), 0)


def _fetch_injury_json(url: str) -> Optional[dict]:
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        log.warning("injury_report: CDN fetch failed: %s", exc)
        return None


def _parse_injury_json(raw: dict) -> List[dict]:
    """Parse NBA CDN injury JSON into flat records."""
    records: List[dict] = []
    try:
        report_date = raw.get("injuryDate", date.today().isoformat())
        for team_entry in raw.get("injuryReport", []):
            team_abbrev = team_entry.get("teamAbbreviation", "")
            for player in team_entry.get("injuredPlayers", []):
                status = player.get("personStatus", "")
                records.append({
                    "report_date":   str(report_date)[:10],
                    "player_id":     player.get("playerId"),
                    "player_name":   player.get("playerName", ""),
                    "team_abbrev":   team_abbrev,
                    "status":        status,
                    "severity":      _severity(status),
                    "reason":        player.get("injuryNote", ""),
                    "game_date":     player.get("gameDate", ""),
                })
    except Exception as exc:
        log.warning("injury_report parse failed: %s", exc)
    return records


def _load_fallback() -> List[dict]:
    if not _FALLBACK_JSON.exists():
        return []
    try:
        raw = json.loads(_FALLBACK_JSON.read_text(encoding="utf-8"))
        return _parse_injury_json(raw)
    except Exception as exc:
        log.warning("injury_report fallback parse failed: %s", exc)
        return []


def ingest_injury_report(
    cache_path: Path = _CACHE_PATH,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch and cache today's NBA injury report.

    Returns DataFrame: report_date, player_id, player_name, team_abbrev,
    status, severity (0-4), reason, game_date.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    if not force_refresh and cache_path.exists():
        try:
            cached = pd.read_parquet(cache_path)
            if "report_date" in cached.columns and today in cached["report_date"].values:
                log.info("injury_report: today's report already cached (%d rows)", len(cached))
                return cached
        except Exception as exc:
            log.warning("injury_report cache read failed: %s", exc)

    raw = _fetch_injury_json(_NBA_INJURY_URL)
    records = _parse_injury_json(raw) if raw else _load_fallback()

    if not records:
        log.error("injury_report: no data — returning empty DataFrame")
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Append to existing cache (keep all dates for history)
    if cache_path.exists():
        try:
            existing = pd.read_parquet(cache_path)
            df = pd.concat([existing, df]).drop_duplicates(
                subset=["report_date", "player_id"]
            )
        except Exception:
            pass

    try:
        df.to_parquet(cache_path, index=False)
        log.info("injury_report: saved %d rows to %s", len(df), cache_path)
    except Exception as exc:
        log.error("injury_report cache write failed: %s", exc)

    return df


def get_player_status(
    player_id: int,
    game_date: str,
    cache_path: Path = _CACHE_PATH,
) -> dict:
    """
    Look up injury status for a player on a given game date.

    Returns dict: status, severity, reason.  Defaults to 'available' if not found.
    """
    default = {"status": "available", "severity": 0, "reason": ""}
    if not cache_path.exists():
        return default
    try:
        df = pd.read_parquet(cache_path)
        rows = df[
            (df["player_id"].astype(str) == str(player_id)) &
            (df["game_date"].astype(str) == str(game_date))
        ]
        if rows.empty:
            return default
        row = rows.iloc[0]
        return {
            "status":   row["status"],
            "severity": int(row["severity"]),
            "reason":   row.get("reason", ""),
        }
    except Exception as exc:
        log.warning("get_player_status failed: %s", exc)
        return default
