"""
action_network.py — Action Network sharp% / public% fetcher.

Fetches public betting percentages and sharp-money indicators for NBA player
props from the Action Network's public JSON API (unofficial, no auth required).

Action Network exposes:
  - public_bets_pct  : % of public tickets on the over
  - public_money_pct : % of public dollars on the over
  When public_bets_pct is high but the line moves AGAINST the public, that
  confirms sharp money (reverse-line movement = strong steam indicator).

Steam move flag = line_move direction OPPOSITE to public_bets_pct lean.

Cache
-----
    data/nba/action_network_cache.json   (TTL: 15 minutes)

Public API
----------
    get_sharp_pct(player_name, stat)  -> dict
    refresh_action_network(force)     -> dict
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, date, timezone
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH = os.path.join(PROJECT_DIR, "data", "nba", "action_network_cache.json")
_TTL_SEC    = 15 * 60   # 15 minutes

# Action Network public API base
_AN_BASE   = "https://api.actionnetwork.com/web/v1"
_AN_LEAGUE = "nba"

# Map our stat names to Action Network market type strings (best-effort; may vary)
_STAT_TO_AN_MARKET: Dict[str, str] = {
    "pts":  "player_points",
    "reb":  "player_total_rebounds",
    "ast":  "player_assists",
    "fg3m": "player_threes",
    "stl":  "player_steals",
    "blk":  "player_blocks",
    "tov":  "player_turnovers",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def _cache_fresh() -> bool:
    if not os.path.exists(_CACHE_PATH):
        return False
    return (time.time() - os.path.getmtime(_CACHE_PATH)) < _TTL_SEC


def _load_cache() -> dict:
    try:
        with open(_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _prop_key(player: str, stat: str) -> str:
    return f"{player.lower().strip()}|{stat}"


def _norm_name(name: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


# ── Fetcher ───────────────────────────────────────────────────────────────────

def refresh_action_network(force: bool = False) -> dict:
    """
    Fetch today's NBA player prop betting percentages from Action Network.

    Attempts to retrieve public% / sharp% data. Gracefully returns the
    stale cache (or empty dict) when the API is unavailable.

    Returns:
        Dict keyed by "{player_lower}|{stat}" → {
            "player":          str,
            "stat":            str,
            "line":            float | None,
            "public_bets_pct": float,    # 0–100, % tickets on over
            "public_money_pct":float,    # 0–100, % dollars on over
            "steam_move":      bool,     # True if reverse-line movement
            "fetched_at":      str,
        }
    """
    if not force and _cache_fresh():
        return _load_cache()

    try:
        import requests
    except ImportError:
        print("[action_network] requests not installed")
        return _load_cache()

    today_str = date.today().isoformat()   # e.g. "2026-03-19"
    result: dict = {}

    try:
        # Step 1: get today's NBA game IDs from Action Network
        games_url = f"{_AN_BASE}/competitions/{_AN_LEAGUE}/events"
        resp = requests.get(
            games_url,
            params={"date": today_str, "include": "odds"},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        games: List[dict] = payload.get("events", payload) if isinstance(payload, dict) else payload

    except Exception as e:
        print(f"[action_network] Games fetch failed: {e}")
        return _load_cache()

    fetched_at = datetime.now(timezone.utc).isoformat()

    for game in games:
        game_id = game.get("id") or game.get("event_id")
        if not game_id:
            continue

        # Step 2: fetch player prop markets for this game
        for stat, market_type in _STAT_TO_AN_MARKET.items():
            try:
                time.sleep(0.3)
                props_url = f"{_AN_BASE}/{_AN_LEAGUE}/games/{game_id}/markets"
                r = requests.get(
                    props_url,
                    params={"market_type": market_type},
                    headers=_HEADERS,
                    timeout=15,
                )
                r.raise_for_status()
                markets_payload = r.json()
                markets: List[dict] = (
                    markets_payload.get("markets", markets_payload)
                    if isinstance(markets_payload, dict)
                    else markets_payload
                )
            except Exception:
                continue

            for mkt in markets:
                player = mkt.get("player_name") or mkt.get("player") or ""
                if not player:
                    continue
                line          = mkt.get("line") or mkt.get("over_under")
                pub_bets      = float(mkt.get("public_bets_pct")  or mkt.get("public_pct") or 0.0)
                pub_money     = float(mkt.get("public_money_pct") or mkt.get("money_pct")  or 0.0)
                line_move     = float(mkt.get("line_move") or 0.0)

                # Reverse line movement (RLM): public heavy one way but the
                # line moved the other — the classic sharp-money tell.
                rlm = (pub_bets > 60 and line_move < -0.25) or \
                      (pub_bets < 40 and line_move > 0.25)

                key = _prop_key(player, stat)
                result[key] = {
                    "player":           player,
                    "stat":             stat,
                    "line":             float(line) if line is not None else None,
                    "public_bets_pct":  round(pub_bets, 1),
                    "public_money_pct": round(pub_money, 1),
                    "line_move":        round(line_move, 2),
                    "rlm":              rlm,
                    "steam_move":       rlm,   # back-compat alias
                    "fetched_at":       fetched_at,
                }

    if result:
        _save_cache(result)
        print(f"[action_network] Fetched {len(result)} prop markets")
    else:
        print("[action_network] No prop data returned (API may have changed structure)")

    return result or _load_cache()


# ── Public API ────────────────────────────────────────────────────────────────

def get_sharp_pct(player_name: str, stat: str) -> dict:
    """
    Return Action Network sharp/public split for a player prop.

    Args:
        player_name: Full player name (e.g. "LeBron James"). Case-insensitive.
        stat:        One of: pts, reb, ast, fg3m, stl, blk, tov.

    Returns:
        {
            "public_bets_pct":  float,   # 0–100; high = public heavy on over
            "public_money_pct": float,
            "rlm":              bool,    # reverse line movement detected
            "steam_move":       bool,    # back-compat alias of rlm
            "found":            bool,
        }
    """
    _null = {"public_bets_pct": 50.0, "public_money_pct": 50.0,
             "rlm": False, "steam_move": False, "found": False}

    cache = refresh_action_network()

    def _shape(rec: dict) -> dict:
        rlm = bool(rec.get("rlm", rec.get("steam_move", False)))
        return {
            "public_bets_pct":  rec.get("public_bets_pct", 50.0),
            "public_money_pct": rec.get("public_money_pct", 50.0),
            "rlm":              rlm,
            "steam_move":       rlm,
            "found":            True,
        }

    # Try exact key first
    key = _prop_key(player_name, stat)
    if key in cache:
        return _shape(cache[key])

    # Fuzzy name match (normalise unicode)
    norm = _norm_name(player_name)
    for k, rec in cache.items():
        if k.endswith(f"|{stat}") and _norm_name(rec.get("player", "")) == norm:
            return _shape(rec)

    return _null


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Action Network sharp% monitor")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--player",  help="Player name")
    ap.add_argument("--stat",    default="pts")
    args = ap.parse_args()

    if args.player:
        sig = get_sharp_pct(args.player, args.stat)
        print(json.dumps(sig, indent=2))
    else:
        data = refresh_action_network(force=args.refresh)
        print(f"Action Network props cached: {len(data)}")
        for k, v in list(data.items())[:5]:
            print(f"  {k}: pub%={v['public_bets_pct']} steam={v['steam_move']}")
