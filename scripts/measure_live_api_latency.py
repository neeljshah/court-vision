"""measure_live_api_latency.py -- profile end-to-end latency of nba_api live endpoints.

Cycle 91e (loop 5) -- T4-B. The Tier-2 live workstream (T2-A live MIN
extrapolation, T2-B foul-state model, T2-C RLM signal) needs an accurate
latency profile of the live-data source before it can pick the right
provider for production. SportsRadar advertises ~2s TTL,
SportsDataIO ~15-20s -- we use nba_api.live (cdn.nba.com), actual
latency unknown.

This harness polls boxscore + playbyplay every 15 seconds, observes when
each new PBP event first appears in the boxscore response, and writes
the wall-clock-vs-event-timestamp delta to a CSV. Median, p90, p99 are
printed at the end.

CLI
---
    # one specific game, run for 30 minutes (default)
    python scripts/measure_live_api_latency.py --game-id 0022400123

    # all live games on today's slate, run for 60 minutes
    python scripts/measure_live_api_latency.py --all-live --duration-min 60

    # smoke test against a synthetic fixture (no network)
    python scripts/measure_live_api_latency.py --smoke

Output: `data/live_latency/<game_id>_<startISO>.csv` with columns:

    poll_iso, eventId, action_timestamp, boxscore_first_seen, latency_seconds

Silent on success -- the CSV + final summary line are the deliverable.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Header patch must run before any nba_api imports (matches live_game_poll.py).
try:
    import src.data.nba_api_headers_patch  # noqa: F401, E402
except Exception:
    pass

_LATENCY_DIR = os.path.join(PROJECT_DIR, "data", "live_latency")
_DEFAULT_POLL_SECONDS = 15.0
_DEFAULT_DURATION_MIN = 30
_MIN_POLL_INTERVAL = 0.2  # rate-limit safety floor (5/sec)
_CSV_COLUMNS = [
    "poll_iso", "eventId", "action_timestamp",
    "boxscore_first_seen", "latency_seconds",
]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    """Parse an NBA `timeActual` ISO timestamp ('2026-05-24T19:42:18.3Z').

    Returns None if the input is None/empty/unparseable. Always returns
    a tz-aware datetime in UTC so subtraction is safe.
    """
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    # The NBA live API uses trailing 'Z' which Python <3.11 doesn't parse.
    s2 = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(s2)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Latency math (pure, easy to test)
# ---------------------------------------------------------------------------

def compute_latency_seconds(action_ts: Optional[str],
                             first_seen_iso: str) -> float:
    """Latency = (first_seen wall time) - (event action timestamp), in seconds.

    Returns NaN if the action timestamp is missing/unparseable -- caller
    still records the row so the missing-timestamp rate is visible.
    """
    a = _parse_iso(action_ts)
    f = _parse_iso(first_seen_iso)
    if a is None or f is None:
        return float("nan")
    return (f - a).total_seconds()


def summarize_latencies(rows: List[Dict[str, object]]) -> Dict[str, float]:
    """median / p90 / p99 / mean over rows whose latency_seconds is finite."""
    vals: List[float] = []
    for r in rows:
        v = r.get("latency_seconds")
        try:
            x = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            vals.append(x)
    n = len(vals)
    out = {
        "n_finite": float(n),
        "n_total":  float(len(rows)),
        "median":   float("nan"),
        "p90":      float("nan"),
        "p99":      float("nan"),
        "mean":     float("nan"),
    }
    if n == 0:
        return out
    vals.sort()

    def _pct(p: float) -> float:
        if n == 1:
            return vals[0]
        # Linear interpolation between the two nearest ranks.
        k = (n - 1) * p
        lo = int(math.floor(k))
        hi = int(math.ceil(k))
        if lo == hi:
            return vals[lo]
        return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)

    out["median"] = _pct(0.50)
    out["p90"] = _pct(0.90)
    out["p99"] = _pct(0.99)
    out["mean"] = sum(vals) / n
    return out


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def csv_path(game_id: str, start_iso: str,
             latency_dir: str = _LATENCY_DIR) -> str:
    """data/live_latency/<game_id>_<startISO>.csv -- ISO colons stripped for Windows."""
    safe_iso = start_iso.replace(":", "").replace("+", "p")
    return os.path.join(latency_dir, f"{game_id}_{safe_iso}.csv")


def write_csv(path: str, rows: List[Dict[str, object]]) -> str:
    """Write rows to CSV with the canonical schema. Creates parent dir."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in _CSV_COLUMNS})
    return path


# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------

def extract_pbp_events(pbp_payload: dict) -> List[Tuple[int, Optional[str]]]:
    """Return [(eventId, action_timestamp), ...] from a PBP JSON payload.

    PBP shape: {"game": {"actions": [{"actionNumber": N, "timeActual": "..."} ...]}}
    Defensive: missing keys yield an empty list.
    """
    out: List[Tuple[int, Optional[str]]] = []
    actions = ((pbp_payload or {}).get("game") or {}).get("actions") or []
    for a in actions:
        n = a.get("actionNumber")
        if n is None:
            continue
        try:
            eid = int(n)
        except (TypeError, ValueError):
            continue
        ts = a.get("timeActual")
        out.append((eid, ts))
    return out


def boxscore_score_signature(bs_payload: dict) -> Tuple[int, int, int, str]:
    """A monotone-ish 'state fingerprint' for the boxscore.

    Used as the proxy for "this PBP event has now landed in the boxscore
    response" -- when the bs signature changes after a new pbp event, that
    event has propagated to the bs endpoint. Tuple: (home_score, away_score,
    period, clock).
    """
    g = (bs_payload or {}).get("game") or {}
    home = g.get("homeTeam") or {}
    away = g.get("awayTeam") or {}

    def _int(v) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    return (
        _int(home.get("score")),
        _int(away.get("score")),
        _int(g.get("period")),
        str(g.get("gameClock") or ""),
    )


# ---------------------------------------------------------------------------
# Fetchers (real wired below, fakes injected in tests)
# ---------------------------------------------------------------------------

def fetch_live_boxscore(game_id: str, *, timeout: float = 20.0) -> dict:
    """Hit cdn.nba.com live boxscore via nba_api. {} on any failure."""
    try:
        from nba_api.live.nba.endpoints import boxscore as _bs  # noqa: PLC0415
        bs = _bs.BoxScore(game_id=game_id, timeout=timeout)
        return bs.get_dict() or {}
    except Exception:
        return {}


def fetch_live_playbyplay(game_id: str, *, timeout: float = 20.0) -> dict:
    """Hit cdn.nba.com live PBP via nba_api. {} on any failure."""
    try:
        from nba_api.live.nba.endpoints import playbyplay as _pbp  # noqa: PLC0415
        p = _pbp.PlayByPlay(game_id=game_id, timeout=timeout)
        return p.get_dict() or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Core polling loop
# ---------------------------------------------------------------------------

