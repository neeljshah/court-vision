"""Two-way bootstrap effective-n diagnostic for the S202 pregame corpora.

This is an evidence-only diagnostic.  It never changes a gate, ledger, corpus,
or prediction route.  The crossed estimator uses a pigeonhole bootstrap: for
each draw it independently samples both label dimensions, then weights each
original row by the product of its two sampled label multiplicities.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.calibration_report import _oof_per_regime
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size
from scripts.platformkit.regime_calibration import buckets

REPO = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO / "docs" / "evidence"
DETAIL_DIR = EVIDENCE_DIR / "S202_two_way_neff_2026-09-04"
SUMMARY_PATH = EVIDENCE_DIR / "S202_two_way_neff_2026-09-04.json"
SEED = 20260904
ITERATIONS = 1000

CONFIG: dict[str, dict[str, Any]] = {
    "nba": {"gate": "data/cache/combo/gate_corpus_nba.parquet",
            "labels": ["data/domains/basketball_nba/games.parquet"],
            "event": "game_id", "first": "away_team", "second": "home_team",
            "one_way": "away_team", "expected_n": 1814},
    "mlb": {"gate": "data/cache/combo/gate_corpus_mlb.parquet",
            "labels": ["data/domains/mlb/games.parquet", "data/domains/mlb/games_current.parquet"],
            "event": "event_id", "first": "away_team", "second": "home_team",
            "one_way": "away_team", "expected_n": 39162},
    "soccer": {"gate": "data/cache/combo/gate_corpus_soccer.parquet",
               "labels": ["data/domains/soccer/matches.parquet"], "event": "event_id",
               "first": "home_team", "second": "away_team", "one_way": "div",
               "expected_n": 25834},
    "tennis": {"gate": "data/cache/combo/gate_corpus_tennis.parquet",
               "labels": ["data/domains/tennis/matches.parquet", "data/domains/tennis/wta_matches.parquet"],
               "event": "event_id", "first": "p1_id", "second": "p2_id",
               "one_way": "p1_id", "expected_n": 41886},
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_record(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "resolution": "not_applicable_tabular", "sha256": _sha256(path)}


def _label_frame(sport: str, config: Mapping[str, Any]) -> pd.DataFrame:
    paths = [REPO / value for value in config["labels"]]
    columns = [config["event"], config["first"], config["second"]]
    if sport == "soccer":
        columns.append("div")
    frames = [pd.read_parquet(path)[columns] for path in paths]
    labels = pd.concat(frames, ignore_index=True)
    labels[config["event"]] = labels[config["event"]].astype(str)
    if labels[config["event"]].duplicated().any():
        raise ValueError("duplicate event labels for %s" % sport)
    return labels


def load_labeled_corpus(sport: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Load exactly one gate corpus and its named label stores without filtering."""
    config = CONFIG[sport]
    gate_path = REPO / config["gate"]
    gate = pd.read_parquet(gate_path)
    gate["event_id"] = gate["event_id"].astype(str)
    labels = _label_frame(sport, config).rename(columns={config["event"]: "event_id"})
    rows = gate.merge(labels, on="event_id", how="left", validate="one_to_one")
    required = [config["first"], config["second"], config["one_way"]]
    if len(rows) != config["expected_n"] or rows[required].isna().any().any():
        raise ValueError("S202 denominator or labels failed for %s" % sport)
    return rows, [_input_record(gate_path), *[_input_record(REPO / value) for value in config["labels"]]]


def _crossed_means(values: np.ndarray, first: np.ndarray, second: np.ndarray,
                   iterations: int, seed: int) -> np.ndarray:
    first_levels, first_codes = np.unique(first.astype(str), return_inverse=True)
    second_levels, second_codes = np.unique(second.astype(str), return_inverse=True)
    if len(first_levels) < 2 or len(second_levels) < 2:
        raise ValueError("crossed bootstrap needs at least two labels per dimension")
    rng = np.random.default_rng(seed)
    means = np.empty(iterations, dtype=float)
    for index in range(iterations):
        first_counts = np.bincount(rng.integers(len(first_levels), size=len(first_levels)),
                                   minlength=len(first_levels))
        second_counts = np.bincount(rng.integers(len(second_levels), size=len(second_levels)),
                                    minlength=len(second_levels))
        weights = first_counts[first_codes] * second_counts[second_codes]
        total_weight = int(weights.sum())
        if total_weight == 0:
            raise RuntimeError("crossed bootstrap produced no row weight")
        means[index] = float(np.dot(weights, values) / total_weight)
    return means


