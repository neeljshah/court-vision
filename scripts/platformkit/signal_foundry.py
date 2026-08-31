"""Offline, leak-safe screening for proposed prediction signals.

Grades are pre-registered: STRONG needs positive lift, z >= adjusted 3.0
threshold, and split-half sign agreement; WEAK needs positive lift and z >= 2;
FLAT is within 0.01 MAE; everything else is REJECT.  This is evidence tooling,
not a production-signal or betting-edge claim.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import StandardScaler

from scripts.platformkit.novel_metric_lift import CANDIDATE_METRICS, pivot_player_metrics
from scripts.platformkit.teacher_student_ab import BASE_FEATURES, LOAD_FEATURES, build_features, expanding_folds


EMBARGO_BLOCKS = 1
PERMUTATIONS = 50
FLAT_LIFT = 0.01
REGISTRY: dict[str, "SignalSpec"] = {}
LEDGER_PATH = Path(os.environ.get("SIGNAL_FOUNDRY_LEDGER", "data/ab_reports/foundry_ledger.jsonl"))


@dataclass(frozen=True)
class SignalSpec:
    """Metadata and either a matrix column or dataframe-to-Series computation."""

    name: str
    sport: str
    grain: str
    story: str
    compute: Callable[[pd.DataFrame], pd.Series] | str


def register(spec: SignalSpec) -> SignalSpec:
    """Register and return a signal specification, rejecting accidental duplicates."""
    if spec.name in REGISTRY:
        raise ValueError("Signal already registered: {0}".format(spec.name))
    REGISTRY[spec.name] = spec
    return spec


def report_significance(z: float, n_trials: int, alpha: float = 0.0027) -> dict[str, float | bool]:
    """Apply a two-sided Bonferroni threshold that increases with trial count."""
    trials = max(1, int(n_trials))
    threshold = NormalDist().inv_cdf(1.0 - alpha / (2.0 * trials))
    return {"z": float(z), "n_trials": trials, "threshold": threshold, "significant": abs(z) >= threshold}


def _date_column(frame: pd.DataFrame) -> str:
    for name in ("gameDate", "date", "timestamp"):
        if name in frame:
            return name
    raise ValueError("matrix needs gameDate, date, or timestamp for embargo")


def _signal(frame: pd.DataFrame, spec: SignalSpec) -> pd.Series:
    value = frame[spec.compute] if isinstance(spec.compute, str) else spec.compute(frame)
    result = pd.to_numeric(pd.Series(value, index=frame.index), errors="coerce")
    if result.notna().sum() == 0:
        raise ValueError("Signal has no numeric values: {0}".format(spec.name))
    return result.rename(spec.name)


def _base_columns(frame: pd.DataFrame, target: str, excluded: Iterable[str]) -> list[str]:
    skip = {target, "gameId", "personId", "playerId", _date_column(frame), *excluded}
    names = [name for name in frame if name not in skip and pd.api.types.is_numeric_dtype(frame[name])]
    return names or ["__intercept__"]


def _design(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    for name in columns:
        result[name] = 1.0 if name == "__intercept__" else pd.to_numeric(frame[name], errors="coerce")
    return result.replace([np.inf, -np.inf], np.nan)


def _impute(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    medians = train.median(axis=0).fillna(0.0)
    return train.fillna(medians), test.fillna(medians)


def _embargo(frame: pd.DataFrame, train_index: np.ndarray) -> np.ndarray:
    dates = pd.to_datetime(frame.iloc[train_index][_date_column(frame)], errors="raise")
    blocks = np.sort(dates.drop_duplicates().to_numpy())
    if len(blocks) <= EMBARGO_BLOCKS:
        raise ValueError("Train window too short after embargo")
    keep = blocks[:-EMBARGO_BLOCKS]
    return train_index[np.asarray(dates.isin(keep))]


def _lift(frame: pd.DataFrame, target: str, base: Sequence[str], signal: pd.Series,
          folds: Sequence[tuple[np.ndarray, np.ndarray]], shuffled: bool = False, seed: int = 0) -> tuple[float, list[float]]:
    actual, augmented, fold_lifts = [], [], []
    rng = np.random.default_rng(seed)
    work = frame.copy()
    work[signal.name] = signal
    for train_i, test_i in folds:
        train_i = _embargo(work, np.asarray(train_i))
        test_i = np.asarray(test_i)
        train_y = pd.to_numeric(work.iloc[train_i][target], errors="raise").to_numpy()
        if shuffled:
            train_y = rng.permutation(train_y)
        test_y = pd.to_numeric(work.iloc[test_i][target], errors="raise").to_numpy()
        bx_train, bx_test = _impute(_design(work.iloc[train_i], base), _design(work.iloc[test_i], base))
        sx_train, sx_test = _impute(_design(work.iloc[train_i], [*base, signal.name]), _design(work.iloc[test_i], [*base, signal.name]))
        b_model = Ridge(alpha=1.0).fit(StandardScaler().fit_transform(bx_train), train_y)
        b_pred = b_model.predict(StandardScaler().fit(bx_train).transform(bx_test))
        scaler = StandardScaler().fit(sx_train)
        s_pred = Ridge(alpha=1.0).fit(scaler.transform(sx_train), train_y).predict(scaler.transform(sx_test))
        b_error, s_error = mean_absolute_error(test_y, b_pred), mean_absolute_error(test_y, s_pred)
        actual.extend(np.abs(test_y - b_pred)); augmented.extend(np.abs(test_y - s_pred)); fold_lifts.append(float(b_error - s_error))
    return float(np.mean(actual) - np.mean(augmented)), fold_lifts


def _trials() -> int:
    if not LEDGER_PATH.exists():
        return 0
    return sum(1 for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines() if line.strip())


def _append(spec: SignalSpec, grade: str, lift: float, z: float) -> dict[str, object]:
    count = _trials() + 1
    item = {"ts": datetime.now(timezone.utc).isoformat(), "signal": spec.name, "sport": spec.sport,
            "n_trials_total": count, "grade": grade, "lift": lift, "z": z}
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, allow_nan=False) + "\n")
    return item


def evaluate_signal(matrix: pd.DataFrame, target: str, spec: SignalSpec,
                    folds: Sequence[tuple[np.ndarray, np.ndarray]]) -> dict[str, object]:
    """Run embargoed marginal lift, permutation z, stability, and trial ledger."""
    if target not in matrix:
        raise ValueError("Missing target: {0}".format(target))
    signal = _signal(matrix, spec)
    base = _base_columns(matrix, target, [signal.name, spec.compute] if isinstance(spec.compute, str) else [signal.name])
    fold_list = list(folds)
    lift, fold_lifts = _lift(matrix, target, base, signal, fold_list)
    null = np.asarray([_lift(matrix, target, base, signal, fold_list, True, number)[0] for number in range(PERMUTATIONS)])
    z = float((lift - null.mean()) / (null.std(ddof=1) + 1e-9))
    midpoint = len(fold_lifts) // 2
    stable = bool(midpoint and np.sign(np.mean(fold_lifts[:midpoint])) == np.sign(np.mean(fold_lifts[midpoint:])) and lift > 0)
    significance = report_significance(z, _trials() + 1)
    grade = "STRONG" if lift > FLAT_LIFT and stable and significance["significant"] else (
        "WEAK" if lift > FLAT_LIFT and z >= 2.0 else "FLAT" if abs(lift) <= FLAT_LIFT else "REJECT")
    ledger = _append(spec, grade, lift, z)
    print("{0} grade={1} lift={2:.4f} z={3:.3f} threshold={4:.3f} trials={5}".format(
        spec.name, grade, lift, z, significance["threshold"], significance["n_trials"]
    ))
    return {"signal": spec.name, "grade": grade, "lift": lift, "z": z, "null_lifts": null.tolist(),
            "fold_lifts": fold_lifts, "split_half_stable": stable, "significance": significance, "ledger": ledger}


def combine_pool(matrix: pd.DataFrame, target: str, pool_specs: Sequence[SignalSpec],
                 folds: Sequence[tuple[np.ndarray, np.ndarray]]) -> dict[str, object]:
    """Compare an ElasticNet plus HistGB pool against Ridge base, then rank interactions."""
    signals = [_signal(matrix, item) for item in pool_specs]
    work = matrix.copy()
    for value in signals: work[value.name] = value
    base = _base_columns(work, target, [value.name for value in signals])
    pool = [value.name for value in signals]
    base_errors, pool_errors = [], []
    for train_i, test_i in folds:
        train_i = _embargo(work, np.asarray(train_i)); test_i = np.asarray(test_i)
        bx_train, bx_test = _impute(_design(work.iloc[train_i], base), _design(work.iloc[test_i], base))
        px_train, px_test = _impute(_design(work.iloc[train_i], [*base, *pool]), _design(work.iloc[test_i], [*base, *pool]))
        y_train, y_test = work.iloc[train_i][target], work.iloc[test_i][target]
        bs = StandardScaler().fit(bx_train); ps = StandardScaler().fit(px_train)
        b_pred = Ridge(alpha=1.0).fit(bs.transform(bx_train), y_train).predict(bs.transform(bx_test))
        en = ElasticNet(alpha=0.05, l1_ratio=0.3, max_iter=5000, random_state=0).fit(ps.transform(px_train), y_train)
        hgb = HistGradientBoostingRegressor(max_iter=150, random_state=0).fit(px_train, y_train)
        prediction = (en.predict(ps.transform(px_test)) + hgb.predict(px_test)) / 2.0
        base_errors.extend(np.abs(y_test.to_numpy() - b_pred)); pool_errors.extend(np.abs(y_test.to_numpy() - prediction))
    pairs = []
    for left in range(len(pool)):
        for right in range(left + 1, len(pool)):
            score = abs(float(np.corrcoef(work[pool[left]].fillna(0) * work[pool[right]].fillna(0), work[target])[0, 1]))
            pairs.append({"pair": [pool[left], pool[right]], "score": score})
    pairs.sort(key=lambda item: item["score"], reverse=True)
    candidates = pairs[:10]
    try:
        import shap
        full_x, _ = _impute(_design(work, [*base, *pool]), _design(work, [*base, *pool]))
        full_model = HistGradientBoostingRegressor(max_iter=150, random_state=0).fit(full_x, work[target])
        values = shap.TreeExplainer(full_model).shap_interaction_values(full_x.iloc[: min(200, len(full_x))])
        strength = np.abs(values).mean(axis=0)
        names = list(full_x.columns); ranked = []
        for left in range(len(names)):
            for right in range(left + 1, len(names)):
                if names[left] in pool and names[right] in pool:
                    ranked.append({"pair": [names[left], names[right]], "score": float(strength[left, right])})
        candidates = sorted(ranked, key=lambda item: item["score"], reverse=True)[:10]
        shap_available = True
    except (ImportError, AttributeError):
        shap_available = False
    for item in candidates: print("CANDIDATE composite signal {0} x {1} score={2:.4f}".format(*item["pair"], item["score"]))
    return {"oos_lift": float(np.mean(base_errors) - np.mean(pool_errors)), "mae_base": float(np.mean(base_errors)),
            "mae_pool": float(np.mean(pool_errors)), "candidate_interactions": candidates, "shap_available": shap_available}


def main() -> None:
    """Screen the four static metrics alongside load and embedding columns offline."""
    root = Path(os.environ.get("NBA_DATA_ROOT", "data")); nba = root / "nba"
    frame = build_features(pd.read_parquet(nba / "player_tracking_features_asof.parquet"), pd.read_parquet(nba / "player_load_state_asof.parquet"), pd.read_parquet(nba / "player_embeddings_asof.parquet"))
    metrics = pivot_player_metrics(pd.read_parquet(root / "ab_reports" / "novel_metrics_players.parquet"))
    frame = frame.merge(metrics, on="personId", how="left").dropna(subset=["gameDate"]).sort_values("gameDate").reset_index(drop=True)
    names = [*CANDIDATE_METRICS, *[x for x in frame if x in LOAD_FEATURES or x.startswith("style_embedding_")]]
    specs = [register(SignalSpec(name, "nba", "player_game", "none", name)) for name in names if name not in REGISTRY]
    folds = list(expanding_folds(frame))
    for spec in specs: evaluate_signal(frame, "minutes", spec, folds)
    combine_pool(frame, "minutes", specs, folds)


if __name__ == "__main__":
    main()
