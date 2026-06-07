"""Leak-free in-game PACE-INTELLIGENCE enricher (gated, default OFF).

THE IDEA
--------
Remaining POSSESSIONS drive every counting stat AND the team total. The in-game
ensemble projects finals by extrapolating the game forward from the live state.
The production team projection (``baseline_team_projection``) and the snapshot
player head both extrapolate *the current score / box* by a pure CLOCK share
(played_share) -- they do NOT explicitly model that a game running ABOVE or
BELOW the two teams' structural pace identity is partly a transient that will
mean-revert. So when live tempo diverges from the pregame pace identity, the
remaining-possessions estimate is biased.

This module computes, for a live game state, a LEAK-FREE remaining-possessions
multiplier that BLENDS the live realized pace with the two teams' pregame pace
identity, and exposes it as a scalar ``poss_mult`` that callers can apply to the
remaining (not the already-banked) portion of a counting-stat / total projection.

  live_ppm      = state's possessions-so-far / minutes-so-far (already on the
                  game_row as ``pace_poss_per_min``; FGA+0.44*FTA+TOV-OREB est).
  exp_ppm       = pregame expected combined pace = (home_pace_pg + away_pace_pg)
                  / 48, from atlas_team_pace_identity.parquet (a SEASON identity,
                  not derived from this game's future => leak-free).
  blend_ppm     = BLEND_LIVE * live_ppm + (1 - BLEND_LIVE) * exp_ppm
  poss_mult     = blend_ppm / live_ppm      (multiplier on the REMAINING pace
                  the production extrapolation implicitly assumed == live_ppm)

A pure clock-share extrapolation implicitly assumes the rest of the game runs at
the LIVE pace. ``poss_mult`` < 1 when the game is running HOT (blend pulls it
back toward the slower structural identity => fewer remaining possessions than
live pace implies); > 1 when running COLD. The amount of pull-back is governed
by ``BLEND_LIVE`` in (0,1]; BLEND_LIVE=1 => no adjustment (pure live), the
mean-reversion-skeptic null.

EARLY-GAME CONFIDENCE RAMP
--------------------------
Live pace is NOISY early (few possessions). We damp the adjustment toward 1.0
when little game time has elapsed, scaling the pull-back by ``played_share``
(clamped): the correction is ~0 in the first minutes and reaches full strength
by the configured ramp point. This avoids amplifying early-game live-pace noise.

GATING / LEAK-SAFETY
--------------------
* Flag ``CV_INGAME_PACE_INTEL`` (default OFF). With the flag OFF,
  ``poss_mult_for_state`` returns EXACTLY 1.0 (byte-identical no-op) so any
  caller is a pure pass-through. ADDITIVE; no live default touched.
* Only score/clock (live_ppm, played_share) + pregame season pace identity are
  read. NO future possessions, no closing lines, nothing derived from the label.
* Priors are loaded once and cached; a missing/!covered team => return 1.0
  (no-op) so the adjustment never fires on partial data.

This module is consumed ONLY by the analysis + experiment scripts this wave
(read-only diagnostics); it does not touch prop_pergame / the live serve path.
"""
from __future__ import annotations

import json
import os
from typing import Dict, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PACE_INTEL_FLAG = "CV_INGAME_PACE_INTEL"

# Tunables (overridable via env so the experiment harness can sweep without edits)
_DEFAULT_BLEND_LIVE = 0.55   # weight on LIVE pace; (1-w) on structural identity
_DEFAULT_RAMP_SHARE = 0.40   # played_share at which the correction reaches full
_MAX_MULT_DELTA = 0.20       # clamp |poss_mult - 1| to keep it sane

_PACE_PRIOR_PATH = os.path.join(
    ROOT, "data", "cache", "atlas_team_pace_identity.parquet")

# League-average pace-per-game fallback (poss/48-min) if a team is uncovered AND
# we still want a defined exp pace; used only to fill ONE missing side so a game
# with one covered team still gets a (weaker) prior. Set from the atlas mean.
_LEAGUE_PACE_PG = 99.5

_PRIOR_CACHE: Optional[Dict[str, float]] = None


def is_enabled() -> bool:
    """True iff CV_INGAME_PACE_INTEL is set truthy. Default OFF."""
    v = os.environ.get(PACE_INTEL_FLAG, "")
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def load_team_pace_priors(path: str = _PACE_PRIOR_PATH) -> Dict[str, float]:
    """``{team_tricode: pace_pg}`` from atlas_team_pace_identity.parquet.

    pace_pg is per-team possessions-per-GAME (season identity). Leak-free: it is
    a pregame structural prior, not derived from any in-progress game's future.
    Cached after first load. Returns {} if the artifact is missing.
    """
    global _PRIOR_CACHE
    if _PRIOR_CACHE is not None:
        return _PRIOR_CACHE
    out: Dict[str, float] = {}
    if os.path.exists(path):
        try:
            import pandas as pd
            df = pd.read_parquet(path, columns=["team_tricode", "tempo", "value"])
            for r in df.itertuples(index=False):
                pace = None
                try:
                    t = json.loads(r.tempo) if isinstance(r.tempo, str) else r.tempo
                    if isinstance(t, dict):
                        pace = t.get("pace_pg")
                except (TypeError, ValueError, json.JSONDecodeError):
                    pace = None
                if pace is None:
                    pace = getattr(r, "value", None)
                if pace is not None:
                    try:
                        out[str(r.team_tricode)] = float(pace)
                    except (TypeError, ValueError):
                        continue
        except Exception:
            out = {}
    _PRIOR_CACHE = out
    return out


