"""predict_service.frontend.improve_ledger_routes -- GET /api/improve/ledger.

Exposes the self-improve loop's per-cycle Brier/ECE/BSS metrics as an API
endpoint the Models page and BssDeltaChart component read.

Response adds per_market [{market,brier,ece,delta,status}] from
improve_ledger_segmented.jsonl, improvement_trend list from
improvement_trend.compute_trends, and n_promoted (SHIP count); when
n_promoted==0 honest_note says 'ratchet has not promoted a version yet'.

INVARIANTS: read-only; no $ / pnl / roi field; <=300 LOC; ASCII only;
never raises to caller; INSUFFICIENT_DATA surfaced verbatim (never green).
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
    raise ImportError("improve_ledger_routes requires fastapi.") from exc

logger = logging.getLogger(__name__)

router = APIRouter()

_REPO = pathlib.Path(__file__).resolve().parents[2]
_LEDGER_PATH = _REPO / "data" / "frontend" / "improve_ledger.jsonl"
_SEGMENTED_LEDGER_PATH = _REPO / "data" / "frontend" / "improve_ledger_segmented.jsonl"
_HONEST_NOTE = (
    "Calibration metrics only -- no $ / edge / profit claim. "
    "INSUFFICIENT_DATA is honest when too few real games have settled. "
    "SHIP means the Platt recalibration passed all 5 gates; n_shipped "
    "counts only real promotions."
)
_RATCHET_NOT_PROMOTED = "ratchet has not promoted a version yet"
_KNOWN_SPORTS = ("nba", "mlb", "soccer", "tennis")


def _pipeline_enabled() -> bool:
    """True only when the human-managed PIPELINE_ENABLED sentinel exists."""
    try:
        from scripts.platformkit.improve.pipeline_flag import (  # noqa: PLC0415
            pipeline_enabled,
        )
        return bool(pipeline_enabled())
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_ledger_routes: pipeline_flag import failed: %s", exc)
        return False


def _read_ledger(limit: int = 50,
                 sport_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read up to `limit` rows per sport from improve_ledger.jsonl.

    Returns rows in chronological order. Missing/torn file -> []. Never raises.
    """
    if not _LEDGER_PATH.exists():
        return []
    raw: List[Dict[str, Any]] = []
    try:
        text = _LEDGER_PATH.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            raw.append(obj)
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_ledger_routes: read error: %s", exc)
        return []

    # Group by sport, keep last `limit` rows per sport.
    by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for row in raw:
        sp = str(row.get("sport", "")).lower()
        if sport_filter and sp != sport_filter.lower():
            continue
        by_sport.setdefault(sp, []).append(row)

    out: List[Dict[str, Any]] = []
    for sp, rows in by_sport.items():
        tail = rows[-limit:]  # keep last `limit` in chrono order
        for cycle_idx, r in enumerate(tail):
            readout = r.get("readout") or {}
            out.append({
                "ts":           r.get("ts"),
                "sport":        sp,
                "cycle":        cycle_idx,
                "verdict":      r.get("verdict", "UNKNOWN"),
                "n_settled":    r.get("n_settled"),
                "brier":        readout.get("raw_brier"),
                "ece":          readout.get("raw_ece"),
                "bss_vs_close": readout.get("bss_vs_close"),
                "note":         r.get("note", ""),
            })

    # Sort chronologically (ts is ISO so lexicographic order works).
    out.sort(key=lambda d: (str(d.get("ts") or ""), str(d.get("sport") or "")))
    return out


def _summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-sport summary: n_cycles, n_shipped, latest_brier, latest_bss."""
    summary: Dict[str, Any] = {}
    for sp in {r["sport"] for r in rows}:
        sp_rows = [r for r in rows if r["sport"] == sp]
        n_shipped = sum(1 for r in sp_rows if r.get("verdict") == "SHIP")
        last = sp_rows[-1] if sp_rows else {}
        summary[sp] = {
            "n_cycles":     len(sp_rows),
            "n_shipped":    n_shipped,
            "latest_brier": last.get("brier"),
            "latest_bss":   last.get("bss_vs_close"),
        }
    return summary


def _read_segmented_jsonl(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Read all rows from the segmented ledger JSONL. Never raises."""
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
                if isinstance(obj, dict):
                    rows.append(obj)
            except json.JSONDecodeError:
                continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_ledger_routes: segmented read error: %s", exc)
    return rows


