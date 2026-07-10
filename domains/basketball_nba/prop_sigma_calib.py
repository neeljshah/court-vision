"""domains.basketball_nba.prop_sigma_calib -- Per-stat NBA prop sigma inflation.

Computes a multiplicative scale factor k >= 1.0 per stat from OOF residuals
(k > 1 when window-sigma underestimates true error; thin/absent data -> k=1.0).

Usage::
    from domains.basketball_nba.prop_sigma_calib import load_scale_factors
    SCALE = load_scale_factors()          # cached; 1.0 fallback when absent
    sd = raw_sample_sd * SCALE.get(stat, 1.0)

Method: effective_z = |actual-oof_pred| / std(prior-15 actuals) per (stat, player,
game).  k = 68.27th percentile of effective_z per stat, clamped to >= 1.0 (never
deflate).  compute_scale_factors()+coverage_summary() fit and score k on the SAME
sample (in-sample, near-tautological) -- chrono_split_coverage() is the honest OOS
readout: fit on earlier dates, score coverage on later held-out dates.

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

from domains.basketball_nba.totals_recal import assert_no_leak

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


# Shared by compute_scale_factors/coverage_summary/chrono_split_coverage below
# so the in-sample fit and the OOS readout never drift apart.
def _effective_z_by_stat(
    df: pd.DataFrame,
    min_window: int,
    window: int,
) -> Dict[str, list]:
    """Per-stat list of effective_z = |actual-oof_pred| / std(prior window)."""
    out: Dict[str, list] = {}
    for stat in sorted(df["stat"].unique()):
        sub = df[df["stat"] == stat]
        effective_z: list = []
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
                    continue  # skip near-constant windows (all-zero stat)
                resid = float(actuals[i] - preds[i])
                effective_z.append(abs(resid) / sigma_w)
        out[stat] = effective_z
    return out


def _load_oof(oof_path: Path) -> Optional[pd.DataFrame]:
    """Load+validate the OOF parquet; None if absent or missing required cols."""
    if not Path(oof_path).exists():
        log.warning("OOF file not found at %s", oof_path)
        return None
    df = pd.read_parquet(oof_path)
    required = {"player_id", "stat", "oof_pred", "actual", "game_date"}
    if not required.issubset(df.columns):
        log.warning("OOF parquet missing columns %s", required - set(df.columns))
        return None
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_scale_factors(
    oof_path: Path = _OOF_PATH,
    min_n: int = _MIN_N,
    min_window: int = _MIN_WINDOW,
    window: int = _WINDOW,
) -> Dict[str, float]:
    """Compute per-stat sigma inflation k>=1.0 (dict) from OOF residuals; k=1.0
    for insufficient data; {} if OOF file absent (callers use .get(stat, 1.0))."""
    df = _load_oof(oof_path)
    if df is None:
        return {}
    results: Dict[str, float] = {}
    # Sigma floor NOT applied here (it's a call-site safety net) -- would hide
    # over-confidence for high-variance stats where sample_std exceeds the floor.
    z_by_stat = _effective_z_by_stat(df, min_window, window)

    for stat, effective_z in z_by_stat.items():
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
    """Load per-stat {stat: k} (k>=1.0), computing+caching if necessary; {}
    (callers use .get(stat, 1.0)) if neither cache nor OOF file is available."""
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


def coverage_summary(
    factors: Dict[str, float],
    oof_path: Path = _OOF_PATH,
    window: int = _WINDOW,
) -> Dict[str, Dict[str, float]]:
    """Per-stat {coverage_raw, coverage_scaled, k, n} IN-SAMPLE (same data k was
    fit on -- see chrono_split_coverage for the OOS readout). Stats in both
    `factors` and OOF data only.  effective_z<=1.0 <=> resid<=sigma_w; <=k <=> <=k*sigma_w."""
    df = _load_oof(oof_path)
    if df is None:
        return {}
    z_by_stat = _effective_z_by_stat(df, min_window=5, window=window)

    summary: Dict[str, Dict[str, float]] = {}
    for stat, k in factors.items():
        ez = z_by_stat.get(stat, [])
        if not ez:
            continue
        ez_arr = np.array(ez)
        summary[stat] = {
            "coverage_raw": round(float(np.mean(ez_arr <= 1.0)), 4),
            "coverage_scaled": round(float(np.mean(ez_arr <= k)), 4),
            "k": k,
            "n": len(ez),
        }
    return summary


# Chrono-split OOS readout: mirrors totals_recal.fit_wf's temporal half-split
# (reuses its assert_no_leak guard) -- fits k on earlier dates, scores coverage
# on later held-out dates.  Read-only: does not change load_scale_factors().

def chrono_split_coverage(
    oof_path: Path = _OOF_PATH,
    min_n: int = _MIN_N,
    min_window: int = _MIN_WINDOW,
    window: int = _WINDOW,
    fit_frac: float = 0.6,
) -> Dict[str, Dict]:
    """Fit k on early dates, score coverage on later (held-out) dates.  Returns
    {stat: {k_fit, n_fit, n_eval, coverage_eval_raw, coverage_eval_scaled,
    target_pct, survives_oos, verdict}}; verdict in SURVIVES / DOES_NOT_SURVIVE_OOS
    / UNDERPOWERED (same +-8pp band as the in-sample coverage test)."""
    df = _load_oof(oof_path)
    if df is None:
        return {}

    dates = np.sort(df["game_date"].unique())
    if len(dates) < 4:
        return {}
    cutoff = dates[int(len(dates) * fit_frac)]
    fit_df = df[df["game_date"] < cutoff]
    eval_df = df[df["game_date"] >= cutoff]
    if fit_df.empty or eval_df.empty:
        return {}

    # Leak guard (reused from totals_recal.fit_wf): every fit-window row must
    # sort strictly before every eval-window row.
    df_sorted = df.sort_values("game_date").reset_index(drop=True)
    fit_idx = df_sorted.index[df_sorted["game_date"] < cutoff].tolist()
    eval_idx = df_sorted.index[df_sorted["game_date"] >= cutoff].tolist()
    assert_no_leak(fit_idx, eval_idx, window_label="prop_sigma_calib chrono split")

    fit_z = _effective_z_by_stat(fit_df, min_window, window)
    eval_z = _effective_z_by_stat(eval_df, min_window, window)

    target = _TARGET_PCT / 100.0
    out: Dict[str, Dict] = {}
    for stat, fz in fit_z.items():
        ez = eval_z.get(stat, [])
        if len(fz) < min_n or len(ez) < min_n:
            out[stat] = {"verdict": "UNDERPOWERED", "n_fit": len(fz), "n_eval": len(ez)}
            continue
        k_fit = max(1.0, float(np.percentile(fz, _TARGET_PCT)))
        ez_arr = np.array(ez)
        cov_raw = float(np.mean(ez_arr <= 1.0))
        cov_scaled = float(np.mean(ez_arr <= k_fit))
        survives = abs(cov_scaled - target) <= 0.08
        out[stat] = {
            "k_fit": round(k_fit, 4),
            "n_fit": len(fz),
            "n_eval": len(ez),
            "coverage_eval_raw": round(cov_raw, 4),
            "coverage_eval_scaled": round(cov_scaled, 4),
            "target_pct": _TARGET_PCT,
            "survives_oos": survives,
            "verdict": "SURVIVES" if survives else "DOES_NOT_SURVIVE_OOS",
        }
    return out


def _main() -> None:
    import logging as _logging
    _logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    factors = load_scale_factors(recompute=True)
    print("Computed sigma scale factors:", factors)
    summ = coverage_summary(factors)
    print("IN-SAMPLE coverage (near-tautological, see chrono_split_coverage):", summ)
    print("Chrono-split OOS readout:", chrono_split_coverage())


if __name__ == "__main__":
    _main()