def crossed_bootstrap_neff(rows: pd.DataFrame, value_column: str, first_column: str,
                           second_column: str, *, iterations: int = ITERATIONS,
                           seed: int = SEED) -> dict[str, Any]:
    """Estimate mean-equivalent n_eff with crossed label resampling.

    Every original row stays in the denominator.  A resample changes weights but
    never filters a row or suppresses a small cluster.  The iid variance of a
    mean is sample_variance / n; equating it to bootstrap_mean_variance gives
    n_eff = sample_variance / bootstrap_mean_variance.
    """
    if iterations < 1000:
        raise ValueError("S202 requires at least 1000 resamples")
    values = rows[value_column].to_numpy(dtype=float)
    if not np.isfinite(values).all() or len(values) < 2:
        raise ValueError("finite, non-degenerate row values required")
    first, second = rows[first_column].to_numpy(), rows[second_column].to_numpy()
    if pd.isna(first).any() or pd.isna(second).any():
        raise ValueError("crossed labels must be complete")
    means = _crossed_means(values, first, second, iterations, seed)
    sample_variance = float(np.var(values, ddof=1))
    bootstrap_variance = float(np.var(means, ddof=1))
    if sample_variance <= 0.0 or bootstrap_variance <= 0.0:
        raise ValueError("non-zero variance required")
    return {"n_rows": int(len(rows)), "first_clusters": int(pd.Series(first).nunique()),
            "second_clusters": int(pd.Series(second).nunique()), "iterations": iterations,
            "seed": seed, "sample_variance": sample_variance,
            "bootstrap_mean_variance": bootstrap_variance,
            "n_eff": sample_variance / bootstrap_variance,
            "bootstrap_mean_min": float(means.min()), "bootstrap_mean_max": float(means.max())}


def _one_way(rows: pd.DataFrame, value_column: str, key: str) -> dict[str, Any]:
    frame = rows[[key, value_column]].rename(columns={key: "game", value_column: "loss_differential"})
    return dict(effective_sample_size(frame, "game", "loss_differential"))


def _recalibrated(rows: pd.DataFrame) -> np.ndarray:
    records = rows[["p_base", "y"]].rename(columns={"p_base": "model_prob"}).to_dict("records")
    return np.asarray(_oof_per_regime(rows["p_base"].astype(float).tolist(),
                                      rows["y"].astype(float).tolist(), buckets(records), 200), dtype=float)


def analyze_sport(sport: str, *, iterations: int = ITERATIONS, seed: int = SEED) -> tuple[dict[str, Any], pd.DataFrame]:
    """Produce both loss definitions and one-way/crossed n_eff for one corpus."""
    config = CONFIG[sport]
    rows, inputs = load_labeled_corpus(sport)
    rows = rows.copy()
    rows["p_recalibrated_s05"] = _recalibrated(rows)
    rows["standin_loss"] = (rows["y"] - rows["p_base"]) ** 2
    rows["loss_base"] = rows["standin_loss"]
    rows["loss_recalibrated"] = (rows["y"] - rows["p_recalibrated_s05"]) ** 2
    rows["paired_loss_differential"] = rows["loss_recalibrated"] - rows["loss_base"]
    metrics: dict[str, Any] = {}
    for metric, column in (("standin_loss", "standin_loss"),
                           ("paired_loss_differential", "paired_loss_differential")):
        metrics[metric] = {"one_way": _one_way(rows, column, config["one_way"]),
                           "two_way": crossed_bootstrap_neff(
                               rows, column, config["first"], config["second"],
                               iterations=iterations, seed=seed)}
    detail_columns = ["event_id", "event_date", "y", "p_base", "p_recalibrated_s05",
                      "standin_loss", "loss_base", "loss_recalibrated", "paired_loss_differential",
                      config["first"], config["second"], config["one_way"]]
    detail = rows[detail_columns].copy()
    result = {"sport": sport, "n_rows": int(len(rows)), "one_way_key": config["one_way"],
              "crossed_labels": {"first": config["first"], "second": config["second"],
                                  "first_clusters": int(rows[config["first"]].nunique()),
                                  "second_clusters": int(rows[config["second"]].nunique())},
              "inputs": inputs, "metrics": metrics}
    return result, detail


def run(output_dir: Path = DETAIL_DIR, summary_path: Path = SUMMARY_PATH, *,
        iterations: int = ITERATIONS, seed: int = SEED) -> dict[str, Any]:
    """Write reproducible S202 evidence; no data store is written."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"gap": "S202", "seed": seed, "iterations": iterations,
                               "method": "crossed pigeonhole bootstrap of both label dimensions",
                               "row_policy": "all corpus rows retained; no size filter or dropped cluster",
                               "recalibrated_arm": {"prereg_path": "docs/evidence/harness/S05_calibration_prereg_2026-09-03.md",
                                                   "prereg_seal_sha256": "9051BB6E3BD89F7309A799F9739C8E61EA6DB3530E52AD87666568220591DF8A"},
                               "code_sha256": {}, "corpora": {}}
    for route in (Path(__file__), REPO / "scripts/platformkit/ingame/gap_effective_n.py",
                  REPO / "scripts/platformkit/eval_gate/calibration_report.py"):
        summary["code_sha256"][str(route.resolve())] = _sha256(route)
    for sport in CONFIG:
        result, detail = analyze_sport(sport, iterations=iterations, seed=seed)
        detail_path = output_dir / (sport + "_paired_losses.csv")
        detail.to_csv(detail_path, index=False, encoding="ascii")
        result["paired_loss_series_path"] = str(detail_path.relative_to(REPO)).replace("\\", "/")
        result["paired_loss_series_sha256"] = _sha256(detail_path)
        summary["corpora"][sport] = result
        print("%s n=%d standin_one_way=%.6f standin_two_way=%.6f paired_one_way=%.6f paired_two_way=%.6f" % (
            sport, result["n_rows"], result["metrics"]["standin_loss"]["one_way"]["n_eff"],
            result["metrics"]["standin_loss"]["two_way"]["n_eff"],
            result["metrics"]["paired_loss_differential"]["one_way"]["n_eff"],
            result["metrics"]["paired_loss_differential"]["two_way"]["n_eff"]))
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


if __name__ == "__main__":
    run()
