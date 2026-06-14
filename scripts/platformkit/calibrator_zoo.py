"""scripts/platformkit/calibrator_zoo.py — Extended calibration zoo + N-method OOS selector.

Extends isotonic (recalibration.py) and Platt (calibration_ladder.py) with:
  walk_forward_temperature : scalar-T temperature scaling (pure numpy, no scipy)
  walk_forward_beta        : beta calibration via 2-feature IRLS logistic (pure numpy)
  select_calibrator        : N-method leak-free OOS log-loss selector (generalises
                             walk_forward_auto from 2 → N methods).

CALIBRATION != EDGE.  Calibrated probabilities do NOT imply beating the close.
NOTE (market_probs): if market_probs passed to select_calibrator, per-method
log-loss delta vs the market is reported as context — NOT an edge claim.
"Calibrate only where you lose to the market" requires live closing prices and
proven forward CLV (not provided here).
Durable home: kernel/calibration/ (HUMAN-GATED). This is the platformkit prototype.
"""
from __future__ import annotations

import sys
from typing import List, Optional, Sequence

import numpy as np

from scripts.platformkit.recalibration import (
    CALIBRATION_NOTE, _ece, walk_forward_recalibrate,
)
from scripts.platformkit.calibration_ladder import (
    _logit, _logloss_vec, walk_forward_platt,
)

__all__ = ["walk_forward_temperature", "walk_forward_beta",
           "select_calibrator", "CALIBRATION_NOTE"]

_EPS = 1e-15
_ALL_METHODS: List[str] = ["identity", "temperature", "platt", "beta", "isotonic"]
_TIEBREAK: List[str] = _ALL_METHODS  # simpler = earlier


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return np.where(x >= 0, 1.0 / (1.0 + np.exp(-x)),
                    np.exp(x) / (1.0 + np.exp(x)))


def _fit_temperature(raw_p: np.ndarray, y: np.ndarray) -> float:
    """Fit scalar T in [0.2, 5] via coarse-grid + golden-section; pure numpy."""
    valid = np.isfinite(raw_p) & np.isfinite(y)
    pv, yv = raw_p[valid], y[valid]
    if len(pv) < 2 or len(np.unique(yv)) < 2:
        return 1.0
    logits = _logit(pv)

    def _loss(t: float) -> float:
        if t <= 0:
            return float("inf")
        cal = np.clip(_sigmoid(logits / t), _EPS, 1 - _EPS)
        return float(np.mean(-(yv * np.log(cal) + (1 - yv) * np.log(1 - cal))))

    t_grid = np.linspace(0.2, 5.0, 40)
    losses = np.array([_loss(t) for t in t_grid])
    bi = int(np.argmin(losses))
    t_lo, t_hi = t_grid[max(0, bi - 1)], t_grid[min(len(t_grid) - 1, bi + 1)]
    phi = (np.sqrt(5.0) - 1.0) / 2.0
    for _ in range(30):
        if t_hi - t_lo < 1e-7:
            break
        t1, t2 = t_hi - phi * (t_hi - t_lo), t_lo + phi * (t_hi - t_lo)
        if _loss(t1) < _loss(t2):
            t_hi = t2
        else:
            t_lo = t1
    return float((t_lo + t_hi) / 2.0)


def _fit_beta_irls(raw_p: np.ndarray, y: np.ndarray,
                   ridge: float = 1e-3, max_iter: int = 10) -> Optional[np.ndarray]:
    """Fit logistic on [log(p), log(1-p)] -> y via Newton-IRLS + ridge."""
    valid = np.isfinite(raw_p) & np.isfinite(y)
    pv, yv = raw_p[valid], y[valid]
    if len(pv) < 3 or len(np.unique(yv)) < 2:
        return None
    pc = np.clip(pv, _EPS, 1 - _EPS)
    X = np.column_stack([np.ones(len(pv)), np.log(pc), np.log(1.0 - pc)])
    R = ridge * np.eye(3)
    w = np.zeros(3)
    for _ in range(max_iter):
        mu = np.clip(_sigmoid(X @ w), _EPS, 1 - _EPS)
        grad = X.T @ (mu - yv) + R @ w
        H = (X.T * (mu * (1.0 - mu))) @ X + R
        try:
            delta = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        w -= delta
        if np.linalg.norm(delta) < 1e-8:
            break
    return w


