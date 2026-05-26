"""daemon_heartbeat.py — single-line helper for daemons to emit heartbeats.

Each registered daemon should call ``write_heartbeat("<daemon_name>")`` at
the top of every loop iteration.  The watchdog (R19_L3) treats heartbeat
mtime > expected_interval_sec * 3 as "daemon is dead/wedged".

Design rules
------------
* Single function, stdlib-only.
* Always wrapped in try/except — heartbeat failure must NEVER take down a
  daemon's hot path.
* Atomic write: temp file + os.replace so the watchdog can never read a
  half-written file.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HB_DIR = os.path.join(_PROJECT_DIR, "data", "cache", "daemon_heartbeats")


def write_heartbeat(name: str, hb_dir: Optional[str] = None) -> bool:
    """Touch ``<hb_dir>/<name>.txt`` with the current ISO timestamp.

    Returns True if the write succeeded, False otherwise.  Never raises.
    """
    try:
        target_dir = hb_dir or _HB_DIR
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"{name}.txt")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=target_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(ts + "\n")
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        return True
    except Exception:  # noqa: BLE001 — never raise from the hot path
        return False
