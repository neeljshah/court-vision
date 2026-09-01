"""Leak-free A/B test of state features for settled in-game win probabilities.

ARM B never receives market probability: the goal is to test whether current-game
state adds information beyond the stored model, not to reproduce market prices.
"""
from __future__ import annotations

import argparse
import importlib
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from scripts.platformkit.brier_decomposition import decompose
from scripts.platformkit.ingame_replay_scoreboard import discover_store
from scripts.platformkit.lag_window_calibration import _classify_game
from scripts.platformkit.market_lag_study import load_records
from scripts.platformkit.wp_diag_oos import _game_dates, load_ticks

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path(os.environ.get(
    "NBA_CACHE_ROOT",
    os.path.join(os.environ.get("NBA_DATA_ROOT", "data"), "cache")))
_BOOTSTRAP_SEED = 20260831
_PRIOR = {"model_brier": 0.234, "market_brier": 0.187, "delta_market_minus_model": -0.047}


def _load_enriched_ticks(store: Path) -> List[Dict[str, Any]]:
    """Load canonical normalized ticks, adding score state where records match."""
    records = {(row["game"], row["timestamp"]): row for row in load_records(store)}
    ticks = load_ticks(store)
    for number, tick in enumerate(ticks):
        record = records.get((tick["game"], tick["timestamp"]), {})
        tick["state_summary"] = record.get("state_summary")
        tick["raw"] = record.get("raw", {})
        tick["_row_id"] = number
    return ticks


def _optional_feature_frame(ticks: Any) -> Optional[pd.DataFrame]:
    """Return the prebuilt in-game state features, joined to tick labels.

    The tick loader drops ``state_summary``, so features cannot be rebuilt from
    its output. ``mlb_state_features`` writes a parquet that already carries the
    parsed state columns alongside game/timestamp/model_prob/market_prob/outcome
    -- read that artifact when present (built pod-side by the retrain loop).
    """
    root = os.environ.get("NBA_DATA_ROOT", "data")
    path = Path(root) / "ab_reports" / "mlb_state_features.parquet"
    if not path.is_file():
        return None
    frame = pd.read_parquet(path)
    if frame.empty:
        return None
    # keep join keys + state features only. market_prob/model_prob/outcome are
    # evaluation-only and come from the tick loader; state_summary is raw text.
    drop = [name for name in ("market_prob", "model_prob", "outcome", "state_summary")
            if name in frame.columns]
    frame = frame.drop(columns=drop)
    # the store can emit several ticks sharing a (game, timestamp) second; keep
    # the last observation of that second so the join key is unique.
    keys = [name for name in ("game", "timestamp") if name in frame.columns]
    if keys:
        frame = frame.drop_duplicates(subset=keys, keep="last")
    return frame


