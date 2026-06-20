"""predict_service.progress_semantics -- honest_note helper for /progress/* routes.

The /progress/summary and /progress/readiness endpoints expose engine_enabled=True
while model_status may be degraded or stale.  A reader who sees
engine_enabled=True without context could mistake it for a production-ready
signal.  This module attaches a clarifying honest_note that mirrors the
/api/improve/timeline pattern:

    engine_enabled=True  -> measurement loop is running; real-money gate = DENY
    engine_enabled=False -> pipeline sentinel absent; loop not running

The note never contains $, roi, pnl, or any retracted figure.
The helper never raises on a partial / missing status dict (safe default).

RAILS: no $ field; no retracted numbers; ASCII only; <=300 LOC; pure-function.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Retracted figures we must never include in any output string.
_BANNED_FRAGMENTS = (
    "18.38", "0.119", "54%", "78.11", "8.94", "54.57",
    "$", "roi", "pnl", "profit",
)

_NOTE_ENABLED = (
    "engine_enabled=true means the MEASUREMENT loop is running: "
    "calibration metrics are being collected and gates are being evaluated. "
    "It does NOT mean the model is production-authorized. "
    "real-money gate = DENY until the human PIPELINE_ENABLED sentinel is set. "
    "vs_close UNPROVEN; model_static=True; no edge is claimed."
)

_NOTE_DISABLED = (
    "engine_enabled=false: the PIPELINE_ENABLED sentinel is absent; "
    "the measurement loop is not running. "
    "real-money gate = DENY. model_static=True; no edge is claimed."
)


def engine_honest_note(
    status: Optional[Dict[str, Any]] = None,
    engine_enabled: Optional[bool] = None,
) -> str:
    """Return a clarifying honest_note string for the /progress/* endpoints.

    Parameters
    ----------
    status:
        The progress row dict (may be None or partial -- never raises).
    engine_enabled:
        Explicit override.  When None the value is read from ``status``.

    Returns
    -------
    str
        A non-empty ASCII honest_note that contains:
          - 'measurement loop' and 'real-money gate = DENY' when enabled is True
          - a neutral disabled note when enabled is False or unknown
          - NO $, roi, pnl, or any retracted figure regardless of input
    """
    # Determine enabled state safely.
    if engine_enabled is None:
        if isinstance(status, dict):
            raw = status.get("engine_enabled")
            engine_enabled = bool(raw) if raw is not None else False
        else:
            engine_enabled = False

    note = _NOTE_ENABLED if engine_enabled else _NOTE_DISABLED

    # Safety check: ensure no banned fragment leaked into the note string.
    note_lower = note.lower()
    for frag in _BANNED_FRAGMENTS:
        if frag.lower() in note_lower:
            # Strip the offending fragment defensively -- should never happen,
            # but keeps the invariant ironclad.
            note = note.replace(frag, "")

    return note


__all__ = ["engine_honest_note"]
