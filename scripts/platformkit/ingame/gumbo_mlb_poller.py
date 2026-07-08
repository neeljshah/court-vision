"""scripts.platformkit.ingame.gumbo_mlb_poller -- STANDALONE MLB GUMBO live poller (LANE 2).

Bootstrap-then-diffPatch poller: for each live game on the day's schedule, GET the
bootstrap `feed/live` snapshot once, cache metaData.timeStamp, then steady-state poll
`feed/live/diffPatch?startTimecode=<ts>` and append one extracted tick per pass to
data/domains/mlb/gumbo_live/<gamePk>.jsonl.

LIVE CADENCE (latency-audit fix, 2026-07-07): while >=1 game is live, run_live_window()
fast-polls at CV_GUMBO_LIVE_SEC (default 10s, hard floor 5s) using diffPatch deltas, with
exponential backoff (cap 60s) on all-error passes. Idle behavior is unchanged (the m37
runner's 30s tick). Each row now also carries `captured_at` (our poll receive time, ISO
UTC) alongside `ts` (MLB's own metaData.timeStamp event wall-clock) -- additive key only,
existing schema/keys byte-identical. One shared HTTP session (keep-alive) for all fetches.

Disk growth at 10s live cadence: ~4-5x today's 104-247 rows/game -> ~400-1,200 rows/game,
~350 bytes/row => <=0.5 MB/game, ~3-7 MB/day on a full 15-game slate. sidecar_retention's
gumbo_live policy (30d active + 1 GiB byte budget) absorbs this >5x growth with ~150x
headroom -- existing rotation handles it, no policy change needed.

STANDALONE (per this wave's binding invariant): does NOT touch inplay_capture_loop.py or
any shared runner. Bounded via --once (one pass over all live games, then exit) -- there is
no unbounded default loop entrypoint here; --once is the only mode this module implements.

Politeness: plain urllib + a descriptive User-Agent (statsapi.mlb.com verified keyless, no
auth/stealth needed); ~1s pacing between per-game requests; short timeouts; every game's
fetch is error-isolated (one bad game/network blip never stops the others or crashes the
pass).

Sidecar state file data/domains/mlb/gumbo_live/_poller_state.json remembers each gamePk's
last timeStamp + a copy of the last full snapshot (for diffPatch application) across runs.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/ingame/test_gumbo_mlb_poller.py -q
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame.ingame_gumbo_mlb import extract_state
from scripts.platformkit.ingame.ingame_gumbo_mlb_patch import apply_diffpatch_response

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live"
DEFAULT_STATE_FILE = DEFAULT_OUT_DIR / "_poller_state.json"

_UA = "CourtVision-research/1.0 (contact: neeljshah22@gmail.com)"
_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
_BOOTSTRAP_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
_DIFFPATCH_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live/diffPatch?startTimecode={ts}"

FetchFn = Callable[[str], Any]

_SESSION: Optional[Any] = None  # one shared keep-alive session for ALL statsapi fetches


def live_cadence_sec() -> float:
    """Live-game poll cadence from CV_GUMBO_LIVE_SEC (default 10s), politeness floor 5s."""
    try:
        v = float(os.environ.get("CV_GUMBO_LIVE_SEC", "") or 10.0)
    except ValueError:
        v = 10.0
    return max(5.0, v)


def _http_get_json(url: str, timeout: float = 15.0) -> Optional[Any]:
    """GET url via one shared requests.Session (keep-alive), return parsed JSON or None
    on any network/HTTP/JSON error (never raises). Falls back to plain urllib if the
    requests import itself is unavailable."""
    global _SESSION
    try:
        if _SESSION is None:
            import requests
            _SESSION = requests.Session()
            _SESSION.headers["User-Agent"] = _UA
        resp = _SESSION.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except ImportError:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            logger.warning("gumbo_mlb_poller GET failed url=%s: %s", url, exc)
            return None
    except Exception as exc:  # noqa: BLE001 -- fetch failures degrade to None, never raise
        logger.warning("gumbo_mlb_poller GET failed url=%s: %s", url, exc)
        return None


def list_live_game_pks(date_str: Optional[str] = None,
                        fetch_fn: FetchFn = _http_get_json) -> List[Dict[str, Any]]:
    """Return [{game_pk, status, away, home}, ...] for games "In Progress" on date_str
    (default: the MLB "baseball date" -- UTC minus 10h, so the slate date rolls at
    ~5-6am ET after the last west-coast game, NOT at 00:00 UTC. The old today-UTC
    default went blind every evening at 7-8pm CT: past midnight UTC it queried
    tomorrow's all-Preview slate and found 0 live games while 12 were in progress).
    Uses the schedule endpoint; never raises."""
    date_str = date_str or (
        datetime.now(timezone.utc) - timedelta(hours=10)).strftime("%Y-%m-%d")
    data = fetch_fn(_SCHEDULE_URL.format(date=date_str))
    if not isinstance(data, dict):
        return []
    out: List[Dict[str, Any]] = []
    for d in data.get("dates", []) or []:
        for g in d.get("games", []) or []:
            status = (g.get("status", {}) or {}).get("detailedState", "")
            if status != "In Progress":
                continue
            teams = g.get("teams", {}) or {}
            out.append({
                "game_pk": g.get("gamePk"),
                "status": status,
                "away": (teams.get("away", {}).get("team", {}) or {}).get("name"),
                "home": (teams.get("home", {}).get("team", {}) or {}).get("name"),
            })
    return out


def _load_poller_state(state_file: Path) -> Dict[str, Any]:
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _save_poller_state(state_file: Path, state: Dict[str, Any]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state), encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True))
        f.write("\n")


def poll_one_game(game_pk: int, poller_state: Dict[str, Any],
                   fetch_fn: FetchFn = _http_get_json) -> Optional[Dict[str, Any]]:
    """Bootstrap-or-diffPatch one game, returning the extracted tick dict (or None on a
    clean skip: no usable snapshot yet). Mutates poller_state[str(game_pk)] in place with
    the new {ts, snapshot} for the next pass. Never raises -- a bad payload -> None."""
    key = str(game_pk)
    prior = poller_state.get(key)
    full: Optional[Dict[str, Any]] = None

    if not prior or not prior.get("ts"):
        full = fetch_fn(_BOOTSTRAP_URL.format(game_pk=game_pk))
    else:
        resp = fetch_fn(_DIFFPATCH_URL.format(game_pk=game_pk, ts=prior["ts"]))
        if resp is not None:
            full = apply_diffpatch_response(prior.get("snapshot"), resp)
        if full is None:
            full = fetch_fn(_BOOTSTRAP_URL.format(game_pk=game_pk))  # fallback re-fetch

    if not isinstance(full, dict) or "liveData" not in full:
        return None

    ts = full.get("metaData", {}).get("timeStamp") if isinstance(full.get("metaData"), dict) else None
    poller_state[key] = {"ts": ts, "snapshot": full}

    tick = extract_state(full)
    return tick or None


def run_once(date_str: Optional[str] = None,
             out_dir: Path = DEFAULT_OUT_DIR,
             state_file: Path = DEFAULT_STATE_FILE,
             fetch_fn: FetchFn = _http_get_json,
             sleep_fn: Callable[[float], None] = time.sleep,
             pace_sec: float = 1.0) -> Dict[str, Any]:
    """One bounded pass: list live games, poll each once, append a tick row per success.

    Returns a report dict {n_live_games, n_rows_written, game_pks, errors}. Error-isolated
    per game (one bad game never stops the pass). ~pace_sec between games (politeness)."""
    games = list_live_game_pks(date_str, fetch_fn=fetch_fn)
    poller_state = _load_poller_state(state_file)
    report: Dict[str, Any] = {"n_live_games": len(games), "n_rows_written": 0,
                               "game_pks": [], "errors": []}

    for i, g in enumerate(games):
        gp = g.get("game_pk")
        if gp is None:
            continue
        if i > 0:
            sleep_fn(pace_sec)
        try:
            tick = poll_one_game(gp, poller_state, fetch_fn=fetch_fn)
        except Exception as exc:  # noqa: BLE001 -- one bad game must never kill the pass
            report["errors"].append("%s: %s" % (gp, exc))
            continue
        report["game_pks"].append(gp)
        if tick:
            # captured_at = OUR poll receive time (UTC); `ts` stays MLB's own
            # metaData.timeStamp event wall-clock. Additive key, schema otherwise
            # byte-identical (closes the latency audit's "true event time" gap).
            tick["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _append_jsonl(out_dir / ("%s.jsonl" % gp), tick)
            report["n_rows_written"] += 1

    _save_poller_state(state_file, poller_state)
    return report


def run_live_window(window_sec: float,
                    date_str: Optional[str] = None,
                    out_dir: Path = DEFAULT_OUT_DIR,
                    state_file: Path = DEFAULT_STATE_FILE,
                    fetch_fn: FetchFn = _http_get_json,
                    sleep_fn: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.monotonic,
                    cadence_sec: Optional[float] = None) -> Dict[str, Any]:
    """Fast-poll live games every ~live_cadence_sec() for one window of window_sec.

    Meant to be called for the m37 runner's inter-tick wait, right AFTER a run_once pass
    already fired -- so it waits one cadence FIRST, then passes. Behavior:
      * a pass finding 0 live games -> plain-sleep the remaining window and stop (idle
        cadence unchanged; the runner's own 30s tick governs when idle);
      * a pass with live games but 0 rows written (fetch/extract failures) -> exponential
        backoff (cadence * 2^k, capped 60s), reset on any successful row;
      * cadence has a hard 5s politeness floor (live_cadence_sec()).
    Returns {passes, rows_written, window_sec, cadence_sec}. Never hammers, never raises
    beyond what run_once already isolates."""
    cad = max(5.0, float(cadence_sec) if cadence_sec else live_cadence_sec())
    start = clock()
    passes = 0
    rows = 0
    fails = 0
    while True:
        wait = min(cad * (2 ** fails), 60.0)
        remaining = window_sec - (clock() - start)
        if remaining < wait + 1.0:
            if remaining > 0:
                sleep_fn(remaining)
            break
        sleep_fn(wait)
        report = run_once(date_str=date_str, out_dir=out_dir, state_file=state_file,
                          fetch_fn=fetch_fn, sleep_fn=sleep_fn)
        passes += 1
        rows += report["n_rows_written"]
        if report["n_live_games"] <= 0:
            remaining = window_sec - (clock() - start)
            if remaining > 0:
                sleep_fn(remaining)
            break
        fails = 0 if report["n_rows_written"] > 0 else fails + 1
    return {"passes": passes, "rows_written": rows,
            "window_sec": window_sec, "cadence_sec": cad}


if __name__ == "__main__":  # pragma: no cover -- CLI smoke, not exercised by tests
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True,
                         help="process one bounded pass over today's live games and exit")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC)")
    args = parser.parse_args()
    rep = run_once(date_str=args.date)
    print(json.dumps(rep, indent=2))
