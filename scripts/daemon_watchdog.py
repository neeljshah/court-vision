"""daemon_watchdog.py — R19_L3 watchdog for the 14 always-on daemons.

Reads ``scripts/daemon_registry.json``.  Every ``--check-interval-sec`` seconds
it walks the registered daemons and asks two questions per daemon:

  1. Is the heartbeat file fresh enough?
     (mtime newer than ``expected_interval_sec * STALE_MULTIPLIER``)
  2. Is there a live process matching ``process_match``?

If either check fails (heartbeat stale OR process gone), the daemon is
considered dead.  The watchdog then:

  * Appends a row to ``vault/Improvements/daemon_restarts.md``.
  * Fires a Discord ``WARN`` alert via ``src.alerts.discord_webhook.post_alert``.
  * Re-launches the daemon by shelling out ``restart_cmd`` (already wrapped in
    nohup/tmux by the registry).
  * Records the restart timestamp in an in-memory bucket so the daemon
    can't be restarted more than ``--max-restarts-per-hour`` (default 3)
    times per rolling 60-min window.

Design rules
------------
* Stdlib-only.  No external deps beyond ``src.alerts.discord_webhook``.
* All restart actions are wrapped in try/except — a single bad daemon must
  never crash the watchdog itself.
* ``--once`` does a single pass and exits (used by the unit test + probe).
* ``--dry-run`` logs what it WOULD restart without actually shelling out.

CLI
---
    python scripts/daemon_watchdog.py --once
    python scripts/daemon_watchdog.py --check-interval-sec 60
    python scripts/daemon_watchdog.py --once --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Mapping, Optional, Tuple

# Make sure we can import src.alerts.* whether invoked from project root or not.
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

try:  # noqa: SIM105 — keep import optional so unit tests can monkeypatch
    from src.alerts.discord_webhook import post_alert as _post_alert
except Exception:  # pragma: no cover — fallback no-op if alerts module missing
    def _post_alert(**_kwargs: Any) -> bool:  # type: ignore[misc]
        return False

log = logging.getLogger("daemon_watchdog")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALE_MULTIPLIER = 3.0  # heartbeat older than expected_interval * 3 == dead
RATE_LIMIT_WINDOW_SEC = 3600  # 1 hour
DEFAULT_MAX_RESTARTS_PER_HOUR = 3
DEFAULT_CHECK_INTERVAL_SEC = 60
DEFAULT_REGISTRY_PATH = os.path.join(_PROJECT_DIR, "scripts", "daemon_registry.json")
DEFAULT_RESTART_LOG = os.path.join(_PROJECT_DIR, "vault", "Improvements", "daemon_restarts.md")

_RUNNING = True


def _handle_sig(signum: int, _frame: Any) -> None:  # pragma: no cover
    global _RUNNING
    log.info("watchdog received signal %s — shutting down", signum)
    _RUNNING = False


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------

def load_registry(path: str = DEFAULT_REGISTRY_PATH) -> List[Dict[str, Any]]:
    """Load daemon entries from ``daemon_registry.json``."""
    with open(path, "r", encoding="utf-8") as fh:
        blob = json.load(fh)
    daemons = blob.get("daemons", [])
    if not isinstance(daemons, list):
        raise ValueError("daemon_registry.json: 'daemons' must be a list")
    return daemons


# ---------------------------------------------------------------------------
# Health checks (pure-ish; injectable for tests)
# ---------------------------------------------------------------------------

def _heartbeat_age_sec(heartbeat_file: str, now: Optional[float] = None) -> Optional[float]:
    """Return age (seconds) of heartbeat file mtime, or None if missing."""
    if not os.path.exists(heartbeat_file):
        return None
    mtime = os.path.getmtime(heartbeat_file)
    return (now if now is not None else time.time()) - mtime


def _process_alive(process_match: str, ps_runner: Optional[Any] = None) -> bool:
    """Check via ``ps`` if any process command-line matches ``process_match``.

    ``ps_runner`` is a hook for unit tests; defaults to subprocess.run.
    """
    if ps_runner is None:
        try:
            out = subprocess.run(
                ["ps", "-eo", "pid,cmd", "--no-headers"],
                capture_output=True, text=True, timeout=5, check=False,
            ).stdout
        except Exception as exc:  # noqa: BLE001
            log.warning("ps failed: %r — assuming process alive (fail-open)", exc)
            return True
    else:
        out = ps_runner()
    for line in out.splitlines():
        if process_match in line and "daemon_watchdog" not in line:
            return True
    return False


def check_daemon(daemon: Mapping[str, Any], *, now: Optional[float] = None,
                 ps_runner: Optional[Any] = None) -> Dict[str, Any]:
    """Return a status dict for one daemon.

    Keys: name, heartbeat_age_sec, heartbeat_stale, process_alive, dead, reason.
    """
    name = daemon["name"]
    expected = float(daemon.get("expected_interval_sec", 60))
    hb_path = os.path.join(_PROJECT_DIR, daemon["heartbeat_file"]) \
        if not os.path.isabs(daemon["heartbeat_file"]) else daemon["heartbeat_file"]
    age = _heartbeat_age_sec(hb_path, now=now)
    hb_optional = bool(daemon.get("heartbeat_optional", False))
    if age is None:
        heartbeat_stale = not hb_optional  # missing only matters if NOT optional
        reason_hb = "heartbeat_missing" if heartbeat_stale else "heartbeat_optional_missing"
    else:
        heartbeat_stale = age > expected * STALE_MULTIPLIER
        reason_hb = f"heartbeat_age={age:.0f}s>limit={expected * STALE_MULTIPLIER:.0f}s" \
            if heartbeat_stale else "heartbeat_ok"
    proc_alive = _process_alive(daemon.get("process_match", name), ps_runner=ps_runner)
    # Dead iff process is gone OR heartbeat is stale (a wedged process with a
    # frozen heartbeat is still a problem).  For heartbeat_optional daemons,
    # we trust only the process check.
    if hb_optional:
        dead = not proc_alive
    else:
        dead = (not proc_alive) or heartbeat_stale
    if not dead:
        reason = "ok"
    elif not proc_alive and heartbeat_stale:
        reason = f"process_gone+{reason_hb}"
    elif not proc_alive:
        reason = "process_gone"
    else:
        reason = reason_hb
    return {
        "name": name,
        "heartbeat_age_sec": age,
        "heartbeat_stale": heartbeat_stale,
        "process_alive": proc_alive,
        "dead": dead,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RestartRateLimiter:
    """Per-daemon sliding-window rate limiter (default: 3 restarts / hour)."""

    def __init__(self, max_per_hour: int = DEFAULT_MAX_RESTARTS_PER_HOUR) -> None:
        self.max_per_hour = max_per_hour
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, name: str, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        bucket = self._buckets[name]
        # Evict timestamps outside the rolling window.
        while bucket and (now - bucket[0]) > RATE_LIMIT_WINDOW_SEC:
            bucket.popleft()
        if len(bucket) >= self.max_per_hour:
            return False
        bucket.append(now)
        return True

    def restarts_in_window(self, name: str, now: Optional[float] = None) -> int:
        now = now if now is not None else time.time()
        bucket = self._buckets[name]
        while bucket and (now - bucket[0]) > RATE_LIMIT_WINDOW_SEC:
            bucket.popleft()
        return len(bucket)


# ---------------------------------------------------------------------------
# Restart actions
# ---------------------------------------------------------------------------

def _append_restart_log(log_path: str, name: str, reason: str,
                        rc: Optional[int], restart_cmd: str) -> None:
    """Append a markdown row to vault/Improvements/daemon_restarts.md."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    write_header = not os.path.exists(log_path)
    with open(log_path, "a", encoding="utf-8") as fh:
        if write_header:
            fh.write("# Daemon Restarts (R19_L3 watchdog)\n\n")
            fh.write("Auto-generated log of daemon restart events.\n\n")
            fh.write("| timestamp_utc | daemon | reason | rc | restart_cmd |\n")
            fh.write("|---|---|---|---|---|\n")
        rc_str = "n/a" if rc is None else str(rc)
        # markdown-escape any pipes in the cmd so the table stays valid
        safe_cmd = restart_cmd.replace("|", "\\|")
        fh.write(f"| {_iso_now()} | {name} | {reason} | {rc_str} | `{safe_cmd}` |\n")


