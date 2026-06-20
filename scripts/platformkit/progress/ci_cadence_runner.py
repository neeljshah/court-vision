"""scripts.platformkit.progress.ci_cadence_runner -- supervised M8 entry (W4).

A thin, always-on LOOP wrapper around the externally-triggered ONE-tick cadence
(`ci_schedule.main` -> `ci_cadence.run_once`) so the M9 supervisor can spawn it as
``python -u -m scripts.platformkit.progress.ci_cadence_runner`` and keep it alive on
a cadence WITHOUT a self-installing OS scheduler.

WHY a wrapper instead of the cadence's own ``main``:
  * ``ci_schedule.main`` runs EXACTLY ONE tick and returns -- it is the cron / Task
    Scheduler entrypoint. The supervisor only knows how to keep a process ALIVE; an
    always-alive proc that exits after one tick would restart-loop hot. This wrapper
    sleeps a declared cadence between ticks so a supervised forever-run ticks at the
    intended HOURLY-light interval, not in a tight loop.
  * Each tick already beats the ``m8_ci_cadence`` liveness heartbeat (ci_cadence._beat
    -> ops.liveness.heartbeat). This wrapper ALSO beats at boot + on every sleep
    boundary so a hung tick (no fresh beat) ages out as NOT-READY -- stale-never-green.

The cadence stays MEASUREMENT-ONLY + INERT: ``run_once`` enqueues only ALLOWED_KINDS,
auto-gates with recalibrate_fn=None (-> NO_CANDIDATE while the PIPELINE_ENABLED sentinel
is absent), and appends exactly one progress row. This wrapper adds NO new math; it only
adds liveness + a sleep cadence + a runnable entry. It NEVER ships, NEVER flips a flag,
NEVER creates the sentinel, NEVER writes data/registry/ or MEMORY.md, NEVER arms
autostart / real money / push. NO $ field. stdlib + repo-internal; ASCII; <=300 LOC.

Heartbeat component: ``m8_ci_cadence`` ->
data/cache/daemon_heartbeats/m8_ci_cadence.txt (consumed by ops.liveness /
the supervisor heartbeat-fresh readiness probe).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/progress/test_ci_cadence_runner.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from scripts.platformkit.progress.ci_cadence import HEARTBEAT_COMPONENT
from scripts.platformkit.progress.ci_schedule import HOURLY_LIGHT, run_tick

logger = logging.getLogger("ci_cadence_runner")

# Declared cadence between ticks. The HOURLY_LIGHT descriptor is the intended low-churn
# cadence (liveness + freshness, skip the heavy finder refresh). fresh_sec on the
# supervisor side (7800s) comfortably exceeds this so a healthy runner reads fresh and a
# genuinely dead/hung tick ages out -- never a stale-green.
DEFAULT_INTERVAL_SEC = 3600.0


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for THIS runner. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- liveness write must never sink loop
        logger.debug("ci_cadence_runner heartbeat skipped: %s", exc)


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        run_fn: Optional[Callable[..., Any]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Drive ``run_tick`` on a cadence forever (or for ``max_ticks``). Never raises out.

    Everything is injectable so an offline test drives it with a fake clock/sleep, a stub
    run_fn, a bounded ``max_ticks`` and NO real sleep / NO substrate. Beats the heartbeat
    at boot and before every sleep so liveness advances at the cadence; a hung tick stops
    advancing it and the supervisor reads NOT-READY. Returns the number of ticks run.

    MEASUREMENT-ONLY: each tick is ci_cadence.run_once (INERT while the sentinel is
    absent). This wrapper flips no flag, creates no sentinel, writes no registry, arms no
    autostart, touches no real money.
    """
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    # Beat once at boot so the service is "live" before the first tick completes.
    try:
        _beat(float(_clock()))
    except Exception:  # noqa: BLE001
        _beat()
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001 -- a bad stop hook must not crash loop
                break
        try:
            now = float(_clock())
        except Exception:  # noqa: BLE001 -- a bad clock degrades to wall time
            now = _time.time()
        # run_tick is itself degrade-isolated (NEVER raises out); the cadence's own
        # _beat also fires inside run_once. We beat again here for boundary liveness.
        run_tick(now, run_fn=run_fn)
        _beat(now)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001 -- a bad sleep ends the loop cleanly
            break
    return ticks


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Supervised continuous-improvement cadence runner (M8): runs ONE "
                    "ci_cadence tick (INERT, measurement-only) every interval + beats a "
                    "liveness heartbeat. Ships nothing, flips no flag, no real money.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between cadence ticks (default: %(default)s).")
    a = p.parse_args()
    print("ci_cadence_runner | started interval=%ss component=%s | cadence=%s "
          "(measurement-only, INERT, no $/flag/registry/autostart)"
          % (a.interval, HEARTBEAT_COMPONENT, HOURLY_LIGHT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("ci_cadence_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "run"]
