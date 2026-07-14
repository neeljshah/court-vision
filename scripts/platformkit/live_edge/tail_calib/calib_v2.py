"""scripts.platformkit.live_edge.tail_calib.calib_v2 -- fixes the v1
clip-beyond-anchors artifact (commit 7f7cc645) with a PARAMETRIC TAIL: an
exponential tail beyond the 0.5%/99.5% empirical anchors, slope-matched to
the outermost empirical quantile gap so ppf/cdf extrapolate SMOOTHLY to
0/1 instead of pinning at the anchor (the pileup that hurt v1's PIT-KS).

v1 (calib.py) is imported READ-ONLY for the shared fit + baseline Normal +
CRPS/PIT/coverage plumbing -- this module adds the v2 predictor and a 3-way
(baseline / tail-v1-clip / tail-v2-parametric) head-to-head runner.

Math: right tail models 1-F(x) = (1-q_hi)*exp(-(x-v_hi)/scale) for x > v_hi,
where scale is chosen so the tail's density at v_hi matches the empirical
finite-difference slope dv/dq there (scale = slope*(1-q_hi)). Left tail is
the mirror image. Both are continuous AND smooth at the anchor (C0 and C1),
and ppf(q->1)->+inf / ppf(q->0)->-inf as a proper open-ended tail should.

INVARIANTS: pandas/numpy/scipy + stdlib only. <=300 LOC. ASCII stdout.
Never writes data/registry/. No $/edge claims -- calibration language only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge.tail_calib import calib as tc

QUANTILES = tc.QUANTILES
COVERAGE_LEVELS = tc.COVERAGE_LEVELS
BIN_EDGES = tc.BIN_EDGES


def _sorted_qv(quantiles: dict) -> tuple[list[float], list[float]]:
    qs = sorted(float(k) for k in quantiles)
    vals = [quantiles[str(k)] if str(k) in quantiles else quantiles[k] for k in qs]
    return qs, vals


def _right_tail_scale(qs: list[float], vals: list[float]) -> tuple[float, float, float]:
    q_hi, v_hi = qs[-1], vals[-1]
    q_prev, v_prev = qs[-2], vals[-2]
    slope = (v_hi - v_prev) / (q_hi - q_prev) if q_hi != q_prev else 0.0
    return q_hi, v_hi, max(slope * (1 - q_hi), 0.0)


def _left_tail_scale(qs: list[float], vals: list[float]) -> tuple[float, float, float]:
    q_lo, v_lo = qs[0], vals[0]
    q_next, v_next = qs[1], vals[1]
    slope = (v_next - v_lo) / (q_next - q_lo) if q_next != q_lo else 0.0
    return q_lo, v_lo, max(slope * q_lo, 0.0)


def tail_aware_v2_ppf(q: float, quantiles: dict) -> float:
    """Empirical quantile vector inside the anchors (same as v1), exponential
    tail extrapolation beyond them. q<=0 / q>=1 are the open ends of a
    continuous distribution -> +-inf (correct, not a degenerate pin)."""
    if q <= 0.0:
        return float("-inf")
    if q >= 1.0:
        return float("inf")
    qs, vals = _sorted_qv(quantiles)
    if qs[0] <= q <= qs[-1]:
        return float(np.interp(q, qs, vals))
    if q < qs[0]:
        q_lo, v_lo, scale = _left_tail_scale(qs, vals)
        if scale <= 1e-9:  # ponytail: degenerate (flat quantiles) -> v1 flat fallback
            return v_lo
        return float(v_lo + scale * np.log(q / q_lo))
    q_hi, v_hi, scale = _right_tail_scale(qs, vals)
    if scale <= 1e-9:
        return v_hi
    return float(v_hi - scale * np.log((1 - q) / (1 - q_hi)))


def tail_aware_v2_cdf(x: float, quantiles: dict) -> float:
    """Inverse of tail_aware_v2_ppf. Smoothly approaches 0/1 for x beyond the
    anchors instead of pinning PIT at 0.005/0.995 (v1's artifact)."""
    qs, vals = _sorted_qv(quantiles)
    if vals[0] <= x <= vals[-1]:
        return float(np.interp(x, vals, qs))
    if x < vals[0]:
        q_lo, v_lo, scale = _left_tail_scale(qs, vals)
        if scale <= 1e-9:
            return q_lo
        return float(min(max(q_lo * np.exp((x - v_lo) / scale), 0.0), 1.0))
    q_hi, v_hi, scale = _right_tail_scale(qs, vals)
    if scale <= 1e-9:
        return q_hi
    return float(min(max(1 - (1 - q_hi) * np.exp(-(x - v_hi) / scale), 0.0), 1.0))


PPF = {"baseline": lambda q, m: tc.baseline_ppf(q, m["mean"], m["std"]),
       "tail_v1": lambda q, m: tc.tail_aware_ppf(q, m["quantiles"]),
       "tail_v2": lambda q, m: tail_aware_v2_ppf(q, m["quantiles"])}
CDF = {"baseline": lambda x, m: tc.baseline_cdf(x, m["mean"], m["std"]),
       "tail_v1": lambda x, m: tc.tail_aware_cdf(x, m["quantiles"]),
       "tail_v2": lambda x, m: tail_aware_v2_cdf(x, m["quantiles"])}


def evaluate_reserve_3way(reserve: pd.DataFrame, fit_metrics: dict[str, dict],
                           entity_col: str, stat_col: str) -> pd.DataFrame:
    """Per-row PIT + CRPS for all 3 predictors in one pass (same rows scored,
    fair head-to-head)."""
    rows = []
    for _, r in reserve.iterrows():
        e = r[entity_col]
        m = fit_metrics.get(e)
        if m is None or m.get("insufficient"):
            continue
        x = float(r[stat_col])
        row = {"entity": e, "actual": x}
        for name in ("baseline", "tail_v1", "tail_v2"):
            row[f"pit_{name}"] = min(max(CDF[name](x, m), 0.0), 1.0)
            row[f"crps_{name}"] = tc.crps_approx(lambda q, n=name: PPF[n](q, m), x)
        rows.append(row)
    return pd.DataFrame(rows)


def coverage_table_3way(reserve: pd.DataFrame, fit_metrics: dict[str, dict],
                         entity_col: str, stat_col: str) -> pd.DataFrame:
    rows = []
    for level in COVERAGE_LEVELS:
        lo_q, hi_q = round((1 - level) / 2, 4), round(1 - (1 - level) / 2, 4)
        hits = {n: 0 for n in PPF}
        total = 0
        for _, r in reserve.iterrows():
            e = r[entity_col]
            m = fit_metrics.get(e)
            if m is None or m.get("insufficient"):
                continue
            x = float(r[stat_col])
            for name, fn in PPF.items():
                lo_v, hi_v = fn(lo_q, m), fn(hi_q, m)
                hits[name] += int(lo_v <= x <= hi_v)
            total += 1
        row = {"nominal": level, "n": total}
        for name in PPF:
            row[f"realized_{name}"] = hits[name] / total if total else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def tail_bin_check_3way(reserve: pd.DataFrame, fit_metrics: dict[str, dict],
                         predictor: str, entity_col: str, stat_col: str) -> pd.DataFrame:
    ppf = PPF[predictor]
    rows = []
    for lo, hi in zip(BIN_EDGES[:-1], BIN_EDGES[1:]):
        nominal = hi - lo
        hits, total = 0, 0
        for e, g in reserve.groupby(entity_col, observed=True):
            m = fit_metrics.get(e)
            if m is None or m.get("insufficient"):
                continue
            lo_v, hi_v = ppf(lo, m), ppf(hi, m)
            vals = g[stat_col].to_numpy(dtype=float)
            hits += int(np.sum((vals >= lo_v) & (vals < hi_v)))
            total += len(vals)
        realized = hits / total if total else float("nan")
        rows.append({"bin": f"{lo*100:g}-{hi*100:g}%", "predicted": nominal,
                      "realized": realized, "n": total,
                      "ratio": (realized / nominal) if nominal and total else float("nan")})
    return pd.DataFrame(rows)


def pit_uniformity(pit_values: np.ndarray) -> dict:
    return tc.pit_uniformity(pit_values)
