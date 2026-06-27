"""frontend.gate_routes -- the real-money MODE gate state, read-only for the UI.

BE-P1-06. The UI must show "PAPER ONLY" by reading the ACTUAL governance gate
state, not static text -- so that if the gate ever changed the UI would reflect
it. This route reads the vetted, default-DENY gate and surfaces ITS verdict.

  GET /api/gate/status
      {
        "paper_only": true,            # always true until authorize() flips
        "real_money_enabled": false,   # mirror of governance authorize().authorized
        "n_settled_true_close": int,   # from the M4 eligibility metrics
        "threshold": int,              # the pre-registered min settled-N bar
        "eligible": bool,              # M4 decision-only eligibility
        "reasons": [str, ...],         # why real money is denied
      }

ENFORCEMENT NOTE: this is READ-ONLY observability. It NEVER authorizes anything,
NEVER flips a flag, NEVER places a bet. It calls governance.realmoney_gate.
authorize with human_approved=False and no token, so the ONLY answer it can ever
report is the default-DENY one (real_money_enabled=False) unless a human has
already signed an authorization out of band. The honest, conservative default.

HONESTY: no $ / dollar / roi / profit / pnl / stake / bankroll key anywhere; this
is a mode/eligibility readout, not a money figure. Never raises: any gate failure
degrades to the safe DENY sentinel (paper_only=True). edge_claimed always False.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.gate_routes requires fastapi.") from exc

logger = logging.getLogger(__name__)

router = APIRouter()

HONEST_NOTE = (
    "Real-money MODE is default-DENY. This endpoint is read-only observability of "
    "the governance gate; it never authorizes, never flips a flag, never places a "
    "bet. PAPER ONLY until a human signs a valid token out of band. No $ edge."
)


def _safe_deny(reason: str) -> Dict[str, Any]:
    """The conservative DENY sentinel when the gate cannot be evaluated."""
    return {
        "status": "ok",
        "paper_only": True,
        "real_money_enabled": False,
        "eligible": False,
        "n_settled_true_close": None,
        "threshold": None,
        "reasons": [reason],
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    }


def _threshold() -> Any:
    try:
        from governance import policy as _pol  # noqa: PLC0415
        thr = _pol.REALMONEY_THRESHOLDS or {}
        return thr.get("min_settled_n")
    except Exception as exc:  # noqa: BLE001
        logger.debug("gate_routes: threshold read failed: %s", exc)
        return None


def _n_settled_true_close(metrics: Dict[str, Any]) -> Any:
    """settled-N that cleared with a TRUE close = n * true_close_frac (when known)."""
    n = metrics.get("n")
    frac = metrics.get("true_close_frac")
    if isinstance(n, (int, float)) and isinstance(frac, (int, float)):
        return int(round(float(n) * float(frac)))
    return None


@router.get("/api/gate/status")
def gate_status() -> JSONResponse:
    """Real-money mode gate state (default-DENY). Read-only; never raises."""
    try:
        from governance import realmoney_gate as _gate  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 -- no gate -> safe DENY
        logger.warning("gate_routes: gate import failed: %s", exc)
        return JSONResponse(_safe_deny(
            "governance gate unavailable (%s) -- default-DENY" % type(exc).__name__))
    try:
        # human_approved=False + no token => can only ever report default-DENY.
        verdict = _gate.authorize(human_approved=False, token=None)
    except Exception as exc:  # noqa: BLE001 -- a gate failure must stay DENY
        logger.warning("gate_routes: authorize failed: %s", exc)
        return JSONResponse(_safe_deny(
            "gate evaluation failed (%s) -- default-DENY" % type(exc).__name__))

    eligibility = verdict.get("eligibility") or {}
    metrics = eligibility.get("metrics") or {}
    reasons: List[str] = list(verdict.get("reasons") or [])
    authorized = bool(verdict.get("authorized", False))
    body = {
        "status": "ok",
        "paper_only": (not authorized),
        "real_money_enabled": authorized,
        "eligible": bool(eligibility.get("eligible", False)),
        "n_settled_true_close": _n_settled_true_close(metrics),
        "threshold": _threshold(),
        "reasons": reasons,
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    }
    return JSONResponse(body)


__all__ = ["router"]
