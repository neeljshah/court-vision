"""frontend.autonomy_routes -- read-only autonomy + self-improve timeline routes.

Surfaces two observability endpoints the CourtVision P6 dashboard reads, with the
RAIL that the self-improve loop is MEASUREMENT-ONLY and must read honestly INERT,
and that a missing/stale autonomy feed is NEVER green:

  GET /api/improve/timeline
      The self-improve loop's OWN per-cycle decisions, read from
      data/cache/improve/{proposals.jsonl, status.jsonl, checkpoint.json}:
        {status, cycles:[{cycle,decision,reason,at}], n_cycles, cycle_counter,
         n_promoted, enabled, edge_claimed:false, honest_note}
      CRITICAL honesty: `enabled` = pipeline_flag.pipeline_enabled() (the human-
      managed PIPELINE_ENABLED sentinel; False on this box -> the loop ships
      nothing). `n_promoted` counts ONLY real version promotions (a proposals row
      with decision SHIP/PROMOTE that advanced a shipped_version) -- a no_candidate
      / reject / faked label can never inflate it. No $ key, no edge claim.

  GET /api/ops/autonomy
      The ONE canonical autonomy status doc data/frontend/ops/autonomy_status.json
      VERBATIM (written by scripts.platformkit.autonomy.status_composer), or an
      honest {status:'unavailable', overall:'down'} sentinel when the file is
      missing / torn / STALE (older than the SLA). Never green-on-missing; we only
      READ the composer's output, never recompute it here.

Both endpoints NEVER raise: a missing/torn source collapses to an explicit
unavailable sentinel the UI degrades on. No $ field is ever emitted.

INVARIANTS: build only under frontend/; reads only (never writes data/registry/,
MEMORY.md; never flips a flag); <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import json
import logging
import pathlib
import time
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.autonomy_routes requires fastapi.") from exc

logger = logging.getLogger(__name__)

router = APIRouter()

# Repo-root-anchored paths to the self-improve outputs + the canonical autonomy
# status doc. Resolved from this file so a flaky cwd never matters.
_REPO = pathlib.Path(__file__).resolve().parents[1]
_IMPROVE_DIR = _REPO / "data" / "cache" / "improve"
_IMPROVE_CKPT = _IMPROVE_DIR / "checkpoint.json"
_IMPROVE_STATUS = _IMPROVE_DIR / "status.jsonl"
_IMPROVE_PROPOSALS = _IMPROVE_DIR / "proposals.jsonl"
_AUTONOMY_STATUS = _REPO / "data" / "frontend" / "ops" / "autonomy_status.json"

# A canonical autonomy doc older than this is STALE -> reported unavailable, never
# green-on-stale (the composer writers refresh on each loop tick ~60s).
_AUTONOMY_STALE_SEC = 600.0


# -- low-level reads (NEVER raise) --------------------------------------------

def _read_jsonl(path: pathlib.Path, max_rows: int = 50) -> List[Dict[str, Any]]:
    """Return up to the last *max_rows* JSON objects of a .jsonl file, in
    chronological order. Missing/torn -> [] (never raises)."""
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="ascii", errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001
        logger.debug("autonomy_routes: read_jsonl(%s) failed: %s", path, exc)
        return []
    out: List[Dict[str, Any]] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict):
            out.append(obj)
        if len(out) >= max_rows:
            break
    out.reverse()
    return out


def _read_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Best-effort JSON dict read; missing/torn/garbage -> None (never raises)."""
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="ascii", errors="replace")
        data = json.loads(raw) if raw.strip() else None
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("autonomy_routes: read_json(%s) failed: %s", path, exc)
        return None


# -- self-improve timeline (INERT-honest) -------------------------------------

def _pipeline_enabled() -> bool:
    """True ONLY when the human-managed PIPELINE_ENABLED sentinel exists on disk.

    The self-improve loop is MEASUREMENT-ONLY: it NEVER creates this sentinel, so
    on this box it reads False and the UI must label the loop 'measurement-only /
    not-enabled', never 'shipping'. A missing helper degrades to False (inert).
    """
    try:
        from scripts.platformkit.improve.pipeline_flag import (  # noqa: PLC0415
            pipeline_enabled,
        )
        return bool(pipeline_enabled())
    except Exception as exc:  # noqa: BLE001 -- absent helper -> inert, never enabled
        logger.warning("autonomy_routes: pipeline_flag import failed: %s", exc)
        return False


