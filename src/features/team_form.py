"""
team_form.py — Advanced rolling form features for NBA game models.

Extends basic W/L form with quality-of-wins, schedule strength,
clutch record, shooting variance, blowout rate, and starter-minutes load.

Public API
----------
    get_team_form_features(team_abbrev, game_date, season,
                           window)                 -> dict
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCHED_DIR   = os.path.join(_PROJECT_DIR, "data", "nba", "schedule")
_NBA_CACHE   = os.path.join(_PROJECT_DIR, "data", "nba")

# ── Net-rating lookup (cached ELO / team-stats file) ──────────────────────────
_net_ratings: Optional[Dict[str, float]] = None


def _load_net_ratings() -> Dict[str, float]:
    global _net_ratings
    if _net_ratings is not None:
        return _net_ratings
    # Try elo_ratings.json first
    elo_path = os.path.join(_NBA_CACHE, "elo_ratings.json")
    if os.path.exists(elo_path):
        try:
            with open(elo_path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Could be {team: elo_score} or nested
                flat: Dict[str, float] = {}
                for k, v in data.items():
                    if isinstance(v, (int, float)):
                        flat[k] = float(v)
                    elif isinstance(v, dict):
                        flat[k] = float(v.get("rating", 1500))
                _net_ratings = flat
                return _net_ratings
        except Exception:
            pass
    # Fallback: mid-season net ratings (2024-25 estimates)
    _net_ratings = {
        "BOS": 9.2, "OKC": 7.8, "CLE": 7.1, "DEN": 6.5, "NYK": 5.4,
        "MIN": 5.0, "MIL": 4.1, "MIA": 3.8, "IND": 3.5, "PHI": 2.9,
        "LAL": 2.5, "GSW": 2.2, "HOU": 1.8, "SAC": 1.4, "DAL": 1.1,
        "LAC": 0.9, "PHX": 0.7, "NOP": -0.4, "ORL": -0.8, "ATL": -1.1,
        "BKN": -2.3, "CHA": -3.1, "CHI": -3.5, "TOR": -4.0, "POR": -4.8,
        "MEM": -5.2, "SAS": -5.8, "DET": -6.2, "WAS": -7.4, "UTA": -8.1,
    }
    return _net_ratings


def _load_schedule(team_abbrev: str, season: str) -> List[dict]:
    sched_path = os.path.join(_SCHED_DIR, f"schedule_{team_abbrev}_{season}_v2.json")
    if os.path.exists(sched_path):
        try:
            with open(sched_path) as f:
                return json.load(f)
        except Exception:
            pass
    try:
        import sys
        sys.path.insert(0, _PROJECT_DIR)
        from src.data.schedule_context import get_season_schedule  # type: ignore
        return get_season_schedule(team_abbrev, season)
    except Exception as exc:
        log.warning("team_form: schedule fetch failed %s %s: %s", team_abbrev, season, exc)
        return []


def _parse_boxscore(game_id: str) -> Optional[dict]:
    """Load cached boxscore for 3P%, minutes data."""
    path = os.path.join(_NBA_CACHE, f"boxscore_{game_id}.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _get_3p_pct_from_boxscore(game_id: str, team_abbrev: str) -> Optional[float]:
    """Compute team 3P% from boxscore players list."""
    bs = _parse_boxscore(game_id)
    if not bs:
        return None
    # Native boxscore format: {players: [{team_abbreviation, fg3m, fg3a, ...}]}
    players = bs.get("players")
    if isinstance(players, list):
        fg3m_total, fg3a_total = 0, 0
        for row in players:
            if row.get("team_abbreviation") == team_abbrev:
                try:
                    fg3m_total += int(row.get("fg3m") or 0)
                    fg3a_total += int(row.get("fg3a") or 0)
                except (TypeError, ValueError):
                    pass
        if fg3a_total > 0:
            return round(fg3m_total / fg3a_total, 4)
        return None
    # Fallback: try legacy key patterns
    for key in ("teamStats", "TeamStats", "team_stats"):
        ts = bs.get(key)
        if isinstance(ts, list):
            for row in ts:
                if row.get("TEAM_ABBREVIATION") == team_abbrev or row.get("team") == team_abbrev:
                    for col in ("FG3_PCT", "fg3_pct"):
                        val = row.get(col)
                        if val is not None:
                            try:
                                return float(val)
                            except (TypeError, ValueError):
                                pass
    return None


def _get_plus_minus_from_boxscore(game_id: str, team_abbrev: str) -> Optional[float]:
    """Get team point differential from boxscore home/away scores."""
    bs = _parse_boxscore(game_id)
    if not bs:
        return None
    home_team  = bs.get("home_team")
    away_team  = bs.get("away_team")
    home_score = bs.get("home_score")
    away_score = bs.get("away_score")
    if home_score is not None and away_score is not None:
        try:
            if team_abbrev == home_team:
                return float(home_score) - float(away_score)
            elif team_abbrev == away_team:
                return float(away_score) - float(home_score)
        except (TypeError, ValueError):
            pass
    return None


def _avg_starter_minutes(game_id: str, team_abbrev: str) -> Optional[float]:
    """Return average minutes of top-5 minute-earners for the team."""
    bs = _parse_boxscore(game_id)
    if not bs:
        return None
    players_data: List[dict] = []
    # Native format
    players = bs.get("players")
    if isinstance(players, list):
        for row in players:
            if row.get("team_abbreviation") == team_abbrev:
                try:
                    mins_raw = row.get("min", 0)
                    mins = float(mins_raw) if mins_raw else 0.0
                    if mins > 0:
                        players_data.append({"mins": mins})
                except (TypeError, ValueError):
                    pass
    if not players_data:
        return None
    players_data.sort(key=lambda x: x["mins"], reverse=True)
    top5 = players_data[:5]
    return round(sum(p["mins"] for p in top5) / len(top5), 2)


def get_team_form_features(
    team_abbrev: str,
    game_date: str,
    season: str,
    window: int = 10,
) -> dict:
    """
    Return advanced rolling form features for a team over the last `window` games.

    Args:
        team_abbrev: NBA team abbreviation (e.g. "LAL")
        game_date:   ISO date string "YYYY-MM-DD" of the target game (excluded)
        season:      Season string (e.g. "2024-25")
        window:      Number of prior games to include (default 10)

    Returns:
        dict with keys:
            team_quality_of_wins_l{n},
            team_strength_of_schedule_l{n},
            team_clutch_record_l{n},
            team_3pt_variance_l{n},
            team_blowout_factor_l{n},
            team_avg_minutes_starters_l{n},
            team_win_pct_l{n},
            team_form_games (actual count in window)
    """
    target_dt = datetime.strptime(game_date, "%Y-%m-%d")
    net_ratings = _load_net_ratings()

    games = _load_schedule(team_abbrev, season)
    if not games:
        return _default_form(team_abbrev, window)

    # Sort ascending and filter prior to target
    prior: List[dict] = []
    for g in games:
        try:
            gd = datetime.strptime(g["date"], "%Y-%m-%d")
        except Exception:
            continue
        if gd < target_dt and g.get("wl") in ("W", "L"):
            prior.append({**g, "_dt": gd})

    prior.sort(key=lambda x: x["_dt"])
    recent = prior[-window:]  # last N played games

    n = len(recent)
    if n == 0:
        return _default_form(team_abbrev, window)

    # ── Quality of wins ────────────────────────────────────────────────────────
    quality_of_wins = 0.0
    for g in recent:
        if g.get("wl") == "W":
            opp = g.get("opponent", "")
            quality_of_wins += net_ratings.get(opp, 0.0)

    # ── Strength of schedule ───────────────────────────────────────────────────
    opp_ratings = [net_ratings.get(g.get("opponent", ""), 0.0) for g in recent]
    sos = sum(opp_ratings) / max(n, 1)

    # ── Clutch record (games decided by ≤5) ───────────────────────────────────
    clutch_wins = 0
    clutch_games = 0
    blowout_count = 0
    pm_games = 0

    for g in recent:
        game_id = g.get("game_id", "")
        # Schedule cache doesn't store plus_minus; derive from boxscore
        pm_raw = g.get("plus_minus")
        if pm_raw is None and game_id:
            pm_raw = _get_plus_minus_from_boxscore(game_id, team_abbrev)
        if pm_raw is None:
            continue
        try:
            pm_val = float(pm_raw)
        except (TypeError, ValueError):
            continue
        pm_games += 1
        if abs(pm_val) <= 5:
            clutch_games += 1
            if g.get("wl") == "W":
                clutch_wins += 1
        if abs(pm_val) > 15:
            blowout_count += 1

    # ── 3PT variance ──────────────────────────────────────────────────────────
    fg3_pcts: List[float] = []
    for g in recent:
        game_id = g.get("game_id", "")
        pct = _get_3p_pct_from_boxscore(game_id, team_abbrev)
        if pct is not None:
            fg3_pcts.append(pct)

    fg3_variance = 0.0
    if len(fg3_pcts) >= 2:
        mean = sum(fg3_pcts) / len(fg3_pcts)
        fg3_variance = round(math.sqrt(sum((x - mean) ** 2 for x in fg3_pcts) / len(fg3_pcts)), 4)

    # ── Blowout factor ─────────────────────────────────────────────────────────
    blowout_factor = round(blowout_count / max(pm_games, 1), 4) if pm_games else 0.0

    # ── Average starter minutes ────────────────────────────────────────────────
    starter_mins_list: List[float] = []
    for g in recent:
        game_id = g.get("game_id", "")
        avg_m = _avg_starter_minutes(game_id, team_abbrev)
        if avg_m is not None:
            starter_mins_list.append(avg_m)

    avg_starter_mins = (round(sum(starter_mins_list) / len(starter_mins_list), 2)
                        if starter_mins_list else 30.0)

    # ── Win pct ────────────────────────────────────────────────────────────────
    wins = sum(1 for g in recent if g.get("wl") == "W")
    win_pct = round(wins / n, 4)

    suf = f"l{window}"
    return {
        f"team_quality_of_wins_{suf}":        round(quality_of_wins, 2),
        f"team_strength_of_schedule_{suf}":   round(sos, 3),
        f"team_clutch_record_{suf}":          round(clutch_wins / max(clutch_games, 1), 4),
        f"team_3pt_variance_{suf}":           fg3_variance,
        f"team_blowout_factor_{suf}":         blowout_factor,
        f"team_avg_minutes_starters_{suf}":   avg_starter_mins,
        f"team_win_pct_{suf}":                win_pct,
        "team_form_games":                    n,
        "team_abbrev":                        team_abbrev,
    }


def _default_form(team_abbrev: str, window: int) -> dict:
    suf = f"l{window}"
    return {
        f"team_quality_of_wins_{suf}":        0.0,
        f"team_strength_of_schedule_{suf}":   0.0,
        f"team_clutch_record_{suf}":          0.5,
        f"team_3pt_variance_{suf}":           0.0,
        f"team_blowout_factor_{suf}":         0.2,
        f"team_avg_minutes_starters_{suf}":   30.0,
        f"team_win_pct_{suf}":                0.5,
        "team_form_games":                    0,
        "team_abbrev":                        team_abbrev,
    }