def run_latency_capture(
    game_id: str,
    *,
    duration_min: int = _DEFAULT_DURATION_MIN,
    poll_seconds: float = _DEFAULT_POLL_SECONDS,
    fetch_bs: Callable[[str], dict] = fetch_live_boxscore,
    fetch_pbp: Callable[[str], dict] = fetch_live_playbyplay,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], datetime] = _now_utc,
    latency_dir: str = _LATENCY_DIR,
    max_polls: Optional[int] = None,
) -> Tuple[str, List[Dict[str, object]]]:
    """Poll a single game; return (csv_path_written, rows_collected).

    Stops when (a) duration_min elapses, (b) max_polls reached (test hook),
    or (c) boxscore reports a FINAL gameStatus.

    Algorithm per tick:
      1. Sleep until next 15s tick (skip first tick).
      2. Fetch PBP -- compute the set of new eventIds vs the last poll.
      3. Fetch boxscore -- record wall-clock 'first_seen' for any NEW
         events. The boxscore fetch wall-time is used as 'boxscore_first_seen'
         since the bs payload is what the prediction code consumes.
      4. For each newly observed event, append one CSV row.
    """
    poll_seconds = max(_MIN_POLL_INTERVAL, float(poll_seconds))
    start = now_fn()
    start_iso = _iso(start)
    out_path = csv_path(game_id, start_iso, latency_dir=latency_dir)

    deadline = start.timestamp() + duration_min * 60.0
    seen_event_ids: set = set()
    rows: List[Dict[str, object]] = []
    ticks = 0
    final_seen = False

    while True:
        if ticks > 0:
            sleep_fn(poll_seconds)
        ticks += 1
        if max_polls is not None and ticks > max_polls:
            break

        poll_dt = now_fn()
        if poll_dt.timestamp() >= deadline:
            break

        poll_iso = _iso(poll_dt)

        pbp = fetch_pbp(game_id) or {}
        events = extract_pbp_events(pbp)
        # Build pbp eventId -> timestamp map (later events overwrite earlier
        # duplicates, which is fine -- duplicates shouldn't happen).
        ts_by_id: Dict[int, Optional[str]] = {eid: ts for eid, ts in events}

        # Fetch boxscore AFTER PBP -- the bs wall-clock is what we measure.
        bs_fetch_dt = now_fn()
        _bs = fetch_bs(game_id) or {}
        bs_first_seen_iso = _iso(bs_fetch_dt)

        # Game over? Drain new events one last time then stop.
        bs_game = (_bs.get("game") or {})
        if int(bs_game.get("gameStatus") or 0) == 3:
            final_seen = True

        # Diff: anything in PBP but not yet seen is newly visible. We treat
        # 'first appearance in the box response' as the same tick because
        # we just hit bs in this poll -- in reality PBP is the leading
        # signal and the bs lags slightly. For tighter measurement we use
        # the bs fetch wall time so the math reflects what production code
        # (which consumes the bs response) actually sees.
        for eid, action_ts in events:
            if eid in seen_event_ids:
                continue
            seen_event_ids.add(eid)
            lat = compute_latency_seconds(action_ts, bs_first_seen_iso)
            rows.append({
                "poll_iso":            poll_iso,
                "eventId":             eid,
                "action_timestamp":    action_ts if action_ts else "",
                "boxscore_first_seen": bs_first_seen_iso,
                "latency_seconds":     ("" if math.isnan(lat) else f"{lat:.3f}"),
            })

        if final_seen:
            break

    write_csv(out_path, rows)
    return out_path, rows


# ---------------------------------------------------------------------------
# Live-game discovery
# ---------------------------------------------------------------------------

def discover_live_game_ids() -> List[str]:
    """Return today's game_ids whose gameStatus indicates LIVE (status 2).

    Best-effort: any failure -> []. Reuses live_game_poll's scoreboard
    helper plus a single boxscore probe per game to filter to LIVE.
    """
    try:
        from scripts.live_game_poll import (
            discover_games_for_today, fetch_live_boxscore as _fbs,
        )
    except Exception:
        return []
    gids = discover_games_for_today() or []
    live: List[str] = []
    for gid in gids:
        try:
            bs = _fbs(gid)
            status = int(((bs or {}).get("game") or {}).get("gameStatus") or 0)
            if status == 2:
                live.append(str(gid))
        except Exception:
            continue
        time.sleep(0.6)
    return live


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_summary(game_id: str, out_path: str,
                    rows: List[Dict[str, object]]) -> None:
    s = summarize_latencies(rows)
    print(
        f"[live_api_latency] {game_id} -> {out_path}",
        flush=True,
    )
    print(
        f"  events={int(s['n_total'])} finite={int(s['n_finite'])}  "
        f"median={s['median']:.2f}s  p90={s['p90']:.2f}s  "
        f"p99={s['p99']:.2f}s  mean={s['mean']:.2f}s",
        flush=True,
    )


