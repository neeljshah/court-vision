"""scripts.platformkit.canary.canary_runner -- IOX-2 supervised M15 entry point.

A MEASUREMENT-ONLY daemon that, every ~15 minutes, runs all stack canary probes
(stack_canary.run_canary), ATOMICALLY writes the result to
data/frontend/ops/canary_status.json, and beats the m15_canary heartbeat so the
supervisor / ops layer can see THIS daemon is itself alive.

WHY a separate daemon:
  * run_canary() is a PURE read (never writes). Something must run it on a cadence
    and persist the envelope where the front end reads it without recomputing.
    That is this runner and ONLY that.
  * Wrapping it in a supervised service gives the canary its OWN heartbeat so a
    dead canary (stale canary_status.json) is itself RED, never absent-as-green.

HONEST-DEGRADE RAIL (stale-never-green):
  * If run_canary() ever raises unexpectedly this runner does NOT crash-loop and
    does NOT leave a stale-but-ok file: it writes a minimal DOWN envelope
    (status=DOWN, failing_stage='canary_internal_error') instead.
  * The write is ATOMIC (tmp + os.replace) so a reader never sees a torn file.
  * The heartbeat advances AFTER the write so 'alive monitor, bad result' and
    'dead monitor' are distinguishable.
  * read_canary_status() RE-CHECKS file age at read time: if the file is older
    than its configured interval the returned status is STALE (never READY/green).
    An 8h-stale canary_status.json is a blind spot, not a green signal.

SAFETY / INVARIANTS: MEASUREMENT-ONLY. Never writes data/registry/, never flips
a flag, never registers autostart, never touches real money. Injectable probes,
clock, sleep, max_ticks for offline tests. stdlib + repo-internal; ASCII; <=300 LOC.

Heartbeat component: m15_canary -> data/cache/daemon_heartbeats/m15_canary.txt
(consumed by ops.liveness / ops.health_aggregator via service_registry).
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("canary_runner")

HEARTBEAT_COMPONENT = "m15_canary"
DEFAULT_INTERVAL_SEC = 900.0  # 15 minutes

_REPO = pathlib.Path(__file__).resolve().parents[3]
_CANARY_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "canary_status.json"


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for THIS daemon. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("canary_runner heartbeat skipped: %s", exc)


def _error_result(now: float, reason: str, interval_sec: float = DEFAULT_INTERVAL_SEC) -> Dict[str, Any]:
    """A minimal DOWN result used when run_canary() itself raises."""
    return {
        "status": "DOWN",
        "failing_stage": "canary_internal_error",
        "probes": [],
        "notes": ["canary_runner: run_canary raised -> DOWN (%s)" % reason],
        "checked_at": now,
        "generated_at": now,
        "canary_interval_sec": interval_sec,
    }


def _atomic_write_json(path: pathlib.Path, doc: Dict[str, Any]) -> bool:
    """Atomically write *doc* as ASCII JSON to *path*. Returns True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("canary_runner atomic write failed: %s", exc)
        return False


def tick(
    *,
    now: float,
    run_fn: Optional[Callable[..., Any]] = None,
    out_path: Optional[pathlib.Path] = None,
    read_fn: Optional[Callable[[], Any]] = None,
    ops_path: Optional[pathlib.Path] = None,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
) -> Dict[str, Any]:
    """One canary tick: probe -> atomic write -> heartbeat. Never raises.

    Parameters
    ----------
    now          : current epoch seconds (injectable for tests)
    run_fn       : optional override for run_canary (e.g. a stub in tests)
    out_path     : override for canary_status.json path (tests use a tmp dir)
    read_fn      : forwarded to run_canary as read_fn (injectable store read)
    ops_path     : forwarded to run_canary as ops_path (injectable ops status path)
    interval_sec : canary polling interval; stamped into the doc so read_canary_status
                   can detect staleness without out-of-band config.

    Returns the dict that was written to canary_status.json.
    """
    path = out_path if out_path is not None else _CANARY_OUT_PATH

    if run_fn is not None:
        try:
            result_obj = run_fn(now=now, read_fn=read_fn, ops_path=ops_path)
            doc = result_obj.to_dict() if hasattr(result_obj, "to_dict") else dict(result_obj)
        except Exception as exc:  # noqa: BLE001
            doc = _error_result(now, type(exc).__name__, interval_sec)
    else:
        try:
            from scripts.platformkit.canary.stack_canary import run_canary
            result = run_canary(now=now, read_fn=read_fn, ops_path=ops_path)
            doc = result.to_dict()
        except Exception as exc:  # noqa: BLE001
            doc = _error_result(now, type(exc).__name__, interval_sec)

    # Stamp provenance so read_canary_status() can detect a stale file at read time.
    doc.setdefault("generated_at", now)
    doc["canary_interval_sec"] = interval_sec

    _atomic_write_json(path, doc)
    _beat(now)
    return doc


