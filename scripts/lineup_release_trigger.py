"""
lineup_release_trigger.py — Rerun daily slate 30 minutes before each game's tip-off.

NBA starting lineups are released ~30 min before tip-off.  Running the full
slate at that moment ensures predictions use the freshest possible lineups,
which is the single largest source of avoidable prop misfires.

Usage (long-running daemon mode):
    python scripts/lineup_release_trigger.py [--date 2026-05-21] [--season 2024-25]

Design:
    - Tip-off times fetched from NBA ScoreboardV3 (gameTimeUTC field).
    - Trigger fires at  tipoff_utc - 30 minutes  for each game.
    - Calls run_daily_slate.main() in-process (no subprocess needed).
    - Logs each rerun to  data/output/lineup_trigger_<DATE>.log.
    - Fully injectable: pass `now_fn` + `games` kwargs to override for tests.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

# ── project path setup ────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "output")
_LOG_FMT = "%(asctime)s %(levelname)s [lineup_trigger] %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT)
log = logging.getLogger("lineup_release_trigger")

# Trigger window: fire this many minutes before tip-off
_PRE_TIP_MINUTES: int = 30

# Poll interval while waiting for the next trigger (seconds)
_POLL_INTERVAL_SECONDS: int = 60


# ── tip-off source ─────────────────────────────────────────────────────────────

def fetch_tipoff_times(date_str: str) -> List[dict]:
    """
    Fetch today's games with UTC tip-off times from NBA ScoreboardV3.

    Tip-off time source: ScoreboardV3.game_header['gameTimeUTC'] (ISO-8601 UTC).
    Falls back to ScoreboardV2 + a sentinel 19:00 ET if V3 is unavailable.

    Args:
        date_str: Game date in YYYY-MM-DD format.

    Returns:
        List of dicts, one per game::

            {
                "game_id":     str,       # e.g. "0022400561"
                "home_team":   str,       # 3-letter abbreviation
                "away_team":   str,
                "tipoff_utc":  datetime,  # timezone-aware UTC datetime
            }
    """
    games: List[dict] = []

    # Primary: ScoreboardV3 (has gameTimeUTC)
    try:
        from nba_api.stats.endpoints import scoreboardv3
        time.sleep(0.6)
        sb = scoreboardv3.ScoreboardV3(game_date=date_str, timeout=15)
        df = sb.game_header.get_data_frame()
        for _, row in df.iterrows():
            game_code = str(row.get("gameCode", ""))
            # GAMECODE format: YYYYMMDD/AWAYABBRHOMEABBR
            if "/" in game_code:
                teams = game_code.split("/", 1)[1]
                away = teams[:3]
                home = teams[3:6]
            else:
                away, home = "", ""

            raw_utc = str(row.get("gameTimeUTC", ""))
            try:
                # ISO-8601 with trailing Z: "2025-01-16T00:00:00Z"
                tipoff_utc = datetime.fromisoformat(raw_utc.replace("Z", "+00:00"))
            except Exception:
                log.warning("Could not parse gameTimeUTC=%r for %s", raw_utc, game_code)
                continue

            games.append({
                "game_id":    str(row.get("gameId", "")),
                "home_team":  home,
                "away_team":  away,
                "tipoff_utc": tipoff_utc,
            })

        if games:
            log.info("ScoreboardV3: %d games for %s", len(games), date_str)
            return games
    except Exception as exc:
        log.warning("ScoreboardV3 unavailable (%s); falling back to V2", exc)

    # Fallback: ScoreboardV2 — no per-game time, use 19:00 ET (midnight UTC) sentinel
    try:
        from nba_api.stats.endpoints import scoreboardv2
        time.sleep(0.6)
        sb2 = scoreboardv2.ScoreboardV2(game_date=date_str, timeout=15)
        df2 = sb2.game_header.get_data_frame()
        # Sentinel: 19:00 ET = 00:00 UTC next day; use game date at 00:00 UTC + 1 day
        # as a rough placeholder so the trigger still fires on the right calendar day.
        _fallback_utc = datetime.fromisoformat(date_str + "T00:00:00+00:00") + timedelta(hours=24)

        for _, row in df2.iterrows():
            gamecode = str(row.get("GAMECODE", ""))
            if "/" in gamecode:
                teams = gamecode.split("/", 1)[1]
                away, home = teams[:3], teams[3:6]
            else:
                away, home = "", ""
            games.append({
                "game_id":    str(row.get("GAME_ID", "")),
                "home_team":  home,
                "away_team":  away,
                "tipoff_utc": _fallback_utc,
            })
        log.info("ScoreboardV2 fallback: %d games (no tip-off times — using sentinel)", len(games))
    except Exception as exc:
        log.warning("ScoreboardV2 also failed: %s", exc)

    return games


# ── logging helper ─────────────────────────────────────────────────────────────

def _get_log_path(date_str: str) -> str:
    """Return path to the trigger log file for the given date."""
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    date_compact = date_str.replace("-", "")
    return os.path.join(_OUTPUT_DIR, f"lineup_trigger_{date_compact}.log")


def _append_log(log_path: str, game_id: str, ran_at: datetime) -> None:
    """Append one rerun record to the trigger log file."""
    line = f"{ran_at.isoformat()} game_id={game_id} rerun=run_daily_slate\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)
    log.info("Logged rerun: game_id=%s at %s", game_id, ran_at.isoformat())


# ── slate runner ───────────────────────────────────────────────────────────────

def _run_slate(date_str: str, season: str, game_id: str, run_slate_fn: Optional[Callable]) -> None:
    """Invoke run_daily_slate for one game (or the full slate for the date)."""
    log.info("Triggering slate rerun for date=%s game_id=%s", date_str, game_id)
    if run_slate_fn is not None:
        # Injectable override for tests
        run_slate_fn(date_str=date_str, game_id=game_id)
        return

    # Default: call run_daily_slate.main() in-process
    try:
        from scripts.run_daily_slate import main as _slate_main
        _slate_main(season=season, date_str=date_str)
    except Exception as exc:
        log.error("run_daily_slate.main() raised: %s", exc)


# ── core trigger loop ──────────────────────────────────────────────────────────

def run_trigger(
    date_str: str,
    season: str = "2024-25",
    *,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    games: Optional[List[dict]] = None,
    run_slate_fn: Optional[Callable] = None,
    poll_interval: int = _POLL_INTERVAL_SECONDS,
) -> int:
    """
    Wait and fire run_daily_slate exactly 30 min before each game's tip-off.

    This function blocks until all triggers for the day have fired.

    Args:
        date_str:      Game date (YYYY-MM-DD).
        season:        NBA season string (e.g. "2024-25").
        now_fn:        Injectable clock; returns timezone-aware UTC datetime.
                       Defaults to ``datetime.now(timezone.utc)``.  Override in
                       tests to simulate time passage without sleeping.
        games:         Injectable game list (list of dicts with game_id, home_team,
                       away_team, tipoff_utc).  If None, fetched from ScoreboardV3.
        run_slate_fn:  Optional callable(date_str, game_id) called instead of the
                       real run_daily_slate.main(); useful for unit tests.
        poll_interval: Seconds to sleep between polling cycles (default 60).

    Returns:
        Number of reruns fired.
    """
    if games is None:
        games = fetch_tipoff_times(date_str)

    if not games:
        log.warning("No games found for %s — nothing to trigger.", date_str)
        return 0

    # Build sorted list of (trigger_utc, game) — trigger = tipoff - 30 min
    pending = []
    for game in games:
        tipoff = game["tipoff_utc"]
        if tipoff.tzinfo is None:
            tipoff = tipoff.replace(tzinfo=timezone.utc)
        trigger_at = tipoff - timedelta(minutes=_PRE_TIP_MINUTES)
        pending.append({"trigger_at": trigger_at, "game": game, "fired": False})

    pending.sort(key=lambda x: x["trigger_at"])

    log.info(
        "Lineup trigger armed: %d games, first trigger at %s UTC",
        len(pending),
        pending[0]["trigger_at"].isoformat(),
    )

    log_path = _get_log_path(date_str)
    fired_count = 0

    while True:
        now = now_fn()
        all_done = True

        for item in pending:
            if item["fired"]:
                continue
            all_done = False
            if now >= item["trigger_at"]:
                g = item["game"]
                _run_slate(date_str, season, g["game_id"], run_slate_fn)
                _append_log(log_path, g["game_id"], now)
                item["fired"] = True
                fired_count += 1

        if all_done or all(item["fired"] for item in pending):
            break

        time.sleep(poll_interval)

    log.info("Lineup trigger complete: %d reruns fired, log=%s", fired_count, log_path)
    return fired_count


# ── CLI entry-point ────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    from datetime import date as _date

    ap = argparse.ArgumentParser(
        prog="lineup_release_trigger",
        description="Rerun daily slate 30 min before each game's tip-off.",
    )
    ap.add_argument("--date",   default=str(_date.today()), help="Game date YYYY-MM-DD")
    ap.add_argument("--season", default="2024-25",           help="NBA season (e.g. 2024-25)")
    args = ap.parse_args()

    run_trigger(date_str=args.date, season=args.season)


if __name__ == "__main__":
    main()
