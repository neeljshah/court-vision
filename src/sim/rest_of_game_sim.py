"""Possession-level rest-of-game Monte-Carlo simulator (FRONT A).

Given a mid-game state row (the leak-free game-state dict emitted by
``src.ingame.state_featurizer.featurize_game`` at some event/grid point E), roll
the REST of the game forward possession-by-possession to a distribution over the
FINAL score, and from that a home win probability.

LEAK-FREE BY CONSTRUCTION
-------------------------
``simulate(game_row, ...)`` reads ONLY:
  * the current state row (score, clock, per-team four-factors-SO-FAR, possession
    counts, pace) -- all of which are pure functions of events <= E in THIS game
    (truncation-invariant, tested in tests/test_ingame_leak_free.py), and
  * an OPTIONAL ``priors`` dict of per-team strengths (ppp / pace) the CALLER
    derives from games strictly BEFORE this game's date -- a game-constant
    injected once, never future state.
No field of ``game_row`` that depends on events after E is touched. The sim is
therefore safe to score walk-forward on held-out games.

INTENDED INTERFACE (stable; a learned possession model can be slotted in later)
-------------------------------------------------------------------------------
    sim = RestOfGameSim(n_sims=2000, model=None, seed=0)
    res = sim.simulate(game_row, priors=None)         # SimResult
    res.home_final_mean, res.away_final_mean          # E[final score]
    res.margin_mean, res.total_mean                   # E[margin], E[total]
    res.home_win_prob                                 # P(home wins) incl. OT
    res.home_final_samples / res.away_final_samples   # np arrays (n_sims,)

``model`` is an optional ``PossessionModel`` (duck-typed): given a per-team
"offense state" it returns (p_score_event, points_if_score). The DEFAULT model
is ``EmpiricalPossessionModel`` -- a closed-form / empirical-Bayes estimator of
each team's points-per-possession and possessions-remaining from the four-factors
so far, shrunk toward a league prior (and toward the caller's prior-form pace if
supplied). This makes the module runnable TODAY without a separately-trained
possession network.

> TODO(learned-possession-model): replace ``EmpiricalPossessionModel`` with a
>   ``src/sim/possession_model.py`` that learns P(outcome | possession-state)
>   from the ~1.1M historical PBP possessions (walk-forward, leak-free per the
>   __init__ contract) and inject it via the ``model=`` arg. The eval harness
>   (scripts/ingame/eval_possession_sim.py) already scores whatever model is
>   injected, so swapping it in requires no harness change.

Granularity honesty: the sim advances by discrete POSSESSIONS, not wall-clock
seconds. The number of possessions remaining is derived from time + pace; between
possessions nothing changes. This is "per-possession, rolled to a final-score
distribution", NOT sub-event/per-second resolution -- do not overclaim.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

# Regulation/OT lengths (kept local so this module has no hard import of the
# featurizer; values mirror src.ingame.state_featurizer).
REG_GAME_LEN_SEC = 2880          # 48 min
OT_PERIOD_LEN = 300              # 5 min
_OT_HALF_SEC = OT_PERIOD_LEN     # one OT period

# League priors (empirical-Bayes shrinkage targets). These are season-agnostic
# constants, NOT as-of-today aggregates -> not a leak. ppp ~ points per
# possession; pace ~ possessions per 48 for ONE team.
LEAGUE_PPP = 1.12                # league avg points per possession (~modern NBA)
LEAGUE_PACE_PER48 = 99.0         # one team's possessions per 48 min
# Shrinkage strength: equivalent "prior possessions" of weight on the league
# mean. With ~50 real possessions by halftime, k=40 means roughly half-weight on
# the in-game rate at the half, more on the prior earlier. Conservative on
# purpose; the eval will say whether more/less in-game weight wins.
PPP_PRIOR_K = 40.0
PACE_PRIOR_K = 25.0

# ---------------------------------------------------------------------------
# CV_LATE_FOUL_STATE: possession-count inflation for intentional-foul sequences
# in late-game trailing situations.
#
# When a trailing team intentionally fouls in the last ~3 min with the opponent
# in the bonus, possessions-per-minute roughly doubles (foul stop → 2 FTs →
# rebound → new possession, ~all within 15-20 s).  This inflates the effective
# remaining possessions above the pure-pace extrapolation.
#
# Inflation formula (linear in trailing margin, capped):
#   inflation = 1 + LATE_FOUL_INFLATION_BASE * margin_factor
# where margin_factor ramps from 0 at margin=0 to 1 at LATE_FOUL_FULL_MARGIN.
#
# Default OFF when flag unset → byte-identical to baseline.
# ---------------------------------------------------------------------------
_LATE_FOUL_REM_THRESHOLD = 180.0   # <= 3 min remaining triggers check
_LATE_FOUL_INFLATION_BASE = 0.20   # up to 20% more possessions at full deficit
_LATE_FOUL_FULL_MARGIN = 10.0      # |margin| >= 10 → full inflation factor
_LATE_FOUL_BONUS_ONLY = True       # only inflate when opp already in bonus


def _cv_late_foul_state_enabled() -> bool:
    """Return True when CV_LATE_FOUL_STATE is set to a truthy value."""
    return os.environ.get("CV_LATE_FOUL_STATE", "0").strip() not in (
        "0", "", "false", "False"
    )


def _late_foul_poss_inflation(game_row: Dict[str, Any]) -> float:
    """Compute possession-count inflation factor for late-game fouling.

    Returns 1.0 (no change) unless:
    - CV_LATE_FOUL_STATE is enabled
    - game_remaining_sec <= _LATE_FOUL_REM_THRESHOLD (<=3 min left)
    - one team is trailing (|score_margin| > 0)
    - when _LATE_FOUL_BONUS_ONLY: the fouled team is already in the bonus
      (trailing team has committed 5+ fouls → opponent in bonus → every foul
      yields FTs)

    Leak-free: reads only state <= E (scores, fouls, clock).
    """
    if not _cv_late_foul_state_enabled():
        return 1.0
    rem_sec = _f(game_row, "game_remaining_sec")
    if rem_sec > _LATE_FOUL_REM_THRESHOLD or rem_sec <= 0:
        return 1.0
    margin = _f(game_row, "score_margin")       # home - away; negative = home trailing
    abs_margin = abs(margin)
    if abs_margin < 1.0:
        return 1.0                              # tied game — no intentional fouling

    # Check bonus state: is the trailing team in the penalty?
    # (state_featurizer convention: home_in_bonus=1 means HOME has 5+ fouls
    # in the period → HOME is in the penalty → any HOME foul → AWAY FTs.)
    # For trailing HOME to foul intentionally effectively, HOME must be in
    # the penalty (home_in_bonus=1).
    if _LATE_FOUL_BONUS_ONLY:
        if margin < 0:
            # home is trailing → home fouls intentionally → need home_in_bonus == 1
            in_bonus = int(_f(game_row, "home_in_bonus"))
        else:
            # away is trailing → away fouls intentionally → need away_in_bonus == 1
            in_bonus = int(_f(game_row, "away_in_bonus"))
        if not in_bonus:
            return 1.0

    # Linear ramp: 0 at margin=0, full inflation at LATE_FOUL_FULL_MARGIN
    margin_factor = min(1.0, abs_margin / _LATE_FOUL_FULL_MARGIN)
    inflation = 1.0 + _LATE_FOUL_INFLATION_BASE * margin_factor
    return float(inflation)


@dataclass
class SimResult:
    """Final-score / win-prob distribution from a rest-of-game roll."""
    home_final_mean: float
    away_final_mean: float
    margin_mean: float            # home - away
    total_mean: float             # home + away
    home_win_prob: float          # includes simulated OT resolution
    home_final_samples: np.ndarray = field(repr=False)
    away_final_samples: np.ndarray = field(repr=False)
    n_sims: int = 0
    poss_remaining_mean: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "home_final_mean": self.home_final_mean,
            "away_final_mean": self.away_final_mean,
            "margin_mean": self.margin_mean,
            "total_mean": self.total_mean,
            "home_win_prob": self.home_win_prob,
            "n_sims": self.n_sims,
            "poss_remaining_mean": self.poss_remaining_mean,
        }


def _f(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    v = row.get(key, default)
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _shrunk_ppp(points_so_far: float, poss_so_far: float,
                prior_ppp: Optional[float]) -> float:
    """Empirical-Bayes points-per-possession.

    Blend the in-game rate (points/possession SO FAR) with a prior (the caller's
    prior-form ppp if supplied, else the league mean) using PPP_PRIOR_K pseudo-
    possessions. Pure function of state<=E + a game-constant prior -> leak-free.
    """
    target = prior_ppp if (prior_ppp is not None and prior_ppp > 0) else LEAGUE_PPP
    if poss_so_far <= 0:
        return target
    in_game = points_so_far / poss_so_far
    w = poss_so_far / (poss_so_far + PPP_PRIOR_K)
    return w * in_game + (1.0 - w) * target


def _shrunk_pace_per48(total_poss: float, game_elapsed_sec: float,
                       prior_pace_per48: Optional[float]) -> float:
    """Empirical-Bayes possessions-per-48 (combined both teams scaled to one).

    ``total_poss`` counts BOTH teams; per-48 here is the COMBINED tempo divided
    by 2 so it is comparable to a single team's pace prior. Blend in-game tempo
    with the prior using PACE_PRIOR_K.
    """
    target = (prior_pace_per48 if (prior_pace_per48 is not None and prior_pace_per48 > 0)
              else LEAGUE_PACE_PER48)
    if game_elapsed_sec <= 0 or total_poss <= 0:
        return target
    # combined possessions per 48 min, then halve to one-team basis
    combined_per48 = total_poss * (REG_GAME_LEN_SEC / game_elapsed_sec)
    one_team_per48 = combined_per48 / 2.0
    # weight by elapsed game fraction (more time -> trust in-game tempo more)
    w_units = total_poss / 2.0
    w = w_units / (w_units + PACE_PRIOR_K)
    return w * one_team_per48 + (1.0 - w) * target


class EmpiricalPossessionModel:
    """Default leak-free possession model: per-team ppp + scoring-event params
    estimated from the four-factors so far, shrunk to a prior.

    Exposes ``team_params(game_row, side, priors)`` -> dict with:
      * ``ppp``           : expected points per possession (shrunk)
      * ``p_score``       : P(possession yields >0 points)
      * ``mean_pts_score``: E[points | scored]  (so ppp = p_score*mean_pts_score)
    A possession's points are drawn as: Bernoulli(p_score) then a small discrete
    points distribution (2/3 weighted by the team's 3PA share) calibrated so the
    mean equals ``ppp``. This keeps variance realistic without a learned net.
    """

    def team_params(self, game_row: Dict[str, Any], side: str,
                    priors: Optional[Dict[str, Any]]) -> Dict[str, float]:
        pts = _f(game_row, f"{side}_score")
        poss = _f(game_row, f"{side}_poss")
        prior_ppp = None
        if priors:
            prior_ppp = priors.get(f"{side}_ppp")
        ppp = _shrunk_ppp(pts, poss, prior_ppp)
        # scoring-event probability: derive from eFG-so-far + FT-rate, shrunk.
        # p_score ~ fraction of possessions that end in >=1 point. Use the team's
        # made-shot + FT proxy; fall back to ppp/avg_pts mapping.
        fgm = _f(game_row, f"{side}_fgm")
        ftm = _f(game_row, f"{side}_ftm")
        # scoring possessions proxy: made FGs + (made FT trips). Bounded blend
        # with a league-ish 0.50 base via the same poss-weight idea.
        scoring_events = fgm + 0.5 * ftm
        if poss > 0:
            in_game_pscore = min(0.95, scoring_events / poss)
        else:
            in_game_pscore = 0.50
        w = poss / (poss + PPP_PRIOR_K) if poss > 0 else 0.0
        p_score = w * in_game_pscore + (1.0 - w) * 0.50
        p_score = float(min(0.95, max(0.20, p_score)))
        mean_pts_score = ppp / p_score if p_score > 1e-6 else 2.0
        # 3-point tendency (for variance shape): 3PA share so far
        fg3a = _f(game_row, f"{side}_fg3a")
        fga = _f(game_row, f"{side}_fga")
        three_share = (fg3a / fga) if fga > 0 else 0.35
        return {
            "ppp": ppp,
            "p_score": p_score,
            "mean_pts_score": float(max(1.5, min(3.2, mean_pts_score))),
            "three_share": float(min(0.6, max(0.1, three_share))),
        }


class RestOfGameSim:
    """Monte-Carlo rest-of-game roller producing a final-score / win-prob dist."""

    def __init__(self, n_sims: int = 2000, model: Optional[Any] = None,
                 seed: int = 0):
        self.n_sims = int(n_sims)
        self.model = model if model is not None else EmpiricalPossessionModel()
        self.rng = np.random.default_rng(seed)

    # -- possessions remaining ------------------------------------------------
    def _poss_remaining(self, game_row: Dict[str, Any],
                        priors: Optional[Dict[str, Any]]) -> float:
        """Expected possessions remaining FOR EACH TEAM (symmetric split).

        When CV_LATE_FOUL_STATE is enabled and the game is in a late-game
        intentional-foul situation (trailing team fouling with opp in bonus,
        <=3 min remaining), inflates the possession count to reflect the
        accelerated-clock effect of intentional-foul sequences.  Flag OFF =>
        byte-identical to baseline.
        """
        rem_sec = _f(game_row, "game_remaining_sec")
        if rem_sec <= 0:
            return 0.0
        total_poss = _f(game_row, "total_poss_count")
        if total_poss <= 0:
            total_poss = _f(game_row, "home_poss") + _f(game_row, "away_poss")
        elapsed = _f(game_row, "game_elapsed_sec")
        prior_pace = None
        if priors:
            hp = priors.get("home_pace_per48")
            ap = priors.get("away_pace_per48")
            both = [p for p in (hp, ap) if p]
            prior_pace = float(np.mean(both)) if both else None
        one_team_per48 = _shrunk_pace_per48(total_poss, elapsed, prior_pace)
        # possessions remaining for ONE team over remaining regulation seconds
        one_team_rem = one_team_per48 * (rem_sec / REG_GAME_LEN_SEC)
        # CV_LATE_FOUL_STATE: inflate possessions in intentional-foul situations
        inflation = _late_foul_poss_inflation(game_row)
        one_team_rem *= inflation
        return float(max(0.0, one_team_rem))

    # -- per-possession point draw -------------------------------------------
    def _draw_points(self, n: int, params: Dict[str, float]) -> np.ndarray:
        """Vectorized points for ``n`` possessions of one team."""
        if n <= 0:
            return np.zeros(0)
        p_score = params["p_score"]
        mean_pts = params["mean_pts_score"]
        three_share = params["three_share"]
        scored = self.rng.random(n) < p_score
        # conditional-on-scoring points: mix of 2 and 3 (and occasional 1-pt FT
        # finishes / 4-pt plays folded into the mean). Build a small categorical
        # whose mean ~= mean_pts.
        # Base outcomes {1,2,3}; tune weights so expectation == mean_pts.
        # Let weights w1,w2,w3. Fix w3 ~ three_share*0.9, solve 1*w1+2*w2+3*w3.
        w3 = min(0.6, three_share * 0.9)
        # remaining mass on {1,2}; choose w1 to hit the target mean.
        rem = 1.0 - w3
        # mean from {1,2} part must be (mean_pts - 3*w3)/rem
        target_12 = (mean_pts - 3.0 * w3) / rem if rem > 1e-6 else 2.0
        target_12 = min(2.0, max(1.0, target_12))
        w2 = (target_12 - 1.0)           # P(2) within the {1,2} block
        w2 = min(1.0, max(0.0, w2))
        w1 = 1.0 - w2
        probs = np.array([w1 * rem, w2 * rem, w3])
        probs = probs / probs.sum()
        draws = self.rng.choice([1, 2, 3], size=n, p=probs)
        return np.where(scored, draws, 0).astype(float)

    def _sim_segment_points(self, params: Dict[str, float],
                            poss_per_sim: int) -> np.ndarray:
        """Total points for each of n_sims, each playing ``poss_per_sim`` poss."""
        if poss_per_sim <= 0:
            return np.zeros(self.n_sims)
        flat = self._draw_points(self.n_sims * poss_per_sim, params)
        return flat.reshape(self.n_sims, poss_per_sim).sum(axis=1)

    # -- main -----------------------------------------------------------------
    def simulate(self, game_row: Dict[str, Any],
                 priors: Optional[Dict[str, Any]] = None) -> SimResult:
        """Roll the rest of the game; return final-score / win-prob distribution.

        Leak-free: reads only state<=E from ``game_row`` + optional caller priors.
        """
        home_now = _f(game_row, "home_score")
        away_now = _f(game_row, "away_score")
        hp = self.model.team_params(game_row, "home", priors)
        ap = self.model.team_params(game_row, "away", priors)

        rem = self._poss_remaining(game_row, priors)
        # round possessions remaining; both teams get ~equal possessions
        poss_each = int(round(rem))
        if poss_each <= 0 and _f(game_row, "game_remaining_sec") > 0:
            poss_each = 1

        home_add = self._sim_segment_points(hp, poss_each)
        away_add = self._sim_segment_points(ap, poss_each)
        home_fin = home_now + home_add
        away_fin = away_now + away_add

        # resolve ties with simulated OT periods (one team's ppp over ~OT poss)
        ot_poss = max(1, int(round(self._ot_poss(game_row, priors))))
        tied = np.isclose(home_fin, away_fin)
        max_ot = 4
        ot_round = 0
        while tied.any() and ot_round < max_ot:
            idx = np.where(tied)[0]
            h_ot = self._draw_block(hp, len(idx), ot_poss)
            a_ot = self._draw_block(ap, len(idx), ot_poss)
            home_fin[idx] += h_ot
            away_fin[idx] += a_ot
            tied = np.isclose(home_fin, away_fin)
            ot_round += 1
        # any still-tied: coin flip (rare)
        still = np.isclose(home_fin, away_fin)
        if still.any():
            flip = self.rng.random(still.sum()) < 0.5
            home_fin[np.where(still)[0][flip]] += 1
            away_fin[np.where(still)[0][~flip]] += 1

        margin = home_fin - away_fin
        return SimResult(
            home_final_mean=float(home_fin.mean()),
            away_final_mean=float(away_fin.mean()),
            margin_mean=float(margin.mean()),
            total_mean=float((home_fin + away_fin).mean()),
            home_win_prob=float((home_fin > away_fin).mean()),
            home_final_samples=home_fin,
            away_final_samples=away_fin,
            n_sims=self.n_sims,
            poss_remaining_mean=float(poss_each),
        )

    def _draw_block(self, params: Dict[str, float], n_rows: int,
                    poss: int) -> np.ndarray:
        if n_rows <= 0 or poss <= 0:
            return np.zeros(n_rows)
        flat = self._draw_points(n_rows * poss, params)
        return flat.reshape(n_rows, poss).sum(axis=1)

    def _ot_poss(self, game_row: Dict[str, Any],
                 priors: Optional[Dict[str, Any]]) -> float:
        total_poss = _f(game_row, "total_poss_count")
        elapsed = _f(game_row, "game_elapsed_sec")
        prior_pace = None
        if priors:
            both = [p for p in (priors.get("home_pace_per48"),
                                priors.get("away_pace_per48")) if p]
            prior_pace = float(np.mean(both)) if both else None
        one_team_per48 = _shrunk_pace_per48(total_poss, elapsed, prior_pace)
        return one_team_per48 * (_OT_HALF_SEC / REG_GAME_LEN_SEC)
