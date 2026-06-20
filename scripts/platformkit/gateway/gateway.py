"""scripts.platformkit.gateway.gateway -- the unified-gateway FACES registry + wrap().

WAVE 4. ONE sports-intelligence model is exposed through MANY contracted FACES:

    prediction   -- the calibrated pregame/in-game number (predict_service)
    execution    -- the auditable bet-validation / CLV surface (quant_routes)
    lines        -- the all-books line board (lines_routes)
    intelligence -- the NUMBER-FREE brain/archetype scouting surface (brain_query)

This module owns TWO things and no new math:

  FACES
      A declarative registry: one FaceSpec per face carrying its id, version,
      capabilities, route prefixes, and a one-line honest_note. catalog.py reads
      this to build GET /api/catalog and the all_honest verdict.

  wrap(body, *, face, sport_dir=None, now=None)
      Stamps EVERY face response with the standing honesty rails:
        * units            -> "probability"  (units only, NEVER $)
        * edge_claimed     -> False
        * real_money_enabled -> False
        * face / face_version
        * freshness        -> inherited from odds_provider.freshness.sidecar_status
                              when a sport_dir is given; serveable=False on a
                              stale/missing/unknown feed (NEVER green-on-stale).
      wrap NEVER fabricates a $ field and NEVER flips a flag on. It is pure +
      total (a freshness-read failure degrades to serveable=False, never raises).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no
secrets; no $ field; reuse odds_provider.freshness verbatim (no new staleness math).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# The standing honesty rails stamped on every face response. These are the
# product-wide invariants: units only (never $), no edge claimed, real money
# default-DENY. They are constants, never computed from request input.
RAIL_UNITS = "probability"
RAIL_EDGE_CLAIMED = False
RAIL_REAL_MONEY_ENABLED = False


@dataclass(frozen=True)
class FaceSpec:
    """One contracted API face over the single sports-intelligence model.

    All fields are declarative; a FaceSpec carries NO number and NO $ field. It
    describes a face's id, version, capabilities, route prefixes, and an honest
    one-line note (calibration framing -- never an edge claim).
    """
    face_id: str
    version: str
    title: str
    capabilities: List[str]
    routes: List[str]
    honest_note: str
    units: str = RAIL_UNITS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face": self.face_id,
            "version": self.version,
            "title": self.title,
            "capabilities": list(self.capabilities),
            "routes": list(self.routes),
            "units": self.units,
            "edge_claimed": RAIL_EDGE_CLAIMED,
            "real_money_enabled": RAIL_REAL_MONEY_ENABLED,
            "honest_note": self.honest_note,
        }


# --------------------------------------------------------------------------- #
# The FACES registry -- one row per contracted face over the SAME model.
# --------------------------------------------------------------------------- #
FACES: Dict[str, FaceSpec] = {
    "prediction": FaceSpec(
        face_id="prediction",
        version="1.1.0",
        title="Calibrated prediction face",
        capabilities=["pregame", "ingame", "uncertainty", "surface", "multi_sport"],
        routes=["/api/predict/{sport}", "/api/predict/{sport}/{game_id}",
                "/api/predict/contract", "/api/ingame/{sport}/{game_id}"],
        honest_note=(
            "Calibrated probability/units only. Pregame MATCHES the devigged "
            "close (a success, never a beat); in-game is the proven conditioning "
            "calibration. vs_close defaults UNPROVEN. No $ edge."),
    ),
    "execution": FaceSpec(
        face_id="execution",
        version="1.0.0",
        title="Auditable execution / CLV face",
        capabilities=["validate", "devig", "arb_descriptive", "risk_units", "clv"],
        routes=["/api/quant/{sport}/validate", "/api/quant/{sport}/devig",
                "/api/quant/{sport}/arb", "/api/quant/risk", "/api/quant/clv"],
        honest_note=(
            "Transparency only -- units/probability, never $. MOST verdicts are "
            "no_bet / match-the-close (a success). RoR is descriptive, never a "
            "guarantee. Placement stays paper (executed=False). No $ edge."),
    ),
    "lines": FaceSpec(
        face_id="lines",
        version="1.0.0",
        title="All-books line board face",
        capabilities=["board", "history", "is_close", "clv_proxy_flag"],
        routes=["/api/lines/{sport}", "/api/lines/{sport}/{game_id}/history"],
        honest_note=(
            "Raw multi-book lines + tick history. A proxy close is flagged, never "
            "hidden; a stale/absent feed reads unavailable, never green. No $ edge."),
    ),
    "intelligence": FaceSpec(
        face_id="intelligence",
        version="1.0.0",
        title="Number-free scouting / archetype face",
        capabilities=["brain_query", "archetypes", "schemes", "person_free",
                      "number_free"],
        routes=["/api/intel/{query}"],
        honest_note=(
            "Descriptive, person-free scouting from the brain graph. Returns "
            "UNDERSTANDING + provenance chips ONLY -- never a probability, odds, "
            "edge, Kelly, or any bettable number. No $ edge."),
    ),
}


def list_faces() -> List[Dict[str, Any]]:
    """Return the catalog rows for every registered face (declarative; no number)."""
    return [FACES[k].to_dict() for k in sorted(FACES)]


def _freshness_block(
    sport_dir: Optional[Any], now: Optional[Any]
) -> Dict[str, Any]:
    """Inherit the serving-path freshness verdict from odds_provider.freshness.

    Returns {"serveable": bool, "status": str, "age_sec": ..., "as_of": ...}.
    When no sport_dir is given, freshness is NOT_APPLICABLE and serveable stays
    True (a face with no feed -- e.g. number-free intel -- is not gated on lines).
    A read failure degrades to serveable=False (NEVER green-on-stale); never raises.
    """
    if sport_dir is None:
        return {"serveable": True, "status": "not_applicable", "age_sec": None,
                "as_of": None}
    try:
        from scripts.platformkit.odds_provider.freshness import sidecar_status
        verdict = sidecar_status(sport_dir, now=now)
        return {
            "serveable": bool(verdict.get("ok", False)),
            "status": str(verdict.get("status", "unknown")),
            "age_sec": verdict.get("age_sec"),
            "as_of": verdict.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001 -- a freshness-read failure is never green
        logger.warning("gateway._freshness_block failed for %r: %s", sport_dir, exc)
        return {"serveable": False, "status": "unknown", "age_sec": None,
                "as_of": None}


def wrap(
    body: Dict[str, Any],
    *,
    face: str,
    sport_dir: Optional[Any] = None,
    now: Optional[Any] = None,
) -> Dict[str, Any]:
    """Stamp the standing honesty rails on a face response *body*.

    Mutates and returns *body* with: units (probability), edge_claimed=False,
    real_money_enabled=False, face, face_version, and a freshness block whose
    serveable flag inherits odds_provider.freshness (False on stale/missing/unknown
    -- NEVER green-on-stale). When sport_dir is None, freshness is not applicable
    and serveable stays True (e.g. the number-free intel face has no feed).

    A pre-existing honest_note on body is preserved; otherwise the face's note is
    stamped. NEVER introduces a $ field; NEVER flips a flag on. Pure + total.
    """
    if not isinstance(body, dict):  # defensive: only dict envelopes are wrapped
        body = {"status": "error", "reason": "non-dict body"}
    spec = FACES.get(face)
    body["units"] = RAIL_UNITS
    body["edge_claimed"] = RAIL_EDGE_CLAIMED
    body["real_money_enabled"] = RAIL_REAL_MONEY_ENABLED
    body["face"] = face
    body["face_version"] = spec.version if spec is not None else "unknown"
    body["freshness"] = _freshness_block(sport_dir, now)
    # A stale/missing/unknown feed can never read serveable=True.
    if not body["freshness"].get("serveable", False):
        body.setdefault("serveable", False)
        body["serveable"] = False
    else:
        body.setdefault("serveable", True)
    if spec is not None:
        body.setdefault("honest_note", spec.honest_note)
    return body


__all__ = ["FACES", "FaceSpec", "list_faces", "wrap",
           "RAIL_UNITS", "RAIL_EDGE_CLAIMED", "RAIL_REAL_MONEY_ENABLED"]