def _build_per_market(seg_path: pathlib.Path) -> List[Dict[str, Any]]:
    """Build per_market breakdown from the segmented ledger.

    For each market found in improve_ledger_segmented.jsonl, return the latest
    brier/ece/delta (delta = brier vs previous row; null when only 1 row exists).
    Status is the latest row's status (INSUFFICIENT_DATA / SHIP / HOLD / REJECT).
    Never fabricates a readout for INSUFFICIENT_DATA rows.
    """
    all_rows = _read_segmented_jsonl(seg_path)
    # Group chronologically by market (JSONL is append-only).
    by_mkt: Dict[str, List[Dict[str, Any]]] = {}
    for row in all_rows:
        mkt = str(row.get("market", "")).lower()
        if mkt:
            by_mkt.setdefault(mkt, []).append(row)

    out: List[Dict[str, Any]] = []
    for mkt in sorted(by_mkt):
        mkt_rows = by_mkt[mkt]
        latest = mkt_rows[-1]
        readout = latest.get("readout") or {}
        brier = readout.get("raw_brier")
        ece = readout.get("raw_ece")
        # Compute delta vs previous row with a readout.
        prev_brier: Optional[float] = None
        for prev in reversed(mkt_rows[:-1]):
            pb = (prev.get("readout") or {}).get("raw_brier")
            if pb is not None:
                try:
                    prev_brier = float(pb)
                except (TypeError, ValueError):
                    pass
                break
        delta: Optional[float] = None
        if brier is not None and prev_brier is not None:
            try:
                delta = round(float(brier) - prev_brier, 6)
            except (TypeError, ValueError):
                pass
        out.append({
            "market": mkt,
            "brier":  brier,
            "ece":    ece,
            "delta":  delta,
            "status": str(latest.get("status", "UNKNOWN")),
        })
    return out


def _build_improvement_trend(seg_path: pathlib.Path) -> List[Dict[str, Any]]:
    """Call improvement_trend.compute_trends and reproject to a compact list.

    Each entry: {market, n_data_cycles, monotone_improving, regression_flag, status}.
    Returns [] on import/IO error. Never raises.
    """
    try:
        from scripts.platformkit.improve.improvement_trend import (  # noqa: PLC0415
            compute_trends,
        )
        raw = compute_trends(ledger_path=seg_path) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("improve_ledger_routes: improvement_trend error: %s", exc)
        return []

    out: List[Dict[str, Any]] = []
    for mkt, entry in sorted(raw.items()):
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "INSUFFICIENT_DATA"))
        item: Dict[str, Any] = {
            "market":             mkt,
            "n_data_cycles":      entry.get("n_data_cycles", 0),
            "monotone_improving": entry.get("monotone_improving") if status == "ok" else None,
            "regression_flag":    entry.get("regression_flag") if status == "ok" else None,
            "status":             status,
        }
        out.append(item)
    return out


def _count_promoted(seg_path: pathlib.Path) -> int:
    """Count SHIP rows in the segmented ledger (actual promoted versions). Never raises."""
    rows = _read_segmented_jsonl(seg_path)
    return sum(1 for r in rows if str(r.get("status", "")).upper() == "SHIP")


@router.get("/api/improve/ledger")
def improve_ledger(
    sport: Optional[str] = Query(default=None, description="Filter to one sport"),
    limit: int = Query(default=50, ge=1, le=500,
                       description="Max rows per sport to return"),
) -> JSONResponse:
    """Brier/ECE/BSS per sport per cycle from the self-improve loop ledger.

    The Models page (W9) uses this to render the BssDeltaChart component.
    An honest INSUFFICIENT_DATA verdict is passed through verbatim -- the UI
    must render it as 'cold start / not enough games', never as a SHIP.
    No $ key is ever emitted. `enabled` reflects the PIPELINE_ENABLED sentinel.
    per_market, improvement_trend, and n_promoted join from the segmented ledger.
    When n_promoted==0 the honest_note field says 'ratchet has not promoted a
    version yet' -- no fabricated convergence.
    """
    rows = _read_ledger(limit=limit, sport_filter=sport)
    enabled = _pipeline_enabled()
    by_sport = _summarise(rows)

    per_market = _build_per_market(_SEGMENTED_LEDGER_PATH)
    improvement_trend = _build_improvement_trend(_SEGMENTED_LEDGER_PATH)
    n_promoted = _count_promoted(_SEGMENTED_LEDGER_PATH)

    honest_note = _HONEST_NOTE
    if n_promoted == 0:
        honest_note = _RATCHET_NOT_PROMOTED + ". " + _HONEST_NOTE

    status = "ok" if rows or enabled else "unavailable"
    return JSONResponse({
        "status":            status,
        "rows":              rows,
        "by_sport":          by_sport,
        "per_market":        per_market,
        "improvement_trend": improvement_trend,
        "n_promoted":        n_promoted,
        "enabled":           enabled,
        "edge_claimed":      False,
        "honest_note":       honest_note,
    })


__all__ = ["router"]
