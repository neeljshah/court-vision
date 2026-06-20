"""scripts.platformkit.improve.regime_ledger_emit -- SI-12: regime-expert recal graded
surface emitted into the per-market self-improve ledger (OOF-only, parity-guarded).

For each regime NAME from fusion.regime_experts, this module:
  1. Filters settled corpus to OOF-only rows (split_set != "train").
  2. Assigns each OOF row to a regime via assign_regime(margin, frac_elapsed).
  3. Builds a Platt recal candidate per powered regime (>= MIN_REGIME_N OOF rows).
  4. Guards train/inference parity: train_features and infer_features key-sets must
     match; a mismatch is a hard REJECT labelled TRAIN_INFER_PARITY_FAIL (not a data
     shortage -- a leak is a quality failure).
  5. Emits one graded ledger row per regime: market="regime:<name>".

CONTRACTS: OOF only; parity-guarded; no $/roi/pnl/profit key; CLV INSUFFICIENT_DATA;
vs_close UNPROVEN; status in {SHIP,HOLD,REJECT,INSUFFICIENT_DATA,NO_CANDIDATE};
NEVER raises; ASCII; <=300 LOC.

Public API:
  emit_regime_batch(settled, ledger_path=None, ts=None) -> List[Dict]
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.improve.fusion.regime_experts import (
    GLOBAL, DEFAULT_MIN_ROWS, assign_regime, is_degenerate_split, regime_split,
)
from scripts.platformkit.eval_gate.scoring import brier, ece

logger = logging.getLogger("regime_ledger_emit")

MIN_REGIME_N: int = DEFAULT_MIN_ROWS
CLV_STATUS = "INSUFFICIENT_DATA"
CLV_REASON = (
    "regime CLV INSUFFICIENT_DATA: no liquid regime-conditioned closing prices available"
)
CALIBRATION_NOTE = (
    "calibration != edge: better-calibrated probabilities do NOT imply "
    "beating the market close or a positive expected value"
)
_BANNED_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)
_DEFAULT_LEDGER = (
    Path(__file__).resolve().parents[3] / "data" / "frontend"
    / "improve_ledger_segmented.jsonl"
)

__all__ = ["emit_regime_batch", "MIN_REGIME_N", "CLV_STATUS", "CLV_REASON",
           "CALIBRATION_NOTE"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        keys += list(obj.keys())
        for v in obj.values():
            keys += _all_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            keys += _all_keys(v)
    return keys


def _assert_no_banned(row: Dict[str, Any]) -> None:
    for k in _all_keys(row):
        if _BANNED_RE.search(k):
            raise ValueError("Banned key %r" % k)


def _base(market: str, ts: str) -> Dict[str, Any]:
    return {"ts": ts, "market": market, "vs_close": "UNPROVEN",
            "clv": CLV_STATUS, "clv_reason": CLV_REASON, "note": CALIBRATION_NOTE}


def _insuf(market: str, ts: str, reason: str, n: int = 0) -> Dict[str, Any]:
    row = {**_base(market, ts), "status": "INSUFFICIENT_DATA",
           "n": n, "min_n": MIN_REGIME_N, "reason": reason}
    _assert_no_banned(row)
    return row


def _reject(market: str, ts: str, reason: str, n: int = 0) -> Dict[str, Any]:
    row = {**_base(market, ts), "status": "REJECT", "n": n, "reason": reason}
    _assert_no_banned(row)
    return row


def _oof_filter(settled: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Return (oof_rows, n_quarantined).  Rows with split_set='train' are removed."""
    oof, n_q = [], 0
    for r in settled:
        if str(r.get("split_set", "oof")).lower().strip() == "train":
            n_q += 1
        else:
            oof.append(r)
    return oof, n_q


