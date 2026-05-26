"""probe_R27_T7_ledger_insurance.py — end-to-end probe for ledger insurance.

Procedure (LOCAL ONLY — read-only against the real ledger)
-----------------------------------------------------------
1. Locate ``data/pnl_ledger.csv``. If the worktree's own ``data/`` lacks
   it (separate per-worktree data dir on a fresh clone), fall back to
   the canonical maintainer path ``../../../data/pnl_ledger.csv``. If
   neither exists, fall back to a synthetic in-tmp ledger so the probe
   still exercises every code path on a fresh clone.
2. Run ``backup()`` against whatever ledger we found, writing to a
   probe-scoped backup dir under ``data/backups_probe/`` so we NEVER
   pollute the real ``data/backups/`` and NEVER touch the real
   ledger.csv.
3. Verify the produced backup:
     * gz file exists + decompresses
     * sidecar exists + holds the right sha256
     * --verify reports ok
4. ``list_backups()`` returns exactly the one we just wrote.
5. Persist results to ``data/cache/probe_R27_T7_results.json``.

Hard rules
----------
    * Never writes to ``data/pnl_ledger.csv``.
    * Never writes to ``data/backups/`` (production) — uses
      ``data/backups_probe/`` scoped to the probe.
    * Never calls --restore --commit.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import ledger_insurance as li  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(
    _ROOT, "data", "cache", "probe_R27_T7_results.json"
)
PROBE_BACKUP_DIR = os.path.join(_ROOT, "data", "backups_probe")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _locate_ledger() -> Dict[str, Any]:
    """Find the best ledger to probe against. Never returns a write path."""
    candidates = [
        Path(_ROOT) / "data" / "pnl_ledger.csv",
        # Worktree fallback — the maintainer keeps the real ledger in the
        # main repo's data dir; worktrees often have their own empty data/.
        Path(_ROOT).parent.parent.parent / "data" / "pnl_ledger.csv",
    ]
    for c in candidates:
        try:
            if c.exists() and c.is_file() and c.stat().st_size > 0:
                return {"path": str(c), "synthetic": False,
                        "size_bytes": c.stat().st_size}
        except OSError:
            continue
    # Fallback — synthetic ledger so the probe still validates the script
    # end-to-end on a fresh clone with no real ledger.
    tmp = Path(tempfile.mkdtemp(prefix="R27_T7_probe_ledger_"))
    p = tmp / "pnl_ledger.csv"
    lines = ["ts,bet_id,stake,result,pnl"]
    for i in range(100):
        lines.append(f"2026-05-26T12:00:00Z,bet{i:05d},10.0,W,9.09")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(p), "synthetic": True, "size_bytes": p.stat().st_size}


def _run_probe() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "probe":      "R27_T7",
        "started_at": _iso_now(),
    }
    try:
        loc = _locate_ledger()
        out["ledger"] = loc
        ledger_path = Path(loc["path"])
        backup_dir = Path(PROBE_BACKUP_DIR)
        # Clean any leftovers from prior probe runs of the same date to
        # keep the snapshot deterministic.
        from datetime import date as _date_cls
        date_str = _date_cls.today().isoformat()
        existing = backup_dir / f"pnl_ledger.csv.{date_str}.gz"
        if existing.exists():
            try:
                existing.unlink()
            except OSError:
                pass
        sidecar = existing.with_suffix(existing.suffix + ".sha256")
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass

        # ---- (1) Backup against the real ledger ----
        res = li.backup(
            ledger_path=ledger_path, backup_dir=backup_dir,
            keep=30, today=date_str,
        )
        out["backup"] = res
        out["backup_ok"] = bool(res.get("ok"))
        if not res.get("ok"):
            out["ship_ok"] = False
            out["ended_at"] = _iso_now()
            return out

        gz_path = Path(res["gz_path"])
        sidecar_path = gz_path.with_suffix(gz_path.suffix + ".sha256")

        # ---- (2) File-system invariants ----
        out["gz_exists"]      = gz_path.exists()
        out["sidecar_exists"] = sidecar_path.exists()
        out["backup_size_mb"] = (
            gz_path.stat().st_size / 1024.0 / 1024.0
            if gz_path.exists() else 0.0
        )
        # Row count = newlines in the decompressed payload.
        out["backup_rows"] = li._gzip_row_count(gz_path)

        # ---- (3) Verify catches no corruption right after write ----
        v = li.verify(backup_dir=backup_dir, date_str=date_str)
        out["verify"] = v
        out["verify_ok"] = bool(v.get("ok"))

        # ---- (4) List returns our entry ----
        listed = li.list_backups(backup_dir=backup_dir)
        out["list_n"] = len(listed)
        out["list_dates"] = [e["date"] for e in listed]
        out["list_contains_today"] = any(
            e["date"] == date_str for e in listed
        )

        # ---- (5) Restore dry-run is no-op + recognises our backup ----
        rr = li.restore(
            date_str=date_str, ledger_path=ledger_path,
            backup_dir=backup_dir, commit=False,
        )
        out["restore_dryrun"] = {
            "ok":         rr.get("ok"),
            "dry_run":    rr.get("dry_run"),
            "commit":     rr.get("commit"),
            "reason":     rr.get("reason"),
            "expected":   rr.get("expected_sha256"),
            "actual":     rr.get("actual_sha256"),
        }
        out["restore_dryrun_ok"] = bool(
            rr.get("ok") and rr.get("dry_run") is True
        )

        # ---- Headline ship fields ----
        out["sha256_short"] = (res.get("sha256") or "")[:16]
        out["ship_ok"] = bool(
            out.get("backup_ok")
            and out.get("gz_exists")
            and out.get("sidecar_exists")
            and out.get("verify_ok")
            and out.get("list_contains_today")
            and out.get("restore_dryrun_ok")
        )
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        out["error"] = repr(exc)
        out["ship_ok"] = False

    out["ended_at"] = _iso_now()
    return out


def main() -> int:
    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    try:
        result = _run_probe()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        result = {
            "probe":     "R27_T7",
            "timestamp": _iso_now(),
            "ship_ok":   False,
            "error":     repr(exc),
        }
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ship_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
