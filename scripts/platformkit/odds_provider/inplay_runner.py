"""scripts.platformkit.odds_provider.inplay_runner -- supervised P2 entry.

A thin, runnable wrapper around ``inplay_snapshot_daemon.serve_inplay_forever``
so the M9 supervisor can spawn it as ``python -u -m
scripts.platformkit.odds_provider.inplay_runner`` and keep it alive.

WHY a wrapper instead of the daemon's own ``__main__``:
  * The supervisor / ops layer needs ONE liveness heartbeat per service so the
    aggregator can mark the service live/stale in the single status.json. The
    daemon writes a per-sport ``_freshness.json`` (data freshness) but NOT a
    process-liveness heartbeat. This wrapper beats ``ops.liveness`` on every
    poll tick by wrapping the daemon's sleep callable.
  * Keeps the daemon module itself injectable + test-only-pure (no liveness I/O
    inside the capture loop).

Per-sport error isolation lives INSIDE serve_inplay_forever (one bad feed never
sinks the loop); this wrapper adds only the heartbeat + a runnable entry. It
never raises out of the loop, never flips a flag, never writes data/registry/.

Heartbeat component: ``m2_inplay`` ->
data/cache/daemon_heartbeats/m2_inplay.txt (consumed by ops.liveness /
ops.health_aggregator via service_registry).

Stdlib + repo-internal only; ASCII; <=300 LOC. Paper/measurement only.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, Sequence

from scripts.platformkit.odds_provider.inplay_snapshot_daemon import (
    DEFAULT_SPORTS,
    FAST_INTERVAL_SEC,
    IDLE_INTERVAL_SEC,
    serve_inplay_forever,
)

logger = logging.getLogger("inplay_runner")

HEARTBEAT_COMPONENT = "m2_inplay"


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for this service. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- liveness write must never sink loop
        logger.debug("inplay_runner heartbeat skipped: %s", exc)


def _heartbeat_sleep(
    base_sleep: Callable[[float], None],
    *,
    clock: Optional[Callable[[], float]] = None,
) -> Callable[[float], None]:
    """Wrap a sleep callable so a heartbeat is written on every wake boundary.

    The daemon calls ``sleep(wait)`` once per poll tick; beating right before the
    sleep means the heartbeat is refreshed at the poll cadence (fast while live,
    idle otherwise). Beating never raises and never blocks the real sleep.
    """
    def _sleep(seconds: float) -> None:
        now = None
        if clock is not None:
            try:
                now = float(clock())
            except Exception:  # noqa: BLE001
                now = None
        _beat(now)
        base_sleep(seconds)

    return _sleep


def run(*, sports: Sequence[str] = DEFAULT_SPORTS,
        interval: int = FAST_INTERVAL_SEC,
        idle_interval: int = IDLE_INTERVAL_SEC,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        **kwargs) -> None:
    """Run the in-play capture loop with a liveness heartbeat. Never raises out.

    All daemon knobs (``clock`` / ``fetch_fn`` / ``is_live_fn`` / ``out_dir``)
    pass straight through via **kwargs so an offline test can drive it with fakes
    + a bounded ``max_ticks`` and NO network / NO real sleep.
    """
    import time as _time
    base_sleep = sleep if sleep is not None else _time.sleep
    clock = kwargs.get("clock")
    # Beat once at boot so the service is "live" before the first poll completes.
    _beat()
    wrapped_sleep = _heartbeat_sleep(base_sleep, clock=clock)
    serve_inplay_forever(
        sports=tuple(sports), interval=int(interval),
        idle_interval=int(idle_interval), sleep=wrapped_sleep,
        max_ticks=max_ticks, **kwargs)


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Supervised in-play capture runner (P2): polls keyless "
                    "venues for in-game markets + beats a liveness heartbeat.")
    p.add_argument("--sports", default=",".join(DEFAULT_SPORTS),
                   help="Comma-separated sport ids (default: %s)."
                        % ",".join(DEFAULT_SPORTS))
    p.add_argument("--interval", type=int, default=FAST_INTERVAL_SEC,
                   help="Fast poll interval (s) while a game is live.")
    a = p.parse_args()
    sport_list = tuple(s.strip() for s in a.sports.split(",") if s.strip())
    print("inplay_runner | started sports=%s interval=%ss component=%s"
          % (",".join(sport_list), a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(sports=sport_list, interval=a.interval)
    except KeyboardInterrupt:
        print("inplay_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "run"]
