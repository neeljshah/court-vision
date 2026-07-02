"""scripts.platformkit.improve.ingame_segment_emit -- in-game segment recal SHIP-readout
emitter (SI-05).  margin x period x time_bucket -> graded ledger rows.

Each segment -> one row with market="ingame:<seg>". CLV is now DATA-DRIVEN: graded from
the sport's captured in-play series via ingame_clv_grade.grade_sport (honest BEAT/BEHIND/
MATCH/INSUFFICIENT_DATA, market-majority guarded), falling back to INSUFFICIENT_DATA when
no liquid in-play data exists. No $/roi/pnl/profit key. NEVER raises. ASCII; <=300 LOC.

Public API:
  emit_ingame_segments(sport, segments, ledger_path=None, ts=None, clv_summary=None) -> List
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.improve.ingame_recal_segments import (
    build_ingame_segment_candidate,
    _MARGIN_THRESHOLDS,
    _PERIOD_THRESHOLDS,
    _TIME_THRESHOLDS,
)
from scripts.platformkit.eval_gate.scoring import brier, ece

logger = logging.getLogger("ingame_segment_emit")

# Default when a sport has no captured in-play data to grade against (e.g. NBA offseason).
# When data DOES exist, CLV is graded data-driven via _resolve_sport_clv below.
CLV_STATUS = "INSUFFICIENT_DATA"
CLV_REASON = (
    "in-game CLV INSUFFICIENT_DATA: no captured liquid in-play series to grade "
    "against for this sport (e.g. offseason / no live games)"
)

# Minimum clean obs to produce a Brier readout (mirrors ingame_recal_segments._MIN_OBS).
_MIN_OBS = 8

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

CALIBRATION_NOTE = (
    "calibration != edge: better-calibrated probabilities do NOT imply "
    "beating the market close or a positive expected value"
)

_DEFAULT_LEDGER = (
    Path(__file__).resolve().parents[3]
    / "data" / "frontend" / "improve_ledger_segmented.jsonl"
)

_VALID_MARGINS = frozenset(_MARGIN_THRESHOLDS)
_VALID_PERIODS = frozenset(_PERIOD_THRESHOLDS)
_VALID_TIMES = frozenset(_TIME_THRESHOLDS)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_sport_clv(
    sport: str, summary: Optional[Dict[str, Any]] = None
) -> Tuple[str, str]:
    """Data-driven (clv_status, clv_reason) via ingame_clv_grade. NEVER raises."""
    try:
        from scripts.platformkit.improve.ingame_clv_grade import resolve_clv_status
        return resolve_clv_status(sport, summary)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_resolve_sport_clv(%s) failed: %s", sport, exc)
        return CLV_STATUS, CLV_REASON


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(row: Dict[str, Any]) -> None:
    for k in _all_keys(row):
        if _BANNED_KEY_RE.search(k):
            raise ValueError("Banned key %r violates no-dollar-field contract." % k)


def _seg_label(margin_bucket: str, period_bucket: str, time_bucket: str) -> str:
    return "margin:%s|period:%s|time:%s" % (margin_bucket, period_bucket, time_bucket)


def _validate_segment(mb: str, pb: str, tb: str) -> Optional[str]:
    """Return error string if any bucket label is invalid, else None."""
    if mb not in _VALID_MARGINS:
        return "invalid margin_bucket %r; valid: %s" % (mb, sorted(_VALID_MARGINS))
    if pb not in _VALID_PERIODS:
        return "invalid period_bucket %r; valid: %s" % (pb, sorted(_VALID_PERIODS))
    if tb not in _VALID_TIMES:
        return "invalid time_bucket %r; valid: %s" % (tb, sorted(_VALID_TIMES))
    return None


def _build_insufficient_row(
    market: str, reason: str, ts: str, n: int = 0,
    clv: str = CLV_STATUS, clv_reason: str = CLV_REASON,
) -> Dict[str, Any]:
    return {
        "ts": ts,
        "market": market,
        "status": "INSUFFICIENT_DATA",
        "n": n,
        "clv": clv,
        "clv_reason": clv_reason,
        "reason": reason,
        "note": CALIBRATION_NOTE,
        "vs_close": "UNPROVEN" if clv in (CLV_STATUS, "MATCH") else clv,
    }


def _brier_readout(
    base_preds: List[float], cand_preds: List[float], y: List[float]
) -> Dict[str, Any]:
    """Compute honest Brier + ECE from candidate arrays. NEVER raises."""
    try:
        bp = np.clip(np.asarray(base_preds, dtype=float), 1e-6, 1.0 - 1e-6)
        cp = np.clip(np.asarray(cand_preds, dtype=float), 1e-6, 1.0 - 1e-6)
        yy = np.asarray(y, dtype=float)
        base_b = float(brier(bp, yy))
        cand_b = float(brier(cp, yy))
        delta = base_b - cand_b  # positive = candidate better
        return {
            "n": int(len(yy)),
            "base_brier": round(base_b, 6),
            "cand_brier": round(cand_b, 6),
            "brier_delta": round(delta, 6),
            "cand_ece": round(float(ece(cp, yy)), 6),
            "brier_improves": bool(delta > 0.0),
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("_brier_readout failed: %s", exc)
        return {"n": 0, "error": "readout_failed"}


def _grade_segment(
    sport: str, margin_bucket: str, period_bucket: str, time_bucket: str,
    ts: str, candidate_name: str,
    clv_status: str = CLV_STATUS, clv_reason: str = CLV_REASON,
) -> Dict[str, Any]:
    """Build + grade one segment candidate. NEVER raises; returns a ledger row.

    clv_status/clv_reason carry the sport-level data-driven in-play CLV verdict.
    """
    seg = _seg_label(margin_bucket, period_bucket, time_bucket)
    market = "ingame:%s" % seg

    err = _validate_segment(margin_bucket, period_bucket, time_bucket)
    if err:
        return _build_insufficient_row(
            market, "invalid segment: %s" % err, ts,
            clv=clv_status, clv_reason=clv_reason)

    try:
        cand = build_ingame_segment_candidate(
            name=candidate_name, sport=sport,
            margin_bucket=margin_bucket, period_bucket=period_bucket,
            time_bucket=time_bucket,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_segment_emit(%s/%s): build failed: %s", sport, seg, exc)
        cand = None

    if cand is None:
        return _build_insufficient_row(
            market,
            "NO_CANDIDATE for '%s' (sentinel absent, under-N, feed degraded, degenerate)" % seg,
            ts, clv=clv_status, clv_reason=clv_reason,
        )

    y = cand.get("y", [])
    if len(y) < _MIN_OBS:
        return _build_insufficient_row(
            market,
            "segment '%s' has only %d clean obs (need >= %d)" % (seg, len(y), _MIN_OBS),
            ts, n=len(y), clv=clv_status, clv_reason=clv_reason,
        )

    readout = _brier_readout(
        list(cand.get("base_preds", [])),
        list(cand.get("cand_preds", [])),
        list(y),
    )
    status = "SHIP" if readout.get("brier_improves") else "HOLD"
    payload = cand.get("payload", {})
    return {
        "ts": ts,
        "market": market,
        "status": status,
        "n_clean": cand.get("n_clean", len(y)),
        "n_quarantined": cand.get("n_quarantined", 0),
        "segment": seg,
        "sport": str(sport),
        "readout": readout,
        "platt_a": payload.get("a"),
        "platt_b": payload.get("b"),
        "clv": clv_status,
        "clv_reason": clv_reason,
        "oos_improves": bool(cand.get("oos_improves", False)),
        "vs_close": "UNPROVEN" if clv_status in (CLV_STATUS, "MATCH") else clv_status,
        "note": CALIBRATION_NOTE,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def emit_ingame_segments(
    sport: str,
    segments: Sequence[Tuple[str, str, str]],
    ledger_path: Optional[Path] = None,
    ts: Optional[str] = None,
    clv_summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Grade a batch of in-game segments and append rows to the per-market ledger.

    segments: (margin_bucket, period_bucket, time_bucket) triples
      (margin: close|mid|blowout, period: early|late, time: ample|scarce).
    clv_summary: optional precomputed grade_sport() result (tests inject for hermetic
      runs); when None the sport's captured in-play series are graded once here.

    Returns one row per segment (market="ingame:<seg>"). NEVER raises. CLV is
    DATA-DRIVEN (INSUFFICIENT_DATA when no in-play data). No $/roi keys.
    """
    ts = ts or _now_iso()
    lpath = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    rows: List[Dict[str, Any]] = []
    clv_status, clv_reason = _resolve_sport_clv(sport, clv_summary)

    for seg_triple in segments:
        try:
            margin_bucket, period_bucket, time_bucket = seg_triple
        except (TypeError, ValueError) as exc:
            logger.debug("ingame_segment_emit: bad triple %r: %s", seg_triple, exc)
            rows.append(_build_insufficient_row(
                "ingame:invalid",
                "malformed segment triple: %r" % (seg_triple,),
                ts, clv=clv_status, clv_reason=clv_reason,
            ))
            continue

        name = "ingame_seg_%s_%s_%s_%s" % (
            str(sport).lower(), margin_bucket, period_bucket, time_bucket
        )
        try:
            row = _grade_segment(sport, margin_bucket, period_bucket, time_bucket, ts, name,
                                 clv_status=clv_status, clv_reason=clv_reason)
        except Exception as exc:  # noqa: BLE001
            seg = _seg_label(margin_bucket, period_bucket, time_bucket)
            logger.debug("ingame_segment_emit: _grade_segment(%s) failed: %s", seg, exc)
            row = _build_insufficient_row(
                "ingame:%s" % seg, "internal error: %s" % exc, ts,
                clv=clv_status, clv_reason=clv_reason,
            )

        _assert_no_banned_keys(row)
        rows.append(row)

    if rows:
        try:
            lpath.parent.mkdir(parents=True, exist_ok=True)
            with lpath.open("a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingame_segment_emit: ledger write failed: %s", exc)

    return rows


__all__ = [
    "emit_ingame_segments",
    "CLV_STATUS",
    "CLV_REASON",
    "CALIBRATION_NOTE",
]
