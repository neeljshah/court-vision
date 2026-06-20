"""predict_service.freshness_align -- /api/produce/status + /api/freshness aligner.

BE-R5-3. Routes BOTH produce_status rows and freshness_sidecar rows through
status_freshness_normalizer and returns the WORST-OF severity (monotone-DOWN) so
the two ops faces cannot give opposite stale/fresh verdicts for the same stem.

  align_stem(stem, produce_row, freshness_row, sla_sec) -> dict
      produce fresh + freshness stale -> aligned stale; fresh=null+age>=sla ->
      stale; both fresh -> ok; either absent -> unavailable (never green).

  align_stems(stems, produce_rows, freshness_rows, sla_sec, sla_map) -> dict
      Batch monotone-DOWN rollup across stems.

  coerce_produce_row(row)   -- adapt produce_status shape for normalize_row.
  coerce_freshness_row(row) -- adapt freshness_sidecar shape for normalize_row.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII; no I/O at
import; NEVER raises; stdlib only; no $ field; calibration not edge.
Reuses: status_freshness_normalizer.normalize_row + DEFAULT_SLA_SEC.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from predict_service.status_freshness_normalizer import (
    DEFAULT_SLA_SEC,
    HONEST_NOTE,
    normalize_row,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity vocabulary and monotone-DOWN helper.
# ---------------------------------------------------------------------------
_OK = "ok"
_DEGRADED = "degraded"
_DOWN = "down"
_RANK = {_OK: 0, _DEGRADED: 1, _DOWN: 2}
_BY_RANK = {0: _OK, 1: _DEGRADED, 2: _DOWN}


def _degrade(current: str, candidate: str) -> str:
    """Return the WORSE of two severity strings (monotone-DOWN). NEVER raises."""
    try:
        cur = _RANK.get(current, 1)
        cand = _RANK.get(candidate, 1)
        return _BY_RANK[max(cur, cand)]
    except Exception:  # noqa: BLE001
        return _DEGRADED


def _fresh_to_severity(fresh: Optional[str]) -> str:
    """Map a normalized 'fresh' value onto a composer severity."""
    if fresh == "fresh":
        return _OK
    if fresh == "down":
        return _DOWN
    return _DEGRADED  # stale / unknown / None -> never OK


# ---------------------------------------------------------------------------
# Row coercers -- adapt each endpoint's shape into normalize_row's key space.
# ---------------------------------------------------------------------------

def coerce_produce_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a produce_status row into normalize_row's key space. NEVER raises.

    ok=True->fresh='fresh'; ok=False+unavailable->fresh='down';
    ok=False->fresh='stale'; ok=None->fresh=None (let normalizer derive from age).
    'age_seconds' aliased to 'age_sec'; 'name' set from 'sport'.
    """
    try:
        out = dict(row)
        # Rename age field for the normalizer.
        if "age_sec" not in out:
            age = row.get("age_seconds")
            if isinstance(age, (int, float)) and age >= 0:
                out["age_sec"] = float(age)
        # Derive name from sport for sla_map.
        if "name" not in out:
            out["name"] = str(row.get("sport") or "")
        # Derive fresh from the produce row's own ok/status.
        ok_val = row.get("ok")
        status_val = str(row.get("status") or "")
        if ok_val is True:
            out["fresh"] = "fresh"
        elif ok_val is False:
            if status_val in ("unavailable", "missing"):
                out["fresh"] = "down"
            else:
                out["fresh"] = "stale"
        else:
            # ok missing/None: let normalize_row re-derive from timestamp.
            out["fresh"] = None
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("freshness_align.coerce_produce_row failed: %s", exc)
        row_copy = dict(row) if row else {}
        row_copy["fresh"] = "stale"
        row_copy["_coerce_error"] = type(exc).__name__
        return row_copy


