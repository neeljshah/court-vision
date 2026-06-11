"""src/ingame/bayes_player_update.py — P3.2: the single minutes-weighted Bayesian player update.

ROADMAP: D04 §1/§4/§module-layout — replaces the 4–5 independent endQ3 correction heads (cycle110 /
foul_residual / blowout_residual / heat_check / R2_F) with ONE parametric form:

    posterior = trust_w · evidence_extrap + (1 - trust_w) · prior

where ``prior`` is the BASE projected-final (FROZEN at tip — RED-B Attack 4: never recomputed during a
resync), ``evidence_extrap`` extrapolates the player's CURRENT pace to the full game, and
``trust_w = trust_curve(stat, remaining_frac, regime)`` weights the evidence.

THE SHRINK-ARTIFACT GUARD (the keystone in-game discipline, RED-B Attack 1 / the MAE-vs-RMSE memory):
trust_w is NOT a shrink-toward-current knob. The DEFAULT trust curve is IDENTITY (trust_w=0) → the
posterior reproduces BASE EXACTLY (byte-identical, no shrink). Raising trust_w (trusting current pace)
is the GATED experiment that must beat BASE on **RMSE+bias, NOT MAE**, on a same-era held-out fold.

Behaviour at trust_w>0: a COLD star (low current, high remaining) reverts UP toward its prior; a HOT
player reverts DOWN. The minutes-weighting lives in the trust curve (low trust_w early when current pace
is noisy). Playoff guard: for AST in a playoff regime, trust_w is capped toward BASE (D04 §227).

DEFAULT-OFF: reached only under CV_INGAME_STATE; with the identity curve it is a no-op. numpy not needed.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from ingame import trust_curve

# Playoff AST is the one real reg-season model edge and must stay near BASE in playoffs (memory:
# never bet AST in playoffs). Cap the evidence weight for AST when the regime is a playoff game.
_AST_PLAYOFF_TRUST_CAP = 0.10


def evidence_extrap(current: float, min_so_far: float, remaining_min: float) -> float:
    """Extrapolate the player's CURRENT pace to the full game (the 'hold current pace' extreme).

    = current + (current / min_so_far) * remaining_min. If no minutes have been played the current
    pace is undefined, so we return ``current`` (no extrapolation) — the caller's prior then dominates.
    """
    if min_so_far is None or min_so_far <= 0.0:
        return float(current)
    rate = float(current) / float(min_so_far)
    return float(current) + rate * float(remaining_min)


def _is_playoff(regime: Optional[Any]) -> bool:
    if regime is None:
        return False
    if isinstance(regime, dict):
        return bool(regime.get("is_playoff", False))
    return bool(getattr(regime, "is_playoff", False))


def posterior_projection(
    prior: float,
    current: float,
    min_so_far: float,
    remaining_min: float,
    stat: str,
    regime: Optional[Any] = None,
    trust_override: Optional[float] = None,
) -> Tuple[float, float, str]:
    """Return (posterior_final, trust_w, direction).

    ``prior``        : the BASE projected-final (frozen at tip).
    ``current``      : stat accumulated so far.
    ``min_so_far``   : minutes the player has logged.
    ``remaining_min``: minutes the player is projected to still play.
    ``stat``         : "pts"/"reb"/... (selects the trust-curve cell + the AST playoff guard).
    ``regime``       : RegimeVector | dict | None (selects the trust-curve cell).
    ``trust_override``: bypass the curve (for tests / explicit experiments).

    direction is "up" iff the prior pulls the projection ABOVE the naive current-pace extrapolation
    (a cold star reverting up); "down" otherwise (a hot player cooling toward prior).
    """
    total_min = float(min_so_far or 0.0) + float(remaining_min or 0.0)
    rf = (float(remaining_min or 0.0) / total_min) if total_min > 0 else 1.0

    if trust_override is not None:
        tw = float(trust_override)
    else:
        tw = trust_curve.trust_w(stat, rf, regime, min_so_far)

    # Playoff AST guard: keep near BASE (do not let in-game evidence inflate the AST edge in playoffs).
    if stat == "ast" and _is_playoff(regime):
        tw = min(tw, _AST_PLAYOFF_TRUST_CAP)

    tw = min(1.0, max(0.0, tw))

    e = evidence_extrap(current, min_so_far, remaining_min)
    posterior = tw * e + (1.0 - tw) * float(prior)
    direction = "up" if float(prior) > e else "down"
    return posterior, tw, direction
