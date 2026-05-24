"""live_game_poll.py — poll active NBA games and snapshot live state to JSON.

Cycle 88a (loop 5) — component 3 of the live in-game prediction stack.
Top sharp shops outperform pre-tip published lines by updating LIVE during
games (actual Q1 pace, foul trouble, blowout state, warmup injuries,
lineup confirmations). This poller is the data backbone that makes all of
those signals possible — it captures the canonical per-game state every N
seconds and writes one timestamped JSON per snapshot.

Output schema (per snapshot — `data/live/<game_id>_<unix_ts>.json`):

    {
      "game_id": "0022400123",
      "captured_at": "2026-05-24T19:42:18+00:00",
      "game_status": "PRE_GAME"|"LIVE"|"FINAL",
      "period": 2,
      "clock": "5:42",
      "home_team": "LAL",
      "away_team": "DEN",
      "home_score": 56,
      "away_score": 48,
      "players": [
        {"player_id": 203999, "name": "Nikola Jokic", "team": "DEN",
         "min": 14.5, "pts": 12, "reb": 4, "ast": 3,
         "fg3m": 2, "stl": 1, "blk": 0, "tov": 1, "pf": 2,
         "is_starter": true},
        ...
      ]
    }

Endpoints
---------
* `https://cdn.nba.com/static/json/liveData/boxscore/boxscore_<gid>.json`
  — single CDN request per game that returns game.gameStatus / period /
    gameClock + full per-player live stats. No auth, no rate-limit issues.
    Already used in production by `src/data/nba_stats.fetch_full_boxscore`.
* `scoreboardv2` (via `NBAStatsHTTP` raw HTTP) — the day's slate, so we
    know which `game_id`s to poll. Reused from `scripts/predict_slate.py`
    because the ScoreboardV2 wrapper has the known WinProbability KeyError.

Each poll tick issues 1 CDN request per active game (plus 1 scoreboard
request at startup), well within polite rate limits. `_API_SLEEP = 0.6`
between calls matches the convention established in `predict_slate.py`.

CLI
---
    python scripts/live_game_poll.py --once
    python scripts/live_game_poll.py --daemon --interval 30
    python scripts/live_game_poll.py --game-id 0022400123 --once
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, date as _date
from typing import Callable, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Header patch must run before any nba_api imports.
import src.data.nba_api_headers_patch  # noqa: F401, E402

_LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
_API_SLEEP = 0.6  # polite delay between live API calls (matches predict_slate)
_CDN_URL_TPL = (
    "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
)
_CDN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":  "application/json",
    "Referer": "https://www.nba.com/",
}

# NBA gameStatus integer → canonical status string.
_STATUS_MAP = {1: "PRE_GAME", 2: "LIVE", 3: "FINAL"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """UTC ISO-8601 timestamp with seconds precision + tz suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_int(v) -> int:
    try:
        return int(v) if v is not None else 0
    except (ValueError, TypeError):
        return 0


