"""Purged, symmetric-embargoed S205 calibration fits."""
from __future__ import annotations

from typing import Any, Callable, Sequence

import numpy as np

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.regime_calibration import fit_per_regime

EMBARGO_DAYS = 1
N_GROUPS = 8
N_TEST_GROUPS = 1
MIN_HISTORY = 200
EPS = 1e-6
ARMS = ("isotonic", "temperature", "beta")


def _logit(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, EPS, 1.0 - EPS)
    return np.log(clipped) - np.log1p(-clipped)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -40.0, 40.0)))


def _teams(event_id: str, row_index: int) -> tuple[str, str]:
    """Recover names where the corpus identifier carries them; otherwise isolate it."""
    parts = event_id.split("-")
    if len(parts) == 4 and len(parts[1]) == 3 and len(parts[2]) == 3:
        return parts[1], parts[2]  # MLB: date-home-away-game
    if len(parts) >= 4 and len(parts[0]) == 8 and parts[0].isdigit():
        return parts[2], "-".join(parts[3:])  # soccer: date-league-home-away
    if len(parts) >= 6 and parts[0].isdigit():
        return parts[-3], parts[-2]  # tennis: date-tour-event-player-player-round
    return "event-home-%d" % row_index, "event-away-%d" % row_index


def states(rows: Sequence[dict[str, Any]], raw: Sequence[float], outcomes: Sequence[float],
           regimes: Sequence[str]) -> list[dict[str, Any]]:
    """Build CPCV states from the read-only corpus date and row identity."""
    out = []
    for index, (row, probability, outcome, regime) in enumerate(zip(rows, raw, outcomes, regimes)):
        day = str(row["event_date"])[:10]
        stamp = day + "T19:00:00"
        home, away = _teams(str(row.get("event_id", index)), index)
        out.append({
            "game_id": str(index), "state_ts": stamp, "home": home, "away": away,
            "features": {"raw_probability": float(probability)},
            "feature_avail": {"raw_probability": day + "T00:00:00"},
            "outcome": int(outcome), "row_index": index, "regime": str(regime),
            "raw_probability": float(probability),
        })
    return out


def _temperature(source: Sequence[dict[str, Any]]) -> Callable[[float], float]:
    x = _logit(np.asarray([row["raw_probability"] for row in source], dtype=float))
    y, alpha = np.asarray([row["outcome"] for row in source], dtype=float), 1.0
    for _ in range(24):
        fitted = _sigmoid(alpha * x)
        gradient = float(np.dot(x, fitted - y))
        hessian = float(np.dot(x * x, fitted * (1.0 - fitted)))
        step = gradient / max(hessian, 1e-12)
        alpha = min(20.0, max(0.05, alpha - step))
        if abs(step) < 1e-11:
            break
    return lambda value: float(_sigmoid(np.asarray([alpha * _logit(np.asarray([value]))[0]]))[0])


def _beta(source: Sequence[dict[str, Any]]) -> Callable[[float], float]:
    p = np.clip(np.asarray([row["raw_probability"] for row in source], dtype=float), EPS, 1.0 - EPS)
    x = np.column_stack((np.log(p), -np.log1p(-p), np.ones(len(p))))
    y, params = np.asarray([row["outcome"] for row in source], dtype=float), np.array([1.0, 1.0, 0.0])
    for _ in range(30):
        fitted = _sigmoid(x @ params)
        gradient = x.T @ (fitted - y)
        hessian = x.T @ (x * (fitted * (1.0 - fitted))[:, None])
        try:
            step = np.linalg.solve(hessian + np.eye(3) * 1e-10, gradient)
        except np.linalg.LinAlgError:
            break
        scale, before = 1.0, _loss(fitted, y)
        while scale >= 1e-6:
            candidate = params - scale * step
            candidate[:2], candidate[2] = np.clip(candidate[:2], 0.0, 20.0), np.clip(candidate[2], -20.0, 20.0)
            if _loss(_sigmoid(x @ candidate), y) <= before:
                params = candidate
                break
            scale *= 0.5
        if float(np.max(np.abs(step))) < 1e-10:
            break
    def apply(value: float) -> float:
        clipped = float(np.clip(value, EPS, 1.0 - EPS))
        feature = np.asarray([np.log(clipped), -np.log1p(-clipped), 1.0])
        return float(_sigmoid(np.asarray([feature @ params]))[0])
    return apply


