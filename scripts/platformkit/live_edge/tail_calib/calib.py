"""scripts.platformkit.live_edge.tail_calib.calib -- OOS distribution
calibration for B2's tail/skew claims (data/omni/live_edge/tails/, commit
3fdbc688). B4-HARDEN proved conditional-MEAN conditioning is a NULL, but B4
structurally never tested B2's claims, which are distribution-SHAPE results.
This module tests the RIGHT instrument: does the B2 empirical quantile
vector (fit on discovery) calibrate better on the RESERVE (2025-26) than a
naive same-mean/std NORMAL predictive distribution?

Both predictors are fit on the SAME discovery rows (2023-24 + 2024-25) via
tails.compute_tail_metrics (reuse, not reimplement -- gives mean/std/quantiles
per entity in one pass) and evaluated on the untouched reserve season.

Pure compute module. No ledger writes (tail_calib lane does not write the
claims journal -- see run_calib.py for report I/O only).

INVARIANTS: pandas/numpy/scipy + stdlib only. <=300 LOC. ASCII stdout.
Never writes data/registry/. No $/edge claims -- calibration language only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

from scripts.platformkit.live_edge import tails as tl

QUANTILES = tl.QUANTILES  # [0.005 .. 0.995], 13 points -- shared grid, fair CRPS comparison
COVERAGE_LEVELS = [0.50, 0.80, 0.90, 0.95, 0.99]
BIN_EDGES = [0.0, 0.005, 0.01, 0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90,
             0.95, 0.975, 0.99, 0.995, 1.0]  # same grid as tail_sweep.py's P7 table


def fit_predictors(discovery: pd.DataFrame, entity_col: str = "player_id",
                    stat_col: str = "pts") -> dict[str, dict]:
    """One fit pass on discovery -> per-entity {mean, std, quantiles, n}.
    Both baseline and tail-aware predictors read off this SAME dict, so any
    calibration difference is attributable to distribution SHAPE, not to
    which rows/entities were fit."""
    return tl.compute_tail_metrics(discovery, entity_col, stat_col)


def baseline_ppf(q: float, mean: float, std: float) -> float:
    """Naive predictor: Normal(mean, std) fit on discovery -- assumes no
    fat tail, the null hypothesis B2 is testing against."""
    if std <= 0:
        return mean
    return float(sps.norm.ppf(q, loc=mean, scale=std))


def tail_aware_ppf(q: float, quantiles: dict) -> float:
    """B2 predictor: empirical discovery quantile vector, linearly
    interpolated between the 13 fitted points. Flat-extrapolated beyond the
    stored 0.5%/99.5% anchors (numpy default) -- a known ceiling: true mass
    further into the tail than 99.5%/0.5% is invisible to this vector."""
    qs = sorted(float(k) for k in quantiles)
    vals = [quantiles[str(k)] if str(k) in quantiles else quantiles[k] for k in qs]
    return float(np.interp(q, qs, vals))


def baseline_cdf(x: float, mean: float, std: float) -> float:
    if std <= 0:
        return 0.5
    return float(sps.norm.cdf(x, loc=mean, scale=std))


def tail_aware_cdf(x: float, quantiles: dict) -> float:
    """Inverse of tail_aware_ppf: PIT value via interpolating value->prob on
    the same 13-point grid (ponytail: one np.interp, not a KDE)."""
    qs = sorted(float(k) for k in quantiles)
    vals = [quantiles[str(k)] if str(k) in quantiles else quantiles[k] for k in qs]
    return float(np.interp(x, vals, qs))


def _pinball(y_pred: float, y_true: float, q: float) -> float:
    diff = y_true - y_pred
    return diff * q if diff >= 0 else -diff * (1 - q)


def crps_approx(ppf_fn, y_true: float) -> float:
    """Quantile-based CRPS approximation: 2x the mean pinball loss over the
    shared QUANTILES grid (Gneiting-Raftery quantile decomposition). Both
    predictors use the SAME grid -> any bias in the discretization is
    identical, so the head-to-head delta is comparable even though the
    absolute constant is an approximation."""
    losses = [_pinball(ppf_fn(q), y_true, q) for q in QUANTILES]
    return 2.0 * float(np.mean(losses))


def evaluate_reserve(reserve: pd.DataFrame, fit_metrics: dict[str, dict],
                      entity_col: str = "player_id", stat_col: str = "pts") -> pd.DataFrame:
    """Per-player-game row: PIT + CRPS for both predictors. Only rows whose
    entity had sufficient discovery data (MIN_N) are scored -- the rest are
    reported separately as uncovered (new reserve-only entity)."""
    rows = []
    for _, r in reserve.iterrows():
        e = r[entity_col]
        m = fit_metrics.get(e)
        if m is None or m.get("insufficient"):
            continue
        x = float(r[stat_col])
        mean, std = m["mean"], m["std"]
        quantiles = m["quantiles"]
        rows.append({
            "entity": e, "actual": x,
            "pit_baseline": min(max(baseline_cdf(x, mean, std), 0.0), 1.0),
            "pit_tail": min(max(tail_aware_cdf(x, quantiles), 0.0), 1.0),
            "crps_baseline": crps_approx(lambda q: baseline_ppf(q, mean, std), x),
            "crps_tail": crps_approx(lambda q: tail_aware_ppf(q, quantiles), x),
        })
    return pd.DataFrame(rows)


def coverage_table(reserve: pd.DataFrame, fit_metrics: dict[str, dict],
                    entity_col: str = "player_id", stat_col: str = "pts") -> pd.DataFrame:
    """Nominal vs realized two-sided coverage at COVERAGE_LEVELS, per
    predictor, on the reserve."""
    rows = []
    for level in COVERAGE_LEVELS:
        lo_q, hi_q = round((1 - level) / 2, 4), round(1 - (1 - level) / 2, 4)
        hits_base = hits_tail = total = 0
        for _, r in reserve.iterrows():
            e = r[entity_col]
            m = fit_metrics.get(e)
            if m is None or m.get("insufficient"):
                continue
            x = float(r[stat_col])
            mean, std, quantiles = m["mean"], m["std"], m["quantiles"]
            lo_b, hi_b = baseline_ppf(lo_q, mean, std), baseline_ppf(hi_q, mean, std)
            lo_t, hi_t = tail_aware_ppf(lo_q, quantiles), tail_aware_ppf(hi_q, quantiles)
            hits_base += int(lo_b <= x <= hi_b)
            hits_tail += int(lo_t <= x <= hi_t)
            total += 1
        rows.append({
            "nominal": level, "n": total,
            "realized_baseline": hits_base / total if total else float("nan"),
            "realized_tail_aware": hits_tail / total if total else float("nan"),
        })
    return pd.DataFrame(rows)


def pit_uniformity(pit_values: np.ndarray) -> dict:
    """KS test of PIT values against Uniform(0,1) -- PIT uniform <=>
    predictive distribution is well calibrated."""
    if len(pit_values) < 5:
        return {"n": len(pit_values), "ks_stat": float("nan"), "ks_pvalue": float("nan")}
    stat, p = sps.kstest(pit_values, "uniform")
    return {"n": len(pit_values), "ks_stat": float(stat), "ks_pvalue": float(p)}


def tail_bin_check(reserve: pd.DataFrame, fit_metrics: dict[str, dict], ppf_fn_name: str,
                    entity_col: str = "player_id", stat_col: str = "pts") -> pd.DataFrame:
    """P7-style realized-vs-predicted bin table, OOS on reserve, for ONE
    predictor (ppf_fn_name in {'baseline', 'tail_aware'})."""
    ppf = baseline_ppf if ppf_fn_name == "baseline" else tail_aware_ppf
    rows = []
    for lo, hi in zip(BIN_EDGES[:-1], BIN_EDGES[1:]):
        nominal = hi - lo
        hits, total = 0, 0
        for e, g in reserve.groupby(entity_col, observed=True):
            m = fit_metrics.get(e)
            if m is None or m.get("insufficient"):
                continue
            lo_v = ppf(lo, m["mean"], m["std"]) if ppf_fn_name == "baseline" else ppf(lo, m["quantiles"])
            hi_v = ppf(hi, m["mean"], m["std"]) if ppf_fn_name == "baseline" else ppf(hi, m["quantiles"])
            vals = g[stat_col].to_numpy(dtype=float)
            hits += int(np.sum((vals >= lo_v) & (vals < hi_v)))
            total += len(vals)
        realized = hits / total if total else float("nan")
        rows.append({"bin": f"{lo*100:g}-{hi*100:g}%", "predicted": nominal,
                      "realized": realized, "n": total,
                      "ratio": (realized / nominal) if nominal and total else float("nan")})
    return pd.DataFrame(rows)
