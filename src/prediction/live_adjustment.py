"""src/prediction/live_adjustment.py — same-day adjustment layer for prop projections.

The trained PTS/REB models are near the ceiling of the HISTORICAL data; their
residual error is dominated by minutes-surprise driven by same-day events the
training features can't see (confirmed inactives, blowouts/pace). See
docs/VS_VEGAS_ASSESSMENT.md §3. This layer consumes the live feeds (lineup daemon
+ odds websocket) at PREDICTION time and nudges the base projection for:

  1. INACTIVE usage bump  — teammates ruled OUT tonight free up minutes/usage.
  2. PACE                 — tonight's game total vs the league baseline.
  3. BLOWOUT minutes      — a large spread implies garbage-time minutes cuts.

All magnitudes come from data/models/live_adjustment_coeffs.json
(scripts/calibrate_live_adjustment.py, leak-free fit). Adjustments are damped and
the net multiplier is clamped, so this can only nudge — never swing — a projection.
It is OFF unless the caller opts in; it never mutates the trained model.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
_COEFF_PATH = _ROOT / "data" / "models" / "live_adjustment_coeffs.json"

# Stat -> which calibrated bump applies. pts/ast/fg3m/tov are usage-driven (k_pts);
# reb/stl/blk are opportunity-driven (k_reb). Only pts & reb are directly fit; the
# rest borrow the nearest calibrated coefficient.
_USAGE_STATS = ("pts", "ast", "fg3m", "tov")
_OPP_STATS = ("reb", "stl", "blk")

# Net multiplier clamp — this layer nudges, never swings.
_MULT_LO, _MULT_HI = 0.80, 1.30

_DEFAULT_COEFFS: Dict[str, float] = {
    "inactive_pts_k": 0.44,
    "inactive_reb_k": 0.25,
    "blowout_min_k": -0.0035,
    "blowout_slack": 12.0,
    "baseline_game_total": 228.0,
    "pace_damp": 0.5,
}


@lru_cache(maxsize=1)
def load_coeffs() -> Dict[str, float]:
    """Load calibrated coefficients, falling back to baked-in defaults."""
    try:
        c = json.loads(_COEFF_PATH.read_text(encoding="utf-8"))
        return {**_DEFAULT_COEFFS, **{k: v for k, v in c.items()
                                      if isinstance(v, (int, float))}}
    except Exception:
        return dict(_DEFAULT_COEFFS)


def vacated_usage_share(out_l10_pts: Iterable[float], player_l10_pts: float) -> float:
    """Share of scoring/usage freed up by OUT teammates, relative to a team's worth.

    MUST match the definition used in scripts/calibrate_live_adjustment.py:
        vac_pts / (vac_pts + player_l10_pts * 5)
    (the *5 normalises against ~a starting five's scoring). Returns 0.0 when no
    teammate is out. Bounded [0, 1).
    """
    vac = float(sum(max(p, 0.0) for p in out_l10_pts))
    denom = vac + max(player_l10_pts, 0.0) * 5.0 + 1e-6
    return max(0.0, min(vac / denom, 0.95))


def _clamp(x: float) -> float:
    return max(_MULT_LO, min(x, _MULT_HI))


_VAC_BUMP_STRONG_STATS = frozenset({"pts", "reb"})  # AST excluded per tuning audit
_VAC_BUMP_STRONG_GATE = 0.60                         # only fires above this vac_share
_VAC_BUMP_STRONG_SCALE = 1.28                        # s=1.28 MAE-optimal, split-robust


def adjust_projection(
    base_proj: Dict[str, float],
    *,
    vac_share: float = 0.0,
    game_total: Optional[float] = None,
    game_spread: Optional[float] = None,
    coeffs: Optional[Dict[str, float]] = None,
    return_breakdown: bool = False,
    vac_min_share: float = 0.0,
    vac_stats: Optional[frozenset] = None,
    vac_strong_scale: Optional[float] = None,
):
    """Return a same-day-adjusted copy of *base_proj* (a {stat: value} dict).

    Args:
        base_proj:    the trained model's projection for ONE player.
        vac_share:    output of vacated_usage_share() for this player tonight (0 if
                      no teammate out / unknown).
        game_total:   tonight's Vegas game total (points). None -> no pace term.
        game_spread:  tonight's Vegas spread MAGNITUDE (abs points). None -> no
                      blowout term. Applies to rotation players of either side.
        coeffs:       override coefficient dict (else the calibrated file).
        return_breakdown: also return per-effect multipliers for logging/UI.
        vac_strong_scale: override the CV_VAC_BUMP_STRONG scale (default None =
                      read from env). Pass 1.0 to force byte-identical to 1x bump.

    Pure function. Unknown stats pass through untouched. Every net multiplier is
    clamped to [0.80, 1.30].
    """
    c = coeffs or load_coeffs()
    # CV_VAC_BUMP_GATED (leak-free VAC_BUMP_ACCURACY_VALIDATION.md, n=88,386): the
    # FLAT vacated-load bump HURTS served accuracy (+0.57% MAE) — the base model
    # already absorbs typical vac load via l10_min (absorbers under-predicted ~51%).
    # The bump only HELPS at HIGH vac_share (>= ~0.6: PTS -3.95% / REB -2.95% MAE);
    # AST is mis-tuned (it borrows inactive_pts_k=0.44). vac_min_share gates the
    # share below which NO vac bump applies; vac_stats (when set) restricts the bump
    # to the validated stats (pts, reb). Defaults (0.0 / None) = byte-identical.

    # CV_VAC_BUMP_STRONG (leak-free VAC_BUMP_COEFFICIENT_TUNING.md, temporal held-out):
    # At vac_share >= 0.60, the MAE-optimal scale s=1.28 beats 1x on HELD-OUT RMSE
    # consistently across both 70/30 and 65/35 temporal splits for PTS and REB.
    # Default OFF (byte-identical). AST excluded (mis-tuned coefficient).
    if vac_strong_scale is None:
        vac_strong_scale = (
            _VAC_BUMP_STRONG_SCALE
            if os.environ.get("CV_VAC_BUMP_STRONG", "0") == "1"
            else 1.0
        )

    eff_vac = vac_share if vac_share >= float(vac_min_share) else 0.0
    pace_mult = 1.0
    if game_total is not None and c.get("baseline_game_total"):
        dev = game_total / float(c["baseline_game_total"]) - 1.0
        pace_mult = 1.0 + float(c.get("pace_damp", 0.5)) * dev
    blow_mult = 1.0
    if game_spread is not None:
        sev = max(0.0, abs(game_spread) - float(c.get("blowout_slack", 12.0)))
        blow_mult = 1.0 + float(c.get("blowout_min_k", -0.0035)) * sev

    out: Dict[str, float] = {}
    breakdown: Dict[str, Dict[str, float]] = {}
    for stat, val in base_proj.items():
        if not isinstance(val, (int, float)):
            out[stat] = val
            continue
        s = stat.lower()
        _vac_ok = (vac_stats is None) or (s in vac_stats)
        # CV_VAC_BUMP_STRONG: scale the bump unit by vac_strong_scale for PTS/REB
        # when vac_share is in the high-vac gated regime. Default scale=1.0 = no-op.
        _strong_ok = (
            s in _VAC_BUMP_STRONG_STATS
            and vac_share >= _VAC_BUMP_STRONG_GATE
            and vac_strong_scale != 1.0
        )
        _eff_scale = float(vac_strong_scale) if _strong_ok else 1.0
        if s in _USAGE_STATS and _vac_ok:
            inact_mult = 1.0 + float(c.get("inactive_pts_k", 0.44)) * eff_vac * _eff_scale
        elif s in _OPP_STATS and _vac_ok:
            inact_mult = 1.0 + float(c.get("inactive_reb_k", 0.25)) * eff_vac * _eff_scale
        else:
            inact_mult = 1.0  # unknown stat, or vac gated off for this stat
        net = _clamp(inact_mult * pace_mult * blow_mult)
        out[stat] = round(float(val) * net, 3)
        if return_breakdown:
            breakdown[stat] = {"inactive": round(inact_mult, 4),
                               "pace": round(pace_mult, 4),
                               "blowout": round(blow_mult, 4),
                               "net": round(net, 4)}
    if return_breakdown:
        return out, breakdown
    return out


def is_enabled() -> bool:
    """Opt-in flag. OFF unless CV_LIVE_ADJUST=1 (mirrors CV_INGAME_SBS pattern)."""
    return os.environ.get("CV_LIVE_ADJUST", "0") == "1"
