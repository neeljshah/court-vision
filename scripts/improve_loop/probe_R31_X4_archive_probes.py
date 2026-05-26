"""probe_R31_X4_archive_probes.py — dry-run inventory probe for R31_X4.

Runs ``archive_probe_results.archive_probes(commit=False)`` against the
real ``data/cache/`` (LOCAL ONLY — no SSH/RunPod). Reports
``n_eligible_files`` and ``archive_size_mb_estimate``. Persists results
to ``data/cache/probe_R31_X4_results.json``.

Hard rules
----------
* Default: dry-run only. NEVER mutates real data.
* The ``--really-archive`` flag is required to call --commit; even then
  it only runs against the canonical repo root, never RunPod/SSH paths.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import archive_probe_results as apr  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(
    _ROOT, "data", "cache", "probe_R31_X4_results.json"
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_scan_root() -> Path:
    """If we're inside a worktree, prefer main repo root so the inventory
    reflects actual disk pressure on the maintainer's machine."""
    candidate = Path(_ROOT)
    parts = candidate.as_posix().split("/")
    if len(parts) >= 4 and parts[-3:-1] == [".claude", "worktrees"]:
        candidate = candidate.parents[2]
    if not (candidate / "data" / "cache").is_dir():
        candidate = Path(_ROOT)
    return candidate


def _run_probe(really_archive: bool = False, keep_days: int = 7) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "probe":      "R31_X4",
        "started_at": _iso_now(),
        "keep_days":  int(keep_days),
        "really_archive": bool(really_archive),
    }
    try:
        scan_root = _resolve_scan_root()
        out["scan_root"] = str(scan_root)
        dry = apr.archive_probes(
            root=scan_root, keep_days=keep_days,
            min_keep=apr.DEFAULT_MIN_KEEP, commit=False,
        )
        out["n_eligible_files"]       = int(dry.get("n_eligible", 0) or 0)
        out["archive_size_mb_estimate"] = float(dry.get("size_mb_estimate", 0.0) or 0.0)
        out["dry_run_archive_path"]   = dry.get("archive")
        out["dry_run_warnings"]       = list(dry.get("warnings", []) or [])

        if really_archive and out["n_eligible_files"] > 0:
            live = apr.archive_probes(
                root=scan_root, keep_days=keep_days,
                min_keep=apr.DEFAULT_MIN_KEEP, commit=True,
            )
            out["live_archive"]   = live.get("archive")
            out["live_sha256"]    = live.get("sha256")
            out["live_n_archived"] = int(live.get("n_archived", 0) or 0)
            out["live_n_deleted"]  = int(live.get("n_deleted", 0) or 0)
            out["live_size_mb"]    = float(live.get("size_mb_archive", 0.0) or 0.0)
            out["live_warnings"]   = list(live.get("warnings", []) or [])

        out["ship_ok"] = True
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        out["error"] = repr(exc)
        out["ship_ok"] = False
    out["ended_at"] = _iso_now()
    return out


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="R31_X4 archive-probe probe (dry-run default).")
    ap.add_argument("--really-archive", action="store_true",
                    help="actually run --commit (default OFF)")
    ap.add_argument("--keep", type=int, default=7)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    try:
        result = _run_probe(really_archive=bool(args.really_archive),
                            keep_days=int(args.keep))
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        result = {
            "probe":     "R31_X4",
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
