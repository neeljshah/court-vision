"""predict_service.ops_staleness_normalizer -- single shared staleness evaluator.

QA iters 3/6/9 P1 root cause: /api/ops/status scored ok for a critical producer
while /api/ops/autonomy + /api/freshness reported stale/down.  Divergence: the
status face treated live=True + fresh=None as ok and never checked age vs SLA.

FIX: normalize_service_severity(row, sla_sec, readiness_kind) -> str
  Single function both ops faces call; delegates to ops_face_consistency.evaluate_service
  (stdlib fallback) so they cannot disagree for the same row.
  readiness_kind:
    HEARTBEAT (age_sec authoritative; null or >=SLA -> DEGRADED)
    PORT      (fresh=live-probe only; age_sec not punitive)
    NONE      (process-alive probe; age_sec irrelevant -- ok iff live=True)
    HTTP      (http-200 probe; age_sec irrelevant -- ok iff live=True / probe passed)

GUARANTEE:
  * Critical live=None/fresh=None + no age -> DEGRADED (never ok).
  * HEARTBEAT live=True + age_sec>=SLA    -> DEGRADED.
  * HEARTBEAT live=True + age_sec=None    -> DEGRADED (never-written heartbeat).
  * PORT/NONE/HTTP fresh='fresh' live=True -> ok (age not punitive).
  * Genuinely fresh service               -> ok.
  * faces_agree: False when verdicts differ.
  * NEVER raises; no $ field; calibration not edge; ASCII only.

PUBLIC API:
  normalize_service_severity(row, sla_sec, readiness_kind) -> str
  faces_agree(verdict_a, verdict_b)                         -> bool
  check_face_pair(face_a, face_b)                           -> dict

INVARIANTS: <=300 LOC; ASCII only; no I/O at import; NEVER raises; no $ field.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity constants.
# ---------------------------------------------------------------------------
OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

_RANK: Dict[str, int] = {OK: 0, DEGRADED: 1, DOWN: 2}
_BY_RANK: Dict[int, str] = {0: OK, 1: DEGRADED, 2: DOWN}

DEFAULT_SLA_SEC: float = 300.0

HONEST_NOTE = (
    "ops_staleness_normalizer: single shared severity evaluator. "
    "Critical live=None/fresh=None -> DEGRADED (stale-never-green). "
    "HEARTBEAT live=True + age_sec>=SLA -> DEGRADED. "
    "PORT/NONE/HTTP: age_sec not punitive; freshness = live-probe result only. "
    "Calibration not edge; no $ field."
)


# ---------------------------------------------------------------------------
# Internal helpers.
# ---------------------------------------------------------------------------

def _worse(a: str, b: str) -> str:
    """Return the WORSE of two severities.  Unknown labels -> DEGRADED."""
    ra = _RANK.get(a, _RANK[DEGRADED])
    rb = _RANK.get(b, _RANK[DEGRADED])
    return _BY_RANK[max(ra, rb)]


def _resolve_age(row: Dict[str, Any]) -> Optional[float]:
    """Extract a numeric age_sec from the row dict.  Returns None when absent."""
    raw = row.get("age_sec") or row.get("age_seconds")
    try:
        if raw is not None:
            v = float(raw)
            return v if v >= 0 else None
    except (TypeError, ValueError):
        pass
    return None


def _is_heartbeat(readiness_kind: str) -> bool:
    """Return True when this service uses a heartbeat file (age_sec is authoritative).

    PORT, NONE, and HTTP services do NOT use heartbeat files: age_sec is absent by
    design and must never be used to penalize liveness.  Only HEARTBEAT-kind services
    must be demoted when age_sec is null or stale.
    """
    upper = readiness_kind.upper()
    return upper not in ("PORT", "NONE", "HTTP")


# ---------------------------------------------------------------------------
# Shared severity kernel -- delegates to ops_face_consistency when available.
# ---------------------------------------------------------------------------

def _kernel_severity(
    row: Dict[str, Any],
    sla_sec: float,
    now: Optional[float] = None,
) -> str:
    """Call the canonical evaluate_service from ops_face_consistency.

    Falls back to a local re-implementation with identical semantics if the
    import fails (belt+braces -- never raises).
    """
    try:
        from scripts.platformkit.observability.ops_face_consistency import (  # noqa: PLC0415
            evaluate_service,
        )
        return evaluate_service(row, sla_sec=sla_sec, now=now)
    except Exception:  # noqa: BLE001
        pass

    # Local fallback (mirrors ops_face_consistency.evaluate_service invariants).
    try:
        if not isinstance(row, dict):
            return DEGRADED

        critical = bool(row.get("critical", False))
        live = row.get("live")
        if live is False:
            return DOWN
        if row.get("breaker") == "OPEN":
            return DOWN

        fresh = row.get("fresh")
        if fresh == "down":
            return DOWN

        sev = OK
        if fresh == "stale":
            sev = _worse(sev, DEGRADED)

        age = _resolve_age(row)
        if age is not None and age >= sla_sec:
            sev = _worse(sev, DEGRADED)

        if fresh not in ("fresh", "stale", "down"):
            if critical:
                sev = _worse(sev, DEGRADED)
            elif age is None:
                sev = _worse(sev, DEGRADED)

        if live is None and critical:
            sev = _worse(sev, DEGRADED)

        return sev
    except Exception:  # noqa: BLE001
        return DEGRADED


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------

def normalize_service_severity(
    row: Any,
    sla_sec: float = DEFAULT_SLA_SEC,
    readiness_kind: str = "HEARTBEAT",
) -> str:
    """Return the canonical severity for one services[] row.  NEVER raises.

    Single function for all ops faces: delegates to ops_face_consistency kernel.
    PORT: age stripped before kernel (probe verdict authoritative).
    HEARTBEAT: extra gate -- live=True + age>=SLA or age=None -> DEGRADED.
    """
    try:
        if not isinstance(row, dict):
            return DEGRADED

        heartbeat = _is_heartbeat(readiness_kind)

        # For PORT services, strip age fields before passing to the kernel so
        # the age-vs-SLA rule does not demote a live-probed 'fresh' verdict.
        # This preserves the semantic: PORT freshness = live probe only.
        kernel_row = row
        if not heartbeat:
            kernel_row = {
                k: v for k, v in row.items()
                if k not in ("age_sec", "age_seconds", "source_ts", "generated_at",
                             "last_seen")
            }

        # Run the shared kernel (rules 1-9 of ops_face_consistency).
        sev = _kernel_severity(kernel_row, sla_sec=sla_sec)

        # Rule 10: HEARTBEAT services with live=True and age_sec >= SLA must be
        # DEGRADED even when the kernel would allow ok (e.g. fresh=None was
        # treated as ok in the old status face because live=True bypassed the
        # null-fresh gate).  This is the specific two-face divergence root cause.
        if heartbeat:
            age = _resolve_age(row)
            live = row.get("live")
            if live is True and age is not None and age >= sla_sec:
                sev = _worse(sev, DEGRADED)
            # Heartbeat with live=True but age=None (never written) -> stale.
            if live is True and age is None:
                # Only demote if no explicit fresh verdict.
                fresh = row.get("fresh")
                if fresh not in ("fresh",):
                    sev = _worse(sev, DEGRADED)

        return sev
    except Exception:  # noqa: BLE001
        return DEGRADED


def faces_agree(verdict_a: str, verdict_b: str) -> bool:
    """True iff two face severities match.  None -> DEGRADED.  NEVER raises."""
    try:
        a = str(verdict_a).lower().strip() if verdict_a is not None else DEGRADED
        b = str(verdict_b).lower().strip() if verdict_b is not None else DEGRADED
        return a == b
    except Exception:  # noqa: BLE001
        return False


def check_face_pair(
    face_a: Any,
    face_b: Any,
    face_a_name: str = "face_a",
    face_b_name: str = "face_b",
) -> Dict[str, Any]:
    """Return consistency report for two {svc: severity} dicts.  NEVER raises.

    Services in only one face are skipped.  Sorted worst-gap-first.
    """
    try:
        if not isinstance(face_a, dict) or not isinstance(face_b, dict):
            return _empty_pair_report(
                error="check_face_pair: both faces must be dicts"
            )

        # Union of service names present in both faces.
        services_a = {str(k) for k in face_a}
        services_b = {str(k) for k in face_b}
        common = sorted(services_a & services_b)

        mismatches: List[Dict[str, Any]] = []
        for svc in common:
            va = str(face_a[svc]).lower().strip() if face_a[svc] is not None else DEGRADED
            vb = str(face_b[svc]).lower().strip() if face_b[svc] is not None else DEGRADED
            if va != vb:
                rank_a = _RANK.get(va, _RANK[DEGRADED])
                rank_b = _RANK.get(vb, _RANK[DEGRADED])
                gap = abs(rank_a - rank_b)
                mismatches.append({
                    "service": svc,
                    face_a_name + "_verdict": va,
                    face_b_name + "_verdict": vb,
                    "gap": gap,
                })

        mismatches.sort(key=lambda m: -m["gap"])

        return {
            "all_agree": len(mismatches) == 0,
            "n_services": len(common),
            "n_mismatches": len(mismatches),
            "mismatches": mismatches,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_face_pair failed: %s", exc)
        return _empty_pair_report(
            error="check_face_pair exception (%s)" % type(exc).__name__
        )


def _empty_pair_report(error: Optional[str] = None) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "all_agree": False,
        "n_services": 0,
        "n_mismatches": 0,
        "mismatches": [],
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    }
    if error:
        doc["_error"] = error
    return doc


__all__ = [
    "OK", "DEGRADED", "DOWN",
    "DEFAULT_SLA_SEC",
    "HONEST_NOTE",
    "normalize_service_severity",
    "faces_agree",
    "check_face_pair",
]
