"""domains.basketball_nba.prop_coverage_diag -- Empirical interval-coverage diagnostic.

READ-ONLY observability surface.  Measures whether the prop sigma (window std *
scale-factor k from prop_sigma_calib) achieves the nominal 68.27% coverage in
OOF residuals.  Does NOT change any served number.

Public API::

    result = diagnose_coverage(oof_path=..., scale_factors={...})
    # or
    result = diagnose_coverage()   # reads defaults + auto-loads k from calib cache

Each per-stat entry is one of:
  - A dict with keys:
      stat              str   -- e.g. "pts"
      n                 int   -- triplets scored
      coverage_at_1sig  float -- empirical fraction |resid| <= 1 * effective_sigma
      nominal           float -- 0.6827 (Gaussian 1-sigma)
      gap               float -- coverage_at_1sig - nominal  (negative = under-covered)
      coverage_below_nominal bool -- True when gap < -COVERAGE_TOL
      k                 float -- scale factor applied (from prop_sigma_calib or 1.0)
      note              str   -- human-readable verdict
  - The string "INSUFFICIENT_DATA" when n < MIN_N.

HONEST: calibration only, no $ edge, no ROI.  This module NEVER writes parquets.
INVARIANTS: <= 300 LOC; ASCII only; per-file test only; never write data/registry/.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_OOF_PATH = Path("data/cache/pregame_oof.parquet")

# Minimum (player, game) residual triplets per stat before we trust coverage.
MIN_N = 100

# Rolling window width: matches prop_sigma_calib._WINDOW and player_props.py L15.
_WINDOW = 15
_MIN_WINDOW = 5

# Nominal coverage at 1-sigma under a Gaussian.
_NOMINAL = 0.6827

# Gap tolerance: if empirical coverage is more than this below nominal we flag it.
# 3pp below is a meaningful shortfall on typical NBA sample sizes.
COVERAGE_TOL = 0.03

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# Per-stat sigma floors that player_props.py applies (read-only mirror).
_SIGMA_FLOOR: Dict[str, float] = {
    "pts": 4.0, "reb": 2.0, "ast": 1.5, "stl": 1.0,
    "blk": 1.0, "fg3m": 1.0, "tov": 1.2,
}


# ---------------------------------------------------------------------------
# Core diagnostic
# ---------------------------------------------------------------------------

def diagnose_coverage(
    oof_path: Path = _OOF_PATH,
    scale_factors: Optional[Dict[str, float]] = None,
    min_n: int = MIN_N,
    window: int = _WINDOW,
    min_window: int = _MIN_WINDOW,
    nominal: float = _NOMINAL,
    coverage_tol: float = COVERAGE_TOL,
) -> Dict[str, Union[str, dict]]:
    """Measure empirical 1-sigma interval coverage per stat from OOF residuals.

    Parameters
    ----------
    oof_path:
        Path to pregame_oof.parquet (player_id, stat, oof_pred, actual, game_date).
    scale_factors:
        Per-stat k values from prop_sigma_calib.load_scale_factors().
        When None, tries to auto-load; falls back to all-1.0.
    min_n:
        Minimum triplets per stat to emit a result (else INSUFFICIENT_DATA).
    window:
        Rolling window width for sigma_window (must match prop_sigma_calib).
    min_window:
        Minimum prior games to form a valid window.
    nominal:
        Nominal coverage target (default 0.6827 = Gaussian z=1).
    coverage_tol:
        Gap below nominal that triggers coverage_below_nominal=True.

    Returns
    -------
    dict mapping stat -> result dict  OR  INSUFFICIENT_DATA string.
    Never writes files; never raises.
    """
    oof_path = Path(oof_path)

    # Resolve scale factors (read-only: import calib module, never write)
    factors = _resolve_scale_factors(scale_factors)

    if not oof_path.exists():
        log.warning("prop_coverage_diag: OOF not found at %s", oof_path)
        return {}

    try:
        df = pd.read_parquet(oof_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("prop_coverage_diag: failed to read OOF: %s", exc)
        return {}

    required = {"player_id", "stat", "oof_pred", "actual", "game_date"}
    if not required.issubset(df.columns):
        missing = required - set(df.columns)
        log.warning("prop_coverage_diag: OOF missing columns %s", missing)
        return {}

    df["game_date"] = pd.to_datetime(df["game_date"])
    results: Dict[str, Union[str, dict]] = {}

    for stat in sorted(df["stat"].unique()):
        sub = df[df["stat"] == stat].copy()
        k = factors.get(stat, 1.0)

        within: list[int] = []
        total = 0

        for _pid, grp in sub.groupby("player_id"):
            if len(grp) < min_window + 1:
                continue
            grp_sorted = grp.sort_values("game_date")
            actuals = grp_sorted["actual"].to_numpy(dtype=float)
            preds = grp_sorted["oof_pred"].to_numpy(dtype=float)

            for i in range(min_window, len(grp_sorted)):
                prior = actuals[max(0, i - window):i]
                if len(prior) < min_window:
                    continue
                sigma_w = float(np.std(prior, ddof=1))
                if sigma_w < 0.01:
                    continue  # near-constant window (all-zero stat)
                # Apply the sigma floor the way player_props.py does:
                # effective_sigma = max(sigma_w, floor) * k
                effective_sigma = max(sigma_w, _SIGMA_FLOOR.get(stat, 0.0)) * k
                resid = abs(float(actuals[i] - preds[i]))
                within.append(int(resid <= effective_sigma))
                total += 1

        if total < min_n:
            log.info(
                "prop_coverage_diag: stat=%s: only %d triplets (< %d) -> %s",
                stat, total, min_n, INSUFFICIENT_DATA,
            )
            results[stat] = INSUFFICIENT_DATA
            continue

        coverage = float(sum(within) / total)
        gap = round(coverage - nominal, 4)
        below = gap < -coverage_tol

        if below:
            verdict = (
                "UNDER-COVERED: empirical coverage %.1f%% < nominal %.1f%% "
                "(gap=%.1f%%). k=%.3f may need further inflation."
                % (coverage * 100, nominal * 100, gap * 100, k)
            )
        else:
            verdict = (
                "OK: empirical coverage %.1f%% near nominal %.1f%% "
                "(gap=%.1f%%, k=%.3f)."
                % (coverage * 100, nominal * 100, gap * 100, k)
            )

        results[stat] = {
            "stat": stat,
            "n": total,
            "coverage_at_1sig": round(coverage, 4),
            "nominal": nominal,
            "gap": gap,
            "coverage_below_nominal": below,
            "k": k,
            "note": verdict,
        }
        log.info(
            "prop_coverage_diag: stat=%s n=%d cov=%.3f gap=%.3f k=%.3f below=%s",
            stat, total, coverage, gap, k, below,
        )

    return results


# ---------------------------------------------------------------------------
# Summary helper
# ---------------------------------------------------------------------------

def coverage_flag_summary(
    diag: Dict[str, Union[str, dict]],
) -> Dict[str, object]:
    """Summarise diagnostic output into a per-stat flag table.

    Returns::

        {
          "stats": [...],
          "flags": {
            stat: "coverage_below_nominal" | "ok" | "INSUFFICIENT_DATA"
          },
          "any_below_nominal": bool,
          "note": str,
        }

    Read-only aggregation over the diagnose_coverage output.  Never raises.
    """
    flags: Dict[str, str] = {}
    any_below = False

    for stat, result in diag.items():
        if result == INSUFFICIENT_DATA:
            flags[stat] = INSUFFICIENT_DATA
        elif isinstance(result, dict):
            if result.get("coverage_below_nominal"):
                flags[stat] = "coverage_below_nominal"
                any_below = True
            else:
                flags[stat] = "ok"
        else:
            flags[stat] = INSUFFICIENT_DATA

    return {
        "stats": sorted(flags.keys()),
        "flags": flags,
        "any_below_nominal": any_below,
        "note": (
            "Read-only coverage diagnostic. k>1 means sigma was inflated by "
            "prop_sigma_calib; coverage_below_nominal=True means inflation is "
            "still insufficient for that stat."
        ),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_scale_factors(
    scale_factors: Optional[Dict[str, float]],
) -> Dict[str, float]:
    """Return scale factors: use provided dict, else auto-load from calib module."""
    if scale_factors is not None:
        return scale_factors
    try:
        from domains.basketball_nba.prop_sigma_calib import load_scale_factors
        return load_scale_factors()
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "prop_coverage_diag: could not load scale factors (%s); using k=1.0",
            exc,
        )
        return {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    import logging as _logging
    _logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    diag = diagnose_coverage()
    if not diag:
        print("No results (OOF absent or missing columns).")
        return
    summary = coverage_flag_summary(diag)
    print(f"  {'stat':<8} {'cov':>7} {'gap':>7} {'k':>6} {'flag'}")
    for stat in summary["stats"]:
        flag = summary["flags"][stat]
        if flag == INSUFFICIENT_DATA:
            print(f"  {stat:<8} {'N/A':>7} {'N/A':>7} {'N/A':>6}  INSUFFICIENT_DATA")
        else:
            r = diag[stat]
            assert isinstance(r, dict)
            print(f"  {stat:<8} {r['coverage_at_1sig']:>6.1%} "
                  f"{r['gap']:>+.3f} {r['k']:>6.3f}  {flag}")
    print("any_below_nominal:", summary["any_below_nominal"])


if __name__ == "__main__":
    _main()
