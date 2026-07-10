"""scripts.platformkit.autoloop.log_reaper_job -- U4/T2 log rotation.

44 supervisor-managed proc logs live under logs/ opened append-forever
(supervisor/proc_win.py's ``open(out_file, "a")`` / ``open(err_file, "a")`` --
that module is OFF-LIMITS infra, read-only reference, never edited here).
logs/m1_api_paper.out is the one hot file (~23MB measured, ~2.5MB/day) but
every *.out/*.err is structurally unbounded. Low urgency (218G free) but
structural, hence this reaper.

WINDOWS MEASUREMENT (docs/research -- see scratchpad probe, not committed):
a scratch child process held a log open in ``"a"`` mode while a second
process attempted copy / truncate / rename on the SAME live file:
  - ``shutil.copyfile`` of the live file: OK.
  - ``os.truncate(path, 0)``  of the live file: OK -- the writer's next
    ``write()`` lands at the new EOF (0), confirmed by content continuing
    correctly post-truncate with no corruption or exception in the child.
  - ``os.rename``/``os.replace`` of the live file: FAILS (WinError 32 /
    PermissionError) -- Python's default Windows share mode omits
    FILE_SHARE_DELETE, so the directory entry cannot move while any handle
    is open, even though read/write sharing is permitted.
This measurement picks ONE design: copy-then-truncate-in-place for EVERY
over-cap log, live or dead. No supervisor pid-liveness check is needed --
that branch only existed for the "if truncate fails" case, and it doesn't.
# ponytail: single measured branch, not both branches from the spec -- if a
# future Windows update tightens share mode and truncate starts failing,
# add the dead-pid-only fallback (supervisor.proc_win.is_alive) then, not now.

Runs once per autoloop cycle via maintenance_templates._JOB_TABLE (key
"log_reaper"). One bad file is isolated -- never blocks the rest of the scan
or the rest of run_all's table.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/autoloop/test_log_reaper_job.py -q
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.io_atomic import write_json_atomic

_REPO = Path(__file__).resolve().parents[3]
LOGS_DIR = _REPO / "logs"
ARCHIVE_DIRNAME = "archive"
OPS_PATH = _REPO / "data" / "frontend" / "ops" / "log_reaper.json"
CAP_BYTES = 50 * 1024 * 1024  # 50MB per log, per LANE U4 spec
_PATTERNS = ("*.out", "*.err")


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_log_reaper(watermarks: Optional[Dict[str, Any]] = None, *,
                   logs_dir: Optional[Path] = None,
                   cap_bytes: int = CAP_BYTES,
                   ops_path: Optional[Path] = None,
                   copy_fn: Callable[[str, str], Any] = shutil.copyfile,
                   truncate_fn: Callable[[str, int], None] = os.truncate,
                   now_fn: Callable[[], str] = _now_ts) -> Dict[str, Any]:
    """Archive (copy) then truncate-in-place every logs/*.out|*.err strictly
    over cap_bytes. watermarks accepted for call-shape uniformity with every
    other maintenance job (unused -- the size check is cheap and idempotent,
    no drift risk from re-checking an already-under-cap file each cycle)."""
    d = Path(logs_dir) if logs_dir is not None else LOGS_DIR
    archive_dir = d / ARCHIVE_DIRNAME
    checked = 0
    archived: List[Dict[str, Any]] = []
    failed: List[Dict[str, str]] = []
    if d.is_dir():
        seen = set()
        for pattern in _PATTERNS:
            for p in sorted(d.glob(pattern)):
                if not p.is_file() or p.name in seen:
                    continue
                seen.add(p.name)
                checked += 1
                size = p.stat().st_size
                if size <= cap_bytes:
                    continue
                dest = archive_dir / ("%s.%s%s" % (p.stem, now_fn(), p.suffix))
                try:
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    copy_fn(str(p), str(dest))
                    truncate_fn(str(p), 0)
                    archived.append({"name": p.name, "size_before": size,
                                     "archived_to": dest.name})
                except OSError as exc:  # noqa: BLE001 -- one bad file must not block the rest
                    failed.append({"name": p.name, "error": str(exc)[:200]})
    out = {"status": "ok", "cap_bytes": cap_bytes, "checked": checked,
          "archived": archived, "failed": failed, "ts": now_fn()}
    write_json_atomic(Path(ops_path) if ops_path is not None else OPS_PATH, out)
    return out


__all__ = ["run_log_reaper", "CAP_BYTES"]
