"""scripts.platformkit.improve.ingame_baseout_gate_daemon -- run the in-game base-out
anticipation TRIGGER on the flywheel, with NO Claude in the loop.

ingame_baseout_gate.gate() asks the honest question "does the deep base-out / RE24 /
count / pitch state anticipate the in-play close BEYOND model_prob?" and writes
INSUFFICIENT until the captured corpus is large enough, then SHIP_REVIEW / REJECT.
This daemon re-runs that gate on a slow cadence so the verdict crosses on its OWN the
moment the corpus is ready -- the user's "when does in-play start beating" made into a
self-firing trigger instead of a date guess.

HONEST RAILS: candidate-only (reads the captured grade cache, flips NO flag, touches NO
predictor, places NO bet); probability space only; INSUFFICIENT/REJECT are honest
successes; never raises out; ASCII; injectable clock/sleep/should_stop for tests.

CLI:
    python -m scripts.platformkit.improve.ingame_baseout_gate_daemon            # slow loop
    python -m scripts.platformkit.improve.ingame_baseout_gate_daemon --once
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence

DEFAULT_INTERVAL_SEC = 3600.0          # the deep corpus only grows during live games
DEFAULT_SPORTS = ("mlb",)              # only MLB emits the deep base-out state today
COMPONENT = "m_ingame_baseout_gate"


def _gate_one(sport: str) -> Dict[str, Any]:
    from scripts.platformkit.improve import ingame_baseout_gate as G
    return G.gate(sport)               # writes its own verdict doc; returns the row


def sweep(sports: Sequence[str] = DEFAULT_SPORTS,
          gate_fn: Optional[Callable[[str], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Run the gate for each sport (each isolated). Returns {sport: verdict_row}."""
    gf = gate_fn or _gate_one
    out: Dict[str, Any] = {}
    for sp in sports:
        try:
            out[sp] = gf(sp)
        except Exception as exc:  # robust: one sport must not kill the sweep
            out[sp] = {"sport": sp, "verdict": "ERROR", "error": str(exc)[:200]}
    return out


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        sports: Sequence[str] = DEFAULT_SPORTS,
        gate_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Re-run the trigger forever (or ``max_ticks``). Survives any tick failure."""
    import time as _time
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
            res = sweep(sports, gate_fn=gate_fn)
            verds = " ".join("%s=%s" % (sp, r.get("verdict")) for sp, r in res.items())
            print("%s | tick=%d %s" % (COMPONENT, ticks, verds), flush=True)
        except Exception as exc:  # noqa: BLE001 - survive any failure
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
        description="Autonomous in-game base-out anticipation trigger: re-runs the "
                    "leak-free gate on a slow cadence so it crosses on its own when the "
                    "captured corpus is ready. Calibration only; no edge ever claimed.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    p.add_argument("--once", action="store_true", help="Run a single sweep and exit.")
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


__all__ = ["sweep", "run", "DEFAULT_INTERVAL_SEC", "DEFAULT_SPORTS", "COMPONENT"]
