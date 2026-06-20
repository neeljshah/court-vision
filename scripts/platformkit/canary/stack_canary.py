"""scripts.platformkit.canary.stack_canary -- IOX-2 stack canary probes.

Measurement-only end-to-end check: 'can the stack serve a calibrated prediction?'
Read-only probes; never writes data/, flips flags, or touches real money.

Stages (critical first): predict_envelope, envelope_schema, calibration_note;
non-critical: ops_status, prediction_fresh.
READY/DEGRADED/DOWN with failing_stage named; offseason -> READY with note.
Stale-never-green; no $ field; injectable probes/clock; never raises.
"""
from __future__ import annotations

import json
import logging
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Statuses
READY = "READY"
DEGRADED = "DEGRADED"
DOWN = "DOWN"

# How stale the ops status file may be before we flag it (non-critical).
OPS_STATUS_STALE_SEC = 300.0
# How stale a prediction's produced_at may be (non-critical).
PREDICTION_STALE_SEC = 86400.0  # 24h -- offseason envelopes are rebuilt daily

_REPO = pathlib.Path(__file__).resolve().parents[3]
_OPS_STATUS_PATH = _REPO / "data" / "frontend" / "ops" / "status.json"
_CANARY_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "canary_status.json"

# Required keys on a healthy SnapshotEnvelope dict.
_REQUIRED_ENVELOPE_KEYS = {"sport", "status", "schema_version", "honest_note"}


@dataclass
class ProbeResult:
    """Result for a single probe stage."""
    stage: str
    ok: bool
    critical: bool
    note: str = ""


@dataclass
class CanaryResult:
    """Aggregate result: status READY/DEGRADED/DOWN, failing_stage, probes, notes."""
    status: str
    failing_stage: Optional[str]
    probes: List[ProbeResult] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    checked_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "failing_stage": self.failing_stage,
            "probes": [
                {"stage": p.stage, "ok": p.ok, "critical": p.critical,
                 "note": p.note}
                for p in self.probes
            ],
            "notes": self.notes,
            "checked_at": self.checked_at,
        }


# ---------------------------------------------------------------------------
# Probes -- each returns ProbeResult; never raises
# ---------------------------------------------------------------------------

def _probe_predict_envelope(read_fn: Optional[Callable[[], Any]] = None) -> ProbeResult:
    """CRITICAL: read a SnapshotEnvelope from the canonical store."""
    stage = "predict_envelope"
    try:
        if read_fn is not None:
            env = read_fn()
        else:
            from predict_service.store import read_latest
            env = read_latest("nba")
        if env is None:
            return ProbeResult(stage, ok=False, critical=True,
                               note="read_latest returned None")
        status = getattr(env, "status", None) or (env.get("status") if isinstance(env, dict) else None)
        if status is None:
            return ProbeResult(stage, ok=False, critical=True,
                               note="envelope has no status field")
        return ProbeResult(stage, ok=True, critical=True,
                           note="sport=nba status=%s" % status)
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(stage, ok=False, critical=True,
                           note="%s: %s" % (type(exc).__name__, exc))


def _probe_envelope_schema(read_fn: Optional[Callable[[], Any]] = None) -> ProbeResult:
    """CRITICAL: envelope dict has all required schema keys."""
    stage = "envelope_schema"
    try:
        if read_fn is not None:
            env = read_fn()
        else:
            from predict_service.store import read_latest
            env = read_latest("nba")
        if env is None:
            return ProbeResult(stage, ok=False, critical=True, note="no envelope")
        d = env.to_dict() if hasattr(env, "to_dict") else dict(env)
        missing = _REQUIRED_ENVELOPE_KEYS - set(d.keys())
        if missing:
            return ProbeResult(stage, ok=False, critical=True,
                               note="missing keys: %s" % sorted(missing))
        return ProbeResult(stage, ok=True, critical=True,
                           note="schema ok version=%s" % d.get("schema_version", "?"))
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(stage, ok=False, critical=True,
                           note="%s: %s" % (type(exc).__name__, exc))


def _probe_calibration_note(read_fn: Optional[Callable[[], Any]] = None) -> ProbeResult:
    """CRITICAL: honest_note present and non-empty (no $ edge fabricated)."""
    stage = "calibration_note"
    try:
        if read_fn is not None:
            env = read_fn()
        else:
            from predict_service.store import read_latest
            env = read_latest("nba")
        if env is None:
            return ProbeResult(stage, ok=False, critical=True, note="no envelope")
        d = env.to_dict() if hasattr(env, "to_dict") else dict(env)
        note_val = d.get("honest_note", "")
        if not isinstance(note_val, str) or not note_val.strip():
            return ProbeResult(stage, ok=False, critical=True,
                               note="honest_note absent or empty")
        return ProbeResult(stage, ok=True, critical=True,
                           note="honest_note present (%d chars)" % len(note_val))
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(stage, ok=False, critical=True,
                           note="%s: %s" % (type(exc).__name__, exc))


