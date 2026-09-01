"""E4: leak-safe one-parameter in-game logit blend with a market guard."""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.logit_blend import blend, from_logit, guard_vs_market, to_logit

_DEFAULT_MAX_DEVIATION = 0.15
_DEFAULT_W_MAX = 1.0
_GRID_POINTS = 201
_SEED = 20260831


def _brier(probabilities: Iterable[float], outcomes: Iterable[float]) -> float:
    values = [(float(probability) - float(outcome)) ** 2 for probability, outcome in zip(probabilities, outcomes)]
    return float(np.mean(values)) if values else float("nan")


def _date(row: Mapping[str, Any]) -> str:
    value = row.get("game_date", row.get("date", row.get("timestamp")))
    if value is None:
        raise ValueError("each tick requires game_date, date, or timestamp")
    return str(value)[:10]


def _signal(row: Mapping[str, Any]) -> float:
    for name in ("state_signal", "signal", "s"):
        if row.get(name) is not None:
            value = float(row[name])
            if np.isfinite(value):
                return value
    raise ValueError("each tick requires a finite state_signal, signal, or s value")


def _frame(ticks: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for row in ticks:
        required = ("game", "outcome", "model_prob", "market_prob")
        if any(row.get(name) is None for name in required):
            continue
        rows.append({"game": str(row["game"]), "date": _date(row), "outcome": float(row["outcome"]),
                     "model_prob": float(row["model_prob"]), "market_prob": float(row["market_prob"]),
                     "signal": _signal(row), "in_window": bool(row.get("in_window", True))})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    numeric = ["outcome", "model_prob", "market_prob", "signal"]
    if not np.isfinite(frame[numeric].to_numpy(dtype=float)).all():
        raise ValueError("E4 probabilities and signals must be finite")
    if (frame[["outcome", "model_prob", "market_prob"]].to_numpy(dtype=float) < 0.0).any() or (
            frame[["outcome", "model_prob", "market_prob"]].to_numpy(dtype=float) > 1.0).any():
        raise ValueError("E4 probabilities and outcomes must be in [0, 1]")
    return frame


def _guarded_prob(model_prob: np.ndarray, market_prob: np.ndarray, signal: np.ndarray, weight: float,
                  max_abs_deviation: float) -> np.ndarray:
    """Apply the E4 logit offset and the mandatory imported market guard."""
    anchor = np.asarray(blend({"model": model_prob}), dtype=float)
    raw = np.asarray(from_logit(to_logit(anchor) + float(weight) * signal), dtype=float)
    return np.asarray(guard_vs_market(raw, market_prob, max_abs_deviation), dtype=float)


def _fit_weight(train: pd.DataFrame, w_max: float, max_abs_deviation: float) -> float:
    if not np.isfinite(w_max) or w_max < 0.0:
        raise ValueError("w_max must be finite and >= 0")
    grid = np.linspace(0.0, float(w_max), _GRID_POINTS)
    model, market, signal, outcome = (train[name].to_numpy(dtype=float) for name in
                                      ("model_prob", "market_prob", "signal", "outcome"))
    scores = [_brier(_guarded_prob(model, market, signal, weight, max_abs_deviation), outcome) for weight in grid]
    return float(grid[int(np.argmin(scores))])


def _walk_forward(frame: pd.DataFrame, w_max: float, max_abs_deviation: float) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    dates = sorted(frame["date"].unique())
    scored, folds = [], []
    for date in dates[1:]:
        train, test = frame[frame["date"] < date], frame[frame["date"] == date].copy()
        assert not train.empty and train["date"].max() < test["date"].min(), "prior-fold ordering violated"
        if train["outcome"].nunique() < 2:
            folds.append({"train_date_max": str(train["date"].max()), "test_date_min": str(date), "status": "INSUFFICIENT"})
            continue
        weight = _fit_weight(train, w_max, max_abs_deviation)
        test["arm_a_prob"] = _guarded_prob(test["model_prob"].to_numpy(), test["market_prob"].to_numpy(),
                                            test["signal"].to_numpy(), 0.0, max_abs_deviation)
        test["arm_b_prob"] = _guarded_prob(test["model_prob"].to_numpy(), test["market_prob"].to_numpy(),
                                            test["signal"].to_numpy(), weight, max_abs_deviation)
        scored.append(test)
        folds.append({"train_date_max": str(train["date"].max()), "test_date_min": str(date), "weight": weight,
                      "status": "OK", "date_ordering_asserted": True, "test_games": int(test["game"].nunique())})
    return (pd.concat(scored, ignore_index=True) if scored else frame.iloc[0:0].copy(), folds)


def _metrics(rows: pd.DataFrame) -> dict[str, float] | None:
    if rows.empty:
        return None
    outcome = rows["outcome"]
    arm_a, arm_b, market = (_brier(rows[name], outcome) for name in ("arm_a_prob", "arm_b_prob", "market_prob"))
    return {"n_games": int(rows["game"].nunique()), "n_ticks": int(len(rows)), "arm_a_brier": arm_a,
            "arm_b_brier": arm_b, "market_brier": market, "gap": arm_b - market,
            "arm_a_minus_arm_b": arm_a - arm_b}


def _bootstrap_improvement(rows: pd.DataFrame, iterations: int) -> list[float] | None:
    groups = [group for _, group in rows.groupby("game", sort=False)]
    if not groups:
        return None
    rng = random.Random(_SEED)
    values = []
    for _ in range(iterations):
        sample = pd.concat([rng.choice(groups) for _ in groups], ignore_index=True)
        values.append(_metrics(sample)["arm_a_minus_arm_b"])
    return [float(np.quantile(values, .05)), float(np.quantile(values, .95))]


def evaluate(ticks: Sequence[Mapping[str, Any]], w_max: float = _DEFAULT_W_MAX,
             max_abs_deviation: float = _DEFAULT_MAX_DEVIATION, bootstrap_iterations: int = 300) -> dict[str, Any]:
    """Fit E4 only on prior dates and report all/in-window guarded Brier gaps."""
    frame = _frame(ticks)
    if frame.empty:
        return {"status": "INSUFFICIENT", "folds": [], "slices": {}}
    scored, folds = _walk_forward(frame, w_max, max_abs_deviation)
    slices = {"all_ticks": scored, "in_window_ticks": scored[scored["in_window"]]}
    report: dict[str, Any] = {"status": "OK", "w_max": w_max, "max_abs_deviation": max_abs_deviation,
                              "folds": folds, "slices": {}}
    for name, rows in slices.items():
        metrics, ci = _metrics(rows), _bootstrap_improvement(rows, bootstrap_iterations)
        accepted = bool(metrics is not None and metrics["gap"] <= .044 and ci is not None and ci[0] > 0.0)
        report["slices"][name] = {"metrics": metrics, "game_clustered_ci_90_arm_a_minus_arm_b": ci,
                                   "acceptance": {"gap_max": .044, "ci_excludes_zero": bool(ci and ci[0] > 0.0),
                                                  "accepted": accepted}}
    return report
