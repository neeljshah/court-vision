"""S688: CORP reliability and a bias-corrected Brier decomposition (report-only).

Calibration language only; nothing here is a statement about money.

CORP (Dimitriadis, Gneiting and Jordan 2021, PNAS): the reliability diagram is the
isotonic (pool-adjacent-violators) regression of the outcome on the forecast, so it
needs no bin count. With the Brier score BS and r the base rate:
  MCB = BS(p) - BS(pav)   (miscalibration, >= 0)
  DSC = BS(r) - BS(pav)   (discrimination, >= 0)
  UNC = BS(r)
  BS(p) = MCB - DSC + UNC exactly.

Bias-corrected binned decomposition (Ferro and Fricker 2012, QJRMS 138): the naive
Murphy REL and RES from scripts/platformkit/calib_decomp.decompose (read only, same
equal-width bins) are biased upward in small bins. With n_k rows and observed
frequency o_k in bin k, o the base rate and n the total:
  c      = (1/n) sum over bins with n_k >= 2 of n_k o_k (1 - o_k) / (n_k - 1)
  REL_bc = REL - c
  RES_bc = RES - c + o (1 - o) / (n - 1)
  UNC_bc = n o (1 - o) / (n - 1)
so REL_bc - RES_bc + UNC_bc == REL - RES + UNC. Bins with n_k < 2 contribute no
correction and are counted in bins_uncorrected. Both decompositions are reported.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from scripts.platformkit.calib_decomp import bin_edges, decompose


def _probs_outcomes(probs: Sequence[float], outcomes: Sequence[float]) -> tuple:
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if p.ndim != 1 or y.ndim != 1 or len(p) != len(y):
        raise ValueError("probs and outcomes must be equal-length 1-d sequences")
    if not (np.all(np.isfinite(p)) and np.all(np.isfinite(y))):
        raise ValueError("non-finite probability or outcome")
    if np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("probabilities must lie in [0, 1]")
    if np.any((y != 0.0) & (y != 1.0)):
        raise ValueError("outcomes must be 0 or 1")
    return p, y


def pav(x: Sequence[float], y: Sequence[float],
        w: Sequence[float] | None = None) -> np.ndarray:
    """Non-decreasing least-squares fit of y on x (ties in x pooled first).

    Returns the fitted value for every input row, in input order.
    """
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    wa = np.ones_like(ya) if w is None else np.asarray(w, dtype=float)
    if not (len(xa) == len(ya) == len(wa)):
        raise ValueError("x, y and w must have equal length")
    if len(xa) == 0:
        return np.zeros(0)
    ux, inv = np.unique(xa, return_inverse=True)
    wsum = np.bincount(inv, weights=wa, minlength=len(ux))
    ysum = np.bincount(inv, weights=wa * ya, minlength=len(ux))
    # blocks: [weighted sum, weight, number of unique x values]
    blocks: list[list[float]] = []
    for k in range(len(ux)):
        blocks.append([ysum[k], wsum[k], 1])
        while len(blocks) > 1 and (blocks[-2][0] / blocks[-2][1]
                                   >= blocks[-1][0] / blocks[-1][1]):
            s, ww, c = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += ww
            blocks[-1][2] += c
    fitted_unique = np.concatenate([np.full(int(c), s / ww) for s, ww, c in blocks])
    return fitted_unique[inv]


def corp(probs: Sequence[float], outcomes: Sequence[float]) -> dict:
    """CORP reliability diagram points and the MCB / DSC / UNC Brier decomposition."""
    p, y = _probs_outcomes(probs, outcomes)
    n = len(p)
    if n == 0:
        return {"status": "INSUFFICIENT", "n": 0}
    fit = pav(p, y)
    r = float(y.mean())
    bs = float(np.mean((p - y) ** 2))
    bs_pav = float(np.mean((fit - y) ** 2))
    bs_ref = float(np.mean((r - y) ** 2))
    ux, first = np.unique(p, return_index=True)
    mcb = bs - bs_pav
    dsc = bs_ref - bs_pav
    return {"status": "OK", "n": n, "base_rate": r, "brier": bs,
            "MCB": mcb, "DSC": dsc, "UNC": bs_ref,
            "identity_residual": bs - (mcb - dsc + bs_ref),
            "diagram": [[float(a), float(b)] for a, b in zip(ux, fit[first])]}


def brier_decomposition(probs: Sequence[float], outcomes: Sequence[float],
                        bins: int = 10) -> dict:
    """Naive Murphy decomposition (calib_decomp.decompose) beside the
    Ferro-Fricker bias-corrected one, on the same bins."""
    if not isinstance(bins, int) or isinstance(bins, bool) or bins < 1:
        raise ValueError("bins must be a positive integer")
    p, y = _probs_outcomes(probs, outcomes)
    naive = decompose(p, y, bins=bins)
    if naive.get("reliability") is None:
        return {"status": naive.get("status", "INSUFFICIENT"), "naive": naive,
                "bias_corrected": None}
    n = len(p)
    o = float(y.mean())
    corr = 0.0
    uncorrected = 0
    edges = bin_edges(bins)
    for k in range(bins):  # decompose()'s masks; its o_bar is rounded, so recount
        lo, hi = edges[k], edges[k + 1]
        mask = (p >= lo) & ((p < hi) if k < bins - 1 else (p <= hi))
        nk = int(mask.sum())
        if nk == 0:
            continue
        if nk < 2:
            uncorrected += 1
            continue
        ok = float(y[mask].mean())
        corr += nk * ok * (1.0 - ok) / (nk - 1)
    corr /= n
    rel_bc = naive["reliability"] - corr
    res_bc = naive["resolution"] - corr + o * (1.0 - o) / (n - 1)
    unc_bc = n * o * (1.0 - o) / (n - 1)
    return {"status": "OK", "n": n, "bins": bins,
            "naive": {"REL": naive["reliability"], "RES": naive["resolution"],
                      "UNC": naive["uncertainty"], "brier": naive["brier"],
                      "brier_binned": naive["brier_binned"]},
            "bias_corrected": {"REL": rel_bc, "RES": res_bc, "UNC": unc_bc,
                               "correction": corr,
                               "bins_uncorrected": uncorrected},
            "source": "Ferro and Fricker 2012; naive from calib_decomp.decompose"}
