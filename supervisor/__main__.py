"""supervisor.__main__ -- live CLI entrypoint for the always-on supervisor.

boot.ps1 (and the posix path) launch this as the supervised always-on parent::

    python -u -m supervisor [--profile NAME] [--max-cycles N]

It boots the full stack (dependency-ordered, readiness-gated), supervises with
auto-restart + backoff, writes data/frontend/ops/supervisor_status.json each
tick, and drains gracefully on Ctrl-C / CTRL_BREAK / SIGTERM.

Pass --dry-run to print the planned process graph and exit without spawning
anything (used by boot.ps1 -DryRun so the plan is always in sync with the
manifest -- no copy-paste drift).

Uses the REAL socket/urllib readiness fetcher (health.real_fetcher). Tests never
exercise this module -- they drive supervisor.Supervisor directly with fakes.

Stdlib-only, ASCII-only. Never writes data/registry/; never flips a flag on.
"""
from __future__ import annotations

import argparse
import logging
import signal
from typing import Any, List, Optional

from supervisor import _singleton
from supervisor.config import load_profile
from supervisor.health import real_fetcher
from supervisor.supervisor import Supervisor

logger = logging.getLogger("supervisor.main")

_PROBE_LABEL = {
    "tcp-port-open":       "tcp",
    "http-200":            "http-200",
    "heartbeat-file-fresh": "heartbeat",
    "none":                "alive",
}


def _dry_run(profile: str) -> int:
    """Print the planned process graph and return 0. No spawning, no I/O."""
    bp = load_profile(profile)
    specs = bp.specs()
    print("")
    print("M9 supervisor -- dry-run plan")
    print("  profile   : %s  (source: %s)" % (bp.profile, bp.source))
    print("  log_dir   : %s" % bp.log_dir)
    if bp.global_env:
        for k, v in bp.global_env.items():
            print("  env       : %s=%s" % (k, v))
    print("  processes : %d" % len(specs))
    print("")
    for i, spec in enumerate(specs, 1):
        port_str = (":%d" % spec.port) if spec.port else ""
        dep_str  = (" depends_on=[%s]" % ",".join(spec.depends_on)
                    ) if spec.depends_on else ""
        kind_str = ("python -m %s" % spec.module
                    ) if spec.kind == "py" else spec.cmd
        argv_str = (" " + " ".join(spec.argv)) if spec.argv else ""
        probe    = _PROBE_LABEL.get(spec.readiness.kind, spec.readiness.kind)
        probe_detail = ""
        if spec.readiness.kind == "http-200":
            probe_detail = " path=%s" % spec.readiness.http_path
        elif spec.readiness.kind == "heartbeat-file-fresh":
            probe_detail = " file=%s fresh=%ss" % (
                spec.readiness.heartbeat_path, int(spec.readiness.fresh_sec))
        elif spec.readiness.kind == "tcp-port-open":
            probe_detail = " port=%s" % (port_str.lstrip(":") or "?")
        retry_str = ("forever" if spec.restart_policy.max_retries is None
                     else str(spec.restart_policy.max_retries))
        print("  [%d] %s%s%s" % (i, spec.name, port_str, dep_str))
        print("       launch  : %s%s" % (kind_str, argv_str))
        print("       ready   : %s%s" % (probe, probe_detail))
        print("       restart : %s  backoff=%.0f-%.0fs" % (
            retry_str,
            spec.restart_policy.backoff_base_sec,
            spec.restart_policy.backoff_cap_sec))
        print("       log     : logs/%s.out / .err" % spec.name)
        print("")
    print("Dependency order (topo-sorted by manifest):")
    chain = " --> ".join(s.name for s in specs)
    print("  %s" % chain)
    print("")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Boot + supervise forever. Returns a process exit code."""
    parser = argparse.ArgumentParser(description="M9 always-on supervisor")
    parser.add_argument("--profile", default="default",
                        help="boot profile (config/boot/<name>.json)")
    parser.add_argument("--max-cycles", type=int, default=None,
                        help="bound the supervise loop (default: run forever)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the planned process graph and exit "
                             "(no spawning; used by boot.ps1 -DryRun)")
    args = parser.parse_args(argv)

    if args.dry_run:
        return _dry_run(args.profile)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # SINGLE-INSTANCE GUARD: never run two supervisors at once. Each one's
    # reconcile_survivors() kills the other's freshly-spawned children, so a
    # racing boot (watchdog poll + manual boot, or overlapping launchers) flaps
    # forever on ports :8099/:8098/:3000. The OS lock makes the race
    # deterministic -- the loser exits; the winner owns the stack. A dead
    # predecessor releases its lock automatically, so a normal reboot is clean.
    # Keep _lock referenced so the fd stays open (= lock held) for the run.
    _lock = _singleton.acquire()  # noqa: F841 -- held for process lifetime
    if _lock is None:
        logger.warning(
            "supervisor: another live supervisor holds the single-instance "
            "lock -- exiting (refusing to boot a duplicate)")
        return 0

    sv = Supervisor(args.profile, fetcher=real_fetcher)
    # Stamp self-liveness IMMEDIATELY, before the (up-to-~30s) boot() inside
    # run_forever. Otherwise the autostart watchdog -- which declares a supervisor
    # WEDGED when its heartbeat is stale > 90s -- false-fires during the boot
    # window (the first _beat_self only runs AFTER boot completes) and launches a
    # duplicate. An early beat makes a booting supervisor look alive + ticking.
    sv._beat_self()

    def _graceful(_signum: int, _frame: Any) -> None:
        logger.info("supervisor: signal received -- draining")
        sv.drain()
        raise SystemExit(0)

    for _name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        num = getattr(signal, _name, None)
        if num is None:
            continue
        try:
            signal.signal(num, _graceful)
        except (ValueError, OSError):  # not in main thread / unsupported
            pass

    logger.info("supervisor: booting profile=%s status=%s",
                args.profile, "data/frontend/ops/supervisor_status.json")
    try:
        sv.run_forever(max_cycles=args.max_cycles)
    except SystemExit:
        return 0
    except KeyboardInterrupt:
        sv.drain()
        return 0
    sv.drain()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
