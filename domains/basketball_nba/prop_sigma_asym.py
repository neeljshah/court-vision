"""domains.basketball_nba.prop_sigma_asym -- Per-stat ASYMMETRIC sigma measurement.

The symmetric per-stat k from prop_sigma_calib treats over/under tails identically.
NBA count stats are right-skewed (floored at 0), so the Gaussian systematically
misprices the two tails differently.  This module measures that asymmetry WITHOUT
wiring it into production: readout only.

Method
------
For each stat, compute raw OOF residuals: r = actual - oof_pred.

Use an IQR-based robust sigma estimate:
  sigma_iqr = IQR(r) / 1.349

This is consistent with a Gaussian scale but is NOT inflated by right-tail outliers,
so it reflects the central spread that the pricer relies on.  The heavy right tail
(NBA stats are floored at 0, right-skewed) then appears as excess coverage above sigma.

  over_coverage  = realized fraction of r > +sigma_iqr   (P(OVER is extreme))
  under_coverage = realized fraction of r < -sigma_iqr   (P(UNDER is extreme))
  over_nominal   = under_nominal = 15.87%  (Gaussian P(Z > 1))

  k_up_raw   = 84.13th percentile of r / sigma_iqr   [inflation to cover upper tail]
  k_down_raw = 84.13th percentile of (-r) / sigma_iqr [inflation to cover lower tail]

Clamps: k_up = max(1.0, k_up_raw), k_down = max(1.0, k_down_raw)  [do-no-harm].
Asymmetric flag: |k_up - k_down| > ASYM_THRESHOLD.
Thin stat (n < MIN_N) -> INSUFFICIENT_DATA sentinel dict, never raises.

Why IQR-based sigma?
The std(residuals) absorbs heavy right-tail outliers, inflating sigma until
percentile-based k_up shrinks below 1.  The IQR-based sigma reflects the
central body's spread; the excess tail then yields k_up > 1 as intended.
For symmetric Gaussian data, IQR/1.349 ~= std, so k_up ~= k_down ~= 1.

HONEST: calibration only.  No $, ROI, edge, or profit field anywhere.
INVARIANTS: <= 300 LOC; ASCII only; per-file test only; never write data/registry/.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_OOF_PATH = Path("data/cache/pregame_oof.parquet")

# Minimum raw residual count per stat to trust tail rates.
MIN_N = 200

# Gaussian nominal tail probability at z=1: P(Z > 1) = 1 - phi(1)
_UPPER_NOMINAL = 1.0 - 0.5 * (1.0 + math.erf(1.0 / math.sqrt(2.0)))  # ~0.1587

# Threshold for flagging asymmetry: |k_up - k_down| > threshold
ASYM_THRESHOLD = 0.05

# Sentinel string for thin/absent data
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# Conversion constant: IQR / 1.349 -> consistent sigma for Gaussian
_IQR_TO_SIGMA = 1.349


# ---------------------------------------------------------------------------
# Core: per-stat asymmetry computation
# ---------------------------------------------------------------------------

def _robust_sigma(residuals: np.ndarray) -> float:
    """IQR-based sigma: robust to right-tail outliers, consistent for Gaussian."""
    q25, q75 = float(np.percentile(residuals, 25)), float(np.percentile(residuals, 75))
    iqr = q75 - q25
    return max(iqr / _IQR_TO_SIGMA, 1e-6)


def _stat_result(
    stat: str,
    residuals: np.ndarray,
    min_n: int,
) -> Dict:
    """Compute asymmetric sigma report for one stat.

    Returns a dict with keys:
        stat, n, sigma_iqr,
        over_coverage, under_coverage,  -- realized tail fractions
        over_nominal, under_nominal,    -- Gaussian-implied nominal (~0.1587 each)
        asymmetric,                     -- bool: |k_up - k_down| > ASYM_THRESHOLD
        suggested_k_up, suggested_k_down,
        status                          -- "ok" | INSUFFICIENT_DATA
    """
    if len(residuals) < min_n:
        return _insufficient(stat, len(residuals))

    sigma = _robust_sigma(residuals)

    # Realized tail rates at z=1 boundary
    over_rate = float(np.mean(residuals > sigma))    # P(r > +1 robust-sigma)
    under_rate = float(np.mean(residuals < -sigma))  # P(r < -1 robust-sigma)

    # k inflation: how many robust-sigmas cover 84.13% of the distribution?
    # k_up_raw  = 84.13th pct of r / sigma  (upper tail inflation)
    # k_down_raw = 84.13th pct of (-r) / sigma (lower tail inflation)
    k_up_raw = float(np.quantile(residuals, 1.0 - _UPPER_NOMINAL)) / sigma
    k_down_raw = float(np.quantile(-residuals, 1.0 - _UPPER_NOMINAL)) / sigma

    k_up = max(1.0, k_up_raw)    # do-no-harm clamp
    k_down = max(1.0, k_down_raw)

    asymmetric = bool(abs(k_up - k_down) > ASYM_THRESHOLD)

    return {
        "stat": stat,
        "n": int(len(residuals)),
        "sigma_iqr": round(sigma, 4),
        "over_coverage": round(over_rate, 4),
        "under_coverage": round(under_rate, 4),
        "over_nominal": round(_UPPER_NOMINAL, 4),
        "under_nominal": round(_UPPER_NOMINAL, 4),
        "asymmetric": asymmetric,
        "suggested_k_up": round(k_up, 4),
        "suggested_k_down": round(k_down, 4),
        "status": "ok",
    }


def _insufficient(stat: str, n: int) -> Dict:
    """Return safe INSUFFICIENT_DATA sentinel for a stat."""
    return {
        "stat": stat,
        "n": n,
        "sigma_iqr": None,
        "over_coverage": None,
        "under_coverage": None,
        "over_nominal": round(_UPPER_NOMINAL, 4),
        "under_nominal": round(_UPPER_NOMINAL, 4),
        "asymmetric": False,
        "suggested_k_up": 1.0,
        "suggested_k_down": 1.0,
        "status": INSUFFICIENT_DATA,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def measure_asymmetry(
    oof_path: Path = _OOF_PATH,
    min_n: int = MIN_N,
    stats: Optional[List[str]] = None,
) -> Dict[str, Dict]:
    """Measure per-stat asymmetric sigma from OOF residuals.

    Returns a dict {stat: result_dict}.  Each result has:
        over_coverage, under_coverage, asymmetric, suggested_k_up,
        suggested_k_down, status.

    Absent OOF or empty DataFrame -> all stats return INSUFFICIENT_DATA.
    Never raises.

    Parameters
    ----------
    oof_path:  Path to pregame_oof.parquet (read-only).
    min_n:     Minimum residual count per stat to compute (else INSUFFICIENT_DATA).
    stats:     Stats to evaluate; defaults to all stats found in OOF.
    """
    try:
        oof_path = Path(oof_path)
        if not oof_path.exists():
            log.warning("OOF not found at %s; returning INSUFFICIENT_DATA", oof_path)
            target = stats or []
            return {s: _insufficient(s, 0) for s in target}

        df = pd.read_parquet(oof_path)
        required = {"stat", "oof_pred", "actual"}
        if df.empty or not required.issubset(df.columns):
            log.warning("OOF empty or missing columns; returning INSUFFICIENT_DATA")
            target = stats or []
            return {s: _insufficient(s, 0) for s in target}

        df = df.dropna(subset=["oof_pred", "actual"])
        df = df.copy()
        df["resid"] = df["actual"].astype(float) - df["oof_pred"].astype(float)

        all_stats = sorted(df["stat"].unique())
        target_stats = list(stats) if stats else all_stats

        results: Dict[str, Dict] = {}
        for stat in target_stats:
            sub = df[df["stat"] == stat]
            if sub.empty:
                results[stat] = _insufficient(stat, 0)
                continue
            resid = sub["resid"].to_numpy(dtype=float)
            resid = resid[np.isfinite(resid)]
            results[stat] = _stat_result(stat, resid, min_n)
            log.info(
                "stat=%s n=%d sigma_iqr=%.3f k_up=%.3f k_down=%.3f asym=%s",
                stat, results[stat]["n"],
                results[stat]["sigma_iqr"] or 0.0,
                results[stat]["suggested_k_up"],
                results[stat]["suggested_k_down"],
                results[stat]["asymmetric"],
            )

        return results

    except Exception as exc:  # noqa: BLE001
        log.error("measure_asymmetry error: %s", exc)
        target = stats or []
        return {s: _insufficient(s, 0) for s in target}


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

def _main() -> None:
    import logging as _logging
    _logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results = measure_asymmetry()
    print("Per-stat asymmetric sigma measurement (calibration only, no $-edge):")
    print(f"  {'stat':<7} {'n':>7} {'k_up':>6} {'k_down':>7} {'asym':>6} "
          f"{'over_cov':>9} {'under_cov':>10} status")
    for stat, r in sorted(results.items()):
        if r["status"] == INSUFFICIENT_DATA:
            print(f"  {stat:<7} {'n/a':>7}  -- INSUFFICIENT_DATA")
            continue
        print(
            f"  {stat:<7} {r['n']:>7} {r['suggested_k_up']:>6.3f} "
            f"{r['suggested_k_down']:>7.3f} {str(r['asymmetric']):>6} "
            f"{r['over_coverage']:>8.1%} {r['under_coverage']:>9.1%}  {r['status']}"
        )


if __name__ == "__main__":
    _main()
