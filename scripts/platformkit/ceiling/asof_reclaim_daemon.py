"""scripts.platformkit.ceiling.asof_reclaim_daemon -- run the asof reclaim sweep on
a schedule, forever, with NO Claude in the loop.

Each tick calls ``asof_reclaim_sweep.sweep()`` (gate every on-disk leak-free
``*_diff_asof`` candidate -> SHIP/REJECT), which appends a scoreboard row and logs
each verdict to the reject_ledger.  The asof parquets are refreshed by the existing
ingest daemons; this re-gates them so the "getting better" search keeps running
unattended.  Default cadence is DAILY (the parquets change slowly).

CANDIDATE-ONLY / DEFAULT-OFF discipline: flips NO flag, touches NO predictor, writes
NO data/registry/, makes NO real-money action.  A SHIP is recorded as SHIP / and a
control-failing SHIP is downgraded to SHIP_REVIEW for a human -- the daemon NEVER
auto-ships into the live predictor.  REJECT is the expected, honest verdict.

Everything (clock/sleep/sweep/stop) is injectable so the loop is offline-testable.

CLI:
    python -m scripts.platformkit.ceiling.asof_reclaim_daemon            # daily loop
    python -m scripts.platformkit.ceiling.asof_reclaim_daemon --once     # one sweep
    python -m scripts.platformkit.ceiling.asof_reclaim_daemon --interval 3600
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

DEFAULT_INTERVAL_SEC = 86400.0   # daily; parquets refresh slowly
COMPONENT = "m_asof_reclaim"


def _default_sweep() -> List[Dict]:
    from scripts.platformkit.ceiling.asof_reclaim_sweep import sweep
    return sweep()


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        sweep_fn: Optional[Callable[[], List[Dict]]] = None,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the reclaim-gate loop forever (or ``max_ticks``).  Never raises out; one
    failing tick is swallowed so the daemon survives.  Returns ticks executed."""
    import time as _time
    _sweep = sweep_fn if sweep_fn is not None else _default_sweep
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            rows = _sweep()
            n_rej = sum(1 for r in rows if r.get("verdict") == "REJECT")
            n_rev = sum(1 for r in rows if r.get("verdict") in ("SHIP", "SHIP_REVIEW"))
            print("%s | tick=%d candidates=%d reject=%d ship/review=%d"
                  % (COMPONENT, ticks, len(rows), n_rej, n_rev), flush=True)
        except Exception as exc:  # noqa: BLE001 - survive any sweep failure
            print("%s | tick=%d ERROR %s" % (COMPONENT, ticks, str(exc)[:160]),
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
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Autonomous asof-reclaim gate daemon: re-gates every on-disk "
                    "leak-free *_diff_asof candidate on a schedule; logs SHIP/REJECT. "
                    "CANDIDATE-ONLY; flips no flag; no edge ever claimed.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between sweeps (default: %(default)s = daily).")
    p.add_argument("--once", action="store_true",
                   help="Run a single sweep and exit (max_ticks=1).")
    a = p.parse_args()
    print("%s | started interval=%ss once=%s" % (COMPONENT, a.interval, a.once),
          flush=True)
    try:
        run(interval_sec=a.interval, max_ticks=1 if a.once else None)
    except KeyboardInterrupt:
        print("%s | stopped by KeyboardInterrupt" % COMPONENT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
