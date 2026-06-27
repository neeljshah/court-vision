"""supervisor.proc_win -- Windows process control backend (Win11 / PowerShell host).

Mirrors boot.ps1's Start-Det conventions:
  - python -u -m <module> [args...]
  - Hidden window (CREATE_NO_WINDOW via subprocess flags)
  - Stdout/stderr redirected to logs/<name>.out / logs/<name>.err
  - A pid-file is written per process under logs/<name>.pid

Public API (called by supervisor.proc): spawn / is_alive / kill / write_pid_file /
read_pid_file / find_by_match. ProcHandle is a plain dict (round-trippable through
JSON / pid-file): name, pid, pid_file, cmd (list[str]). Stdlib-only; spawn() takes
a subprocess_factory kwarg (tests pass a fake); only spawn() spawns; <=300 LOC.
The CIM process-table helpers live in supervisor.proc_win_cim (wmic is gone on
newer Win11). is_alive(verify_cmdline=True) guards against OS PID reuse.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from supervisor.proc_win_cim import cmdline_for_pid, ps_process_table

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

    spec keys: name (log/pid filenames), python (interpreter, default
    sys.executable), module (python -m <module>), args (extra CLI args).
    log_dir holds .out/.err/.pid. subprocess_factory replaces subprocess.Popen
    for tests (same args; must return an object with .pid).
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

def _cmd_token(handle: ProcHandle) -> Optional[str]:
    """The distinctive cmdline token identifying *handle*'s real process.

    Defeats PID REUSE: a recycled OS pid (a new, unrelated process handed our dead
    child's pid) is alive but its cmdline lacks our token. Returns the python
    ``-m`` module (e.g. predict_service.app) or ``next-server`` (node UI), else
    None (then cmdline checks are skipped).
    """
    cmd = handle.get("cmd")
    if isinstance(cmd, (list, tuple)):
        parts = [str(p) for p in cmd]
        # python -u -m <module> ...  -> the module is the unique token.
        for i, p in enumerate(parts):
            if p == "-m" and i + 1 < len(parts):
                return parts[i + 1]
        joined = " ".join(parts)
        if "next-server" in joined or "next" in joined.lower():
            return "next-server"
    return None


def is_alive(handle: ProcHandle, *, verify_cmdline: bool = False) -> bool:
    """Return True if the process with handle['pid'] is still running.

    Uses OpenProcess + GetExitCodeProcess via ctypes (tasklist fallback).
    PID-REUSE GUARD: ``verify_cmdline=True`` additionally checks the alive pid's
    cmdline for the handle's distinctive token (``-m`` module / ``next-server``);
    a RECYCLED pid lacks it -> returns False (our child is dead, pid was reused).
    Default False keeps the cheap pid-only fast path for the hot kill-wait loop.
    """
    pid = handle.get("pid")
    if not pid:
        return False
    pid_alive = False
    try:
        import ctypes
        import ctypes.wintypes as wt

        PROCESS_QUERY_LIMITED = 0x1000
        STILL_ACTIVE = 259

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
        if not hproc:
            pid_alive = False
        else:
            exit_code = wt.DWORD()
            ok = kernel32.GetExitCodeProcess(hproc, ctypes.byref(exit_code))
            kernel32.CloseHandle(hproc)
            pid_alive = bool(ok and exit_code.value == STILL_ACTIVE)
    except Exception:  # noqa: BLE001 -- ctypes unavailable or not Windows
        # Fallback: tasklist
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                capture_output=True, text=True, timeout=5, check=False,
            ).stdout
            pid_alive = str(pid) in out
        except Exception:  # noqa: BLE001
            return False

    if not pid_alive:
        return False
    if not verify_cmdline:
        return True
    token = _cmd_token(handle)
    if not token:
        return True  # no distinctive token -> cannot disprove; trust pid liveness
    live_cmd = cmdline_for_pid(pid)
    if live_cmd is None:
        return True  # could not read the table -> do not falsely declare dead
    return token in live_cmd


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

    # H1: kill the whole PROCESS TREE. A node UI launches via npm, which spawns the
    # real ``next-server`` listener as a CHILD; killing only the npm pid orphans
    # next-server (keeps holding :3000 -> EADDRINUSE loop). taskkill /T reaps the
    # tree; harmless for the single-process python daemons (tree == themselves).
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except Exception:  # noqa: BLE001 -- taskkill unavailable -> fall back to ctypes
        pass

    # Belt-and-suspenders single-pid terminate (reparented / no-console pid).
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

    Uses Get-CimInstance Win32_Process (wmic is gone on newer Win11). No psutil.
    """
    handles: List[ProcHandle] = []
    for row in ps_process_table():
        cmdline = row.get("cmdline") or ""
        if pattern not in cmdline:
            continue
        handles.append({
            "name": pattern,
            "pid": row["pid"],
            "pid_file": None,
            "cmd": [cmdline],
        })
    return handles
