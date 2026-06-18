"""domains.soccer.prop_recal -- per-stat ISOTONIC recalibration for WC player props.

RELIABILITY IMPROVEMENT -- NOT A $-EDGE CLAIM. Calibration != edge.
The leak-free backtest shows the prop model is UNDER-confident on rare events
(predicts ~2.6% where reality is ~5.8% in the low bin) and over-confident
mid-range. We fit a per-stat isotonic map model_p -> empirical freq so that
P(over) is better calibrated. Better-calibrated probabilities do NOT imply
beating the market.

ALGORITHM: isotonic regression via the Pool-Adjacent-Violators (PAVA)
algorithm in PURE PYTHON (no sklearn required; if sklearn is importable we MAY
use IsotonicRegression with the pure fallback). Monotone non-decreasing: a
higher raw prob maps to a >= calibrated prob (sensible for a ranking model) and
makes no parametric shape assumption -- right for a systematically-biased low
regime. The fitted map is stored as sorted (x_knots, y_knots) and applied by
piecewise-linear interpolation, clamped to [0, 1].

LEAK-FREE PAIRS: we fit on the (p_over, outcome) pairs from
scripts.platformkit.props_eval.backtest_pairs, which runs the SAME walk-forward
leak-free pred-gen loop the calibration readout scores (each match builds its
dist from data strictly before it). MIN_N=150 pairs/stat else the stat is
SKIPPED (identity) -- don't fit noise.

HONESTY: isotonic recal trained on ~24 WC matches is THIN and approximate. It
improves IN-SAMPLE calibration and must be RE-FIT as data grows and validated
OOS before being trusted.

Public functions NEVER raise. ASCII only. No secrets. <=300 LOC.
Per-file test only (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_prop_recal.py -q
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

MIN_N: int = 150  # min (p, outcome) pairs per stat to fit; else identity (skip).
_RECAL_PATH = os.path.join(
    "data", "domains", "soccer", "prop_recal.json")


# ---------------------------------------------------------------------------
# Pure-Python isotonic regression (Pool-Adjacent-Violators)
# ---------------------------------------------------------------------------
def pava(xs: Sequence[float], ys: Sequence[float]
         ) -> Tuple[List[float], List[float]]:
    """Pool-Adjacent-Violators isotonic fit (non-decreasing) for points sorted
    by x. Returns (x_knots, y_knots): each x carries its pooled fitted y, where
    adjacent decreasing blocks are merged into their weighted (here equal-weight)
    mean until the sequence is monotone non-decreasing. Ties in x are pooled
    first. Pure python; never raises on clean numeric input.

    Hand example: x=[.1,.2,.3,.4], y=[0,0,1,1] is already non-decreasing ->
    y_knots == [0,0,1,1]. x=[.1,.2,.3], y=[1,0,0] violates at the first step ->
    blocks [1] and [0] pool to mean 0.5, then [0] -> y_knots ~ [.5,.5,0]? No:
    pooling continues until monotone, giving [1/3,1/3,1/3].
    """
    n = len(xs)
    if n == 0:
        return [], []
    # 1) Pool exact-duplicate x into a single point (mean y) so knots have
    #    unique strictly-increasing x for interpolation.
    order = sorted(range(n), key=lambda i: xs[i])
    ux: List[float] = []
    uy: List[float] = []
    i = 0
    while i < n:
        j = i
        xv = xs[order[i]]
        ssum = 0.0
        cnt = 0
        while j < n and xs[order[j]] == xv:
            ssum += ys[order[j]]
            cnt += 1
            j += 1
        ux.append(float(xv))
        uy.append(ssum / cnt)
        i = j
    # 2) PAVA over the unique-x means. Maintain blocks of (sum, weight) and
    #    merge any block whose mean is below the previous block's mean.
    sums: List[float] = []
    weights: List[float] = []
    edges: List[int] = []  # number of original-unique points in each block
    for k in range(len(ux)):
        sums.append(uy[k])
        weights.append(1.0)
        edges.append(1)
        while len(sums) > 1 and (sums[-2] / weights[-2]) > (sums[-1] / weights[-1]):
            s = sums.pop() + sums.pop()
            w = weights.pop() + weights.pop()
            e = edges.pop() + edges.pop()
            sums.append(s)
            weights.append(w)
            edges.append(e)
    # 3) Expand block means back to per-unique-x fitted values.
    y_fit: List[float] = []
    for s, w, e in zip(sums, weights, edges):
        mean = s / w
        y_fit.extend([mean] * e)
    return ux, y_fit


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
def _fit_one(pairs: Sequence[Tuple[float, float]]) -> Optional[Dict[str, object]]:
    """Fit a single stat's isotonic calibrator from (p, outcome) pairs.
    Returns {"x": [...], "y": [...], "n": int} or None if < MIN_N usable pairs.
    Prefers sklearn IsotonicRegression when importable; pure PAVA fallback."""
    clean: List[Tuple[float, float]] = []
    for p, y in pairs or []:
        try:
            pf = float(p)
            yf = 1.0 if float(y) > 0.5 else 0.0
        except (TypeError, ValueError):
            continue
        if not math.isfinite(pf):
            continue
        clean.append((min(1.0, max(0.0, pf)), yf))
    if len(clean) < MIN_N:
        return None
    xs = [c[0] for c in clean]
    ys = [c[1] for c in clean]
    try:
        from sklearn.isotonic import IsotonicRegression  # type: ignore
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(xs, ys)
        # Sample the fitted map on the sorted unique training x to get knots.
        ux = sorted(set(xs))
        uy = [float(min(1.0, max(0.0, v))) for v in iso.predict(ux)]
        xk, yk = ux, uy
    except Exception:  # noqa: BLE001 -- pure fallback, never raise out of fit
        xk, yk = pava(xs, ys)
    # Collapse exact-duplicate x knots (interp needs strictly increasing x).
    fx: List[float] = []
    fy: List[float] = []
    for x, y in zip(xk, yk):
        if fx and x == fx[-1]:
            fy[-1] = y  # PAVA gives equal y on ties; keep last
            continue
        fx.append(round(float(x), 6))
        fy.append(round(float(min(1.0, max(0.0, y))), 6))
    if len(fx) < 2:  # degenerate (all same x) -> not usable as a map
        return None
    return {"x": fx, "y": fy, "n": len(clean)}


def fit_recalibrators(df, *, stats: Optional[Sequence[str]] = None,
                      club_priors: bool = False,
                      out_path: Optional[str] = None) -> Dict[str, dict]:
    """Fit a per-stat isotonic recalibrator from the LEAK-FREE backtest pairs.

    For each modeled stat we gather (p_over, outcome) pairs across the WC matches
    (via props_eval.backtest_pairs -- the same leak-free walk-forward loop the
    readout scores), then fit isotonic model_p -> empirical freq. Stats with <
    MIN_N pairs are SKIPPED (identity). Writes
    data/domains/soccer/prop_recal.json {as_of, mode, per_stat:{stat:{x,y,n}}}.
    Returns {stat: {x, y, n}} for the stats that were fitted. Never raises."""
    mode = "club-augmented (approx as-of)" if club_priors else "strict leak-free"
    try:
        from scripts.platformkit.props_eval import backtest_pairs
    except Exception:  # noqa: BLE001
        return {}
    try:
        pairs_by_stat = backtest_pairs(df, stats=stats, club_priors=club_priors)
    except Exception:  # noqa: BLE001
        pairs_by_stat = {}
    per_stat: Dict[str, dict] = {}
    for stat, pairs in (pairs_by_stat or {}).items():
        try:
            fit = _fit_one(pairs)
        except Exception:  # noqa: BLE001
            fit = None
        if fit is not None:
            per_stat[stat] = fit
    payload = {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
        "min_n": MIN_N,
        "per_stat": per_stat,
        "note": ("isotonic recal on ~24 WC matches is THIN/approximate; improves "
                 "in-sample calibration only; re-fit as data grows + validate OOS. "
                 "calibration != edge."),
    }
    try:
        path = out_path or _RECAL_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="ascii") as fh:
            json.dump(payload, fh, indent=2)
    except Exception as exc:  # noqa: BLE001 -- write failure must not raise
        logger.warning("prop_recal write failed: %s", exc)
    return per_stat


# ---------------------------------------------------------------------------
# Load + apply
# ---------------------------------------------------------------------------
def load_recal(path: Optional[str] = None) -> Dict[str, dict]:
    """Load per-stat calibrators -> {stat: {x, y, n}}. {} if file absent / bad.
    Never raises."""
    try:
        p = path or _RECAL_PATH
        if not os.path.exists(p):
            return {}
        with open(p, "r", encoding="ascii") as fh:
            payload = json.load(fh)
        out: Dict[str, dict] = {}
        for stat, d in (payload.get("per_stat") or {}).items():
            xs = d.get("x")
            ys = d.get("y")
            if isinstance(xs, list) and isinstance(ys, list) and len(xs) == len(ys) \
                    and len(xs) >= 2:
                out[stat] = {"x": [float(v) for v in xs],
                             "y": [float(v) for v in ys],
                             "n": int(d.get("n", 0))}
        return out
    except Exception:  # noqa: BLE001
        return {}


def _interp(x: float, xs: Sequence[float], ys: Sequence[float]) -> float:
    """Monotone piecewise-linear interpolation of x through (xs, ys) knots
    (xs strictly increasing). Clamp x to [xs[0], xs[-1]] (flat ends)."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:  # binary search for the bracketing knot
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    x0, x1 = xs[lo], xs[hi]
    y0, y1 = ys[lo], ys[hi]
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def recalibrate(stat: str, p: float, recal: Optional[Dict[str, dict]] = None
                ) -> float:
    """Map raw model prob p -> calibrated prob via the stat's isotonic knots.

    Piecewise-linear interpolation through (x, y), clamped to [0, 1] and the knot
    range. IDENTITY (returns the clamped raw p) when the stat is not fitted, recal
    is empty/None, or anything goes wrong. Never raises."""
    try:
        pf = float(p)
        if not math.isfinite(pf):
            return 0.0
        pf = min(1.0, max(0.0, pf))
    except (TypeError, ValueError):
        return 0.0
    try:
        table = recal if recal is not None else load_recal()
        d = (table or {}).get(stat)
        if not d:
            return pf
        xs, ys = d.get("x"), d.get("y")
        if not (isinstance(xs, list) and isinstance(ys, list)
                and len(xs) == len(ys) and len(xs) >= 2):
            return pf
        out = _interp(pf, xs, ys)
        return min(1.0, max(0.0, float(out)))
    except Exception:  # noqa: BLE001
        return pf


__all__ = ["pava", "fit_recalibrators", "load_recal", "recalibrate", "MIN_N"]