def restart_daemon(daemon: Mapping[str, Any], *, dry_run: bool = False,
                   shell_runner: Optional[Any] = None) -> Tuple[bool, Optional[int]]:
    """Shell out the daemon's ``restart_cmd``.  Returns (success, rc)."""
    cmd = daemon.get("restart_cmd")
    if not cmd:
        log.error("daemon %s has no restart_cmd in registry", daemon.get("name"))
        return False, None
    if dry_run:
        log.info("DRY-RUN: would restart %s via %s", daemon["name"], cmd)
        return True, 0
    runner = shell_runner or (lambda c: subprocess.run(
        c, shell=True, capture_output=True, text=True, timeout=30, check=False,
    ))
    try:
        res = runner(cmd)
        rc = getattr(res, "returncode", 0)
        ok = rc == 0
        if not ok:
            log.warning("restart_cmd for %s exited rc=%s stderr=%s",
                        daemon["name"], rc, getattr(res, "stderr", "")[:200])
        return ok, rc
    except Exception as exc:  # noqa: BLE001
        log.exception("restart_cmd for %s raised: %r", daemon["name"], exc)
        return False, None


def fire_discord_alert(name: str, reason: str, rc: Optional[int],
                       *, post_alert_fn: Optional[Any] = None) -> bool:
    """Send a WARN-severity Discord push.  Never raises."""
    fn = post_alert_fn or _post_alert
    try:
        return bool(fn(
            severity="WARN",
            source="daemon_watchdog",
            title=f"Daemon RESTARTED — {name}",
            body=f"reason: {reason}\nrestart_rc: {rc}\nwatchdog: R19_L3",
            fields=[
                {"name": "daemon", "value": name},
                {"name": "reason", "value": reason},
                {"name": "rc",     "value": "n/a" if rc is None else str(rc)},
            ],
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("Discord post_alert failed: %r", exc)
        return False


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def sweep(registry: List[Dict[str, Any]], limiter: RestartRateLimiter, *,
          dry_run: bool = False, restart_log_path: str = DEFAULT_RESTART_LOG,
          ps_runner: Optional[Any] = None, shell_runner: Optional[Any] = None,
          post_alert_fn: Optional[Any] = None,
          now: Optional[float] = None) -> Dict[str, Any]:
    """One sweep across every registered daemon.

    Returns a summary dict so callers (probe + tests) can assert behaviour.
    """
    statuses: List[Dict[str, Any]] = []
    restarts: List[Dict[str, Any]] = []
    rate_limited: List[str] = []
    for daemon in registry:
        status = check_daemon(daemon, now=now, ps_runner=ps_runner)
        statuses.append(status)
        if not status["dead"]:
            continue
        if not limiter.allow(status["name"], now=now):
            rate_limited.append(status["name"])
            log.warning("RATE-LIMIT: %s already restarted %s times in last hour",
                        status["name"], limiter.restarts_in_window(status["name"], now=now))
            continue
        ok, rc = restart_daemon(daemon, dry_run=dry_run, shell_runner=shell_runner)
        discord_ok = fire_discord_alert(status["name"], status["reason"], rc,
                                        post_alert_fn=post_alert_fn)
        try:
            _append_restart_log(restart_log_path, status["name"], status["reason"],
                                rc, daemon.get("restart_cmd", ""))
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to append restart log: %r", exc)
        restarts.append({
            "name": status["name"],
            "reason": status["reason"],
            "restart_ok": ok,
            "rc": rc,
            "discord_fired": discord_ok,
        })
    return {
        "ts": _iso_now(),
        "checked": len(statuses),
        "dead": [s["name"] for s in statuses if s["dead"]],
        "restarted": restarts,
        "rate_limited": rate_limited,
        "statuses": statuses,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="R19_L3 daemon watchdog")
    ap.add_argument("--registry", type=str, default=DEFAULT_REGISTRY_PATH)
    ap.add_argument("--check-interval-sec", type=int, default=DEFAULT_CHECK_INTERVAL_SEC)
    ap.add_argument("--max-restarts-per-hour", type=int, default=DEFAULT_MAX_RESTARTS_PER_HOUR)
    ap.add_argument("--restart-log", type=str, default=DEFAULT_RESTART_LOG)
    ap.add_argument("--once", action="store_true", help="single sweep + exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="log restarts without shelling out")
    ap.add_argument("--log-level", type=str, default="INFO")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    try:
        registry = load_registry(args.registry)
    except Exception as exc:  # noqa: BLE001
        log.error("failed to load registry %s: %r", args.registry, exc)
        return 2
    log.info("watchdog start: %d daemons registered, interval=%ss, dry_run=%s",
             len(registry), args.check_interval_sec, args.dry_run)

    limiter = RestartRateLimiter(max_per_hour=args.max_restarts_per_hour)
    tick = 0
    while _RUNNING:
        tick += 1
        t0 = time.time()
        try:
            summary = sweep(registry, limiter, dry_run=args.dry_run,
                            restart_log_path=args.restart_log)
            log.info("tick=%d checked=%d dead=%s restarted=%d rate_limited=%d",
                     tick, summary["checked"], summary["dead"],
                     len(summary["restarted"]), len(summary["rate_limited"]))
        except Exception as exc:  # noqa: BLE001
            log.exception("sweep raised: %r", exc)
        if args.once:
            break
        # Sleep, but stay responsive to signals.
        end = t0 + args.check_interval_sec
        while _RUNNING and time.time() < end:
            time.sleep(min(0.5, end - time.time()))
    log.info("watchdog exited cleanly after %d ticks", tick)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
