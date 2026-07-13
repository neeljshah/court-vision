"""predict_service.scheduler -- the always-on producer scheduler.

ONE process refreshes every active sport's canonical snapshot on a cadence. It
REUSES the validated chain verbatim: registry.active_sports() decides WHICH
sports to run (corpus present on this box), produce.produce_once() builds + saves
each one through the atomic store. The scheduler adds nothing modelling-wise; it
is pure orchestration + a heartbeat so a watching process (or the frontend) can
see liveness.

FULLY INJECTABLE for offline tests (no real time, no network, no corpus):
  * produce_fn(sport, *, out_dir) -> path-or-envelope : replaces produce_once.
  * now_fn() -> float epoch seconds                   : replaces time.time.
  * clock                                             : a Clock with now()/sleep()
        so serve_forever() can run N ticks against a FAKE clock that never sleeps.

Per-sport isolation: one sport raising inside run_cycle() is caught and recorded
as status='error' in the heartbeat; the other sports still run. The heartbeat is
written ATOMICALLY (tmp + os.replace) so a reader never sees a torn file.

HONESTY: no $ edge is produced or implied here (see predict_service.contracts);
the scheduler only times + persists the existing calibrated snapshots.

INVARIANTS: build only under predict_service/; never edit src/ or kernel/; reuse
produce_once + registry; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from predict_service import produce, registry, store

logger = logging.getLogger(__name__)

ProduceFn = Callable[..., Any]
NowFn = Callable[[], float]

_HEARTBEAT_NAME = "_heartbeat.json"

# Default per-sport cadence (seconds). Any sport not listed uses DEFAULT_INTERVAL.
DEFAULT_INTERVAL = 1200
_SPORT_INTERVALS: Dict[str, int] = {
    "nba": 600,
    "mlb": 900,
    "soccer": 1200,
    "soccer_intl": 1800,
    "tennis": 900,
}


def heartbeat_path(out_dir: Optional[Union[str, Path]] = None) -> Path:
    """Path to the scheduler heartbeat under the store base dir."""
    return store.base_dir(out_dir) / _HEARTBEAT_NAME


def sport_interval(sport: str) -> int:
    """Per-sport cadence in seconds (falls back to DEFAULT_INTERVAL)."""
    return int(_SPORT_INTERVALS.get(str(sport).lower(), DEFAULT_INTERVAL))


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write *payload* as JSON to *path* atomically (tmp + fsync + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, default=str, ensure_ascii=True, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def read_heartbeat(out_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Load the heartbeat dict. Missing/corrupt -> {}. NEVER raises."""
    path = heartbeat_path(out_dir)
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001 -- an unreadable heartbeat is just empty
        logger.warning("read_heartbeat failed: %s", exc)
        return {}


def _run_one(sport: str, produce_fn: ProduceFn,
             out_dir: Optional[Union[str, Path]]) -> Dict[str, Any]:
    """Produce one sport, returning a per-sport heartbeat entry. NEVER raises.

    'ok' carries the saved status (an 'unavailable' snapshot is still a clean run
    -- the producer correctly persists the sentinel). 'error' carries the
    exception type only (no traceback / no secrets in the heartbeat).
    """
    try:
        result = produce_fn(sport, out_dir=out_dir)
        snap_status = "ok"
        try:
            env = store.read_latest(sport, out_dir=out_dir)
            snap_status = env.status
        except Exception:  # noqa: BLE001 -- read-back is best-effort only
            snap_status = "ok"
        return {
            "status": "ok",
            "snapshot_status": snap_status,
            "result": str(result),
        }
    except Exception as exc:  # noqa: BLE001 -- one bad sport must not stop others
        logger.warning("scheduler: produce failed for %s: %s", sport, exc)
        return {"status": "error", "error": type(exc).__name__}


def run_cycle(sports: Optional[List[str]] = None, *,
              out_dir: Optional[Union[str, Path]] = None,
              produce_fn: Optional[ProduceFn] = None,
              now_fn: Optional[NowFn] = None) -> Dict[str, Any]:
    """Run ONE production cycle over *sports* (default: registry.active_sports()).

    Each sport is produced in isolation; a raising sport is caught and recorded as
    status='error' so the remaining sports still run. The heartbeat is refreshed
    atomically with a per-sport last_ok timestamp + status and an overall summary.
    Returns the heartbeat payload that was written. NEVER raises.
    """
    produce_fn = produce_fn or produce.produce_once
    now_fn = now_fn or time.time
    if sports is None:
        try:
            sports = registry.active_sports()
        except Exception:  # noqa: BLE001 -- a registry failure -> empty cycle
            sports = []

    ts = float(now_fn())
    prior = read_heartbeat(out_dir)
    prior_sports = prior.get("sports") if isinstance(prior, dict) else None
    prior_sports = prior_sports if isinstance(prior_sports, dict) else {}

    entries: Dict[str, Any] = {}
    ok_count = 0
    for sport in sports:
        sport = str(sport).lower()
        entry = _run_one(sport, produce_fn, out_dir)
        last_ok = prior_sports.get(sport, {}).get("last_ok")
        if entry["status"] == "ok":
            entry["last_ok"] = ts
            ok_count += 1
        else:
            # keep the previous successful timestamp if there was one
            entry["last_ok"] = last_ok if isinstance(last_ok, (int, float)) else None
        entry["last_run"] = ts
        entries[sport] = entry

    payload = {
        "updated_at": ts,
        "cycle_count": int(prior.get("cycle_count", 0)) + 1,
        "sports_run": list(entries.keys()),
        "ok": ok_count,
        "errors": len(entries) - ok_count,
        "sports": entries,
        "note": "calibrated-snapshot scheduler; no $ edge",
    }
    _atomic_write_json(heartbeat_path(out_dir), payload)
    return payload