def coerce_freshness_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a freshness_sidecar row into normalize_row's key space. NEVER raises.

    fresh=True->'fresh'; fresh=False+missing->'down'; fresh=False->'stale'.
    fresh=None: derives from status field or passes None for normalizer.
    'age_seconds' aliased to 'age_sec'; 'name' set from 'sport'.
    """
    try:
        out = dict(row)
        if "name" not in out:
            out["name"] = str(row.get("sport") or "")
        # Rename age field.
        if "age_sec" not in out:
            age = row.get("age_seconds")
            if isinstance(age, (int, float)) and age >= 0:
                out["age_sec"] = float(age)
        # Normalise fresh to string or None.
        fresh_raw = row.get("fresh")
        if fresh_raw is True:
            out["fresh"] = "fresh"
        elif fresh_raw is False:
            status_val = str(row.get("status") or "")
            out["fresh"] = "down" if status_val == "missing" else "stale"
        elif fresh_raw is None or fresh_raw == "":
            # Derive from status field when fresh is absent.
            status_val = str(row.get("status") or "")
            if status_val == "fresh":
                out["fresh"] = "fresh"
            elif status_val in ("missing",):
                out["fresh"] = "down"
            else:
                out["fresh"] = None  # let normalize_row derive from timestamp
        # else: string fresh value passes through unchanged
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("freshness_align.coerce_freshness_row failed: %s", exc)
        row_copy = dict(row) if row else {}
        row_copy["fresh"] = "stale"
        row_copy["_coerce_error"] = type(exc).__name__
        return row_copy


# ---------------------------------------------------------------------------
# Single-stem aligner.
# ---------------------------------------------------------------------------

def align_stem(
    stem: str,
    produce_row: Optional[Dict[str, Any]],
    freshness_row: Optional[Dict[str, Any]],
    sla_sec: float = DEFAULT_SLA_SEC,
) -> Dict[str, Any]:
    """Worst-of aligned verdict for one stem. NEVER raises.

    Normalizes both rows and returns WORSE severity (monotone-DOWN).
    A missing row -> 'stale' (unavailable is never green).
    Returns: stem, aligned_fresh, aligned_ok, produce_fresh, freshness_fresh,
    severity, honest_note, edge_claimed=False.
    """
    try:
        stem = str(stem) if stem is not None else ""

        # Normalize produce row. A None/missing row coerces to an unavailable stale.
        if produce_row is not None:
            p_coerced = coerce_produce_row(produce_row)
        else:
            p_coerced = {"name": stem, "fresh": "stale",
                         "reason": "produce row absent (unavailable)"}
        p_norm = normalize_row(p_coerced, sla_sec=sla_sec)
        p_fresh = p_norm.get("fresh", "stale")

        # Normalize freshness sidecar row.
        if freshness_row is not None:
            f_coerced = coerce_freshness_row(freshness_row)
        else:
            f_coerced = {"name": stem, "fresh": "stale",
                         "reason": "freshness row absent (unavailable)"}
        f_norm = normalize_row(f_coerced, sla_sec=sla_sec)
        f_fresh = f_norm.get("fresh", "stale")

        # Worst-of (monotone-DOWN): stale beats fresh; down beats stale.
        sev_p = _fresh_to_severity(p_fresh)
        sev_f = _fresh_to_severity(f_fresh)
        worst_sev = _degrade(sev_p, sev_f)

        # Map severity back to a fresh string.
        if worst_sev == _OK:
            aligned_fresh = "fresh"
        elif worst_sev == _DOWN:
            aligned_fresh = "down"
        else:
            aligned_fresh = "stale"

        return {
            "stem": stem,
            "aligned_fresh": aligned_fresh,
            "aligned_ok": aligned_fresh == "fresh",
            "produce_fresh": p_fresh,
            "freshness_fresh": f_fresh,
            "severity": worst_sev,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001 -- aligner must never crash callers
        logger.warning("freshness_align.align_stem(%s) failed: %s", stem, exc)
        return {
            "stem": str(stem) if stem is not None else "",
            "aligned_fresh": "stale",
            "aligned_ok": False,
            "produce_fresh": "stale",
            "freshness_fresh": "stale",
            "severity": _DEGRADED,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
            "_error": "align_stem exception (%s)" % type(exc).__name__,
        }


# ---------------------------------------------------------------------------
# Batch aligner.
# ---------------------------------------------------------------------------

def align_stems(
    stems: List[str],
    produce_rows: Optional[Dict[str, Dict[str, Any]]] = None,
    freshness_rows: Optional[Dict[str, Dict[str, Any]]] = None,
    sla_sec: float = DEFAULT_SLA_SEC,
    sla_map: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Batch monotone-DOWN rollup across stems. NEVER raises.

    Returns: overall, ok, stems[], n_stems, n_fresh, n_stale, honest_note,
    edge_claimed=False. Empty stems -> overall='degraded' (never green).
    """
    try:
        produce_rows = produce_rows or {}
        freshness_rows = freshness_rows or {}
        sla_map = sla_map or {}
        entries: List[Dict[str, Any]] = []
        overall = _OK

        for stem in (stems or []):
            stem_sla = sla_map.get(stem, sla_sec)
            entry = align_stem(
                stem=stem,
                produce_row=produce_rows.get(stem),
                freshness_row=freshness_rows.get(stem),
                sla_sec=stem_sla,
            )
            entries.append(entry)
            overall = _degrade(overall, entry.get("severity", _DEGRADED))

        if not entries:
            overall = _degrade(overall, _DEGRADED)

        n_fresh = sum(1 for e in entries if e.get("aligned_ok"))
        n_stale = len(entries) - n_fresh

        return {
            "overall": overall,
            "ok": overall == _OK,
            "stems": entries,
            "n_stems": len(entries),
            "n_fresh": n_fresh,
            "n_stale": n_stale,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("freshness_align.align_stems failed: %s", exc)
        return {
            "overall": _DOWN,
            "ok": False,
            "stems": [],
            "n_stems": 0,
            "n_fresh": 0,
            "n_stale": len(stems) if stems else 0,
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
            "_error": "align_stems exception (%s)" % type(exc).__name__,
        }


__all__ = [
    "DEFAULT_SLA_SEC",
    "align_stem",
    "align_stems",
    "coerce_freshness_row",
    "coerce_produce_row",
]
