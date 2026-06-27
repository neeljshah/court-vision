"""frontend.funnel_routes -- read-only GATE-VERDICT LEDGER + IMPROVEMENT BACKLOG.

Surfaces two static, on-disk honest artifacts over HTTP so the CourtVision System
page can render them WITHOUT recomputing anything (pure offline reads):

  GET /api/funnel/ledger
      Every signal that has been run through the leak-free gate, as a flat table
      read from data/frontend/funnel/*.json:
        {status, rows:[{id, sport, layer, verdict, vs_close, source}], n, counts}
      verdict is the recorded gate decision VERBATIM (SHIP / REJECT /
      INSUFFICIENT_DATA / PARTIAL / TIER3_BLOCKED / ...). The single SHIP is the
      soccer-corners CALIBRATION survivor -- vs_close stays UNPROVEN (calibration,
      not a market edge). No $ field; nothing is invented -- a torn file is skipped.

  GET /api/meta/backlog
      The ranked "what we'll get better at next" list read VERBATIM from
      .planning/product/meta/improvement_backlog.json:
        {status, note, categories, n, candidates:[...]}
      MEASUREMENT-ONLY: it discovers + ranks; it never fixes / ships / flips a
      flag. A REJECT-leaning expectation is a closed dead-end, never force-fed.

Both endpoints NEVER raise: a missing / torn source collapses to an explicit
unavailable sentinel (status='unavailable', empty list) the UI degrades on, never
green-on-missing and never a fabricated row. No $ field is ever emitted.

INVARIANTS: build only under frontend/; reads only (never writes data/registry/,
never flips a flag); <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.funnel_routes requires fastapi.") from exc

from predict_service.honest_route import honest_route

logger = logging.getLogger(__name__)

router = APIRouter()

# Repo-root-anchored paths resolved from this file so a flaky cwd never matters.
_REPO = pathlib.Path(__file__).resolve().parents[1]
_FUNNEL_DIR = _REPO / "data" / "frontend" / "funnel"
_BACKLOG = _REPO / ".planning" / "product" / "meta" / "improvement_backlog.json"

# vs_close is UNPROVEN everywhere -- there are no liquid in-play prices to grade
# against; every survivor is CALIBRATION only, never a claimed market edge.
_DEFAULT_VS_CLOSE = "UNPROVEN -- CALIBRATION only (no liquid in-play prices)"


# -- low-level reads (NEVER raise) --------------------------------------------

def _read_json(path: pathlib.Path) -> Optional[Any]:
    """Best-effort JSON read; missing / torn / garbage -> None (never raises)."""
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="ascii", errors="replace")
        return json.loads(raw) if raw.strip() else None
    except Exception as exc:  # noqa: BLE001 -- pure offline read; belt + braces
        logger.debug("funnel_routes: read_json(%s) failed: %s", path, exc)
        return None


def _verdict_of(doc: Dict[str, Any]) -> str:
    """The recorded gate verdict, read VERBATIM. Falls back through the known
    alternate keys (parity / coherence docs carry no top-level `verdict`)."""
    for key in ("verdict", "gate_verdict", "overall_verdict"):
        v = doc.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    # Parity / coherence style docs: derive an honest label, never fabricate SHIP.
    if isinstance(doc.get("parity_overall"), str):
        return doc["parity_overall"].strip().upper()
    if doc.get("coherence") is not None:
        return "COHERENCE" if doc.get("status") == "ok" else "INSUFFICIENT_DATA"
    return "INSUFFICIENT_DATA"


def _ledger_rows() -> List[Dict[str, Any]]:
    """One flat row per funnel/*.json gate artifact. Torn files are skipped."""
    rows: List[Dict[str, Any]] = []
    if not _FUNNEL_DIR.exists():
        return rows
    for path in sorted(_FUNNEL_DIR.glob("*.json")):
        doc = _read_json(path)
        if not isinstance(doc, dict):
            continue
        layer = doc.get("layer") or doc.get("real_layer") or doc.get("lane")
        vs_close = doc.get("vs_close")
        rows.append({
            "id": path.stem,
            "sport": doc.get("sport") or _sport_from_stem(path.stem),
            "layer": layer if isinstance(layer, str) else None,
            "verdict": _verdict_of(doc),
            "vs_close": vs_close if isinstance(vs_close, str) else _DEFAULT_VS_CLOSE,
            "source": path.name,
            "edge_claimed": False,
        })
    return rows


def _sport_from_stem(stem: str) -> str:
    """Best-effort sport prefix from the file stem (nba_*, mlb_*, soccer_*...)."""
    for s in ("soccer_intl", "soccer", "nba", "mlb", "tennis"):
        if stem.startswith(s):
            return s
    return "unknown"


def _counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        v = str(r.get("verdict") or "INSUFFICIENT_DATA")
        out[v] = out.get(v, 0) + 1
    return out


# -- gate-verdict ledger ------------------------------------------------------

@router.get("/api/funnel/ledger")
@honest_route(extra={"rows": [], "n": 0, "counts": {}})
def funnel_ledger() -> JSONResponse:
    """Every signal run through the leak-free gate, as a flat verdict table.

    Read-only over data/frontend/funnel/*.json. The lone SHIP is the soccer-corners
    CALIBRATION survivor; vs_close stays UNPROVEN (calibration, not an edge). No $.
    """
    rows = _ledger_rows()
    status = "ok" if rows else "unavailable"
    body = {
        "status": status,
        "rows": rows,
        "n": len(rows),
        "counts": _counts(rows),
        "edge_claimed": False,
        "honest_note": (
            "Gate verdicts read verbatim. A REJECT / INSUFFICIENT_DATA is a "
            "SUCCESS (markets are efficient). The lone SHIP (soccer corners) is a "
            "CALIBRATION improvement, NOT a market edge -- vs_close is UNPROVEN."
        ),
    }
    code = 200 if rows else 503
    return JSONResponse(body, status_code=code)


# -- improvement backlog ------------------------------------------------------

@router.get("/api/meta/backlog")
@honest_route(extra={"candidates": [], "n": 0, "categories": []})
def meta_backlog() -> JSONResponse:
    """The ranked 'what we'll get better at next' list, read VERBATIM.

    MEASUREMENT-ONLY: discovers + ranks; never fixes / ships / flips a flag. A
    missing / torn file degrades to an honest unavailable sentinel. No $ field.
    """
    doc = _read_json(_BACKLOG)
    if not isinstance(doc, dict):
        return JSONResponse(
            {"status": "unavailable",
             "reason": "improvement_backlog.json missing or unreadable",
             "candidates": [], "n": 0, "categories": [], "edge_claimed": False},
            status_code=503,
        )
    cands = doc.get("candidates")
    cands = cands if isinstance(cands, list) else []
    body = {
        "status": "ok",
        "note": doc.get("note"),
        "categories": doc.get("categories") if isinstance(
            doc.get("categories"), list) else [],
        "candidates": cands,
        "n": len(cands),
        "edge_claimed": False,
    }
    return JSONResponse(body)


__all__ = ["router"]
