"""scripts.platformkit.ingame.inplay_derivative_mlb_runner -- CLI entry for the MLB
in-play totals/run-line derivative channel (inplay_derivative_mlb.poll_once).

Thin runner, mirrors inplay_capture_runner.py's split (loop module vs runnable
entry): owns the --once/--interval CLI and a SIMPLE SINGLETON file lock so two
overlapping runs never double-place. Runs ALONGSIDE the moneyline
inplay_capture_runner without touching it (own lock file, own heartbeat path).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no
data/registry write, no flag flip, no autostart.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_derivative_mlb.py -q
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from scripts.platformkit.ingame.inplay_derivative_mlb import (
    DEFAULT_LOCK,
    IDLE_INTERVAL_SEC,
    LIVE_INTERVAL_SEC,
    poll_once,
)

logger = logging.getLogger(__name__)


def acquire_lock(path: Path) -> bool:
    """Simplest-possible SINGLETON guard: an exclusive-create PID file.

    ponytail: no flock (Windows/Git Bash portability), no stale-PID reap -- a crashed
    process leaves a stale lock; delete the file manually to recover. Upgrade to a
    real flock/psutil-liveness check if two real overlapping runs are ever observed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _beat() -> None:
    """ops.liveness heartbeat for component m2_inplay_deriv. Never raises --
    the ops audit 2026-07-19 flagged this file's docstring promised a liveness
    heartbeat that was never actually written."""
    try:
        from ops.liveness import heartbeat
        heartbeat("m2_inplay_deriv")
    except Exception:  # noqa: BLE001 -- liveness is observability, never fatal
        logger.debug("inplay_derivative_mlb_runner heartbeat skipped", exc_info=True)


def release_lock(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 -- best-effort cleanup only
        pass


def run(*, once: bool = False, interval: Optional[float] = None,
       lock_path: Optional[Path] = None, sleep=time.sleep) -> int:
    """Run the derivative channel: one tick (once=True) or forever on a phase-aware
    cadence. Returns the number of ticks run. Never raises out (KeyboardInterrupt
    stops cleanly)."""
    lock = lock_path if lock_path is not None else DEFAULT_LOCK
    if not acquire_lock(lock):
        logger.warning("inplay_derivative_mlb_runner: another instance holds %s -- exiting", lock)
        return 0
    n_ticks = 0
    try:
        while True:
            hb = poll_once()
            n_ticks += 1
            _beat()  # ops.liveness txt heartbeat (m2_inplay_deriv) -- stale-never-green
            print("inplay_derivative_mlb | tick: games=%d captured=%d bets=%d settled=%s"
                  % (hb["n_games"], hb["n_captured"], hb["n_bets"], hb["settled"]), flush=True)
            if once:
                return n_ticks
            wait = interval if interval is not None else (
                LIVE_INTERVAL_SEC if hb["n_games"] else IDLE_INTERVAL_SEC)
            sleep(wait)
    except KeyboardInterrupt:
        print("inplay_derivative_mlb | stopped by KeyboardInterrupt", flush=True)
        return n_ticks
    finally:
        release_lock(lock)


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse
    ap = argparse.ArgumentParser(description="MLB in-play totals/run-line derivative "
                                             "paper channel (measurement-only).")
    ap.add_argument("--once", action="store_true", help="Run a single tick and exit.")
    ap.add_argument("--interval", type=float, default=None,
                    help="Poll interval seconds (default: phase-aware live/idle).")
    a = ap.parse_args()
    run(once=a.once, interval=a.interval)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["run", "acquire_lock", "release_lock"]
