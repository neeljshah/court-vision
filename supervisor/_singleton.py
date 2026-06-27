"""supervisor._singleton -- one-supervisor-at-a-time guard (race-proof).

Two supervisors must NEVER run concurrently. Each one runs reconcile_survivors()
on boot, which kills every OTHER supervisor's freshly-spawned CHILDREN by cmdline
match -- so two boots that race (the autostart watchdog's poll firing at the same
moment as a manual boot, or two overlapping launchers) tear down each other's
children and flap forever on ports :8099/:8098/:3000. This was the recurring
"multi-supervisor deadlock".

``acquire()`` takes an OS-level EXCLUSIVE, non-blocking lock on a lock file that
the kernel auto-releases the instant the holding process dies (msvcrt on Windows,
fcntl.flock on POSIX). The FIRST supervisor to call acquire() wins; a concurrent
caller gets ``None`` and must exit cleanly. A DEAD predecessor's lock is already
released by the OS, so the next boot acquires immediately -- there is no stale-lock
problem and no lock file to clean up.

FAIL-OPEN: this guard sits on the boot-critical path, so any unexpected error
(cannot create the lock dir/file, lock subsystem hiccup) returns a NON-owning
handle and lets boot PROCEED unguarded -- a guard bug must never leave the box
dark. acquire() returns None ONLY when it has POSITIVELY observed another live
holder.

Stdlib-only, ASCII-only.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("supervisor.singleton")

# One global lock for the whole stack: never two supervisors, any profile.
DEFAULT_LOCK_PATH = os.path.join(
    "data", "cache", "supervisor", "supervisor.lock")


class LockHandle:
    """Opaque holder that keeps the lock fd open for the process lifetime.

    held=True  -> we own the single-instance lock (or fail-open: see module doc).
    The fd is intentionally never closed here; the OS releases the lock when the
    process exits. Keep a reference to this handle alive for the whole run.
    """

    __slots__ = ("fd", "path", "held")

    def __init__(self, fd: Optional[int], path: str, held: bool) -> None:
        self.fd = fd
        self.path = path
        self.held = held


def _try_exclusive_lock(fd: int) -> bool:
    """Non-blocking exclusive lock on the first byte of *fd*.

    Returns True if acquired, False if another process already holds it. Raises
    only on a genuinely unexpected lock-subsystem error (the caller fails open).
    """
    try:
        import msvcrt  # Windows
    except ImportError:
        import fcntl  # POSIX
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        # Region already locked by another process (EACCES / EDEADLOCK).
        return False


def acquire(lock_path: str = DEFAULT_LOCK_PATH) -> Optional[LockHandle]:
    """Acquire the single-instance lock.

    Returns a LockHandle when we own the lock (held=True) OR when we fail open
    (held=False -- proceed unguarded). Returns None ONLY when another LIVE
    supervisor positively holds the lock and this process must exit.
    """
    try:
        os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as exc:
        logger.warning("supervisor: lock file unavailable (%s) -- proceeding "
                       "UNGUARDED (fail-open)", type(exc).__name__)
        return LockHandle(None, lock_path, held=False)

    try:
        got = _try_exclusive_lock(fd)
    except Exception as exc:  # noqa: BLE001 -- a lock hiccup must not block boot
        logger.warning("supervisor: lock attempt raised %s -- proceeding "
                       "UNGUARDED (fail-open)", type(exc).__name__)
        return LockHandle(fd, lock_path, held=False)

    if got:
        try:
            os.ftruncate(fd, 0)
            os.write(fd, ("%d\n" % os.getpid()).encode("ascii"))
        except OSError:
            pass  # the PID stamp is advisory only; the lock is what matters
        return LockHandle(fd, lock_path, held=True)

    # Positively held by another live supervisor.
    try:
        os.close(fd)
    except OSError:
        pass
    return None
