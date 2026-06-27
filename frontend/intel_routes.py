"""frontend.intel_routes -- the NUMBER-FREE intelligence (scouting) face.

WAVE 4. GET /api/intel/{query} is the gateway's intelligence face: a person-free,
NUMBER-FREE descriptive scouting query over the Obsidian brain graph. It returns
UNDERSTANDING + provenance chips ONLY -- never a probability, odds, ROI, edge,
Kelly fraction, or any bettable number. Retrieval is read-only over the vetted
scripts.platformkit.brain_query.brain_query (no new retrieval math here).

  GET /api/intel/{query}[?sport=&kind=&top_k=]
      -> {"status", "query", "hits": [{sport, kind, title, provenance,
          stat_signature, excerpt, ...}], "count", honesty rails}

A defensive double-guard enforces the no-number contract at serve time: each hit
is filtered through brain_query.is_number_free AND a structured number-key scrub,
so a number can never leak even if an upstream note drifts. A missing/empty brain
yields an honest empty hit list (status='ok', count=0), never a fabrication.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no number
in a hit; no secrets; reuse brain_query verbatim (never reimplement retrieval).
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Depends, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.intel_routes requires fastapi.") from exc

from frontend.rate_limit import get_default_limiter, rate_limit_dependency
from predict_service.honest_route import honest_route

router = APIRouter()

_guard = rate_limit_dependency(get_default_limiter())

_INTEL_HONEST_NOTE = (
    "Descriptive, person-free scouting from the brain graph. Returns UNDERSTANDING "
    "+ provenance chips ONLY -- never a probability, odds, edge, Kelly, or any "
    "bettable number. Wiring into a model is human-gated. No $ edge."
)

# Forbidden numeric / edge keys that must NEVER appear in a served hit field. A
# hit dict is scrubbed of these so even a drifted upstream note cannot leak one.
_FORBIDDEN_HIT_KEYS = frozenset({
    "probability", "prob", "win_prob", "odds", "roi", "edge", "kelly", "brier",
    "clv", "vig", "juice", "ev", "expected_value", "pnl", "stake", "units",
    "bankroll", "profit", "dollar", "usd",
})


def _scrub_hit(hit_obj: Any) -> Dict[str, Any]:
    """Serialize a BrainHit to a number-free dict (drop any forbidden key)."""
    try:
        d = asdict(hit_obj)
    except Exception:  # noqa: BLE001 -- non-dataclass: shallow-copy what we can
        d = dict(getattr(hit_obj, "__dict__", {}) or {})
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if str(k).lower() in _FORBIDDEN_HIT_KEYS:
            continue
        if isinstance(v, dict):
            v = {kk: vv for kk, vv in v.items()
                 if str(kk).lower() not in _FORBIDDEN_HIT_KEYS}
        out[k] = v
    return out


def _query_brain(query: str, sport: Optional[str], kind: Optional[str],
                 top_k: int) -> List[Dict[str, Any]]:
    """Run the vetted brain_query and return number-free hit dicts. Never raises."""
    try:
        from scripts.platformkit.brain_query import brain_query, is_number_free
    except Exception as exc:  # noqa: BLE001 -- brain unavailable -> honest empty
        logger.warning("intel_routes: brain_query import failed: %s", exc)
        return []
    try:
        hits = brain_query(query, sport=sport, kind=kind, top_k=top_k)
    except Exception as exc:  # noqa: BLE001 -- retrieval failure -> honest empty
        logger.warning("intel_routes: brain_query(%r) failed: %s", query, exc)
        return []
    out: List[Dict[str, Any]] = []
    for h in hits:
        try:
            if not is_number_free(h):  # defensive: skip any hit that fails the contract
                continue
        except Exception:  # noqa: BLE001 -- if the check itself fails, drop the hit
            continue
        out.append(_scrub_hit(h))
    return out


@router.get("/api/intel/{query}", dependencies=[Depends(_guard)])
@honest_route(extra={"hits": [], "count": 0, "number_free": True})
def get_intel(
    query: str,
    sport: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    top_k: int = Query(default=8, ge=1, le=25),
) -> JSONResponse:
    """Number-free scouting retrieval over the brain graph. Never raises."""
    hits = _query_brain(query, sport, kind, top_k)
    return JSONResponse({
        "status": "ok",
        "query": query,
        "sport": sport,
        "kind": kind,
        "hits": hits,
        "count": len(hits),
        "number_free": True,
        "edge_claimed": False,
        "real_money_enabled": False,
        "honest_note": _INTEL_HONEST_NOTE,
    })


__all__ = ["router"]
