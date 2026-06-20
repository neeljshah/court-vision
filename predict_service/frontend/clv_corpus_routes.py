"""predict_service.frontend.clv_corpus_routes -- GET /api/improve/clv-corpus.

Serves per-candidate CLV-delta rows the Models page (SI-06) needs, derived from
the clv_corpus proposals file (data/cache/improve/proposals.jsonl).  Each row
carries honest replication labels:

  n_rep == 1   -> replication_label: REPLICATION_PENDING
  all-proxy    -> vs_close: "UNPROVEN" (surfaced verbatim; never green)
  missing file -> status: "unavailable" (never green)

INVARIANTS: read-only; no $ / pnl / roi field; edge_claimed=false;
UNITS/probability only; INSUFFICIENT_DATA / REPLICATION_PENDING surfaced
verbatim; missing proposals file -> status=unavailable, never green;
vs_close stays UNPROVEN unless the caller has explicit evidence it was
promoted through the full human-gated P2 upgrade path.  ASCII; <=300 LOC;
never raises to caller.
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError("clv_corpus_routes requires fastapi.") from exc

logger = logging.getLogger(__name__)

router = APIRouter()

_REPO = pathlib.Path(__file__).resolve().parents[2]
_PROPOSALS_PATH = _REPO / "data" / "cache" / "improve" / "proposals.jsonl"

_HONEST_NOTE = (
    "Calibration metrics only -- no $ / edge / profit claim.  "
    "REPLICATION_PENDING means n_rep==1: the candidate passed the 5-gate ratchet "
    "on one corpus but requires a second independent corpus before it can SHIP.  "
    "vs_close stays UNPROVEN: the model has not yet beaten the true close on "
    "held-out outcome Brier across >=2 independent corpora with clustered DM p<0.05.  "
    "INSUFFICIENT_DATA is honest when the proposals file is absent or empty.  "
    "All values are probabilities, never dollar amounts."
)

# Keys that must never appear in any response ($ / P&L).
_BANNED_KEYS = frozenset({"$", "roi", "pnl", "profit"})


def _pipeline_enabled() -> bool:
    """True only when the human-managed PIPELINE_ENABLED sentinel exists."""
    try:
        from scripts.platformkit.improve.pipeline_flag import (  # noqa: PLC0415
            pipeline_enabled,
        )
        return bool(pipeline_enabled())
    except Exception as exc:  # noqa: BLE001
        logger.debug("clv_corpus_routes: pipeline_flag import failed: %s", exc)
        return False


def _read_proposals(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Read all rows from proposals.jsonl.  Returns [] on missing/torn file."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    except Exception as exc:  # noqa: BLE001
        logger.debug("clv_corpus_routes: read error: %s", exc)
    return rows


def _replication_label(n_rep: Any) -> str:
    """Return the honest replication label for a candidate row.

    n_rep == 1  -> REPLICATION_PENDING (one corpus; needs a second).
    n_rep >= 2  -> REPLICATED (two or more independent corpora).
    anything else -> REPLICATION_PENDING (honest default; never fabricate SHIP).
    """
    try:
        n = int(n_rep)
    except (TypeError, ValueError):
        return "REPLICATION_PENDING"
    if n >= 2:
        return "REPLICATED"
    return "REPLICATION_PENDING"


def _vs_close_label(row: Dict[str, Any]) -> str:
    """Return an honest vs_close label for a candidate row.

    If every corpus in the row is a proxy close (is_true_close=False or
    saw_proxy=True and NOT all_positive) -> 'vs_close UNPROVEN'.
    Otherwise remain at the stored value or default to 'UNPROVEN'.
    """
    # The candidate row itself may carry a vs_close field from clv_candidate.py.
    stored = str(row.get("vs_close", "UNPROVEN")).strip()
    # The proposals row may have a saw_proxy flag (from the corpus).
    saw_proxy = bool(row.get("saw_proxy", False))
    all_positive = bool(row.get("all_positive", False))
    # If the corpus was built only from proxy closes, label honestly.
    if saw_proxy and not all_positive:
        return "vs_close UNPROVEN"
    # If the stored label is already a known honest value, pass through.
    if stored.upper() in ("UNPROVEN", "VS_CLOSE UNPROVEN"):
        return "UNPROVEN"
    # A stored PROVEN would only come from the human-gated upgrade path.
    return stored


def _build_candidate_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Project a raw proposals.jsonl row into a safe, honest candidate row.

    Strips any banned keys; adds replication_label and vs_close label; ensures
    edge_claimed=false; units=probability.
    """
    n_rep = raw.get("n_corpora_replicated", raw.get("n_rep", 0))
    decision = str(raw.get("decision", "NO_CANDIDATE")).upper()
    vs_close = _vs_close_label(raw)
    rep_label = _replication_label(n_rep)

    # Surface the DM delta if present from a corpus fold.
    dm_p: Optional[float] = None
    delta: Optional[float] = None
    significant: Optional[bool] = None
    try:
        dm_p_raw = raw.get("dm_p")
        if dm_p_raw is not None:
            dm_p = float(dm_p_raw)
    except (TypeError, ValueError):
        pass
    try:
        delta_raw = raw.get("delta")
        if delta_raw is not None:
            delta = float(delta_raw)
    except (TypeError, ValueError):
        pass
    try:
        sig_raw = raw.get("significant")
        if sig_raw is not None:
            significant = bool(sig_raw)
    except (TypeError, ValueError):
        pass

    return {
        "ts":                raw.get("ts"),
        "name":              str(raw.get("name", "")),
        "decision":          decision,
        "n_rep":             int(n_rep) if n_rep is not None else 0,
        "replication_label": rep_label,
        "vs_close":          vs_close,
        "dm_p":              dm_p,
        "delta":             delta,        # probability delta (Brier), NOT $
        "significant":       significant,
        "n_new":             raw.get("n_new"),
        "reasons":           list(raw.get("reasons", [])),
        "units":             "probability",
        "edge_claimed":      False,
        "note":              str(raw.get("note", _HONEST_NOTE)),
    }


