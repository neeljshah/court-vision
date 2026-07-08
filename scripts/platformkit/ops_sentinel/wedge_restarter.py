"""scripts.platformkit.ops_sentinel.wedge_restarter -- persistent output-freshness
RED -> a rate-limited RESTART_REQUEST for the supervisor to honor (M40).

m29 output_freshness marks a daemon RED when its output artifact goes stale (the
ALIVE-but-WEDGED case: process up + heartbeat fresh, but real output stopped
advancing). Neither the supervisor (restarts only DEAD procs) nor heartbeat_reaper
(only STALE-HEARTBEAT procs) acts on that. This detector reads output_freshness
.json; a daemon RED for >=RED_THRESHOLD CONSECUTIVE ticks gets ONE RESTART_REQUEST
row appended to data/frontend/ops/restart_requests.jsonl, which the supervisor's
pickup seam (supervisor._restart.process_restart_requests) honors -- itself rate-
limited + protected-safe, so this detector is REQUEST-ONLY.

Rails: protected daemons (m9/m33/m34/m38 + m40 itself) are never requested; a
per-daemon COOLDOWN prevents a storm; a non-RED read resets the streak. Never
raises; no $ field; no flag flip; no data/registry/ write. Cadence 300s (mirrors
m29). Heartbeat m40_wedge_restarter; state wedge_restarter_state.json.
Per-file test: test_wedge_restarter.py. stdlib + repo-internal; ASCII only.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("wedge_restarter")

_REPO = Path(__file__).resolve().parents[3]
_OPS = _REPO / "data" / "frontend" / "ops"

STATE_PATH = _OPS / "wedge_restarter_state.json"
REQUEST_PATH = _OPS / "restart_requests.jsonl"

HEARTBEAT_COMPONENT = "m40_wedge_restarter"
COMPONENT = "m40_wedge_restarter"
DEFAULT_INTERVAL_SEC = 300.0

RED = "RED"
RED_THRESHOLD = 3          # consecutive RED reads before a request is emitted
COOLDOWN_SEC = 1800.0      # min seconds between two requests for the SAME daemon

# Reliability sentinels + the supervisor itself: never auto-bounced (the supervisor
# pickup guards the same set -- belt + suspenders).
PROTECTED = frozenset({"m9_supervisor", "m33_http_wedge_reaper",
                       "m34_freshness_sla", "m38_autoloop", "m40_wedge_restarter"})


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M40 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("wedge_restarter heartbeat skipped: %s", exc)


def _load_state(path: Optional[Path] = None) -> Dict[str, Any]:
    """Best-effort read of the persisted state. Missing/bad -> empty. Never raises."""
    try:
        p = Path(path) if path is not None else STATE_PATH
        if not p.exists():
            return {}
        doc = json.loads(p.read_text(encoding="ascii"))
        return doc if isinstance(doc, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_state(state: Dict[str, Any], path: Optional[Path] = None) -> bool:
    """Atomically persist state (tmp + os.replace). Never raises."""
    try:
        p = Path(path) if path is not None else STATE_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(p))
        return True
    except Exception:  # noqa: BLE001
        return False


def _append_request(row: Dict[str, Any], path: Optional[Path] = None) -> bool:
    """Append one RESTART_REQUEST row (JSONL). Never raises."""
    try:
        p = Path(path) if path is not None else REQUEST_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="ascii") as fh:
            fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
        return True
    except Exception:  # noqa: BLE001
        return False


def evaluate(rows: List[Dict[str, Any]], state: Dict[str, Any], *, now: float,
             threshold: int = RED_THRESHOLD,
             cooldown_sec: float = COOLDOWN_SEC,
             ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """PURE: given output-freshness rows + prior state, return (requests, new_state).
    RED increments a daemon's consecutive-red streak; any non-RED read resets it. A
    streak reaching *threshold* emits ONE request (unless protected or inside its
    per-daemon cooldown), then resets the streak. Never raises."""
    counts: Dict[str, int] = dict(state.get("consecutive_red", {}) or {})
    last_req: Dict[str, float] = dict(state.get("last_request_ts", {}) or {})
    present: set = set()
    requests: List[Dict[str, Any]] = []
    try:
        for r in rows or []:
            name = r.get("name")
            if not name:
                continue
            present.add(name)
            counts[name] = counts.get(name, 0) + 1 if r.get("status") == RED else 0
        # Forget daemons no longer reported (a dropped row must not read stale-RED).
        counts = {k: v for k, v in counts.items() if k in present}
        for name, streak in counts.items():
            if streak < threshold or name in PROTECTED:
                continue
            if name in last_req and now - float(last_req[name]) < cooldown_sec:
                continue  # cooldown only applies relative to a PRIOR request
            requests.append({
                "ts": now, "daemon": name, "reason": "output_freshness_red",
                "consecutive_red": streak, "source": COMPONENT,
            })
            last_req[name] = now
            counts[name] = 0  # reset after requesting -> natural rate cap
    except Exception:  # noqa: BLE001 -- evaluation must never raise
        pass
    new_state = {"consecutive_red": counts, "last_request_ts": last_req,
                 "updated_at": now}
    return requests, new_state


def tick(*, now: float,
         load_rows_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
         state_path: Optional[Path] = None,
         request_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read freshness rows -> evaluate streaks -> emit requests -> persist state ->
    heartbeat. Never raises. Returns the requests emitted."""
    if load_rows_fn is None:
        from scripts.platformkit.ops_sentinel.output_freshness import load_status
        load_rows_fn = load_status
    try:
        rows = list(load_rows_fn() or [])
    except Exception as exc:  # noqa: BLE001
        logger.debug("wedge_restarter load rows raised: %s", exc)
        rows = []
    state = _load_state(state_path)
    requests, new_state = evaluate(rows, state, now=now)
    for req in requests:
        _append_request(req, request_path)
        logger.warning("wedge_restarter: RESTART_REQUEST emitted for wedged %s "
                       "(consecutive_red=%s)", req.get("daemon"), req.get("consecutive_red"))
    _save_state(new_state, state_path)
    _beat(now)
    return requests


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the loop forever (or max_ticks). Never raises out. Returns ticks run."""
    _clock = clock if clock is not None else time.time
    _sleep = sleep if sleep is not None else time.sleep
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
            now = time.time()
        reqs = tick(now=now)
        print("%s | tick=%d requests=%d" % (COMPONENT, ticks, len(reqs)), flush=True)
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
        description="Supervised wedge-restarter (M40): persistent output-freshness "
                    "RED -> rate-limited RESTART_REQUEST. Request-only, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("wedge_restarter | started interval=%ss component=%s"
          % (a.interval, COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("wedge_restarter | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
