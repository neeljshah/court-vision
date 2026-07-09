"""scripts.platformkit.ops_sentinel.failsafe_jobs -- the failsafe job registry
for the m29 ops_sentinel scheduler tick: guard_integrity + disk_space +
heartbeat_coverage + exception_burst. Each job is try/except-isolated so one
raising sentinel never sinks the tick or a sibling. All read-only; NEVER
auto-reverts, restarts, or flips anything.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_failsafe_jobs.py -q
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

logger = logging.getLogger("failsafe_jobs")


def _jobs() -> Dict[str, Callable[..., object]]:
    from scripts.platformkit.ops_sentinel import (
        disk_space, exception_burst, guard_integrity, heartbeat_coverage,
    )
    return {
        "guard_integrity": guard_integrity.tick,
        "disk_space": disk_space.tick,
        "heartbeat_coverage": heartbeat_coverage.tick,
        "exception_burst": exception_burst.tick,
    }


def run_all(*, now: float,
            jobs: Optional[Dict[str, Callable[..., object]]] = None,
            ) -> Dict[str, bool]:
    """Run every failsafe job for this tick. Returns name -> ok. Never raises."""
    out: Dict[str, bool] = {}
    try:
        table = jobs if jobs is not None else _jobs()
    except Exception as exc:  # noqa: BLE001
        logger.debug("failsafe job table failed: %s", exc)
        return out
    for name, fn in table.items():
        try:
            fn(now=now)
            out[name] = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("failsafe job %s raised: %s", name, exc)
            out[name] = False
    return out


__all__ = ["run_all"]
