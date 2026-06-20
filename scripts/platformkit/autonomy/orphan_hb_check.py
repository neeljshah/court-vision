"""scripts.platformkit.autonomy.orphan_hb_check -- orphan heartbeat registry check.

IOP-06: Scans the live heartbeat directory for .txt files whose stem is NOT
declared in any supervised spec (supervisor.manifest / supervisor.stack_specs).
These "orphan" heartbeats are written by processes that once ran (or still run)
but have NO owning spec, so the supervisor cannot observe or restart them and the
health aggregator cannot surface their liveness.

READ-ONLY. Never mutates heartbeat files, spec files, or registry. NEVER raises.
Writes one JSON report: data/cache/ops/orphan_hb_report.json (atomic tmp+replace).

WHAT "owned" MEANS:
  Any spec in supervisor.manifest() that carries a heartbeat_path under
  data/cache/daemon_heartbeats/ owns the stem of that path. Stems from OTHER
  directories (e.g. data/frontend/ingame/_heartbeat.json) are excluded from the
  scan -- the orphan check only covers daemon_heartbeats/*.txt.

HONEST DEGRADE RAIL:
  * A missing/unreadable heartbeat directory -> orphan_stems=[] with a note
    (absence of the directory is not evidence of orphans, just no data yet).
  * A manifest import failure -> orphan_stems=None (distinct sentinel, not []),
    and an explicit note so ops does not read [] as "all clear".
  * The report is ATOMIC (tmp + os.replace) so a reader never sees a torn file.
  * The file field "stale_never_green" = true signals this tool is passive.

ASCII; stdlib + repo-internal; <=300 LOC. Calibration not edge; no $ field.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List, Optional

_REPO = pathlib.Path(__file__).resolve().parents[3]
_HB_DIR = _REPO / "data" / "cache" / "daemon_heartbeats"
_REPORT_PATH = _REPO / "data" / "cache" / "ops" / "orphan_hb_report.json"

# Stems owned by the autonomy_monitor_runner spec (always in the owned set even
# if the manifest import partially fails) -- added as a safety fallback only.
_KNOWN_AUTONOMY_STEMS = frozenset({"m5_autonomy_monitor"})


# ---------------------------------------------------------------------------
# Owned-stems resolution
# ---------------------------------------------------------------------------

def _manifest_owned_stems() -> Optional[frozenset]:
    """Return the set of heartbeat stems declared in supervisor.manifest().

    Covers ONLY data/cache/daemon_heartbeats/*.txt stems (other directories such
    as data/frontend/... are out of scope for this scanner).

    Returns None on any import/invocation failure so the caller can distinguish
    "no specs owned" from "could not load the manifest" (an honest UNKNOWN).
    Never raises.
    """
    try:
        from supervisor.manifest import manifest as _manifest, HEARTBEAT
    except Exception:  # noqa: BLE001
        return None

    owned: set = set()
    try:
        specs = _manifest()
    except Exception:  # noqa: BLE001
        return None

    for spec in specs:
        try:
            readiness = getattr(spec, "readiness", None)
            if readiness is None:
                continue
            hb_path = getattr(readiness, "heartbeat_path", None)
            if not hb_path:
                continue
            p = pathlib.Path(str(hb_path))
            # Only stems under daemon_heartbeats/ belong to this scanner.
            if p.parent.name == "daemon_heartbeats" and p.suffix == ".txt":
                owned.add(p.stem)
        except Exception:  # noqa: BLE001 -- a single bad spec must not abort
            continue

    return frozenset(owned)


# ---------------------------------------------------------------------------
# On-disk scan
# ---------------------------------------------------------------------------

def _disk_stems(hb_dir: pathlib.Path) -> List[str]:
    """Return sorted list of .txt file stems in *hb_dir*. Returns [] on error."""
    try:
        if not hb_dir.is_dir():
            return []
        return sorted(p.stem for p in hb_dir.glob("*.txt"))
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------

def run_check(
    *,
    hb_dir: Optional[pathlib.Path] = None,
    report_path: Optional[pathlib.Path] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Identify orphan heartbeat stems and write the report. Never raises.

    Parameters
    ----------
    hb_dir :
        Heartbeat directory to scan (default: data/cache/daemon_heartbeats/).
        Injected in tests to use a temp directory.
    report_path :
        Destination for the JSON report (default: data/cache/ops/orphan_hb_report.json).
        Injected in tests to use a temp path.
    now :
        Epoch timestamp (default: time.time()). Injected for deterministic tests.

    Returns
    -------
    dict
        The report document (also written to *report_path* atomically).
        Keys:
          scanned_at      -- ISO-like epoch float.
          hb_dir          -- directory scanned (str).
          all_stems       -- all .txt stems found.
          owned_stems     -- stems with a supervising spec.
          orphan_stems    -- stems NOT owned by any spec (the alert set).
          manifest_ok     -- bool; False if manifest import failed.
          notes           -- list of plain-text notes.
          honest_note     -- calibration disclaimer.
          stale_never_green -- True (this tool is passive / read-only).
    """
    t = float(now) if now is not None else time.time()
    scan_dir = hb_dir if hb_dir is not None else _HB_DIR
    out_path = report_path if report_path is not None else _REPORT_PATH

    notes: List[str] = []

    # 1. Resolve owned stems from the manifest.
    manifest_stems = _manifest_owned_stems()
    manifest_ok = manifest_stems is not None
    if not manifest_ok:
        notes.append(
            "orphan_hb_check: manifest import failed; orphan_stems=None "
            "(cannot determine owned set -- ops alert required)"
        )
        owned_stems: List[str] = []
        orphan_stems: Optional[List[str]] = None  # honest UNKNOWN
    else:
        all_owned = manifest_stems | _KNOWN_AUTONOMY_STEMS
        owned_stems = sorted(all_owned)

    # 2. Scan the disk.
    all_stems = _disk_stems(scan_dir)

    if not scan_dir.is_dir():
        notes.append(
            "orphan_hb_check: heartbeat directory absent (%s); "
            "no stems to scan -- not an error if the stack has not started yet"
            % scan_dir
        )

    # 3. Compute orphans (only when manifest loaded successfully).
    if manifest_ok:
        all_owned_set = set(owned_stems)
        orphan_stems = sorted(s for s in all_stems if s not in all_owned_set)
        if orphan_stems:
            notes.append(
                "orphan_hb_check: %d orphan stem(s) found -- no owning spec in "
                "supervisor.manifest: %s"
                % (len(orphan_stems), ", ".join(orphan_stems))
            )
        else:
            notes.append(
                "orphan_hb_check: all %d on-disk stem(s) are owned by a spec"
                % len(all_stems)
            )

    doc: Dict[str, Any] = {
        "scanned_at": t,
        "hb_dir": str(scan_dir),
        "all_stems": all_stems,
        "owned_stems": owned_stems,
        "orphan_stems": orphan_stems,
        "manifest_ok": manifest_ok,
        "notes": notes,
        "honest_note": (
            "READ-ONLY orphan heartbeat check; calibration not edge; no $ field. "
            "orphan_stems=None means manifest load failed (honest UNKNOWN, not clear). "
            "stale_never_green=true: this tool is passive and never writes heartbeats."
        ),
        "stale_never_green": True,
    }

    _atomic_write_json(out_path, doc)
    return doc


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------

def _atomic_write_json(path: pathlib.Path, doc: Dict[str, Any]) -> bool:
    """Write *doc* as ASCII JSON to *path* atomically (tmp + os.replace).

    Returns True on success, False on any I/O error. Never raises.
    A reader never sees a torn file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# CLI shim
# ---------------------------------------------------------------------------

def _main() -> int:  # pragma: no cover -- thin CLI wrapper
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="IOP-06 orphan heartbeat registry check. "
                    "READ-ONLY -- never mutates heartbeat or spec files."
    )
    p.add_argument(
        "--hb-dir",
        default=str(_HB_DIR),
        help="Heartbeat directory to scan (default: %(default)s)",
    )
    p.add_argument(
        "--report",
        default=str(_REPORT_PATH),
        help="Output JSON report path (default: %(default)s)",
    )
    a = p.parse_args()
    doc = run_check(
        hb_dir=pathlib.Path(a.hb_dir),
        report_path=pathlib.Path(a.report),
    )
    orphans = doc.get("orphan_stems")
    if orphans is None:
        print("orphan_hb_check: manifest load FAILED -- cannot assess orphans", flush=True)
        return 2
    print(
        "orphan_hb_check: %d orphan(s) out of %d stems | report -> %s"
        % (len(orphans), len(doc.get("all_stems") or []), a.report),
        flush=True,
    )
    if orphans:
        for stem in orphans:
            print("  ORPHAN: %s" % stem, flush=True)
    return 1 if orphans else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["run_check"]
