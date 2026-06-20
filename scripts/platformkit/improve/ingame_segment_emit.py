"""scripts.platformkit.improve.ingame_segment_emit -- in-game segment recal SHIP-readout
emitter (SI-05).  margin x period x time_bucket -> graded ledger rows.

Each segment -> one row with market="ingame:<seg>". CLV always INSUFFICIENT_DATA (no
liquid in-play prices). Under-N -> INSUFFICIENT_DATA. No $/roi/pnl/profit key anywhere.
MF1 kill-switch delegated to build_ingame_segment_candidate. NEVER raises. ASCII; <=300 LOC.

Public API:
  emit_ingame_segments(sport, segments, ledger_path=None, ts=None) -> List[Dict]
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

# In-game CLV is always INSUFFICIENT_DATA -- no liquid in-play closing prices available.
CLV_STATUS = "INSUFFICIENT_DATA"
CLV_REASON = (
    "in-game CLV INSUFFICIENT_DATA: live in-play closing prices unavailable "
    "(NBA offseason; no liquid in-play market to grade against)"
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


def _build_insufficient_row(market: str, reason: str, ts: str, n: int = 0) -> Dict[str, Any]:
    return {
        "ts": ts,
        "market": market,
        "status": "INSUFFICIENT_DATA",
        "n": n,
        "clv": CLV_STATUS,
        "clv_reason": CLV_REASON,
        "reason": reason,
        "note": CALIBRATION_NOTE,
        "vs_close": "UNPROVEN",
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
) -> Dict[str, Any]:
    """Build + grade one segment candidate. NEVER raises; returns a ledger row."""
    seg = _seg_label(margin_bucket, period_bucket, time_bucket)
    market = "ingame:%s" % seg

    err = _validate_segment(margin_bucket, period_bucket, time_bucket)
    if err:
        return _build_insufficient_row(market, "invalid segment: %s" % err, ts)

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
            ts,
        )

    y = cand.get("y", [])
    if len(y) < _MIN_OBS:
        return _build_insufficient_row(
            market,
            "segment '%s' has only %d clean obs (need >= %d)" % (seg, len(y), _MIN_OBS),
            ts, n=len(y),
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
        "clv": CLV_STATUS,
        "clv_reason": CLV_REASON,
        "oos_improves": bool(cand.get("oos_improves", False)),
        "vs_close": "UNPROVEN",
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
) -> List[Dict[str, Any]]:
    """Grade a batch of in-game segments and append rows to the per-market ledger.

    Parameters
    ----------
    sport: Sport key (e.g. "nba").
    segments: Sequence of (margin_bucket, period_bucket, time_bucket) triples.
      margin: close|mid|blowout   period: early|late   time: ample|scarce
    ledger_path: Override ledger path (tests use tmp_path).
    ts: ISO timestamp override (default: now UTC).

    Returns one ledger row dict per segment (market="ingame:<seg>"). NEVER raises.
    CLV is always INSUFFICIENT_DATA. Under-N -> INSUFFICIENT_DATA. No $/roi keys.
    """
    ts = ts or _now_iso()
    lpath = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    rows: List[Dict[str, Any]] = []

    for seg_triple in segments:
        try:
            margin_bucket, period_bucket, time_bucket = seg_triple
        except (TypeError, ValueError) as exc:
            logger.debug("ingame_segment_emit: bad triple %r: %s", seg_triple, exc)
            rows.append(_build_insufficient_row(
                "ingame:invalid",
                "malformed segment triple: %r" % (seg_triple,),
                ts,
            ))
            continue

        name = "ingame_seg_%s_%s_%s_%s" % (
            str(sport).lower(), margin_bucket, period_bucket, time_bucket
        )
        try:
            row = _grade_segment(sport, margin_bucket, period_bucket, time_bucket, ts, name)
        except Exception as exc:  # noqa: BLE001
            seg = _seg_label(margin_bucket, period_bucket, time_bucket)
            logger.debug("ingame_segment_emit: _grade_segment(%s) failed: %s", seg, exc)
            row = _build_insufficient_row(
                "ingame:%s" % seg, "internal error: %s" % exc, ts
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
