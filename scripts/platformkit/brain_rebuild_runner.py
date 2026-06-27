"""scripts.platformkit.brain_rebuild_runner -- supervised M14 entry.

A thin, always-on LOOP wrapper around the one-shot brain rebuild
(``brain_pipeline.run_pipeline``) so the M9 supervisor can spawn it as
``python -u -m scripts.platformkit.brain_rebuild_runner`` and keep the organized
Obsidian brain (``vault/_Organized``) freshly rebuilt + FULLY REACHABLE from the
deep ``_vault_legacy_archive`` source -- WITHOUT a self-installing OS scheduler.

WHY a wrapper instead of the pipeline's own ``_main``:
  * ``brain_pipeline._main`` runs EXACTLY ONE rebuild and returns -- it is the
    cron / manual entrypoint. The supervisor only keeps a process ALIVE; an
    always-alive proc that exits after one rebuild would restart-loop hot. This
    wrapper sleeps a declared cadence between rebuilds so a supervised forever-run
    rebuilds at the intended (slow) interval, not in a tight loop.
  * Each boundary beats the ``m14_brain_rebuild`` liveness heartbeat so a hung
    rebuild (no fresh beat) ages out as NOT-READY -- stale-never-green.

SERIALIZED: a rebuild ``rmtree``s + rewrites ``vault/_Organized``. Two concurrent
rebuilds race on the same tree (see the standing "no concurrent brain rebuilds"
rule). This wrapper takes a best-effort lockfile before each rebuild and SKIPS the
tick (still beating liveness) if another rebuild holds a FRESH lock, so a manual
``brain_pipeline`` run and this daemon never rmtree the same tree at once.

The rebuild stays an intelligence MAP, person-free, NO betting edge. The light
default (``with_models=False``) keeps the graph connected + fresh from the archive
WITHOUT the heavy full-corpus model stages; ``--with-models`` opts into the deep
refresh. This wrapper adds NO new math; it only adds liveness + a cadence + a lock.
It NEVER ships, flips a flag, writes ``data/registry/`` or ``MEMORY.md``, arms
autostart / real money / push. NO $ field. stdlib + repo-internal; ASCII; <=300 LOC.

Heartbeat component: ``m14_brain_rebuild`` ->
data/cache/daemon_heartbeats/m14_brain_rebuild.txt (consumed by ops.liveness /
the supervisor heartbeat-fresh readiness probe).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_brain_rebuild_runner.py -q
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger("brain_rebuild_runner")

# Heartbeat component name (mirrors the m14 ProcSpec in supervisor/stack_specs.py).
HEARTBEAT_COMPONENT = "m14_brain_rebuild"

# Declared cadence between rebuilds. The brain's SOURCE (the deep archive + the
# per-sport corpora) moves slowly, so a 6h cadence keeps the graph fresh + fully
# reachable without hogging the box. The supervisor fresh_sec (>2x + margin)
# comfortably exceeds this so a healthy runner reads fresh and a genuinely
# dead/hung rebuild ages out -- never a stale-green.
DEFAULT_INTERVAL_SEC = 21600.0

# A lock is only honored while its WRITER PID is still alive (so a hard-killed rebuild
# -- e.g. the supervisor reaping a mid-rebuild m14 -- never strands the lock). The age
# cap is a belt-and-suspenders safety for the rare case the PID can't be checked: a
# lock older than this is reclaimed regardless. Generous vs a slow --with-models run.
_LOCK_HARD_CAP_SEC = 2400.0
# After a tick is SKIPPED (a live rebuild legitimately holds the lock) retry SOON, not
# after the full 6h cadence, so a transient overlap recovers in minutes not hours.
_RETRY_SEC = 300.0


def _lock_path() -> Path:
    """Best-effort serialization lock shared with manual brain_pipeline runs."""
    return _REPO_ROOT / "data" / "cache" / "daemon_heartbeats" / "m14_brain_rebuild.lock"


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for THIS runner. Never raises."""
    try:
        from ops.liveness import heartbeat  # noqa: PLC0415
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- liveness write must never sink loop
        logger.debug("brain_rebuild_runner heartbeat skipped: %s", exc)


def _pid_alive(pid: int) -> Optional[bool]:
    """Is process ``pid`` alive? True/False, or None if it cannot be determined.

    Windows-safe: uses OpenProcess via ctypes (NEVER os.kill -- on Windows os.kill
    with any sig TERMINATES the target). On POSIX uses os.kill(pid, 0)."""
    if pid is None or pid <= 0:
        return None
    import os  # noqa: PLC0415
    if os.name == "nt":
        try:
            import ctypes  # noqa: PLC0415
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not h:
                return False
            code = ctypes.c_ulong(0)
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            k32.CloseHandle(h)
            # 259 == STILL_ACTIVE; any other exit code means the process has ended.
            return bool(ok) and code.value == 259
        except Exception:  # noqa: BLE001 -- unknown -> let the age cap decide
            return None
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    except Exception:  # noqa: BLE001
        return None


def _read_lock() -> Optional[tuple]:
    """Parse (pid, epoch) from the lock file, or None if absent/unparseable."""
    lp = _lock_path()
    try:
        if not lp.exists():
            return None
        txt = lp.read_text(encoding="ascii")
        pid = epoch = None
        for tok in txt.split():
            if tok.startswith("pid="):
                pid = int(tok[4:])
            elif tok.startswith("epoch="):
                epoch = float(tok[6:])
        return (pid, epoch)
    except Exception:  # noqa: BLE001
        return None


