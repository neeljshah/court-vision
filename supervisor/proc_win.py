"""supervisor.proc_win -- Windows process control backend (Win11 / PowerShell host).

Mirrors boot.ps1's Start-Det conventions:
  - python -u -m <module> [args...]
  - Hidden window (CREATE_NO_WINDOW via subprocess flags)
  - Stdout/stderr redirected to logs/<name>.out / logs/<name>.err
  - A pid-file is written per process under logs/<name>.pid

Public API (called by supervisor.proc):
  spawn(spec, *, log_dir)  -> ProcHandle
  is_alive(handle)         -> bool
  kill(handle)             -> None   (graceful CTRL_BREAK -> terminate after 3s)
  write_pid_file(pid_file, pid) -> None
  read_pid_file(pid_file)       -> int | None
  find_by_match(pattern)        -> list[ProcHandle]

ProcHandle is a plain dict so it can be round-tripped through JSON / pid-file.
Keys: name, pid, pid_file, cmd (list[str]).

Design rules
------------
  - Stdlib-only (subprocess, os, pathlib, signal, time, json, typing).
  - Inject-friendly: spawn() accepts a subprocess_factory kwarg (tests pass a fake).
  - No real process is spawned by the module-level code; only spawn() does that.
  - <=300 LOC.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Windows flag: no console window created for the new process.
_CREATE_NO_WINDOW = 0x08000000

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
    except Exception:  # noqa: BLE001 -- missing, corrupt, non-int
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

    spec keys (all str):
      name     -- logical name; used for log/pid filenames.
      python   -- path to python interpreter (default: sys.executable).
      module   -- python -m <module> to run.
      args     -- list[str] of additional CLI args (optional).

    log_dir:  directory for .out / .err / .pid files (created if absent).

    subprocess_factory:  replaces subprocess.Popen for tests (receives the
        same positional+keyword args and must return an object with .pid).
    """
    import sys
    import os
    import shutil

    name: str = spec["name"]
    kind: str = spec.get("kind") or "py"
    extra_args: List[str] = spec.get("args") or []

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    out_file = str(log_path / f"{name}.out")
    err_file = str(log_path / f"{name}.err")
    pid_file = str(log_path / f"{name}.pid")

    cwd_spec = spec.get("cwd") or None
    if cwd_spec and not os.path.isabs(cwd_spec):
        cwd_spec = os.path.abspath(cwd_spec)

    if kind == "node":
        # node UI (e.g. "npm run dev") in its own cwd; npm is npm.cmd on Windows.
        parts = (spec.get("cmd") or "npm run dev").split()
        exe = parts[0]
        if exe == "npm":
            exe = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
        cmd: List[str] = [exe] + parts[1:] + list(extra_args)
    else:
        python: str = spec.get("python") or sys.executable
        module: str = spec.get("module") or ""
        cmd = [python, "-u", "-m", module] + list(extra_args)

    factory = subprocess_factory if subprocess_factory is not None else subprocess.Popen

    out_fh = open(out_file, "a", encoding="utf-8")  # noqa: WPS515
    err_fh = open(err_file, "a", encoding="utf-8")  # noqa: WPS515

    # RB-P0-02: pass the EXPLICIT env (supervisor merges os.environ < global_env
    # < spec.env). None => inherit parent (legacy behavior) so an old caller that
    # omits "env" is unchanged. A dict with at least the merged base ensures a
    # governance flag reaches the child by value, not fragile shell inheritance.
    spec_env = spec.get("env")
    child_env = dict(spec_env) if isinstance(spec_env, dict) else None

    proc = factory(
        cmd,
        stdout=out_fh,
        stderr=err_fh,
        creationflags=_CREATE_NO_WINDOW,
        close_fds=True,
        cwd=cwd_spec,
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

    Uses OpenProcess + GetExitCodeProcess via ctypes so no subprocess is
    needed.  Falls back to tasklist if ctypes is unavailable.
    """
    pid = handle.get("pid")
    if not pid:
        return False
    try:
        import ctypes
        import ctypes.wintypes as wt

        PROCESS_QUERY_LIMITED = 0x1000
        STILL_ACTIVE = 259

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
        if not hproc:
            return False
        exit_code = wt.DWORD()
        ok = kernel32.GetExitCodeProcess(hproc, ctypes.byref(exit_code))
        kernel32.CloseHandle(hproc)
        return bool(ok and exit_code.value == STILL_ACTIVE)
    except Exception:  # noqa: BLE001 -- ctypes unavailable or not Windows
        pass

    # Fallback: tasklist
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout
        return str(pid) in out
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# kill
# ---------------------------------------------------------------------------

def kill(handle: ProcHandle) -> None:
    """Graceful stop: CTRL_BREAK_EVENT -> wait 3s -> TerminateProcess."""
    pid = handle.get("pid")
    if not pid:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # CTRL_BREAK_EVENT = 1; GenerateConsoleCtrlEvent is graceful for Python procs.
        kernel32.GenerateConsoleCtrlEvent(1, pid)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if not is_alive(handle):
                return
            time.sleep(0.1)
    except Exception:  # noqa: BLE001 -- not available (no console) or not Windows
        pass

    # Force-terminate
    try:
        import ctypes

        PROCESS_TERMINATE = 0x0001
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        hproc = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if hproc:
            kernel32.TerminateProcess(hproc, 1)
            kernel32.CloseHandle(hproc)
    except Exception:  # noqa: BLE001
        pass

    # Best-effort cleanup of pid file
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

    Uses WMIC (always available on Win10+) so no psutil needed.
    """
    handles: List[ProcHandle] = []
    try:
        out = subprocess.run(
            ["wmic", "process", "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout
        for line in out.splitlines():
            if pattern not in line:
                continue
            # WMIC CSV columns: Node,CommandLine,ProcessId
            parts = line.split(",", 2)
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[-1].strip())
            except ValueError:
                continue
            handles.append({
                "name": pattern,
                "pid": pid,
                "pid_file": None,
                "cmd": [parts[1].strip()] if len(parts) > 1 else [],
            })
    except Exception:  # noqa: BLE001
        pass
    return handles
