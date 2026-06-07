"""edge_calibration.py — Per-stat isotonic edge calibration (Iter-34).

Maps raw predicted edge (pred - line, signed units) to calibrated expected margin
via a fitted IsotonicRegression per stat. The calibrated edge is used for Kelly-B
stake sizing; bet selection still uses the raw edge vs the iter-25 thresholds.

Background
----------
Iter-21 linear-shrinkage analysis showed model overconfidence (slopes 0.21-0.68).
Linear shrinkage REVERTed. Iter-34 fits a non-parametric IsotonicRegression on
(raw_edge, actual_margin) training pairs from the 2024 playoffs canonical slice,
preserving monotonicity without forcing a global linear scale.

Iter-34 result: Choice B (raw threshold + isotonic Kelly-B) = +1.17pp vs baseline.
  - Baseline (iter-33 Kelly-B): +22.03% ROI on 1,016 OOS 2025-26 bets
  - Calibrated (iter-34 Choice B): +23.20% ROI
  - Decision: SHIP

Usage
-----
    from src.prediction.edge_calibration import calibrate_edge, load_isotonic_model

    cal_edge = calibrate_edge("pts", raw_edge=2.3)
    # Use cal_edge for Kelly stake, raw_edge for threshold test.
"""
from __future__ import annotations

import os
from typing import Dict, Optional

_ROOT       = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODEL_DIR  = os.path.join(_ROOT, "data", "models", "oos_pre_playoffs")

# Per-stat OLS slopes from iter-21 (fallback when no isotonic model is available)
_FALLBACK_SLOPES: Dict[str, float] = {
    "pts":  0.277,
    "reb":  0.235,
    "ast":  0.366,
    "fg3m": 0.461,
    "stl":  0.651,
    "blk":  0.228,
    "tov":  1.0,   # no calibration for tov
}

# In-process model cache (lazy load)
_MODEL_CACHE: Dict[str, object] = {}


def load_isotonic_model(stat: str) -> Optional[object]:
    """Load the fitted IsotonicRegression for a stat.

    Returns None if the model file is not found (identity fallback applies).
    Caches the loaded model in memory for the process lifetime.
    """
    global _MODEL_CACHE
    if stat in _MODEL_CACHE:
        return _MODEL_CACHE[stat]

    path = os.path.join(_MODEL_DIR, f"edge_isotonic_{stat}.joblib")
    if not os.path.exists(path):
        _MODEL_CACHE[stat] = None
        return None

    try:
        import joblib
        model = joblib.load(path)
        _MODEL_CACHE[stat] = model
        return model
    except Exception:
        _MODEL_CACHE[stat] = None
        return None


def calibrate_edge(stat: str, raw_edge: float) -> float:
    """Return isotonic-calibrated edge for a stat.

    The calibrated edge estimates the EXPECTED MARGIN (actual - line) given
    the model's raw predicted edge (pred - line). It is used for Kelly-B stake
    sizing — NOT for bet selection (which still uses raw_edge >= threshold).

    Fallback chain:
      1. IsotonicRegression (fitted on 2024 playoffs canonical, iter-34)
      2. Linear shrinkage (iter-21 OLS slope)
      3. Identity (raw_edge returned unchanged)

    Args:
        stat:      Stat name (pts/reb/ast/fg3m/stl/blk/tov).
        raw_edge:  Raw predicted edge = pred - line (signed, absolute units).

    Returns:
        Calibrated expected margin in the same units as raw_edge.
    """
    import numpy as np

    model = load_isotonic_model(stat)
    if model is not None:
        try:
            return float(model.predict([raw_edge])[0])
        except Exception:
            pass

    # Fallback: linear shrinkage
    slope = _FALLBACK_SLOPES.get(stat, 1.0)
    return raw_edge * slope


def calibrate_p_win(
    stat: str,
    raw_edge: float,
    threshold: float,
    baseline_hit: float,
) -> float:
    """Convert calibrated edge to a win probability estimate for Kelly sizing.

    Uses the iter-33 linear interpolation: from baseline_hit at threshold to
    baseline_hit + 0.08 at 3x threshold. Operates on the CALIBRATED edge so
    that the Kelly stake is commensurate with expected margin.

    Args:
        stat:          Stat name.
        raw_edge:      Raw predicted edge.
        threshold:     Iter-25 bet threshold for this stat.
        baseline_hit:  Production hit rate (from holdout_baseline.json).

    Returns:
        Win probability in [0.50, 0.90].
    """
    cal_edge = calibrate_edge(stat, abs(raw_edge))
    # SWEEP-2 fix (CV_PWIN_RAW_FRAC, default OFF = byte-identical legacy). The
    # `threshold` is denominated in RAW-edge units (iter-25), but the legacy frac
    # subtracts it from the isotonic-SHRUNK `cal_edge` (slopes 0.21-0.68). For
    # stats whose isotonic saturates below threshold (REB/AST, partly FG3M/STL/BLK)
    # this forces frac==0, pinning p_win at baseline_hit for ALL edge magnitudes
    # and killing edge-proportional Kelly sizing on the live slate. When ON, drive
    # frac off the RAW edge so its units match the raw-edge threshold and p_win
    # scales with edge size again. Real-money stake change -> recommend; validate
    # with run_gate1_full_analysis / iter33_fractional_kelly_backtest before default ON.
    if os.getenv("CV_PWIN_RAW_FRAC", "0") == "1":
        frac = min(1.0, max(0.0, (abs(raw_edge) - threshold) / max(threshold * 2.0, 0.1)))
    else:
        frac = min(1.0, max(0.0, (cal_edge - threshold) / max(threshold * 2.0, 0.1)))
    p_hi = min(0.85, baseline_hit + 0.08)
    p = baseline_hit + frac * (p_hi - baseline_hit)
    return float(min(0.90, max(0.50, p)))


def kelly_b_stake(
    stat: str,
    raw_edge: float,
    threshold: float,
    baseline_hit: float,
    kelly_frac: float = 0.25,
    max_stake_u: float = 3.0,
    payout: float = 100.0 / 110.0,
) -> float:
    """Compute iter-33 Kelly-B stake with isotonic-calibrated p_win.

    Mirrors the iter-33 Kelly-B formula but uses calibrated win probability
    (from calibrate_p_win) instead of the raw-edge interpolation.

    Returns stake in units (0.0 if no edge after calibration).
    """
    p_win  = calibrate_p_win(stat, raw_edge, threshold, baseline_hit)
    q      = 1.0 - p_win
    full_k = (p_win * payout - q) / payout
    if full_k <= 0:
        return 0.0
    return float(min(kelly_frac * full_k, max_stake_u))


def clear_model_cache() -> None:
    """Clear the in-process model cache (useful for testing)."""
    global _MODEL_CACHE
    _MODEL_CACHE = {}
