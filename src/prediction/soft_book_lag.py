"""
soft_book_lag.py -- Phase E3: Detect books slow to adjust after injury news.

Soft books (Caesars, DraftKings retail, smaller regional books) lag sharp
books (Pinnacle, Circa, FanDuel) by 5-30 minutes after injury announcements.

This detector:
  1. Monitors current props vs line from 30 min ago
  2. Flags gaps > threshold vs sharp books
  3. Produces "lag bet" candidates with estimated edge

Public API
----------
    get_lag_bets(season)                          -> list[dict]
    check_book_lag(player_name, stat, season)     -> dict
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

# Soft books that tend to lag (list can be extended)
_SOFT_BOOKS = ["caesars", "betmgm", "wynnbet", "pointsbet"]
_SHARP_BOOKS = ["pinnacle", "circa", "fanduel", "betrivers"]

# Minimum line gap to flag as a lag bet
_LAG_THRESHOLD = 1.5  # points


def _load_current_lines(season: str) -> dict:
    """Load most recent props from cache. {player_name: {stat: {book: line}}}"""
    path = os.path.join(PROJECT_DIR, "data", "external", f"props_latest_{season}.json")
    if os.path.exists(path):
        # Only use if fresh (< 60 min old)
        age_min = (time.time() - os.path.getmtime(path)) / 60
        if age_min < 60:
            try:
                return json.load(open(path))
            except Exception:
                pass
    return {}


def check_book_lag(
    player_name: str,
    stat: str = "pts",
    season: str = "2024-25",
) -> dict:
    """
    Check if a soft book line is lagging behind sharp books for a player/stat.

    Returns:
        {
            "player":       str,
            "stat":         str,
            "sharp_line":   float | None,
            "soft_lines":   dict,         # {book: line}
            "max_lag":      float,        # largest gap soft vs sharp
            "lag_book":     str | None,   # most lagged book
            "is_lag_bet":   bool,
            "edge_estimate": float,       # approx % edge from lag
        }
    """
    lines = _load_current_lines(season)
    player_data = lines.get(player_name, {})
    stat_data = player_data.get(stat, {})

    if not stat_data:
        return {
            "player": player_name, "stat": stat,
            "sharp_line": None, "soft_lines": {},
            "max_lag": 0.0, "lag_book": None,
            "is_lag_bet": False, "edge_estimate": 0.0,
        }

    # Find sharp consensus
    sharp_vals = [v for k, v in stat_data.items() if k.lower() in _SHARP_BOOKS]
    sharp_line = sum(sharp_vals) / len(sharp_vals) if sharp_vals else None

    # Find lagging soft books
    soft_lines = {k: v for k, v in stat_data.items() if k.lower() in _SOFT_BOOKS}

    max_lag = 0.0
    lag_book = None
    if sharp_line is not None and soft_lines:
        for book, line in soft_lines.items():
            gap = abs(line - sharp_line)
            if gap > max_lag:
                max_lag = gap
                lag_book = book

    is_lag_bet = max_lag >= _LAG_THRESHOLD
    edge_estimate = min(max_lag / 5.0, 0.20) if is_lag_bet else 0.0

    return {
        "player":        player_name,
        "stat":          stat,
        "sharp_line":    sharp_line,
        "soft_lines":    soft_lines,
        "max_lag":       round(max_lag, 2),
        "lag_book":      lag_book,
        "is_lag_bet":    is_lag_bet,
        "edge_estimate": round(edge_estimate, 3),
    }


def get_lag_bets(
    season:    str = "2024-25",
    min_lag:   float = _LAG_THRESHOLD,
    stats:     Optional[list] = None,
) -> list:
    """
    Return all current lag bet opportunities across all players.

    Returns:
        list of {player, stat, sharp_line, lag_book, soft_line, edge_estimate}
        sorted by edge_estimate descending.
    """
    if stats is None:
        stats = ["pts", "reb", "ast", "fg3m"]

    lines = _load_current_lines(season)
    if not lines:
        return []

    results = []
    for player_name in lines:
        for stat in stats:
            r = check_book_lag(player_name, stat, season)
            if r["is_lag_bet"] and r["max_lag"] >= min_lag:
                results.append(r)

    results.sort(key=lambda x: -x["edge_estimate"])
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--player", default=None)
    parser.add_argument("--stat",   default="pts")
    parser.add_argument("--season", default="2024-25")
    args = parser.parse_args()

    if args.player:
        import json
        result = check_book_lag(args.player, args.stat, args.season)
        print(json.dumps(result, indent=2))
    else:
        bets = get_lag_bets(args.season)
        if not bets:
            print("[soft_book_lag] No lag bets found (props_latest_*.json missing or no gaps)")
        for b in bets:
            print(f"  {b['player']:25s}  {b['stat']:5s}  "
                  f"sharp={b['sharp_line']}  lag_book={b['lag_book']}  "
                  f"edge={b['edge_estimate']:.1%}")
