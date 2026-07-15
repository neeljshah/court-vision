"""scripts.platformkit.paper.settle_sweep_daemon -- supervised M43 tick.

The heartbeat/--interval loop wrapper around settle_sweep.sweep() (LOC-rail
split so settle_sweep.py itself stays under the 300 LOC rail -- same precedent
as exec_quality_daemon.py wrapping ingame_realized_clv.backfill / paper_today.
build_today). Every DEFAULT_INTERVAL_SEC this calls sweep(write=True): retries
the aged (>=7d) open paper backlog via the existing per-channel settlers and
VOIDs whatever is provably unroutable. See settle_sweep.py's module docstring
for the full contract; MEASUREMENT/SETTLEMENT ONLY -- no $ field, no flag flip,
no data/registry/ write, no edge claim.

Heartbeat: m43_settle_sweep -> data/cache/daemon_heartbeats/m43_settle_sweep.txt
Cadence: DEFAULT_INTERVAL_SEC = 3600s (hourly).
INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; no $-edge.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/paper/test_settle_sweep.py -q
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit.paper.settle_sweep import sweep

logger = logging.getLogger(__name__)

HEARTBEAT_COMPONENT = "m43_settle_sweep"
DEFAULT_INTERVAL_SEC = 3600.0


def _beat(now_epoch: Optional[float] = None) -> None:
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("settle_sweep heartbeat skipped: %s", exc)


def tick(*, now: float, ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """One supervised sweep tick: real sweep(write=True) + heartbeat. Never raises."""
    try:
        result = sweep(ledger_path, write=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("settle_sweep tick raised: %s", exc)
        result = {"error": str(exc)}
    _beat(now)
    return result


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        ledger_path: Optional[Path] = None,
        clock=None, sleep=None, max_ticks: Optional[int] = None,
        should_stop=None) -> int:
    """Run the sweep loop forever (or max_ticks). Injectable for offline tests."""
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
        doc = tick(now=now, ledger_path=ledger_path)
        print("%s | tick=%d settled=%s voided=%s left_open=%s" % (
            HEARTBEAT_COMPONENT, ticks, doc.get("n_settled_now"),
            doc.get("n_voided"), doc.get("n_left_open")), flush=True)
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
    ap = argparse.ArgumentParser(
        description="Supervised settlement-sweep tick (M43): sweep(write=True) "
                    "every --interval seconds. Paper/units only, no $.")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = ap.parse_args()
    ledger = Path(a.ledger) if a.ledger else None
    print("settle_sweep_daemon | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval, ledger_path=ledger)
    except KeyboardInterrupt:
        print("settle_sweep_daemon | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
