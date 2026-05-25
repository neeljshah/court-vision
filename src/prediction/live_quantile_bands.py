"""live_quantile_bands.py -- Cycle 105c + R1_D_v2 (loop 5).

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

R1_D_v2 per-player variance modulation (probe SHIP 2026-05-25):
  half_width = base_sigma * per_stat_rescale * Z80
               * sqrt(clip(std_l20 / pop_mean_std, 0.6, 1.8))
  where std_l20 is the player's last-20-game std (walk-forward, no leakage).
  Fallback: <3 prior games -> multiplier=1.0 (pop_mean_std level).
  Controlled by _USE_PER_PLAYER_VARIANCE (default True). Requires pid +
  game_date on the bands_for() call; if either is absent the legacy path
  (no per-player modulation) is used transparently.

  NOTE: live snapshots from src.data.live do not currently carry game_date
  on the snapshot dict (the field is absent or None). Until game_date is
  plumbed into the canonical snapshot schema, _USE_PER_PLAYER_VARIANCE is
  set to True but the per-player path is only exercised when the caller
  passes both pid and game_date explicitly. For the in-production
  project_from_snapshot path that doesn't pass game_date, the legacy
  (non-per-player) bands are emitted -- back-compat preserved.

Artifact: data/models/live_quantile_calibration.json. Schema:

    {
      "endQ2": {
        "pts": {"sigma": 5.21, "scale": 1.18, "asymmetric": false},
        "fg3m": {"sigma": 0.92, "scale": 1.42, "asymmetric": true},
        ...
      },
      "endQ3": { ... }
    }

Per-player calibration artifact: data/models/per_player_quantile_calibration.json.
Schema:

    {
      "per_stat_rescale": {"pts": 0.9862, ...},
      "pop_mean_std":     {"pts": 5.664, ...},
      "version": "R1_D_v2",
      "ratio_clip": [0.6, 1.8]
    }

The Gaussian assumption is intentional -- the residuals after pace + foul +
blowout adjustments are roughly symmetric for the high-count stats (pts/reb/
ast) and the asymmetric branch handles the skewed counts. The scale factor
absorbs distributional deviation by targeting empirical 80% coverage on the
val slice (cycle 40 pattern).
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CAL_PATH = os.path.join(PROJECT_DIR, "data", "models", "live_quantile_calibration.json")
_PP_CAL_PATH = os.path.join(PROJECT_DIR, "data", "models", "per_player_quantile_calibration.json")
_GAMELOG_GLOB = os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")

# R1_D_v2: per-player variance modulation. Set False if game_date is never
# available in live snapshots and per-player path cannot be exercised.
_USE_PER_PLAYER_VARIANCE = True

_L20 = 20

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

# R1_D_v2 per-player calibration caches.
_PP_CAL_CACHE: Optional[dict] = None
_PP_CAL_LOADED: bool = False
_GAMELOG_IDX: Optional[Dict[int, List[Tuple[str, Dict[str, float]]]]] = None
_GAMELOG_IDX_LOADED: bool = False


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


def _load_pp_calibration() -> Optional[dict]:
    """Lazy loader for per-player calibration artifact. Returns None on miss."""
    global _PP_CAL_CACHE, _PP_CAL_LOADED
    if _PP_CAL_LOADED:
        return _PP_CAL_CACHE
    _PP_CAL_LOADED = True
    if not os.path.exists(_PP_CAL_PATH):
        _PP_CAL_CACHE = None
        return None
    try:
        with open(_PP_CAL_PATH, encoding="utf-8") as fh:
            _PP_CAL_CACHE = json.load(fh) or None
    except Exception:
        _PP_CAL_CACHE = None
    return _PP_CAL_CACHE


def _iso_date(s) -> Optional[str]:
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except Exception:
        return None


def _load_gamelog_idx() -> Dict[int, List[Tuple[str, Dict[str, float]]]]:
    """Lazy loader for gamelog index {pid: [(date_iso, {stat: val}), ...]}."""
    global _GAMELOG_IDX, _GAMELOG_IDX_LOADED
    if _GAMELOG_IDX_LOADED:
        return _GAMELOG_IDX or {}
    _GAMELOG_IDX_LOADED = True
    _stats = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
    out: Dict[int, List[Tuple[str, Dict[str, float]]]] = {}
    for fp in glob.glob(_GAMELOG_GLOB):
        parts = os.path.basename(fp).split("_")
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        try:
            rows = json.load(open(fp, encoding="utf-8")) or []
        except Exception:
            continue
        for row in rows:
            d = _iso_date(row.get("GAME_DATE"))
            if d is None:
                continue
            sv = {s: float(row.get(s.upper(), 0) or 0) for s in _stats}
            out.setdefault(pid, []).append((d, sv))
    for pid in out:
        out[pid].sort(key=lambda x: x[0])
    _GAMELOG_IDX = out
    return out


def _std_l20(pid: int, game_date: str, stat: str) -> Optional[float]:
    """Std of last 20 stat values STRICTLY BEFORE game_date (walk-forward safe).

    Returns None when fewer than 3 prior games exist for this player/stat.
    """
    idx = _load_gamelog_idx()
    log = idx.get(pid)
    if not log:
        return None
    prior = [r[stat] for (d, r) in log if d < game_date][-_L20:]
    if len(prior) < 3:
        return None
    return float(np.std(prior, ddof=1))


def reset_cache():
    """Clear all cached data -- exposed for tests."""
    global _CAL_CACHE, _CAL_PATH_LOADED
    global _PP_CAL_CACHE, _PP_CAL_LOADED
    global _GAMELOG_IDX, _GAMELOG_IDX_LOADED
    _CAL_CACHE = None
    _CAL_PATH_LOADED = None
    _PP_CAL_CACHE = None
    _PP_CAL_LOADED = False
    _GAMELOG_IDX = None
    _GAMELOG_IDX_LOADED = False


def bands_for(stat: str, q50: float, snapshot_point: Optional[str],
              calibration: Optional[dict] = None,
              *, pid: Optional[int] = None,
              game_date: Optional[str] = None) -> Dict[str, float]:
    """Return {"q10", "q50", "q90"} for one (stat, q50, snapshot_point).

    Behaviour:
      * snapshot_point not supported (None / endQ1) -> wide-open bands.
      * calibration artifact absent / missing entry -> wide-open bands
        ``q10=0, q90=2*q50`` (mirrors cycle 40 back-compat semantics).
      * asymmetric stat -> q10 = max(0, q50 - scale * sigma * z),
                            q90 = q50 + scale * sigma * z, then floor q10 at 0.
      * symmetric stat  -> q10 = q50 - scale * sigma * z,
                            q90 = q50 + scale * sigma * z.

    R1_D_v2 per-player modulation (when _USE_PER_PLAYER_VARIANCE is True
    AND pid AND game_date are provided AND the per-player calibration artifact
    exists):
      half_width = base_sigma * per_stat_rescale[stat] * Z80
                   * sqrt(clip(std_l20 / pop_mean_std[stat], 0.6, 1.8))
      Fallback to base_sigma (mult=1.0) when <3 prior games for this player.
      Back-compat: if pid or game_date is absent, the legacy path is used.
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

    # R1_D_v2: per-player variance modulation.
    extra_mult = 1.0
    if (_USE_PER_PLAYER_VARIANCE
            and pid is not None
            and game_date is not None):
        pp_cal = _load_pp_calibration()
        if pp_cal is not None:
            try:
                rescale = float(pp_cal["per_stat_rescale"].get(stat, 1.0))
                pop_std = float(pp_cal["pop_mean_std"].get(stat, 1.0))
                clip_lo, clip_hi = float(pp_cal["ratio_clip"][0]), float(pp_cal["ratio_clip"][1])
                raw_std = _std_l20(int(pid), game_date, stat)
                if raw_std is not None and pop_std > 0:
                    ratio = float(np.clip(raw_std / pop_std, clip_lo, clip_hi))
                else:
                    ratio = 1.0
                extra_mult = rescale * float(np.sqrt(ratio))
            except Exception:
                extra_mult = 1.0

    half = scale * sigma * _Z80 * extra_mult
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
    "_USE_PER_PLAYER_VARIANCE",
    "bands_for",
    "load_calibration",
    "period_to_point",
    "project_from_snapshot_with_bands",
    "reset_cache",
]
