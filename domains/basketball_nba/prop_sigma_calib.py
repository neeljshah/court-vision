"""domains.basketball_nba.prop_sigma_calib -- Per-stat NBA prop sigma inflation.

Computes a multiplicative scale factor k >= 1.0 per stat from OOF residuals.
When the model's window-sigma underestimates true prediction error, k > 1 inflates
it.  Absent/thin data -> k == 1.0 (no-harm fallback).

Usage::
    from domains.basketball_nba.prop_sigma_calib import load_scale_factors
    SCALE = load_scale_factors()          # cached; 1.0 fallback when absent
    sd = raw_sample_sd * SCALE.get(stat, 1.0)

Method: for each (stat, player, game i), effective_z = |actual_i - oof_pred_i| /
std(prior-15 actuals).  k = 68.27th percentile of effective_z per stat (so 68% of
predictions fall within k*sigma).  k_raw < 1 -> k clamped to 1.0 (never deflate).

HONEST: calibration only, no $ edge, no ROI.  k-factors are unit-less.
INVARIANTS: <= 300 LOC; ASCII only; per-file test only; never write data/registry/.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_OOF_PATH = Path("data/cache/pregame_oof.parquet")
_CACHE_PATH = Path("data/cache/prop_sigma_scale.json")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Minimum prediction triplets per stat before we trust the k estimate.
_MIN_N = 200
# Minimum prior games in the window to compute a valid sigma_window.
_MIN_WINDOW = 5
# Window width matching player_props.py L15 sample.
_WINDOW = 15
# Nominal coverage target: 68.27% = z=1 Gaussian.
_TARGET_PCT = 68.27
# Base sigma floors that player_props.py already applies (per stat).
_SIGMA_FLOOR: Dict[str, float] = {
    "pts": 4.0, "reb": 2.0, "ast": 1.5, "stl": 1.0, "blk": 1.0,
    "fg3m": 1.0, "tov": 1.2,
}


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_scale_factors(
    oof_path: Path = _OOF_PATH,
    min_n: int = _MIN_N,
    min_window: int = _MIN_WINDOW,
    window: int = _WINDOW,
) -> Dict[str, float]:
    """Compute per-stat sigma inflation factors from OOF residuals.

    Returns a dict mapping stat -> k, where k >= 1.0.  Stats with insufficient
    data return k == 1.0 (no-harm fallback).  If OOF file is absent, returns
    an empty dict (callers must apply 1.0 fallback themselves via .get(stat, 1.0)).

    Parameters
    ----------
    oof_path:
        Path to pregame_oof.parquet (columns: player_id, stat, oof_pred, actual,
        game_date, fold).
    min_n:
        Minimum number of (player, game) prediction triplets per stat.
    min_window:
        Minimum number of prior games to form a valid sigma_window.
    window:
        Rolling window size for computing sigma_window (matches player_props.py).
    """
    if not Path(oof_path).exists():
        log.warning("OOF file not found at %s; returning empty scale map", oof_path)
        return {}

    df = pd.read_parquet(oof_path)
    required = {"player_id", "stat", "oof_pred", "actual", "game_date"}
    if not required.issubset(df.columns):
        log.warning("OOF parquet missing columns %s", required - set(df.columns))
        return {}

    df["game_date"] = pd.to_datetime(df["game_date"])
    results: Dict[str, float] = {}

    for stat in sorted(df["stat"].unique()):
        sub = df[df["stat"] == stat].copy()
        effective_z: list[float] = []

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
                # Do NOT apply the sigma floor here: the floor is a safety net
                # applied at the call-site (max(sample_std, floor) * k).
                # Including the floor would hide over-confidence for high-variance
                # stats (pts, reb) where sample_std already exceeds the floor.
                if sigma_w < 0.01:
                    continue  # skip near-constant windows (all-zero stat)
                resid = float(actuals[i] - preds[i])
                effective_z.append(abs(resid) / sigma_w)

        if len(effective_z) < min_n:
            log.info("stat=%s: only %d triplets (< %d) -> k=1.0", stat, len(effective_z), min_n)
            results[stat] = 1.0
            continue

        ez = np.array(effective_z)
        k_raw = float(np.percentile(ez, _TARGET_PCT))
        k = max(1.0, k_raw)  # no-harm: never deflate
        cov_at_1 = float(np.mean(ez <= 1.0))
        log.info(
            "stat=%s: n=%d, k_raw=%.3f -> k=%.3f (coverage@z1=%.1f%%)",
            stat, len(ez), k_raw, k, cov_at_1 * 100,
        )
        results[stat] = round(k, 4)

    return results


# ---------------------------------------------------------------------------
# Cache layer (JSON round-trip)
# ---------------------------------------------------------------------------

def save_scale_factors(
    factors: Dict[str, float],
    cache_path: Path = _CACHE_PATH,
) -> None:
    """Persist computed scale factors to JSON cache."""
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scale_factors": factors,
        "target_coverage_pct": _TARGET_PCT,
        "min_n": _MIN_N,
        "window": _WINDOW,
        "note": (
            "Per-stat sigma inflation k >= 1.0 derived from OOF prediction residuals. "
            "Calibration only -- no $ edge claimed."
        ),
    }
    with open(cache_path, "w", encoding="ascii") as fh:
        json.dump(payload, fh, indent=2)
    log.info("Saved scale factors to %s", cache_path)


def load_scale_factors(
    cache_path: Path = _CACHE_PATH,
    oof_path: Path = _OOF_PATH,
    recompute: bool = False,
) -> Dict[str, float]:
    """Load per-stat sigma scale factors, computing and caching if necessary.

    Returns a dict {stat: k} where k >= 1.0.  Falls back to 1.0 for any stat
    not present (via .get(stat, 1.0) at call site).  When neither cache nor OOF
    file is available, returns {} (callers apply 1.0 default).

    Parameters
    ----------
    cache_path:
        JSON cache written by save_scale_factors().
    oof_path:
        OOF parquet; used only when cache is absent or recompute=True.
    recompute:
        Force recomputation from OOF even if cache exists.
    """
    cache_path = Path(cache_path)
    if not recompute and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="ascii") as fh:
                payload = json.load(fh)
            factors = payload.get("scale_factors", {})
            # Validate: all values must be float >= 1.0
            if factors and all(isinstance(v, (int, float)) and v >= 1.0
                               for v in factors.values()):
                return {str(k): float(v) for k, v in factors.items()}
            log.warning("Cache at %s is malformed; recomputing", cache_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to read cache %s: %s; recomputing", cache_path, exc)

    factors = compute_scale_factors(oof_path=oof_path)
    if factors:
        save_scale_factors(factors, cache_path=cache_path)
    return factors


# ---------------------------------------------------------------------------
# Coverage summary (diagnostic)
# ---------------------------------------------------------------------------

def coverage_summary(
    factors: Dict[str, float],
    oof_path: Path = _OOF_PATH,
    window: int = _WINDOW,
) -> Dict[str, Dict[str, float]]:
    """Return per-stat coverage before and after applying scale factors.

    Used for validation / tests.  Returns::

        {stat: {
            "coverage_raw":    float,  # fraction within 1*sigma_window of oof_pred
            "coverage_scaled": float,  # fraction within 1*(k*sigma_window) of oof_pred
            "k":               float,
            "n":               int,
        }}

    Only stats present in both `factors` and OOF data are included.
    """
    if not Path(oof_path).exists():
        return {}

    df = pd.read_parquet(oof_path)
    df["game_date"] = pd.to_datetime(df["game_date"])
    summary: Dict[str, Dict[str, float]] = {}
    min_window = 5

    for stat, k in factors.items():
        sub = df[df["stat"] == stat].copy()
        if sub.empty:
            continue
        within_raw, within_scaled, total = 0, 0, 0
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
                    continue
                resid = abs(float(actuals[i] - preds[i]))
                within_raw += int(resid <= sigma_w)
                within_scaled += int(resid <= k * sigma_w)
                total += 1

        if total > 0:
            summary[stat] = {
                "coverage_raw": round(within_raw / total, 4),
                "coverage_scaled": round(within_scaled / total, 4),
                "k": k,
                "n": total,
            }
    return summary


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

def _main() -> None:
    import logging as _logging
    _logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    factors = load_scale_factors(recompute=True)
    print("Computed sigma scale factors:")
    for stat, k in sorted(factors.items()):
        print(f"  {stat}: k={k:.4f}")
    summ = coverage_summary(factors)
    if summ:
        print()
        print("Coverage summary (fraction within 1-sigma of oof_pred):")
        print(f"  {'stat':<8} {'k':>6} {'raw':>8} {'scaled':>8} {'n':>8}")
        for stat, row in sorted(summ.items()):
            print(f"  {stat:<8} {row['k']:>6.3f} {row['coverage_raw']:>7.1%}"
                  f" {row['coverage_scaled']:>7.1%} {row['n']:>8d}")


if __name__ == "__main__":
    _main()
