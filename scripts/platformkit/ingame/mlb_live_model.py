"""scripts.platformkit.ingame.mlb_live_model -- in-game P(home win) for MLB.

Wires the daily MLB slate into LIVE in-game paper trading. The in-play capture loop
hands model_fn a state carrying the leak-free pregame prior (p0), the realized run
differential (state_diff), and the freshness lever (frac_elapsed from innings). This
blends that prior toward the realized state using the SAME verified eval-gate in-game
blend core (scripts.platformkit.ingame.blend_apply.apply_surface) the NBA repricer uses
-- it does NOT reimplement the blend math.

HONEST (binding):
  * The only validated lever is FRESHNESS: variance shrinks as the game elapses (early
    innings trust the pregame prior; late innings trust the live score). This is a
    CALIBRATION step on realized information, NOT a $ edge. edge_claimed stays False.
  * The MLB surface is a SEED (freshness-ramped weights + an MLB-realistic run-margin
    sigma ~3.2); the BLEND CORE is the verified one. It carries the proven prior; it
    NEVER fabricates -- missing p0/frac/diff or a FINAL game -> None (clean skip, no bet).
  * The in-play day-trader still gates every placement (calibration_justified requires
    p0_source PRIOR + is_liquid + is_fresh + tier floor) -- this only supplies the number.

INVARIANTS: build only under scripts/platformkit/; never edit src/ or kernel/; ASCII;
<=300 LOC; pure (no network); public fn NEVER raises.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Freshness ramp: weight on the LIVE score-anchor by time bucket (0=early innings ->
# 3=late innings). Early -> ~pregame prior; late -> ~live state. Monotone-increasing
# (the validated Brownian shape). Applied uniformly across run-margin buckets.
_W_BY_TIME = (0.12, 0.40, 0.70, 0.92)
_N_TIME, _N_MARGIN = 4, 5

# SEED MLB blend surface for apply_surface. regulation_sec is a nominal scale (the blend
# keys on the frac-derived seconds-remaining, so the absolute value cancels). margin_sigma
# is the MLB final run-margin SD (~3.2 runs), far tighter than NBA's ~13.5 points.
_MLB_SURFACE: Dict[str, Any] = {
    "n_time": _N_TIME, "n_margin": _N_MARGIN, "regulation_sec": 100.0,
    "margin_sigma": 3.2, "margin_edges_abs": [-2.5, -0.5, 0.5, 2.5],
    "default_w": 0.5,
    "grid": {"%d,%d" % (t, m): _W_BY_TIME[t]
             for t in range(_N_TIME) for m in range(_N_MARGIN)},
}


class _ShimState:
    """Minimal GameState duck-type for apply_surface: fraction_elapsed() + scores.
    Only the run differential matters to the anchor, so home_score=diff, away_score=0."""

    def __init__(self, frac: float, diff: float) -> None:
        self._frac = float(frac)
        self.home_score = float(diff)
        self.away_score = 0.0

    def fraction_elapsed(self) -> float:
        return self._frac


def _is_final(state: Dict[str, Any]) -> bool:
    st = str(state.get("status") or "").lower()
    return any(k in st for k in ("final", "post", "complete"))


def mlb_home_prob(state: Dict[str, Any]) -> Optional[float]:
    """In-game P(home win) for MLB from {p0, state_diff, frac_elapsed}, or None (skip).

    None (clean no-bet) when: state is not a dict; p0/state_diff/frac_elapsed missing or
    unparseable; frac_elapsed outside [0,1); or the game is FINAL. Otherwise returns the
    verified freshness-blended P(home win). NEVER raises (a miss is a skip, not a crash)."""
    try:
        if not isinstance(state, dict) or _is_final(state):
            return None
        p0 = state.get("p0")
        diff = state.get("state_diff")
        frac = state.get("frac_elapsed")
        if p0 is None or diff is None or frac is None:
            return None
        frac_f = float(frac)
        if not (0.0 <= frac_f < 1.0):
            return None  # pre-game (0 ok) but a finished game (>=1.0) is no in-game bet
        from scripts.platformkit.ingame.blend_apply import apply_surface
        out = apply_surface({"p0": float(p0)},
                            _ShimState(frac_f, float(diff)), _MLB_SURFACE)
        p = out.get("p_home") if isinstance(out, dict) else None
        return float(p) if isinstance(p, (int, float)) else None
    except Exception as exc:  # noqa: BLE001 -- a model miss is a clean skip, never a crash
        logger.debug("mlb_live_model.mlb_home_prob failed: %s", exc)
        return None


__all__ = ["mlb_home_prob"]
