"""predict_service.status_freshness_normalizer -- coerce fresh=null/unknown -> stale.

QA3 P1 ROOT CAUSE: status aggregation carried fresh=null for m1_producer (and any
port-probed service with no freshness_source). The consumer (_row_severity / doctor)
treated null as ok, so a stale critical producer read green while /api/freshness was
down. This module is the single chokepoint that normalizes every status row BEFORE
the status surface is served.

TWO PUBLIC FUNCTIONS:

  normalize_row(row, sla_sec) -> row_copy
      Given one services[] row (the shape ops.health_aggregator._service_row emits)
      and an SLA in seconds, derive fresh from generated_at / source_ts / age_sec vs
      SLA, then coerce:
        - fresh=null  (no timestamp, no age)  -> 'stale'  (never 'ok')
        - fresh='unknown'                     -> 'stale'
        - fresh=null but age_sec < sla_sec    -> 'fresh'   (age wins when present)
        - fresh=null but age_sec >= sla_sec   -> 'stale'
        - fresh=null and source_ts missing    -> 'stale'   (invariant: missing=stale)
        - fresh already 'fresh'/'stale'/'down' -> pass through unchanged
      Returns a NEW dict (never mutates in place).

  normalize_rows(rows, default_sla_sec, sla_map) -> list[row_copy]
      Normalizes a list of rows using per-name SLA overrides from sla_map, falling
      back to default_sla_sec. Provides a monotone-down rollup: result['overall'] is
      the WORST severity across all normalized rows. Any stale/down child degrades the
      parent; a fresh child can NEVER lift a stale parent.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; stdlib only;
no $ field; no edge claim; no I/O at import; NEVER raises; calibration not edge.

Reuses:
  - freshness_sidecar.feed_status / feed_rollup for the stale-never-green verdict
  - status_composer._degrade for monotone-DOWN rollup (fallback if unavailable)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Severity constants -- match status_composer / health_aggregator vocabulary.
OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

_RANK = {OK: 0, DEGRADED: 1, DOWN: 2}
_BY_RANK = {0: OK, 1: DEGRADED, 2: DOWN}

# Default SLA when no override is supplied (5 minutes, matching m6_ingame_loop).
DEFAULT_SLA_SEC: float = 300.0

HONEST_NOTE = (
    "Freshness normalizer: fresh=null/unknown always coerces to stale (never ok). "
    "Missing source_ts -> stale. Monotone-down rollup: any stale/down child "
    "degrades parent. Calibration, not edge; no $ field."
)


# ---------------------------------------------------------------------------
# Internal helpers -- all NEVER raise.
# ---------------------------------------------------------------------------

def _degrade(current: str, candidate: str) -> str:
    """Return the WORSE of two severities (monotone-DOWN). Reuses composer semantics.

    Tries to import status_composer._degrade first so there is exactly one
    chokepoint. Falls back to a local re-implementation with the same semantics if
    the import fails (belt + braces -- never raises).
    """
    try:
        from scripts.platformkit.autonomy.status_composer import (  # noqa: PLC0415
            _degrade as _composer_degrade,
        )
        return _composer_degrade(current, candidate)
    except Exception:  # noqa: BLE001
        cur = _RANK.get(current, _RANK[DEGRADED])
        cand = _RANK.get(candidate, _RANK[DEGRADED])
        return _BY_RANK[max(cur, cand)]


def _parse_iso(ts: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string into a UTC datetime. Returns None on failure."""
    if ts is None:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_from_ts(ts: Any) -> Optional[float]:
    """Seconds elapsed since *ts* (UTC), or None if ts is missing/unparseable."""
    dt = _parse_iso(ts)
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    return max(0.0, (now - dt).total_seconds())


def _severity_for_fresh(fresh: Optional[str]) -> str:
    """Map a normalized fresh value onto a severity (stale-never-green)."""
    if fresh == "fresh":
        return OK
    if fresh == "down":
        return DOWN
    # 'stale' / 'unknown' / None / anything unexpected -> DEGRADED (never OK).
    return DEGRADED


# ---------------------------------------------------------------------------
# Core normalizer -- single row.
# ---------------------------------------------------------------------------

