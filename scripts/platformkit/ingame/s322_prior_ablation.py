"""S322 train-only cached-logit prior ablation through the shared evaluator."""
from __future__ import annotations

import csv
import math
import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.scoring import brier, ece, log_loss
from scripts.platformkit.ingame.series_schema import read_series, recompute_metrics

EMBARGO_DAYS = 3
BOOTSTRAPS = 2000
ARMS = ("temperature_intercept", "temperature_intercept_m0", "null")


def _clip(value: float) -> float:
    return min(max(float(value), 1e-6), 1.0 - 1e-6)


def _logit(value: float) -> float:
    value = _clip(value)
    return math.log(value / (1.0 - value))


def _expit(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-min(max(value, -35.0), 35.0)))


def _fit(rows: list[dict], use_m0: bool) -> np.ndarray:
    """Fit an L2-stabilised logistic calibration only on a fold's train rows."""
    if not rows:
        return np.array([0.0, 1.0, 0.0] if use_m0 else [0.0, 1.0])
    x = np.array([[1.0, _logit(row["features"]["p_sim"])] +
                  ([_logit(row["features"]["p_m0"])] if use_m0 else []) for row in rows])
    y = np.array([row["outcome"] for row in rows], dtype=float)
    beta = np.zeros(x.shape[1]); beta[1] = 1.0
    penalty = np.diag([1e-6] + [1e-4] * (x.shape[1] - 1))
    for _ in range(80):
        p = 1.0 / (1.0 + np.exp(-np.clip(x @ beta, -35.0, 35.0)))
        weight = np.maximum(p * (1.0 - p), 1e-8)
        gradient = x.T @ (y - p) - penalty @ beta
        hessian = x.T @ (weight[:, None] * x) + penalty
        step = np.linalg.solve(hessian, gradient)
        beta += step
        if float(np.max(np.abs(step))) < 1e-10:
            break
    return beta


def _prediction(train: list[dict], test: dict, use_m0: bool, fits: dict[tuple, np.ndarray]) -> float:
    key = (use_m0, tuple(row["game_id"] for row in train))
    beta = fits.setdefault(key, _fit(train, use_m0))
    values = [1.0, _logit(test["features"]["p_sim"])]
    if use_m0:
        values.append(_logit(test["features"]["p_m0"]))
    return _expit(float(np.dot(beta, values)))


def states_from_rows(rows: Iterable[Mapping[str, object]]) -> tuple[list[dict], str]:
    """Create one strict shared-evaluator state for every cached tick."""
    result: list[dict] = []
    substitution = "pregame_m0"
    for raw in rows:
        game = str(raw["game_id"])
        elapsed = int(raw["elapsed_s"])
        state_key = str(raw.get("timestamp") or f"{game}:{elapsed}")
        m0 = raw.get("p_market_pregame")
        if m0 in (None, ""):
            m0 = raw["p_market"]; substitution = "tick_market_substitution"
        stamp = str(raw["timestamp_utc"]).replace("Z", "+00:00")
        result.append({
            "game_id": state_key, "state_ts": stamp, "home": "home:" + game,
            "away": "away:" + game, "outcome": int(raw["outcome"]),
            "features": {"p_sim": float(raw["p_simulator"]), "p_m0": float(m0),
                         "p_null": float(raw["p_null"])},
            "feature_avail": {"p_sim": "1970-01-01T00:00:00+00:00",
                              "p_m0": "1970-01-01T00:00:00+00:00",
                              "p_null": "1970-01-01T00:00:00+00:00"},
            "cluster_id": game, "state_key": state_key,
        })
    keys = [state["state_key"] for state in result]
    if len(keys) != len(set(keys)):
        raise AssertionError("one evaluator state is required for every scored tick")
    return result, substitution


def _records(states: list[dict], arm: str) -> list[dict]:
    fits: dict[tuple, np.ndarray] = {}
    if arm == "null":
        predictor = lambda _train, test, _inside: float(test["features"]["p_null"])
    else:
        use_m0 = arm == "temperature_intercept_m0"
        predictor = lambda train, test, _inside: _prediction(train, test, use_m0, fits)
    return cpcv_evaluate(states, predictor, n_groups=8, n_test_groups=1,
                         embargo_days=EMBARGO_DAYS, strict_redaction=True,
                         allow_keys=("cluster_id", "state_key"), guard_state_keys=True)


