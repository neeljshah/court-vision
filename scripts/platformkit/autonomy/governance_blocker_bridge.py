"""scripts.platformkit.autonomy.governance_blocker_bridge -- surface governance
blockers (e.g. CLV ledger dups) on the ops face.

IOPiii-02: m18_dupaudit writes data/frontend/ops/clv_dup_report.json with
status=DUPS_FOUND when the ledger contains duplicate keys and governance exits
1. However, autonomy_status.json never reflects this -- ops reads DEGRADED only
for m1_producer, so a governance-BLOCKING condition is invisible to operators.

WHAT THIS MODULE DOES
---------------------
1.  ``snapshot(*, dup_report_path, out_path, now)`` -- reads
    clv_dup_report.json, builds a governance_blockers.json that lists every
    blocking condition, and atomically writes it. Called by an ops tick.

2.  ``merge_into(compose_doc, *, dup_report_path)`` -- degrade-only merge.
    If any blocker has blocking=True, the compose_doc["overall"] is degraded to
    at least DEGRADED and a note is appended. Never mutates the ledger.
    Never raises.

OUTPUT SCHEMA (governance_blockers.json): {blockers:[{name, status, n_dups, blocking}],
generated_at, honest_note}. INVARIANTS: absent -> UNAVAILABLE+blocking=True (never green);
DUPS_FOUND -> blocking=True; CLEAN -> blockers=[]; degrade-only; never mutates ledger;
no $ key; never raises; stdlib+ASCII.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List, Optional

# Severity constants -- mirrors status_composer to avoid circular import.
_OK = "ok"
_DEGRADED = "degraded"
_DOWN = "down"
_RANK = {_OK: 0, _DEGRADED: 1, _DOWN: 2}
_BY_RANK = {0: _OK, 1: _DEGRADED, 2: _DOWN}

_REPO = pathlib.Path(__file__).resolve().parents[3]

# Canonical input: written by m18_dupaudit.
DEFAULT_DUP_REPORT_PATH = (
    _REPO / "data" / "frontend" / "ops" / "clv_dup_report.json"
)

# Canonical output: written by this module.
DEFAULT_BLOCKERS_PATH = (
    _REPO / "data" / "frontend" / "ops" / "governance_blockers.json"
)

_HONEST_NOTE = (
    "calibration not edge; no $ field; degrade-only merge; "
    "absent dup report -> UNAVAILABLE (never green on missing data)."
)

# Status strings from clv_dup_report.json.
_STATUS_DUPS_FOUND = "DUPS_FOUND"
_STATUS_CLEAN = "CLEAN"
_STATUS_UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _degrade(current: str, candidate: str) -> str:
    """Return the WORSE of two severity strings. Never upgrades."""
    cur = _RANK.get(current, _RANK[_DEGRADED])
    cand = _RANK.get(candidate, _RANK[_DEGRADED])
    return _BY_RANK[max(cur, cand)]


def _read_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Best-effort JSON read. Missing / malformed -> None. Never raises."""
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="ascii")
        if not raw.strip():
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _build_clv_dup_blocker(
    dup_report_path: pathlib.Path,
) -> Dict[str, Any]:
    """Read clv_dup_report.json and return a single blocker dict.

    Absent file or read error -> UNAVAILABLE + blocking=True (never green).
    DUPS_FOUND -> blocking=True.
    CLEAN -> blocking=False.
    """
    doc = _read_json(dup_report_path)
    if doc is None:
        # File absent or unreadable: unknown is not safe; treat as blocking.
        return {
            "name": "clv_ledger_dups",
            "status": _STATUS_UNAVAILABLE,
            "n_dups": 0,
            "blocking": True,
        }

    raw_status = str(doc.get("status") or "").upper()
    if raw_status == _STATUS_DUPS_FOUND:
        n_dups = int(doc.get("n_dups") or 0)
        return {
            "name": "clv_ledger_dups",
            "status": _STATUS_DUPS_FOUND,
            "n_dups": n_dups,
            "blocking": True,
        }
    if raw_status == _STATUS_CLEAN:
        return {
            "name": "clv_ledger_dups",
            "status": _STATUS_CLEAN,
            "n_dups": 0,
            "blocking": False,
        }
    # Unrecognised status: treat as unavailable (conservative).
    return {
        "name": "clv_ledger_dups",
        "status": _STATUS_UNAVAILABLE,
        "n_dups": 0,
        "blocking": True,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def snapshot(
    *,
    dup_report_path: Optional[pathlib.Path] = None,
    out_path: Optional[pathlib.Path] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Read clv_dup_report.json, build and atomically write governance_blockers.json.

    Parameters
    ----------
    dup_report_path:
        Path to clv_dup_report.json. Defaults to the canonical ops location.
    out_path:
        Destination for governance_blockers.json. Defaults to the canonical path.
    now:
        Epoch timestamp for generated_at; defaults to time.time().

    Returns
    -------
    dict
        The written governance_blockers document.  Also written atomically to
        *out_path*. Never raises; returns an UNAVAILABLE document on I/O error.
    """
    try:
        dup_path = (
            pathlib.Path(dup_report_path)
            if dup_report_path is not None
            else DEFAULT_DUP_REPORT_PATH
        )
        dest = (
            pathlib.Path(out_path)
            if out_path is not None
            else DEFAULT_BLOCKERS_PATH
        )
        ts = float(now) if now is not None else time.time()

        blocker = _build_clv_dup_blocker(dup_path)

        # Only emit non-empty blockers list when there IS a blocker entry.
        # If CLEAN -> blockers=[] as per spec.
        if blocker["status"] == _STATUS_CLEAN:
            blockers: List[Dict[str, Any]] = []
        else:
            blockers = [blocker]

        doc: Dict[str, Any] = {
            "blockers": blockers,
            "generated_at": ts,
            "honest_note": _HONEST_NOTE,
        }

        # Atomic write via tmp + os.replace.
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(dest))
        return doc

    except Exception:  # noqa: BLE001 -- must never raise
        return {
            "blockers": [{
                "name": "clv_ledger_dups",
                "status": _STATUS_UNAVAILABLE,
                "n_dups": 0,
                "blocking": True,
            }],
            "generated_at": float(now) if now is not None else time.time(),
            "honest_note": _HONEST_NOTE,
        }


def merge_into(
    compose_doc: Dict[str, Any],
    *,
    dup_report_path: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """Degrade-only merge of governance blocker state into a compose document.

    If any blocker is blocking=True, compose_doc["overall"] is degraded to at
    least DEGRADED and a descriptive note is appended to compose_doc["notes"].

    Parameters
    ----------
    compose_doc:
        The canonical autonomy status document produced by status_composer.compose.
        This dict is mutated IN-PLACE (degrade-only -- overall may only worsen,
        notes may only grow). The ledger is never touched.
    dup_report_path:
        Path to clv_dup_report.json. Defaults to the canonical ops location.

    Returns
    -------
    dict
        The same (mutated) compose_doc, for convenience chaining.
        Never raises; returns compose_doc unchanged on any error.
    """
    try:
        dup_path = (
            pathlib.Path(dup_report_path)
            if dup_report_path is not None
            else DEFAULT_DUP_REPORT_PATH
        )
        blocker = _build_clv_dup_blocker(dup_path)

        if not blocker.get("blocking"):
            # CLEAN -- nothing to degrade.
            return compose_doc

        # At least one blocking condition: degrade overall to >= DEGRADED.
        current_overall = str(compose_doc.get("overall", _DEGRADED))
        if current_overall not in _RANK:
            current_overall = _DEGRADED
        compose_doc["overall"] = _degrade(current_overall, _DEGRADED)

        # Append an honest human-readable note.
        notes: List[str] = compose_doc.get("notes") or []
        if not isinstance(notes, list):
            notes = list(notes)
        status = blocker["status"]
        n_dups = blocker.get("n_dups", 0)
        if status == _STATUS_DUPS_FOUND:
            notes.append(
                "governance BLOCKED: clv_ledger_dups DUPS_FOUND "
                "(n_dups=%d); autonomy gates require a clean ledger." % n_dups
            )
        else:
            notes.append(
                "governance BLOCKED: clv_dup_report.json UNAVAILABLE; "
                "cannot confirm ledger integrity (stale-never-green)."
            )
        compose_doc["notes"] = notes

        return compose_doc

    except Exception:  # noqa: BLE001 -- merge must never crash the compose caller
        return compose_doc


__all__ = [
    "snapshot",
    "merge_into",
    "DEFAULT_DUP_REPORT_PATH",
    "DEFAULT_BLOCKERS_PATH",
]
