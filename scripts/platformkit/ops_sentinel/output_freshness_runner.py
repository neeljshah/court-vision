"""scripts.platformkit.ops_sentinel.output_freshness_runner -- supervised M29 entry.

Every ~300s: checks every readiness=NONE daemon's declared output artifact against
its expected cadence (output_freshness.check_all), atomically writes the verdict
doc, then beats the M29 heartbeat. Independent branch (no depends_on) so a dead
sentinel tick is itself just ONE red status entry -- it never blocks the rest of
the stack. Read-only + no restart authority; NO $ field, NO flag flip, NO
data/registry/ write, NO real-money action.

Heartbeat: m29_output_freshness -> data/cache/daemon_heartbeats/m29_output_freshness.txt
Cadence: DEFAULT_INTERVAL_SEC = 300 s. Report: data/frontend/ops/output_freshness.json.
stdlib + repo-internal; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("output_freshness_runner")

HEARTBEAT_COMPONENT = "m29_output_freshness"
DEFAULT_INTERVAL_SEC = 300.0


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M29 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("output_freshness heartbeat skipped: %s", exc)


def tick(*, now: float,
         check_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
         write_fn: Optional[Callable[..., bool]] = None) -> List[Dict[str, Any]]:
    """One sentinel tick: check every daemon's output freshness -> write the
    verdict doc -> run the registered failsafe jobs (guard_integrity /
    disk_space / heartbeat_coverage / exception_burst, each isolated) ->
    heartbeat. Never raises."""
    from scripts.platformkit.ops_sentinel.output_freshness import check_all, write_status
    _check = check_fn if check_fn is not None else check_all
    _write = write_fn if write_fn is not None else write_status
    try:
        rows = list(_check(now=now) or [])
    except Exception as exc:  # noqa: BLE001
        logger.debug("output_freshness check raised: %s", exc)
        rows = []
    try:
        _write(rows, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("output_freshness write raised: %s", exc)
    try:
        from scripts.platformkit.ops_sentinel.failsafe_jobs import run_all
        run_all(now=now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("failsafe jobs raised: %s", exc)
    _beat(now)
    return rows


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        check_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
        write_fn: Optional[Callable[..., bool]] = None,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the sentinel loop forever (or max_ticks). Never raises out. Everything
    injectable for offline tests. Returns ticks executed."""
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    try:
        _beat(float(_clock()))
    except Exception:  # noqa: BLE001
        _beat()
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            now = float(_clock())
        except Exception:  # noqa: BLE001
            now = _time.time()
        rows = tick(now=now, check_fn=check_fn, write_fn=write_fn)
        n_red = sum(1 for r in rows if r.get("status") == "RED")
        print("%s | tick=%d daemons=%d red=%d" % (
            HEARTBEAT_COMPONENT, ticks, len(rows), n_red), flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(
        description="Supervised output-freshness sentinel (M29): every 300 s checks "
                    "every readiness=NONE daemon's output artifact. Read-only, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("output_freshness_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("output_freshness_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
