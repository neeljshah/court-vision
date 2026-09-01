"""Fixed-offset residual experiment for in-game probability calibration.

The stored model probability is an offset, never a learned feature.  State-only
features can therefore learn a small log-odds correction without re-learning
the incumbent probability map.  Market probability is evaluation-only.
"""
from __future__ import annotations

import argparse
import importlib
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier

from scripts.platformkit.ingame_state_lift import _feature_matrix, _window_ids
from scripts.platformkit.ingame_replay_scoreboard import discover_store
from scripts.platformkit.wp_diag_oos import _game_dates

_EPSILON = 1e-6
_SEED = 20260831
_MIN_TRAIN_GAMES = 5


def _logit(probabilities: Iterable[float]) -> np.ndarray:
    values = np.clip(np.asarray(list(probabilities), dtype=float), _EPSILON, 1.0 - _EPSILON)
    return np.log(values / (1.0 - values))


def _sigmoid(scores: Iterable[float]) -> np.ndarray:
    values = np.asarray(list(scores), dtype=float)
    return 1.0 / (1.0 + np.exp(-values))


def _brier(probabilities: Iterable[float], outcomes: Iterable[float]) -> float:
    probability = np.asarray(list(probabilities), dtype=float)
    outcome = np.asarray(list(outcomes), dtype=float)
    return float(np.mean((probability - outcome) ** 2))


def zero_capacity_prob(model_prob: Iterable[float]) -> np.ndarray:
    """Return the fixed-offset prediction when the residual capacity is zero."""
    return _sigmoid(_logit(model_prob))


def _trip_number_features(ticks: List[Dict[str, Any]]) -> pd.DataFrame:
    """Derive capped batter trips from ordered GUMBO batter changes, as-of each tick."""
    rows: List[Dict[str, Any]] = []
    games: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tick in ticks:
        games[str(tick["game"])].append(tick)
    for game, group in games.items():
        appearances: Dict[str, int] = defaultdict(int)
        prior_batter: Optional[str] = None
        for tick in sorted(group, key=lambda row: str(row["timestamp"])):
            raw = tick.get("raw") if isinstance(tick.get("raw"), dict) else {}
            batter_id = raw.get("batter_id", tick.get("batter_id"))
            trip = math.nan
            if batter_id is not None:
                batter = str(batter_id)
                if batter != prior_batter:
                    trip = float(min(4, appearances[batter] + 1))
                    appearances[batter] += 1
                    prior_batter = batter
                else:
                    trip = float(min(4, appearances[batter]))
            rows.append({"game": game, "timestamp": tick["timestamp"], "trip_number": trip})
    return pd.DataFrame(rows, columns=["game", "timestamp", "trip_number"])


def _state_features(ticks: List[Dict[str, Any]], include_trip_number: bool = False) -> Optional[pd.DataFrame]:
    """Build the existing declared state block, excluding all evaluation fields."""
    try:
        module = importlib.import_module("scripts.platformkit.mlb_state_features")
    except ImportError:
        return None
    builder = getattr(module, "game_state_features", None)
    columns = getattr(module, "_FEATURE_COLUMNS", None)
    if not callable(builder) or not isinstance(columns, list):
        return None
    frame = builder(pd.DataFrame(ticks).sort_values("timestamp", kind="stable").reset_index(drop=True))
    result = frame[["game", "timestamp"] + columns].copy()
    if include_trip_number:
        trip = _trip_number_features(ticks)
        result = result.merge(trip, on=["game", "timestamp"], how="left", validate="one_to_one")
    return result


