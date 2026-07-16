"""scripts.platformkit.evidence.exec_evidence_daemon -- supervised M44 tick.

Hourly wrapper around exec_evidence_series.append_snapshot() (LOC-rail split,
same precedent as exec_quality_daemon.py wrapping ingame_realized_clv.backfill
/ paper_today.build_today). Every DEFAULT_INTERVAL_SEC this appends one hourly
vintage to data/frontend/exec_evidence_series.jsonl -- a no-op if the current
UTC hour already has a line (append_snapshot's own idempotency).

MEASUREMENT ONLY: no bet/decision path touched, no flag flipped, no
data/registry/ write, no $ field, no edge claim.

Heartbeat: m44_exec_evidence -> data/cache/daemon_heartbeats/m44_exec_evidence.txt
Cadence: DEFAULT_INTERVAL_SEC = 3600s (hourly).
INVARIANTS: scripts/platformkit/evidence/ only; <=300 LOC; ASCII; no secrets.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/evidence/test_exec_evidence_daemon.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.evidence.exec_evidence_series import append_snapshot

logger = logging.getLogger("exec_evidence_daemon")

HEARTBEAT_COMPONENT = "m44_exec_evidence"
DEFAULT_INTERVAL_SEC = 3600.0


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M44 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("exec_evidence heartbeat skipped: %s", exc)


def tick(*, now: float, append_fn: Optional[Callable[[], Optional[Dict[str, Any]]]] = None
         ) -> Dict[str, Any]:
    """One evidence tick: append_snapshot() + heartbeat. Never raises."""
    _append = append_fn if append_fn is not None else append_snapshot
    try:
        doc = _append()
        result = {"appended": doc is not None, "snapshot_hour": (doc or {}).get("snapshot_hour")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("exec_evidence tick raised: %s", exc)
        result = {"error": str(exc), "appended": False}
    _beat(now)
    return result


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the evidence loop forever (or max_ticks). Everything injectable for
    offline tests. Returns ticks executed."""
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
        doc = tick(now=now)
        print("%s | tick=%d appended=%s hour=%s" % (
            HEARTBEAT_COMPONENT, ticks, doc.get("appended"), doc.get("snapshot_hour")),
            flush=True)
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
        description="Supervised hourly exec-evidence tick (M44): append_snapshot() "
                    "every --interval seconds. Measurement only, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("exec_evidence_daemon | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("exec_evidence_daemon | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