def _timeline_cycles() -> List[Dict[str, Any]]:
    """Per-cycle rows {cycle, decision, reason, at}.

    Source priority: the daemon's proposals.jsonl (its own per-cycle PROPOSAL log)
    when present, else the status.jsonl escalation tail. Both are the loop's OWN
    output -- nothing here is fabricated; an empty log -> [] (cold / inert).
    """
    rows = _read_jsonl(_IMPROVE_PROPOSALS)
    cycles: List[Dict[str, Any]] = []
    if rows:
        for i, r in enumerate(rows):
            reasons = r.get("reasons")
            reason = (reasons[0] if isinstance(reasons, list) and reasons
                      else r.get("note"))
            cycles.append({
                "cycle": i,
                "decision": r.get("decision"),
                "reason": reason,
                "at": r.get("ts"),
            })
        return cycles
    for i, r in enumerate(_read_jsonl(_IMPROVE_STATUS)):
        cycles.append({
            "cycle": i,
            "decision": r.get("decision") or r.get("status"),
            "reason": r.get("status"),
            "at": r.get("ts"),
        })
    return cycles


def _n_promoted() -> int:
    """Count REAL ships ONLY: a proposals row with decision SHIP/PROMOTE that also
    advanced a shipped_version. Reads the raw proposals so a faked decision label
    alone can never inflate it; a no_candidate / no_new_games / reject is 0."""
    n = 0
    for r in _read_jsonl(_IMPROVE_PROPOSALS):
        dec = str(r.get("decision") or "").upper()
        if dec in ("SHIP", "PROMOTE") and r.get("shipped_version") is not None:
            n += 1
    return n


@router.get("/api/improve/timeline")
def improve_timeline() -> JSONResponse:
    """Self-improve loop timeline -- INERT / measurement-only honest.

    Surfaces the loop's own per-cycle decisions WITHOUT claiming a ship that did
    not happen: `enabled` reflects the PIPELINE_ENABLED sentinel (False here), and
    `n_promoted` counts only real shipped_version advances. No $ key, no edge claim.
    """
    enabled = _pipeline_enabled()
    cycles = _timeline_cycles()
    ckpt = _read_json(_IMPROVE_CKPT) or {}
    n_promoted = _n_promoted()
    status = "ok" if (cycles or ckpt) else "unavailable"
    body = {
        "status": status,
        "cycles": cycles,
        "n_cycles": len(cycles),
        "cycle_counter": int(ckpt.get("cycle", 0) or 0),
        "n_promoted": n_promoted,
        "enabled": enabled,
        "edge_claimed": False,
        "honest_note": (
            "Self-improve loop is MEASUREMENT-ONLY and reads INERT: it never "
            "creates the PIPELINE_ENABLED sentinel, ships nothing until a human "
            "enables it, and claims no $ edge. enabled=%s; n_promoted counts only "
            "real version promotions." % str(enabled).lower()
        ),
    }
    return JSONResponse(body)


# -- canonical autonomy status (fail-closed on missing/stale) -----------------

@router.get("/api/ops/autonomy")
def ops_autonomy() -> JSONResponse:
    """The ONE canonical autonomy_status.json verbatim, or an honest unavailable
    sentinel when the file is missing / torn / STALE.

    NEVER green-on-missing: an absent or stale doc (older than the SLA) yields
    status='unavailable' + overall='down' with an explicit reason, never a
    fabricated 'ok'. We only READ the composer output; we never recompute it here.
    """
    doc = _read_json(_AUTONOMY_STATUS)
    if doc is None:
        return JSONResponse(
            {"status": "unavailable",
             "reason": "autonomy_status.json missing or unreadable",
             "overall": "down", "edge_claimed": False},
            status_code=503,
        )
    gen = doc.get("generated_at")
    try:
        age = time.time() - float(gen) if gen is not None else None
    except (TypeError, ValueError):
        age = None
    if age is not None and age > _AUTONOMY_STALE_SEC:
        return JSONResponse(
            {"status": "unavailable",
             "reason": "autonomy_status.json stale (%.0fs > %.0fs SLA)" % (
                 age, _AUTONOMY_STALE_SEC),
             "overall": "down", "generated_at": gen, "edge_claimed": False},
            status_code=503,
        )
    out = dict(doc)
    out.setdefault("status", "ok")
    out.setdefault("edge_claimed", False)
    return JSONResponse(out)


__all__ = ["router"]
