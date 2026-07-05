"""domains.basketball_wnba.injuries_daily_daemon -- supervised DAILY WNBA injuries entry.

Per PROPOSED_wnba_injuries_daily.md: the ingest module (ingest_espn_injuries.
ingest_snapshot) already does the right thing on every call -- idempotent
same-day re-run, atomic write, no network at import. This is only the
SCHEDULING hook: loop -> run ingest_snapshot() once -> sleep until the next
daily boundary (default 11:00Z, after most WNBA slates settle overnight).

KNOWLEDGE/SUBSTRATE ONLY -- ingest only, no feature derivation, no model wire.
Never raises out: a fetch/parse failure inside ingest_snapshot degrades to a
0-row snapshot (logged), never crashes this loop. NO $ field, no flag flip,
no data/registry/ write, no real-money action.

Heartbeat: wnba_injuries_daily -> data/cache/daemon_heartbeats/wnba_injuries_daily.txt
Cadence: DAILY_HOUR_UTC = 11 (once per day). stdlib + repo-internal; ASCII; <=80 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_injuries_daily_daemon.py -q
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Callable, Optional

logger = logging.getLogger("wnba_injuries_daily")

HEARTBEAT_COMPONENT = "wnba_injuries_daily"
DAILY_HOUR_UTC = 11


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for this service. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- liveness write must never sink loop
        logger.debug("wnba_injuries_daily heartbeat skipped: %s", exc)


def _seconds_until_next_run(now_utc: dt.datetime, hour_utc: int = DAILY_HOUR_UTC) -> float:
    """Seconds from *now_utc* to the next daily boundary at *hour_utc*:00 UTC. Pure."""
    target = now_utc.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now_utc:
        target += dt.timedelta(days=1)
    return (target - now_utc).total_seconds()


def tick(ingest_fn: Optional[Callable[[], object]] = None) -> int:
    """Run one ingest pass; returns the row count (0 on any failure). Never raises."""
    from domains.basketball_wnba.ingest_espn_injuries import ingest_snapshot
    fn = ingest_fn if ingest_fn is not None else ingest_snapshot
    try:
        df = fn()
        return 0 if df is None else len(df)
    except Exception as exc:  # noqa: BLE001 -- a bad fetch must never crash the daemon
        logger.warning("wnba_injuries_daily ingest failed: %s", exc)
        return 0


def run(*, ingest_fn: Optional[Callable[[], object]] = None,
        clock: Optional[Callable[[], dt.datetime]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None) -> int:
    """Loop forever (or *max_ticks*): ingest once, beat, sleep until next 11:00Z.

    Injectable clock/sleep so the tested path needs NO real wall-clock wait and
    NO network. Returns the number of ticks executed. Never raises out.
    """
    _clock = clock if clock is not None else (lambda: dt.datetime.now(dt.timezone.utc))
    _sleep = sleep if sleep is not None else __import__("time").sleep
    ticks = 0
    _beat()
    while max_ticks is None or ticks < max_ticks:
        n_rows = tick(ingest_fn=ingest_fn)
        now = _clock()
        _beat(now.timestamp() if hasattr(now, "timestamp") else None)
        print("wnba_injuries_daily | tick=%d rows=%d" % (ticks, n_rows), flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        _sleep(_seconds_until_next_run(now))
    return ticks


def _main() -> int:  # pragma: no cover -- thin CLI shim
    print("wnba_injuries_daily | started component=%s daily_hour_utc=%d"
          % (HEARTBEAT_COMPONENT, DAILY_HOUR_UTC), flush=True)
    try:
        run()
    except KeyboardInterrupt:
        print("wnba_injuries_daily | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DAILY_HOUR_UTC", "tick", "run"]
