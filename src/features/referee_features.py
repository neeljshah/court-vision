"""
referee_features.py — Per-referee crew tendency features.

Referee crews materially shift game pace, FT rate, total points, and
home-court edge.  This module builds historical profiles from cached
boxscores + NBA API and exposes crew-aggregate features at prediction time.

Public API
----------
    get_referees(game_id)              -> List[Dict]
    build_ref_history(seasons)         -> pd.DataFrame
    get_ref_crew_features(game_id, game_date) -> dict
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE      = os.path.join(PROJECT_DIR, "data", "nba")
_OFFICIALS_DIR  = os.path.join(PROJECT_DIR, "data", "cache", "officials")
_MODEL_DIR      = os.path.join(PROJECT_DIR, "data", "models")
_HISTORY_PATH   = os.path.join(_MODEL_DIR, "ref_history.json")

_API_THROTTLE   = 0.65   # seconds between NBA API calls

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# NBA API session (mirrors nba_stats.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

def _configure_session() -> None:
    """Inject retry-capable requests.Session into nba_api HTTP layer."""
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    try:
        from nba_api.stats.library.http import NBAStatsHTTP
    except ImportError:
        return

    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":         "application/json, text/plain, */*",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token":  "true",
        "Referer":        "https://www.nba.com/",
    })
    orig_get = session.get

    def _get_timeout(url, **kwargs):
        kwargs.setdefault("timeout", 30)
        return orig_get(url, **kwargs)

    session.get = _get_timeout  # type: ignore[method-assign]
    NBAStatsHTTP.set_session(session)


try:
    _configure_session()
except Exception:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# get_referees
# ─────────────────────────────────────────────────────────────────────────────

def get_referees(game_id: str) -> List[Dict]:
    """
    Return the officiating crew for *game_id*.

    Resolution order:
      1. data/cache/officials/{game_id}.json   — per-game cache
      2. data/nba/boxscore_{game_id}.json      — local enriched boxscore
         (only if it contains an 'officials' key)
      3. NBA API BoxScoreSummaryV2              — live fetch + cache

    Returns:
        List of dicts with keys: id (int), name (str), jersey_num (str).
        Empty list if referees cannot be determined.
    """
    os.makedirs(_OFFICIALS_DIR, exist_ok=True)
    cache_path = os.path.join(_OFFICIALS_DIR, f"{game_id}.json")

    # 1. Per-game disk cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass

    # 2. Embedded in local boxscore
    bs_path = os.path.join(_NBA_CACHE, f"boxscore_{game_id}.json")
    if os.path.exists(bs_path):
        try:
            with open(bs_path, encoding="utf-8") as fh:
                bs = json.load(fh)
            if "officials" in bs and bs["officials"]:
                refs = bs["officials"]
                with open(cache_path, "w", encoding="utf-8") as fh:
                    json.dump(refs, fh)
                return refs
        except Exception:
            pass

    # 3. NBA API — try V3 first (preferred for games >= 2025-04-10), V2 fallback
    officials: List[Dict] = []
    try:
        from nba_api.stats.endpoints import boxscoresummaryv3
        time.sleep(_API_THROTTLE)
        bs3 = boxscoresummaryv3.BoxScoreSummaryV3(game_id=str(game_id))
        for df in bs3.get_data_frames():
            if df is None or df.empty:
                continue
            # V3 officials df: gameId, personId, name, nameI, firstName, familyName, jerseyNum
            if "personId" in df.columns and "firstName" in df.columns:
                for _, row in df.iterrows():
                    first = str(row.get("firstName", "")).strip()
                    last  = str(row.get("familyName", "")).strip()
                    officials.append({
                        "id":         int(row.get("personId", 0)),
                        "name":       f"{first} {last}".strip(),
                        "jersey_num": str(row.get("jerseyNum", "")),
                    })
                break
    except Exception as exc:
        log.debug("get_referees V3 error for %s: %s", game_id, exc)

    if not officials:
        try:
            import warnings
            from nba_api.stats.endpoints import boxscoresummaryv2
            time.sleep(_API_THROTTLE)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                bs2 = boxscoresummaryv2.BoxScoreSummaryV2(game_id=str(game_id))
            for df in bs2.get_data_frames():
                if df is None or df.empty:
                    continue
                if "OFFICIAL_ID" in df.columns:
                    for _, row in df.iterrows():
                        first = str(row.get("FIRST_NAME", "")).strip()
                        last  = str(row.get("LAST_NAME", "")).strip()
                        officials.append({
                            "id":         int(row.get("OFFICIAL_ID", 0)),
                            "name":       f"{first} {last}".strip(),
                            "jersey_num": str(row.get("JERSEY_NUM", "")),
                        })
                    break
        except Exception as exc:
            log.debug("get_referees V2 error for %s: %s", game_id, exc)

    if officials:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(officials, fh)
        return officials

    return []


# ─────────────────────────────────────────────────────────────────────────────
# build_ref_history
# ─────────────────────────────────────────────────────────────────────────────

def _extract_game_stats(bs_path: str) -> Optional[Dict]:
    """
    Extract scoring + foul stats from a cached boxscore file.

    Returns dict with game_id, total_pts, home_pts, away_pts,
    home_fta, away_fta, home_pf, away_pf, home_team, away_team,
    home_win (int 0/1).  Returns None on parse failure.
    """
    try:
        with open(bs_path, encoding="utf-8") as fh:
            d = json.load(fh)

        game_id    = str(d.get("game_id", ""))
        home_score = int(d.get("home_score", 0) or 0)
        away_score = int(d.get("away_score", 0) or 0)
        home_team  = str(d.get("home_team", ""))
        away_team  = str(d.get("away_team", ""))

        if not game_id or (home_score == 0 and away_score == 0):
            return None

        players = d.get("players", [])
        home_fta = away_fta = home_pf = away_pf = 0
        home_min = away_min = 0.0
        for p in players:
            abbr = p.get("team_abbreviation", "")
            if abbr == home_team:
                home_fta += int(p.get("fta", 0) or 0)
                home_pf  += int(p.get("pf", 0) or 0)
                home_min += float(p.get("min", 0) or 0)
            elif abbr == away_team:
                away_fta += int(p.get("fta", 0) or 0)
                away_pf  += int(p.get("pf", 0) or 0)
                away_min += float(p.get("min", 0) or 0)

        # Pace proxy: total player-minutes / 48 (normalise to possessions proxy)
        # Using total team minutes ÷ 5 players = game minutes per team
        total_min = (home_min + away_min) / 2.0
        pace_proxy = total_min / 5.0 if total_min > 0 else 0.0

        return {
            "game_id":    game_id,
            "home_team":  home_team,
            "away_team":  away_team,
            "home_pts":   home_score,
            "away_pts":   away_score,
            "total_pts":  home_score + away_score,
            "home_fta":   home_fta,
            "away_fta":   away_fta,
            "avg_fta":    (home_fta + away_fta) / 2.0,
            "home_pf":    home_pf,
            "away_pf":    away_pf,
            "avg_pf":     (home_pf + away_pf) / 2.0,
            "pace_proxy": pace_proxy,
            "home_win":   1 if home_score > away_score else 0,
        }
    except Exception:
        return None


def build_ref_history(seasons: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Walk all cached boxscores, fetch officials for each game via
    get_referees(), and build per-referee aggregate statistics.

    Saves result to data/models/ref_history.json.

    Args:
        seasons: Unused filter (season info not reliably in local cache).
                 Kept for API compatibility — walks all cached games.

    Returns:
        DataFrame with one row per referee, columns:
            ref_id, ref_name, games_officiated, avg_game_total,
            avg_pace, avg_fta_per_team, avg_pf_per_team, home_win_pct
    """
    os.makedirs(_MODEL_DIR, exist_ok=True)

    boxscore_files = sorted(glob.glob(os.path.join(_NBA_CACHE, "boxscore_*.json")))
    log.info("build_ref_history: scanning %d boxscore files", len(boxscore_files))

    # game_id -> stats dict
    game_stats: Dict[str, Dict] = {}
    for fpath in boxscore_files:
        stats = _extract_game_stats(fpath)
        if stats:
            game_stats[stats["game_id"]] = stats

    log.info("build_ref_history: %d games with valid stats", len(game_stats))

    # Per-referee accumulators: ref_id -> list of game stat dicts
    ref_games: Dict[int, List[Dict]] = {}
    ref_names: Dict[int, str]        = {}

    processed = 0
    skipped   = 0
    for game_id, stats in game_stats.items():
        refs = get_referees(game_id)
        if not refs:
            skipped += 1
            continue
        for ref in refs:
            rid  = int(ref.get("id", 0))
            name = str(ref.get("name", "")).strip()
            if rid == 0 and not name:
                continue
            if rid not in ref_games:
                ref_games[rid]  = []
                ref_names[rid]  = name
            ref_games[rid].append(stats)
        processed += 1

    log.info(
        "build_ref_history: %d games processed, %d skipped (no officials found)",
        processed, skipped,
    )

    if not ref_games:
        log.warning("build_ref_history: no referee data found — returning empty DataFrame")
        empty = pd.DataFrame(columns=[
            "ref_id", "ref_name", "games_officiated", "avg_game_total",
            "avg_pace", "avg_fta_per_team", "avg_pf_per_team", "home_win_pct",
        ])
        empty.to_json(_HISTORY_PATH, orient="records", indent=2)
        return empty

    rows = []
    for rid, g_list in ref_games.items():
        n = len(g_list)
        rows.append({
            "ref_id":            rid,
            "ref_name":          ref_names[rid],
            "games_officiated":  n,
            "avg_game_total":    sum(g["total_pts"] for g in g_list) / n,
            "avg_pace":          sum(g["pace_proxy"] for g in g_list) / n,
            "avg_fta_per_team":  sum(g["avg_fta"]   for g in g_list) / n,
            "avg_pf_per_team":   sum(g["avg_pf"]    for g in g_list) / n,
            "home_win_pct":      sum(g["home_win"]   for g in g_list) / n,
        })

    df = pd.DataFrame(rows).sort_values("games_officiated", ascending=False)
    df.to_json(_HISTORY_PATH, orient="records", indent=2)
    log.info(
        "build_ref_history: saved %d referees across %d games → %s",
        len(df), processed, _HISTORY_PATH,
    )
    return df


