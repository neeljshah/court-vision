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
from typing import Any, Dict, List, Optional


def ps_process_table() -> List[Dict[str, Any]]:
    """Return [{pid, cmdline}, ...] for every process, via Get-CimInstance.

    Never raises (returns [] on powershell-absent / timeout / parse failure).
    """
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
