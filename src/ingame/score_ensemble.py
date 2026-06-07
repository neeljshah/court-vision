"""Team-score ENSEMBLE — combine each head's MEASURED strength into one output.

Measured truth from the held-out walk-forward eval curves
(``eval_possession_sim_full`` / ``ALL_FRONTS_EVAL``):

  * For the team final-score POINT estimate, the **learned-ridge** (a per-bucket
    ridge on the leak-free state row ``[home_score, away_score, margin, ...]``)
    is the best POINT estimate.
  * For the WIN PROBABILITY (Brier / LogLoss, decisive late) and the SCORE
    DISTRIBUTION / final-score-vs-production, the **possession-sim**
    (``src.sim.rest_of_game_sim.RestOfGameSim``) wins.

Neither head wins everywhere, so this module does NOT pick one — it COMBINES the
two by their measured strengths into one coherent output:

    point estimate  := ridge  (its measured strength)
    win prob        := sim    (its measured strength)
    score DISTR.    := sim    (its measured strength)
    [optional]      := re-centre the sim score samples onto the ridge point so
                       the reported uncertainty band is anchored to the better
                       point estimate WITHOUT distorting the sim's spread/shape.

This is the team-score analogue of ``unified_projector`` (which assembles the two
PLAYER-line heads). It is additive, leak-free, and reuses existing modules — it
NEVER retrains.

LEAK-FREE
---------
The sim is leak-free by construction (see ``rest_of_game_sim`` header: reads only
state<=E + optional caller priors derived from games STRICTLY before this game).
The ridge point estimate is INJECTED by the caller (``ridge_point=``), who is
responsible for deriving it leak-free (per-bucket ridge fit on games strictly
before the held-out game — exactly how the eval harness scores it). This module
does not fit or persist a ridge; it consumes the point the caller provides and,
when none is provided, transparently falls back to the sim mean (so the output is
always coherent and never invents a number).

HONESTY ON "WIN"
----------------
A combined output is only a genuine improvement if, on HELD-OUT games across the
full game-time grid, it is >= the best individual head at each bucket AND beats
production overall. That comparison is the eval harness's job (route the ridge
point + sim distribution and grade vs every component). This module is the
runtime ASSEMBLY of the measured-best pieces; it does not itself claim the win --
it produces the object the harness grades. If, when graded, simply using
"sim-where-it-wins, ridge-where-it-wins" does not beat the routed combination,
the harness should say so straight.

GPU: the sim is pure NumPy (CPU). The ridge point is injected (caller's device).
Granularity: per-event / per-snapshot; the sim advances by discrete possessions
rolled to a final-score distribution -- NOT per-second. Do not overclaim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

# Reuse the validated possession sim (do NOT retrain). Imported lazily inside the
# function that needs it so importing this module is cheap and side-effect-free.
DEFAULT_N_SIMS = 2000
DEFAULT_SEED = 0

__all__ = [
    "ScoreEnsembleResult",
    "project_score_ensemble",
    "DEFAULT_N_SIMS",
    "DEFAULT_SEED",
]


@dataclass
class ScoreEnsembleResult:
    """Coherent team-score output combining ridge point + sim distribution.

    Fields:
      * ``home_final``/``away_final`` -- the SERVED point estimate (ridge if the
        caller supplied one, else the sim mean). This is the number to display /
        bet the team line against.
      * ``margin``/``total`` -- derived from the served point estimate.
      * ``home_win_prob`` -- from the SIM (its measured strength), unchanged.
      * ``home_final_samples``/``away_final_samples`` -- the sim's score
        distribution; if ``calibrate_to_point`` was on, the score samples are
        mean-shifted onto the ridge point (spread/shape preserved).
      * ``point_source`` -- "ridge" or "sim_fallback".
      * ``winprob_source`` -- always "possession_sim".
      * ``distribution_source`` -- "possession_sim" or
        "possession_sim+ridge_recentred".
    """
    home_final: float
    away_final: float
    margin: float                       # home - away (served point)
    total: float                        # home + away (served point)
    home_win_prob: float                # from the sim
    home_final_samples: np.ndarray = field(repr=False)
    away_final_samples: np.ndarray = field(repr=False)
    n_sims: int = 0
    poss_remaining_mean: float = 0.0
    # provenance / honesty
    point_source: str = "sim_fallback"
    winprob_source: str = "possession_sim"
    distribution_source: str = "possession_sim"
    # carry the raw sim means so the caller can shadow-grade the components
    sim_home_final_mean: float = 0.0
    sim_away_final_mean: float = 0.0
    ridge_home_final: Optional[float] = None
    ridge_away_final: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "home_final": self.home_final,
            "away_final": self.away_final,
            "margin": self.margin,
            "total": self.total,
            "home_win_prob": self.home_win_prob,
            "n_sims": self.n_sims,
            "poss_remaining_mean": self.poss_remaining_mean,
            "point_source": self.point_source,
            "winprob_source": self.winprob_source,
            "distribution_source": self.distribution_source,
            "sim_home_final_mean": self.sim_home_final_mean,
            "sim_away_final_mean": self.sim_away_final_mean,
            "ridge_home_final": self.ridge_home_final,
            "ridge_away_final": self.ridge_away_final,
        }


def _coerce_ridge_point(
    ridge_point: Optional[Any],
) -> Optional[Dict[str, float]]:
    """Normalise the injected ridge point estimate into {home, away} floats.

    Accepts:
      * dict with ``home_final``/``away_final`` (or ``home_score``/``away_score``,
        or ``home``/``away``, or ``home_final_mean``/``away_final_mean``),
      * a 2-tuple/list/ndarray ``(home, away)``.
    Returns None if it can't extract two finite numbers (caller then falls back
    to the sim mean -- never invents a number).
    """
    if ridge_point is None:
        return None

    home = away = None
    if isinstance(ridge_point, dict):
        for hk, ak in (
            ("home_final", "away_final"),
            ("home_score", "away_score"),
            ("home", "away"),
            ("home_final_mean", "away_final_mean"),
        ):
            if hk in ridge_point and ak in ridge_point:
                home, away = ridge_point[hk], ridge_point[ak]
                break
    else:
        try:
            seq = list(ridge_point)
            if len(seq) >= 2:
                home, away = seq[0], seq[1]
        except TypeError:
            return None

    try:
        home = float(home)
        away = float(away)
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(home) and np.isfinite(away)):
        return None
    return {"home": home, "away": away}


def _recentre_samples(
    samples: np.ndarray, current_mean: float, target_mean: float
) -> np.ndarray:
    """Shift ``samples`` so their mean becomes ``target_mean``; keep the shape.

    A pure additive translation: variance, skew, and every quantile-WIDTH is
    preserved. This anchors the sim's UNCERTAINTY band on the better (ridge)
    point estimate without pretending the sim produced a different spread.
    """
    if samples is None or samples.size == 0:
        return samples
    return samples + (float(target_mean) - float(current_mean))


def project_score_ensemble(
    state: Dict[str, Any],
    *,
    ridge_point: Optional[Any] = None,
    priors: Optional[Dict[str, Any]] = None,
    n_sims: int = DEFAULT_N_SIMS,
    seed: int = DEFAULT_SEED,
    calibrate_to_point: bool = True,
    sim: Optional[Any] = None,
) -> ScoreEnsembleResult:
    """Combine ridge POINT + sim DISTRIBUTION/WIN-PROB into one team-score output.

    Args:
        state: the leak-free game-state ``game_row`` (as emitted by
            ``src.ingame.state_featurizer.featurize_game`` / ``featurize_live_snapshot``
            and consumed by the sim). Reads only state<=E.
        ridge_point: the learned-ridge POINT estimate for the FINAL team score,
            derived leak-free by the CALLER (per-bucket ridge fit on games strictly
            before this game -- the same construction the eval harness scores). May
            be a dict ({home_final, away_final}) or a (home, away) pair. If None /
            unparseable, the point estimate transparently FALLS BACK to the sim
            mean (``point_source="sim_fallback"``) so the output is always coherent.
        priors: optional per-team prior-form strengths for the sim
            (home_ppp/away_ppp/home_pace_per48/away_pace_per48), caller-derived
            from games strictly before this game's date. Passed through unchanged.
        n_sims / seed: possession-sim rollout count + RNG seed (deterministic).
        calibrate_to_point: when True (default) AND a ridge point is present, the
            sim's score SAMPLES are mean-shifted onto the ridge point (spread/shape
            preserved) so the reported band is anchored to the better point. The
            WIN PROBABILITY is ALWAYS taken from the un-recentred sim so that
            point-calibration can never move the measured-best win prob. Set False
            to leave the sim distribution exactly as rolled.
        sim: optional pre-constructed ``RestOfGameSim`` (skip re-construction; used
            by tests / a warm server). If None, one is built with n_sims/seed.

    Returns:
        ScoreEnsembleResult -- point estimate = ridge (its strength), win prob +
        distribution = sim (its strength), optionally mean-anchored to the ridge.
    """
    # Lazy import so importing this module is side-effect-free.
    from src.sim.rest_of_game_sim import RestOfGameSim

    if sim is None:
        sim = RestOfGameSim(n_sims=int(n_sims), seed=int(seed))
    res = sim.simulate(state, priors=priors)

    # WIN PROB is the sim's strength -- taken from the ORIGINAL roll, never moved
    # by point-calibration (preserve the measured-best win prob exactly).
    home_win_prob = float(res.home_win_prob)

    sim_home_mean = float(res.home_final_mean)
    sim_away_mean = float(res.away_final_mean)

    ridge = _coerce_ridge_point(ridge_point)

    # --- POINT estimate := ridge (measured-best), else sim mean fallback. ---
    if ridge is not None:
        home_final = ridge["home"]
        away_final = ridge["away"]
        point_source = "ridge"
        ridge_home = ridge["home"]
        ridge_away = ridge["away"]
    else:
        home_final = sim_home_mean
        away_final = sim_away_mean
        point_source = "sim_fallback"
        ridge_home = None
        ridge_away = None

    # --- DISTRIBUTION := sim, optionally re-centred onto the ridge point. ---
    home_samples = res.home_final_samples
    away_samples = res.away_final_samples
    distribution_source = "possession_sim"
    if calibrate_to_point and ridge is not None:
        home_samples = _recentre_samples(home_samples, sim_home_mean, ridge["home"])
        away_samples = _recentre_samples(away_samples, sim_away_mean, ridge["away"])
        distribution_source = "possession_sim+ridge_recentred"

    return ScoreEnsembleResult(
        home_final=float(home_final),
        away_final=float(away_final),
        margin=float(home_final - away_final),
        total=float(home_final + away_final),
        home_win_prob=home_win_prob,
        home_final_samples=home_samples,
        away_final_samples=away_samples,
        n_sims=int(res.n_sims),
        poss_remaining_mean=float(res.poss_remaining_mean),
        point_source=point_source,
        winprob_source="possession_sim",
        distribution_source=distribution_source,
        sim_home_final_mean=sim_home_mean,
        sim_away_final_mean=sim_away_mean,
        ridge_home_final=ridge_home,
        ridge_away_final=ridge_away,
    )
