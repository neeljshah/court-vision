"""Continuously screen the Signal Foundry pool across rotated CPCV-lite configs."""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd

from scripts.platformkit import signal_foundry as foundry
from scripts.platformkit.novel_metric_lift import CANDIDATE_METRICS, pivot_player_metrics
from scripts.platformkit.teacher_student_ab import LOAD_FEATURES, build_features, expanding_folds


SUMMARY_PATH = Path(os.environ.get("FOUNDRY_RUNNER_SUMMARY", "data/ab_reports/foundry_runner.jsonl"))
PASS_CONFIGS = ((3, 1), (4, 2), (5, 1), (3, 2), (4, 1), (5, 2))


def build_minutes_matrix() -> tuple[pd.DataFrame, list[foundry.SignalSpec]]:
    """Build the demo minutes matrix and its complete reusable signal pool."""
    root = Path(os.environ.get("NBA_DATA_ROOT", "data"))
    nba = root / "nba"
    frame = build_features(
        pd.read_parquet(nba / "player_tracking_features_asof.parquet"),
        pd.read_parquet(nba / "player_load_state_asof.parquet"),
        pd.read_parquet(nba / "player_embeddings_asof.parquet"),
    )
    metrics = pivot_player_metrics(pd.read_parquet(root / "ab_reports" / "novel_metrics_players.parquet"))
    frame = frame.merge(metrics, on="personId", how="left").dropna(subset=["gameDate"])
    frame = frame.sort_values("gameDate").reset_index(drop=True)
    names = [*CANDIDATE_METRICS, *[name for name in frame if name in LOAD_FEATURES or name.startswith("style_embedding_")]]
    specs = []
    for name in names:
        spec = foundry.REGISTRY.get(name)
        if spec is None:
            spec = foundry.register(foundry.SignalSpec(name, "nba", "player_game", "none", name))
        specs.append(spec)
    return frame, specs


def _append_summary(item: dict[str, object]) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, allow_nan=False) + "\n")


def run_pass(number: int) -> dict[str, object]:
    """Run one configuration, preserving progress when an individual stage fails."""
    n_folds, embargo_blocks = PASS_CONFIGS[number % len(PASS_CONFIGS)]
    config = {"n_folds": n_folds, "embargo_blocks": embargo_blocks}
    grades: dict[str, int] = {}
    pool_delta: float | None = None
    signals: Sequence[foundry.SignalSpec] = []
    try:
        matrix, signals = build_minutes_matrix()
        folds = list(expanding_folds(matrix, folds=n_folds))
        original_embargo = foundry.EMBARGO_BLOCKS
        try:
            foundry.EMBARGO_BLOCKS = embargo_blocks
            for spec in signals:
                try:
                    result = foundry.evaluate_signal(matrix, "minutes", spec, folds)
                    grade = str(result.get("grade", "ERROR"))
                except Exception as error:  # A bad signal must not stop the pod.
                    print("signal_failed name={0} error={1}".format(spec.name, type(error).__name__))
                    grade = "ERROR"
                grades[grade] = grades.get(grade, 0) + 1
            try:
                pool_delta = float(foundry.combine_pool(matrix, "minutes", signals, folds)["oos_lift"])
            except Exception as error:  # Pool analysis is evidence-only and non-fatal.
                print("pool_failed error={0}".format(type(error).__name__))
        finally:
            foundry.EMBARGO_BLOCKS = original_embargo
    except Exception as error:
        print("pass_failed error={0}".format(type(error).__name__))
    summary = {"ts": datetime.now(timezone.utc).isoformat(), "pass_config": config,
               "n_signals": len(signals), "grades_histogram": grades, "pool_delta": pool_delta}
    _append_summary(summary)
    print("foundry_pass={0} folds={1} embargo={2} signals={3}".format(
        number, n_folds, embargo_blocks, len(signals)))
    return summary


def run(max_passes: int | None = None, sleep_seconds: float = 900.0) -> list[dict[str, object]]:
    """Run until stopped, or for a bounded number of passes in tests and jobs."""
    results = []
    while max_passes is None or len(results) < max_passes:
        results.append(run_pass(len(results)))
        if max_passes is None or len(results) < max_passes:
            time.sleep(sleep_seconds)
    return results


def main() -> None:
    """Run the pod loop with an optional bounded pass count."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-passes", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=900.0)
    args = parser.parse_args()
    run(args.max_passes, args.sleep_seconds)


if __name__ == "__main__":
    main()