def _assert_no_banned_keys(obj: Any) -> None:
    """Raise ValueError if a banned key ($/roi/pnl/profit) appears in obj."""
    if isinstance(obj, dict):
        for k in obj:
            if str(k).lower() in _BANNED_KEYS:
                raise ValueError("Banned key %r in response" % k)
            _assert_no_banned_keys(obj[k])
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _assert_no_banned_keys(item)


@router.get("/api/improve/clv-corpus")
def clv_corpus_candidates(
    limit: int = Query(default=100, ge=1, le=1000,
                       description="Max rows to return"),
    name_filter: Optional[str] = Query(default=None,
                                       description="Filter to one candidate name"),
) -> JSONResponse:
    """Per-candidate CLV-delta rows the Models page (SI-06) needs.

    Reads data/cache/improve/proposals.jsonl and annotates each row with:
      * replication_label: REPLICATION_PENDING (n_rep<2) or REPLICATED (n_rep>=2)
      * vs_close: UNPROVEN (all-proxy / no beat / not upgraded) or stored value
      * edge_claimed: false (always)
      * units: probability (never $)

    Missing proposals file -> status=unavailable, never green.
    INSUFFICIENT_DATA when the file exists but has no candidate rows.
    Never raises; any unexpected error returns unavailable.
    """
    enabled = _pipeline_enabled()

    try:
        if not _PROPOSALS_PATH.exists():
            # Honest unavailable: file absent is not a SHIP, never green.
            return JSONResponse({
                "status":       "unavailable",
                "candidates":   [],
                "n_total":      0,
                "enabled":      enabled,
                "edge_claimed": False,
                "honest_note":  _HONEST_NOTE,
                "reason":       "proposals file absent; no candidate data",
            })

        raw_rows = _read_proposals(_PROPOSALS_PATH)

        # Filter to candidate name if requested.
        if name_filter:
            raw_rows = [r for r in raw_rows
                        if str(r.get("name", "")).lower() == name_filter.lower()]

        # Keep only the last `limit` rows (chronological order is append-only).
        raw_rows = raw_rows[-limit:]

        if not raw_rows:
            return JSONResponse({
                "status":       "INSUFFICIENT_DATA",
                "candidates":   [],
                "n_total":      0,
                "enabled":      enabled,
                "edge_claimed": False,
                "honest_note":  _HONEST_NOTE,
                "reason":       "proposals file present but no candidate rows found",
            })

        candidates = [_build_candidate_row(r) for r in raw_rows]

        # Safety: strip banned keys from the full response before emitting.
        response: Dict[str, Any] = {
            "status":       "ok",
            "candidates":   candidates,
            "n_total":      len(candidates),
            "enabled":      enabled,
            "edge_claimed": False,
            "honest_note":  _HONEST_NOTE,
        }
        _assert_no_banned_keys(response)
        return JSONResponse(response)

    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> unavailable
        logger.debug("clv_corpus_routes: unexpected error: %s", exc)
        return JSONResponse({
            "status":       "unavailable",
            "candidates":   [],
            "n_total":      0,
            "enabled":      enabled,
            "edge_claimed": False,
            "honest_note":  _HONEST_NOTE,
            "reason":       "unexpected error; proposals unavailable",
        })


__all__ = ["router"]
