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

LANE-2 FIX (grade-write wedge, wave-14): ingame_live_state._frac_elapsed's MLB formula is
denom_half=18.0 (9 innings x 2 halves = regulation) -- (2*(inning-1)+half)/18.0 SATURATES at
exactly 1.0 from the bottom of the 9th onward and stays clamped at 1.0 for the entire rest of
extras (min(1.0, ...)). The OLD guard here (`frac_f < 1.0` -> None) therefore treated every
still-LIVE bottom-9th/extra-innings tick as if the game had ended, permanently starving
model_fn (-> capture_pair_once never called again) for any game that runs to or past 9
innings -- NOT a transient failure, a deterministic one every tick from that point on.
FINALITY is decided ONLY by _is_final(state) (the real ESPN status string, e.g. "Top 11th"
vs "Final"), never by frac_elapsed's saturation. frac_f is now CLAMPED just under 1.0 for
the blend's freshness math (extras get the same max-freshness treatment as a tied bottom-9th
would) instead of being rejected. See test_late_and_extra_innings_still_price in
test_mlb_live_model.py + m2_stall_triage.json (MIL@ARI, KXMLBGAME-26JUL032145MILAZ).

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


# frac_elapsed's clamp ceiling for the freshness blend. Genuinely-live extra-innings /
# bottom-9th ticks arrive with frac_elapsed==1.0 (ingame_live_state's MLB formula
# saturates there -- see the LANE-2 FIX note above); pin the blend's *input* just under
# 1.0 rather than reject the tick, so a live extras game still gets a (maximally-fresh,
# score-dominated) number instead of being silently dropped forever.
_FRAC_CEIL = 0.999


def mlb_home_prob(state: Dict[str, Any]) -> Optional[float]:
    """In-game P(home win) for MLB from {p0, state_diff, frac_elapsed}, or None (skip).

    None (clean no-bet) when: state is not a dict; p0/state_diff/frac_elapsed missing or
    unparseable; frac_elapsed is negative; or the game is FINAL (decided ONLY by the real
    ESPN status string via _is_final -- NEVER by frac_elapsed reaching/saturating at 1.0,
    since bottom-9th-onward innings legitimately saturate the frac formula while the game
    is still live). Otherwise returns the verified freshness-blended P(home win), with
    frac_elapsed clamped to _FRAC_CEIL so extras get the same max-freshness treatment a
    tied bottom-9th would. NEVER raises (a miss is a skip, not a crash)."""
    try:
        if not isinstance(state, dict) or _is_final(state):
            return None
        p0 = state.get("p0")
        diff = state.get("state_diff")
        frac = state.get("frac_elapsed")
        if p0 is None or diff is None or frac is None:
            return None
        frac_f = float(frac)
        if frac_f < 0.0:
            return None  # unparseable/negative freshness lever -> honest skip
        frac_f = min(frac_f, _FRAC_CEIL)  # extras/bottom-9th saturation -> clamp, never reject
        from scripts.platformkit.ingame.blend_apply import apply_surface
        out = apply_surface({"p0": float(p0)},
                            _ShimState(frac_f, float(diff)), _MLB_SURFACE)
        p = out.get("p_home") if isinstance(out, dict) else None
        return float(p) if isinstance(p, (int, float)) else None
    except Exception as exc:  # noqa: BLE001 -- a model miss is a clean skip, never a crash
        logger.debug("mlb_live_model.mlb_home_prob failed: %s", exc)
        return None


__all__ = ["mlb_home_prob"]
