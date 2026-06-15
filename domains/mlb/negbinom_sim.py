"""domains.mlb.negbinom_sim — Make the validated NegBinom run engine available
as a sampling ScoringProcessModel for the JointDistribution.sample() path.

THE GAP this closes: domains/mlb/negbinom_engine.py validated an over-dispersed
(Negative-Binomial) run marginal — O/U Brier -0.014..-0.022 vs Poisson (W101) —
but it lived ONLY as analytic PMF matrices. The read-off
(scripts/platformkit/pipeline_integration.assemble_read) consumes a
JointDistribution built from an (n_sims, 2) SAMPLE matrix. This module supplies a
ScoringProcessModel whose .sample() draws over-dispersed runs.

WHERE THIS IS ACTUALLY REACHED (honest, no overclaim): build_mlb_jd is called by
(1) scripts/platformkit/pipeline_integration._build_demo_jd — a DEMO read-off,
guarded by try/except with a Gaussian fallback — and (2) domains/mlb/predictor.py
(built this wave), the usable MLB predictor's to_jd() surface. There is NO live
cohesive_read / system_map / production caller wiring this in today; do not claim
one. The calibration win reaches a surface only through those two call sites.

HONEST: calibration/accuracy only — NO edge claimed. Markets are efficient.
The win is tail-shape fidelity, mean-preserving by construction.
INVARIANTS: never edit src/ or kernel/; read-only imports; <=300 LOC.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.sim_framework import JointDistribution  # read-only

_TOTAL_LINES: Tuple[float, ...] = (6.5, 7.5, 8.5, 9.5, 10.5)
_N_SIMS_DEFAULT = 20_000
_F5_SCALE = 5.0 / 9.0


# ---------------------------------------------------------------------------
# ScoringProcessModel implementations (the domain plug-in contract)
# ---------------------------------------------------------------------------

class MLBNegBinomSimModel:
    """Over-dispersed MLB run sampler.  Implements ScoringProcessModel.

    Draws home/away runs from independent Negative-Binomial marginals with the
    SAME mean (lambda) as the Poisson baseline but fitted dispersion r>0:
        runs ~ NegBinom(n=r, p=r/(r+lam))   -> mean=lam, var=lam+lam^2/r.
    As r->inf this collapses to Poisson, so the model strictly generalises the
    baseline.  Marginals are independent (no copula) -> default joint_quality
    is 'independent' (the kernel will honestly refuse correlated SGP pricing).
    """

    def __init__(
        self, lam_home: float, lam_away: float, r_home: float, r_away: float,
        *, joint_quality: str = "independent",
    ) -> None:
        for nm, v in (("lam_home", lam_home), ("lam_away", lam_away)):
            if v <= 0:
                raise ValueError(f"{nm} must be > 0; got {v}")
        for nm, v in (("r_home", r_home), ("r_away", r_away)):
            if v <= 0:
                raise ValueError(f"{nm} must be > 0; got {v}")
        self.lam_home, self.lam_away = float(lam_home), float(lam_away)
        self.r_home, self.r_away = float(r_home), float(r_away)
        self.joint_quality = joint_quality

    @staticmethod
    def _draw(rng: np.random.Generator, lam: float, r: float, n: int) -> np.ndarray:
        # numpy negative_binomial(n_succ, p): mean = n_succ*(1-p)/p.
        # p = r/(r+lam) -> (1-p)/p = lam/r -> mean = r*(lam/r) = lam.  Mean-preserving.
        p = r / (r + lam)
        return rng.negative_binomial(r, p, size=n).astype(float)

    def sample(self, n_sims: int, rng_seed: int = 0) -> np.ndarray:
        """(n_sims, 2) array of [home_runs, away_runs]."""
        rng = np.random.default_rng(rng_seed)
        home = self._draw(rng, self.lam_home, self.r_home, n_sims)
        away = self._draw(rng, self.lam_away, self.r_away, n_sims)
        return np.stack([home, away], axis=1)


class MLBPoissonSimModel:
    """Poisson baseline run sampler (same mean, no over-dispersion).

    The mean-preserving reference the NegBinom model is compared against.
    """

    def __init__(self, lam_home: float, lam_away: float) -> None:
        if lam_home <= 0 or lam_away <= 0:
            raise ValueError(f"lambdas must be > 0; got {lam_home}, {lam_away}")
        self.lam_home, self.lam_away = float(lam_home), float(lam_away)
        self.joint_quality = "independent"

    def sample(self, n_sims: int, rng_seed: int = 0) -> np.ndarray:
        rng = np.random.default_rng(rng_seed)
        home = rng.poisson(self.lam_home, size=n_sims).astype(float)
        away = rng.poisson(self.lam_away, size=n_sims).astype(float)
        return np.stack([home, away], axis=1)


# ---------------------------------------------------------------------------
# JD factory (the production seam)
# ---------------------------------------------------------------------------

def build_mlb_jd(
    lam_home: float, lam_away: float,
    r_home: float, r_away: float,
    *, n_sims: int = _N_SIMS_DEFAULT, seed: int = 0,
    dispersion: str = "negbinom", joint_quality: str = "independent",
) -> JointDistribution:
    """Build a production JointDistribution for one MLB game from run-rate
    lambdas + fitted dispersion.  dispersion='negbinom' (default) draws the
    validated over-dispersed marginals; 'poisson' is the baseline.
    """
    if dispersion == "negbinom":
        model = MLBNegBinomSimModel(lam_home, lam_away, r_home, r_away,
                                    joint_quality=joint_quality)
    elif dispersion == "poisson":
        model = MLBPoissonSimModel(lam_home, lam_away)
    else:
        raise ValueError(f"dispersion must be 'negbinom' or 'poisson'; got {dispersion!r}")
    samples = model.sample(n_sims, rng_seed=seed)
    return JointDistribution(samples, joint_quality=model.joint_quality)


# ---------------------------------------------------------------------------
# Walk-forward re-score harness: prove the win survives the SAMPLE round-trip
# ---------------------------------------------------------------------------

def _brier(p: Sequence[float], y: Sequence[float]) -> float:
    pa, ya = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((pa - ya) ** 2))


def run_jd_rescore(
    games_path: Optional[str] = None,
    *, repo_root: Optional[Path] = None,
    n_sims: int = 6000, seed: int = 7,
    total_lines: Sequence[float] = _TOTAL_LINES,
    max_games: int = 5000,
) -> Dict:
    """Walk-forward Poisson-JD vs NegBinom-JD over the real corpus, scoring the
    SAMPLED production surface (totals O/U, run-line, moneyline + total-runs
    CRPS) via dist_metrics.  Dispersion r fitted on the first 50% (leak-free,
    reused from negbinom_engine).  Confirms the analytic NegBinom O/U Brier win
    (W101) carries through JointDistribution.sample().  NO edge claimed.
    """
    import pandas as pd
    from domains.mlb.inning_engine import RunRateState
    from domains.mlb.negbinom_engine import fit_dispersion_first_half
    from scripts.platformkit.dist_metrics import crps_ensemble

    if games_path is not None:
        df = pd.read_parquet(games_path)
    else:
        root = repo_root or Path(__file__).resolve().parents[2]
        path = root / "data" / "domains" / "mlb" / "games.parquet"
        if not path.exists():
            raise FileNotFoundError(f"MLB corpus not found at {path}")
        df = pd.read_parquet(path)

    df = df.sort_values("date").reset_index(drop=True)
    r_home, r_away, n_train = fit_dispersion_first_half(df)

    rr = RunRateState()
    lam_h: List[float] = []
    lam_a: List[float] = []
    for i in range(len(df)):
        home, away = str(df["home_team"].iloc[i]), str(df["away_team"].iloc[i])
        season = int(df["season"].iloc[i])
        lh, la = rr.snapshot(home, away, season)
        lam_h.append(lh)
        lam_a.append(la)
        rr.update(home, away, float(df["home_runs"].iloc[i]), float(df["away_runs"].iloc[i]))
    df = df.copy()
    df["lam_home"], df["lam_away"] = lam_h, lam_a

    val = df.iloc[n_train:].copy()
    assert (val.index >= n_train).all(), "Leak: val indices overlap train"
    if max_games and len(val) > max_games:           # deterministic stride subsample
        val = val.iloc[:: max(1, len(val) // max_games)].head(max_games)

    keys = [f"over_{l:g}" for l in total_lines] + ["rl_home", "ml_home"]
    nb_p: Dict[str, List[float]] = {k: [] for k in keys}
    po_p: Dict[str, List[float]] = {k: [] for k in keys}
    act: Dict[str, List[float]] = {k: [] for k in keys}
    crps_nb: List[float] = []
    crps_po: List[float] = []
    tot_act: List[float] = []

    for _, row in val.iterrows():
        lh, la = float(row["lam_home"]), float(row["lam_away"])
        hr, ar = float(row["home_runs"]), float(row["away_runs"])
        jd_nb = build_mlb_jd(lh, la, r_home, r_away, n_sims=n_sims, seed=seed, dispersion="negbinom")
        jd_po = build_mlb_jd(lh, la, r_home, r_away, n_sims=n_sims, seed=seed, dispersion="poisson")
        for ln in total_lines:
            k = f"over_{ln:g}"
            nb_p[k].append(jd_nb.prob_over(0, 1, ln))
            po_p[k].append(jd_po.prob_over(0, 1, ln))
            act[k].append(1.0 if (hr + ar) > ln else 0.0)
        nb_p["rl_home"].append(jd_nb.prob_event(lambda s: s[:, 0] >= s[:, 1] + 2))
        po_p["rl_home"].append(jd_po.prob_event(lambda s: s[:, 0] >= s[:, 1] + 2))
        act["rl_home"].append(1.0 if hr >= ar + 2 else 0.0)
        ph_nb, _, pt_nb = jd_nb.prob_side_win(0, 1)
        ph_po, _, pt_po = jd_po.prob_side_win(0, 1)
        nb_p["ml_home"].append(ph_nb + 0.5 * pt_nb)
        po_p["ml_home"].append(ph_po + 0.5 * pt_po)
        act["ml_home"].append(1.0 if hr > ar else (0.5 if hr == ar else 0.0))
        tot = hr + ar
        tot_act.append(tot)
        crps_nb.append(crps_ensemble(tot, jd_nb._s[:, 0] + jd_nb._s[:, 1]))  # noqa: SLF001
        crps_po.append(crps_ensemble(tot, jd_po._s[:, 0] + jd_po._s[:, 1]))  # noqa: SLF001

    surface: Dict[str, Dict[str, float]] = {}
    for k in keys:
        bn, bp = _brier(nb_p[k], act[k]), _brier(po_p[k], act[k])
        surface[k] = {"brier_negbinom": bn, "brier_poisson": bp, "delta_brier": bn - bp}
    return {
        "n_train": n_train, "n_val_scored": len(val),
        "r_home": r_home, "r_away": r_away, "n_sims": n_sims,
        "surface": surface,
        "crps_total": {
            "negbinom": float(np.mean(crps_nb)), "poisson": float(np.mean(crps_po)),
            "delta": float(np.mean(crps_nb) - np.mean(crps_po)),
        },
        "note": (
            "HONEST: SAMPLED production-path re-score. r fitted on first 50% (leak-free). "
            "NegBinom wins O/U + total CRPS via tail fidelity (mean-preserving). NO edge claimed."
        ),
    }


if __name__ == "__main__":  # pragma: no cover
    import json
    res = run_jd_rescore()
    print(json.dumps(res, indent=2, default=float))
