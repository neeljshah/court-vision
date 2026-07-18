"""scripts.platformkit.tip_capture.daemon -- forward capture of tip-time info.

THE GAP (standing directive): early in-game predictions are worse than late
ones largely because we evaluate them AFTER the fact with information (final
injury/lineup state, closing price) the model never had AT TIP. The fix is not
a smarter model -- it is an honest, timestamped, FORWARD record of exactly what
was knowable at T-60/T-30/T-5 minutes before tip, so a future evaluation is
information-complete instead of leaking hindsight.

For each upcoming NBA/WNBA/MLB game, at each due capture pass, this daemon
records: (1) injury/lineup state, (2) schedule + tip time, (3) our own frozen
win-prob prior, (4) an optional pregame market price snapshot -- see
capture.py's module docstring for exactly which existing fetcher backs each
one (no new transport, no new team-matching logic anywhere in this package).

schedule.py  -- pure T-60/T-30/T-5 capture-pass math (no I/O).
capture.py   -- the four fail-open capture sources + row builder.
store.py     -- append-only JSONL store, flock singleton, heartbeat.
daemon.py    -- this file: the tick/run loop + CLI.

CAPTURES DATA ONLY -- places nothing, flips no flag. Meant to run on the pod
(RunPod, Linux, /workspace/court-vision), not the local fleet.

INVARIANTS: scripts/platformkit/ only; <=300 LOC/file; ASCII only; stdlib +
in-repo fetchers only; no data/registry/ writes; no $/edge claims.
Per-file test: tests/platformkit/tip_capture/test_daemon.py
Run: python -m scripts.platformkit.tip_capture.daemon --once
"""
from __future__ import annotations

import argparse
import json
import logging
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .capture import build_row, fetch_schedule
from .schedule import due_passes, next_wake_seconds, parse_iso
from .store import acquire_singleton, append_row, beat, captured_passes_for
from .store import DEFAULT_LOCK_PATH, DEFAULT_OUT_DIR

logger = logging.getLogger("tip_capture")

SPORTS: Tuple[str, ...] = ("nba", "wnba", "mlb")


def tick(*, sports: Sequence[str] = SPORTS, now: Optional[datetime] = None,
        out_dir: Optional[Path] = None, deps: Optional[Dict[str, Callable]] = None,
        schedule_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """One pass: capture every due (game, pass) across *sports*, heartbeat,
    and report the next useful wake time. Never raises."""
    nowdt = now if now is not None else datetime.now(timezone.utc)
    sched = schedule_fn if schedule_fn is not None else fetch_schedule
    summary: Dict[str, Any] = {"as_of": nowdt.isoformat(), "sports": {}}
    all_games: List[Tuple[datetime, set]] = []
    for sport in sports:
        n_captured = 0
        try:
            games = sched(sport)
        except Exception as exc:  # noqa: BLE001 -- one sport must never sink the tick
            logger.warning("tip_capture schedule fetch failed sport=%s: %s", sport, exc)
            games = []
        for game in games:
            tip = parse_iso(game.get("tip_time"))
            if tip is None:
                continue
            captured = captured_passes_for(game["game_id"], sport, game["tip_time"],
                                           out_dir=out_dir)
            for pass_name in due_passes(tip, nowdt, captured):
                row = build_row(game, pass_name, now=nowdt, deps=deps)
                append_row(row, out_dir=out_dir)
                captured.add(pass_name)
                n_captured += 1
            all_games.append((tip, captured))
        summary["sports"][sport] = {"n_games": len(games), "n_captured": n_captured}
    beat(nowdt.timestamp())
    summary["next_wake_sec"] = next_wake_seconds(all_games, nowdt)
    return summary


def run(*, sports: Sequence[str] = SPORTS, out_dir: Optional[Path] = None,
       deps: Optional[Dict[str, Callable]] = None, schedule_fn: Optional[Callable] = None,
       clock: Optional[Callable[[], datetime]] = None,
       sleep: Optional[Callable[[float], None]] = None,
       max_ticks: Optional[int] = None,
       should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Schedule-driven loop: never busy-polls -- sleeps exactly until the next
    due pass (bounded). Returns ticks executed."""
    _clock = clock or (lambda: datetime.now(timezone.utc))
    _sleep = sleep or _time.sleep
    ticks = 0
    while True:
        if should_stop is not None and should_stop():
            break
        summary = tick(sports=sports, now=_clock(), out_dir=out_dir, deps=deps,
                       schedule_fn=schedule_fn)
        print("tip_capture | tick=%d as_of=%s %s next_wake=%.0fs" % (
            ticks, summary["as_of"],
            " ".join("%s=%s/%s" % (sp, d["n_captured"], d["n_games"])
                     for sp, d in summary["sports"].items()),
            summary["next_wake_sec"]), flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(summary["next_wake_sec"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("tip_capture sleep failed: %s", exc)
    return ticks


def _main() -> int:  # pragma: no cover -- thin CLI shim
    ap = argparse.ArgumentParser(description="Forward tip-time capture daemon.")
    ap.add_argument("--once", action="store_true", help="single pass, for cron")
    ap.add_argument("--sports", default=",".join(SPORTS))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--lock-path", default=None)
    ap.add_argument("--no-lock", action="store_true")
    a = ap.parse_args()
    sports = tuple(s.strip() for s in a.sports.split(",") if s.strip())
    lock_path = Path(a.lock_path) if a.lock_path else DEFAULT_LOCK_PATH
    if not a.no_lock and not acquire_singleton(lock_path):
        print("tip_capture: already running (lock held), exiting", flush=True)
        return 1
    out_dir = Path(a.out_dir) if a.out_dir else None
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if a.once:
        summary = tick(sports=sports, out_dir=out_dir)
        print(json.dumps(summary, default=str), flush=True)
        return 0
    print("tip_capture | started sports=%s" % ",".join(sports), flush=True)
    try:
        run(sports=sports, out_dir=out_dir)
    except KeyboardInterrupt:
        print("tip_capture | stopped", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["SPORTS", "DEFAULT_OUT_DIR", "DEFAULT_LOCK_PATH", "tick", "run"]
