"""scripts.platformkit.combo.combo_daemon -- the always-on Lane-L loop wrapper.

A thin, runnable wrapper around combo_runner.combo_cycle so a supervisor can spawn it as
``python -u -m scripts.platformkit.combo.combo_daemon`` and keep it alive,
checkpoint-resumable across restarts. It owns NO math: every cycle delegates to
combo_cycle (which inherits MF1-MF4 safety by construction).

SAFETY: MEASUREMENT-ONLY by default. With the human-only PIPELINE_ENABLED sentinel
ABSENT, the build choke returns None for every spec, so every cycle decides NO_CANDIDATE
-- the daemon advances its cycle counter + a liveness heartbeat and ships/serves NOTHING.
A STALE/DEGRADED ingest reads DEGRADED (never green) and never advances the cursor.

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag,
never creates the sentinel; calibration not edge. Stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence

from scripts.platformkit.combo.combo_runner import ComboCycleResult, combo_cycle

logger = logging.getLogger("combo_daemon")

HEARTBEAT_COMPONENT = "m_combo_loop"
DEFAULT_NAMES = ("nba", "mlb", "soccer", "tennis")


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for this service. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- liveness write must never sink the loop.
        logger.debug("combo_daemon heartbeat skipped: %s", exc)


def run_cycle(name: str, *, now: float = 0.0, **kw: Any) -> ComboCycleResult:
    """Run ONE combo cycle for `name` (delegates to combo_cycle). NEVER raises."""
    return combo_cycle(name, now=now, **kw)


def run_forever(*, names: Sequence[str] = DEFAULT_NAMES,
                interval_sec: float = 300.0,
                clock: Optional[Callable[[], float]] = None,
                sleep: Optional[Callable[[float], None]] = None,
                max_cycles: Optional[int] = None,
                should_stop: Optional[Callable[[], bool]] = None,
                **cycle_kw: Any) -> List[ComboCycleResult]:
    """Run the checkpoint-resumable combo loop + a liveness heartbeat. NEVER raises out.

    Each pass runs ONE cycle per name then sleeps. Everything is injectable so an offline
    test drives it with a fake clock/sleep, a bounded ``max_cycles`` and isolated paths.
    Defaults are measurement-only (sentinel absent -> NO_CANDIDATE every cycle).
    """
    import time as _time
    base_sleep = sleep if sleep is not None else _time.sleep
    _clock = clock if clock is not None else _time.time
    out: List[ComboCycleResult] = []
    cycles = 0
    _beat(_safe_now(_clock))
    while True:
        if should_stop is not None and _safe_stop(should_stop):
            break
        for name in names:
            now = _safe_now(_clock)
            try:
                out.append(run_cycle(name, now=now, **cycle_kw))
            except Exception as exc:  # noqa: BLE001 -- one bad cycle never kills the loop.
                logger.debug("combo_daemon cycle(%s) failed: %s", name, exc)
        cycles += 1
        _beat(_safe_now(_clock))
        if max_cycles is not None and cycles >= int(max_cycles):
            break
        base_sleep(float(interval_sec))
    return out


def _safe_now(clock: Callable[[], float]) -> float:
    try:
        return float(clock())
    except Exception:  # noqa: BLE001
        return 0.0


def _safe_stop(should_stop: Callable[[], bool]) -> bool:
    try:
        return bool(should_stop())
    except Exception:  # noqa: BLE001
        return False


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Lane-L combination-discovery loop: idempotent, checkpoint-resumable, "
                    "MEASUREMENT-ONLY (inert when the PIPELINE_ENABLED sentinel is absent).")
    p.add_argument("--names", default=",".join(DEFAULT_NAMES),
                   help="Comma-separated sport names (default: %s)." % ",".join(DEFAULT_NAMES))
    p.add_argument("--interval", type=float, default=300.0, help="Seconds between cycles.")
    p.add_argument("--once", action="store_true", help="Run a single pass then exit.")
    a = p.parse_args()
    name_list = tuple(s.strip() for s in a.names.split(",") if s.strip())
    print("combo_daemon | started names=%s interval=%ss component=%s (measurement-only)"
          % (",".join(name_list), a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run_forever(names=name_list, interval_sec=a.interval,
                    max_cycles=1 if a.once else None)
    except KeyboardInterrupt:
        print("combo_daemon | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_NAMES", "run_cycle", "run_forever"]
