"""supervisor.proc_win_cim -- CIM-backed Windows process table (wmic replacement).

wmic is DEPRECATED and REMOVED on newer Win11 builds, where it returns an empty
string SILENTLY -- so the old find_by_match() saw [] and reconcile never reaped a
survivor, DUPLICATING daemons. boot.ps1 already uses Get-CimInstance
Win32_Process; this module mirrors that supported successor for proc_win.

Emits NDJSON (one compact JSON object per line) from PowerShell so a CommandLine
containing commas never corrupts parsing. Every function NEVER raises (returns an
empty list / None on any failure). Stdlib-only, ASCII-only, <=300 LOC.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

# Mirror proc_win.py: hide the console window of every powershell probe --
# without this the 30s process-table cadence flashes a visible terminal.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# TICK-COST FIX (2026-07-10): every liveness call (is_alive(verify_cmdline=True)
# via cmdline_for_pid, plus find_by_match) re-spawned PowerShell to enumerate the
# WHOLE Win32_Process table (~1.3s / 400+ procs) just to read ONE pid's cmdline.
# supervise() fires 2-3 such calls per spec x ~43 specs = ~90-130 enumerations per
# tick -> ~2-3min ticks under load. A short TTL cache collapses one tick's burst
# to a SINGLE enumeration (all subsequent lookups hit the cache in microseconds).
# Staleness is bounded by _TABLE_TTL_SEC and only affects the PID-REUSE guard /
# survivor scan, both of which already tolerate one-tick latency.
# RESIDUAL FIX (2026-07-10b): a 2.0s TTL still expired MID-TICK -- measured ~1
# enumeration per ~2.4s of tick time, so a 60-90s tick re-paid ~25-40 x 1.3-2s
# = 40-80s (the observed 66-90s residual). 30s covers a whole slow tick with ONE
# enumeration. Safe: a dead pid fails the cheap OpenProcess check BEFORE the
# cache is consulted, and an unknown (fresh) pid returns None -> caller trusts
# pid liveness -- staleness can only delay the rare pid-reuse detection by <=30s.
# ponytail: wall-clock TTL; per-tick generation token if 30s ever proves too stale.
_TABLE_TTL_SEC = 30.0
_table_cache: Dict[str, Any] = {"t": 0.0, "rows": []}


def ps_process_table(*, max_age_sec: float = _TABLE_TTL_SEC) -> List[Dict[str, Any]]:
    """Return [{pid, cmdline}, ...] for every process, via Get-CimInstance.

    Result is cached for ``max_age_sec`` (monotonic) so one supervise tick's
    liveness burst enumerates the table ONCE, not once per pid. A failed/empty
    enumeration is never served from cache (retries next call). Never raises
    (returns [] on powershell-absent / timeout / parse failure).
    """
    now = time.monotonic()
    cached = _table_cache
    if cached["rows"] and (now - cached["t"]) < max_age_sec:
        return cached["rows"]
    rows: List[Dict[str, Any]] = []
    ps_script = (
        "Get-CimInstance Win32_Process | "
        "ForEach-Object { "
        "[pscustomobject]@{ pid = $_.ProcessId; cmdline = $_.CommandLine } | "
        "ConvertTo-Json -Compress }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=15, check=False,
            creationflags=_CREATE_NO_WINDOW,
        ).stdout
    except Exception:  # noqa: BLE001 -- powershell unavailable / timeout
        return rows
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            pid = int(obj.get("pid"))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        rows.append({"pid": pid, "cmdline": str(obj.get("cmdline") or "")})
    if rows:  # cache only a real (non-empty) enumeration; a failure retries next call
        _table_cache["t"] = time.monotonic()
        _table_cache["rows"] = rows
    return rows


def cmdline_for_pid(pid: int) -> Optional[str]:
    """Return the live command line for *pid*, or None if not found. Never raises."""
    if not pid:
        return None
    for row in ps_process_table():
        if row.get("pid") == pid:
            return row.get("cmdline")
    return None


__all__ = ["ps_process_table", "cmdline_for_pid"]
