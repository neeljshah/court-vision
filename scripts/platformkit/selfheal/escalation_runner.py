"""scripts.platformkit.selfheal.escalation_runner -- supervised M16 entry.

A MEASUREMENT-ONLY daemon that, every ~60s:
  1. Reads data/frontend/ops/autonomy_status.json services[] (read-only).
  2. Calls escalation_ladder.tick() to update per-daemon consecutive-stale streaks.
  3. Persists state to data/cache/selfheal_streaks.json (atomic write).
  4. Writes an advisory feed to data/frontend/ops/escalation_feed.json (atomic).
  5. Beats a liveness heartbeat as component ``m16_escalation``.

PURE ADVICE: this runner NEVER calls proc.restart, NEVER mutates stack_specs,
NEVER flips a feature flag, NEVER authorises real money.  The feed is consumed
by a human or orchestrator that decides whether to act.

SAFETY INVARIANTS
-----------------
  * MEASUREMENT-ONLY header; no $ field; no "action"/"command" key in feed.
  * Atomic writes (tmp + os.replace): readers never see torn files.
  * Never raises out of run() -- all errors degrade to safe stubs.
  * Heartbeat always fires (even on read/parse failure) so the monitor can
    distinguish "runner alive, source missing" from "runner dead".
  * Injectable clock/sleep/max_ticks/paths for deterministic offline tests.
  * <=300 LOC; ASCII only; stdlib only.

Heartbeat component: ``m16_escalation``
  -> data/cache/daemon_heartbeats/m16_escalation.txt

Per-file test:
    python -m pytest tests/platformkit/selfheal/test_escalation_runner.py -q
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("escalation_runner")

HEARTBEAT_COMPONENT = "m16_escalation"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_AUTONOMY_PATH = _REPO / "data" / "frontend" / "ops" / "autonomy_status.json"
_STREAKS_PATH = _REPO / "data" / "cache" / "selfheal_streaks.json"
_FEED_PATH = _REPO / "data" / "frontend" / "ops" / "escalation_feed.json"

DEFAULT_INTERVAL_SEC = 60.0


# ---------------------------------------------------------------------------
# Helpers -- I/O (never raise)
# ---------------------------------------------------------------------------

def _beat(now_epoch: Optional[float] = None) -> None:
    """Write liveness heartbeat for m16_escalation. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("escalation_runner heartbeat skipped: %s", exc)


def _utc_iso(ts: Optional[float] = None) -> str:
    dt = (datetime.fromtimestamp(ts, tz=timezone.utc)
          if ts is not None
          else datetime.now(timezone.utc))
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_services(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Read services[] from autonomy_status.json. Returns [] on any error."""
    try:
        raw = path.read_text(encoding="utf-8")
        doc = json.loads(raw)
        return doc.get("services", []) or []
    except Exception as exc:  # noqa: BLE001
        logger.debug("escalation_runner: could not read autonomy_status: %s", exc)
        return []


def _load_streaks(path: pathlib.Path) -> Dict[str, Any]:
    """Load streak store from disk. Returns {} on missing/corrupt file."""
    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw) or {}
    except Exception:  # noqa: BLE001
        return {}


def _atomic_write(path: pathlib.Path, doc: Any) -> None:
    """Atomically write *doc* as ASCII JSON to *path*. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, indent=2, ensure_ascii=True, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
    except Exception as exc:  # noqa: BLE001
        logger.debug("escalation_runner: write failed to %s: %s", path, exc)


# ---------------------------------------------------------------------------
# One tick
# ---------------------------------------------------------------------------

def tick(
    *,
    now: float,
    autonomy_path: Optional[pathlib.Path] = None,
    streaks_path: Optional[pathlib.Path] = None,
    feed_path: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """Execute one escalation cycle. Never raises.

    1. Read autonomy_status services[].
    2. Update streak store via escalation_ladder.tick().
    3. Persist updated streaks to selfheal_streaks.json.
    4. Write escalation_feed.json.
    5. Beat heartbeat.

    Returns the feed document that was written.
    """
    from scripts.platformkit.selfheal.escalation_ladder import tick as _ladder_tick
    from scripts.platformkit.selfheal.escalation_ladder import build_feed

    ap = autonomy_path or _AUTONOMY_PATH
    sp = streaks_path or _STREAKS_PATH
    fp = feed_path or _FEED_PATH
    now_iso = _utc_iso(now)

    services = _read_services(ap)
    streaks = _load_streaks(sp)

    new_streaks = _ladder_tick(services, streaks, now_iso=now_iso)

    _atomic_write(sp, new_streaks)

    feed = build_feed(new_streaks, generated_at=now_iso)
    _atomic_write(fp, feed)

    _beat(now)
    return feed


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------

def run(
    *,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
    autonomy_path: Optional[pathlib.Path] = None,
    streaks_path: Optional[pathlib.Path] = None,
    feed_path: Optional[pathlib.Path] = None,
    clock: Optional[Callable[[], float]] = None,
    sleep: Optional[Callable[[float], None]] = None,
    max_ticks: Optional[int] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> int:
    """Run the escalation loop forever (or ``max_ticks`` iterations). Never raises out.

    All I/O paths and timing are injectable for deterministic offline tests.
    Returns the count of ticks completed.

    MEASUREMENT-ONLY: writes escalation_feed.json + selfheal_streaks.json +
    heartbeat only.  Flips no flag, calls no restart, touches no real money.
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
        try:
            tick(
                now=now,
                autonomy_path=autonomy_path,
                streaks_path=streaks_path,
                feed_path=feed_path,
            )
        except Exception as exc:  # noqa: BLE001 -- tick must not crash the loop
            logger.debug("escalation_runner: tick raised (should not happen): %s", exc)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(
        description=(
            "Supervised self-heal escalation runner (M16): tracks consecutive-stale "
            "streaks per daemon and emits RESTART_RECOMMENDED advice. "
            "MEASUREMENT-ONLY -- never restarts anything, flips no flag."
        )
    )
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between ticks (default: %(default)s).")
    a = p.parse_args()
    print(
        "escalation_runner | started interval=%.0fs component=%s feed=%s"
        % (a.interval, HEARTBEAT_COMPONENT, _FEED_PATH),
        flush=True,
    )
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("escalation_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "tick", "run"]
