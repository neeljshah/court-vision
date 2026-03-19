"""
line_monitor.py — The Odds API wrapper for NBA game lines (Phase 5).

Fetches NBA spread, total, and moneyline from https://api.the-odds-api.com.
Caches lines to data/nba/lines_cache.json with TTL:
    - Pre-game  : 1 hour
    - Live (<2h to tip) : 5 minutes

Requires:
    ODDS_API_KEY environment variable set to your The Odds API key.

Public API
----------
    get_game_lines(home_team, away_team)     -> dict
    get_sharp_signal(home_team, away_team)   -> float
    refresh_lines(force)                     -> dict
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH       = os.path.join(PROJECT_DIR, "data", "nba", "lines_cache.json")
_HISTORY_PATH     = os.path.join(PROJECT_DIR, "data", "nba", "lines_opening.json")
_TTL_LIVE_SEC     = 5 * 60      # 5 minutes (game day, <2h to tip)
_TTL_PREGAME_SEC  = 60 * 60     # 1 hour (pregame)
_ODDS_API_KEY_ENV = "ODDS_API_KEY"
_SPORT            = "basketball_nba"
_MARKETS          = "h2h,spreads,totals"
_REGIONS          = "us"
_ODDS_FORMAT      = "american"
_BASE_URL         = "https://api.the-odds-api.com/v4/sports/{sport}/odds/"

# NBA team name aliases — The Odds API uses full city+name strings
_TEAM_ALIASES: Dict[str, List[str]] = {
    "ATL": ["Atlanta Hawks"],
    "BOS": ["Boston Celtics"],
    "BKN": ["Brooklyn Nets"],
    "CHA": ["Charlotte Hornets"],
    "CHI": ["Chicago Bulls"],
    "CLE": ["Cleveland Cavaliers"],
    "DAL": ["Dallas Mavericks"],
    "DEN": ["Denver Nuggets"],
    "DET": ["Detroit Pistons"],
    "GSW": ["Golden State Warriors"],
    "HOU": ["Houston Rockets"],
    "IND": ["Indiana Pacers"],
    "LAC": ["LA Clippers", "Los Angeles Clippers"],
    "LAL": ["LA Lakers", "Los Angeles Lakers"],
    "MEM": ["Memphis Grizzlies"],
    "MIA": ["Miami Heat"],
    "MIL": ["Milwaukee Bucks"],
    "MIN": ["Minnesota Timberwolves"],
    "NOP": ["New Orleans Pelicans"],
    "NYK": ["New York Knicks"],
    "OKC": ["Oklahoma City Thunder"],
    "ORL": ["Orlando Magic"],
    "PHI": ["Philadelphia 76ers"],
    "PHX": ["Phoenix Suns"],
    "POR": ["Portland Trail Blazers"],
    "SAC": ["Sacramento Kings"],
    "SAS": ["San Antonio Spurs"],
    "TOR": ["Toronto Raptors"],
    "UTA": ["Utah Jazz"],
    "WAS": ["Washington Wizards"],
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_team(name: str) -> List[str]:
    """
    Return list of known display-name variants for a team.

    Accepts 3-letter abbreviation or any known variant.
    Returns the name as-is (wrapped in a list) if not found.
    """
    upper = name.upper().strip()
    if upper in _TEAM_ALIASES:
        return _TEAM_ALIASES[upper]
    # Maybe it's already a full name — check values
    for aliases in _TEAM_ALIASES.values():
        if name in aliases or name.lower() in [a.lower() for a in aliases]:
            return aliases
    return [name]


def _team_matches(api_name: str, query: str) -> bool:
    """Return True if api_name matches the query team (alias-aware)."""
    variants = _resolve_team(query)
    return api_name in variants or any(v.lower() == api_name.lower() for v in variants)


def _cache_ttl() -> int:
    """Return TTL in seconds based on time-to-next-tipoff heuristic."""
    now_hour = datetime.now().hour
    # NBA tipoffs 19-22 ET; treat 17-23 window as live mode
    if 17 <= now_hour <= 23:
        return _TTL_LIVE_SEC
    return _TTL_PREGAME_SEC


def _cache_is_fresh() -> bool:
    """Return True if lines_cache.json exists and is within TTL."""
    if not os.path.exists(_CACHE_PATH):
        return False
    age = time.time() - os.path.getmtime(_CACHE_PATH)
    return age < _cache_ttl()


def _load_cache() -> dict:
    with open(_CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_cache(data: dict) -> None:
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _load_opening_history() -> dict:
    """Load opening-line history (for sharp signal calculation)."""
    if not os.path.exists(_HISTORY_PATH):
        return {}
    try:
        with open(_HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_opening_history(data: dict) -> None:
    os.makedirs(os.path.dirname(_HISTORY_PATH), exist_ok=True)
    with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _game_key(home_team: str, away_team: str) -> str:
    """Canonical key for a matchup."""
    return f"{home_team.upper()}_{away_team.upper()}"


# ── core API ──────────────────────────────────────────────────────────────────

def refresh_lines(force: bool = False) -> dict:
    """
    Fetch current NBA lines from The Odds API and cache to disk.

    Skips the network call if the cache is fresh (respects live vs pre-game TTL).
    Falls back to stale cache if the API is unavailable.
    Silently returns empty dict if ODDS_API_KEY is not set.

    Args:
        force: If True, bypass TTL and always re-fetch.

    Returns:
        Dict of game_id → {home_team, away_team, commence_time,
                            spread_home, total_over, home_ml, away_ml,
                            bookmakers_count, fetched_at}
    """
    api_key = os.environ.get(_ODDS_API_KEY_ENV)
    if not api_key:
        print(f"[line_monitor] {_ODDS_API_KEY_ENV} not set — no odds data available")
        return _load_cache() if os.path.exists(_CACHE_PATH) else {}

    if not force and _cache_is_fresh():
        return _load_cache()

    try:
        import requests

        url = _BASE_URL.format(sport=_SPORT)
        params = {
            "apiKey":     api_key,
            "regions":    _REGIONS,
            "markets":    _MARKETS,
            "oddsFormat": _ODDS_FORMAT,
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        raw_games: List[dict] = resp.json()

    except Exception as e:
        print(f"[line_monitor] Odds API fetch error: {e}")
        if os.path.exists(_CACHE_PATH):
            print("[line_monitor] Returning stale cache.")
            return _load_cache()
        return {}

    fetched_at = datetime.now(timezone.utc).isoformat()
    history    = _load_opening_history()
    lines: dict = {}

    for game in raw_games:
        gid         = game.get("id", "")
        home_team   = game.get("home_team", "")
        away_team   = game.get("away_team", "")
        commence    = game.get("commence_time", "")
        bookmakers  = game.get("bookmakers", [])

        spread_vals: List[float] = []
        total_vals:  List[float] = []
        home_ml_vals: List[int]  = []
        away_ml_vals: List[int]  = []

        for bk in bookmakers:
            for mkt in bk.get("markets", []):
                key = mkt.get("key", "")
                outcomes = mkt.get("outcomes", [])
                if key == "spreads":
                    for o in outcomes:
                        if o.get("name") == home_team:
                            try:
                                spread_vals.append(float(o["point"]))
                            except (KeyError, ValueError):
                                pass
                elif key == "totals":
                    for o in outcomes:
                        if o.get("name") == "Over":
                            try:
                                total_vals.append(float(o["point"]))
                            except (KeyError, ValueError):
                                pass
                elif key == "h2h":
                    for o in outcomes:
                        try:
                            if o.get("name") == home_team:
                                home_ml_vals.append(int(o["price"]))
                            elif o.get("name") == away_team:
                                away_ml_vals.append(int(o["price"]))
                        except (KeyError, ValueError):
                            pass

        spread_avg  = round(sum(spread_vals) / len(spread_vals), 1) if spread_vals else None
        total_avg   = round(sum(total_vals)  / len(total_vals),  1) if total_vals  else None
        home_ml_avg = round(sum(home_ml_vals) / len(home_ml_vals)) if home_ml_vals else None
        away_ml_avg = round(sum(away_ml_vals) / len(away_ml_vals)) if away_ml_vals else None

        record = {
            "home_team":        home_team,
            "away_team":        away_team,
            "commence_time":    commence,
            "spread_home":      spread_avg,
            "total_over":       total_avg,
            "home_ml":          home_ml_avg,
            "away_ml":          away_ml_avg,
            "bookmakers_count": len(bookmakers),
            "fetched_at":       fetched_at,
        }
        lines[gid] = record

        # Save first-seen as opening line (for sharp signal)
        key = _game_key(home_team, away_team)
        if key not in history and spread_avg is not None:
            history[key] = {
                "spread_home_open": spread_avg,
                "total_open":       total_avg,
                "recorded_at":      fetched_at,
            }

    _save_cache(lines)
    _save_opening_history(history)
    print(f"[line_monitor] Fetched {len(lines)} NBA games → {_CACHE_PATH}")
    return lines


def get_game_lines(home_team: str, away_team: str) -> dict:
    """
    Return current lines for a specific matchup.

    Args:
        home_team: Team abbreviation or full name (e.g. "BOS", "Boston Celtics").
        away_team: Team abbreviation or full name.

    Returns:
        {
            "home_team": str, "away_team": str,
            "spread_home": float | None,   # negative = home favoured
            "total_over": float | None,
            "home_ml": int | None,
            "away_ml": int | None,
            "bookmakers_count": int,
            "found": bool,
        }
        "found" is False if no matching game is in the current cache.
    """
    lines = refresh_lines()
    for gid, rec in lines.items():
        if _team_matches(rec.get("home_team", ""), home_team) and \
           _team_matches(rec.get("away_team", ""), away_team):
            return {**rec, "found": True}
    return {
        "home_team":        home_team,
        "away_team":        away_team,
        "spread_home":      None,
        "total_over":       None,
        "home_ml":          None,
        "away_ml":          None,
        "bookmakers_count": 0,
        "found":            False,
    }


def get_sharp_signal(home_team: str, away_team: str) -> float:
    """
    Compute sharp-money signal for the home team.

    Compares the current closing spread to the opening line.
    A positive value means the line moved in the home team's favour
    (sharp money on home).  Returns 0.0 if no history or lines available.

    Args:
        home_team: Team abbreviation or full name.
        away_team: Team abbreviation or full name.

    Returns:
        Line movement in points (positive = sharp on home, negative = sharp on away).
        0.0 if opening line not recorded or current line unavailable.
    """
    current = get_game_lines(home_team, away_team)
    if not current["found"] or current["spread_home"] is None:
        return 0.0

    history = _load_opening_history()
    key     = _game_key(home_team, away_team)
    if key not in history or history[key].get("spread_home_open") is None:
        return 0.0

    opening = float(history[key]["spread_home_open"])
    closing = float(current["spread_home"])
    # Movement: if home was -4 open and now -6, that's 2 pts sharper on home → +2
    return round(opening - closing, 1)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="NBA Line Monitor (The Odds API)")
    ap.add_argument("--refresh",    action="store_true", help="Force-refresh lines from API")
    ap.add_argument("--game",       nargs=2, metavar=("HOME", "AWAY"),
                    help="Look up lines for HOME vs AWAY")
    ap.add_argument("--sharp",      nargs=2, metavar=("HOME", "AWAY"),
                    help="Get sharp signal for HOME vs AWAY")
    args = ap.parse_args()

    if args.refresh:
        lines = refresh_lines(force=True)
        print(f"Lines cached: {len(lines)} games")

    elif args.game:
        info = get_game_lines(args.game[0], args.game[1])
        print(json.dumps(info, indent=2))

    elif args.sharp:
        signal = get_sharp_signal(args.sharp[0], args.sharp[1])
        print(f"Sharp signal ({args.sharp[0]} vs {args.sharp[1]}): {signal:+.1f} pts")

    else:
        lines = refresh_lines()
        for gid, rec in list(lines.items())[:5]:
            print(f"  {rec['away_team']} @ {rec['home_team']}: "
                  f"spread={rec['spread_home']}  total={rec['total_over']}  "
                  f"ML {rec['home_ml']}/{rec['away_ml']}")
