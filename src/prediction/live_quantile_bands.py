"""live_quantile_bands.py -- Cycle 105c (loop 5).

In-play quantile bands around the cycle-88 point projection.

Pre-game predictions get q10/q50/q90 bands via cycle 40's quantile_calibration.
Live in-play projections returned by ``project_from_snapshot`` are POINT
estimates only -- the operator can't size live bets by Bayesian
"is this edge robust to my uncertainty?" decisions without an interval.

This module is the live analog of cycle 40. The point projection becomes q50;
q10/q90 are computed from a learned per-(snapshot_period, stat) scale of the
residual distribution (actual_final - projected_final) on the 550-game retro.

Design rules:

  * NEVER changes the q50 point prediction (q50 == projected_final exactly).
  * Bands are ADDITIVE -- attached as q10/q50/q90 fields on each row.
  * Asymmetric branch for skewed counts (fg3m/stl/blk/tov) floors q10 at 0.
  * endQ1 is INTENTIONALLY skipped (data too sparse for stable calibration).
  * Missing calibration artifact -> wide-open bands (q10=0, q90=2*q50).
  * Opt-in via live_engine._INCLUDE_QUANTILE_BANDS=False (default off).

Artifact: data/models/live_quantile_calibration.json. Schema:

    {
      "endQ2": {
        "pts": {"sigma": 5.21, "scale": 1.18, "asymmetric": false},
        "fg3m": {"sigma": 0.92, "scale": 1.42, "asymmetric": true},
        ...
      },
      "endQ3": { ... }
    }

The Gaussian assumption is intentional -- the residuals after pace + foul +
blowout adjustments are roughly symmetric for the high-count stats (pts/reb/
ast) and the asymmetric branch handles the skewed counts. The scale factor
absorbs distributional deviation by targeting empirical 80% coverage on the
val slice (cycle 40 pattern).
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CAL_PATH = os.path.join(PROJECT_DIR, "data", "models", "live_quantile_calibration.json")

# Asymmetric branch -- mirrors cycle 40 for skewed counts that floor at 0.
ASYMMETRIC_STATS = ("fg3m", "stl", "blk", "tov")

# Standard-normal z-scores for symmetric 80% interval.
_Z80 = 1.2816  # P(Z < 1.2816) ~= 0.90 -> [q10, q90] covers 80%.

# Snapshot points we calibrate. endQ1 is intentionally absent (sparse data
# yields unstable scales; one quarter of play is not enough signal).
SUPPORTED_PERIODS = (3, 4)   # period=3 -> endQ2; period=4 -> endQ3
_PERIOD_TO_POINT = {3: "endQ2", 4: "endQ3"}


def period_to_point(period: int) -> Optional[str]:
    """Map snapshot ``period`` field to a calibration key, or None when
    unsupported (endQ1, OT, etc.)."""
    try:
        return _PERIOD_TO_POINT.get(int(period))
    except (TypeError, ValueError):
        return None


_CAL_CACHE: Optional[dict] = None
_CAL_PATH_LOADED: Optional[str] = None


def load_calibration(path: str = _CAL_PATH) -> dict:
    """Idempotent JSON loader. Returns {} when the artifact is absent."""
    global _CAL_CACHE, _CAL_PATH_LOADED
    if _CAL_CACHE is not None and _CAL_PATH_LOADED == path:
        return _CAL_CACHE
    if not os.path.exists(path):
        _CAL_CACHE = {}
        _CAL_PATH_LOADED = path
        return _CAL_CACHE
    try:
        with open(path, encoding="utf-8") as fh:
            _CAL_CACHE = json.load(fh) or {}
    except Exception:
        _CAL_CACHE = {}
    _CAL_PATH_LOADED = path
    return _CAL_CACHE


def reset_cache():
    """Clear cached calibration -- exposed for tests."""
    global _CAL_CACHE, _CAL_PATH_LOADED
    _CAL_CACHE = None
    _CAL_PATH_LOADED = None


def bands_for(stat: str, q50: float, snapshot_point: Optional[str],
              calibration: Optional[dict] = None) -> Dict[str, float]:
    """Return {"q10", "q50", "q90"} for one (stat, q50, snapshot_point).

    Behaviour:
      * snapshot_point not supported (None / endQ1) -> wide-open bands.
      * calibration artifact absent / missing entry -> wide-open bands
        ``q10=0, q90=2*q50`` (mirrors cycle 40 back-compat semantics).
      * asymmetric stat -> q10 = max(0, q50 - scale * sigma * z),
                            q90 = q50 + scale * sigma * z, then floor q10 at 0.
      * symmetric stat  -> q10 = q50 - scale * sigma * z,
                            q90 = q50 + scale * sigma * z.
    """
    try:
        q50f = float(q50)
    except (TypeError, ValueError):
        q50f = 0.0

    cal = calibration if calibration is not None else load_calibration()
    entry = None
    if snapshot_point and cal:
        entry = (cal.get(snapshot_point) or {}).get(stat)
    if entry is None:
        # back-compat wide-open
        return {
            "q10": 0.0,
            "q50": q50f,
            "q90": max(0.0, 2.0 * q50f),
        }
    try:
        sigma = float(entry.get("sigma", 0.0))
        scale = float(entry.get("scale", 1.0))
        asym = bool(entry.get("asymmetric", stat in ASYMMETRIC_STATS))
    except Exception:
        return {"q10": 0.0, "q50": q50f, "q90": max(0.0, 2.0 * q50f)}

    half = scale * sigma * _Z80
    if asym:
        q10v = max(0.0, q50f - half)
        q90v = q50f + half
    else:
        q10v = q50f - half
        q90v = q50f + half

    # Guarantee monotonicity even after the floor in the asymmetric branch.
    if q10v > q50f:
        q10v = q50f
    if q90v < q50f:
        q90v = q50f
    return {"q10": float(q10v), "q50": float(q50f), "q90": float(q90v)}


def project_from_snapshot_with_bands(snap: dict, *, period: Optional[int] = None,
                                     calibration_path: str = _CAL_PATH) -> List[Dict]:
    """Like ``live_engine.project_from_snapshot`` but each row also carries
    q10/q50/q90 fields.

    The point prediction (``projected_final``) is UNCHANGED -- q50 mirrors it
    exactly. Bands are additive: callers that don't want them can ignore the
    three new keys.

    Snapshot points endQ1 (period=2) and unsupported / OT periods get
    wide-open bands (q10=0, q90=2*q50) so the caller's downstream code
    never trips on missing keys.
    """
    # Local import to avoid circular import at module load (live_engine
    # imports many helpers; this module is also imported from there).
    from src.prediction.live_engine import project_from_snapshot

    rows = project_from_snapshot(snap, period=period)
    snap_period = period if period is not None else snap.get("period")
    point = period_to_point(snap_period) if snap_period is not None else None
    cal = load_calibration(calibration_path)
    for r in rows:
        stat = r.get("stat")
        try:
            q50 = float(r.get("projected_final", 0.0) or 0.0)
        except (TypeError, ValueError):
            q50 = 0.0
        bands = bands_for(stat, q50, point, calibration=cal)
        r["q10"] = bands["q10"]
        r["q50"] = bands["q50"]
        r["q90"] = bands["q90"]
    return rows


__all__ = [
    "ASYMMETRIC_STATS",
    "SUPPORTED_PERIODS",
    "bands_for",
    "load_calibration",
    "period_to_point",
    "project_from_snapshot_with_bands",
    "reset_cache",
]
