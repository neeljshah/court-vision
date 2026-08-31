"""Leak-free NFL scoreboard against simple published-style baselines.

Evaluation only: this compares predictive calibration, not betting profitability.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.nfl_game_model import (
    FEATURE_COLUMNS, _data_root, _read_schedule, build_features,
)

METHODS = ("HOME_FIELD", "ELO_LITE", "MARKET", "NFL_GAME_MODEL")
MONEYLINE_PAIRS = (("home_moneyline", "away_moneyline"),
                   ("home_ml", "away_ml"),
                   ("home_money_line", "away_money_line"))


def devig_moneyline(home: float, away: float) -> Tuple[float, float]:
    """Convert two American moneylines to proportional no-vig probabilities."""
    def implied(value: float) -> float:
        return 100.0 / (value + 100.0) if value > 0 else -value / (-value + 100.0)
    home_prob, away_prob = implied(float(home)), implied(float(away))
    return home_prob / (home_prob + away_prob), away_prob / (home_prob + away_prob)


def _market_columns(frame: pd.DataFrame) -> Optional[Tuple[str, str]]:
    return next((pair for pair in MONEYLINE_PAIRS if set(pair).issubset(frame.columns)), None)


def _game_ids(frame: pd.DataFrame) -> pd.Series:
    days = pd.to_datetime(frame["gameday"], errors="coerce")
    fallback = days.dt.strftime("%Y-%m-%d") + "_" + frame["home_team"].astype(str) + "_" + frame["away_team"].astype(str)
    return frame.get("game_id", fallback).fillna(fallback).astype(str)


def market_probabilities(frame: pd.DataFrame) -> Tuple[Dict[str, float], List[str]]:
    """Return home probabilities keyed by game id and the source columns used."""
    columns = _market_columns(frame)
    if not columns:
        return {}, []
    home, away = (pd.to_numeric(frame[name], errors="coerce") for name in columns)
    output: Dict[str, float] = {}
    for game_id, h, a in zip(_game_ids(frame), home, away):
        if pd.notna(h) and pd.notna(a) and h != 0 and a != 0:
            output[game_id] = devig_moneyline(float(h), float(a))[0]
    return output, list(columns)


def elo_probabilities(train: pd.DataFrame, test: pd.DataFrame, k: float = 20.0) -> np.ndarray:
    """Rate train outcomes then predict test slates before ingesting each slate's results."""
    ratings: Dict[str, float] = defaultdict(lambda: 1500.0)

    def update(row: pd.Series) -> None:
        home, away = str(row.home_team), str(row.away_team)
        expected = 1.0 / (1.0 + 10.0 ** ((ratings[away] - ratings[home]) / 400.0))
        change = k * (float(row.home_win) - expected)
        ratings[home] += change
        ratings[away] -= change

    ordered_train = train.sort_values(["gameday", "game_id"], kind="mergesort")
    for _, day in ordered_train.groupby("gameday", sort=True):
        for _, row in day.iterrows():
            update(row)
    predictions: Dict[str, float] = {}
    ordered_test = test.sort_values(["gameday", "game_id"], kind="mergesort")
    for _, day in ordered_test.groupby("gameday", sort=True):
        for _, row in day.iterrows():
            predictions[str(row.game_id)] = 1.0 / (1.0 + 10.0 ** ((ratings[str(row.away_team)] - ratings[str(row.home_team)]) / 400.0))
        for _, row in day.iterrows():
            update(row)
    return np.array([predictions[str(game_id)] for game_id in test["game_id"]], dtype=float)


def _scores(probability: Iterable[float], outcome: Iterable[int]) -> Dict[str, float]:
    probability, outcome = np.asarray(list(probability), dtype=float), np.asarray(list(outcome), dtype=int)
    return {"n": int(len(outcome)), "brier": float(np.mean((probability - outcome) ** 2)),
            "accuracy": float(np.mean((probability >= 0.5) == outcome))}


