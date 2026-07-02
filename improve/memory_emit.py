"""improve.memory_emit -- LLM-free durable-learning proposal emitter.

On every SHIP/REJECT/HOLD/INSUFFICIENT_DATA verdict from the self-improvement
ratchet, emit_memory_proposal(verdict) writes one structured JSON artifact under
data/frontend/improve/proposals/<ts>.json describing WHAT happened and WHY in a
shape that mirrors the existing MEMORY.md entry format.

WHAT THIS IS NOT:
- It does NOT write to MEMORY.md or any file under the memory/ dir.  A human or
  the ratchet loop applies the artifact to MEMORY.md (or ignores it).  The emitter
  is a PROPOSAL emitter only -- append-only, never mutates anything a human owns.
- It does NOT claim a $ edge anywhere.  The durable learning is calibration-only.

SHAPE of each proposal artifact:
  {
    "schema":       "memory_proposal_v1",
    "ts":           "<ISO-8601 UTC>",       -- wall-clock of emit
    "verdict_ts":   "<ISO-8601 UTC>|null",  -- ts embedded in the verdict dict
    "sport":        "<str>|null",
    "verdict":      "SHIP|REJECT|HOLD|INSUFFICIENT_DATA|<other>",
    "headline":     "<str>",                -- one-sentence summary (ASCII)
    "metrics":      {<subset of numeric verdict fields>},
    "reason":       "<str>",                -- copied from verdict["reason"]
    "note":         "<str>",                -- calibration disclaimer
    "apply_to_memory": false,               -- always False; human decides
    "source_ledger": "data/frontend/improve_ledger.jsonl"
  }

GUARANTEES:
- Pure, append-only, never raises.  Missing/corrupt verdict -> writes a
  PROPOSAL_ERROR artifact so the loop can see what happened.
- Never writes to data/registry/, MEMORY.md, or any human-gated path.
- ASCII-only output (no unicode, no emoji).
- <=300 LOC; no external deps (stdlib + pathlib only).
"""
from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_PROPOSALS_DIR = _REPO / "data" / "frontend" / "improve" / "proposals"

_CALIBRATION_NOTE = (
    "calibration != edge: better-calibrated probabilities do NOT imply "
    "beating the market close or a positive expected value"
)
_SOURCE_LEDGER = "data/frontend/improve_ledger.jsonl"

_NUMERIC_FIELDS = (
    "baseline_brier", "recal_brier", "delta_brier",
    "baseline_ece", "recal_ece",
    "dm_stat", "dm_p", "dm_n",
    "n_settled",
)

