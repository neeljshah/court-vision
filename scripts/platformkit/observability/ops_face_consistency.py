"""scripts.platformkit.observability.ops_face_consistency -- single canonical
freshness severity evaluator shared by all three ops faces.

ROOT CAUSE (QA iters 3/6/9 + iters 2/3/6 'doctor=ok while autonomy=down'):
  /api/ops/status, /api/ops/doctor, and /api/ops/autonomy each computed their
  own per-service severity independently.  A CRITICAL service with live=None or
  fresh=None (never-started heartbeat, or port-probed service with no data age)
  scored OK on some faces while DOWN or DEGRADED on others.  Similarly, a row
  with age_sec=560 against a 300s SLA was read as fresh on /api/ops/status but
  stale on /api/ops/doctor -- a stale-never-green violation.

FIX (pure evaluator, no side-effects):
  evaluate_service(row, sla_sec, now) -> severity
    The SINGLE function every ops face must call for per-service severity.  It
    applies the following invariants (ALL evaluated in order, monotone-DOWN):
      1. live is None on a CRITICAL service  -> DEGRADED (never OK on unknown).
      2. live is False                       -> DOWN.
      3. breaker == 'OPEN'                   -> DOWN.
      4. fresh is None on a CRITICAL service -> DEGRADED (never OK on unknown).
      5. fresh == 'down'                     -> DOWN.
      6. fresh == 'stale'                    -> DEGRADED.
      7. age_sec is not None and >= sla_sec  -> DEGRADED ('stale', overrides fresh=None).
      8. age_sec is None on a CRITICAL with fresh=None -> DEGRADED.
      9. Otherwise                           -> OK.

  consistency_matrix(face_results) -> report
    Given {face_name: {service_name: severity}} from all three faces for the
    same poll window, return a report flagging every service where the worst
    face severity != the best face severity (a disagreement).  Reports are
    sorted worst-mismatch-first.  An empty mismatch list means ALL faces agree.

GUARANTEE CONTRACT:
  * Critical live=None or fresh=None  -> DEGRADED, never OK.
  * Non-critical live=None or fresh=None + no age -> DEGRADED (missing = stale).
  * age_sec >= sla_sec                -> DEGRADED, regardless of fresh string.
  * live=False                        -> DOWN.
  * Any two faces with same (row, sla_sec, now) input -> identical severity.
  * consistency_matrix with one face 'ok' and another 'down' -> mismatch flagged.
  * NEVER raises; no $ field; calibration not edge; ASCII only.

PUBLIC API:
  evaluate_service(row, sla_sec, now) -> str  ('ok'|'degraded'|'down')
  consistency_matrix(face_results)    -> dict

INVARIANTS: <=300 LOC; ASCII only; stdlib only; no I/O at import; NEVER raises.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Severity constants -- lowercase to match the rest of the ops stack.
OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

# Rank map: higher = worse.  Used in monotone-DOWN helpers.
_RANK: Dict[str, int] = {OK: 0, DEGRADED: 1, DOWN: 2}
_BY_RANK: Dict[int, str] = {0: OK, 1: DEGRADED, 2: DOWN}

# Default SLA (mirrors ops.liveness.DEFAULT_SLA_SEC and ops_consensus_reconciler).
DEFAULT_SLA_SEC: float = 300.0

HONEST_NOTE = (
    "ops_face_consistency: canonical freshness evaluator. "
    "Critical live=None/fresh=None -> DEGRADED (stale-never-green). "
    "age_sec>=SLA -> DEGRADED. Monotone-DOWN only. "
    "Calibration not edge; no $ field."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _worse(a: str, b: str) -> str:
    """Return whichever severity is worse.  Unknown labels -> DEGRADED."""
    ra = _RANK.get(a, _RANK[DEGRADED])
    rb = _RANK.get(b, _RANK[DEGRADED])
    return _BY_RANK[max(ra, rb)]


def _resolve_age(row: Dict[str, Any], now: Optional[float]) -> Optional[float]:
    """Extract numeric age_sec from the row.  Returns None when unavailable."""
    raw = row.get("age_sec") or row.get("age_seconds")
    if isinstance(raw, (int, float)) and raw >= 0:
        return float(raw)
    # Attempt to derive from timestamp fields when now is given.
    if now is not None:
        for key in ("source_ts", "generated_at", "last_seen"):
            ts = row.get(key)
            if ts is None:
                continue
            try:
                from datetime import datetime, timezone
                ds = str(ts).replace("Z", "+00:00")
                dt = datetime.fromisoformat(ds)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(timezone.utc)
                import time
                now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
                age = max(0.0, (now_dt - dt).total_seconds())
                return age
            except Exception:  # noqa: BLE001
                continue
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_service(
    row: Any,
    sla_sec: float = DEFAULT_SLA_SEC,
    now: Optional[float] = None,
) -> str:
    """Return the canonical severity for one services[] row.  NEVER raises.

    This is the single function all three ops faces must call so they cannot
    disagree for the same service at the same poll instant.

    Rules applied in order (monotone-DOWN; once degraded/down, stays there):
      1. Non-dict input                              -> DEGRADED.
      2. live=False                                  -> DOWN.
      3. breaker='OPEN'                              -> DOWN.
      4. fresh='down'                                -> DOWN.
      5. fresh='stale'                               -> DEGRADED.
      6. age_sec >= sla_sec (resolved from row/now) -> DEGRADED.
      7. fresh=None on critical service              -> DEGRADED.
      8. live=None on critical service               -> DEGRADED.
      9. fresh=None + no resolvable age              -> DEGRADED (missing=stale).
      10. Otherwise                                  -> OK.
    """
    try:
        if not isinstance(row, dict):
            return DEGRADED

        sev = OK
        critical = bool(row.get("critical", False))

        # --- liveness gate (rules 2-3) ---
        live = row.get("live")
        if live is False:
            return DOWN
        if row.get("breaker") == "OPEN":
            return DOWN

        # --- freshness verdict (rules 4-6) ---
        fresh = row.get("fresh")
        if fresh == "down":
            return DOWN
        if fresh == "stale":
            sev = _worse(sev, DEGRADED)

        # --- age-based stale check (rule 6) ---
        age = _resolve_age(row, now)
        if age is not None and age >= sla_sec:
            sev = _worse(sev, DEGRADED)

        # --- unknown / missing on critical (rules 7-9) ---
        if fresh not in ("fresh", "stale", "down"):
            # fresh is None or something unexpected.
            if critical:
                # Critical services must never read OK on unknown fresh.
                sev = _worse(sev, DEGRADED)
            elif age is None:
                # Non-critical: no age and no fresh verdict -> missing = stale.
                sev = _worse(sev, DEGRADED)

        # live=None on critical -> DEGRADED (rule 8).
        if live is None and critical:
            sev = _worse(sev, DEGRADED)

        return sev

    except Exception:  # noqa: BLE001
        return DEGRADED


def consistency_matrix(
    face_results: Any,
    sla_sec: float = DEFAULT_SLA_SEC,
) -> Dict[str, Any]:
    """Flag services where any two ops faces return different severities.

    *face_results* shape:
      {
        "status":   {"svc_a": "ok",      "svc_b": "degraded", ...},
        "doctor":   {"svc_a": "degraded","svc_b": "ok",       ...},
        "autonomy": {"svc_a": "ok",      "svc_b": "ok",       ...},
      }

    Returns:
      {
        "mismatches": [
          {"service": str, "face_verdicts": {face: sev, ...},
           "best": str, "worst": str, "gap": int},
          ...
        ],
        "all_agree": bool,
        "n_services": int,
        "n_mismatches": int,
        "honest_note": str,
        "edge_claimed": False,
      }

    Sorted worst-gap-first.  An empty mismatches list means all faces agree for
    all services visible in at least one face.  NEVER raises.
    """
    try:
        if not isinstance(face_results, dict):
            return _empty_matrix(error="face_results must be a dict")

        # Collect all service names across all faces.
        all_services: List[str] = []
        face_maps: Dict[str, Dict[str, str]] = {}
        for face_name, svc_map in face_results.items():
            if not isinstance(svc_map, dict):
                continue
            face_maps[str(face_name)] = {
                str(k): str(v) for k, v in svc_map.items()
                if isinstance(v, str) and v in (OK, DEGRADED, DOWN)
            }
            for svc in face_maps[str(face_name)]:
                if svc not in all_services:
                    all_services.append(svc)

        mismatches: List[Dict[str, Any]] = []

        for svc in all_services:
            verdicts: Dict[str, str] = {}
            for face_name, svc_map in face_maps.items():
                if svc in svc_map:
                    verdicts[face_name] = svc_map[svc]

            if len(verdicts) < 2:
                # Only one face reported this service -- no comparison possible.
                continue

            sev_vals = list(verdicts.values())
            ranks = [_RANK.get(s, _RANK[DEGRADED]) for s in sev_vals]
            best_rank = min(ranks)
            worst_rank = max(ranks)
            gap = worst_rank - best_rank

            if gap > 0:
                mismatches.append({
                    "service": svc,
                    "face_verdicts": verdicts,
                    "best": _BY_RANK[best_rank],
                    "worst": _BY_RANK[worst_rank],
                    "gap": gap,
                })

        mismatches.sort(key=lambda m: -m["gap"])

        return {
            "mismatches": mismatches,
            "all_agree": len(mismatches) == 0,
            "n_services": len(all_services),
            "n_mismatches": len(mismatches),
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
        }

    except Exception as exc:  # noqa: BLE001
        logger.warning("consistency_matrix failed: %s", exc)
        return _empty_matrix(error="consistency_matrix exception (%s)" % type(exc).__name__)


def _empty_matrix(error: Optional[str] = None) -> Dict[str, Any]:
    """Return a safe empty consistency matrix document."""
    doc: Dict[str, Any] = {
        "mismatches": [],
        "all_agree": False,
        "n_services": 0,
        "n_mismatches": 0,
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
    "evaluate_service",
    "consistency_matrix",
]
