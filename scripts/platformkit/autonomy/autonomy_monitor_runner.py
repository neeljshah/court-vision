"""scripts.platformkit.autonomy.autonomy_monitor_runner -- supervised M5 entry.

A MEASUREMENT-ONLY daemon that, every ~60s, composes the ONE canonical autonomy
status (scripts.platformkit.autonomy.status_composer.compose) and ATOMICALLY
publishes it to data/frontend/ops/autonomy_status.json so the UI / runbook reads
a single, always-current, honestly-degraded document -- and beats a liveness
heartbeat so the supervisor / ops layer can see THIS monitor is itself alive.

WHY a separate publisher daemon:
  * status_composer.compose() is a PURE read (it never writes). Something has to
    actually run it on a cadence and persist the envelope where the front end can
    read it without recomputing. That is this runner -- and ONLY that. It adds no
    new observability primitive; it just refreshes the file the composer builds.
  * Wrapping it in a supervised service gives the monitor its OWN heartbeat, so a
    dead monitor (stale autonomy_status.json) is itself visible as RED, never an
    absence read as green.

HONEST-DEGRADE RAIL (never green on failure):
  * compose() is documented NEVER to raise, but if it ever does, this runner does
    NOT crash-loop and does NOT leave a stale-but-green file: it writes a minimal
    DEGRADED envelope (overall="degraded", explicit error note) instead. The
    monitor's own heartbeat still advances so the supervisor can distinguish "the
    monitor is alive but the composer is unhappy" from "the monitor is dead".
  * The write is ATOMIC (tmp + os.replace) so a reader never sees a torn file.

REAPER WIRE (IOP-08): after compose, load_reaper_status() reads the supervisor's
reaper snapshot. STALE_HUNG / NO_HEARTBEAT rows degrade the matching service[];
HEALTHY rows and missing files leave services unchanged (unknown, never green).
The overall severity is re-derived from the merged services before write.

M5FIX WIRE (IOP-07): after reaper merge, status_composer_m5fix.patch_m5_row
forces the m5 row to "degraded" when its own heartbeat is stale/absent. Never
upgrades a worse row; never raises.

ORPHAN WIRE (IOP-06): after m5fix, orphan_hb_check.run_check surfaces orphan
heartbeat stems (no owning spec) into doc["notes"]. READ-ONLY; never raises.

MERGE ORDER: compose() -> reaper_merge -> m5fix -> orphan_surface -> write -> beat

Merge helpers (IOP-06/07/08) live in _monitor_merge_helpers to keep this file
under the 300-LOC rail. They are re-exported in __all__ for backward compat.

SAFETY / INVARIANTS: MEASUREMENT-ONLY. Reads only; never flips flags; never
touches real money; calibration not edge. Injectable for offline tests. ASCII.

Heartbeat component: ``m5_autonomy_monitor`` ->
data/cache/daemon_heartbeats/m5_autonomy_monitor.txt (consumed by ops.liveness /
ops.health_aggregator via service_registry).
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import time
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.autonomy._monitor_merge_helpers import (
    _apply_m5fix,
    _apply_orphan_surface,
    _apply_reaper_merge,
)

logger = logging.getLogger("autonomy_monitor_runner")

HEARTBEAT_COMPONENT = "m5_autonomy_monitor"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_STATUS_PATH = _REPO / "data" / "frontend" / "ops" / "autonomy_status.json"

DEFAULT_INTERVAL_SEC = 60.0

DEGRADED = "degraded"


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for THIS monitor. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("autonomy_monitor heartbeat skipped: %s", exc)


def _degraded_envelope(now: float, reason: str) -> Dict[str, Any]:
    """A minimal, honestly-DEGRADED status doc (never green) for compose failure.

    Used only when status_composer.compose() raises (it is documented not to, but
    a defense-in-depth must never let the monitor publish a stale-but-green file).
    """
    return {
        "generated_at": None,
        "overall": DEGRADED,
        "services": [],
        "loop": {},
        "ratchet": {},
        "high_water": {},
        "idle_reason": None,
        "notes": ["autonomy_monitor: status_composer.compose raised -> "
                  "degraded envelope published (%s)" % reason],
        "monitor": {
            "component": HEARTBEAT_COMPONENT,
            "wrote_at": now,
            "compose_ok": False,
        },
        "honest_note": (
            "MEASUREMENT-ONLY autonomy monitor; calibration not edge, no $ field. "
            "compose failed -> this document is DEGRADED, never green."
        ),
    }


def _compose_status(now: float, *,
                    compose: Callable[..., Dict[str, Any]],
                    profile: str,
                    breakers: Optional[Dict[str, Any]],
                    reaper_path: Optional[pathlib.Path] = None,
                    m5_hb_path: Optional[pathlib.Path] = None,
                    orphan_hb_dir: Optional[pathlib.Path] = None,
                    orphan_report_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """compose -> reaper_merge -> m5fix -> orphan_surface. Never raises; DEGRADED on error."""
    try:
        doc = compose(now=now, profile=profile, breakers=breakers)
        if not isinstance(doc, dict):
            return _degraded_envelope(now, "compose returned non-dict")
    except Exception as exc:  # noqa: BLE001
        logger.debug("autonomy_monitor compose raised: %s", exc)
        return _degraded_envelope(now, type(exc).__name__)
    doc = _apply_reaper_merge(doc, reaper_path=reaper_path)
    doc = _apply_m5fix(doc, now=now, m5_hb_path=m5_hb_path)
    doc = _apply_orphan_surface(
        doc, hb_dir=orphan_hb_dir, orphan_report_path=orphan_report_path, now=now
    )
    out = dict(doc)
    out["monitor"] = {
        "component": HEARTBEAT_COMPONENT,
        "wrote_at": now,
        "compose_ok": True,
    }
    return out


def _atomic_write_json(path: pathlib.Path, doc: Dict[str, Any]) -> bool:
    """Atomically write *doc* as ASCII JSON to *path* (tmp + os.replace).

    Returns True on success, False on any I/O error (never raises). A reader never
    sees a torn file: the rename is atomic on the same filesystem.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("autonomy_monitor atomic write failed: %s", exc)
        return False


