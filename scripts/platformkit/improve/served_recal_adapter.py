"""scripts.platformkit.improve.served_recal_adapter -- the DO-NO-HARM closed-loop seam
(FIX C) that lets the pregame producer CONSULT a gate-SHIPPED recal artifact, without
ever destabilizing the currently-honest live producer.

THE GAP THIS CLOSES: the self-improve loop can SHIP a recalibration artifact
(data/cache/improve/artifacts/<sport>/current.json -- already past the 5-gate ratchet +
held-out + auto-rollback), but NOTHING in the serving path ever READS it, so a ship
changes nothing the user sees -- the loop is not closed.

This adapter is the read seam. It is BUILT-but-INACTIVE-by-construction: it is a
GUARDED NO-OP that returns the producer's RAW probabilities UNCHANGED unless ALL of:

  1. ARMED        -- the human-only PIPELINE_ENABLED sentinel is present
                     (improve.pipeline_flag.pipeline_enabled). Absent -> raw passthrough,
                     byte-identical to today. This adapter NEVER creates the sentinel.
  2. SHIPPED      -- a current.json artifact exists for the sport and parses to a finite
                     Platt (a, b) recal map. Absent/torn -> raw passthrough.
  3. HELD-OUT OK  -- at SERVE TIME, the shipped map must NOT regress Brier on the caller's
                     leak-free held-out (raw_prob, outcome) window (auto-rollback-on-
                     regression in spirit): if applying it would worsen held-out Brier, we
                     REJECT it and return RAW (the do-no-harm guarantee). Too-thin a window
                     (< _MIN_HELDOUT) -> RAW (never trust an unvalidated map on serve).

Because conditions 1-3 are ALL required and condition 1 is a human-only file, this module
is INERT in the running system: it is wired NOWHERE in the live producer here (FIX C is
shipped as BUILT-but-inactive-pending-human). A human wire-in calls maybe_apply_shipped()
at the serve boundary; until then the live producer is untouched.

INVARIANTS: additive; reads only (never data/registry/, MEMORY.md; never flips a flag,
never creates the sentinel); pure + injectable; NEVER raises (any failure -> RAW); NO
$/roi/pnl/edge field; calibration not edge. stdlib + numpy + repo-internal; ASCII; <=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_served_recal_adapter.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger("served_recal_adapter")

# Minimum leak-free held-out observations required before we trust a shipped map at serve
# time. Below this the map is NOT applied (RAW passthrough) -- never validate on noise.
_MIN_HELDOUT = 8

# A new map must not WORSEN held-out Brier by more than this slack to be accepted. Strictly
# do-no-harm: a flat or improving map passes; a regressing map is rejected -> RAW.
_REGRESS_SLACK = 1e-9


def _clip01(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-6, 1.0 - 1e-6)


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _apply_platt(raw: np.ndarray, a: float, b: float) -> np.ndarray:
    """P = sigmoid(a*logit(raw) + b), the exact map the recalibrator shipped."""
    z = np.log(_clip01(raw) / (1.0 - _clip01(raw)))
    return _clip01(1.0 / (1.0 + np.exp(-(a * z + b))))


def _load_shipped_platt(sport: str, root: Optional[str],
                        current_fn: Optional[Any]) -> Optional[Tuple[float, float]]:
    """Return the SHIPPED Platt (a, b) for `sport`, or None (absent / torn / non-finite).

    Reads the gate-shipped artifact via artifact_store.current (injectable for tests). The
    payload is the recalibrator's {"family":"platt","a":..,"b":..}. NEVER raises.
    """
    try:
        getter = current_fn
        if getter is None:
            from scripts.platformkit.improve.artifact_store import current as getter
        rec = getter(str(sport).lower(), root)
    except Exception as exc:  # noqa: BLE001 -- no store / torn pointer -> no map
        logger.debug("served_recal_adapter load(%s) failed: %s", sport, exc)
        return None
    if not isinstance(rec, dict):
        return None
    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else rec
    if str(payload.get("family", "")) != "platt":
        return None
    try:
        a, b = float(payload["a"]), float(payload["b"])
    except (TypeError, ValueError, KeyError):
        return None
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    return a, b


def maybe_apply_shipped(sport: str,
                        raw_probs: Sequence[float],
                        *,
                        heldout_probs: Optional[Sequence[float]] = None,
                        heldout_outcomes: Optional[Sequence[float]] = None,
                        root: Optional[str] = None,
                        require_enabled: bool = True,
                        current_fn: Optional[Any] = None,
                        sentinel_fn: Optional[Any] = None,
                        ) -> Dict[str, Any]:
    """Consult the gate-shipped recal artifact for `sport`; apply it ONLY if do-no-harm.

    Returns {probs, applied(bool), status, note} where ``probs`` is the producer-facing
    output -- the recalibrated probs when ALL guards pass, else the RAW input UNCHANGED.

    status is one of:
      "raw_inert"        -- the PIPELINE_ENABLED sentinel is absent (not armed) -> RAW.
      "raw_no_artifact"  -- armed, but no shipped Platt artifact on disk -> RAW.
      "raw_insufficient" -- armed + shipped, but the held-out window is too thin -> RAW.
      "raw_rejected"     -- armed + shipped, but the map REGRESSES held-out Brier -> RAW
                            (the do-no-harm guarantee: a regressing ship is never served).
      "applied"          -- armed + shipped + held-out NOT regressed -> recalibrated probs.

    Leak-free: held-out (probs, outcomes) must be a strictly-past, outcome-settled window
    supplied by the caller; this adapter never derives it from the row being served. NEVER
    raises (any failure -> RAW passthrough). No $ field anywhere.
    """
    raw = _clip01(np.asarray(list(raw_probs), dtype=float))
    base = {"probs": raw.tolist(), "applied": False,
            "note": "calibration, not edge; do-no-harm serve seam"}
    try:
        # GUARD 1 -- armed? (human-only sentinel). Absent -> RAW, byte-identical to today.
        if require_enabled:
            sgetter = sentinel_fn
            if sgetter is None:
                from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
                sgetter = pipeline_enabled
            if not bool(sgetter()):
                base["status"] = "raw_inert"
                return base

        # GUARD 2 -- a shipped Platt artifact on disk?
        ab = _load_shipped_platt(sport, root, current_fn)
        if ab is None:
            base["status"] = "raw_no_artifact"
            return base

        # GUARD 3 -- held-out do-no-harm check AT SERVE TIME (auto-rollback in spirit).
        hp = np.asarray(list(heldout_probs or ()), dtype=float)
        hy = np.asarray(list(heldout_outcomes or ()), dtype=float)
        if hp.size < _MIN_HELDOUT or hp.size != hy.size:
            base["status"] = "raw_insufficient"
            return base
        if set(np.unique(hy).tolist()) - {0.0, 1.0}:
            base["status"] = "raw_insufficient"
            return base
        hp = _clip01(hp)
        recal_ho = _apply_platt(hp, ab[0], ab[1])
        if _brier(recal_ho, hy) > _brier(hp, hy) + _REGRESS_SLACK:
            # The shipped map WORSENS held-out Brier -> reject it, serve RAW (do-no-harm).
            base["status"] = "raw_rejected"
            base["note"] = ("calibration, not edge; shipped recal regressed held-out "
                            "Brier -> rejected at serve (do-no-harm)")
            return base

        # All guards pass: apply the shipped, held-out-validated map.
        out = _apply_platt(raw, ab[0], ab[1])
        return {"probs": out.tolist(), "applied": True, "status": "applied",
                "note": "calibration, not edge; gate-shipped + held-out-validated recal"}
    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> RAW passthrough
        logger.debug("maybe_apply_shipped(%s) failed -> RAW: %s", sport, exc)
        base["status"] = "raw_error"
        return base


__all__ = ["maybe_apply_shipped"]
