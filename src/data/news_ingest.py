"""
news_ingest.py — Same-day injury / lineup news ingestion from free public sources.

Sources
-------
1. NBA.com CDN injury JSON   (official, machine-readable, most reliable)
2. ESPN injury API           (site.api.espn.com — same endpoint used by injury_monitor)
3. Reddit r/nba sticky       (daily game thread/injury thread titles via .json API)

Records are normalised to a flat schema and cached at:
    data/cache/news/{date}.json

Cache TTL: 60 minutes per date bucket (re-hits within 1 hour are returned from disk).

Public API
----------
    fetch_all_injury_news(game_date, force)  -> List[dict]
    get_injury_records(game_date)            -> List[dict]   (cached or fresh)
"""

from __future__ import annotations

import json
import logging
import os
import time
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR   = os.path.join(PROJECT_DIR, "data", "cache", "news")
_NBA_CACHE   = os.path.join(PROJECT_DIR, "data", "nba")
_CACHE_TTL   = 3600  # 1 hour

_UA = "NBA-AI-Research/1.0 (contact: neeljshah22@gmail.com)"
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/html;q=0.9",
}

_THROTTLE = 1.5  # seconds between requests to the same source

# Canonical status values
VALID_STATUSES = {"OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE", "ACTIVE"}

# NBA CDN — same feed used by src/ingest/injury_report.py
_NBA_CDN_URL = "https://cdn.nba.com/static/json/liveData/injuryReport/injuryreport.json"
# ESPN injury API
_ESPN_URL    = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
# Reddit r/nba JSON endpoint
_REDDIT_URL  = "https://www.reddit.com/r/nba/hot.json?limit=25"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _norm_name(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _norm_status(raw: str) -> str:
    mapping = {
        "out":          "OUT",
        "doubtful":     "DOUBTFUL",
        "questionable": "QUESTIONABLE",
        "probable":     "PROBABLE",
        "available":    "ACTIVE",
        "active":       "ACTIVE",
        "healthy":      "ACTIVE",
        "day-to-day":   "QUESTIONABLE",
        "dtd":          "QUESTIONABLE",
    }
    key = raw.lower().strip()
    for k, v in mapping.items():
        if k in key:
            return v
    return "ACTIVE"


def _cache_path(game_date: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{game_date}.json")


def _cache_is_fresh(game_date: str) -> bool:
    path = _cache_path(game_date)
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < _CACHE_TTL


def _load_cache(game_date: str) -> List[dict]:
    path = _cache_path(game_date)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("[news_ingest] cache load failed: %s", exc)
        return []


def _save_cache(game_date: str, records: List[dict]) -> None:
    try:
        with open(_cache_path(game_date), "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        log.warning("[news_ingest] cache save failed: %s", exc)


def _get(url: str, timeout: int = 12, accept_json: bool = True) -> Optional[requests.Response]:
    headers = dict(_HEADERS)
    if accept_json:
        headers["Accept"] = "application/json"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as exc:
        log.warning("[news_ingest] GET %s failed: %s", url, exc)
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Player name → NBA player_id resolver
# ──────────────────────────────────────────────────────────────────────────────

_id_lookup: Optional[dict] = None  # lazy-loaded


def _build_id_lookup() -> dict:
    """Build {norm_name: player_id} from player_avgs cache or nba_api."""
    for season in ("2024-25", "2025-26", "2023-24"):
        path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                avgs = json.load(f)
            result = {
                _norm_name(name): int(info["player_id"])
                for name, info in avgs.items()
                if isinstance(info, dict) and "player_id" in info
            }
            if result:
                log.debug("[news_ingest] ID lookup built from %s (%d players)", path, len(result))
                return result
        except Exception as exc:
            log.debug("[news_ingest] avgs parse error: %s", exc)

    # Fallback: nba_api static players list
    try:
        from nba_api.stats.static import players as nba_players
        result = {}
        for p in nba_players.get_players():
            result[_norm_name(p["full_name"])] = int(p["id"])
        log.debug("[news_ingest] ID lookup built from nba_api static (%d players)", len(result))
        return result
    except Exception as exc:
        log.warning("[news_ingest] nba_api player lookup failed: %s", exc)
    return {}


def resolve_player_id(player_name: str) -> Optional[int]:
    global _id_lookup
    if _id_lookup is None:
        _id_lookup = _build_id_lookup()
    return _id_lookup.get(_norm_name(player_name))


# ──────────────────────────────────────────────────────────────────────────────
# Source 1: NBA CDN official injury report
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_nba_cdn(game_date: str) -> List[dict]:
    resp = _get(_NBA_CDN_URL)
    if resp is None:
        return []
    time.sleep(_THROTTLE)
    try:
        raw = resp.json()
    except Exception as exc:
        log.warning("[news_ingest] NBA CDN JSON parse error: %s", exc)
        return []

    records: List[dict] = []
    reported_at = datetime.now(timezone.utc).isoformat()
    report_date = str(raw.get("injuryDate", game_date))[:10]

    for team_entry in raw.get("injuryReport", []):
        team = team_entry.get("teamAbbreviation", "")
        for player in team_entry.get("injuredPlayers", []):
            name   = player.get("playerName", "")
            status = _norm_status(player.get("personStatus", ""))
            records.append({
                "player_id":   player.get("playerId") or resolve_player_id(name),
                "player_name": name,
                "team":        team,
                "status":      status,
                "reason":      player.get("injuryNote", ""),
                "source":      "nba_cdn",
                "reported_at": reported_at,
                "game_date":   report_date,
            })

    log.info("[news_ingest] NBA CDN: %d records", len(records))
    return records


# ──────────────────────────────────────────────────────────────────────────────
# Source 2: ESPN injury API
# ──────────────────────────────────────────────────────────────────────────────

# ESPN team ID → 3-letter abbreviation (static mapping)
_ESPN_TEAM_MAP: dict[str, str] = {
    "1":  "ATL", "2":  "BOS", "3":  "NOP", "4":  "CHI", "5":  "CLE",
    "6":  "DAL", "7":  "DEN", "8":  "DET", "9":  "GSW", "10": "HOU",
    "11": "IND", "12": "LAC", "13": "LAL", "14": "MEM", "15": "MIA",
    "16": "MIL", "17": "MIN", "18": "BKN", "19": "NYK", "20": "ORL",
    "21": "PHI", "22": "PHX", "23": "POR", "24": "SAC", "25": "SAS",
    "26": "OKC", "27": "UTA", "28": "WAS", "29": "TOR", "30": "OKC",
    "41": "CHA",
}


def _espn_abbrev(team_id: str, display_name: str) -> str:
    if team_id in _ESPN_TEAM_MAP:
        return _ESPN_TEAM_MAP[team_id]
    words = display_name.split()
    return words[-1][:3].upper() if words else ""


def _fetch_espn(game_date: str) -> List[dict]:
    resp = _get(_ESPN_URL)
    if resp is None:
        return []
    time.sleep(_THROTTLE)
    try:
        data = resp.json()
    except Exception as exc:
        log.warning("[news_ingest] ESPN JSON parse error: %s", exc)
        return []

    records: List[dict] = []
    reported_at = datetime.now(timezone.utc).isoformat()

    for team_entry in data.get("injuries", []):
        team_id   = str(team_entry.get("id", ""))
        team_name = team_entry.get("displayName", "")
        team_abbr = _espn_abbrev(team_id, team_name)

        for player_entry in team_entry.get("injuries", []):
            athlete = player_entry.get("athlete", {})
            name    = athlete.get("displayName", "") or athlete.get("fullName", "")
            if not name:
                continue
            status = _norm_status(player_entry.get("status", ""))
            records.append({
                "player_id":   resolve_player_id(name),
                "player_name": name,
                "team":        team_abbr,
                "status":      status,
                "reason":      player_entry.get("shortComment", ""),
                "source":      "espn",
                "reported_at": reported_at,
                "game_date":   game_date,
            })

    log.info("[news_ingest] ESPN: %d records", len(records))
    return records


# ──────────────────────────────────────────────────────────────────────────────
# Source 3: Reddit r/nba hot posts (sticky threads, injury mentions)
# ──────────────────────────────────────────────────────────────────────────────

_INJURY_KEYWORDS = {"injury", "injured", "out", "doubtful", "questionable",
                    "dnp", "ruled out", "knee", "ankle", "hamstring", "back",
                    "shoulder", "wrist", "day-to-day", "dtd", "scratch"}


def _parse_reddit_status(title: str) -> str:
    title_lower = title.lower()
    if "ruled out" in title_lower or " out " in title_lower or title_lower.endswith(" out"):
        return "OUT"
    if "doubtful" in title_lower:
        return "DOUBTFUL"
    if "questionable" in title_lower or "day-to-day" in title_lower or "dtd" in title_lower:
        return "QUESTIONABLE"
    if "probable" in title_lower:
        return "PROBABLE"
    return "QUESTIONABLE"  # generic injury mention — treat as questionable


def _fetch_reddit(game_date: str) -> List[dict]:
    resp = _get(_REDDIT_URL)
    if resp is None:
        return []
    time.sleep(_THROTTLE)
    try:
        data = resp.json()
    except Exception as exc:
        log.warning("[news_ingest] Reddit JSON parse error: %s", exc)
        return []

    records: List[dict] = []
    reported_at = datetime.now(timezone.utc).isoformat()

    posts = data.get("data", {}).get("children", [])
    for post in posts:
        post_data = post.get("data", {})
        title     = post_data.get("title", "")
        flair     = (post_data.get("link_flair_text") or "").lower()

        # Only look at posts with injury-related flairs or keywords
        title_lower = title.lower()
        has_injury_word = any(kw in title_lower for kw in _INJURY_KEYWORDS)
        if not has_injury_word:
            continue

        # Try to extract a player name (first two consecutive capitalized words)
        import re
        name_match = re.search(r"\b([A-Z][a-z']+\s+[A-Z][a-z']+)\b", title)
        if not name_match:
            continue

        player_name = name_match.group(1)
        status      = _parse_reddit_status(title)

        records.append({
            "player_id":   resolve_player_id(player_name),
            "player_name": player_name,
            "team":        "",  # Reddit posts rarely have reliable team abbrev
            "status":      status,
            "reason":      title[:200],
            "source":      "reddit_nba",
            "reported_at": reported_at,
            "game_date":   game_date,
        })

    log.info("[news_ingest] Reddit r/nba: %d relevant posts -> %d records",
             len(posts), len(records))
    return records


# ──────────────────────────────────────────────────────────────────────────────
# Main public API
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all_injury_news(
    game_date: Optional[str] = None,
    force: bool = False,
) -> List[dict]:
    """
    Fetch injury news from all sources, merge, deduplicate, and cache.

    Args:
        game_date: ISO date string (YYYY-MM-DD).  Defaults to today.
        force:     If True, bypass the 1-hour cache and re-fetch all sources.

    Returns:
        List of normalised injury records:
        {
            "player_id":   int | None,
            "player_name": str,
            "team":        str,
            "status":      "OUT|DOUBTFUL|QUESTIONABLE|PROBABLE|ACTIVE",
            "reason":      str,
            "source":      str,
            "reported_at": str (ISO-8601),
            "game_date":   str (YYYY-MM-DD),
        }
    """
    if game_date is None:
        game_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not force and _cache_is_fresh(game_date):
        log.info("[news_ingest] Returning cached records for %s", game_date)
        return _load_cache(game_date)

    all_records: List[dict] = []
    source_counts: dict[str, int] = {}

    # Source 1: NBA CDN (most authoritative)
    try:
        nba_records = _fetch_nba_cdn(game_date)
        all_records.extend(nba_records)
        source_counts["nba_cdn"] = len(nba_records)
    except Exception as exc:
        log.warning("[news_ingest] NBA CDN source failed: %s", exc)
        source_counts["nba_cdn"] = 0

    # Source 2: ESPN
    try:
        espn_records = _fetch_espn(game_date)
        all_records.extend(espn_records)
        source_counts["espn"] = len(espn_records)
    except Exception as exc:
        log.warning("[news_ingest] ESPN source failed: %s", exc)
        source_counts["espn"] = 0

    # Source 3: Reddit r/nba
    try:
        reddit_records = _fetch_reddit(game_date)
        all_records.extend(reddit_records)
        source_counts["reddit_nba"] = len(reddit_records)
    except Exception as exc:
        log.warning("[news_ingest] Reddit source failed: %s", exc)
        source_counts["reddit_nba"] = 0

    # Deduplicate by (player_name, source) — keep first (highest-priority source first)
    seen: set[tuple] = set()
    deduped: List[dict] = []
    for rec in all_records:
        key = (_norm_name(rec.get("player_name", "")), rec.get("source", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(rec)

    _save_cache(game_date, deduped)
    log.info("[news_ingest] Total: %d records (sources: %s)", len(deduped), source_counts)
    return deduped


def get_injury_records(game_date: Optional[str] = None) -> List[dict]:
    """
    Return cached injury records for a date, fetching if not yet cached.

    Args:
        game_date: ISO date string.  Defaults to today.

    Returns:
        List of injury record dicts.
    """
    if game_date is None:
        game_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _cache_is_fresh(game_date):
        return _load_cache(game_date)
    return fetch_all_injury_news(game_date)


def get_team_injury_records(team: str, game_date: Optional[str] = None) -> List[dict]:
    """Return injury records for a specific team abbreviation."""
    records = get_injury_records(game_date)
    team_upper = team.upper()
    return [r for r in records if r.get("team", "").upper() == team_upper]