# ─────────────────────────────────────────────────────────────────────────────
# get_ref_crew_features
# ─────────────────────────────────────────────────────────────────────────────

_HISTORY_CACHE: Optional[pd.DataFrame] = None


def _load_history() -> pd.DataFrame:
    """Load ref history from disk; rebuild if absent."""
    global _HISTORY_CACHE
    if _HISTORY_CACHE is not None:
        return _HISTORY_CACHE
    if os.path.exists(_HISTORY_PATH):
        try:
            _HISTORY_CACHE = pd.read_json(_HISTORY_PATH, orient="records")
            return _HISTORY_CACHE
        except Exception:
            pass
    log.info("ref_history.json not found — running build_ref_history()")
    _HISTORY_CACHE = build_ref_history()
    return _HISTORY_CACHE


def _zero_features() -> Dict:
    """Return zero-valued feature dict used when crew is unknown."""
    return {
        "ref_crew_game_total_avg": 0.0,
        "ref_crew_pace_avg":       0.0,
        "ref_crew_fta_avg":        0.0,
        "ref_crew_pf_avg":         0.0,
        "ref_crew_home_win_pct":   0.0,
        "ref_crew_games_avg":      0.0,
        "ref_crew_known":          0,
    }


def get_ref_crew_features(game_id: str, game_date: str = "") -> Dict:
    """
    Compute crew-aggregate referee features for prediction.

    Fetches the assigned crew for *game_id* (from cache or NBA API),
    looks each referee up in the historical profile table, and returns
    the mean of their per-ref aggregates.

    If the crew is unavailable (future game, pre-tip) returns zeros
    with ref_crew_known=0.

    Args:
        game_id:   NBA game ID string (e.g. "0022401234").
        game_date: ISO date string (YYYY-MM-DD); informational only.

    Returns:
        dict with keys:
            ref_crew_game_total_avg  — mean game total for this crew
            ref_crew_pace_avg        — mean pace proxy
            ref_crew_fta_avg         — mean FTA per team
            ref_crew_pf_avg          — mean PF per team
            ref_crew_home_win_pct    — mean home win pct
            ref_crew_games_avg       — mean games officiated (experience proxy)
            ref_crew_known           — 1 if crew identified, 0 otherwise
    """
    refs = get_referees(game_id)
    if not refs:
        log.debug("get_ref_crew_features: no crew found for %s", game_id)
        return _zero_features()

    history = _load_history()
    if history.empty:
        log.debug("get_ref_crew_features: history empty, returning zeros")
        return _zero_features()

    # Index by ref_id for fast lookup
    hist_by_id: Dict[int, Dict] = {}
    for _, row in history.iterrows():
        hist_by_id[int(row["ref_id"])] = row.to_dict()

    matched_rows = []
    for ref in refs:
        rid = int(ref.get("id", 0))
        if rid in hist_by_id:
            matched_rows.append(hist_by_id[rid])
        else:
            # Unknown ref — use league-average row if available
            log.debug("get_ref_crew_features: ref id=%d (%s) not in history",
                      rid, ref.get("name", ""))

    if not matched_rows:
        return _zero_features()

    n = len(matched_rows)
    return {
        "ref_crew_game_total_avg": sum(r["avg_game_total"]   for r in matched_rows) / n,
        "ref_crew_pace_avg":       sum(r["avg_pace"]         for r in matched_rows) / n,
        "ref_crew_fta_avg":        sum(r["avg_fta_per_team"] for r in matched_rows) / n,
        "ref_crew_pf_avg":         sum(r["avg_pf_per_team"]  for r in matched_rows) / n,
        "ref_crew_home_win_pct":   sum(r["home_win_pct"]     for r in matched_rows) / n,
        "ref_crew_games_avg":      sum(r["games_officiated"] for r in matched_rows) / n,
        "ref_crew_known":          1,
    }