def _feature_values(train: pd.DataFrame, other: pd.DataFrame, columns: Sequence[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    train_x, other_x = train[list(columns)].copy(), other[list(columns)].copy()
    for column in columns:
        train_x[column] = pd.to_numeric(train_x[column], errors="coerce")
        other_x[column] = pd.to_numeric(other_x[column], errors="coerce")
        median = float(train_x[column].median()) if train_x[column].notna().any() else 0.0
        train_x[column] = train_x[column].fillna(median)
        other_x[column] = other_x[column].fillna(median)
    return train_x, other_x


def _split_prior_games(game_dates: Dict[str, str], eval_date: str) -> Tuple[set[str], set[str]]:
    prior = sorted((date, game) for game, date in game_dates.items() if date < eval_date)
    calibration_n = max(1, int(math.ceil(len(prior) * 0.2)))
    fit_games = {game for _, game in prior[:-calibration_n]}
    calibration_games = {game for _, game in prior[-calibration_n:]}
    assert not (fit_games & calibration_games), "fit and calibration games must be disjoint"
    return fit_games, calibration_games


def _fit_fold(train: pd.DataFrame, calibration: pd.DataFrame, evaluation: pd.DataFrame,
              columns: Sequence[str], max_estimators: int) -> np.ndarray:
    if max_estimators == 0:
        return zero_capacity_prob(evaluation["model_prob"])
    train_x, calibration_x = _feature_values(train, calibration, columns)
    _, evaluation_x = _feature_values(train, evaluation, columns)
    model = XGBClassifier(n_estimators=max_estimators, learning_rate=0.03, max_depth=2,
                          min_child_weight=10, subsample=0.8, colsample_bytree=0.8,
                          reg_lambda=10.0, objective="binary:logistic", eval_metric="logloss",
                          early_stopping_rounds=20, random_state=_SEED, n_jobs=1)
    train_offset = _logit(train["model_prob"])
    calibration_offset = _logit(calibration["model_prob"])
    model.fit(train_x, train["outcome"].astype(int), base_margin=train_offset,
              eval_set=[(calibration_x, calibration["outcome"].astype(int))],
              base_margin_eval_set=[calibration_offset], verbose=False)
    calibration_raw = model.predict_proba(calibration_x, base_margin=calibration_offset)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(calibration_raw, calibration["outcome"])
    evaluation_raw = model.predict_proba(evaluation_x, base_margin=_logit(evaluation["model_prob"]))[:, 1]
    return np.asarray(calibrator.predict(evaluation_raw), dtype=float)


def _walk_forward(joined: pd.DataFrame, columns: Sequence[str], game_dates: Dict[str, str],
                  max_estimators: int) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    predictions: List[pd.DataFrame] = []
    folds: List[Dict[str, Any]] = []
    for eval_date in sorted(set(game_dates.values())):
        fit_games, calibration_games = _split_prior_games(game_dates, eval_date)
        eval_games = {game for game, date in game_dates.items() if date == eval_date}
        fold = {"train_games": len(fit_games), "calibration_games": len(calibration_games),
                "eval_games": len(eval_games), "eval_date": eval_date,
                "game_disjoint": not (fit_games & calibration_games or fit_games & eval_games or calibration_games & eval_games)}
        train, calibration = joined[joined.game.isin(fit_games)], joined[joined.game.isin(calibration_games)]
        evaluation = joined[joined.game.isin(eval_games)].copy()
        if len(fit_games) < _MIN_TRAIN_GAMES or train.outcome.nunique() < 2 or calibration.outcome.nunique() < 2:
            fold["status"] = "INSUFFICIENT"
            folds.append(fold)
            continue
        assert max(game_dates[game] for game in fit_games) < eval_date
        assert max(game_dates[game] for game in calibration_games) < eval_date
        evaluation["arm_b_prob"] = _fit_fold(train, calibration, evaluation, columns, max_estimators)
        fold["status"] = "OK"
        folds.append(fold)
        predictions.append(evaluation)
    return (pd.concat(predictions, ignore_index=True) if predictions else joined.iloc[0:0].copy(), folds)


def _metrics(rows: pd.DataFrame) -> Optional[Dict[str, float]]:
    if rows.empty:
        return None
    arm_a = _brier(rows.model_prob, rows.outcome)
    arm_b = _brier(rows.arm_b_prob, rows.outcome)
    market = _brier(rows.market_prob, rows.outcome)
    return {"n_ticks": int(len(rows)), "n_games": int(rows.game.nunique()), "arm_a_brier": arm_a,
            "arm_b_brier": arm_b, "market_brier": market, "gap_b": arm_b - market,
            "market_minus_arm_a": market - arm_a, "market_minus_arm_b": market - arm_b}


def _bootstrap(rows: pd.DataFrame, iterations: int) -> Dict[str, List[float]]:
    groups = [group for _, group in rows.groupby("game", sort=False)]
    if not groups:
        return {}
    sampled: Dict[str, List[float]] = defaultdict(list)
    chooser = random.Random(_SEED)
    for _ in range(iterations):
        metrics = _metrics(pd.concat([chooser.choice(groups) for _ in groups], ignore_index=True))
        assert metrics is not None
        for key in ("market_minus_arm_a", "market_minus_arm_b"):
            sampled[key].append(metrics[key])
        sampled["arm_a_minus_arm_b"].append(metrics["arm_a_brier"] - metrics["arm_b_brier"])
    return {key: [float(np.quantile(values, 0.05)), float(np.quantile(values, 0.95))]
            for key, values in sampled.items()}


def _verdict(metrics: Optional[Dict[str, float]], ci: Dict[str, List[float]]) -> str:
    if metrics is None:
        return "INSUFFICIENT"
    if metrics["gap_b"] <= 0.040 and ci["market_minus_arm_b"][0] > ci["market_minus_arm_a"][0]:
        return "SHIP"
    if metrics["gap_b"] <= 0.047:
        return "DO-NOT-ABANDON"
    movement_ci = ci["arm_a_minus_arm_b"]
    if movement_ci[0] <= 0.0 <= movement_ci[1]:
        return "REJECT"
    return "INCONCLUSIVE"


@dataclass(frozen=True)
class GapOffsetArm:
    """Fixed-offset residual arm with an opt-in GUMBO trip-number state feature."""

    include_trip_number: bool = False

    def evaluate(self, ticks: List[Dict[str, Any]], features: pd.DataFrame,
                 bootstrap_iterations: int = 300, max_estimators: int = 300) -> Dict[str, Any]:
        """Evaluate using game-disjoint, strictly prior-date folds."""
        usable = [dict(tick, _row_id=tick.get("_row_id", index)) for index, tick in enumerate(ticks)
                  if all(tick.get(key) is not None for key in ("model_prob", "market_prob", "outcome"))]
        for tick in usable:
            tick.setdefault("raw", {})
        feature_frame = features
        if self.include_trip_number:
            trip = _trip_number_features(usable)
            feature_frame = features.merge(trip, on=["game", "timestamp"], how="left", validate="one_to_one")
        joined, columns = _feature_matrix(usable, feature_frame)
        assert "model_prob" not in columns
        assert not any("market" in column.lower() for column in columns)
        scored, folds = _walk_forward(joined, columns, _game_dates(usable), max_estimators)
        window_ids = _window_ids(usable)
        report: Dict[str, Any] = {"status": "OK", "state_features": list(columns), "folds": folds, "slices": {}}
        for name, rows in {"all_ticks": scored, "in_window_ticks": scored[scored._row_id.isin(window_ids)]}.items():
            metrics, ci = _metrics(rows), _bootstrap(rows, bootstrap_iterations)
            report["slices"][name] = {"metrics": metrics, "bootstrap_ci_90": ci, "verdict": _verdict(metrics, ci)}
        return report


def evaluate(ticks: List[Dict[str, Any]], features: pd.DataFrame, bootstrap_iterations: int = 300,
             max_estimators: int = 300, include_trip_number: bool = False) -> Dict[str, Any]:
    """Compatibility entry point; trip-number capacity remains disabled by default."""
    return GapOffsetArm(include_trip_number).evaluate(ticks, features, bootstrap_iterations, max_estimators)


def render(report: Dict[str, Any]) -> str:
    """Render an ASCII-only experiment summary with game counts."""
    lines = ["SLICE | N_GAMES | N_TICKS | GAP_B | VERDICT"]
    for name, section in report["slices"].items():
        metrics = section["metrics"]
        if metrics is None:
            lines.append("%s | 0 | 0 | - | INSUFFICIENT" % name)
        else:
            lines.append("%s | %d | %d | %.6f | %s" %
                         (name, metrics["n_games"], metrics["n_ticks"], metrics["gap_b"], section["verdict"]))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """Run E1 from the canonical stored-tick corpus without writing artifacts."""
    parser = argparse.ArgumentParser(description="Run fixed-offset residual calibration experiment.")
    parser.add_argument("--cache-root", type=Path, default=Path(r"C:\Users\neelj\nba-ai-system\data\cache"))
    parser.add_argument("--bootstrap-iterations", type=int, default=300)
    args = parser.parse_args(argv)
    store = discover_store(args.cache_root)
    if store is None:
        print("NO PARSEABLE TICK STORE")
        return 0
    from scripts.platformkit.ingame_state_lift import _load_enriched_ticks
    ticks = _load_enriched_ticks(store)
    features = _state_features(ticks)
    if features is None:
        print("PENDING: state-feature builder unavailable")
        return 0
    print(render(evaluate(ticks, features, bootstrap_iterations=args.bootstrap_iterations)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
