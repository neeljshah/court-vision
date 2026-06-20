"""scripts.platformkit.ledger_audit.dup_runner -- CLV ledger dup-audit entry point.

Wraps dup_key_detector.scan_ledger, writes the result ATOMICALLY to
data/frontend/ops/clv_dup_report.json, and beats a liveness heartbeat under the
component name ``m18_dupaudit``.

Safety invariants:
  * NEVER mutates or dedupes the ledger (read-only).
  * NEVER authorises a bet; NEVER claims edge (calibration not edge; units not $).
  * Atomic write: JSON written to <report>.tmp then os.replace -> no torn file.
  * Never raises: all exceptions are caught; a degraded envelope is emitted instead.
  * Heartbeat always fires even on failure so the monitor sees the runner as alive.

CLI: python -m scripts.platformkit.ledger_audit.dup_runner [--ledger PATH]

Returns 0 always (measurement only; exit code is not an error signal).

INVARIANTS: <=300 LOC; ASCII; no secrets.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("dup_runner")

HEARTBEAT_COMPONENT = "m18_dupaudit"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_REPORT_PATH = _REPO / "data" / "frontend" / "ops" / "clv_dup_report.json"


# ---------------------------------------------------------------------------
# Heartbeat helper
# ---------------------------------------------------------------------------

def _beat(now_epoch: Optional[float] = None) -> None:
    """Write liveness heartbeat for m18_dupaudit. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("dup_runner heartbeat skipped: %s", exc)


# ---------------------------------------------------------------------------
# Atomic report write
# ---------------------------------------------------------------------------

def _write_report(report: Dict[str, Any], report_path: Path) -> None:
    """Atomically write *report* as JSON to *report_path*. Never raises."""
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = report_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        os.replace(str(tmp), str(report_path))
        logger.debug("dup_runner: report written to %s", report_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dup_runner: report write failed: %s", exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    ledger_path: Optional[Path] = None,
    report_path: Optional[Path] = None,
    now_epoch: Optional[float] = None,
) -> Dict[str, Any]:
    """Scan the ledger for dup keys, write report, beat heartbeat.

    Parameters
    ----------
    ledger_path:  Override ledger location (None -> canonical DEFAULT_LEDGER).
    report_path:  Override report output path (None -> clv_dup_report.json).
    now_epoch:    Override current epoch time (for tests).

    Returns the scan result dict (never raises).
    """
    _beat(now_epoch)

    report: Dict[str, Any] = {}
    try:
        from scripts.platformkit.ledger_audit.dup_key_detector import scan_ledger
        result = scan_ledger(path=ledger_path)
        result["generated_at"] = _iso_now()
        result["component"] = HEARTBEAT_COMPONENT
        report = result
    except Exception as exc:  # noqa: BLE001
        logger.exception("dup_runner: scan_ledger raised unexpectedly")
        report = {
            "status": "UNAVAILABLE",
            "n_dups": 0,
            "dup_keys": [],
            "first_seen_kept": {},
            "n_rows_scanned": 0,
            "ledger_path": str(ledger_path or "unknown"),
            "error": "dup_runner internal error: %s" % exc,
            "generated_at": _iso_now(),
            "component": HEARTBEAT_COMPONENT,
        }

    _write_report(report, report_path or _REPORT_PATH)
    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="CLV ledger duplicate-key audit (read-only)")
    ap.add_argument("--ledger", default=None, help="Override ledger path")
    ap.add_argument("--report", default=None, help="Override report output path")
    args = ap.parse_args()

    ledger = Path(args.ledger) if args.ledger else None
    report = Path(args.report) if args.report else None

    result = run(ledger_path=ledger, report_path=report)

    status = result.get("status", "UNKNOWN")
    n_dups = result.get("n_dups", 0)
    n_rows = result.get("n_rows_scanned", 0)

    print("status=%s  n_dups=%d  n_rows_scanned=%d" % (status, n_dups, n_rows))
    if n_dups:
        print("dup_keys: %s" % result.get("dup_keys", []))
    if result.get("error"):
        print("error: %s" % result["error"])


if __name__ == "__main__":
    _main()


__all__ = ["run", "HEARTBEAT_COMPONENT"]
