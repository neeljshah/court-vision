"""scripts.platformkit.ingame.ingame_gate_generic_models -- SPORT-BLIND models +
loader for the generic in-game detail-layer gate (companion to ingame_gate_generic.py).

Split out so each file stays <=300 LOC. Holds the FROZEN-schema loader plus the two
fit-on-TRAIN-only models the gate compares:

  BASE   = sigmoid((a + b*frac_elapsed) * state_diff)   -- a,b FIT per corpus (scale-
           normalized grid search), so run-diff / goal-diff / point-diff all work with
           NO basketball slope hardcoded.
  +PRIOR = blend(p0, BASE, w(time,margin))              -- w fit per (time,margin) cell;
           margin-bucket edges DERIVED from the train state_diff quantiles; sparse cells
           fall back to w=0 (trust BASE) so a NOISE p0 degrades to +PRIOR==BASE.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.ingame_blend import WeightSurface, blend, margin_bucket
from scripts.platformkit.eval_gate.scoring import brier

_REQUIRED = ("game_id", "state_diff", "frac_elapsed", "p0", "outcome")


# --------------------------------------------------------------------------- load
def load_states(path: str) -> List[dict]:
    """Load + validate one corpus of as-of states from a parquet into a list of dicts.

    Validates the FROZEN schema: state_diff float; frac_elapsed and p0 in [0,1];
    outcome in {0,1}. Raises ValueError on a malformed corpus (fail honest, not silent).
    """
    import pandas as pd
    df = pd.read_parquet(path)
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing required columns {missing}")
    states: List[dict] = []
    for r in df.itertuples(index=False):
        fe = float(r.frac_elapsed)
        p0 = float(r.p0)
        y = int(r.outcome)
        if not (0.0 <= fe <= 1.0):
            raise ValueError(f"{path}: frac_elapsed out of [0,1]: {fe}")
        if not (0.0 <= p0 <= 1.0):
            raise ValueError(f"{path}: p0 out of [0,1]: {p0}")
        if y not in (0, 1):
            raise ValueError(f"{path}: outcome not in {{0,1}}: {y}")
        states.append({
            "game_id": r.game_id, "state_diff": float(r.state_diff),
            "frac_elapsed": fe, "p0": p0, "outcome": y,
        })
    return states


# --------------------------------------------------------------------------- BASE
def fit_base(states: List[dict]) -> Tuple[float, float]:
    """Fit BASE logistic slope (a, b) so p = sigmoid((a + b*frac)*state_diff) on TRAIN.

    Grid search over scale-NORMALIZED slopes: state_diff is normalized by its train
    spread so the SAME grid covers a +/-1..3 goal corpus and a +/-10 point corpus.
    Returns (a, b) in RAW state_diff units (grid value / spread). NO hardcoded slope.
    """
    sd = np.array([s["state_diff"] for s in states], float)
    fe = np.array([s["frac_elapsed"] for s in states], float)
    y = np.array([s["outcome"] for s in states], float)
    spread = float(np.std(sd)) or 1.0
    z = sd / spread
    grid = np.linspace(0.0, 4.0, 17)
    best, best_b = (1.0, 0.0), float("inf")
    for a in grid:
        for b in grid:
            p = 1.0 / (1.0 + np.exp(-(a + b * fe) * z))
            sc = float(np.mean((p - y) ** 2))
            if sc < best_b:
                best_b, best = sc, (a / spread, b / spread)
    return best


def base_predict(states: List[dict], ab: Tuple[float, float]) -> np.ndarray:
    """BASE win-prob from (state_diff, frac_elapsed) using fitted (a, b)."""
    a, b = ab
    sd = np.array([s["state_diff"] for s in states], float)
    fe = np.array([s["frac_elapsed"] for s in states], float)
    return 1.0 / (1.0 + np.exp(-(a + b * fe) * sd))


# ----------------------------------------------------------------- honesty guard
# A BASE direction is DEGENERATE (vacuous in-game state model) when the (state,time)
# model adds ~no signal over a constant base-rate. Two principled, scale-free checks:
#   (1) slope:  the per-unit slope is near-zero even AFTER normalizing by the train
#               state_diff spread (a+b is the effective max logit-per-spread-unit),
#               so the base barely uses state_diff -> p ~ 0.5 everywhere.
#   (2) skill:  the held-out BASE Brier is not meaningfully below the constant-
#               base-rate Brier (predicting the TRAIN outcome mean) -- Brier Skill
#               Score vs base-rate <= a small floor. If the state model can't beat a
#               constant, there is NO in-game result for a prior to "improve".
# Thresholds (documented): normalized |a|+|b|*spread < 0.05 logits, OR BSS < 0.005.
_DEGEN_SLOPE_EPS = 0.05   # effective logit-per-spread-unit below this => no state use
_DEGEN_BSS_EPS = 0.005    # base Brier Skill Score vs base-rate below this => vacuous


def base_is_degenerate(ab: Tuple[float, float], train: List[dict],
                       base_test: np.ndarray, y_test: np.ndarray) -> Dict:
    """Return a dict describing whether the fitted BASE is a vacuous (state,time) model.

    Compares the held-out BASE Brier to the constant TRAIN-base-rate Brier and checks
    the scale-normalized slope. degenerate=True iff the base neither uses state_diff
    (slope check) NOR beats the base-rate constant (skill check) by the documented eps.
    """
    sd = np.array([s["state_diff"] for s in train], float)
    spread = float(np.std(sd)) or 1.0
    a, b = ab
    eff_slope = (abs(a) + abs(b)) * spread          # max logit per spread-unit of lead
    ybar = float(np.mean([s["outcome"] for s in train]))
    const = np.full(len(y_test), ybar, float)
    base_brier = float(np.mean((base_test - y_test) ** 2))
    const_brier = float(np.mean((const - y_test) ** 2))
    bss = 1.0 - base_brier / const_brier if const_brier > 0 else 0.0
    weak_slope = eff_slope < _DEGEN_SLOPE_EPS
    weak_skill = bss < _DEGEN_BSS_EPS
    return {
        "degenerate": bool(weak_slope or weak_skill),
        "eff_slope": round(eff_slope, 6), "base_rate": round(ybar, 6),
        "base_brier": round(base_brier, 5), "baserate_brier": round(const_brier, 5),
        "base_bss_vs_baserate": round(bss, 6),
        "weak_slope": bool(weak_slope), "weak_skill": bool(weak_skill),
    }


# --------------------------------------------------------------------------- PRIOR
def _margin_edges(states: List[dict]) -> Tuple[float, ...]:
    """Sport-blind signed margin-bucket edges from the TRAIN state_diff quantiles.

    Quartile-based so goal-diff (+/-1..3) and point-diff (+/-10) both get sane buckets
    -- no basketball (-12,-4,4,12) constant.
    """
    sd = np.array([s["state_diff"] for s in states], float)
    qs = np.quantile(sd, [0.2, 0.4, 0.6, 0.8])
    edges = tuple(sorted(set(round(float(q), 6) for q in qs)))
    return edges or (0.0,)


def _time_bucket(frac: float, n: int = 4) -> int:
    return min(n - 1, max(0, int(float(frac) * n)))


def fit_prior_surface(states: List[dict], base_pred: np.ndarray,
                      min_cell: int = 20) -> WeightSurface:
    """Fit blend weight w per (time, margin) cell minimizing Brier of blend(p0,BASE,w).

    Sport-blind: time buckets from frac_elapsed, margin buckets from data-derived edges.
    Sparse cells fall back to default 0.0 (trust BASE) -> a noise p0 yields w->0 ->
    +PRIOR == BASE (graceful degrade). w is NEVER fit on the test corpus.
    """
    edges = _margin_edges(states)
    surf = WeightSurface(default=0.0)
    surf.grid["__edges__"] = edges  # stash for apply (off the numeric (int,int) path)
    w_grid = np.linspace(0.0, 1.0, 21)
    p0 = np.array([s["p0"] for s in states], float)
    y = np.array([s["outcome"] for s in states], float)
    cells: Dict[Tuple[int, int], List[int]] = {}
    for i, s in enumerate(states):
        key = (_time_bucket(s["frac_elapsed"]), margin_bucket(s["state_diff"], edges))
        cells.setdefault(key, []).append(i)
    for key, idx in cells.items():
        if len(idx) < min_cell:
            continue
        ix = np.array(idx)
        pl, p0c, yc = base_pred[ix], p0[ix], y[ix]
        best_w, best_b = 0.0, float(np.mean((p0c - yc) ** 2))
        for w in w_grid:
            b = float(np.mean((w * pl + (1 - w) * p0c - yc) ** 2))
            if b < best_b:
                best_b, best_w = b, float(w)
        surf.grid[key] = best_w
    return surf


def prior_predict(states: List[dict], base_pred: np.ndarray,
                  surf: WeightSurface) -> np.ndarray:
    """Apply fitted surface: blend(p0, BASE, w(time, margin)) per state."""
    edges = surf.grid.get("__edges__", (0.0,))
    out = np.empty(len(states), float)
    for i, s in enumerate(states):
        key = (_time_bucket(s["frac_elapsed"]), margin_bucket(s["state_diff"], edges))
        w = surf.grid.get(key, surf.default)
        out[i] = blend(s["p0"], float(base_pred[i]), w)
    return out


# ----------------------------------------------------------------- one direction
def _elapsed_breakdown(states, base, prior, y) -> Dict[str, Dict[str, float]]:
    fe = np.array([s["frac_elapsed"] for s in states], float)
    out: Dict[str, Dict[str, float]] = {}
    edges = (0.0, 0.25, 0.5, 0.75, 1.0)
    for k in range(4):
        lo, hi = edges[k], edges[k + 1]
        m = (fe >= lo) & (fe < hi) if k < 3 else (fe >= lo) & (fe <= hi)
        if not m.any():
            continue
        bb, bp = float(brier(base[m], y[m])), float(brier(prior[m], y[m]))
        out[f"t{k}"] = {"brier_base": round(bb, 4), "brier_prior": round(bp, 4),
                        "delta": round(bb - bp, 5), "n": int(m.sum())}
    return out


def cross_direction(train: List[dict], test: List[dict], eps: float = 0.05,
                    min_cell: int = 20) -> Dict:
    """Fit BASE+surface on the WHOLE train corpus, score BASE vs +PRIOR on TEST.

    Leak-free: a,b and w never see a test state. DM clustered by game_id. Returns
    pooled Brier(BASE/+PRIOR), clustered DM, elapsed breakdown, prior_beats_base.
    """
    ab = fit_base(train)
    base_tr = base_predict(train, ab)
    surf = fit_prior_surface(train, base_tr, min_cell=min_cell)
    y = np.array([s["outcome"] for s in test], float)
    base = base_predict(test, ab)
    prior = prior_predict(test, base, surf)
    gids = [s["game_id"] for s in test]
    bb, bp = float(brier(base, y)), float(brier(prior, y))
    d = (base - y) ** 2 - (prior - y) ** 2            # +ve => prior beats base
    dm = diebold_mariano(d, gids)
    bk = _elapsed_breakdown(test, base, prior, y)
    d_early = bk.get("t0", {}).get("delta")
    d_late = bk.get("t3", {}).get("delta")
    early_helps_most = bool(d_early is not None and d_late is not None
                            and d_early > d_late and d_early > 0.0)
    degen = base_is_degenerate(ab, train, base, y)
    # HONESTY GUARD: a beat over a VACUOUS base is NOT an in-game conditioning win.
    prior_beats_base = bool((bp < bb) and (dm.p_value < eps)
                            and not degen["degenerate"])
    return {
        "n_train_states": len(train), "n_test_states": len(test),
        "n_test_games": dm.n_clusters,
        "base_slope": [round(ab[0], 6), round(ab[1], 6)],
        "brier_base": round(bb, 4), "brier_prior": round(bp, 4),
        "brier_delta": round(bb - bp, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "prior_beats_base": prior_beats_base,
        "base_degenerate": bool(degen["degenerate"]),
        "base_check": degen,
        "elapsed_breakdown": bk, "early_helps_most": early_helps_most,
    }
