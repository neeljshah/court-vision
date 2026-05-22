"""
pinnacle_monitor.py — Pinnacle player-prop line movement tracker.

Fetches player prop lines specifically from Pinnacle (the sharpest sharp book)
via The Odds API player-props endpoint. Tracks opening vs. current movement
per player+stat — a 1.5pt move in 10 minutes on the over signals sharp steam.

Cache
-----
    data/nba/pinnacle_props_current.json  — current lines (TTL: 5 min live, 30 min pregame)
    data/nba/pinnacle_props_opening.json  — first-seen lines (never overwritten, grows over time)

Environment
-----------
    ODDS_API_KEY — The Odds API key (same key used by line_monitor.py)

Public API
----------
    get_prop_signal(player_name, stat)  -> dict
    refresh_pinnacle_props(force)       -> dict
    get_all_prop_signals()              -> dict   {"{player}|{stat}": signal_dict}
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.data.pinnacle_gate import strip_vig as _strip_vig

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_CURRENT = os.path.join(PROJECT_DIR, "data", "nba", "pinnacle_props_current.json")
_CACHE_OPENING = os.path.join(PROJECT_DIR, "data", "nba", "pinnacle_props_opening.json")
_ODDS_API_KEY_ENV = "ODDS_API_KEY"
_SPORT           = "basketball_nba"
_BOOKMAKER       = "pinnacle"

# Player prop markets supported by The Odds API
_PROP_MARKETS: Dict[str, str] = {
    "pts":  "player_points",
    "reb":  "player_rebounds",
    "ast":  "player_assists",
    "fg3m": "player_threes",
    "stl":  "player_steals",
    "blk":  "player_blocks",
    "tov":  "player_turnovers",
}

_TTL_LIVE_SEC    = 5 * 60   # 5 min during game window (17–23 ET)
_TTL_PREGAME_SEC = 30 * 60  # 30 min pregame


def _ttl() -> int:
    hour = datetime.now().hour
    return _TTL_LIVE_SEC if 17 <= hour <= 23 else _TTL_PREGAME_SEC


def _cache_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < _ttl()


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _prop_key(player: str, stat: str) -> str:
    return f"{player.lower().strip()}|{stat}"


def _vig_free_prob(over_odds: int, under_odds: int) -> float:
    """Remove vig from over/under pair and return vig-free over probability."""
    return _strip_vig(over_odds, under_odds)["over_prob"]


# ── Core fetcher ──────────────────────────────────────────────────────────────

def refresh_pinnacle_props(force: bool = False) -> dict:
    """
    Fetch current Pinnacle player prop lines from The Odds API.

    Iterates over today's NBA events and fetches player prop markets
    for each, filtering to Pinnacle only.

    Args:
        force: Bypass TTL and always re-fetch.

    Returns:
        Dict keyed by "{player_lower}|{stat}" → {
            "line":          float,
            "over_odds":     int,
            "under_odds":    int,
            "vig_free_prob": float,
            "player":        str,
            "stat":          str,
            "fetched_at":    str,
        }
    """
    if not force and _cache_fresh(_CACHE_CURRENT):
        return _load(_CACHE_CURRENT)

    api_key = os.environ.get(_ODDS_API_KEY_ENV)
    if not api_key:
        print(f"[pinnacle_monitor] {_ODDS_API_KEY_ENV} not set — no Pinnacle data")
        return _load(_CACHE_CURRENT)

    try:
        import requests
    except ImportError:
        print("[pinnacle_monitor] requests not installed")
        return _load(_CACHE_CURRENT)

    # Step 1: get today's game event IDs
    try:
        events_resp = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{_SPORT}/events",
            params={"apiKey": api_key},
            timeout=15,
        )
        events_resp.raise_for_status()
        events: List[dict] = events_resp.json()
    except Exception as e:
        print(f"[pinnacle_monitor] Events fetch error: {e}")
        return _load(_CACHE_CURRENT)

    fetched_at = datetime.now(timezone.utc).isoformat()
    current: dict = {}

    for event in events:
        event_id   = event.get("id", "")
        if not event_id:
            continue

        # Step 2: fetch player prop markets for this event (Pinnacle only)
        for stat, market_key in _PROP_MARKETS.items():
            try:
                time.sleep(0.3)  # gentle rate-limiting (each call costs API credits)
                resp = requests.get(
                    f"https://api.the-odds-api.com/v4/sports/{_SPORT}/events/{event_id}/odds",
                    params={
                        "apiKey":     api_key,
                        "regions":    "us",
                        "markets":    market_key,
                        "bookmakers": _BOOKMAKER,
                        "oddsFormat": "american",
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue

            for bk in data.get("bookmakers", []):
                if bk.get("key") != _BOOKMAKER:
                    continue
                for mkt in bk.get("markets", []):
                    if mkt.get("key") != market_key:
                        continue
                    outcomes = mkt.get("outcomes", [])
                    # Group by player description → over + under pair
                    player_lines: Dict[str, dict] = {}
                    for o in outcomes:
                        desc    = o.get("description", "")  # player name
                        name    = o.get("name", "")         # "Over" / "Under"
                        price   = o.get("price")
                        point   = o.get("point")
                        if not desc or price is None or point is None:
                            continue
                        pl_key = desc.strip()
                        if pl_key not in player_lines:
                            player_lines[pl_key] = {}
                        player_lines[pl_key]["line"]  = float(point)
                        player_lines[pl_key][name.lower() + "_odds"] = int(price)

                    for player_name, pl in player_lines.items():
                        line      = pl.get("line")
                        over_odds = pl.get("over_odds")
                        under_odds = pl.get("under_odds")
                        if line is None or over_odds is None or under_odds is None:
                            continue
                        key = _prop_key(player_name, stat)
                        current[key] = {
                            "player":        player_name,
                            "stat":          stat,
                            "line":          line,
                            "over_odds":     over_odds,
                            "under_odds":    under_odds,
                            "vig_free_prob": _vig_free_prob(over_odds, under_odds),
                            "fetched_at":    fetched_at,
                        }

    _save(_CACHE_CURRENT, current)

    # Save opening lines (first-seen — never overwrite existing entries)
    opening = _load(_CACHE_OPENING)
    updated = False
    for key, rec in current.items():
        if key not in opening:
            opening[key] = {
                "line":          rec["line"],
                "vig_free_prob": rec["vig_free_prob"],
                "recorded_at":   fetched_at,
            }
            updated = True
    if updated:
        _save(_CACHE_OPENING, opening)

    print(f"[pinnacle_monitor] Fetched {len(current)} Pinnacle prop lines")
    return current


# ── Public API ────────────────────────────────────────────────────────────────

def get_prop_signal(player_name: str, stat: str) -> dict:
    """
    Return Pinnacle sharp-money signal for a player prop.

    Line movement = opening_line - current_line (positive = line moved UP,
    sharps hammered the over; negative = line moved DOWN, sharps on under).
    vig_free_prob is Pinnacle's market-implied probability of the over.

    Args:
        player_name: Full player name (e.g. "Jayson Tatum"). Case-insensitive.
        stat:        One of: pts, reb, ast, fg3m, stl, blk, tov.

    Returns:
        {
            "line":           float | None,
            "over_odds":      int   | None,
            "under_odds":     int   | None,
            "vig_free_prob":  float,          # vig-removed implied P(over)
            "line_move":      float,          # opening - current (+ = over steam)
            "found":          bool,
        }
    """
    _null = {
        "line": None, "over_odds": None, "under_odds": None,
        "vig_free_prob": 0.5, "line_move": 0.0, "found": False,
    }

    current = refresh_pinnacle_props()
    key     = _prop_key(player_name, stat)
    rec     = current.get(key)
    if not rec:
        return _null

    opening = _load(_CACHE_OPENING)
    open_rec = opening.get(key)
    line_move = 0.0
    if open_rec and open_rec.get("line") is not None:
        line_move = round(float(open_rec["line"]) - float(rec["line"]), 2)

    return {
        "line":          rec["line"],
        "over_odds":     rec.get("over_odds"),
        "under_odds":    rec.get("under_odds"),
        "vig_free_prob": rec.get("vig_free_prob", 0.5),
        "line_move":     line_move,
        "found":         True,
    }


def get_all_prop_signals() -> dict:
    """
    Return all current Pinnacle prop signals (full cache).

    Returns:
        Dict keyed by "{player_lower}|{stat}" → signal dict.
    """
    return refresh_pinnacle_props()


# ── line-movement history (for steam detection, task 16.7-02) ────────────────
# Timestamped snapshot log so downstream consumers (line_timing.detect_steam)
# can see intra-window movement, not just opening-vs-current.
_LINE_HISTORY = os.path.join(PROJECT_DIR, "data", "nba", "pinnacle_line_history.json")


def record_line_snapshot(player_name: str, stat: str, line: float,
                         ts: Optional[str] = None,
                         history_path: Optional[str] = None) -> None:
    """Append one timestamped Pinnacle line observation to the history log."""
    path = history_path or _LINE_HISTORY
    os.makedirs(os.path.dirname(path), exist_ok=True)
    hist = _load(path)
    key = _prop_key(player_name, stat)
    hist.setdefault(key, []).append({
        "timestamp": ts or datetime.now(timezone.utc).isoformat(),
        "line": float(line),
    })
    _save(path, hist)


def get_line_history(player_name: str, stat: str,
                     history_path: Optional[str] = None) -> List[Dict]:
    """Return the chronological line-snapshot history for a player+stat prop.

    Each element is ``{"timestamp": iso8601, "line": float}``.  Returns [] when
    no history has been recorded yet.
    """
    path = history_path or _LINE_HISTORY
    hist = _load(path)
    snaps = hist.get(_prop_key(player_name, stat), [])
    return sorted(snaps, key=lambda s: s.get("timestamp", ""))


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Pinnacle player prop monitor")
    ap.add_argument("--refresh", action="store_true", help="Force-refresh props")
    ap.add_argument("--player",  help="Player name to look up")
    ap.add_argument("--stat",    default="pts", help="Stat to look up (pts/reb/ast/...)")
    args = ap.parse_args()

    if args.player:
        sig = get_prop_signal(args.player, args.stat)
        print(json.dumps(sig, indent=2))
    else:
        props = refresh_pinnacle_props(force=args.refresh)
        print(f"Total Pinnacle props cached: {len(props)}")
        for k, v in list(props.items())[:5]:
            print(f"  {k}: line={v['line']} move={v.get('line_move', 0.0):+.1f} "
                  f"prob={v['vig_free_prob']:.3f}")