def expected_combined_ppm(home: Optional[str], away: Optional[str],
                          priors: Optional[Dict[str, float]] = None,
                          fill_missing: bool = True) -> Optional[float]:
    """Pregame expected combined pace in possessions-per-MINUTE.

    exp = (home_pace_pg + away_pace_pg) / 48  (both teams' possessions per 48
    min). Mirrors the featurizer's ``pace_poss_per_min`` = total possessions both
    teams / elapsed-minutes definition, so live_ppm and exp_ppm are commensurate.

    If one team is uncovered and ``fill_missing`` is True, fills that side with
    the league-average pace so a half-covered game still gets a (weaker) prior.
    Returns None if BOTH teams are uncovered (no prior => caller no-ops).
    """
    if priors is None:
        priors = load_team_pace_priors()
    hp = priors.get(home) if home else None
    ap = priors.get(away) if away else None
    if hp is None and ap is None:
        return None
    if fill_missing:
        hp = hp if hp is not None else _LEAGUE_PACE_PG
        ap = ap if ap is not None else _LEAGUE_PACE_PG
    elif hp is None or ap is None:
        return None
    return (float(hp) + float(ap)) / 48.0


def poss_mult_for_state(
    home_team: Optional[str],
    away_team: Optional[str],
    live_pace_ppm: float,
    played_share: float,
    *,
    priors: Optional[Dict[str, float]] = None,
    blend_live: float = _DEFAULT_BLEND_LIVE,
    ramp_share: float = _DEFAULT_RAMP_SHARE,
    max_delta: float = _MAX_MULT_DELTA,
    force: bool = False,
) -> float:
    """Leak-free remaining-possessions multiplier in [1-max_delta, 1+max_delta].

    Returns EXACTLY 1.0 (no-op) when:
      * the flag is OFF and ``force`` is False, OR
      * live_pace_ppm <= 0 (no live pace yet), OR
      * neither team has a pace prior.

    Otherwise returns blend_ppm / live_ppm, damped by a played_share ramp and
    clamped to +-max_delta. ``force=True`` lets the experiment harness compute
    the multiplier regardless of the env flag (so the A/B is deterministic).

    blend_ppm = blend_live*live + (1-blend_live)*exp  (pull live toward identity)
    poss_mult = blend_ppm / live  -> <1 when running hot, >1 when running cold.
    """
    if not force and not is_enabled():
        return 1.0
    if live_pace_ppm is None or live_pace_ppm <= 0:
        return 1.0
    exp_ppm = expected_combined_ppm(home_team, away_team, priors=priors)
    if exp_ppm is None or exp_ppm <= 0:
        return 1.0
    blend_ppm = blend_live * float(live_pace_ppm) + (1.0 - blend_live) * exp_ppm
    raw_mult = blend_ppm / float(live_pace_ppm)
    # Early-game confidence ramp: pull raw_mult toward 1.0 when little played.
    ps = max(0.0, min(1.0, float(played_share) / ramp_share)) if ramp_share > 0 \
        else 1.0
    mult = 1.0 + ps * (raw_mult - 1.0)
    # clamp
    lo, hi = 1.0 - max_delta, 1.0 + max_delta
    return float(max(lo, min(hi, mult)))


def apply_poss_mult_to_projection(current: float, projected_final: float,
                                  poss_mult: float) -> float:
    """Apply ``poss_mult`` to the REMAINING (not banked) part of a projection.

    A counting-stat / team-total projection is current(banked) + remaining. Pace
    only affects the REMAINING possessions, so we scale only the remaining part:

        adjusted = current + poss_mult * (projected_final - current)

    Never drops below ``current`` (floored). With poss_mult==1.0 this returns
    projected_final exactly (byte-identical no-op).
    """
    cur = float(current or 0.0)
    pf = float(projected_final or 0.0)
    remaining = pf - cur
    adj = cur + float(poss_mult) * remaining
    return max(cur, adj)


__all__ = [
    "PACE_INTEL_FLAG",
    "is_enabled",
    "load_team_pace_priors",
    "expected_combined_ppm",
    "poss_mult_for_state",
    "apply_poss_mult_to_projection",
]
