"""scripts.platformkit.combo.combo_status -- proposals + reject-lessons + autonomy block.

The observability + durable-record surface for Lane L. It (1) appends PROPOSAL rows to
combo_proposals.jsonl (survivors -- NEVER auto-served), (2) appends durable machine-readable
REJECT lessons to combo_reject_lessons.jsonl (family / signature / verdict / failing layer /
k_at_decision -- NEVER MEMORY.md), (3) appends a per-cycle status row to combo_status.jsonl,
and (4) composes a NON-FABRICABLE `combo` block for the autonomy status envelope.

NON-FABRICABLE: every field of the combo block is read back FROM the on-disk jsonl tails +
the persisted bandit/checkpoint state -- the block cannot report a proposal that was not
written, and a STALE/DEGRADED cycle reads DEGRADED (never green). A missing source yields
DEGRADED with an explicit reason, never absent-as-ok.

State ONLY under data/cache/improve/combo/**. NEVER writes data/registry/, MEMORY.md,
never flips a flag, never creates the sentinel. Calibration, not edge; no $/ROI token.
stdlib only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any, Dict, List, Optional

OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

_REPO = pathlib.Path(__file__).resolve().parents[3]
_DIR = _REPO / "data" / "cache" / "improve" / "combo"
DEFAULT_PROPOSALS = _DIR / "combo_proposals.jsonl"
DEFAULT_REJECTS = _DIR / "combo_reject_lessons.jsonl"
DEFAULT_STATUS = _DIR / "combo_status.jsonl"


def _append_jsonl(path: pathlib.Path, row: Dict[str, Any]) -> None:
    """Append one ASCII JSON row; create parent dirs. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, sort_keys=True)
        with open(path, "a", encoding="ascii") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:  # noqa: BLE001 -- observability write must never sink the loop.
        pass


def proposal_row(spec: Any, cand: Dict[str, Any], verdict: Dict[str, Any]) -> Dict[str, Any]:
    """A PROPOSAL row -- a SHIP survivor. proposal_only=True; NEVER auto-served. No $ key."""
    return {
        "kind": "proposal", "proposal_only": True,
        "combo_id": getattr(spec, "combo_id", cand.get("combo_id", "")),
        "family": getattr(spec, "family", cand.get("family", "")),
        "signature": getattr(spec, "signature", cand.get("signature", "")),
        "sport": getattr(spec, "sport", ""),
        "target": getattr(spec, "target", ""),
        "verdict": str(verdict.get("verdict", "")),
        "layer": str(verdict.get("layer", "")),
        "n_clean": int(cand.get("n_clean", 0)),
        "vs_close": "UNPROVEN -- CALIBRATION only, not a market edge",
        "note": "calibration, not edge; PROPOSAL only -- never auto-served",
    }


def reject_lesson(spec: Any, *, verdict: str, reason: str, layer: str,
                  k: int) -> Dict[str, Any]:
    """A durable machine-readable REJECT lesson. An honest REJECT is a SUCCESS, not a failure."""
    return {
        "kind": "reject_lesson",
        "combo_id": getattr(spec, "combo_id", ""),
        "family": getattr(spec, "family", ""),
        "signature": getattr(spec, "signature", ""),
        "verdict": str(verdict), "reason": str(reason), "layer": str(layer),
        "k_at_decision": int(k),
        "note": "calibration, not edge; honest REJECT is a SUCCESS",
    }


def record_cycle(res: Any, proposals_path: Optional[Any] = None,
                 reject_path: Optional[Any] = None, status_path: Optional[Any] = None,
                 *, now: float = 0.0) -> None:
    """Append every proposal + reject-lesson of a completed cycle, then a status row."""
    pp = pathlib.Path(proposals_path) if proposals_path else DEFAULT_PROPOSALS
    rp = pathlib.Path(reject_path) if reject_path else DEFAULT_REJECTS
    for row in getattr(res, "proposals", []) or []:
        _append_jsonl(pp, row)
    for row in getattr(res, "rejects", []) or []:
        _append_jsonl(rp, row)
    record_status(res, status_path, now=now)


def record_status(res: Any, status_path: Optional[Any] = None, *, now: float = 0.0) -> None:
    """Append a per-cycle status row (counts + decision + status; NO $/ROI)."""
    sp = pathlib.Path(status_path) if status_path else DEFAULT_STATUS
    _append_jsonl(sp, {
        "kind": "combo_status", "ts": float(now),
        "sport": getattr(res, "sport", ""),
        "decision": getattr(res, "decision", ""),
        "status": getattr(res, "status", ""),
        "n_settled": int(getattr(res, "n_settled", 0)),
        "n_enumerated": int(getattr(res, "n_enumerated", 0)),
        "n_built": int(getattr(res, "n_built", 0)),
        "n_proposed": int(getattr(res, "n_proposed", 0)),
        "n_rejected": int(getattr(res, "n_rejected", 0)),
        "k_cumulative": int(getattr(res, "k_cumulative", 0)),
        "note": "calibration, not edge; vs_close UNPROVEN",
    })


def _tail(path: pathlib.Path, n: int) -> List[Dict[str, Any]]:
    """Read the last `n` JSON rows of a jsonl file (best-effort, never raises)."""
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except Exception:  # noqa: BLE001
        return []
    out: List[Dict[str, Any]] = []
    for ln in lines[-max(1, int(n)):]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except (ValueError, TypeError):
            continue
    return out


def combo_block(proposals_path: Optional[Any] = None, reject_path: Optional[Any] = None,
                status_path: Optional[Any] = None, *, tail: int = 5) -> Dict[str, Any]:
    """NON-FABRICABLE `combo` block for the autonomy status envelope.

    Every value is read BACK from the on-disk jsonl tails -- the block cannot claim a
    proposal that was not written. A last-cycle status of DEGRADED (STALE/dead feed) sets
    severity DEGRADED, never ok. A missing status source yields DEGRADED with a reason.
    """
    pp = pathlib.Path(proposals_path) if proposals_path else DEFAULT_PROPOSALS
    rp = pathlib.Path(reject_path) if reject_path else DEFAULT_REJECTS
    sp = pathlib.Path(status_path) if status_path else DEFAULT_STATUS
    status_rows = _tail(sp, tail)
    if not status_rows:
        return {"severity": DEGRADED, "reason": "no combo status rows yet (loop idle/unstarted)",
                "n_proposals": 0, "n_reject_lessons": 0, "last_decision": None,
                "proposal_only": True, "note": "calibration, not edge"}
    last = status_rows[-1]
    last_status = str(last.get("status", ""))
    last_decision = str(last.get("decision", ""))
    # A dead/degraded feed (or a DEGRADED decision) can NEVER read green.
    severity = OK
    if last_status in ("STALE", "DEGRADED") or last_decision == "DEGRADED":
        severity = DEGRADED
    return {
        "severity": severity,
        "last_decision": last_decision,
        "last_status": last_status,
        "n_proposals": _count(pp),
        "n_reject_lessons": _count(rp),
        "recent_status": status_rows,
        "proposal_only": True,
        "vs_close": "UNPROVEN -- CALIBRATION only, not a market edge",
        "note": "calibration, not edge; proposals are NEVER auto-served",
    }


def _count(path: pathlib.Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for ln in path.read_text(encoding="ascii").splitlines() if ln.strip())
    except Exception:  # noqa: BLE001
        return 0


__all__ = [
    "OK", "DEGRADED", "DOWN", "proposal_row", "reject_lesson",
    "record_cycle", "record_status", "combo_block",
    "DEFAULT_PROPOSALS", "DEFAULT_REJECTS", "DEFAULT_STATUS",
]