def read_canary_status(
    path: Optional[pathlib.Path] = None,
    now: Optional[float] = None,
    interval_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Read canary_status.json and re-check its age at read time.

    STALE-NEVER-GREEN RAIL: if the file's generated_at is older than the
    canary interval (or than the fallback DEFAULT_INTERVAL_SEC), the returned
    status is downgraded to STALE regardless of what was written -- an 8h-stale
    canary_status.json is a blind spot, not a green light.

    Parameters
    ----------
    path         : path to canary_status.json (defaults to the canonical location)
    now          : current epoch (injectable for tests; defaults to time.time())
    interval_sec : override interval threshold; if None, uses the value stamped
                   in the file (canary_interval_sec) or DEFAULT_INTERVAL_SEC.

    Returns a dict always containing at minimum: status, age_sec, stale_reason.
    Never raises.
    """
    import time as _time
    _now = now if now is not None else _time.time()
    _path = path if path is not None else _CANARY_OUT_PATH

    absent_doc: Dict[str, Any] = {
        "status": "STALE",
        "stale_reason": "canary_status.json absent",
        "age_sec": None,
        "canary_interval_sec": interval_sec or DEFAULT_INTERVAL_SEC,
    }

    try:
        if not _path.exists():
            return absent_doc
        raw = _path.read_text(encoding="ascii")
        doc: Dict[str, Any] = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "STALE",
            "stale_reason": "canary_status.json unreadable: %s" % type(exc).__name__,
            "age_sec": None,
            "canary_interval_sec": interval_sec or DEFAULT_INTERVAL_SEC,
        }

    # Determine the interval to apply: caller override > file-stamped > default.
    effective_interval = (
        interval_sec
        if interval_sec is not None
        else float(doc.get("canary_interval_sec", DEFAULT_INTERVAL_SEC))
    )

    generated_at = doc.get("generated_at")
    if generated_at is None:
        # Legacy file without generated_at: treat as stale (unknown age = unsafe).
        doc["status"] = "STALE"
        doc["stale_reason"] = "generated_at missing (legacy file)"
        doc["age_sec"] = None
        doc["canary_interval_sec"] = effective_interval
        return doc

    try:
        age_sec = _now - float(generated_at)
    except (TypeError, ValueError):
        doc["status"] = "STALE"
        doc["stale_reason"] = "generated_at unparseable"
        doc["age_sec"] = None
        doc["canary_interval_sec"] = effective_interval
        return doc

    doc["age_sec"] = age_sec
    doc["canary_interval_sec"] = effective_interval

    # The critical check: age > interval means canary has not run recently.
    if age_sec > effective_interval:
        original_status = doc.get("status", "UNKNOWN")
        doc["status"] = "STALE"
        doc["stale_reason"] = (
            "canary not refreshed in %.0fs (interval=%.0fs, was=%s)"
            % (age_sec, effective_interval, original_status)
        )

    return doc


def run(
    *,
    run_fn: Optional[Callable[..., Any]] = None,
    out_path: Optional[pathlib.Path] = None,
    read_fn: Optional[Callable[[], Any]] = None,
    ops_path: Optional[pathlib.Path] = None,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
    clock: Optional[Callable[[], float]] = None,
    sleep: Optional[Callable[[float], None]] = None,
    max_ticks: Optional[int] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> int:
    """Run the canary loop forever (or for ``max_ticks`` ticks). Never raises out.

    Everything is injectable for offline tests: fake clock/sleep, stub run_fn,
    bounded max_ticks, isolated out_path -- no network, no real sleep, no real
    store. Returns the number of ticks run.

    MEASUREMENT-ONLY: publishes canary_status.json + heartbeat and NOTHING else.
    Flips no flag, registers no autostart, writes no registry, touches no money.
    """
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
        tick(now=now, run_fn=run_fn, out_path=out_path,
             read_fn=read_fn, ops_path=ops_path, interval_sec=interval_sec)
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
        description="Supervised stack canary (M15): every ~15min probes the "
                    "stack end-to-end + publishes canary_status.json + beats "
                    "m15_canary heartbeat. MEASUREMENT-ONLY -- no flag flip, "
                    "no registry write, no real money.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between probe cycles (default: %(default)s).")
    a = p.parse_args()
    print("canary_runner | started interval=%ss component=%s out=%s"
          % (a.interval, HEARTBEAT_COMPONENT, _CANARY_OUT_PATH), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("canary_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run",
           "read_canary_status"]
