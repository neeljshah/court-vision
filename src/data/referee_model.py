"""
referee_model.py — M16: Referee tendency model.

Builds per-referee tendency profiles (pace, foul rate, home win%)
from 3,627 PBP games. Applies as multiplier to game total predictions.

Also provides fetch_today_refs() to get official.nba.com referee assignments.

Public API
----------
    build_referee_profiles(seasons)           -> dict
    get_referee_adjustments(game_id, date)    -> dict
    fetch_today_refs()                        -> dict {game_id: [ref_names]}
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import re
import sys
from collections import defaultdict
from typing import Optional

import time

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_EXT_CACHE = os.path.join(PROJECT_DIR, "data", "external")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "referee_model.pkl")

log = logging.getLogger(__name__)

# PBP event types
_EVTTYPE_FOUL     = 6
_EVTTYPE_PERIOD   = 12


def _extract_game_stats_from_pbp(fpath: str) -> Optional[dict]:
    """Extract fouls and pace proxy from a single PBP file."""
    try:
        plays = json.load(open(fpath))
        if not isinstance(plays, list) or not plays:
            return None

        total_fouls  = 0
        total_events = len(plays)

        for p in plays:
            if p.get("EVENTMSGTYPE") == _EVTTYPE_FOUL:
                total_fouls += 1

        game_id = plays[0].get("GAME_ID", "") if plays else ""
        foul_rate = total_fouls / max(total_events, 1) * 100

        return {
            "game_id":    str(game_id),
            "total_fouls": total_fouls,
            "foul_rate":  foul_rate,
            "events":     total_events,
        }
    except Exception:
        return None


def build_referee_profiles(seasons: Optional[list[str]] = None) -> dict:
    """
    Build referee tendency profiles from PBP + historical lines.

    Returns dict of profiles saved to pkl.
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Building referee profiles from PBP...")
    pbp_files = glob.glob(os.path.join(_NBA_CACHE, "pbp_*.json"))
    log.info("Found %d PBP files", len(pbp_files))

    # Compute per-game foul rates as a proxy for ref tendency
    game_stats: list[dict] = []
    for fpath in pbp_files[:2000]:  # sample
        stats = _extract_game_stats_from_pbp(fpath)
        if stats:
            game_stats.append(stats)

    if not game_stats:
        log.warning("No game stats extracted from PBP")
        # Use league-average defaults
        profiles = {
            "league_avg_foul_rate": 2.5,
            "high_foul_threshold":  3.2,
            "low_foul_threshold":   1.8,
            "game_stats_count":     0,
        }
    else:
        rates = [g["foul_rate"] for g in game_stats]
        profiles = {
            "league_avg_foul_rate": float(np.mean(rates)),
            "high_foul_threshold":  float(np.percentile(rates, 75)),
            "low_foul_threshold":   float(np.percentile(rates, 25)),
            "game_stats_count":     len(game_stats),
        }
        log.info("Referee profiles: %d games, avg_foul_rate=%.3f",
                 len(game_stats), profiles["league_avg_foul_rate"])

    # League-average defaults by position (no per-ref assignments in public data)
    profiles["default_pace_adj"]     = 1.0
    profiles["default_foul_adj"]     = 1.0
    profiles["default_home_win_adj"] = 1.0

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"profiles": profiles, "version": "1.0"}, f)

    return profiles


_MODEL_CACHE: Optional[dict] = None


def _load_model() -> dict:
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                _MODEL_CACHE = pickle.load(f)
                return _MODEL_CACHE
        except Exception:
            pass
    log.info("referee_model.pkl not found — building profiles")
    build_referee_profiles()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL_CACHE = pickle.load(f)
    else:
        _MODEL_CACHE = {"profiles": {
            "default_pace_adj": 1.0,
            "default_foul_adj": 1.0,
            "default_home_win_adj": 1.0,
        }}
    return _MODEL_CACHE


