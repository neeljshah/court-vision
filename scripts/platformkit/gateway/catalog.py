"""scripts.platformkit.gateway.catalog -- the catalog + single all_honest verdict.

WAVE 4. Two pure helpers over the gateway FACES registry:

  catalog()
      The GET /api/catalog payload: the list of faces (id / version / capabilities
      / routes / honest_note), the schema-wide honest framing, and the standing
      rails (units only, edge_claimed=False, real_money_enabled=False). No number.

  all_honest(faces=None, *, probe=None)
      THE single boolean. True ONLY when NO face is serving a $ field, a fabricated
      edge, a stale-green, or real-money-enabled. It flips False the INSTANT any
      face does. The verdict is computed by scanning each face's declared rails
      AND (optionally) a caller-injected `probe` list of LIVE face responses -- so
      a runtime violation (a $ key, edge_claimed=True, real_money_enabled=True, or
      a stale+serveable=True body) flips it False immediately.

This is the honesty heartbeat of the unified gateway: one bit the whole product
can be judged on. It NEVER fabricates a pass -- any ambiguity reads dishonest.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no $
field; reuse gateway.FACES + the honesty_mw money-key tokens (no new rules math).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from scripts.platformkit.gateway.gateway import (
    FACES,
    RAIL_EDGE_CLAIMED,
    RAIL_REAL_MONEY_ENABLED,
    RAIL_UNITS,
    list_faces,
)

logger = logging.getLogger(__name__)

CATALOG_HONEST_NOTE = (
    "One sports-intelligence model exposed through many contracted faces. Every "
    "face is units/probability only -- NO $, no fabricated edge, no real money. "
    "Pregame matches the devigged close (a success, never a beat); in-game is the "
    "proven conditioning calibration. A stale/missing feed reads not-serveable, "
    "never green. all_honest is the single bit: True iff no face violates a rail."
)

# The $/P&L/ROI key tokens that flip all_honest False if they appear as an object
# KEY anywhere in a live face response. Mirrors predict_service.honesty_mw's
# forbidden set (imported when available; a small fallback keeps this pure/total).
try:
    from predict_service.honesty_mw import _FORBIDDEN_MONEY_KEYS as _MONEY_TOKENS
except Exception:  # noqa: BLE001 -- keep catalog importable without the app deps
    _MONEY_TOKENS = (
        "pnl", "roi", "bankroll", "profit", "dollar", "usd", "dollars",
        "stake", "stake_dollars", "stake_usd",
    )

# UNITS-rail exemption -- MUST mirror predict_service.honesty_mw exactly so the two
# money-key scanners agree. The bare "stake" token (above) over-matches the
# canonical units field stake_units and the two-leg arb unit stakes stake_a/stake_b;
# these are the UNITS rail itself, NOT a $/P&L field, so they must NOT flip the
# honesty bit. The explicit $ keys stake_dollars/stake_usd stay forbidden (they
# carry no "units" token and are listed explicitly below).
try:
    from predict_service.honesty_mw import (
        _UNITS_RAIL_EXEMPT_KEYS as _UNITS_EXEMPT_KEYS,
        _UNITS_RAIL_EXEMPT_TOKEN as _UNITS_EXEMPT_TOKEN,
    )
except Exception:  # noqa: BLE001 -- fallback keeps catalog importable + consistent
    _UNITS_EXEMPT_KEYS = ("stake_a", "stake_b")
    _UNITS_EXEMPT_TOKEN = "units"
_EXPLICIT_DOLLAR_KEYS = ("stake_dollars", "stake_usd")

# Retracted figures that must NEVER print live (see no-edge-claims rule). Matched
# as numeric VALUES anywhere in a probed body -- their live appearance is dishonest.
_RETRACTED_NUMBERS = (18.38, 0.119, 54.0, 78.11, 8.94, 54.57)


def catalog() -> Dict[str, Any]:
    """The GET /api/catalog payload. Lists every face + the standing rails. Pure."""
    return {
        "status": "ok",
        "faces": list_faces(),
        "count": len(FACES),
        "units": RAIL_UNITS,
        "edge_claimed": RAIL_EDGE_CLAIMED,
        "real_money_enabled": RAIL_REAL_MONEY_ENABLED,
        "honest_note": CATALOG_HONEST_NOTE,
    }


def _has_money_key(node: Any, depth: int = 0) -> bool:
    """True iff any object KEY in *node* is a forbidden $/P&L/ROI token. Total."""
    if depth > 40:
        return False
    if isinstance(node, dict):
        for k, v in node.items():
            kl = str(k).lower()
            words = set(kl.replace("-", "_").split("_"))
            hit = kl in _MONEY_TOKENS or bool(words & set(_MONEY_TOKENS))
            if hit:
                # UNITS-rail exemption (mirror honesty_mw): forgive ONLY when the
                # sole matching token is the bare unit-stake token on a units-rail
                # key (stake_units / stake_a / stake_b). A real $/roi/pnl token --
                # or an explicit $ key (stake_dollars/stake_usd) -- still trips.
                is_units_rail = (
                    _UNITS_EXEMPT_TOKEN in words or kl in _UNITS_EXEMPT_KEYS)
                if is_units_rail:
                    bad = (words & set(_MONEY_TOKENS)) - {"stake"}
                    if not bad and kl not in _EXPLICIT_DOLLAR_KEYS:
                        hit = False
            if hit:
                return True
            if _has_money_key(v, depth + 1):
                return True
    elif isinstance(node, (list, tuple)):
        for v in node:
            if _has_money_key(v, depth + 1):
                return True
    return False


def _has_retracted_number(node: Any, depth: int = 0) -> bool:
    """True iff a retracted figure appears as a numeric VALUE in *node*. Total."""
    if depth > 40:
        return False
    if isinstance(node, bool):
        return False
    if isinstance(node, (int, float)):
        return any(abs(float(node) - r) < 1e-6 for r in _RETRACTED_NUMBERS)
    if isinstance(node, dict):
        return any(_has_retracted_number(v, depth + 1) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(_has_retracted_number(v, depth + 1) for v in node)
    return False


def _face_violation(body: Any) -> Optional[str]:
    """Return a one-line reason if a LIVE face body violates a rail, else None."""
    if not isinstance(body, dict):
        return None
    if _has_money_key(body):
        return "live $/P&L/ROI key in a face response"
    if body.get("edge_claimed") is True:
        return "a face response sets edge_claimed=True"
    if body.get("real_money_enabled") is True:
        return "a face response enables real money"
    if _has_retracted_number(body):
        return "a retracted figure printed live"
    # stale-green: a not-serveable freshness verdict but serveable still True.
    fresh = body.get("freshness")
    if isinstance(fresh, dict) and fresh.get("serveable") is False \
            and body.get("serveable") is True:
        return "a stale feed served green (serveable=True on stale)"
    return None


def all_honest(
    faces: Optional[Dict[str, Any]] = None,
    *,
    probe: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """The single honesty verdict. ok=True ONLY if NO face violates a rail.

    Two layers, both must pass:
      1. The DECLARED rails on every FaceSpec (units==probability, edge_claimed
         False, real_money_enabled False). A face whose static contract claims an
         edge or enables money flips this False.
      2. The LIVE bodies in *probe* (optional): any injected face response carrying
         a $ key, edge_claimed=True, real_money_enabled=True, a retracted number,
         or a stale-green flips this False the instant it is observed.

    Returns {"ok": bool, "violations": [...], "n_faces": int, "honest_note": ...}.
    NEVER fabricates a pass: a non-dict / ambiguous probe body is skipped, but any
    detected violation is fatal.
    """
    reg = faces if faces is not None else FACES
    violations: List[Dict[str, Any]] = []

    for fid, spec in reg.items():
        units = getattr(spec, "units", None) or (
            spec.get("units") if isinstance(spec, dict) else None)
        edge = getattr(spec, "edge_claimed", None)
        rme = getattr(spec, "real_money_enabled", None)
        if isinstance(spec, dict):
            edge = spec.get("edge_claimed")
            rme = spec.get("real_money_enabled")
        if units not in (None, RAIL_UNITS):
            violations.append({"face": fid, "reason": "declared units are not probability"})
        if edge is True:
            violations.append({"face": fid, "reason": "FaceSpec claims an edge"})
        if rme is True:
            violations.append({"face": fid, "reason": "FaceSpec enables real money"})

    for i, body in enumerate(probe or []):
        reason = _face_violation(body)
        if reason:
            violations.append({"face": "probe[%d]" % i, "reason": reason})

    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "n_faces": len(reg),
        "honest_note": CATALOG_HONEST_NOTE,
    }


__all__ = ["catalog", "all_honest", "CATALOG_HONEST_NOTE"]