def _row(test: pd.DataFrame, probabilities: Dict[str, np.ndarray]) -> Dict:
    outcome = test["home_win"].to_numpy(dtype=int)
    scores = {name: _scores(value, outcome) for name, value in probabilities.items()}
    market = probabilities.get("MARKET")
    ours = probabilities["NFL_GAME_MODEL"]
    verdicts = {
        "vs_home_field": "BEATS_BASELINE" if scores["NFL_GAME_MODEL"]["brier"] < scores["HOME_FIELD"]["brier"] else "DOES_NOT_BEAT",
        "vs_elo_lite": "BEATS_BASELINE" if scores["NFL_GAME_MODEL"]["brier"] < scores["ELO_LITE"]["brier"] else "DOES_NOT_BEAT",
    }
    if market is not None and np.isfinite(market).any():
        mask = ~np.isnan(market)
        market_scores, our_market_scores = _scores(market[mask], outcome[mask]), _scores(ours[mask], outcome[mask])
        scores["MARKET"] = market_scores
        verdicts["vs_market"] = "MATCH" if our_market_scores["brier"] <= market_scores["brier"] else "TRAIL"
        verdicts["market_brier_delta_our_minus_market"] = our_market_scores["brier"] - market_scores["brier"]
    ranking = [name for name, _ in sorted(scores.items(), key=lambda item: item[1]["brier"])]
    return {"n": int(len(test)), "scores": scores, "ranking_by_brier": ranking, "verdicts": verdicts}


def run(schedule_path: Optional[Path] = None) -> Dict:
    """Evaluate the same last-four adjacent-season folds as nfl_game_model."""
    path = schedule_path or _data_root() / "nfl" / "schedules.parquet"
    raw = _read_schedule(path)
    features = build_features(raw)
    market_by_id, columns = market_probabilities(raw)
    seasons = sorted(int(value) for value in features["season"].unique())
    folds, pooled = [], defaultdict(list)
    for train_season, test_season in [(s, s + 1) for s in seasons if s + 1 in seasons][-4:]:
        train, test = features[features.season <= train_season], features[features.season == test_season]
        if train.empty or test.empty or train.home_win.nunique() < 2:
            continue
        assert int(train.season.max()) < int(test.season.min())
        model = LogisticRegression(max_iter=1000, random_state=0).fit(train[FEATURE_COLUMNS], train.home_win)
        probabilities = {
            "HOME_FIELD": np.full(len(test), float(train.home_win.mean())),
            "ELO_LITE": elo_probabilities(train, test),
            "NFL_GAME_MODEL": model.predict_proba(test[FEATURE_COLUMNS])[:, 1],
        }
        if columns:
            market = np.array([market_by_id.get(str(key), np.nan) for key in test.game_id])
            if np.isfinite(market).any():
                probabilities["MARKET"] = market
        report = _row(test, probabilities)
        report.update({"train_through_season": train_season, "test_season": test_season,
                       "max_train_season": int(train.season.max())})
        folds.append(report)
        for name, values in probabilities.items():
            pooled[name].extend(zip(values, test.home_win.astype(int)))
    pooled_probs = {name: np.array([pair[0] for pair in values]) for name, values in pooled.items()}
    pooled_test = pd.DataFrame({"home_win": [pair[1] for pair in pooled["NFL_GAME_MODEL"]]})
    result = _row(pooled_test, pooled_probs)
    return {"sport": "NFL", "metric": "Brier and accuracy", "market_columns": columns,
            "folds": folds, "pooled": result,
            "disclaimer": "Leak-free calibration evaluation only; no betting edge or ROI is claimed. BEATS_BASELINE is a CI-free simple Brier delta."}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Score NFL model against published-style baselines.")
    parser.add_argument("--schedule-path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data") / "ab_reports" / "published_baseline_nfl.json")
    args = parser.parse_args(argv)
    report = run(args.schedule_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("NFL PUBLISHED-BASELINE SCOREBOARD")
    for fold in report["folds"] + [dict(report["pooled"], test_season="POOLED")]:
        print("%s | %s" % (fold["test_season"], " > ".join(fold["ranking_by_brier"])))
    print("REPORT: %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