def tick(*, now: float,
         compose: Optional[Callable[..., Dict[str, Any]]] = None,
         status_path: Optional[pathlib.Path] = None,
         profile: str = "default",
         breakers: Optional[Dict[str, Any]] = None,
         reaper_path: Optional[pathlib.Path] = None,
         m5_hb_path: Optional[pathlib.Path] = None,
         orphan_hb_dir: Optional[pathlib.Path] = None,
         orphan_report_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """One cycle: compose -> reaper_merge -> m5fix -> orphan_surface -> write -> beat.

    Returns the doc written (DEGRADED on failure). Heartbeat is beat after write.
    All path args are injectable for offline tests. Never raises.
    """
    if compose is None:
        from scripts.platformkit.autonomy.status_composer import compose as _c
        compose = _c
    path = status_path if status_path is not None else _STATUS_PATH
    doc = _compose_status(
        now,
        compose=compose,
        profile=profile,
        breakers=breakers,
        reaper_path=reaper_path,
        m5_hb_path=m5_hb_path,
        orphan_hb_dir=orphan_hb_dir,
        orphan_report_path=orphan_report_path,
    )
    _atomic_write_json(path, doc)
    _beat(now)
    return doc


def run(*, compose: Optional[Callable[..., Dict[str, Any]]] = None,
        status_path: Optional[pathlib.Path] = None,
        profile: str = "default",
        breakers: Optional[Dict[str, Any]] = None,
        reaper_path: Optional[pathlib.Path] = None,
        m5_hb_path: Optional[pathlib.Path] = None,
        orphan_hb_dir: Optional[pathlib.Path] = None,
        orphan_report_path: Optional[pathlib.Path] = None,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Publish loop: runs until max_ticks or should_stop. Returns tick count. Never raises."""
    import time as _time
    _clock = clock if clock is not None else _time.time
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
            now = float(_clock())
        except Exception:  # noqa: BLE001
            now = _time.time()
        tick(
            now=now,
            compose=compose,
            status_path=status_path,
            profile=profile,
            breakers=breakers,
            reaper_path=reaper_path,
            m5_hb_path=m5_hb_path,
            orphan_hb_dir=orphan_hb_dir,
            orphan_report_path=orphan_report_path,
        )
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Supervised autonomy monitor (M5): every ~60s composes the "
                    "ONE canonical autonomy status + publishes it atomically + "
                    "beats a liveness heartbeat. MEASUREMENT-ONLY -- ships "
                    "nothing, flips no flag, touches no real money.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between publish cycles (default: %(default)s).")
    a = p.parse_args()
    print("autonomy_monitor_runner | started interval=%ss component=%s out=%s"
          % (a.interval, HEARTBEAT_COMPONENT, _STATUS_PATH), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("autonomy_monitor_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "HEARTBEAT_COMPONENT",
    "DEFAULT_INTERVAL_SEC",
    "tick",
    "run",
    "_apply_reaper_merge",
    "_apply_m5fix",
    "_apply_orphan_surface",
]