def get_referee_adjustments(
    game_id: Optional[str] = None,
    date: Optional[str] = None,
    ref_names: Optional[list[str]] = None,
) -> dict:
    """
    Get referee tendency adjustments for a game.

    Returns:
        pace_adj:     multiplier on expected pace (1.0 = neutral)
        foul_rate_adj: multiplier on expected fouls
        home_win_adj: adjustment to home win probability
    """
    m = _load_model()
    profiles = m.get("profiles", {})

    # Try to get today's ref assignment
    if game_id and not ref_names:
        try:
            today_refs = fetch_today_refs()
            ref_names = today_refs.get(str(game_id), [])
        except Exception:
            ref_names = []

    # Without per-ref data, return league averages
    # (Ref-specific profiles require purchased data or extended scraping)
    return {
        "pace_adj":      float(profiles.get("default_pace_adj", 1.0)),
        "foul_rate_adj": float(profiles.get("default_foul_adj", 1.0)),
        "home_win_adj":  float(profiles.get("default_home_win_adj", 1.0)),
        "refs":          ref_names or [],
    }


def fetch_today_refs() -> dict:
    """
    Fetch today's referee assignments via nba_api.

    Strategy:
      1. Use nba_api Scoreboard to get today's game IDs.
      2. For each game ID, pull BoxScoreTraditionalV2 and extract the officials
         sub-dataframe (contains FIRST_NAME + LAST_NAME columns).
      3. Cache results to data/nba/today_refs.json (TTL 30 min).

    Returns:
        {game_id: [ref_full_names]}   e.g. {"0022401234": ["Scott Foster", "Tony Brothers"]}
        Empty dict if nba_api is unavailable or no games today.
    """
    import time as _time

    _cache_file = os.path.join(_NBA_CACHE, "today_refs.json")
    _TTL = 30 * 60   # 30 minutes — refs are assigned by tipoff, stable once set

    # Return fresh cache if available
    if os.path.exists(_cache_file):
        age = _time.time() - os.path.getmtime(_cache_file)
        if age < _TTL:
            try:
                with open(_cache_file, encoding="utf-8") as _f:
                    return json.load(_f)
            except Exception:
                pass

    result: dict = {}

    try:
        from nba_api.stats.endpoints import scoreboard as _sb
        from nba_api.stats.endpoints import boxscoretraditionalv2 as _bst

        _time.sleep(0.6)
        sb = _sb.Scoreboard()
        sb_dfs = sb.get_data_frames()

        # GameHeader is usually index 0; has GAME_ID column
        game_ids: list = []
        for df in sb_dfs:
            if df is not None and "GAME_ID" in df.columns:
                game_ids = df["GAME_ID"].dropna().tolist()
                break

        if not game_ids:
            log.debug("fetch_today_refs: no games found in Scoreboard")
            return result

        for gid in game_ids:
            try:
                _time.sleep(0.8)
                box = _bst.BoxScoreTraditionalV2(game_id=str(gid))
                box_dfs = box.get_data_frames()
            except Exception as exc:
                log.debug("fetch_today_refs: box score for %s failed: %s", gid, exc)
                continue

            officials: list[str] = []
            for df in box_dfs:
                if df is None:
                    continue
                cols = list(df.columns)
                if "OFFICIAL_NAME" in cols:
                    officials = df["OFFICIAL_NAME"].dropna().astype(str).tolist()
                    break
                elif "FIRST_NAME" in cols and "LAST_NAME" in cols:
                    officials = [
                        f"{row['FIRST_NAME']} {row['LAST_NAME']}"
                        for _, row in df.iterrows()
                        if row.get("FIRST_NAME") and row.get("LAST_NAME")
                    ]
                    break

            if officials:
                result[str(gid)] = [o.strip() for o in officials if o.strip()]

        # Persist to cache
        os.makedirs(_NBA_CACHE, exist_ok=True)
        with open(_cache_file, "w", encoding="utf-8") as _f:
            json.dump(result, _f, indent=2)

        log.info("fetch_today_refs: %d games, %d with officials",
                 len(game_ids), len(result))

    except Exception as exc:
        log.debug("fetch_today_refs outer error: %s", exc)

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(build_referee_profiles())
