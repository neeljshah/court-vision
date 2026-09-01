"""Regression gate for fixed tracking reference clips.

This compares self-consistency metrics on fixed footage and detects regressions;
it does not certify tracking accuracy. A clip can pass every gate while still
tracking the wrong court.
"""
from __future__ import annotations

import argparse
import importlib
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from scripts.platformkit.adapter_run import ADAPTERS, PLAYER_ONLY
from scripts.platformkit.corpus_rescore import _improvement, _metric_deltas
from scripts.platformkit.tracking_harness import evaluate


_VIDEO_SUFFIXES = {".avi", ".mkv", ".mov", ".mp4", ".webm"}
MetricDiff = tuple[float | None, float | None, str]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _read_baseline(path: Path) -> dict[str, dict[str, float]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid baseline JSON: {}".format(path)) from exc
    sports = raw.get("sports", raw) if isinstance(raw, dict) else {}
    if not isinstance(sports, dict):
        raise ValueError("baseline sports must be an object")
    return {
        str(sport): {str(name): float(value) for name, value in metrics.items()
                     if _is_number(value)}
        for sport, metrics in sports.items() if isinstance(metrics, dict)
    }


def _reference_clips(reference_dir: Path) -> list[tuple[str, Path]]:
    if not reference_dir.is_dir():
        return []
    clips: list[tuple[str, Path]] = []
    for clip in sorted(reference_dir.rglob("*")):
        if not clip.is_file() or clip.suffix.lower() not in _VIDEO_SUFFIXES:
            continue
        relative = clip.relative_to(reference_dir)
        if len(relative.parts) < 2 or relative.parts[0] not in ADAPTERS:
            raise ValueError(
                "reference clips must be under <sport>/ and use an adapter sport: {}"
                .format(relative)
            )
        clips.append((relative.parts[0], clip))
    return clips


def _track_clip(sport: str, clip: Path, scratch_root: Path) -> dict[str, Any]:
    """Track one clip through its existing adapter and return harness metrics."""
    module_name, class_name = ADAPTERS[sport]
    module = importlib.import_module(module_name)
    adapter = getattr(module, class_name)()
    options: dict[str, Any] = {"max_frames": 30000, "stride": 3}
    if sport in PLAYER_ONLY:
        options["player_only"] = True
    frame = adapter.process_video(str(clip), **options)
    game_id = "reference_{}_{}".format(sport, clip.stem)
    output_path = scratch_root / game_id / "tracking_data.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    module.write_csv(frame, str(output_path))
    return asdict(evaluate(pd.read_csv(output_path), sport))


def _current_metrics(reference_dir: Path) -> dict[str, dict[str, float]]:
    clips = _reference_clips(reference_dir)
    if not clips:
        return {}
    current: dict[str, dict[str, float]] = {}
    with tempfile.TemporaryDirectory(prefix="tracking_regression_") as scratch:
        scratch_root = Path(scratch)
        for sport, clip in clips:
            if sport in current:
                raise ValueError("only one reference clip per sport is supported: {}".format(sport))
            report = _track_clip(sport, clip, scratch_root)
            current[sport] = {key: float(value) for key, value in report.items()
                              if _is_number(value)}
    return current


def _compare_metrics(baseline: Mapping[str, Any],
                     current: Mapping[str, Any]) -> dict[str, MetricDiff]:
    deltas = _metric_deltas(baseline, current)
    comparisons: dict[str, MetricDiff] = {}
    for metric in sorted(set(baseline) | set(current)):
        before, after = baseline.get(metric), current.get(metric)
        if not _is_number(before):
            if _is_number(after):
                comparisons[metric] = (None, float(after), "new")
            continue
        if not _is_number(after):
            comparisons[metric] = (float(before), None, "regressed")
            continue
        delta = deltas[metric]
        if delta == 0:
            verdict = "ok"
        elif _improvement(metric, delta) > 0:
            verdict = "improved"
        else:
            verdict = "regressed"
        comparisons[metric] = (float(before), float(after), verdict)
    return comparisons


def run_reference_regression(
        baseline_path: str | Path,
        reference_dir: Path = Path("data/videos/reference"),
) -> dict[str, dict[str, MetricDiff]]:
    """Re-track reference clips and compare their harness metrics to baseline."""
    baseline = _read_baseline(Path(baseline_path))
    current = _current_metrics(Path(reference_dir))
    return {sport: _compare_metrics(baseline.get(sport, {}), metrics)
            for sport, metrics in current.items()}


def _write_baseline(path: Path, results: Mapping[str, Mapping[str, MetricDiff]]) -> None:
    sports = {
        sport: {metric: current for metric, (_, current, _) in metrics.items()
                if _is_number(current)}
        for sport, metrics in results.items()
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "sports": sports}, indent=2,
                               sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def _print_results(results: Mapping[str, Mapping[str, MetricDiff]]) -> None:
    if not results:
        print("reference regression: no reference corpus yet")
    for sport, metrics in sorted(results.items()):
        print("sport={}".format(sport))
        for metric, (before, after, verdict) in sorted(metrics.items()):
            print("  {} baseline={} current={} verdict={}".format(
                metric, before, after, verdict
            ))
    print("This detects regressions on fixed footage; it does not certify tracking accuracy.")
    print("A clip can pass every gate and still be tracking the wrong court.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fixed-footage tracking regression checks.")
    parser.add_argument("--baseline", default="scripts/platformkit/reference_baseline.json")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)
    results = run_reference_regression(args.baseline)
    _print_results(results)
    if args.update_baseline:
        _write_baseline(Path(args.baseline), results)
        print("baseline updated={}".format(args.baseline))
    return int(any(verdict == "regressed" for metrics in results.values()
                   for _, _, verdict in metrics.values()))


if __name__ == "__main__":
    raise SystemExit(main())
