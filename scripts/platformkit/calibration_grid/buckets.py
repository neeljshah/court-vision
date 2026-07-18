"""scripts.platformkit.calibration_grid.buckets -- sport-blind, pure, TOTAL
bucket-key functions for the state-bucket calibration grid.

Never raise: every function clamps its inputs to the nearest valid band on
ANY numeric input (NaN, inf, negative, absurdly large, or a non-numeric
value) -- a weird/bad tick gets a band, never an exception. Bands are
deliberately coarse, hand-picked before any calibration was measured (a
moat-shape scan, not a fit) -- see calibration_grid/{nba,mlb,soccer}_grid.py
for the honest can_price gate each grid applies on top of these keys.

KEY SHAPES (examples):
  nba_bucket(24.0, 7, False)   -> "lead_+05_10|rem_12_24|reg"
  nba_bucket(50.0, -2, True)   -> "lead_-01_05|ot|ot"
  mlb_bucket(7, 3, False)      -> "inn_07|diff_+03|reg"
  mlb_bucket(11, -9, True)     -> "extras|diff_-06|extras"   (run_diff clipped +-6)
  soccer_bucket(52.0, 1)       -> "min_45_60|diff_+01"
  soccer_bucket(52.0, None)    -> "min_45_60|score_unknown"
"""
from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

# ascending, contiguous, non-overlapping; last band's hi=None means unbounded.
_LEAD_MAG_BANDS: Tuple[Tuple[int, Optional[int]], ...] = (
    (1, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, None))
_REM_BANDS: Tuple[Tuple[int, Optional[int]], ...] = (
    (0, 2), (2, 5), (5, 12), (12, 24), (24, 36), (36, None))
_MINUTE_BANDS: Tuple[Tuple[int, Optional[int]], ...] = (
    (0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, None))
_RUN_DIFF_CLIP = 6
_SOCCER_DIFF_CLIP = 5


def _safe_float(x, default: float = 0.0) -> float:
    """Never raises: bad/missing/non-finite input -> default."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(v) or math.isinf(v) else v


def _band_label(mag: float, bands: Sequence[Tuple[int, Optional[int]]]) -> str:
    """First ascending band containing mag>=0 (bands are contiguous from 0),
    formatted "LL_HH" (open top band uses 99 as the display sentinel)."""
    mag = max(0.0, mag)
    for lo, hi in bands:
        if hi is None or mag < hi:
            return "%02d_%02d" % (lo, hi if hi is not None else 99)
    lo, _hi = bands[-1]
    return "%02d_99" % lo


def _signed_clip_label(prefix: str, value: float, clip: float) -> str:
    v = max(-clip, min(clip, value))
    sign = "+" if v > 0 else ("-" if v < 0 else "+")
    return "%s_%s%02d" % (prefix, sign, int(round(abs(v))))


def nba_bucket(elapsed_min: float, home_lead: float, is_ot: bool) -> str:
    """elapsed_min = minutes elapsed (0-48 regulation, >48 in OT); home_lead =
    home_score-away_score (signed); is_ot collapses the time segment (an OT
    game-clock reading isn't comparable to a regulation one)."""
    lead = _safe_float(home_lead)
    mag = abs(lead)
    if mag < 1:
        lead_label = "lead_00"
    else:
        sign = "+" if lead > 0 else "-"
        lead_label = "lead_%s%s" % (sign, _band_label(mag, _LEAD_MAG_BANDS))
    if bool(is_ot):
        return "%s|ot|ot" % lead_label
    remaining = max(0.0, 48.0 - _safe_float(elapsed_min))
    return "%s|rem_%s|reg" % (lead_label, _band_label(remaining, _REM_BANDS))


def mlb_bucket(inning: float, run_diff: float, extras: bool) -> str:
    """inning clamped to 1-9 (extras=True collapses it to a single "extras"
    band -- inning 10 vs 14 is not a meaningfully different calibration
    question with this corpus's n); run_diff (home-away) clipped +-6."""
    ex = bool(extras)
    if ex:
        inning_label = "extras"
    else:
        inning_i = int(round(_safe_float(inning, default=1.0)))
        inning_label = "inn_%02d" % max(1, min(9, inning_i))
    diff_label = _signed_clip_label("diff", _safe_float(run_diff), float(_RUN_DIFF_CLIP))
    phase = "extras" if ex else "reg"
    return "%s|%s|%s" % (inning_label, diff_label, phase)


def soccer_bucket(minute: float, score_diff: Optional[float]) -> str:
    """minute banded 0-15/../75+; score_diff (home-away) clipped +-5, or the
    "score_unknown" band when the source row never carried a parseable score."""
    minute_label = "min_%s" % _band_label(_safe_float(minute), _MINUTE_BANDS)
    if score_diff is None:
        return "%s|score_unknown" % minute_label
    return "%s|%s" % (minute_label, _signed_clip_label("diff", _safe_float(score_diff),
                                                        float(_SOCCER_DIFF_CLIP)))


__all__ = ["nba_bucket", "mlb_bucket", "soccer_bucket"]