def walk_forward_temperature(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    *,
    min_history: int = 50,
    refit_every: int = 1,
) -> np.ndarray:
    """Leak-free expanding-window temperature scaling (pure numpy, no scipy).

    For i < min_history: pass raw. For i >= min_history: fit scalar T on [:i],
    apply sigmoid(logit(raw[i])/T). Refit every K events (leak-free any K).
    NaN/inf dropped from fit; invalid query -> raw passthrough.
    Returns (N,) clipped [0,1]. CALIBRATION != EDGE.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = len(p)
    if n != len(y):
        raise ValueError(f"Length mismatch: {n} vs {len(y)}")
    step = max(1, int(refit_every))
    out = np.empty(n, dtype=float)
    T, have_T, next_fit = 1.0, False, min_history
    for i in range(n):
        if i < min_history:
            out[i] = float(p[i])
            continue
        if i >= next_fit:
            T = _fit_temperature(p[:i], y[:i])
            have_T = True
            next_fit = i + step
        if have_T and np.isfinite(p[i]):
            out[i] = float(_sigmoid(np.array([float(_logit(np.array([p[i]]))[0]) / T]))[0])
        else:
            out[i] = float(p[i])
    return np.clip(out, 0.0, 1.0)


def walk_forward_beta(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    *,
    min_history: int = 50,
    refit_every: int = 1,
) -> np.ndarray:
    """Leak-free expanding-window beta calibration (pure numpy IRLS).

    Fits logistic on [log(p), log(1-p)] features. Same refit/NaN/passthrough
    rules as walk_forward_temperature. Returns (N,) clipped [0,1].
    CALIBRATION != EDGE.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = len(p)
    if n != len(y):
        raise ValueError(f"Length mismatch: {n} vs {len(y)}")
    step = max(1, int(refit_every))
    out = np.empty(n, dtype=float)
    w: Optional[np.ndarray] = None
    next_fit = min_history
    for i in range(n):
        if i < min_history:
            out[i] = float(p[i])
            continue
        if i >= next_fit:
            w = _fit_beta_irls(p[:i], y[:i])
            next_fit = i + step
        if w is not None and np.isfinite(p[i]):
            pc = float(np.clip(p[i], _EPS, 1 - _EPS))
            x_q = np.array([1.0, np.log(pc), np.log(1.0 - pc)])
            out[i] = float(_sigmoid(np.array([float(w @ x_q)]))[0])
        else:
            out[i] = float(p[i])
    return np.clip(out, 0.0, 1.0)


