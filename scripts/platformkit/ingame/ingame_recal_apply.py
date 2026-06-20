"""scripts.platformkit.ingame.ingame_recal_apply -- do-no-harm serve-side applier
of the persisted isotonic recal map (surfaces/nba_recal.json) onto the blended
p_home produced by blend_apply.apply_surface.

DESIGN INVARIANTS (binding):
  * Identity when absent: if nba_recal.json does not exist, is empty, is malformed,
    or has no map for the relevant time-bucket, the input p_home is returned unchanged.
  * Monotone preserved: the serialised isotonic map is stored as sorted (x, y) knots
    (strictly non-decreasing in x; y non-decreasing since IsotonicRegression). Linear
    interpolation between knots preserves the monotone property end-to-end.
  * Clamp to [0,1]: the recalibrated probability is clamped regardless of the map.
  * Never raises: all errors (IO, KeyError, bad types) are caught and return identity.
  * No dollar key: no $ or monetary fields anywhere in this module.
  * p stays in [0,1]: guaranteed by _clamp01 on every return path.

nba_recal.json schema (written by ig-recal-persist):
  {
    "sport": "nba",
    "verdict": "SHIP" | "PARTIAL",
    "n_buckets": 4,
    "buckets": {
      "0": {"x": [...], "y": [...]},   // Q1 (early)
      "1": {"x": [...], "y": [...]},
      "2": {"x": [...], "y": [...]},
      "3": {"x": [...], "y": [...]}    // Q4 (late)
    }
  }

USAGE:
  from scripts.platformkit.ingame.ingame_recal_apply import load_recal_map, apply_recal

  recal = load_recal_map(path_to_nba_recal_json)  # None -> identity
  blend_result = blend_apply.apply_surface(prior, game_state, surface)
  result = apply_recal(blend_result, recal)
  # result["p_home"] is now recalibrated (or unchanged if recal is None/absent)

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_N_BUCKETS_DEFAULT = 4
_RECAL_SURFACES_DIR = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
    "scripts", "platformkit", "ingame", "surfaces",
)
_DEFAULT_RECAL_PATH = os.path.join(_RECAL_SURFACES_DIR, "nba_recal.json")


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _interp1d_monotone(x_knots: list, y_knots: list, p: float) -> float:
    """Linear interpolation over sorted (x, y) knot arrays; extrapolates flat.

    The isotonic regression guarantees y is non-decreasing. x must be sorted
    ascending (IsotonicRegression.X_thresholds_ is sorted). We clip at the
    boundary values so the map extrapolates flat (no out-of-range fabrication).
    """
    n = len(x_knots)
    if n == 0:
        return p
    if n == 1:
        return float(y_knots[0])
    # flat extrapolation below / above
    if p <= x_knots[0]:
        return float(y_knots[0])
    if p >= x_knots[-1]:
        return float(y_knots[-1])
    # binary search for the interval
    lo, hi = 0, n - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if x_knots[mid] <= p:
            lo = mid
        else:
            hi = mid
    x0, x1 = float(x_knots[lo]), float(x_knots[hi])
    y0, y1 = float(y_knots[lo]), float(y_knots[hi])
    if x1 <= x0:
        return y0
    t = (p - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def _time_bucket_from_frac(frac_elapsed: float, n: int = _N_BUCKETS_DEFAULT) -> int:
    """Convert fraction_elapsed to time-bucket index (0=early, n-1=late).

    Mirrors ingame_serve_persist.time_bucket(frac, n) and
    eval_gate.ingame_blend.time_bucket: bucket = clamp(0, floor(frac*n), n-1).
    """
    frac = float(frac_elapsed)
    frac = max(0.0, min(1.0, frac))
    return min(n - 1, max(0, int(frac * n)))


def _validate_map(m: Any) -> bool:
    """Return True iff m is a dict with non-empty lists 'x' and 'y' of equal length."""
    if not isinstance(m, dict):
        return False
    x = m.get("x")
    y = m.get("y")
    if not isinstance(x, list) or not isinstance(y, list):
        return False
    if len(x) == 0 or len(x) != len(y):
        return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

RecalMap = Optional[Dict[str, Any]]


def load_recal_map(path: Optional[str] = None) -> RecalMap:
    """Load and validate the persisted recal map from *path* (default nba_recal.json).

    Returns None (identity) when:
      * path is None and the default does not exist
      * the file is missing, empty, or not valid JSON
      * 'buckets' key is absent or empty
      * no bucket has a valid (x, y) map

    Never raises.
    """
    try:
        resolved = path if path is not None else _DEFAULT_RECAL_PATH
        if not os.path.exists(resolved):
            return None
        with open(resolved, encoding="ascii") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        buckets = data.get("buckets")
        if not isinstance(buckets, dict) or not buckets:
            return None
        # Validate that at least one bucket has a usable map
        any_valid = any(_validate_map(v) for v in buckets.values())
        if not any_valid:
            return None
        return data
    except Exception:  # noqa: BLE001 -- never raise, identity passthrough
        return None


def apply_recal(
    blend_result: Dict[str, Any],
    recal_map: RecalMap,
    *,
    remaining_frac_key: str = "remaining_frac",
    p_home_key: str = "p_home",
) -> Dict[str, Any]:
    """Apply the persisted isotonic recal map to blend_result['p_home'].

    Parameters
    ----------
    blend_result : dict
        Output of blend_apply.apply_surface. Must contain 'p_home' (float in
        [0,1]) and 'remaining_frac' (float in [0,1], fraction of game REMAINING).
        Any additional keys are passed through unchanged.
    recal_map : dict | None
        Loaded by load_recal_map(). None -> identity passthrough (no mutation).

    Returns
    -------
    dict
        A copy of blend_result with:
          p_home          : recalibrated value (or original if identity)
          p_away          : 1 - p_home (updated consistently)
          recal_applied   : True if the isotonic map was applied, False otherwise
          recal_bucket    : int time-bucket used (or None if identity)
        No dollar key ($) is present anywhere in the output.

    Never raises -- all exceptions produce identity passthrough.
    """
    try:
        out = dict(blend_result)
        p_in = _clamp01(float(out.get(p_home_key, 0.5)))

        # Identity if no recal map
        if recal_map is None:
            out["recal_applied"] = False
            out["recal_bucket"] = None
            out[p_home_key] = p_in
            out["p_away"] = _clamp01(1.0 - p_in)
            return out

        # Derive frac_elapsed from remaining_frac
        remaining = float(out.get(remaining_frac_key, 1.0))
        remaining = max(0.0, min(1.0, remaining))
        frac_elapsed = 1.0 - remaining

        buckets = recal_map.get("buckets") or {}
        n = int(recal_map.get("n_buckets", _N_BUCKETS_DEFAULT))
        b = _time_bucket_from_frac(frac_elapsed, n=n)

        # Look for the bucket (try int key then str key)
        bmap = buckets.get(b) or buckets.get(str(b))

        if not _validate_map(bmap):
            # No valid map for this bucket -> identity
            out["recal_applied"] = False
            out["recal_bucket"] = b
            out[p_home_key] = p_in
            out["p_away"] = _clamp01(1.0 - p_in)
            return out

        p_out = _clamp01(_interp1d_monotone(bmap["x"], bmap["y"], p_in))
        out[p_home_key] = p_out
        out["p_away"] = _clamp01(1.0 - p_out)
        out["recal_applied"] = True
        out["recal_bucket"] = b
        return out

    except Exception:  # noqa: BLE001 -- never raise, identity passthrough
        safe = dict(blend_result)
        safe["recal_applied"] = False
        safe["recal_bucket"] = None
        return safe


__all__ = [
    "load_recal_map",
    "apply_recal",
    "RecalMap",
]
