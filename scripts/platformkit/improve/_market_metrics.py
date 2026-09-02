"""scripts.platformkit.improve._market_metrics -- metric helpers for per_market_ledger.

Split from per_market_ledger.py to keep that module under 300 LOC.
Private module -- import via per_market_ledger public API only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from scripts.platformkit.eval_gate import scoring as S

BRIER_IMPROVE_TOL: float = 0.005
BRIER_REGRESS_TOL: float = 0.005


def _valid_scored(r: Dict[str, Any]) -> bool:
    """Return True only when a row is safe to include in Brier/ECE computation.

    Requires:
    - p_raw present, finite, and in [0.0, 1.0]
    - y present, finite, and exactly 0.0 or 1.0 (void/None rows are excluded)
    """
    try:
        p = float(r["p_raw"])
        y = float(r["y"])
    except (TypeError, ValueError, KeyError):
        return False
    if not (math.isfinite(p) and math.isfinite(y)):
        return False
    if not (0.0 <= p <= 1.0):
        return False
    if y not in (0.0, 1.0):
        return False
    return True


def _valid_close(r: Dict[str, Any]) -> bool:
    """Return True when p_close is present, finite, and in [0.0, 1.0]."""
    try:
        pc = float(r["p_close"])
    except (TypeError, ValueError, KeyError):
        return False
    return math.isfinite(pc) and 0.0 <= pc <= 1.0


def readout_for_segment(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute honest Brier/ECE/BSS over a segment's settled rows.

    Void or unscored rows (y=None, p_raw=NaN/None/out-of-range) are silently
    excluded before any computation.  n reflects valid scored rows only.
    """
    valid = [r for r in rows if _valid_scored(r)]
    n = len(valid)
    if n == 0:
        return {"n": 0}
    p = np.array([float(r["p_raw"]) for r in valid], dtype=float)
    y = np.array([float(r["y"]) for r in valid], dtype=float)
    out: Dict[str, Any] = {
        "n": n,
        "raw_brier": round(float(S.brier(p, y)), 6),
        "raw_ece": round(float(S.ece(p, y)), 6),
        "base_rate": round(float(y.mean()), 6),
        "sharpness": round(float(S.sharpness(p)), 6),
    }
    with_close = [r for r in valid if _valid_close(r)]
    if with_close:
        pc = np.array([float(r["p_close"]) for r in with_close], dtype=float)
        pm = np.array([float(r["p_raw"]) for r in with_close], dtype=float)
        yc = np.array([float(r["y"]) for r in with_close], dtype=float)
        out["n_with_close"] = len(with_close)
        out["bss_vs_close"] = round(float(S.brier_skill_score(pm, pc, yc)), 6)
        out["pct_beat_close"] = round(100.0 * float(np.mean(pm > pc)), 4)
    else:
        out["n_with_close"] = 0
        out["bss_vs_close"] = None
        out["pct_beat_close"] = None
    return out


def verdict_from_readout(readout: Dict[str, Any]) -> str:
    """Derive SHIP/HOLD/REJECT from the readout metrics.

    SHIP  -> bss_vs_close > BRIER_IMPROVE_TOL
    REJECT-> bss_vs_close < -BRIER_REGRESS_TOL
    HOLD  -> otherwise (no meaningful gap vs close, or no close price)
    """
    bss = readout.get("bss_vs_close")
    if bss is None:
        return "HOLD"
    if bss > BRIER_IMPROVE_TOL:
        return "SHIP"
    if bss < -BRIER_REGRESS_TOL:
        return "REJECT"
    return "HOLD"