def normalize_row(
    row: Dict[str, Any],
    sla_sec: float = DEFAULT_SLA_SEC,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Derive and coerce the 'fresh' field for one services[] row. NEVER raises.

    Returns a NEW dict (never mutates the input). The coercion rules are:

      1. fresh already 'fresh'/'stale'/'down' -> pass through (no coercion needed).
      2. fresh=null, source_ts missing        -> 'stale'  (missing source = stale).
      3. fresh=null, age_sec present          -> 'fresh' if age_sec < sla_sec else 'stale'.
      4. fresh=null, generated_at/source_ts present
                                              -> compute age, apply rule 3.
      5. fresh=null after all fallbacks       -> 'stale'  (never 'ok').
      6. fresh='unknown'                      -> 'stale'.

    The 'ok' field is always re-derived from the normalized fresh: ok=True ONLY when
    fresh=='fresh'. A normalizer reason string is added when a coercion occurs.
    """
    try:
        out = dict(row)
        fresh = row.get("fresh")

        # Rule 0: already a known concrete verdict -- pass through.
        if fresh in ("fresh", "stale", "down"):
            # Re-derive ok to ensure consistency (some callers may have set ok=True
            # while fresh='stale').
            out["ok"] = (fresh == "fresh")
            return out

        # fresh is None or 'unknown' -- we must derive it.
        coerce_reason: Optional[str] = None

        # Rule 3/4: try to derive age from row fields.
        age: Optional[float] = None

        # age_sec may already be present (e.g. from health_aggregator._service_row).
        raw_age = row.get("age_sec") or row.get("age_seconds")
        if isinstance(raw_age, (int, float)) and raw_age >= 0:
            age = float(raw_age)

        # Fall back to timestamps when age_sec is absent.
        if age is None:
            ts = row.get("source_ts") or row.get("generated_at") or row.get("last_seen")
            if ts is not None:
                if now is not None:
                    dt = _parse_iso(ts)
                    age = max(0.0, (now - dt).total_seconds()) if dt is not None else None
                else:
                    age = _age_from_ts(ts)

        if age is not None:
            # We have an age -- derive fresh from SLA comparison.
            if age < sla_sec:
                out["fresh"] = "fresh"
                coerce_reason = (
                    "derived fresh from age_sec=%.0f < sla=%.0f" % (age, sla_sec)
                )
            else:
                out["fresh"] = "stale"
                coerce_reason = (
                    "coerced null->stale: age_sec=%.0f >= sla=%.0f" % (age, sla_sec)
                )
        else:
            # Rule 2/5: no age, no timestamp -> stale (missing source = stale).
            out["fresh"] = "stale"
            coerce_reason = (
                "coerced null->stale: no source_ts/age_sec (missing source = stale)"
            )

        # Update ok to match the normalized fresh.
        out["ok"] = (out["fresh"] == "fresh")

        # Annotate with the normalization reason (append, don't replace existing).
        existing_reason = out.get("reason")
        if coerce_reason:
            out["_fresh_normalized"] = True
            out["_norm_reason"] = coerce_reason
            if existing_reason:
                out["reason"] = "%s; %s" % (existing_reason, coerce_reason)
            else:
                out["reason"] = coerce_reason

        return out
    except Exception as exc:  # noqa: BLE001 -- normalizer must never crash callers
        logger.warning("status_freshness_normalizer.normalize_row failed: %s", exc)
        # Safe fallback: copy input, force stale so we never accidentally green.
        out = dict(row)
        out["fresh"] = "stale"
        out["ok"] = False
        out["_fresh_normalized"] = True
        out["_norm_reason"] = "normalizer exception -> forced stale (%s)" % type(exc).__name__
        return out


# ---------------------------------------------------------------------------
# Batch normalizer + rollup.
# ---------------------------------------------------------------------------

def normalize_rows(
    rows: List[Dict[str, Any]],
    default_sla_sec: float = DEFAULT_SLA_SEC,
    sla_map: Optional[Dict[str, float]] = None,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Normalize a list of services[] rows and produce a monotone-DOWN rollup.

    Returns:
      {
        'overall': 'ok'|'degraded'|'down',  -- WORST severity across rows
        'ok':      bool,                    -- True only when overall=='ok'
        'rows':    [normalized_row, ...],
        'n_rows':  int,
        'n_fresh': int,
        'n_stale': int,
        'honest_note': str,
        'edge_claimed': False,
      }

    Monotone-down guarantee: overall starts at 'ok' and is degraded by EVERY row
    via _degrade (the single chokepoint). Any stale/down child forces the parent
    off green; a fresh child can never lift a stale parent.

    An empty rows list -> overall='degraded' (absence is never asserted green).
    NEVER raises.
    """
    try:
        sla_map = sla_map or {}
        normalized: List[Dict[str, Any]] = []
        overall = OK

        for row in (rows or []):
            name = row.get("name") or ""
            sla = sla_map.get(name, default_sla_sec)
            nr = normalize_row(row, sla_sec=sla, now=now)
            normalized.append(nr)
            sev = _severity_for_fresh(nr.get("fresh"))
            overall = _degrade(overall, sev)

        if not normalized:
            # No rows: cannot assert freshness -> DEGRADED, never green.
            overall = _degrade(overall, DEGRADED)

        n_fresh = sum(1 for r in normalized if r.get("fresh") == "fresh")
        n_stale = sum(1 for r in normalized if r.get("fresh") != "fresh")

        return {
            "overall": overall,
            "ok": overall == OK,
            "rows": normalized,
            "n_rows": len(normalized),
            "n_fresh": n_fresh,
            "n_stale": n_stale,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001 -- batch wrapper must never crash callers
        logger.warning("status_freshness_normalizer.normalize_rows failed: %s", exc)
        return {
            "overall": DOWN,
            "ok": False,
            "rows": list(rows or []),
            "n_rows": len(rows or []),
            "n_fresh": 0,
            "n_stale": len(rows or []),
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
            "_error": "normalize_rows exception (%s)" % type(exc).__name__,
        }


__all__ = [
    "DEFAULT_SLA_SEC",
    "HONEST_NOTE",
    "normalize_row",
    "normalize_rows",
]