def _parse_minutes(v) -> float:
    """Convert 'PT14M30.00S' / '14:30' / 14.5 → decimal minutes."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        if s.startswith("PT") and "M" in s:
            s = s[2:]
            mins = float(s[: s.index("M")])
            secs = s[s.index("M") + 1:].rstrip("S")
            return round(mins + float(secs or 0) / 60, 2)
        if ":" in s:
            mm, ss = s.split(":", 1)
            return round(float(mm) + float(ss) / 60, 2)
        return round(float(s), 2)
    except (ValueError, TypeError):
        return 0.0


def _parse_clock(v) -> str:
    """Convert NBA ISO duration ('PT05M42.00S') to 'MM:SS' display string."""
    if not v:
        return ""
    s = str(v).strip()
    if s.startswith("PT") and "M" in s:
        try:
            body = s[2:]
            mins = int(float(body[: body.index("M")]))
            secs_part = body[body.index("M") + 1:].rstrip("S")
            secs = int(float(secs_part or 0))
            return f"{mins}:{secs:02d}"
        except (ValueError, TypeError):
            return s
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_boxscore_payload(payload: dict, captured_at: Optional[str] = None) -> dict:
    """Convert raw cdn.nba.com live boxscore JSON to the canonical snapshot.

    `payload` is the dict returned by the CDN endpoint (already json-decoded).
    Returns a snapshot dict whose schema is described in the module docstring.
    `captured_at` is injected so tests can pin the timestamp deterministically.
    """
    game = payload.get("game") or {}
    home = game.get("homeTeam") or {}
    away = game.get("awayTeam") or {}

    status_int = _safe_int(game.get("gameStatus"))
    status_str = _STATUS_MAP.get(status_int, "UNKNOWN")

    players: List[dict] = []
    for side, team_obj in (("home", home), ("away", away)):
        tricode = str(team_obj.get("teamTricode", "") or "")
        for p in team_obj.get("players", []) or []:
            st = p.get("statistics") or {}
            players.append({
                "player_id":  _safe_int(p.get("personId")),
                "name":       str(p.get("name", "") or ""),
                "team":       tricode,
                "min":        _parse_minutes(st.get("minutes")),
                "pts":        _safe_int(st.get("points")),
                "reb":        _safe_int(st.get("reboundsTotal")),
                "ast":        _safe_int(st.get("assists")),
                "fg3m":       _safe_int(st.get("threePointersMade")),
                "stl":        _safe_int(st.get("steals")),
                "blk":        _safe_int(st.get("blocks")),
                "tov":        _safe_int(st.get("turnovers")),
                "pf":         _safe_int(st.get("foulsPersonal")),
                "is_starter": bool(p.get("starter", False)),
            })

    return {
        "game_id":     str(game.get("gameId", "") or ""),
        "captured_at": captured_at or _now_iso(),
        "game_status": status_str,
        "period":      _safe_int(game.get("period")),
        "clock":       _parse_clock(game.get("gameClock")),
        "home_team":   str(home.get("teamTricode", "") or ""),
        "away_team":   str(away.get("teamTricode", "") or ""),
        "home_score":  _safe_int(home.get("score")),
        "away_score":  _safe_int(away.get("score")),
        "players":     players,
    }


# ─────────────────────────────────────────────────────────────────────────────
# I/O: fetch + persist
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_boxscore(game_id: str, *, timeout: float = 20.0) -> dict:
    """Hit cdn.nba.com for one game's live box score. Empty dict on error."""
    import requests as _req  # noqa: PLC0415
    url = _CDN_URL_TPL.format(game_id=game_id)
    try:
        resp = _req.get(url, headers=_CDN_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [warn] live boxscore fetch {game_id}: {e}")
        return {}


def snapshot_path(game_id: str, *, captured_at: Optional[str] = None,
                  live_dir: str = _LIVE_DIR) -> str:
    """Build a path like data/live/<game_id>_<unix_ts>.json.

    Uses a millisecond unix timestamp so multiple snapshots within the same
    second (rare but possible with --once across processes) don't collide.
    """
    if captured_at:
        try:
            dt = datetime.fromisoformat(captured_at)
            ts_ms = int(dt.timestamp() * 1000)
        except (ValueError, TypeError):
            ts_ms = int(time.time() * 1000)
    else:
        ts_ms = int(time.time() * 1000)
    return os.path.join(live_dir, f"{game_id}_{ts_ms}.json")


def write_snapshot(snapshot: dict, *, live_dir: str = _LIVE_DIR) -> str:
    """Persist a snapshot to data/live/<game_id>_<ts>.json. Returns the path."""
    game_id = snapshot.get("game_id") or "unknown"
    os.makedirs(live_dir, exist_ok=True)
    path = snapshot_path(game_id, captured_at=snapshot.get("captured_at"),
                          live_dir=live_dir)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Schedule discovery
# ─────────────────────────────────────────────────────────────────────────────

def discover_games_for_today(date_str: Optional[str] = None) -> List[str]:
    """Return the list of game_ids on the given date (default: today).

    Delegates to `scripts.predict_slate.fetch_games` so we share the
    proven raw-HTTP scoreboard workaround. Returns [] on failure.
    """
    date_str = date_str or _date.today().isoformat()
    try:
        from scripts.predict_slate import fetch_games  # noqa: PLC0415
    except Exception as e:
        print(f"  [warn] could not import fetch_games: {e}")
        return []
    games = fetch_games(date_str) or []
    return [str(g.get("game_id")) for g in games if g.get("game_id")]


# ─────────────────────────────────────────────────────────────────────────────
# Polling loop
# ─────────────────────────────────────────────────────────────────────────────

def poll_once(game_ids: List[str],
              *,
              fetch_fn: Callable[[str], dict] = fetch_live_boxscore,
              sleep_fn: Callable[[float], None] = time.sleep,
              api_sleep: float = _API_SLEEP,
              live_dir: str = _LIVE_DIR) -> Dict[str, dict]:
    """One pass: fetch + snapshot every game_id. Returns {game_id: snapshot}.

    Sleeps `api_sleep` between game fetches (politeness — established
    convention from predict_slate.py). Empty payloads are skipped silently.
    """
    out: Dict[str, dict] = {}
    for i, gid in enumerate(game_ids):
        if i > 0:
            sleep_fn(api_sleep)
        payload = fetch_fn(gid)
        if not payload or not payload.get("game"):
            continue
        snap = parse_boxscore_payload(payload)
        write_snapshot(snap, live_dir=live_dir)
        out[gid] = snap
    return out


def poll_daemon(game_ids: List[str],
                *,
                interval: float = 30.0,
                fetch_fn: Callable[[str], dict] = fetch_live_boxscore,
                sleep_fn: Callable[[float], None] = time.sleep,
                api_sleep: float = _API_SLEEP,
                live_dir: str = _LIVE_DIR,
                max_ticks: Optional[int] = None) -> int:
    """Continuous polling until every game is FINAL (or max_ticks reached).

    Drops a game from the active set after we record a FINAL snapshot for
    it — so a 12-game slate that finishes one game per hour gradually
    quiets down to zero requests/tick. Returns the number of ticks run.
    """
    active = list(game_ids)
    ticks = 0
    while active:
        if max_ticks is not None and ticks >= max_ticks:
            break
        ticks += 1
        results = poll_once(
            active, fetch_fn=fetch_fn, sleep_fn=sleep_fn,
            api_sleep=api_sleep, live_dir=live_dir,
        )
        # Drop FINAL games — they got their last snapshot in this tick.
        active = [gid for gid in active
                  if results.get(gid, {}).get("game_status") != "FINAL"]
        if not active:
            break
        sleep_fn(interval)
    return ticks


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Poll live NBA game state and snapshot per-game JSONs.")
    ap.add_argument("--once", action="store_true",
                    help="One poll pass across all (or --game-id) games, then exit.")
    ap.add_argument("--daemon", action="store_true",
                    help="Poll every --interval seconds until all games FINAL.")
    ap.add_argument("--interval", type=float, default=30.0,
                    help="Daemon poll interval in seconds (default 30).")
    ap.add_argument("--game-id", default=None,
                    help="Poll just this specific game_id instead of today's slate.")
    ap.add_argument("--date", default=None,
                    help="Scoreboard date YYYY-MM-DD (default: today). "
                         "Ignored when --game-id is set.")
    args = ap.parse_args()

    if not (args.once or args.daemon):
        # Default to --once if neither was passed (safer than spinning forever).
        args.once = True

    if args.game_id:
        game_ids = [args.game_id]
    else:
        game_ids = discover_games_for_today(args.date)

    if not game_ids:
        print("[live_game_poll] no games to poll.")
        return 0

    print(f"[live_game_poll] polling {len(game_ids)} game(s) "
          f"-> {_LIVE_DIR}", flush=True)

    # Resolve module-level names at call time so tests can monkeypatch
    # `fetch_live_boxscore` / `_LIVE_DIR` and have the changes take effect.
    if args.daemon:
        ticks = poll_daemon(game_ids, interval=args.interval,
                             fetch_fn=fetch_live_boxscore,
                             live_dir=_LIVE_DIR)
        print(f"[live_game_poll] daemon exit after {ticks} tick(s); "
              f"all games FINAL.")
    else:
        results = poll_once(game_ids,
                             fetch_fn=fetch_live_boxscore,
                             live_dir=_LIVE_DIR)
        for gid, snap in results.items():
            print(f"  {gid}  {snap['away_team']} @ {snap['home_team']}  "
                  f"{snap['game_status']:<8}  "
                  f"Q{snap['period']} {snap['clock']:<5}  "
                  f"{snap['away_score']}-{snap['home_score']}  "
                  f"({len(snap['players'])} players)")
        print(f"[live_game_poll] wrote {len(results)} snapshot(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
