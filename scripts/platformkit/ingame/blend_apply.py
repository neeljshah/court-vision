"""scripts.platformkit.ingame.blend_apply -- apply a SEED blend surface.

Pure function that pulls a calibrated pregame prior toward realized live state by
the amount a hand-seeded (or refit) weight surface prescribes, keyed on the
freshness lever (period/clock) and the current lead. REUSES the VERIFIED eval-gate
in-game blend core (scripts.platformkit.eval_gate.ingame_blend: blend, time_bucket,
margin_bucket) and the garbage clamp from domains.basketball_nba.ingame_blend_surface
-- it does NOT reimplement the blend math.

HONEST in-game invariants (binding):
  * The only validated lever is FRESHNESS. Variance MUST SHRINK monotonically as
    fraction_elapsed rises: var_live ~ var_pregame * remaining_frac (Brownian score
    anchor). Q1 is WIDE, Q4 is TIGHT for the SAME lead. apply_surface enforces this.
  * No dollar edge. The blend is a CALIBRATION step on new (realized) information,
    not a re-pricing of priced pregame facts. EDGE_CLAIMED is False.
  * Never fabricates: if fraction_elapsed is unknown, falls back to the pregame
    prior unchanged (w=0) with remaining_frac=1.0 (no spurious tightening).

INVARIANTS: never edit src/ or kernel/; pure; <=300 LOC; ASCII-only; no network.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Reuse the VERIFIED reference cores -- do NOT reimplement the blend math here.
from scripts.platformkit.eval_gate.ingame_blend import (
    blend,
    margin_bucket,
    time_bucket,
)

EDGE_CLAIMED = False

_REG_SEC_DEFAULT = 2880.0  # NBA: 4 x 12 min. Surface may override.


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _seconds_remaining(state: Any, reg_sec: float) -> Optional[float]:
    """Seconds remaining in regulation from a GameState, or None if unknown.

    Prefers fraction_elapsed() (the validated freshness lever); derives seconds as
    reg_sec * (1 - fraction_elapsed). Never fabricates -- None stays None.
    """
    frac = None
    fe = getattr(state, "fraction_elapsed", None)
    if callable(fe):
        frac = fe()
    if frac is None:
        return None
    return max(0.0, reg_sec * (1.0 - _clamp01(float(frac))))


def _grid_weight(surface: Dict[str, Any], sec_remaining: float,
                 score_diff: float) -> float:
    """Look up the blend weight w for (time_bucket, margin_bucket) in the surface."""
    grid = surface.get("grid") or {}
    n_time = int(surface.get("n_time", 4))
    n_margin = int(surface.get("n_margin", 5))
    reg_sec = float(surface.get("regulation_sec", _REG_SEC_DEFAULT))
    t = time_bucket(sec_remaining, total=reg_sec, n=n_time)
    edges = surface.get("margin_edges_abs")
    m = margin_bucket(score_diff, edges=edges) if edges else margin_bucket(score_diff)
    m = min(m, n_margin - 1)
    key = "%d,%d" % (t, m)
    return float(grid.get(key, surface.get("default_w", 0.0)))


def apply_surface(pregame_prior: Dict[str, Any], game_state: Any,
                  surface: Dict[str, Any]) -> Dict[str, Any]:
    """Blend a calibrated pregame prior toward realized live state via a surface.

    Parameters
    ----------
    pregame_prior : dict
        At minimum {'p0' or 'win_home': P(home win)}; optional 'variance' (the
        pregame win-prob/margin variance to be shrunk).
    game_state : GameState-like
        Exposes fraction_elapsed(), home_score, away_score (duck-typed; never
        imported, so it works with any conforming GameState).
    surface : dict
        A SEED (or refit) blend surface (see surfaces/nba.json).

    Returns
    -------
    dict with:
        p_home          : blended P(home win) in [0,1]
        p_away          : 1 - p_home
        w               : the blend weight actually applied (0 = pregame, 1 = live)
        remaining_frac  : fraction of regulation remaining (1.0 at tip -> 0.0 final)
        variance        : pregame variance * remaining_frac (SHRINKS as game runs)
        p_live          : the realized-state win-prob this blend pulled toward
        basis           : 'blend' | 'pregame_fallback'
        edge_claimed    : False, always

    The variance scales with remaining_frac (Brownian score anchor), so it is
    MONOTONE-DECREASING in fraction_elapsed -- Q1 wide, Q4 tight.
    """
    p0 = pregame_prior.get("p0", pregame_prior.get("win_home", 0.5))
    p0 = _clamp01(float(p0))
    var0 = float(pregame_prior.get("variance", 0.25))  # win-prob var default p(1-p)
    reg_sec = float(surface.get("regulation_sec", _REG_SEC_DEFAULT))

    sec_rem = _seconds_remaining(game_state, reg_sec)
    h = float(getattr(game_state, "home_score", 0) or 0)
    a = float(getattr(game_state, "away_score", 0) or 0)
    score_diff = h - a

    # Unknown freshness -> trust the pregame prior, no spurious tightening.
    if sec_rem is None:
        return {
            "p_home": p0, "p_away": _clamp01(1.0 - p0), "w": 0.0,
            "remaining_frac": 1.0, "variance": var0, "p_live": p0,
            "basis": "pregame_fallback", "edge_claimed": EDGE_CLAIMED,
        }

    remaining_frac = _clamp01(sec_rem / reg_sec) if reg_sec > 0 else 0.0

    # P_live: a lightweight realized-state win-prob from the score anchor. Margin
    # is projected to constant; the remaining-margin SD shrinks with remaining_frac
    # (the same Gaussian anchor the NBA repricer uses). math.erf, no scipy.
    p_live = _p_live_from_anchor(score_diff, remaining_frac, surface)

    w = _grid_weight(surface, sec_rem, score_diff)
    p_home = blend(p0, p_live, w)

    # Optional late-game garbage clamp (a clamp a linear blend cannot give).
    gc = surface.get("garbage_clamp")
    if gc:
        p_home = _maybe_garbage_clamp(p_home, abs(score_diff), sec_rem,
                                      score_diff, gc)

    var_floor = float(surface.get("variance_floor", 1e-4))
    variance = max(var_floor, var0 * remaining_frac)

    return {
        "p_home": _clamp01(p_home), "p_away": _clamp01(1.0 - p_home), "w": float(w),
        "remaining_frac": float(remaining_frac), "variance": float(variance),
        "p_live": float(p_live), "basis": "blend", "edge_claimed": EDGE_CLAIMED,
    }


def _p_live_from_anchor(score_diff: float, remaining_frac: float,
                        surface: Dict[str, Any]) -> float:
    """Realized-state P(home win) from the Gaussian remaining-margin anchor.

    final_margin ~ Normal(score_diff, margin_sigma^2 * remaining_frac). As the
    clock runs (remaining_frac -> 0) this collapses onto sign(score_diff), i.e. the
    live state dominates LATE -- the validated freshness shape.
    """
    import math
    if remaining_frac <= 0.0:
        return 1.0 if score_diff > 0 else (0.5 if score_diff == 0 else 0.0)
    sigma = float(surface.get("margin_sigma", 13.5)) * math.sqrt(remaining_frac)
    sigma = max(1e-6, sigma)
    z = score_diff / sigma
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _maybe_garbage_clamp(p: float, margin_abs: float, sec_remaining: float,
                         score_diff: float, gc: Dict[str, Any]) -> float:
    """Apply the domain garbage clamp when late + blowout (leader = home if dl>0)."""
    from domains.basketball_nba.ingame_blend_surface import garbage_clamp
    return garbage_clamp(
        p, margin_abs, sec_remaining,
        t_gt=float(gc.get("margin_abs", 18.0)),
        s_gt=float(gc.get("seconds_remaining", 120.0)),
        lo=float(gc.get("lo", 0.02)), hi=float(gc.get("hi", 0.98)),
        leader_is_home=(score_diff >= 0),
    )
