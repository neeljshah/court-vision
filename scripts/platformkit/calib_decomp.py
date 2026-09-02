"""scripts/platformkit/calib_decomp.py -- Murphy Brier decomposition.

Murphy (1973): BS = REL - RES + UNC, where:
  REL (reliability) = sum_k (n_k/N) * (o_bar_k - p_bar_k)^2  [calibration loss; want 0]
  RES (resolution)  = sum_k (n_k/N) * (o_bar_k - o_bar)^2    [discrimination; want high]
  UNC (uncertainty) = o_bar * (1 - o_bar)                     [base-rate var; data-fixed]

The identity REL - RES + UNC = brier_binned holds EXACTLY (within float epsilon),
where brier_binned is the Brier score computed when each prediction is replaced by its
bin mean (p_bar_k in place of p_i).  This is the standard Murphy decomposition identity.

The raw Brier score mean((p_i - y_i)^2) differs from brier_binned by the within-bin
forecast variance (the "refinement" term); both are reported. The acceptance test checks
|brier_check - brier_binned| < 1e-6, which holds by algebraic identity.

HONEST ANCHOR:
  - calibration (low REL) != edge. A perfectly calibrated constant forecaster has
    RES ~ 0 -- worthless. Both REL *and* RES matter.
  - INSUFFICIENT_DATA when n < MIN_N_TOTAL; per-bin stats flagged sparse at n < SPARSE_N.
  - No dollar-figure keys anywhere. Units only. Calibration not edge.

Usage (per file, never full-suite):
  python -m pytest scripts/platformkit/test_calib_decomp.py -q

<=300 LOC. ASCII only. No src/kernel/api edits.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

MIN_N_TOTAL: int = 30    # below this the decomposition is unreliable -> INSUFFICIENT_DATA
SPARSE_N: int = 10       # per-bin minimum; bins below flagged sparse


def _arr(x: Sequence[float]) -> np.ndarray:
    return np.asarray(x, dtype=float)


def bin_edges(bins: int = 10) -> np.ndarray:
    """The ONE equal-width edge array every calibration binner must use (S42).

    scoring.ece and decompose() below both bin by `np.linspace(0, 1, bins + 1)`
    with [lo, hi) intervals and a closed last bin. wp_diagnostics.reliability
    used to bin by min(bins-1, int(p*bins)), which disagrees with those edges on
    predictions landing exactly on the grid (float: 0.6*10 == 6.000000000000001
    but linspace's 7th edge is 0.6000000000000001), so a report publishing a bin
    table beside a summary ECE was self-inconsistent. Import this, do not rebuild
    the array. Calibration only -- no edge claim.
    """
    return np.linspace(0.0, 1.0, bins + 1)


def bin_index(prob: float, edges: np.ndarray) -> int:
    """Bin `prob` under `edges` with EXACTLY decompose()/ece() semantics.

    [edges[k], edges[k+1]) for every bin but the last, which is closed on both
    sides so p == 1.0 lands in it. Out-of-range probabilities clamp to the end
    bins rather than raising -- the callers here are diagnostics, not gates.
    """
    k = int(np.searchsorted(edges, prob, side="right")) - 1
    return min(max(k, 0), len(edges) - 2)


# ---------------------------------------------------------------------------
# Core decomposition
# ---------------------------------------------------------------------------

def decompose(
    probs: Sequence[float],
    outcomes: Sequence[float],
    bins: int = 10,
) -> Dict:
    """Murphy Brier decomposition: REL, RES, UNC, and per-bin detail.

    Parameters
    ----------
    probs:    predicted probabilities in [0, 1]
    outcomes: binary outcomes in {0, 1}
    bins:     number of equal-width probability bins (default 10)

    Returns
    -------
    dict with keys:
      status        -- "ok" or "INSUFFICIENT_DATA"
      n             -- total sample size
      brier         -- raw Brier score mean((p_i - y_i)^2)
      brier_binned  -- Brier score with bin-mean forecasts (REL - RES + UNC target)
      reliability   -- REL component (calibration loss, lower is better)
      resolution    -- RES component (discrimination gain, higher is better)
      uncertainty   -- UNC component (base-rate variance, fixed by data)
      brier_check   -- REL - RES + UNC (equals brier_binned within 1e-6)
      base_rate     -- overall observed frequency
      bins_detail   -- list of per-bin dicts: lo, hi, n, p_bar, o_bar, rel_k, res_k, sparse

    No dollar-figure keys. No edge claims. Calibration != edge.
    """
    p = _arr(probs)
    y = _arr(outcomes)
    n = len(p)

    if n < MIN_N_TOTAL:
        return {
            "status": "INSUFFICIENT_DATA",
            "n": n,
            "min_n_required": MIN_N_TOTAL,
            "brier": None,
            "brier_binned": None,
            "reliability": None,
            "resolution": None,
            "uncertainty": None,
            "brier_check": None,
            "base_rate": None,
            "bins_detail": [],
        }

    o_bar = float(y.mean())
    brier_val = float(np.mean((p - y) ** 2))
    unc = float(o_bar * (1.0 - o_bar))

    edges = bin_edges(bins)
    rel = 0.0
    res = 0.0
    bins_detail: List[Dict] = []
    p_binned = p.copy()   # bin-mean version of forecasts (for brier_binned)

    for k in range(bins):
        lo, hi = float(edges[k]), float(edges[k + 1])
        # last bin is closed on both sides to capture p == 1.0
        if k < bins - 1:
            mask = (p >= lo) & (p < hi)
        else:
            mask = (p >= lo) & (p <= hi)
        nk = int(mask.sum())
        if nk == 0:
            continue
        wk = nk / n
        pk = p[mask]
        yk = y[mask]
        p_bar_k = float(pk.mean())
        o_bar_k = float(yk.mean())
        rel_k = wk * (o_bar_k - p_bar_k) ** 2
        res_k = wk * (o_bar_k - o_bar) ** 2
        rel += rel_k
        res += res_k
        p_binned[mask] = p_bar_k
        bins_detail.append({
            "lo": lo,
            "hi": hi,
            "n": nk,
            "p_bar": round(p_bar_k, 6),
            "o_bar": round(o_bar_k, 6),
            "rel_k": rel_k,
            "res_k": res_k,
            "sparse": nk < SPARSE_N,
        })

    # brier_check = REL - RES + UNC holds exactly (within float epsilon) for
    # brier_binned (Brier with bin-mean forecasts), not for the raw brier.
    brier_binned = float(np.mean((p_binned - y) ** 2))
    brier_check = rel - res + unc

    return {
        "status": "ok",
        "n": n,
        "brier": brier_val,
        "brier_binned": brier_binned,
        "reliability": rel,
        "resolution": res,
        "uncertainty": unc,
        "brier_check": brier_check,
        "base_rate": round(o_bar, 6),
        "bins_detail": bins_detail,
    }


# ---------------------------------------------------------------------------
# Multi-(sport, market) runner
# ---------------------------------------------------------------------------

def decompose_batch(
    records: Sequence[Dict],
    bins: int = 10,
) -> List[Dict]:
    """Run decomposition over a list of (sport, market, probs, outcomes) records.

    Each element of `records` must have keys:
      sport    -- str
      market   -- str
      probs    -- sequence of floats
      outcomes -- sequence of floats

    Returns a list of result dicts, each with decompose() output plus sport/market.
    No dollar-figure keys anywhere.
    """
    results: List[Dict] = []
    for rec in records:
        sport = rec.get("sport", "unknown")
        market = rec.get("market", "unknown")
        result = decompose(rec["probs"], rec["outcomes"], bins=bins)
        result["sport"] = sport
        result["market"] = market
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# ASCII summary printer
# ---------------------------------------------------------------------------

def format_summary(result: Dict, label: str = "") -> str:
    """Render decomposition result as ASCII. No dollar-figure keys. Calibration != edge."""
    tag = f" [{label}]" if label else ""
    sport = result.get("sport", "")
    market = result.get("market", "")
    tag_line = f"{sport}/{market}{tag}" if (sport or market) else label

    if result.get("status") == "INSUFFICIENT_DATA":
        return (
            f"[calib_decomp] {tag_line}  "
            f"INSUFFICIENT_DATA (n={result['n']} < {result['min_n_required']})"
        )

    lines = [
        f"[calib_decomp] {tag_line}",
        f"  n={result['n']}  base_rate={result['base_rate']:.4f}",
        f"  Brier(raw)={result['brier']:.6f}  "
        f"Brier(binned)={result['brier_binned']:.6f}  "
        f"check(REL-RES+UNC)={result['brier_check']:.6f}",
        f"  REL(reliability)={result['reliability']:.6f}  "
        f"RES(resolution)={result['resolution']:.6f}  "
        f"UNC(uncertainty)={result['uncertainty']:.6f}",
    ]
    sparse_bins = [b for b in result["bins_detail"] if b["sparse"]]
    if sparse_bins:
        lines.append(
            f"  sparse bins (n<{SPARSE_N}): "
            f"{len(sparse_bins)}/{len(result['bins_detail'])}"
        )
    lines.append(
        "  NOTE: calibration (low REL) != edge. "
        "High RES = discriminating forecasts; both matter. "
        "Units only, no money claim."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI smoke-check
# ---------------------------------------------------------------------------

def main() -> int:
    """Quick smoke-check on synthetic data (no real corpus needed)."""
    rng = np.random.default_rng(42)
    n = 500
    probs = rng.uniform(0.1, 0.9, n)
    outcomes = (rng.uniform(size=n) < probs).astype(float)
    result = decompose(probs, outcomes)
    result["sport"] = "synthetic"
    result["market"] = "smoke_check"
    print(format_summary(result))
    check = result["brier_check"]
    binned = result["brier_binned"]
    err = abs(check - binned)
    ok = err < 1e-6
    print(f"  brier_binned={binned:.8f}  |err|={err:.2e}  identity_ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
