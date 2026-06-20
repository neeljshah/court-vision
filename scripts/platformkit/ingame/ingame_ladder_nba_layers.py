"""scripts.platformkit.ingame.ingame_ladder_nba_layers -- CANDIDATE detail layers +
leak-free state builder for the in-game ladder (companion to ingame_ladder_nba.py).

Split out so each file stays <=300 LOC. Each layer is a pure pair (fit, apply):
  fit(train_states, best_train_prob) -> params      # fit on TRAIN ONLY (leak-free)
  apply(test_states, best_test_prob, params) -> p'  # re-prices the CURRENT BEST prob

NO $ anywhere; everything here is CALIBRATION machinery (Brier), never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import numpy as np

from scripts.platformkit.ingame.ingame_layer_gate_nba_io import (
    QSEC,
    p_live_from_margin,
)

_REG = 2880.0


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


# --------------------------------------------------------------------------- states
def ladder_states_for_games(df, p0_map: Dict[int, float]) -> List[dict]:
    """Like states_for_games but ALSO carries the layer covariates, leak-free.

    total_so_far = home_cum+away_cum AFTER that quarter (past only, the pace proxy).
    recent_delta = this-quarter margin minus previous-quarter margin (run direction;
    endQ1 has no prior quarter so its delta is 0). Both are realized as-of state -- a
    game never sees a later quarter. One game -> 3 states.
    """
    out: List[dict] = []
    for _, r in df.iterrows():
        gid = int(r["event_id"])
        p0 = float(p0_map[gid])
        hq = [float(r["home_q1"]), float(r["home_q2"]),
              float(r["home_q3"]), float(r["home_q4"])]
        aq = [float(r["away_q1"]), float(r["away_q2"]),
              float(r["away_q3"]), float(r["away_q4"])]
        hc = np.cumsum(hq)
        ac = np.cumsum(aq)
        y = int(hc[-1] > ac[-1])
        qmargin = [float(hq[i] - aq[i]) for i in range(4)]  # per-quarter margin
        for q in (1, 2, 3):
            diff = float(hc[q - 1] - ac[q - 1])
            frac = 1.0 - QSEC[q] / _REG
            total = float(hc[q - 1] + ac[q - 1])
            recent_delta = 0.0 if q == 1 else float(qmargin[q - 1] - qmargin[q - 2])
            out.append({
                "game_id": gid, "period": q, "seconds_remaining": QSEC[q],
                "score_diff": diff, "p0": p0,
                "p_live": p_live_from_margin(diff, frac),
                "outcome": y, "total_so_far": total, "recent_delta": recent_delta,
            })
    return out


# --------------------------------------------------------------------------- pace
def _pace_z(states: List[dict], stats: Dict[int, Tuple[float, float]]) -> np.ndarray:
    """Standardize total_so_far WITHIN period using TRAIN per-period (mu,sd).

    total grows mechanically with the quarter, so a raw z_total is mostly a 'how late'
    proxy, not a PACE proxy -- it conflates a normal endQ3 total with a genuinely fast
    game. Standardizing within period isolates pace (above/below the typical total FOR
    THAT quarter). Unseen periods fall back to z=0 (no shrink)."""
    out = np.empty(len(states), float)
    for i, s in enumerate(states):
        mu, sd = stats.get(int(s["period"]), (float(s["total_so_far"]), 1.0))
        out[i] = (float(s["total_so_far"]) - mu) / sd
    return out


def _fit_pace(train: List[dict], best: np.ndarray):
    """Fit a pace shrink of the best prob toward 0.5, on TRAIN only.

    p' = 0.5 + (best-0.5)*s,  s = clip(a + b*z_pace, 0, 1),  z_pace = total standardized
    WITHIN period on TRAIN (see _pace_z). Grid-search (a,b) to minimize TRAIN Brier of the
    shrunk prob. Returns (a, b, per_period_stats). b<0 => tighter (more shrink) as a game
    runs hot FOR ITS QUARTER = the pace-variance hypothesis."""
    y = np.array([s["outcome"] for s in train], float)
    stats: Dict[int, Tuple[float, float]] = {}
    for q in (1, 2, 3):
        tq = np.array([s["total_so_far"] for s in train if int(s["period"]) == q], float)
        if tq.size:
            stats[q] = (float(tq.mean()), float(tq.std() + 1e-9))
    z = _pace_z(train, stats)
    best_ab, best_b = (1.0, 0.0), float(np.mean((best - y) ** 2))
    for a in np.linspace(0.7, 1.0, 7):
        for bb in np.linspace(-0.50, 0.10, 13):
            s = np.clip(a + bb * z, 0.0, 1.0)
            p = 0.5 + (best - 0.5) * s
            br = float(np.mean((p - y) ** 2))
            if br < best_b:
                best_b, best_ab = br, (float(a), float(bb))
    return best_ab[0], best_ab[1], stats


def _apply_pace(test: List[dict], best: np.ndarray, params) -> np.ndarray:
    a, b, stats = params
    z = _pace_z(test, stats)
    s = np.clip(a + b * z, 0.0, 1.0)
    return 0.5 + (best - 0.5) * s


# --------------------------------------------------------------------------- momentum
def _fit_momentum(train: List[dict], best: np.ndarray) -> Tuple[float, float, float]:
    """Fit a logit-shift by standardized recent run direction, on TRAIN only.

    p' = sigmoid(logit(best) + beta*z_delta). Grid beta to minimize TRAIN Brier.
    beta != 0 would mean a run carries info beyond the realized margin. Per INT-81 we
    expect beta ~ 0 / unstable -> REJECT. Returns (beta, mu, sd).
    """
    d = np.array([s["recent_delta"] for s in train], float)
    y = np.array([s["outcome"] for s in train], float)
    mu, sd = float(d.mean()), float(d.std() + 1e-9)
    z = (d - mu) / sd
    lo = _logit(best)
    best_beta, best_b = 0.0, float(np.mean((best - y) ** 2))
    for beta in np.linspace(-0.30, 0.30, 25):
        p = _sigmoid(lo + beta * z)
        br = float(np.mean((p - y) ** 2))
        if br < best_b:
            best_b, best_beta = br, float(beta)
    return best_beta, mu, sd


def _apply_momentum(test: List[dict], best: np.ndarray, params) -> np.ndarray:
    beta, mu, sd = params
    d = np.array([s["recent_delta"] for s in test], float)
    z = (d - mu) / sd
    return _sigmoid(_logit(best) + beta * z)


# --------------------------------------------------------------------------- home bias
def _fit_home_bias(train: List[dict], best: np.ndarray) -> Tuple[float]:
    """Fit a single global logit intercept (home-court calibration), on TRAIN only.

    p' = sigmoid(logit(best) + c). c is the residual home/away bias the best model
    leaves on the table: if best is systematically under/over-confident in the HOME
    direction, a constant logit shift fixes it. Grid c to minimize TRAIN Brier. The
    leak-free Elo prior already prices home-court, so on real data we EXPECT c ~ 0 and a
    REJECT -- a principled control that the best model is already home-calibrated."""
    y = np.array([s["outcome"] for s in train], float)
    lo = _logit(best)
    best_c, best_b = 0.0, float(np.mean((best - y) ** 2))
    for c in np.linspace(-0.40, 0.40, 33):
        p = _sigmoid(lo + c)
        br = float(np.mean((p - y) ** 2))
        if br < best_b:
            best_b, best_c = br, float(c)
    return (best_c,)


def _apply_home_bias(test: List[dict], best: np.ndarray, params) -> np.ndarray:
    (c,) = params
    return _sigmoid(_logit(best) + c)


@dataclass
class Layer:
    name: str
    fit: Callable[[List[dict], np.ndarray], object]
    apply: Callable[[List[dict], np.ndarray, object], np.ndarray]
    why_ship: str
    why_reject: str


LAYERS: List[Layer] = [
    Layer("pace_variance_shrink", _fit_pace, _apply_pace,
          "high-total games are genuinely noisier; shrinking the best prob toward 0.5 "
          "as pace rises improves held-out calibration.",
          "total-so-far adds no calibration signal beyond (margin,time,prior); the "
          "best model already prices remaining variance."),
    Layer("momentum_run_direction", _fit_momentum, _apply_momentum,
          "recent run direction carries win info beyond the realized margin.",
          "momentum is noise (INT-81): the realized margin already captures everything; "
          "the run-direction shift does not beat best OOS / is not fold-consistent."),
    Layer("home_bias_calibration", _fit_home_bias, _apply_home_bias,
          "the best model leaves a residual home/away bias a constant logit shift fixes.",
          "the leak-free Elo prior already prices home-court; no residual constant home "
          "bias remains for the layer to correct OOS."),
]