def _loss(probabilities: np.ndarray, outcomes: np.ndarray) -> float:
    p = np.clip(probabilities, EPS, 1.0 - EPS)
    return float(-np.mean(outcomes * np.log(p) + (1.0 - outcomes) * np.log1p(-p)))


def _arm(states_in: list[dict[str, Any]], arm: str) -> tuple[list[float], list[dict[str, Any]]]:
    values = [0.0] * len(states_in)
    history: dict[int, dict[str, Any]] = {}
    maps: dict[tuple[str, int], tuple[list[dict[str, Any]], Callable[[float], float]]] = {}
    source_cache: dict[int, tuple[list[dict[str, Any]], dict[str, tuple[list[dict[str, Any]], str]]]] = {}

    def predict(train: list[dict[str, Any]], test: dict[str, Any], _: bool) -> float:
        train_key = id(train)
        if train_key not in source_cache:
            raw, y, keys = ([row["raw_probability"] for row in train], [row["outcome"] for row in train],
                            [row["regime"] for row in train])
            fitted = fit_per_regime(raw, y, keys, min_n=MIN_HISTORY)
            source_cache[train_key] = (train, {})
            for regime in set(keys):
                local = [row for row in train if row["regime"] == regime]
                source_cache[train_key][1][regime] = ((local, regime) if fitted[regime] is not fitted["GLOBAL"]
                                                      else (train, "GLOBAL"))
        source, source_key = source_cache[train_key][1][str(test["regime"])]
        key = (arm, id(source))
        if key not in maps:
            if arm == "isotonic":
                fitted = fit_per_regime([row["raw_probability"] for row in source],
                                        [row["outcome"] for row in source],
                                        [source_key] * len(source), min_n=1)[source_key]
                maps[key] = (source, lambda value, fitted=fitted: fitted.apply([value])[0])
            elif arm == "temperature":
                maps[key] = (source, _temperature(source))
            else:
                maps[key] = (source, _beta(source))
        index = int(test["row_index"])
        history[index] = {"fit_history": len(source), "fit_history_source": source_key,
                          "n_train_after_purge": len(train), "split_id": None}
        return maps[key][1](float(test["raw_probability"]))

    records = cpcv_evaluate(states_in, predict, n_groups=N_GROUPS, n_test_groups=N_TEST_GROUPS,
                            embargo_days=EMBARGO_DAYS, strict_redaction=True,
                            allow_keys=("row_index", "regime", "raw_probability"))
    assert len(records) == len(states_in) == len(history), "S205 needs one OOF value per corpus row"
    for record in records:
        index = int(record["game_id"])
        values[index] = float(record["p_model"])
        history[index]["split_id"] = int(record["split_id"])
    return values, [history[index] for index in range(len(states_in))]


def calibrate(rows: Sequence[dict[str, Any]], raw: Sequence[float], outcomes: Sequence[float],
              regimes: Sequence[str]) -> tuple[dict[str, list[float]], list[dict[str, Any]]]:
    """Return one CPCV OOF prediction and actual regime history per corpus row."""
    corpus_states = states(rows, raw, outcomes, regimes)
    arms, baseline_history = {}, None
    for arm in ARMS:
        values, history = _arm(corpus_states, arm)
        arms[arm] = values
        if baseline_history is None:
            baseline_history = history
        else:
            assert history == baseline_history, "calibrator arms changed the fit history"
    assert baseline_history is not None
    return arms, baseline_history