def select_calibrator(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    *,
    min_history: int = 50,
    refit_every: int = 1,
    methods: Optional[List[str]] = None,
    market_probs: Optional[Sequence[float]] = None,
) -> dict:
    """Run N calibrators; select min OOS log-loss (tie-break: simpler method).

    Generalises walk_forward_auto (2 methods) to N.  Methods: identity,
    temperature, platt, beta, isotonic (or any subset via `methods`).
    market_probs: if given, per-method delta log-loss vs market in table
    (context only — NOT an edge claim).
    Returns dict: chosen_method, chosen_probs (np.ndarray), table (sorted by
    logloss), n_eval, note.  CALIBRATION != EDGE.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = len(p)
    active = methods if methods is not None else list(_ALL_METHODS)
    unknown = [m for m in active if m not in _ALL_METHODS]
    if unknown:
        raise ValueError(f"Unknown method(s): {unknown}. Valid: {_ALL_METHODS}")

    mkt: Optional[np.ndarray] = None
    if market_probs is not None:
        mkt = np.asarray(market_probs, dtype=float)
        if len(mkt) != n:
            raise ValueError("market_probs length must equal raw_probs length")

    def _run(name: str) -> np.ndarray:
        if name == "identity":
            return np.clip(p.copy(), 0.0, 1.0)
        if name == "temperature":
            return walk_forward_temperature(p, y, min_history=min_history,
                                            refit_every=refit_every)
        if name == "platt":
            return walk_forward_platt(p, y, min_history=min_history,
                                      refit_every=refit_every)
        if name == "beta":
            return walk_forward_beta(p, y, min_history=min_history,
                                     refit_every=refit_every)
        return walk_forward_recalibrate(p, y, min_history=min_history,
                                        refit_every=refit_every)  # isotonic

    arrs = {name: _run(name) for name in active}

    eval_mask = np.arange(n) >= min_history
    eval_mask &= np.isfinite(y)
    for arr in arrs.values():
        eval_mask &= np.isfinite(arr)
    n_eval = int(eval_mask.sum())

    rows = []
    for name, arr in arrs.items():
        if n_eval > 0:
            ll = float(_logloss_vec(arr[eval_mask], y[eval_mask]).mean())
            brier = float(np.mean((arr[eval_mask] - y[eval_mask]) ** 2))
            ece_val = float(_ece(arr[eval_mask], y[eval_mask]))
        else:
            ll, brier, ece_val = float("inf"), float("nan"), float("nan")
        row: dict = {"method": name, "logloss": ll, "brier": brier, "ece": ece_val}
        if mkt is not None:
            mm = eval_mask & np.isfinite(mkt)
            row["market_logloss"] = (
                float(_logloss_vec(arr[mm], y[mm]).mean()
                      - _logloss_vec(mkt[mm], y[mm]).mean()) if mm.sum() > 0
                else float("nan")
            )
        rows.append(row)

    rows.sort(key=lambda r: (r["logloss"],
                              _TIEBREAK.index(r["method"]) if r["method"] in _TIEBREAK else 99))
    best_ll = rows[0]["logloss"]
    tied = [r for r in rows if abs(r["logloss"] - best_ll) < 1e-12]
    chosen = min(tied, key=lambda r: (_TIEBREAK.index(r["method"])
                                      if r["method"] in _TIEBREAK else 99))
    return {
        "chosen_method": chosen["method"],
        "chosen_probs": arrs[chosen["method"]],
        "table": rows,
        "n_eval": n_eval,
        "note": ("leak-free walk-forward OOS selection; CALIBRATION != EDGE; "
                 "no market edge claimed"),
    }


def _main() -> int:
    rng = np.random.default_rng(42)
    N = 500
    true_p = rng.uniform(0.3, 0.7, N)
    raw = np.clip(np.where(true_p >= 0.5,
                            0.5 + (true_p - 0.5) * 2.2,
                            0.5 - (0.5 - true_p) * 2.2), 0.01, 0.99)
    outcomes = rng.binomial(1, true_p).astype(float)
    result = select_calibrator(raw, outcomes, min_history=50)
    print()
    print("=" * 65)
    print("calibrator_zoo.py — Synthetic overconfident demo")
    print(f"N={N}, seed=42, true_p~Uniform(0.3,0.7), raw pushed ±2.2x")
    print(f"NOTE: {CALIBRATION_NOTE}")
    print("=" * 65)
    hdr = f"{'Method':<12} {'LogLoss':>10} {'Brier':>8} {'ECE':>8}"
    print(f"\n{hdr}\n{'-' * len(hdr)}")
    for row in result["table"]:
        marker = " <-- CHOSEN" if row["method"] == result["chosen_method"] else ""
        print(f"{row['method']:<12} {row['logloss']:>10.5f} "
              f"{row['brier']:>8.5f} {row['ece']:>8.5f}{marker}")
    print(f"{'-' * len(hdr)}\nChosen : {result['chosen_method']}")
    print(f"n_eval : {result['n_eval']}\nNote   : {result['note']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
