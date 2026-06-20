"""scripts.platformkit.ingame.ingame_ladder_mlb_layers -- the L1/L2/L3 fit+apply layer
helpers split out of ingame_ladder_mlb.py to keep each file <=300 LOC (mirrors the
existing ingame_ladder_mlb_baseout.py sibling).

Each layer is fit on TRAIN only (leak-free) as a structural adjustment to a strong BASE
(run_diff, frac_elapsed) win-prob model:
  L1 late_inning_shrink     : shrink BASE toward 0.5 by normalized inning lateness.
  L2 leverage_late_close    : logit-shift by a late*close (small-lead-late) interaction.
  L3 inning_half_calibration: logit-shift by is_bottom (home bats last) calibration.

ASCII-only; <=300 LOC; no $ claims; never edit src/ or kernel/. numpy + stdlib.
"""
from __future__ import annotations

from typing import List

import numpy as np


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


# --------------------------------------------------------------------------- L1
def fit_late_shrink(train: List[dict], best: np.ndarray):
    """L1: shrink best toward 0.5 based on normalized inning lateness.

    p' = 0.5 + (best-0.5)*clip(a + b*inning_z, 0, 1)
    inning_z standardized on TRAIN. Hypothesis: large b<0 means a late small lead
    is safer (less shrink needed), contradicting the intuition -- BUT the key is that
    for extreme frac_elapsed the base is already very confident. The real signal is
    whether INNING has non-linear info beyond frac_elapsed.
    """
    inning = np.array([s["inning"] for s in train], float)
    y = np.array([s["outcome"] for s in train], float)
    mu_i, sd_i = float(inning.mean()), float(inning.std() + 1e-9)
    inning_z = (inning - mu_i) / sd_i
    best_params = (1.0, 0.0, mu_i, sd_i)
    best_b = float(np.mean((best - y) ** 2))
    for a in np.linspace(0.7, 1.0, 7):
        for b in np.linspace(-0.30, 0.30, 13):
            s = np.clip(a + b * inning_z, 0.0, 1.0)
            p = 0.5 + (best - 0.5) * s
            sc = float(np.mean((p - y) ** 2))
            if sc < best_b:
                best_b, best_params = sc, (a, b, mu_i, sd_i)
    return best_params


def apply_late_shrink(test: List[dict], best: np.ndarray, params) -> np.ndarray:
    a, b, mu_i, sd_i = params
    inning = np.array([s["inning"] for s in test], float)
    inning_z = (inning - mu_i) / sd_i
    s = np.clip(a + b * inning_z, 0.0, 1.0)
    return 0.5 + (best - 0.5) * s


# --------------------------------------------------------------------------- L2
def fit_leverage(train: List[dict], best: np.ndarray):
    """L2: logit-shift by late * small_lead interaction (leverage proxy).

    z_lev = late_flag * clip(-abs(run_diff), -3, 0) standardized on TRAIN.
    Positive z_lev means: late AND close game. Hypothesis: this raises confidence
    for the leading team (large lead late is already certain; only matters for 1-2 run
    leads in innings 7+). beta fit on TRAIN by Brier of p' = sig(lo + beta*z_lev).
    """
    sd = np.array([s["state_diff"] for s in train], float)
    inning = np.array([s["inning"] for s in train], float)
    late = (inning >= 7.0).astype(float)
    close = np.clip(-np.abs(sd), -3.0, 0.0)   # 0 when large lead, -abs when close
    lev = late * close   # 0 unless late AND close (late*0=0 for blowouts)
    y = np.array([s["outcome"] for s in train], float)
    mu_l, sd_l = float(lev.mean()), float(lev.std() + 1e-9)
    lev_z = (lev - mu_l) / sd_l
    lo = logit(best)
    best_params = (0.0, mu_l, sd_l)
    best_b = float(np.mean((best - y) ** 2))
    for beta in np.linspace(-0.50, 0.50, 25):
        p = sigmoid(lo + beta * lev_z)
        sc = float(np.mean((p - y) ** 2))
        if sc < best_b:
            best_b, best_params = sc, (float(beta), mu_l, sd_l)
    return best_params


def apply_leverage(test: List[dict], best: np.ndarray, params) -> np.ndarray:
    beta, mu_l, sd_l = params
    sd = np.array([s["state_diff"] for s in test], float)
    inning = np.array([s["inning"] for s in test], float)
    late = (inning >= 7.0).astype(float)
    close = np.clip(-np.abs(sd), -3.0, 0.0)
    lev = late * close
    lev_z = (lev - mu_l) / sd_l
    return sigmoid(logit(best) + beta * lev_z)


# --------------------------------------------------------------------------- L3
def fit_inning_half(train: List[dict], best: np.ndarray):
    """L3: bottom-half calibration for home-team advantage.

    In MLB the home team bats last; in a tie entering the bottom half the home team
    has an additional at-bat. Logit-shift: p' = sig(lo + c*is_bottom). c~0 =>
    no residual half effect (BASE's state_diff already prices it) => REJECT.
    """
    y = np.array([s["outcome"] for s in train], float)
    is_b = np.array([float(s["is_bottom"]) for s in train], float)
    lo = logit(best)
    best_c = 0.0
    best_b = float(np.mean((best - y) ** 2))
    for c in np.linspace(-0.40, 0.40, 33):
        p = sigmoid(lo + c * is_b)
        sc = float(np.mean((p - y) ** 2))
        if sc < best_b:
            best_b, best_c = sc, float(c)
    return (best_c,)


def apply_inning_half(test: List[dict], best: np.ndarray, params) -> np.ndarray:
    (c,) = params
    is_b = np.array([float(s["is_bottom"]) for s in test], float)
    return sigmoid(logit(best) + c * is_b)


__all__ = [
    "logit", "sigmoid",
    "fit_late_shrink", "apply_late_shrink",
    "fit_leverage", "apply_leverage",
    "fit_inning_half", "apply_inning_half",
]
