"""scripts.platformkit.sla.sla_runner -- supervised M14 daemon entry (IOX-1).

Runs a cadence loop that:
  1. Reads (artifact_path, sla_sec) pairs from the configured SLA table (derived
     from supervisor.stack_specs.base_specs() heartbeat_path + fresh_sec pairs).
  2. Calls sla_scoreboard.build(artifacts, now) to get per-row verdicts.
  3. Writes the scoreboard atomically to data/frontend/ops/sla_scoreboard.json.
  4. Beats the m14_sla heartbeat via ops.liveness.heartbeat().

MEASUREMENT-ONLY: reads heartbeat mtimes, writes one JSON file + one .txt
heartbeat. No $ field, no flag flip, no real money, no data/registry/ write.

Injectable: clock, sleep, max_ticks, artifacts, out_path -- so an offline test
drives the full loop with zero I/O side effects.

Heartbeat component: ``m14_sla``
    -> data/cache/daemon_heartbeats/m14_sla.txt

Default cadence: 60s.  The SLA window for this daemon itself is 150s (>2x).

PROPOSE-ONLY note: the ProcSpec line for m14_sla is in
docs/research/iox1_m14_procspec.md (stack_specs.py is human-gated).

INVARIANTS: <=300 LOC; ASCII only; stdlib + repo-internal; never raises.
"""
from __future__ import annotations

import logging
import pathlib
import time
from typing import Any, Callable, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger("sla_runner")

HEARTBEAT_COMPONENT = "m14_sla"
DEFAULT_INTERVAL_SEC = 60.0

_REPO = pathlib.Path(__file__).resolve().parents[3]
_DEFAULT_OUT = _REPO / "data" / "frontend" / "ops" / "sla_scoreboard.json"


# ---------------------------------------------------------------------------
# Default artifact table (from stack_specs base_specs heartbeat entries)
# ---------------------------------------------------------------------------

def _default_artifacts() -> List[Tuple[str, float]]:
    """Derive the SLA artifact list from supervisor.stack_specs (read-only).

    Each ProcSpec with HEARTBEAT readiness contributes its (heartbeat_path,
    fresh_sec) pair.  On import error (e.g. supervisor not on path), returns [].
    Never raises.
    """
    try:
        from supervisor.stack_specs import base_specs
        from supervisor.manifest import HEARTBEAT
        pairs: List[Tuple[str, float]] = []
        for spec in base_specs():
            r = getattr(spec, "readiness", None)
            if r is None:
                continue
            kind = getattr(r, "kind", None)
            if kind != HEARTBEAT:
                continue
            hb_path = getattr(r, "heartbeat_path", None)
            fresh_sec = getattr(r, "fresh_sec", None)
            if not hb_path or not fresh_sec:
                continue
            # heartbeat_path is relative to repo root
            abs_path = str(_REPO / hb_path)
            pairs.append((abs_path, float(fresh_sec)))
        return pairs
    except Exception:  # noqa: BLE001 -- import failure must not crash runner
        return []


# ---------------------------------------------------------------------------
# Heartbeat helper
# ---------------------------------------------------------------------------

def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for m14_sla. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("sla_runner heartbeat skipped: %s", exc)


# ---------------------------------------------------------------------------
# Single tick
# ---------------------------------------------------------------------------

def tick(
    *,
    now: float,
    artifacts: Optional[Sequence[Tuple[Union[str, pathlib.Path], float]]] = None,
    out_path: Optional[Union[str, pathlib.Path]] = None,
) -> List[Any]:
    """One SLA scoreboard cycle: build -> write -> beat. Never raises.

    Parameters
    ----------
    now :
        Epoch timestamp (injectable clock value).
    artifacts :
        List of (artifact_path, sla_sec) pairs. Defaults to _default_artifacts().
    out_path :
        Destination JSON path. Defaults to DEFAULT_OUT.

    Returns
    -------
    list[dict]
        The verdict rows written (empty list on any error).
    """
    try:
        from scripts.platformkit.sla.sla_scoreboard import build, write_scoreboard
        art = list(artifacts) if artifacts is not None else _default_artifacts()
        rows = build(art, now=now)
        write_scoreboard(
            rows,
            out_path=out_path,
            generated_at_epoch=now,
        )
        _beat(now)
        return rows
    except Exception as exc:  # noqa: BLE001 -- tick must not crash the loop
        logger.debug("sla_runner tick error: %s", exc)
        _beat(now)
        return []


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

def run(
    *,
    artifacts: Optional[Sequence[Tuple[Union[str, pathlib.Path], float]]] = None,
    out_path: Optional[Union[str, pathlib.Path]] = None,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
    clock: Optional[Callable[[], float]] = None,
    sleep: Optional[Callable[[float], None]] = None,
    max_ticks: Optional[int] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> int:
    """Run the SLA scoreboard loop forever (or for ``max_ticks`` ticks).

    All parameters are injectable so offline tests can drive the full loop
    deterministically without real I/O or real sleeps.

    Returns the number of ticks executed. Never raises out.
    """
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    # Check max_ticks=0 before entering the loop body
    if max_ticks is not None and ticks >= max_ticks:
        return ticks
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            now = float(_clock())
        except Exception:  # noqa: BLE001 -- bad clock -> wall time
            now = _time.time()
        tick(now=now, artifacts=artifacts, out_path=out_path)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001 -- bad sleep ends loop cleanly
            break
    return ticks


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse as _ap
    p = _ap.ArgumentParser(
        description=(
            "SLA scoreboard daemon (M14 / IOX-1): every ~60s reads heartbeat "
            "mtimes, computes per-artifact SLA verdicts, and atomically writes "
            "data/frontend/ops/sla_scoreboard.json. MEASUREMENT-ONLY."
        )
    )
    p.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL_SEC,
        help="Seconds between scoreboard refreshes (default: %(default)s).",
    )
    a = p.parse_args()
    print(
        "sla_runner | started interval=%ss component=%s out=%s"
        % (a.interval, HEARTBEAT_COMPONENT, _DEFAULT_OUT),
        flush=True,
    )
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("sla_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
