"""S675 acceptance simulations for multiplicity_haircut (spec + AMENDMENT 1, all settings frozen).

Run once:  python3 -m scripts.platformkit.eval_gate.multiplicity_nullcheck
Prints one JSON object. NOISE-60 (seeds 0..199), NULL-40 (1000..1199), PLANTED +0.6 sd
(2000..2199), and a report-only power line at +0.35 sd (3000..3199). Each family draws
X = default_rng(seed).standard_normal((K, 80)) and bootstraps with the same seed.
Pure simulation: reads no data, writes no file, charges no ledger.
"""
from __future__ import annotations

import json
import math
import sys
from typing import Sequence

import numpy as np
from scipy import stats

from scripts.platformkit.eval_gate.multiplicity_haircut import BETTER, haircut

ALPHA, N_BOOTSTRAP, N_GAMES, BLOCK = 0.05, 199, 80, 5.0
NOISE_SEED0, NULL_SEED0, PLANTED_SEED0, POWER_SEED0 = 0, 1000, 2000, 3000
PLANTED_SHIFT, POWER_SHIFT = 0.6, 0.35
BAR_NOISE60_MAX, BAR_NULL40_SHARE, BAR_PLANTED_SHARE, BAR_PLANTED_TOL = 3, 0.05, 0.95, 0.05


def family(seed: int, k: int, shift0: float = 0.0) -> list:
    """The frozen data generation: one rng per seed, a (K, 80) standard-normal block."""
    x = np.random.default_rng(seed).standard_normal((k, N_GAMES))
    x[0] += shift0
    ids = ["g%03d" % i for i in range(N_GAMES)]
    return [{"name": "arm%02d" % j, "diffs": x[j].tolist(), "game_ids": ids} for j in range(k)]


def run_family(seed: int, k: int, shift0: float = 0.0) -> dict:
    rep = haircut(family(seed, k, shift0), alpha=ALPHA, n_bootstrap=N_BOOTSTRAP, seed=seed,
                  mean_block_length=BLOCK)
    arms = rep["arms"]
    return {"arms": arms,
            "better": sum(a["label"] == BETTER for a in arms),
            "raw": sum(a["raw_p"] <= ALPHA for a in arms),
            "holm_any": any(a["holm_p"] <= ALPHA and a["mean_diff"] > 0 for a in arms),
            "rw_any": any(a["romano_wolf_p"] <= ALPHA and a["mean_diff"] > 0 for a in arms),
            "spa_any": rep["family"]["spa_family_p"] <= ALPHA}


def clopper_pearson(x: int, n: int) -> list:
    lo = 0.0 if x == 0 else float(stats.beta.ppf(0.025, x, n - x + 1))
    hi = 1.0 if x == n else float(stats.beta.ppf(0.975, x + 1, n - x))
    return [round(lo, 6), round(hi, 6)]


def count_line(x: int, n: int) -> dict:
    """Count, share, 95 pct Clopper-Pearson interval, and P(Bin(n, 0.05) >= x)."""
    return {"count": int(x), "n": int(n), "share": x / n, "cp95": clopper_pearson(x, n),
            "tail_p_bin_0.05": float(stats.binom.sf(x - 1, n, ALPHA))}


def null_check(n_seeds: int = 200) -> dict:
    """All acceptance and report-only lines; n_seeds < 200 is a smoke subset, not acceptance."""
    noise = [run_family(NOISE_SEED0 + s, 60) for s in range(n_seeds)]
    null = [run_family(NULL_SEED0 + s, 40) for s in range(n_seeds)]
    planted = [run_family(PLANTED_SEED0 + s, 40, PLANTED_SHIFT) for s in range(n_seeds)]
    power = [run_family(POWER_SEED0 + s, 40, POWER_SHIFT) for s in range(n_seeds)]
    survivors = [r["better"] for r in noise]
    null_any = sum(r["better"] > 0 for r in null)
    p_hit = sum(r["arms"][0]["label"] == BETTER for r in planted)
    p_est = float(np.mean([r["arms"][0]["mean_diff"] for r in planted]))   # unconditional
    w_hit = sum(r["arms"][0]["label"] == BETTER for r in power)
    t_crit = float(stats.t.isf(ALPHA / 40, N_GAMES - 1))
    analytic = float(stats.nct.sf(t_crit, N_GAMES - 1, POWER_SHIFT * math.sqrt(N_GAMES)))
    comp = {name: {key: count_line(sum(r[key] for r in rows), n_seeds)
                   for key in ("holm_any", "rw_any", "spa_any")}
            for name, rows in (("noise60", noise), ("null40", null))}
    out = {
        "settings": {"n_seeds": n_seeds, "n_games": N_GAMES, "n_bootstrap": N_BOOTSTRAP,
                     "alpha": ALPHA, "mean_block_length": BLOCK},
        "a_noise60": {"max_survivors": int(max(survivors)), "bar_max": BAR_NOISE60_MAX,
                      "total_survivors": int(sum(survivors)),
                      "mean_survivors": float(np.mean(survivors)),
                      "seeds_with_any": count_line(sum(x > 0 for x in survivors), n_seeds),
                      "raw_unadjusted_max": int(max(r["raw"] for r in noise)),
                      "raw_unadjusted_mean": float(np.mean([r["raw"] for r in noise]))},
        "b_null40": {**count_line(null_any, n_seeds), "bar_share": BAR_NULL40_SHARE},
        "c_planted": {"shift": PLANTED_SHIFT, "better": count_line(p_hit, n_seeds),
                      "bar_share": BAR_PLANTED_SHARE, "mean_estimate_all_seeds": p_est,
                      "bar_tol": BAR_PLANTED_TOL},
        "report_only_components": comp,
        "report_only_power": {"shift": POWER_SHIFT, "better": count_line(w_hit, n_seeds),
                              "analytic_holm_first_step_power": analytic},
    }
    out["verdict"] = {
        "a_pass": out["a_noise60"]["max_survivors"] <= BAR_NOISE60_MAX,
        "b_pass": null_any / n_seeds <= BAR_NULL40_SHARE,
        "c_pass": (p_hit / n_seeds >= BAR_PLANTED_SHARE
                   and abs(p_est - PLANTED_SHIFT) <= BAR_PLANTED_TOL),
        "acceptance_run": n_seeds == 200,
    }
    return out


def main(argv: Sequence[str]) -> int:
    seeds = int(argv[0]) if argv else 200
    print(json.dumps(null_check(seeds), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
