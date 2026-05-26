"""game_tip_detector.py — resolves scheduled tip-off time for a game and
exposes ``is_pregame(game_id)`` so the live bet ranker (R16_E2) can
transition out of pregame surfacing the moment a game tips.

Resolution order for ``get_tip_time(game_id)``:
  1. Cached JSON at ``data/cache/tip_times_<YYYY-MM-DD>.json`` keyed by
     ``game_id`` (cheap, populated by ``write_today_tip_cache``).
  2. The season-schedule JSON ``data/nba/season_games_2025-26.json``
     if a ``tip_time`` / ``game_time`` field is present.
  3. NBA Stats ``scoreboardv2`` GameHeader for the game_date — parses
     the ``GAME_STATUS_TEXT`` field (e.g. ``"8:30 pm ET"``) into a UTC
     ``datetime``.
  4. Fixed default: 8:30 PM ET on the game_date (covers playoff games
     not yet in the schedule cache).

``is_pregame(game_id)`` returns True when:
  * No ``data/cache/quarter_box/<game_id>_q1.json`` exists AND
  * ``utcnow < tip_time + GRACE_MINUTES``.

A 5-minute grace period absorbs scoreboard-time drift / late tips so
the ranker doesn't prematurely flip to in-play mode.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

logger = logging.getLogger("game_tip_detector")

GRACE_MINUTES = 5  # absorb late tips / scoreboard time drift
DEFAULT_TIP_HOUR_ET = 20  # 8 PM ET — playoff prime-time default
DEFAULT_TIP_MIN_ET = 30   # :30 — Game 7 WCF is 8:30 PM ET
SEASON_SCHEDULE = os.path.join(
    PROJECT_DIR, "data", "nba", "season_games_2025-26.json"
)
QBOX_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
TIP_CACHE_TEMPLATE = os.path.join(
    PROJECT_DIR, "data", "cache", "tip_times_{date}.json"
)


# ---------- timezone helpers ----------
def _et_to_utc(year: int, month: int, day: int, hour: int, minute: int
               ) -> datetime:
    """Convert an Eastern-time wall-clock to UTC.

    Tries zoneinfo first (handles DST automatically) and falls back to
    a fixed-offset heuristic (EDT=UTC-4 March-Nov, EST=UTC-5 Nov-March)
    if tzdata is unavailable in the runtime.
    """
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        local = datetime(year, month, day, hour, minute, tzinfo=et)
        return local.astimezone(timezone.utc)
    except Exception:
        # Heuristic: roughly DST from second Sunday of March through
        # first Sunday of November. Good enough for live betting.
        offset_hours = 4 if 3 <= month <= 11 else 5
        # March/November edges: be conservative — May (5) is solidly EDT.
        if month == 3 and day < 10:
            offset_hours = 5
        if month == 11 and day > 1:
            offset_hours = 5
        naive = datetime(year, month, day, hour, minute)
        return (naive + timedelta(hours=offset_hours)).replace(
            tzinfo=timezone.utc
        )


# ---------- schedule lookup ----------
def _load_schedule_row(game_id: str) -> Optional[dict]:
    if not os.path.exists(SEASON_SCHEDULE):
        return None
    try:
        with open(SEASON_SCHEDULE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("schedule load failed: %s", e)
        return None
    rows = data.get("rows") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return None
    for r in rows:
        if str(r.get("game_id")) == str(game_id):
            return r
    return None


def _tip_from_schedule(row: dict) -> Optional[datetime]:
    """Return a UTC datetime if the schedule row carries a tip time."""
    if not row:
        return None
    # Accept several common field names.
    for fld in ("tip_time_utc", "game_time_utc", "tipTimeUTC",
                "gameTimeUTC"):
        v = row.get(fld)
        if v:
            try:
                return datetime.fromisoformat(
                    str(v).replace("Z", "+00:00")
                ).astimezone(timezone.utc)
            except Exception:
                continue
    # Accept "8:30 PM ET" style strings paired with a game_date.
    txt = row.get("tip_time") or row.get("game_time")
    game_date = row.get("game_date")
    if txt and game_date:
        parsed = _parse_et_clock(str(txt), str(game_date))
        if parsed is not None:
            return parsed
    return None


# ---------- scoreboard fallback ----------
_ET_CLOCK_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*(am|pm)\s*ET\s*$", re.IGNORECASE
)


def _parse_et_clock(text: str, game_date: str) -> Optional[datetime]:
    """Parse ``"8:30 pm ET"`` + ``"2026-05-26"`` -> UTC datetime."""
    m = _ET_CLOCK_RE.match(text)
    if not m:
        return None
    h = int(m.group(1)) % 12
    if m.group(3).lower() == "pm":
        h += 12
    mn = int(m.group(2))
    try:
        y, mo, d = (int(x) for x in game_date.split("-"))
    except Exception:
        return None
    return _et_to_utc(y, mo, d, h, mn)


def _tip_from_scoreboard(game_id: str, game_date: str
                          ) -> Optional[datetime]:
    """Hit NBA scoreboardv2 for ``game_date`` and pull ``GAME_STATUS_TEXT``
    for ``game_id``."""
    try:
        import src.data.nba_api_headers_patch  # noqa: F401
        from nba_api.stats.library.http import NBAStatsHTTP
    except Exception as e:
        logger.debug("nba_api unavailable: %s", e)
        return None
    try:
        resp = NBAStatsHTTP().send_api_request(
            endpoint="scoreboardv2",
            parameters={
                "GameDate": game_date,
                "LeagueID": "00",
                "DayOffset": 0,
            },
        )
        data = resp.get_dict()
    except Exception as e:
        logger.warning("scoreboard fetch failed: %s", e)
        return None
    rs = data.get("resultSets") or data.get("resultSet") or []
    gh = next((s for s in rs if s.get("name") == "GameHeader"), None)
    if not gh:
        return None
    headers = gh.get("headers") or []
    try:
        gid_idx = headers.index("GAME_ID")
        status_idx = headers.index("GAME_STATUS_TEXT")
    except ValueError:
        return None
    for row in gh.get("rowSet") or []:
        if str(row[gid_idx]) == str(game_id):
            return _parse_et_clock(str(row[status_idx] or ""), game_date)
    return None


# ---------- default ----------
def _default_tip(game_date: str) -> Optional[datetime]:
    """Default to 8:30 PM ET on the supplied date."""
    try:
        y, mo, d = (int(x) for x in game_date.split("-"))
    except Exception:
        return None
    return _et_to_utc(y, mo, d, DEFAULT_TIP_HOUR_ET, DEFAULT_TIP_MIN_ET)


# ---------- public API ----------
def _load_tip_cache(game_date: str) -> dict:
    path = TIP_CACHE_TEMPLATE.format(date=game_date)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_tip_time(game_id: str, game_date: Optional[str] = None
                  ) -> Optional[datetime]:
    """Resolve scheduled tip-off (UTC) for ``game_id``. Returns None
    only if no fallback (incl. default) could be applied — practically
    never None when ``game_date`` is known.
    """
    row = _load_schedule_row(game_id)
    if game_date is None and row is not None:
        game_date = row.get("game_date")

    # 1. tip-time cache (if today's cache is populated)
    if game_date:
        cache = _load_tip_cache(game_date)
        entry = cache.get(str(game_id))
        if entry:
            try:
                return datetime.fromisoformat(
                    str(entry).replace("Z", "+00:00")
                ).astimezone(timezone.utc)
            except Exception:
                pass

    # 2. schedule json
    tip = _tip_from_schedule(row) if row else None
    if tip is not None:
        return tip

    # 3. scoreboardv2
    if game_date:
        tip = _tip_from_scoreboard(game_id, game_date)
        if tip is not None:
            return tip

    # 4. default 8:30 PM ET
    if game_date:
        return _default_tip(game_date)
    return None


def quarter_box_exists(game_id: str) -> bool:
    """Return True iff ``data/cache/quarter_box/<game_id>_q1.json`` (or
    any q1 file containing the game_id) exists."""
    if not os.path.isdir(QBOX_DIR):
        return False
    for fn in os.listdir(QBOX_DIR):
        if str(game_id) in fn and fn.endswith("_q1.json"):
            return True
    return False


def is_pregame(game_id: str, game_date: Optional[str] = None,
                now: Optional[datetime] = None) -> bool:
    """Return True iff the game has not yet tipped.

    A game is considered IN-PLAY when either condition holds:
      * a q1 quarter_box file for the game exists, OR
      * the current UTC time is past ``tip_time + GRACE_MINUTES``.
    """
    if quarter_box_exists(game_id):
        return False
    tip = get_tip_time(game_id, game_date=game_date)
    if tip is None:
        # Without a tip estimate we conservatively keep surfacing
        # pregame bets — but only until the q1 box appears.
        return True
    now = now or datetime.now(timezone.utc)
    return now < (tip + timedelta(minutes=GRACE_MINUTES))


def write_today_tip_cache(game_date: str, game_ids: list[str]
                            ) -> str:
    """Resolve and cache tip-times for the supplied game IDs. Writes
    ``data/cache/tip_times_<game_date>.json``. Returns the path."""
    path = TIP_CACHE_TEMPLATE.format(date=game_date)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = {}
    for gid in game_ids:
        tip = get_tip_time(gid, game_date=game_date)
        if tip is not None:
            out[str(gid)] = tip.isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    return path


# ---------- in-play handoff stub ----------
def in_play_quarter(game_id: str) -> Optional[str]:
    """Return the most-recent quarter file present for ``game_id``
    (``"q1"`` / ``"q2"`` / ...) or None if no quarter file is on disk
    yet. Used by ``live_bet_ranker`` to decide which end-of-quarter
    win-probability model (R10_M5 / R12_F1) to invoke next."""
    if not os.path.isdir(QBOX_DIR):
        return None
    seen = set()
    for fn in os.listdir(QBOX_DIR):
        if str(game_id) in fn and fn.endswith(".json"):
            m = re.search(r"_q(\d)\.json$", fn)
            if m:
                seen.add(f"q{m.group(1)}")
    if not seen:
        return None
    return sorted(seen)[-1]


if __name__ == "__main__":
    # CLI: python scripts/game_tip_detector.py <game_date> <game_id> [...]
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True,
                    help="game date YYYY-MM-DD")
    ap.add_argument("--game-ids", nargs="+", required=True)
    args = ap.parse_args()
    path = write_today_tip_cache(args.date, args.game_ids)
    print(f"[tip-detector] cached {len(args.game_ids)} tip-times -> {path}")
    for gid in args.game_ids:
        tip = get_tip_time(gid, game_date=args.date)
        pre = is_pregame(gid, game_date=args.date)
        print(f"  {gid}: tip={tip}  pregame={pre}")
