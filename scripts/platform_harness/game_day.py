"""game_day.py — offline-safe NBA game-day probe for the autonomous build harness.

Tells the orchestrator whether today is an NBA game day so it can avoid landing
risky build work while the live API and prediction loop are in read-only mode.

Exit code is always 0. The verdict is printed to stdout on the first line.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_CDN_URL = (
    "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _today_local() -> date:
    return date.today()


def _game_date_local(game: dict) -> date | None:
    """Extract the calendar date for a game from gameTimeUTC or gameEt."""
    # Try gameEt first (already in Eastern, easier to match local calendar)
    for key in ("gameEt", "gameTimeUTC"):
        val = game.get(key, "")
        if not val:
            continue
        try:
            # Formats seen: "2026-06-11T00:00:00Z" or "2026-06-11T00:00:00"
            val_clean = val.rstrip("Z")
            dt = datetime.fromisoformat(val_clean)
            return dt.date()
        except (ValueError, TypeError):
            continue
    return None


def _probe_cdn() -> dict:
    """Hit the NBA CDN scoreboard endpoint and return a raw result dict."""
    req = urllib.request.Request(_CDN_URL, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=3) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    games = raw.get("scoreboard", {}).get("games", [])
    today = _today_local()

    games_today = [g for g in games if _game_date_local(g) == today]
    games_today_count = len(games_today)

    # Any game scheduled (1), live (2), or final (3) counts as a game day
    if games_today_count > 0:
        verdict = "GAME_DAY"
    else:
        verdict = "CLEAR"

    # Best-effort next game date from all future games (status 1 = scheduled)
    next_game = "unknown"
    future_dates: list[date] = []
    for g in games:
        if g.get("gameStatus") == 1:
            gd = _game_date_local(g)
            if gd and gd > today:
                future_dates.append(gd)
    if future_dates:
        next_game = str(min(future_dates))

    return {
        "verdict": verdict,
        "today": str(today),
        "source": "cdn",
        "next_game": next_game,
        "games_today": games_today_count,
        "note": None,
    }


def probe() -> dict:
    """Probe whether today is an NBA game day.

    Priority:
    1. CV_GAME_DAY env override (``1``/``true`` → GAME_DAY; ``0``/``false`` → CLEAR).
    2. NBA_OFFLINE=1 → skip network, return CLEAR with source=offline.
    3. NBA CDN live scoreboard (timeout=3 s).
    4. Any exception → offline fallback (CLEAR, source=offline).

    Returns a dict with keys:
        verdict      : "GAME_DAY" | "CLEAR"
        today        : ISO date string
        source       : "cdn" | "offline" | "override"
        next_game    : ISO date string or "unknown"
        games_today  : int or None
        note         : str or None
    """
    today_str = str(_today_local())

    # --- 1. Env override ---
    cv_override = os.environ.get("CV_GAME_DAY", "").strip().lower()
    if cv_override in ("1", "true"):
        return {
            "verdict": "GAME_DAY",
            "today": today_str,
            "source": "override",
            "next_game": "unknown",
            "games_today": None,
            "note": None,
        }
    if cv_override in ("0", "false"):
        return {
            "verdict": "CLEAR",
            "today": today_str,
            "source": "override",
            "next_game": "unknown",
            "games_today": None,
            "note": None,
        }

    # --- 2. Offline mode ---
    if os.environ.get("NBA_OFFLINE", "").strip() == "1":
        return {
            "verdict": "CLEAR",
            "today": today_str,
            "source": "offline",
            "next_game": "unknown",
            "games_today": None,
            "note": "NBA_OFFLINE=1; network skipped; verdict may be wrong",
        }

    # --- 3. CDN probe ---
    try:
        return _probe_cdn()
    except Exception:
        pass

    # --- 4. Offline fallback ---
    return {
        "verdict": "CLEAR",
        "today": today_str,
        "source": "offline",
        "next_game": "unknown",
        "games_today": None,
        "note": "CDN unreachable; defaulting to CLEAR (override via CV_GAME_DAY)",
    }


def _print_result(r: dict) -> None:
    """Print the probe result in the harness-parseable format."""
    print(r["verdict"])
    print(f"today: {r['today']}")
    print(f"source: {r['source']}")
    if r.get("next_game"):
        print(f"next_game: {r['next_game']}")
    if r.get("games_today") is not None:
        print(f"games_today: {r['games_today']}")
    if r.get("note"):
        print(f"note: {r['note']}")


if __name__ == "__main__":
    result = probe()
    _print_result(result)
    sys.exit(0)