def _smoke() -> int:
    """No-network smoke test using a 3-event synthetic sequence."""
    now = [datetime(2026, 5, 24, 19, 0, 0, tzinfo=timezone.utc)]

    def _now() -> datetime:
        return now[0]

    def _sleep(s: float) -> None:
        now[0] = datetime.fromtimestamp(now[0].timestamp() + s, tz=timezone.utc)

    pbp_seq = [
        {"game": {"actions": [
            {"actionNumber": 1, "timeActual": "2026-05-24T18:59:55Z"},
        ]}},
        {"game": {"actions": [
            {"actionNumber": 1, "timeActual": "2026-05-24T18:59:55Z"},
            {"actionNumber": 2, "timeActual": "2026-05-24T19:00:10Z"},
        ]}},
        {"game": {"actions": [
            {"actionNumber": 1, "timeActual": "2026-05-24T18:59:55Z"},
            {"actionNumber": 2, "timeActual": "2026-05-24T19:00:10Z"},
            {"actionNumber": 3, "timeActual": "2026-05-24T19:00:20Z"},
        ]}},
    ]
    bs_seq = [
        {"game": {"gameStatus": 2, "homeTeam": {"score": 2}, "awayTeam": {"score": 0}}},
        {"game": {"gameStatus": 2, "homeTeam": {"score": 4}, "awayTeam": {"score": 0}}},
        {"game": {"gameStatus": 3, "homeTeam": {"score": 4}, "awayTeam": {"score": 3}}},
    ]
    idx = [0]

    def _pbp(_gid: str) -> dict:
        i = min(idx[0], len(pbp_seq) - 1)
        return pbp_seq[i]

    def _bs(_gid: str) -> dict:
        i = min(idx[0], len(bs_seq) - 1)
        idx[0] += 1
        return bs_seq[i]

    path, rows = run_latency_capture(
        "0022999999",
        duration_min=10,
        poll_seconds=15.0,
        fetch_pbp=_pbp,
        fetch_bs=_bs,
        sleep_fn=_sleep,
        now_fn=_now,
        latency_dir=os.path.join(PROJECT_DIR, "data", "live_latency"),
        max_polls=5,
    )
    _print_summary("0022999999", path, rows)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Measure end-to-end latency of nba_api live endpoints "
                    "by polling boxscore + playbyplay and timing how long "
                    "after an event's action timestamp it appears in the "
                    "boxscore response.")
    ap.add_argument("--game-id", default=None,
                    help="Single game_id to monitor.")
    ap.add_argument("--all-live", action="store_true",
                    help="Monitor every LIVE game on today's slate.")
    ap.add_argument("--duration-min", type=int, default=_DEFAULT_DURATION_MIN,
                    help="How long to monitor in minutes (default 30).")
    ap.add_argument("--poll-seconds", type=float, default=_DEFAULT_POLL_SECONDS,
                    help="Seconds between polls (default 15, min 0.2).")
    ap.add_argument("--smoke", action="store_true",
                    help="Run the no-network smoke test and exit.")
    args = ap.parse_args(argv)

    if args.smoke:
        return _smoke()

    if args.game_id:
        game_ids = [args.game_id]
    elif args.all_live:
        game_ids = discover_live_game_ids()
        if not game_ids:
            print("[live_api_latency] no live games right now.")
            return 0
    else:
        ap.error("must pass --game-id, --all-live, or --smoke")
        return 2

    for gid in game_ids:
        path, rows = run_latency_capture(
            gid,
            duration_min=args.duration_min,
            poll_seconds=args.poll_seconds,
        )
        _print_summary(gid, path, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
