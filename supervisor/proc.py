"""supervisor.proc -- cross-platform process control selector.

Picks the right backend by os.name:
  'nt'   -> supervisor.proc_win   (Windows / PowerShell host)
  other  -> supervisor.proc_posix (Linux / RunPod RTX 3090)

Re-exports the full public API so callers only import from here:
  spawn(spec, *, log_dir, subprocess_factory=None) -> ProcHandle
  is_alive(handle)                                 -> bool
  kill(handle)                                     -> None
  write_pid_file(pid_file, pid)                    -> None
  read_pid_file(pid_file)                          -> int | None
  find_by_match(pattern)                           -> list[ProcHandle]
  ProcHandle                                       = dict[str, Any]

Backend selection is done at import time; override via:
  SUPERVISOR_BACKEND env var ('win' | 'posix') -- useful in tests.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

_backend_name = os.environ.get("SUPERVISOR_BACKEND", "").lower()
if _backend_name == "win":
    from supervisor.proc_win import (  # type: ignore[assignment]
        ProcHandle,
        find_by_match,
        is_alive,
        kill,
        read_pid_file,
        spawn,
        write_pid_file,
    )
elif _backend_name == "posix":
    from supervisor.proc_posix import (  # type: ignore[assignment]
        ProcHandle,
        find_by_match,
        is_alive,
        kill,
        read_pid_file,
        spawn,
        write_pid_file,
    )
elif os.name == "nt":
    from supervisor.proc_win import (  # type: ignore[assignment]
        ProcHandle,
        find_by_match,
        is_alive,
        kill,
        read_pid_file,
        spawn,
        write_pid_file,
    )
else:
    from supervisor.proc_posix import (  # type: ignore[assignment]
        ProcHandle,
        find_by_match,
        is_alive,
        kill,
        read_pid_file,
        spawn,
        write_pid_file,
    )

def to_spawn_spec(spec: Any, global_env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Translate a ProcSpec into the dict shape spawn() expects.

    RB-P0-02: thread the env EXPLICITLY into the spawn dict so a governance flag
    (GOVERNANCE_ELIGIBLE) + per-child env reach the child by VALUE, not fragile
    shell inheritance. Precedence (low -> high): os.environ < global_env < spec.env.
    """
    merged: Dict[str, str] = {}
    for k, v in os.environ.items():
        merged[str(k)] = str(v)
    for src in (global_env or {}, getattr(spec, "env", None) or {}):
        for k, v in src.items():
            merged[str(k)] = str(v)
    return {"name": spec.name, "kind": spec.kind, "module": spec.module or "",
            "args": list(spec.argv or []), "cmd": spec.cmd or "",
            "cwd": spec.cwd or "", "env": merged}


__all__ = [
    "ProcHandle",
    "spawn",
    "is_alive",
    "kill",
    "write_pid_file",
    "read_pid_file",
    "find_by_match",
    "to_spawn_spec",
]