_VERDICT_HEADLINES: Dict[str, str] = {
    "SHIP": (
        "Recalibration passed all proper-score gates and ratcheted forward; "
        "no dollar edge claimed."
    ),
    "REJECT": (
        "Recalibration REJECTED: candidate regressed or the leak guard fired; "
        "frozen baseline retained. Honest reject = success."
    ),
    "HOLD": (
        "No meaningful calibration improvement detected; frozen baseline held. "
        "Model already well-calibrated on this corpus."
    ),
    "INSUFFICIENT_DATA": (
        "Insufficient real settled games to recalibrate leak-free; "
        "cold-start state logged honestly, no improvement fabricated."
    ),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts_safe(name: str, verdict: Dict[str, Any]) -> str:
    """Return a filesystem-safe timestamp prefix for the proposal filename."""
    # Use the verdict ts if available; else wall-clock now.
    raw = str(verdict.get("ts") or "").strip()
    if not raw:
        raw = _now_iso()
    # Strip non-filename chars: keep digits and letters only.
    safe = "".join(c if c.isalnum() else "_" for c in raw)
    return safe[:32]


def _extract_metrics(verdict: Dict[str, Any]) -> Dict[str, Any]:
    """Pull numeric fields from the verdict dict, drop None/missing."""
    out: Dict[str, Any] = {}
    for k in _NUMERIC_FIELDS:
        v = verdict.get(k)
        if isinstance(v, (int, float)) and v is not None:
            out[k] = float(v)
    # Carry readout sub-dict if present (Brier/ECE raw readout).
    ro = verdict.get("readout")
    if isinstance(ro, dict):
        raw_brier = ro.get("raw_brier")
        raw_ece = ro.get("raw_ece")
        if isinstance(raw_brier, (int, float)):
            out["readout_raw_brier"] = float(raw_brier)
        if isinstance(raw_ece, (int, float)):
            out["readout_raw_ece"] = float(raw_ece)
    return out


def _build_proposal(verdict: Dict[str, Any]) -> Dict[str, Any]:
    v = str(verdict.get("verdict") or "UNKNOWN").strip().upper()
    headline = _VERDICT_HEADLINES.get(v, "Ratchet cycle verdict: %s" % v)
    reason = str(verdict.get("reason") or verdict.get("note") or "").strip()
    sport = verdict.get("sport")
    return {
        "schema": "memory_proposal_v1",
        "ts": _now_iso(),
        "verdict_ts": str(verdict.get("ts") or ""),
        "sport": (str(sport).lower() if sport is not None else None),
        "verdict": v,
        "headline": headline,
        "metrics": _extract_metrics(verdict),
        "reason": reason,
        "note": _CALIBRATION_NOTE,
        "apply_to_memory": False,
        "source_ledger": _SOURCE_LEDGER,
    }


def _write_proposal(
    proposal: Dict[str, Any],
    proposals_dir: Optional[Path],
) -> Path:
    """Write proposal as JSON to proposals_dir/<ts>_<sport>_<verdict>.json.

    Uses temp+os.replace for atomic writes (no torn partial files).
    """
    out_dir = proposals_dir if proposals_dir is not None else _DEFAULT_PROPOSALS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    ts_safe = "".join(
        c if c.isalnum() else "_" for c in proposal.get("ts", "")
    )[:32]
    sport_safe = str(proposal.get("sport") or "all")
    verdict_safe = str(proposal.get("verdict") or "UNKNOWN")
    fname = "%s_%s_%s.json" % (ts_safe, sport_safe, verdict_safe)
    out_path = out_dir / fname

    payload = json.dumps(proposal, indent=2, sort_keys=True, default=str)
    # Atomic write: temp + os.replace
    tmp = out_path.with_name(out_path.name + ".tmp.%d" % os.getpid())
    tmp.write_text(payload, encoding="ascii")
    os.replace(tmp, out_path)
    return out_path


def emit_memory_proposal(
    verdict: Dict[str, Any],
    proposals_dir: Optional[Path] = None,
) -> Path:
    """Emit one PROPOSAL artifact for this ratchet verdict.  Never raises.

    Parameters
    ----------
    verdict:
        The dict returned by improve_cycle / improve_all (or any dict with at
        least a "verdict" key).  Corrupt / missing fields degrade gracefully.
    proposals_dir:
        Override the output directory (default: data/frontend/improve/proposals/).
        Useful in tests to write to a tmp dir without touching real data.

    Returns
    -------
    Path of the written proposal file.
    """
    try:
        proposal = _build_proposal(verdict)
        return _write_proposal(proposal, proposals_dir)
    except Exception:  # noqa: BLE001 -- never raise; write an error artifact instead
        try:
            error_proposal = {
                "schema": "memory_proposal_v1",
                "ts": _now_iso(),
                "verdict_ts": "",
                "sport": None,
                "verdict": "PROPOSAL_ERROR",
                "headline": "emit_memory_proposal failed; see traceback in reason.",
                "metrics": {},
                "reason": traceback.format_exc()[:400],
                "note": _CALIBRATION_NOTE,
                "apply_to_memory": False,
                "source_ledger": _SOURCE_LEDGER,
            }
            out_dir = proposals_dir if proposals_dir is not None else _DEFAULT_PROPOSALS_DIR
            out_dir.mkdir(parents=True, exist_ok=True)
            ts_safe = "".join(c if c.isalnum() else "_" for c in _now_iso())[:32]
            fname = "%s_error_PROPOSAL_ERROR.json" % ts_safe
            out_path = out_dir / fname
            out_path.write_text(
                json.dumps(error_proposal, indent=2, default=str), encoding="ascii"
            )
            return out_path
        except Exception:  # noqa: BLE001 -- truly last resort: return a sentinel path
            return _DEFAULT_PROPOSALS_DIR / "emit_failed.json"


__all__ = ["emit_memory_proposal", "_DEFAULT_PROPOSALS_DIR", "_CALIBRATION_NOTE"]