def _write_start_beat(out_dir: Optional[Union[str, Path]] = None,
                      now_fn: Optional[NowFn] = None) -> None:
    """Stamp an immediate boot heartbeat BEFORE the first cycle runs (m13
    two-layer-HB pattern, memory project_m13_flap_fix_2026_06_26).

    A freshly restarted process otherwise inherits whatever updated_at a prior
    crash left in the heartbeat file; if cycle 1 is slow (e.g. a provider 429
    boot storm), the supervisor's HEARTBEAT readiness probe judges that stale
    timestamp against fresh_sec and kills the process before it ever completes
    a cycle. Stamping updated_at=now here (same payload shape, prior per-sport
    data preserved, only the note marks it a boot-beat) gives the first cycle
    the full fresh_sec window. run_cycle()'s own beat then supersedes this on
    completion. Never raises.
    """
    now_fn = now_fn or time.time
    prior = read_heartbeat(out_dir)
    payload = dict(prior) if isinstance(prior, dict) else {}
    payload.update({
        "updated_at": float(now_fn()),
        "cycle_count": int(payload.get("cycle_count", 0) or 0),
        "sports_run": payload.get("sports_run", []) or [],
        "ok": int(payload.get("ok", 0) or 0),
        "errors": int(payload.get("errors", 0) or 0),
        "sports": payload.get("sports", {}) or {},
        "note": "boot-beat: process started, first cycle not yet complete (no $ edge)",
    })
    try:
        _atomic_write_json(heartbeat_path(out_dir), payload)
    except Exception as exc:  # noqa: BLE001 -- a failed boot beat must not crash startup
        logger.debug("scheduler: start beat write failed: %s", exc)


class Clock:
    """Injectable wall clock. Default uses real time; tests pass a fake one.

    A fake clock advances now() only when its sleep() is called (or via tick),
    so serve_forever() can run N iterations with NO real waiting.
    """

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, float(seconds)))


def _due(sport: str, now: float, last_run: Dict[str, float]) -> bool:
    """True when *sport* is due to run again given its per-sport cadence."""
    prev = last_run.get(sport)
    if prev is None:
        return True
    return (now - prev) >= float(sport_interval(sport))


def serve_forever(interval: int = DEFAULT_INTERVAL, *,
                  clock: Optional[Clock] = None,
                  out_dir: Optional[Union[str, Path]] = None,
                  produce_fn: Optional[ProduceFn] = None,
                  sports: Optional[List[str]] = None,
                  max_ticks: Optional[int] = None) -> int:
    """Loop: every *interval* seconds run a cycle for the sports that are due.

    *clock* is fully injectable (now()/sleep()); the tested path never touches
    real time. Per-sport cadence is honoured: a sport runs only when its own
    interval has elapsed since its last run. *max_ticks* bounds the loop for
    tests (None = run forever). Returns the number of ticks executed.
    """
    clock = clock or Clock()
    _write_start_beat(out_dir, now_fn=clock.now)
    last_run: Dict[str, float] = {}
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        now = float(clock.now())
        if sports is None:
            try:
                candidates = registry.active_sports()
            except Exception:  # noqa: BLE001
                candidates = []
        else:
            candidates = list(sports)
        due = [s for s in candidates if _due(str(s).lower(), now, last_run)]
        if due:
            run_cycle(due, out_dir=out_dir, produce_fn=produce_fn,
                      now_fn=clock.now)
            for s in due:
                last_run[str(s).lower()] = now
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        clock.sleep(float(interval))
    return ticks


def main(argv: Optional[List[str]] = None) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(
        prog="predict_service.scheduler",
        description="Always-on producer scheduler (refresh all active sports).")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    ap.add_argument("--out-dir", default=None, dest="out_dir")
    ap.add_argument("--once", action="store_true",
                    help="run a single cycle and exit (no loop).")
    a = ap.parse_args(argv)
    if a.once:
        hb = run_cycle(out_dir=a.out_dir)
        print("cycle=%d ok=%d errors=%d sports=%s" % (
            hb["cycle_count"], hb["ok"], hb["errors"], ",".join(hb["sports_run"])))
        return 0
    serve_forever(interval=a.interval, out_dir=a.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