def _feature_matrix(ticks: List[Dict[str, Any]], features: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    required = {"game", "timestamp"}
    if not required.issubset(features.columns):
        raise ValueError("state feature frame requires game and timestamp columns")
    prohibited = [str(column) for column in features.columns if "market" in str(column).lower()]
    assert not prohibited, "market_prob is evaluation-only, never an ARM B feature"
    state_columns = [str(column) for column in features.columns
                     if column not in required and str(column) not in {"outcome", "model_prob"}]
    if not state_columns:
        raise ValueError("state feature frame has no usable state columns")
    if features.duplicated(["game", "timestamp"]).any():
        raise ValueError("state feature frame has duplicate game/timestamp keys")
    base = pd.DataFrame(ticks)
    base["_index"] = np.arange(len(base))
    joined = base.merge(features[["game", "timestamp"] + state_columns], how="left",
                        on=["game", "timestamp"], sort=False, validate="many_to_one")  # ticks repeat within a second
    joined = joined.sort_values("_index").reset_index(drop=True)
    for column in state_columns + ["model_prob"]:
        joined[column] = pd.to_numeric(joined[column], errors="coerce")
    return joined, state_columns


def _window_ids(ticks: List[Dict[str, Any]]) -> Set[int]:
    games: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tick in ticks:
        games[tick["game"]].append(tick)
    selected: Set[int] = set()
    for game, group in games.items():
        classified = _classify_game(game, sorted(group, key=lambda row: row["timestamp"]))
        if classified is not None:
            selected.update(int(tick["_row_id"]) for tick in classified["window"])
    return selected


def _assert_prior_dates(train_dates: Sequence[str], test_dates: Sequence[str]) -> None:
    assert train_dates and test_dates and max(train_dates) < min(test_dates), (
        "walk-forward date ordering violated")


def _walk_forward(joined: pd.DataFrame, state_columns: List[str], game_dates: Dict[str, str]) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    dates = sorted(set(game_dates.values()))
    predictions: List[pd.DataFrame] = []
    folds: List[Dict[str, Any]] = []
    for date in dates[1:]:
        train_dates = [value for value in dates if value < date]
        _assert_prior_dates(train_dates, [date])
        train_games = {game for game, game_date in game_dates.items() if game_date in train_dates}
        test_games = {game for game, game_date in game_dates.items() if game_date == date}
        train = joined[joined["game"].isin(train_games)]
        test = joined[joined["game"].isin(test_games)].copy()
        fold = {"train_date_max": max(train_dates), "test_date_min": date,
                "train_games": len(train_games), "test_games": len(test_games),
                "date_ordering_asserted": True}
        if train.empty or test.empty or train["outcome"].nunique() < 2:
            fold["status"] = "INSUFFICIENT"
            folds.append(fold)
            continue
        columns = ["model_prob"] + state_columns
        model = HistGradientBoostingClassifier(max_iter=80, min_samples_leaf=8,
                                               l2_regularization=1.0, random_state=20260831)
        model.fit(train[columns], train["outcome"])
        test["arm_b_prob"] = model.predict_proba(test[columns])[:, 1]
        fold.update({"status": "OK", "test_ticks": len(test)})
        folds.append(fold)
        predictions.append(test)
    return (pd.concat(predictions, ignore_index=True) if predictions else joined.iloc[0:0].copy(), folds)


def _brier(probabilities: Iterable[float], outcomes: Iterable[float]) -> float:
    values = [(float(probability) - float(outcome)) ** 2 for probability, outcome in zip(probabilities, outcomes)]
    return sum(values) / len(values)


def _metrics(rows: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if rows.empty:
        return None
    outcome = rows["outcome"].astype(float).tolist()
    result = {"n_ticks": len(rows), "arm_a": decompose(rows["model_prob"], outcome),
              "arm_b": decompose(rows["arm_b_prob"], outcome),
              "market": decompose(rows["market_prob"], outcome)}
    a, b, market = result["arm_a"]["brier"], result["arm_b"]["brier"], result["market"]["brier"]
    result["deltas"] = {"market_minus_arm_a": market - a, "market_minus_arm_b": market - b,
                        "arm_a_minus_arm_b": a - b}
    return result


def _quantile(values: List[float], fraction: float) -> float:
    return float(np.quantile(np.asarray(values), fraction))


def _bootstrap(rows: pd.DataFrame, iterations: int, seed: int) -> Dict[str, List[float]]:
    games = [group for _, group in rows.groupby("game", sort=False)]
    if not games:
        return {}
    sampled: Dict[str, List[float]] = defaultdict(list)
    randomizer = random.Random(seed)
    for _ in range(iterations):
        sample = pd.concat([randomizer.choice(games) for _ in games], ignore_index=True)
        scores = _metrics(sample)
        assert scores is not None
        for name, value in scores["deltas"].items():
            sampled[name].append(float(value))
    return {name: [_quantile(values, .05), _quantile(values, .95)] for name, values in sampled.items()}


def _verdict(metrics: Optional[Dict[str, Any]]) -> str:
    if metrics is None:
        return "INSUFFICIENT"
    gap_a = metrics["arm_a"]["brier"] - metrics["market"]["brier"]
    gap_b = metrics["arm_b"]["brier"] - metrics["market"]["brier"]
    movement = gap_a - gap_b
    if gap_b <= 0.0:
        return "CLOSED THE GAP"
    if movement > .002:
        return "NARROWED"
    if movement < -.002:
        return "WORSE"
    return "NO CHANGE"


def evaluate(ticks: List[Dict[str, Any]], features: pd.DataFrame, bootstrap_iterations: int = 300) -> Dict[str, Any]:
    """Run prior-game-only state lift scoring on supplied normalized ticks and features."""
    usable = [dict(tick, _row_id=tick.get("_row_id", index)) for index, tick in enumerate(ticks)
              if tick.get("market_prob") is not None]
    for tick in usable:
        tick.setdefault("raw", {})
    joined, state_columns = _feature_matrix(usable, features)
    scored, folds = _walk_forward(joined, state_columns, _game_dates(usable))
    in_window = _window_ids(usable)
    slices = {"all_ticks": scored, "in_window_ticks": scored[scored["_row_id"].isin(in_window)]}
    report: Dict[str, Any] = {"status": "OK", "prior_measured_baseline": _PRIOR,
                              "state_features": state_columns, "folds": folds, "slices": {}}
    for name, rows in slices.items():
        metrics = _metrics(rows)
        report["slices"][name] = {"metrics": metrics, "bootstrap_ci_90":
                                   _bootstrap(rows, bootstrap_iterations, _BOOTSTRAP_SEED),
                                   "verdict": _verdict(metrics)}
    return report


def _number(value: Optional[float]) -> str:
    return "-" if value is None else "%.6f" % value


def render(report: Dict[str, Any]) -> str:
    lines = ["PRIOR BASELINE: model=0.234000 market=0.187000 delta=-0.047000",
             "SLICE | N | ARM_A | ARM_B | MARKET | B_DELTA | B_CI90 | VERDICT"]
    for name, section in report.get("slices", {}).items():
        metrics = section["metrics"]
        if metrics is None:
            lines.append("%s | 0 | - | - | - | - | - | INSUFFICIENT" % name)
            continue
        ci = section["bootstrap_ci_90"].get("market_minus_arm_b")
        interval = "-" if ci is None else "[%s, %s]" % (_number(ci[0]), _number(ci[1]))
        lines.append("%s | %d | %s | %s | %s | %s | %s | %s" %
                     (name, metrics["n_ticks"], _number(metrics["arm_a"]["brier"]),
                      _number(metrics["arm_b"]["brier"]), _number(metrics["market"]["brier"]),
                      _number(metrics["deltas"]["market_minus_arm_b"]), interval, section["verdict"]))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Test leak-free in-game state-feature calibration lift.")
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=_REPO / "data" / "ab_reports" / "ingame_state_lift.json")
    args = parser.parse_args(argv)
    store = discover_store(args.cache_root)
    if store is None:
        print("NO PARSEABLE TICK STORE")
        return 0
    ticks = _load_enriched_ticks(store)
    features = _optional_feature_frame(ticks)
    if features is None:
        print("PENDING: scripts.platformkit.mlb_state_features is unavailable or exposes no feature builder")
        return 0
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "store": str(store),
              **evaluate(ticks, features)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(render(report))
    print("REPORT: %s" % args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
