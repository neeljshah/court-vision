"""supervisor.proc_posix -- POSIX process control backend (RunPod RTX 3090 / Linux).

Conventions:
  - python -u -m <module> [args...]
  - New session (os.setsid) so killing the supervisor doesn't cascade.
  - Stdout/stderr redirected to logs/<name>.out / logs/<name>.err
  - pid-file written per process under logs/<name>.pid

Public API (identical surface to proc_win):
  spawn(spec, *, log_dir)  -> ProcHandle
  is_alive(handle)         -> bool
  kill(handle)             -> None   (SIGTERM -> wait 3s -> SIGKILL)
  write_pid_file(pid_file, pid) -> None
  read_pid_file(pid_file)       -> int | None
  find_by_match(pattern)        -> list[ProcHandle]

ProcHandle is a plain dict; keys: name, pid, pid_file, cmd (list[str]).

Design rules
------------
  - Stdlib-only (subprocess, os, signal, pathlib, time, typing).
  - Inject-friendly: spawn() accepts a subprocess_factory kwarg.
  - No real process is spawned at module level.
  - <=300 LOC.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ProcHandle = Dict[str, Any]


# ---------------------------------------------------------------------------
# pid-file helpers (pure, no subprocess)
# ---------------------------------------------------------------------------

def write_pid_file(pid_file: str, pid: int) -> None:
    """Atomically write *pid* to *pid_file* (creates parent dirs)."""
    p = Path(pid_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(pid), encoding="ascii")


def read_pid_file(pid_file: str) -> Optional[int]:
    """Return pid stored in *pid_file*, or None if missing / unreadable."""
    p = Path(pid_file)
    try:
        return int(p.read_text(encoding="ascii").strip())
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# spawn
# ---------------------------------------------------------------------------

def spawn(
    spec: Dict[str, Any],
    *,
    log_dir: str,
    subprocess_factory: Optional[Callable[..., Any]] = None,
) -> ProcHandle:
    """Launch the process described by *spec* and return a ProcHandle.

    spec keys:
      name     -- logical name; used for log/pid filenames.
      python   -- path to python interpreter (default: sys.executable).
      module   -- python -m <module> to run.
      args     -- list[str] of additional CLI args (optional).

    subprocess_factory: replaces subprocess.Popen for unit tests.
    """
    import sys

    name: str = spec["name"]
    python: str = spec.get("python") or sys.executable
    module: str = spec["module"]
    extra_args: List[str] = spec.get("args") or []

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    out_file = str(log_path / f"{name}.out")
    err_file = str(log_path / f"{name}.err")
    pid_file = str(log_path / f"{name}.pid")

    cmd: List[str] = [python, "-u", "-m", module] + list(extra_args)

    factory = subprocess_factory if subprocess_factory is not None else subprocess.Popen

    out_fh = open(out_file, "a", encoding="utf-8")  # noqa: WPS515
    err_fh = open(err_file, "a", encoding="utf-8")  # noqa: WPS515

    # RB-P0-02: pass the EXPLICIT env (supervisor merges os.environ < global_env
    # < spec.env). None => inherit parent (legacy behavior) so an old caller that
    # omits "env" is unchanged.
    spec_env = spec.get("env")
    child_env = dict(spec_env) if isinstance(spec_env, dict) else None

    # setsid: new session; child survives supervisor restart, isolated from TTY.
    proc = factory(
        cmd,
        stdout=out_fh,
        stderr=err_fh,
        start_new_session=True,
        close_fds=True,
        env=child_env,
    )

    pid: int = proc.pid
    write_pid_file(pid_file, pid)

    return {
        "name": name,
        "pid": pid,
        "pid_file": pid_file,
        "cmd": cmd,
    }


# ---------------------------------------------------------------------------
# is_alive
# ---------------------------------------------------------------------------

def is_alive(handle: ProcHandle) -> bool:
    """Return True if the process with handle['pid'] is still running.

    Uses os.kill(pid, 0) -- the lightest POSIX check (no signal sent).
    """
    pid = handle.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't have permission to signal it.
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# kill
# ---------------------------------------------------------------------------

def kill(handle: ProcHandle) -> None:
    """SIGTERM -> wait 3s -> SIGKILL.  Best-effort; never raises."""
    pid = handle.get("pid")
    if not pid:
        return

    # Graceful
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:  # noqa: BLE001
        pass

    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not is_alive(handle):
            break
        time.sleep(0.1)

    # Force
    if is_alive(handle):
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001
            pass

    # Cleanup pid file
    pid_file = handle.get("pid_file")
    if pid_file:
        try:
            Path(pid_file).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# find_by_match  (process adoption after supervisor restart)
# ---------------------------------------------------------------------------

def find_by_match(pattern: str) -> List[ProcHandle]:
    """Return ProcHandles for running processes whose cmdline contains *pattern*.

    Reads /proc/<pid>/cmdline on Linux; falls back to 'ps -eo pid,cmd'.
    """
    handles: List[ProcHandle] = []

    # Fast path: /proc (Linux / RunPod)
    proc_path = Path("/proc")
    if proc_path.is_dir():
        for entry in proc_path.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
                if pattern in raw:
                    pid = int(entry.name)
                    handles.append({
                        "name": pattern,
                        "pid": pid,
                        "pid_file": None,
                        "cmd": raw.strip().split(),
                    })
            except Exception:  # noqa: BLE001 -- process vanished mid-scan
                continue
        return handles

    # Fallback: ps
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,cmd", "--no-headers"],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout
        for line in out.splitlines():
            if pattern not in line:
                continue
            parts = line.split(None, 1)
            if not parts:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            handles.append({
                "name": pattern,
                "pid": pid,
                "pid_file": None,
                "cmd": parts[1].split() if len(parts) > 1 else [],
            })
    except Exception:  # noqa: BLE001
        pass
    return handles