def _lock_blocks(now: float) -> bool:
    """True only if a LIVE rebuild legitimately holds the lock (so we should skip).

    A lock whose writer PID is dead is reclaimable (returns False) -- this is what
    prevents a hard-killed mid-rebuild from stranding the brain. If the PID is
    unknown, fall back to the age cap; a lock past the cap is always reclaimable."""
    parsed = _read_lock()
    if parsed is None:
        return False
    pid, epoch = parsed
    age = (now - epoch) if epoch is not None else None
    if age is not None and age >= _LOCK_HARD_CAP_SEC:
        return False  # too old to be a healthy rebuild -> reclaim
    alive = _pid_alive(pid) if pid is not None else None
    if alive is False:
        return False  # writer is dead -> reclaim immediately
    if alive is True:
        return True   # a live rebuild holds it -> skip
    # PID unknown: honor a young lock, reclaim an old one (cap handled above).
    return age is None or age < _LOCK_HARD_CAP_SEC


def _acquire(now: float) -> bool:
    """Take the rebuild lock unless a LIVE rebuild holds it. Returns True on acquire."""
    if _lock_blocks(now):
        return False
    lp = _lock_path()
    try:
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(_default_stamp(now), encoding="ascii")
        return True
    except Exception:  # noqa: BLE001 -- if we cannot lock, skip this tick safely
        return False


def _release() -> None:
    """Drop the rebuild lock. Never raises."""
    try:
        _lock_path().unlink()
    except Exception:  # noqa: BLE001 -- a missing/locked file is fine to ignore
        pass


def _default_stamp(now: float) -> str:
    return "m14_brain_rebuild pid=%s epoch=%.0f" % (_safe_pid(), now)


def _safe_pid() -> int:
    try:
        import os  # noqa: PLC0415
        return os.getpid()
    except Exception:  # noqa: BLE001
        return -1


def _default_rebuild(*, with_models: bool) -> Any:
    """One full rebuild via brain_pipeline. Person-free; no edge; never raises out."""
    try:
        from scripts.platformkit.brain_pipeline import run_pipeline  # noqa: PLC0415
        return run_pipeline(with_models=with_models)
    except Exception as exc:  # noqa: BLE001 -- a bad rebuild is one red tick, not a crash
        logger.warning("brain rebuild tick failed: %s", exc)
        return {"error": str(exc)}


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        with_models: bool = False,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        run_fn: Optional[Callable[..., Any]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Drive the brain rebuild on a cadence forever (or for ``max_ticks``).

    Everything is injectable so an offline test drives it with a fake clock/sleep, a
    stub ``run_fn``, a bounded ``max_ticks`` and NO real sleep / NO real rebuild.
    Beats the heartbeat at boot and on every boundary so liveness advances at the
    cadence; a hung rebuild stops advancing it and the supervisor reads NOT-READY.
    Each tick acquires the serialization lock (skipping the rebuild -- but STILL
    beating -- if a fresh manual rebuild holds it) and releases it after. Returns the
    number of ticks attempted.

    person-free intelligence MAP; flips no flag, writes no registry, arms no
    autostart, touches no real money. Never raises out.
    """
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
    _rebuild = run_fn if run_fn is not None else (
        lambda: _default_rebuild(with_models=with_models))
    ticks = 0
    # Beat once at boot so the service is "live" before the first rebuild completes.
    try:
        _beat(float(_clock()))
    except Exception:  # noqa: BLE001
        _beat()
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001 -- a bad stop hook must not crash loop
                break
        try:
            now = float(_clock())
        except Exception:  # noqa: BLE001 -- a bad clock degrades to wall time
            now = _time.time()
        skipped = False
        if _acquire(now):
            try:
                _rebuild()
            except Exception as exc:  # noqa: BLE001 -- defense in depth
                logger.warning("brain rebuild tick raised: %s", exc)
            finally:
                _release()
        else:
            skipped = True
            logger.info("brain rebuild tick skipped: a live rebuild holds the lock")
        _beat(now)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        # A SKIP means another rebuild is in flight -> retry soon (minutes), not after
        # the full cadence, so a transient overlap recovers fast. A completed rebuild
        # sleeps the full interval.
        try:
            _sleep(float(_RETRY_SEC if skipped else interval_sec))
        except Exception:  # noqa: BLE001 -- a bad sleep ends the loop cleanly
            break
    return ticks


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Supervised brain-rebuild runner (M14): rebuilds the organized "
                    "person-free Obsidian brain (vault/_Organized) from the deep "
                    "archive on a cadence + beats a liveness heartbeat. Ships "
                    "nothing, flips no flag, no real money.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between rebuilds (default: %(default)s).")
    p.add_argument("--with-models", action="store_true",
                   help="Deep refresh: also run the heavy real-corpus model stages "
                        "(slower; default off keeps the graph connected + fresh).")
    a = p.parse_args()
    print("brain_rebuild_runner | started interval=%ss with_models=%s component=%s "
          "(person-free intelligence MAP, no $/flag/registry/autostart)"
          % (a.interval, a.with_models, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval, with_models=a.with_models)
    except KeyboardInterrupt:
        print("brain_rebuild_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_INTERVAL_SEC", "run"]