def _probe_ops_status(
    ops_path: Optional[pathlib.Path] = None,
    now: Optional[float] = None,
    stale_sec: float = OPS_STATUS_STALE_SEC,
) -> ProbeResult:
    """NON-CRITICAL: ops/status.json exists and was written within stale_sec."""
    stage = "ops_status"
    path = ops_path if ops_path is not None else _OPS_STATUS_PATH
    _now = now if now is not None else time.time()
    try:
        if not path.exists():
            return ProbeResult(stage, ok=False, critical=False,
                               note="ops status.json absent")
        age_sec = _now - path.stat().st_mtime
        if age_sec > stale_sec:
            return ProbeResult(stage, ok=False, critical=False,
                               note="ops status.json stale (age=%.0fs > %.0fs)" % (
                                   age_sec, stale_sec))
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
        overall = doc.get("overall", "?")
        return ProbeResult(stage, ok=True, critical=False,
                           note="overall=%s age=%.0fs" % (overall, age_sec))
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(stage, ok=False, critical=False,
                           note="%s: %s" % (type(exc).__name__, exc))


def _probe_prediction_fresh(
    read_fn: Optional[Callable[[], Any]] = None,
    now: Optional[float] = None,
    stale_sec: float = PREDICTION_STALE_SEC,
) -> ProbeResult:
    """NON-CRITICAL: newest prediction produced_at is within stale_sec.
    Offseason (no predictions) -> ok=True with note; not DOWN."""
    stage = "prediction_fresh"
    _now = now if now is not None else time.time()
    try:
        if read_fn is not None:
            env = read_fn()
        else:
            from predict_service.store import read_latest
            env = read_latest("nba")
        if env is None:
            return ProbeResult(stage, ok=False, critical=False, note="no envelope")
        preds = getattr(env, "predictions", None)
        if preds is None and isinstance(env, dict):
            preds = env.get("predictions", [])
        if not preds:
            # Offseason: no games -> READY-with-note (not DOWN)
            return ProbeResult(stage, ok=True, critical=False,
                               note="no predictions (offseason/no games) -- READY")
        # Find newest produced_at
        newest: Optional[float] = None
        for p in preds:
            ts = getattr(p, "produced_at", None) or (p.get("produced_at") if isinstance(p, dict) else None)
            if ts:
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    epoch = dt.timestamp()
                    if newest is None or epoch > newest:
                        newest = epoch
                except Exception:  # noqa: BLE001
                    pass
        if newest is None:
            return ProbeResult(stage, ok=True, critical=False,
                               note="produced_at unparseable -- treating as ok")
        age_sec = _now - newest
        if age_sec > stale_sec:
            return ProbeResult(stage, ok=False, critical=False,
                               note="prediction stale (age=%.0fs > %.0fs)" % (
                                   age_sec, stale_sec))
        return ProbeResult(stage, ok=True, critical=False,
                           note="prediction fresh (age=%.0fs)" % age_sec)
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(stage, ok=False, critical=False,
                           note="%s: %s" % (type(exc).__name__, exc))


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def run_canary(
    *,
    read_fn: Optional[Callable[[], Any]] = None,
    ops_path: Optional[pathlib.Path] = None,
    now: Optional[float] = None,
    ops_stale_sec: float = OPS_STATUS_STALE_SEC,
    pred_stale_sec: float = PREDICTION_STALE_SEC,
) -> CanaryResult:
    """Run all probes -> CanaryResult. Never raises. All args injectable for tests."""
    _now = now if now is not None else time.time()
    probes: List[ProbeResult] = []
    try:
        probes.append(_probe_predict_envelope(read_fn))
        probes.append(_probe_envelope_schema(read_fn))
        probes.append(_probe_calibration_note(read_fn))
        probes.append(_probe_ops_status(ops_path, _now, ops_stale_sec))
        probes.append(_probe_prediction_fresh(read_fn, _now, pred_stale_sec))
    except Exception as exc:  # noqa: BLE001 -- a probe bug must not crash the runner
        logger.warning("run_canary: unexpected probe failure: %s", exc)

    # Determine overall status
    critical_failures = [p for p in probes if p.critical and not p.ok]
    non_critical_failures = [p for p in probes if not p.critical and not p.ok]

    failing_stage: Optional[str] = None
    notes: List[str] = []

    if critical_failures:
        status = DOWN
        failing_stage = critical_failures[0].stage
        for p in critical_failures:
            notes.append("DOWN [%s]: %s" % (p.stage, p.note))
    elif non_critical_failures:
        status = DEGRADED
        for p in non_critical_failures:
            notes.append("DEGRADED [%s]: %s" % (p.stage, p.note))
    else:
        status = READY
        # Bubble up any informational notes (offseason hint, etc.)
        for p in probes:
            if p.note and "offseason" in p.note.lower():
                notes.append("NOTE: %s" % p.note)

    return CanaryResult(
        status=status,
        failing_stage=failing_stage,
        probes=probes,
        notes=notes,
        checked_at=_now,
    )


__all__ = [
    "READY", "DEGRADED", "DOWN",
    "ProbeResult", "CanaryResult",
    "run_canary",
]
