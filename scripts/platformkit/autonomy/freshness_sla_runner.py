"""scripts.platformkit.autonomy.freshness_sla_runner -- supervised entry point
for the per-daemon freshness SLA scoreboard (freshness_sla.TABLE).

Every ~300s: checks every supervised daemon name (from supervisor.manifest())
against freshness_sla.TABLE, writes the GREEN/RED/NA scoreboard, beats its own
heartbeat. Independent branch (no depends_on) so a dead sentinel tick is itself
ONE red status entry. Read-only, NO restart authority (mirrors
output_freshness_runner.py). NO $ field, NO flag flip, NO data/registry/ write.

Heartbeat: m34_freshness_sla -> data/cache/daemon_heartbeats/m34_freshness_sla.txt
Cadence: DEFAULT_INTERVAL_SEC = 300s. Report: data/frontend/ops/freshness_sla.json.
stdlib + repo-internal; ASCII only; <=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_freshness_sla.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("freshness_sla_runner")

HEARTBEAT_COMPONENT = "m34_freshness_sla"
DEFAULT_INTERVAL_SEC = 300.0


def _beat(now_epoch: Optional[float] = None) -> None:
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("freshness_sla heartbeat skipped: %s", exc)


def _daemon_names() -> List[str]:
    """Every supervised daemon name, from the real manifest. Never raises."""
    try:
        from supervisor.manifest import manifest
        return [s.name for s in manifest("default")]
    except Exception as exc:  # noqa: BLE001
        logger.debug("freshness_sla: manifest() raised %s", exc)
        return []


def tick(*, now: float,
         names: Optional[List[str]] = None,
         check_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
         write_fn: Optional[Callable[..., bool]] = None) -> List[Dict[str, Any]]:
    """One sentinel tick: check every daemon's freshness SLA -> write the
    scoreboard -> heartbeat. Never raises."""
    from scripts.platformkit.autonomy.freshness_sla import check_all, write_status
    _names = names if names is not None else _daemon_names()
    _check = check_fn if check_fn is not None else check_all
    _write = write_fn if write_fn is not None else write_status
    try:
        rows = list(_check(_names, now=now) or [])
    except Exception as exc:  # noqa: BLE001
        logger.debug("freshness_sla check raised: %s", exc)
        rows = []
    try:
        _write(rows, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("freshness_sla write raised: %s", exc)
    _beat(now)
    return rows


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        check_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
        write_fn: Optional[Callable[..., bool]] = None,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the sentinel loop forever (or max_ticks). Never raises out."""
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
        n_na = sum(1 for r in rows if r.get("status") == "NA")
        print("%s | tick=%d daemons=%d red=%d na=%d" % (
            HEARTBEAT_COMPONENT, ticks, len(rows), n_red, n_na), flush=True)
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
        description="Supervised per-daemon freshness SLA sentinel (M34): every "
                    "300s checks every supervised daemon's output artifact "
                    "against freshness_sla.TABLE. Read-only, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("freshness_sla_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("freshness_sla_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
