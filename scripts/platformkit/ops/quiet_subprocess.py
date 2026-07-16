"""scripts.platformkit.ops.quiet_subprocess -- spawn helper children with no console flash.

Root cause this exists for: supervisor/proc_win.py correctly passes
creationflags=CREATE_NO_WINDOW when it launches each daemon, but any subprocess
that daemon (or a platformkit script) shells out to a console app (powershell,
cmd, tasklist) WITHOUT that flag gets a fresh, briefly-visible console window on
Windows -- that's the flash. This module is the one place platformkit code
routes such calls through so the flag is never forgotten again.

No-op (flag omitted) on non-Windows. Stdlib-only.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any

# ponytail: CREATE_NO_WINDOW is Windows-only; absent from the subprocess module
# on other platforms, so read it as a getattr with a harmless fallback (0 = no flag).
CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def _with_quiet_flags(kwargs: dict) -> dict:
    if sys.platform == "win32":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return kwargs


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """subprocess.run wrapper that never pops a console window on Windows."""
    return subprocess.run(cmd, **_with_quiet_flags(kwargs))


def popen(cmd: list[str], **kwargs: Any) -> subprocess.Popen:
    """subprocess.Popen wrapper that never pops a console window on Windows."""
    return subprocess.Popen(cmd, **_with_quiet_flags(kwargs))


if __name__ == "__main__":
    # ponytail: smallest runnable check -- flag gets set on win32, left alone elsewhere.
    kw = _with_quiet_flags({})
    if sys.platform == "win32":
        assert kw.get("creationflags") == CREATE_NO_WINDOW, "CREATE_NO_WINDOW not applied"
    else:
        assert "creationflags" not in kw, "creationflags should be untouched off win32"
    print("quiet_subprocess self-check: PASSED")
