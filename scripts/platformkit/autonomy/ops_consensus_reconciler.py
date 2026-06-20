"""scripts.platformkit.autonomy.ops_consensus_reconciler -- single staleness-verdict
reconciler for /api/ops/doctor, /api/ops/autonomy, and /api/freshness.

ROOT CAUSE (QA iters 3/6/9/10 P1/P2): the three ops surfaces can disagree in the
same poll window because each computed its own severity independently.  The specific
gap: ops.health_aggregator._row_severity treats fresh=null as 'ok', so m1_producer
with fresh=null age_sec>=SLA reads GREEN on /api/ops/doctor while /api/ops/autonomy
reads DEGRADED and /api/freshness reads DOWN.

FIX: this module is the SINGLE chokepoint.  Every services[] row -- regardless of
which surface produced it -- is normalised through evaluate_row() which coerces
fresh=null/unknown -> 'stale' (mirrors status_freshness_normalizer semantics, re-
implemented here to avoid a cross-boundary predict_service import).  A single
monotone-DOWN consensus severity is emitted per service; the three views are given
the same input -> they MUST produce the same per-service verdict.

GUARANTEE CONTRACT:
  * fresh=null, age_sec >= SLA_sec  -> consensus 'stale' -> severity DEGRADED.
  * fresh=null, age_sec <  SLA_sec  -> consensus 'fresh' -> severity OK.
  * fresh=null, no age / no ts      -> consensus 'stale' -> severity DEGRADED.
  * fresh child can NEVER lift a stale parent  (monotone-down rollup).
  * Two views given identical input rows  -> identical per-service verdict.
  * Never raises; no $ field; calibration not edge.

PUBLIC API:
  evaluate_row(row, sla_sec)   -> severity ('ok'|'degraded'|'down') for one row.
  reconcile(rows, sla_map, default_sla_sec) -> consensus doc with per-service verdicts.

INVARIANTS: <=300 LOC; ASCII only; stdlib only; no I/O at import; NEVER raises;
build only under scripts/platformkit/; never imports predict_service.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

_RANK: Dict[str, int] = {OK: 0, DEGRADED: 1, DOWN: 2}
_BY_RANK: Dict[int, str] = {0: OK, 1: DEGRADED, 2: DOWN}

# Default SLA when no per-service override is provided (5 min, mirrors freshness_guard).
DEFAULT_SLA_SEC: float = 300.0

HONEST_NOTE = (
    "ops_consensus_reconciler: fresh=null/unknown -> stale (never ok). "
    "Monotone-down: any stale/down child degrades the parent verdict; "
    "a fresh child can never lift a stale parent. "
    "Calibration not edge; no $ field."
)


# ---------------------------------------------------------------------------
# Internal helpers -- all NEVER raise.
# ---------------------------------------------------------------------------

def _degrade(current: str, candidate: str) -> str:
    """Return the WORSE of two severities.  Monotone-DOWN -- never upgrades.

    Unknown labels are treated as DEGRADED (conservative, never green).
    """
    cur = _RANK.get(current, _RANK[DEGRADED])
    cand = _RANK.get(candidate, _RANK[DEGRADED])
    return _BY_RANK[max(cur, cand)]


def _coerce_fresh(row: Dict[str, Any], sla_sec: float) -> str:
    """Derive a concrete fresh value from a services[] row.  NEVER raises.

    Coercion rules (mirrors status_freshness_normalizer, no cross-boundary import):
      1. fresh already 'fresh'/'stale'/'down'  -> pass through unchanged.
      2. fresh='unknown'/None, age_sec present:
           age_sec <  sla_sec  -> 'fresh'
           age_sec >= sla_sec  -> 'stale'
      3. fresh=None/unknown, no age_sec, timestamps:
           compute age from source_ts/generated_at/last_seen, apply rule 2.
      4. fresh=None/unknown, no age, no timestamps -> 'stale' (missing = stale).
      5. fresh='unknown'                           -> 'stale'.
    """
    fresh = row.get("fresh")

    # Rule 1: concrete known verdict -- pass through.
    if fresh in ("fresh", "stale", "down"):
        return str(fresh)

    # Rule 5: 'unknown' is never a concrete ok -- always stale (regardless of age).
    if fresh == "unknown":
        return "stale"

    # fresh is None -- must derive from age/timestamp.
    age: Optional[float] = None

    raw_age = row.get("age_sec") or row.get("age_seconds")
    if isinstance(raw_age, (int, float)) and raw_age >= 0:
        age = float(raw_age)

    # Fall back to timestamp fields when age_sec is absent.
    if age is None:
        ts = row.get("source_ts") or row.get("generated_at") or row.get("last_seen")
        if ts is not None:
            try:
                from datetime import datetime, timezone
                dt_str = str(ts).replace("Z", "+00:00")
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(timezone.utc)
                now = datetime.now(timezone.utc)
                age = max(0.0, (now - dt).total_seconds())
            except Exception:  # noqa: BLE001
                age = None

    if age is not None:
        return "fresh" if age < sla_sec else "stale"

    # Rule 4/5: no age, no timestamp, or 'unknown' -- stale (missing = stale).
    return "stale"


def _fresh_to_severity(fresh: str) -> str:
    """Map a normalised fresh value to a severity label."""
    if fresh == "fresh":
        return OK
    if fresh == "down":
        return DOWN
    # 'stale' / anything unexpected -> DEGRADED (never OK).
    return DEGRADED


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_row(
    row: Dict[str, Any],
    sla_sec: float = DEFAULT_SLA_SEC,
) -> str:
    """Return the consensus severity for one services[] row.  NEVER raises.

    This is the single chokepoint: it normalises fresh=null/unknown, derives
    age-based freshness when available, and returns 'ok'|'degraded'|'down'.
    Every ops surface (doctor, autonomy, freshness) must pipe rows through
    here so they cannot disagree on the same input.
    """
    try:
        fresh = _coerce_fresh(row, sla_sec)
        base_sev = _fresh_to_severity(fresh)

        # Also honour the liveness signal from the row itself.
        if row.get("live") is False:
            base_sev = _degrade(base_sev, DOWN)
        if row.get("breaker") == "OPEN":
            base_sev = _degrade(base_sev, DOWN)

        # Carry forward any pre-existing severity from the row (monotone-down only).
        existing = row.get("severity") or row.get("status") or ""
        if existing in _RANK:
            base_sev = _degrade(base_sev, existing)

        return base_sev
    except Exception:  # noqa: BLE001 -- must never crash callers
        return DEGRADED


def reconcile(
    rows: List[Dict[str, Any]],
    sla_map: Optional[Dict[str, float]] = None,
    default_sla_sec: float = DEFAULT_SLA_SEC,
) -> Dict[str, Any]:
    """Reconcile a list of services[] rows into one consensus document.  NEVER raises.

    Each row is evaluated through evaluate_row() (fresh=null -> stale coercion,
    monotone-down).  The returned document exposes:

      consensus_services  -- list of per-row dicts with 'name', 'consensus_severity',
                             'coerced_fresh', 'input_fresh', 'sla_sec'.
      overall             -- WORST consensus_severity across all rows.
      n_ok / n_degraded / n_down -- counts for quick scanning.
      edge_claimed        -- always False.
      honest_note         -- invariant disclaimer.

    An empty input list -> overall='degraded' (absence is never asserted green).

    Usage contract: feed the SAME rows through this function from every view
    (/api/ops/doctor, /api/ops/autonomy, /api/freshness) to guarantee they agree.
    """
    try:
        sla_map = sla_map or {}
        consensus_rows: List[Dict[str, Any]] = []
        overall = OK

        for row in (rows or []):
            if not isinstance(row, dict):
                # Non-dict rows are DEGRADED (unknown = not-green).
                overall = _degrade(overall, DEGRADED)
                consensus_rows.append({
                    "name": None,
                    "consensus_severity": DEGRADED,
                    "coerced_fresh": "stale",
                    "input_fresh": None,
                    "sla_sec": default_sla_sec,
                    "reason": "non-dict row treated as stale",
                })
                continue

            name = row.get("name") or ""
            sla = sla_map.get(name, default_sla_sec) if name else default_sla_sec
            coerced = _coerce_fresh(row, sla)
            sev = evaluate_row(row, sla_sec=sla)
            overall = _degrade(overall, sev)

            consensus_rows.append({
                "name": name,
                "consensus_severity": sev,
                "coerced_fresh": coerced,
                "input_fresh": row.get("fresh"),
                "sla_sec": sla,
                "age_sec": row.get("age_sec"),
                "critical": row.get("critical"),
            })

        if not consensus_rows:
            overall = _degrade(overall, DEGRADED)

        n_ok = sum(1 for r in consensus_rows if r.get("consensus_severity") == OK)
        n_deg = sum(1 for r in consensus_rows if r.get("consensus_severity") == DEGRADED)
        n_down = sum(1 for r in consensus_rows if r.get("consensus_severity") == DOWN)

        return {
            "overall": overall,
            "ok": overall == OK,
            "consensus_services": consensus_rows,
            "n_rows": len(consensus_rows),
            "n_ok": n_ok,
            "n_degraded": n_deg,
            "n_down": n_down,
            "edge_claimed": False,
            "honest_note": HONEST_NOTE,
        }
    except Exception as exc:  # noqa: BLE001 -- batch wrapper must never crash callers
        logger.warning("ops_consensus_reconciler.reconcile failed: %s", exc)
        return {
            "overall": DOWN,
            "ok": False,
            "consensus_services": [],
            "n_rows": 0,
            "n_ok": 0,
            "n_degraded": 0,
            "n_down": 0,
            "edge_claimed": False,
            "honest_note": HONEST_NOTE,
            "_error": "reconcile exception (%s)" % type(exc).__name__,
        }


__all__ = [
    "OK", "DEGRADED", "DOWN",
    "DEFAULT_SLA_SEC",
    "HONEST_NOTE",
    "evaluate_row",
    "reconcile",
]
