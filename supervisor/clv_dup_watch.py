"""supervisor.clv_dup_watch -- CLV-ledger dup-scan observability daemon.

Runs on a heartbeat-stamped tick cycle.  Each tick:
  1. Calls scripts.platformkit.ledger_audit.dup_key_detector.scan_ledger (read-only).
  2. Translates the scan result into one of three verdicts:
       CLEAN         -- ledger present, zero duplicate keys.
       DUPS_FOUND(n) -- ledger present, n distinct duplicate keys found.
       UNAVAILABLE   -- ledger absent or unreadable.
  3. Atomically writes a heartbeat-stamped status JSON to the configured path
     (default data/frontend/ops/clv_dup_status.json) so the ops/supervisor
     surface can show the verdict stale-never-green.

Design invariants:
- READ-ONLY on the ledger: never writes, mutates, or dedupes anything there.
- MEASUREMENT-ONLY: no bet placed, no flag flipped, no data/registry/ write.
- No $ / P&L field.  Units only if referring to ledger counts.
- Injectable clock / sleep / max_ticks so the test suite can drive any number
  of cycles without wall-clock blocking.
- Status field "ok" is NEVER True when verdict is DUPS_FOUND or UNAVAILABLE
  (stale-never-green guarantee).
- Stdlib-only, ASCII-only, <=300 LOC.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_STATUS_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "clv_dup_status.json"
_SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Verdict strings
# ---------------------------------------------------------------------------
VERDICT_CLEAN = "CLEAN"
VERDICT_DUPS_PREFIX = "DUPS_FOUND"   # appended with (n) at write time
VERDICT_UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_scan(ledger_path: Optional[Path]) -> Dict[str, Any]:
    """Delegate to dup_key_detector.scan_ledger.  Never raises."""
    try:
        from scripts.platformkit.ledger_audit.dup_key_detector import scan_ledger
        return scan_ledger(path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": VERDICT_UNAVAILABLE,
            "n_dups": 0,
            "dup_keys": [],
            "first_seen_kept": {},
            "n_rows_scanned": 0,
            "ledger_path": str(ledger_path) if ledger_path else "",
            "error": "import/call failed: %s" % exc,
        }


def _build_status(scan: Dict[str, Any], now: float) -> Dict[str, Any]:
    """Translate a scan result into the heartbeat-stamped status document."""
    raw_status = scan.get("status", VERDICT_UNAVAILABLE)
    n_dups = int(scan.get("n_dups") or 0)

    if raw_status == "CLEAN":
        verdict = VERDICT_CLEAN
        ok = True
    elif raw_status == "DUPS_FOUND":
        verdict = "%s (%d)" % (VERDICT_DUPS_PREFIX, n_dups)
        ok = False          # stale-never-green: dups are never ok
    else:
        verdict = VERDICT_UNAVAILABLE
        ok = False          # stale-never-green: unavailable is never ok

    return {
        "schema_version": _SCHEMA_VERSION,
        "verdict": verdict,
        "ok": ok,
        "n_dups": n_dups,
        "n_rows_scanned": int(scan.get("n_rows_scanned") or 0),
        "ledger_path": str(scan.get("ledger_path") or ""),
        "error": scan.get("error"),
        "updated_at": now,
    }


def _atomic_write(doc: Dict[str, Any], path: Path) -> bool:
    """Write *doc* to *path* atomically via tmp + os.replace.  Returns True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(doc, indent=2, sort_keys=False, default=str),
            encoding="utf-8",
        )
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tick(
    *,
    ledger_path: Optional[Path] = None,
    status_path: Optional[Path] = None,
    clock: Optional[Callable[[], float]] = None,
) -> Dict[str, Any]:
    """Run one dup-scan tick.

    Scans the CLV ledger, builds the status document, writes it atomically,
    and returns the status dict.  Never raises.

    Parameters
    ----------
    ledger_path:
        Override for the CLV ledger file (default: let scan_ledger choose).
    status_path:
        Override for the output status JSON (default: _DEFAULT_STATUS_PATH).
    clock:
        Zero-arg callable returning epoch float (default: time.time).

    Returns
    -------
    The status dict written to disk (or the in-memory dict if the write failed).
    """
    now = float(clock() if clock is not None else time.time())
    scan = _call_scan(ledger_path)
    doc = _build_status(scan, now)
    out = Path(status_path) if status_path is not None else _DEFAULT_STATUS_PATH
    _atomic_write(doc, out)
    return doc


def run(
    *,
    interval_sec: float = 60.0,
    ledger_path: Optional[Path] = None,
    status_path: Optional[Path] = None,
    clock: Optional[Callable[[], float]] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    max_ticks: Optional[int] = None,
) -> int:
    """Run the daemon loop.

    Runs tick() then sleeps interval_sec, repeating until max_ticks is hit
    (or forever when max_ticks is None).  Returns the number of ticks
    completed.  All I/O is injectable so tests never block.

    Parameters
    ----------
    interval_sec:
        Seconds to sleep between ticks (default 60).
    ledger_path:
        Passed through to tick().
    status_path:
        Passed through to tick().
    clock:
        Injected wall clock (default time.time).
    sleep_fn:
        Injected sleep (default time.sleep).  Receives the interval.
    max_ticks:
        Stop after this many ticks (None -> run forever).

    Returns
    -------
    Number of ticks completed.
    """
    _sleep = sleep_fn if sleep_fn is not None else time.sleep
    completed = 0
    while max_ticks is None or completed < max_ticks:
        tick(
            ledger_path=ledger_path,
            status_path=status_path,
            clock=clock,
        )
        completed += 1
        if max_ticks is not None and completed >= max_ticks:
            break
        _sleep(interval_sec)
    return completed


__all__ = [
    "tick",
    "run",
    "VERDICT_CLEAN",
    "VERDICT_DUPS_PREFIX",
    "VERDICT_UNAVAILABLE",
]
