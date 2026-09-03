"""Runner claim ownership and process-lifecycle helpers."""
from __future__ import annotations

import atexit
import os
import signal
import socket
from contextlib import contextmanager
from typing import Any, Iterator


def claimer_for_pid(pid: int | None = None) -> str:
    """Return the additive, process-specific queue owner identifier."""
    return "{0}:{1}".format(socket.gethostname(), os.getpid() if pid is None else pid)


def dead_same_host_claimer(claimer: str | None) -> bool:
    """Whether a well-formed local claimer names a process that no longer exists."""
    if not claimer or ":" not in claimer:
        return False
    host, text_pid = claimer.rsplit(":", 1)
    if host != socket.gethostname():
        return False
    try:
        pid = int(text_pid)
    except ValueError:
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        ctypes.set_last_error(0)
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER
        status = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(status))
        ctypes.windll.kernel32.CloseHandle(handle)
        return status.value != 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


@contextmanager
def claim_lifecycle(db: Any) -> Iterator[str]:
    """Release this process's unfinished claims on exit or a termination signal."""
    claimer, released = claimer_for_pid(), False

    def release_once() -> None:
        nonlocal released
        if not released:
            db.release(claimer=claimer)
            released = True

    def stop(signum: int, _frame: Any) -> None:
        release_once()
        raise SystemExit(128 + signum)

    atexit.register(release_once)
    old = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        yield claimer
    finally:
        release_once()
        for sig, handler in old.items():
            signal.signal(sig, handler)