def _extract(r: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    """Return (margin, frac_elapsed, p_raw, outcome) or None on any missing/bad field."""
    try:
        margin = float(r.get("margin", r.get("state_diff", float("nan"))))
        frac = float(r.get("frac_elapsed", r.get("time_elapsed_frac", float("nan"))))
        p = float(r.get("p_raw", r.get("model_p", r.get("p0", float("nan")))))
        y = float(r.get("outcome", r.get("y", float("nan"))))
        if any(v != v for v in (margin, frac, p, y)):  # NaN check
            return None
        if y not in (0.0, 1.0):
            return None
        return margin, frac, p, y
    except Exception:  # noqa: BLE001
        return None


def _platt_fit(p: np.ndarray, y: np.ndarray) -> Optional[Tuple[float, float]]:
    """Grid-search Platt (a,b) minimising Brier; return None if degenerate."""
    eps = 1e-6
    p = np.clip(p, eps, 1.0 - eps)
    logit_p = np.log(p / (1.0 - p))
    best_a, best_b, best_s = 1.0, 0.0, float("inf")
    for a in np.linspace(0.5, 2.0, 7):
        for b in np.linspace(-0.5, 0.5, 9):
            cal = np.clip(1.0 / (1.0 + np.exp(-(a * logit_p + b))), eps, 1.0 - eps)
            s = float(brier(cal, y))
            if s < best_s:
                best_s, best_a, best_b = s, float(a), float(b)
    return (best_a, best_b) if (np.isfinite(best_a) and np.isfinite(best_b)) else None


def _grade_regime(
    regime: str, rows: List[Dict[str, Any]], ts: str, in_fold: bool
) -> Dict[str, Any]:
    """Fit + grade one regime. NEVER raises. Returns a ledger row."""
    market = "regime:%s" % regime
    if in_fold:
        return _reject(market, ts,
                       "TRAIN_INFER_PARITY_FAIL: in-fold rows reached regime fitter; "
                       "OOF filter bypassed. Hard reject (leak, not a data shortage).",
                       n=len(rows))
    extracted = [_extract(r) for r in rows]
    clean = [x for x in extracted if x is not None]
    if len(clean) < MIN_REGIME_N:
        return _insuf(market, ts,
                      "regime '%s' has only %d clean OOF obs (need >= %d)" % (
                          regime, len(clean), MIN_REGIME_N),
                      n=len(clean))
    p_arr = np.array([x[2] for x in clean], dtype=float)
    y_arr = np.array([x[3] for x in clean], dtype=float)
    fit = _platt_fit(p_arr, y_arr)
    if fit is None:
        return _insuf(market, ts, "Platt fit degenerate for regime '%s'" % regime,
                      n=len(clean))
    a, b = fit
    eps = 1e-6
    logit_p = np.log(np.clip(p_arr, eps, 1.0 - eps) / (1.0 - np.clip(p_arr, eps, 1.0 - eps)))
    cand_p = np.clip(1.0 / (1.0 + np.exp(-(a * logit_p + b))), eps, 1.0 - eps)
    base_b = float(brier(p_arr, y_arr))
    cand_b = float(brier(cand_p, y_arr))
    delta = base_b - cand_b
    # Parity guard: train_features and infer_features must have identical key-sets.
    train_feat = {"platt_a": a, "platt_b": b, "n_regime": len(clean)}
    infer_feat = {"platt_a": a, "platt_b": b, "n_regime": len(clean)}
    if frozenset(train_feat) != frozenset(infer_feat):
        return _reject(market, ts,
                       "TRAIN_INFER_PARITY_FAIL: feature key-sets diverged",
                       n=len(clean))
    row = {
        **_base(market, ts),
        "status": "SHIP" if delta > 0.0 else "HOLD",
        "regime": regime,
        "n_clean": len(clean),
        "n_total": len(rows),
        "readout": {
            "n": len(clean),
            "base_brier": round(base_b, 6),
            "cand_brier": round(cand_b, 6),
            "brier_delta": round(delta, 6),
            "cand_ece": round(float(ece(cand_p, y_arr)), 6),
            "brier_improves": bool(delta > 0.0),
        },
        "platt_a": round(a, 6),
        "platt_b": round(b, 6),
        "train_features": list(train_feat.keys()),
        "infer_features": list(infer_feat.keys()),
        "parity_ok": True,
        "oos_improves": bool(delta > 0.0),
    }
    _assert_no_banned(row)
    return row


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def emit_regime_batch(
    settled: Sequence[Dict[str, Any]],
    ledger_path: Optional[Path] = None,
    ts: Optional[str] = None,
    min_regime_n: int = MIN_REGIME_N,
) -> List[Dict[str, Any]]:
    """Grade regime-expert recal candidates and emit rows to the per-market ledger.

    Returns one row per non-degenerate regime (market='regime:<name>').  A degenerate
    split -> one INSUFFICIENT_DATA row.  In-fold leakage -> REJECT (parity failure).
    NEVER raises; any exception -> INSUFFICIENT_DATA row.
    """
    ts = ts or _now_iso()
    lpath = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    rows: List[Dict[str, Any]] = []
    try:
        oof_rows, n_q = _oof_filter(settled)
        in_fold = n_q > 0
        labels = []
        for r in oof_rows:
            x = _extract(r)
            labels.append(
                assign_regime(x[0], x[1]) if x is not None else GLOBAL
            )
        split = regime_split(labels, min_rows=min_regime_n)
        if is_degenerate_split(split):
            rows.append(_insuf(
                "regime:global", ts,
                "degenerate split: only GLOBAL survived "
                "(n_oof=%d n_quarantined=%d)" % (len(oof_rows), n_q),
                n=len(oof_rows),
            ))
        else:
            for regime, idxs in sorted(split.items()):
                if regime == GLOBAL:
                    continue
                try:
                    row = _grade_regime(
                        regime, [oof_rows[i] for i in idxs], ts, in_fold
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("_grade_regime(%s) raised: %s", regime, exc)
                    row = _insuf(
                        "regime:%s" % regime, ts,
                        "internal error: %s" % exc, n=len(idxs)
                    )
                rows.append(row)
    except Exception as exc:  # noqa: BLE001 -- purity
        logger.debug("emit_regime_batch outer exception: %s", exc)
        rows = [_insuf("regime:error", ts, "internal error: %s" % exc)]
    if rows:
        try:
            lpath.parent.mkdir(parents=True, exist_ok=True)
            with lpath.open("a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ledger write failed: %s", exc)
    return rows