def paired_bootstrap(records: list[dict], candidate: str, baseline: str = "null",
                     draws: int = BOOTSTRAPS, seed: int = 322) -> tuple[float, float]:
    """Return paired game-cluster 95 percent interval from evaluator records only."""
    paired: dict[str, list[float]] = defaultdict(list)
    for row in records:
        paired[str(row["cluster_id"])].append(row[f"loss_{baseline}"] - row[f"loss_{candidate}"])
    values = np.array([np.mean(value) for _, value in sorted(paired.items())])
    rng = np.random.default_rng(seed)
    draws_values = [float(rng.choice(values, len(values), replace=True).mean()) for _ in range(draws)]
    return tuple(float(value) for value in np.quantile(draws_values, [0.025, 0.975]))


def run_ablation(rows: Iterable[Mapping[str, object]]) -> tuple[list[dict], list[dict], str]:
    """Score frozen S322 arms and retain losses solely from evaluator records."""
    states, substitution = states_from_rows(rows)
    by_arm = {arm: _records(states, arm) for arm in ARMS}
    indexed = {arm: {(row["game_id"], row["split_id"]): row for row in values}
               for arm, values in by_arm.items()}
    keys = set(indexed["null"])
    if any(set(indexed[arm]) != keys for arm in ARMS):
        raise AssertionError("all S322 arms require identical evaluator records")
    archived: list[dict] = []
    for key in sorted(keys):
        source = next(state for state in states if state["game_id"] == key[0])
        record = {"state_key": key[0], "split_id": key[1], "cluster_id": source["cluster_id"],
                  "timestamp": source["state_ts"], "outcome": source["outcome"]}
        for arm in ARMS:
            probability = indexed[arm][key]["p_model"]
            record[f"p_{arm}"] = probability
            record[f"loss_{arm}"] = (probability - source["outcome"]) ** 2
        archived.append(record)
    summary: list[dict] = []
    for arm in ARMS:
        probabilities = [row[f"p_{arm}"] for row in archived]
        outcomes = [row["outcome"] for row in archived]
        improvement = float(np.mean([row["loss_null"] - row[f"loss_{arm}"] for row in archived]))
        ci = paired_bootstrap(archived, arm) if arm != "null" else (0.0, 0.0)
        summary.append({"arm": arm, "n_records": len(archived), "n_clusters": len({r["cluster_id"] for r in archived}),
                        "brier": brier(probabilities, outcomes), "ece_10": ece(probabilities, outcomes, 10),
                        "log_loss": log_loss(probabilities, outcomes), "improvement_vs_null": improvement,
                        "ci95_low": ci[0], "ci95_high": ci[1]})
    return summary, archived, substitution


def write_ablation(path: Path, rows: Iterable[Mapping[str, object]]) -> list[dict]:
    """Write the compact arm table; the caller separately archives evaluator losses."""
    summary, _, _ = run_ablation(rows)
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(summary)
    return summary


def assert_binding_premise(rows: list[Mapping[str, object]], summary_path: Path) -> dict:
    """Recompute the exact S287 cache condition before an S322 comparison."""
    metrics = recompute_metrics(rows)
    clusters = {str(row["game_id"]) for row in rows}
    with summary_path.open(encoding="utf-8") as handle:
        s287 = json.load(handle)
    expected = {"market": s287["arms"]["market"]["brier"],
                "null": s287["arms"]["recal_null"]["brier"],
                "simulator": s287["arms"]["simulator"]["brier"]}
    actual = {arm: metrics[arm]["brier"] for arm in expected}
    if len(rows) != 2130 or len(clusters) != 355 or any(abs(actual[arm] - expected[arm]) > 1e-9 for arm in actual):
        raise AssertionError("PREMISE FALSE: cached v2 count, cluster count, or S287 Brier mismatch")
    print("PREMISE TICKS %06d CLUSTERS %06d" % (len(rows), len(clusters)))
    for arm in ("market", "null", "simulator"):
        print("PREMISE BRIER %s %.12f" % (arm, actual[arm]))
    return actual


def main() -> int:
    """Run only when the separately sealed finisher has rerun the premise."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--series", type=Path, required=True)
    parser.add_argument("--s287-summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = list(read_series(args.series))
    assert_binding_premise(rows, args.s287_summary)
    summary, archived, substitution = run_ablation(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "ablation.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]), lineterminator="\n")
        writer.writeheader()
        for row in summary:
            row = dict(row)
            row["n_records"] = f"{int(row['n_records']):06d}"
            row["n_clusters"] = f"{int(row['n_clusters']):06d}"
            writer.writerow(row)
    with (args.out / "ablation_evaluator_records.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(archived[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(archived)
    print("M0 " + substitution)
    print("RECORDS %06d" % len(archived))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
