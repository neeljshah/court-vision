"""Run evidence-only retraining when the local data fingerprint changes.

Retraining NEVER changes claims. It only rebuilds leak-safe derived inputs and
appends the resulting A/B and out-of-sample evidence to the retrain ledger.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence

import pandas as pd

from scripts.platformkit import (
    player_embeddings,
    teacher_student_ab,
    tracking_features,
    tracking_load_state,
    wp_diag_oos,
    reforecast_refit,
)


LOG = logging.getLogger(__name__)
DEFAULT_INTERVAL_SECONDS = 1800


def fingerprint_data_state(data_root: Path) -> dict[str, Any]:
    """Return the small data-state fingerprint that controls a refit."""
    tracking_files = list((data_root / "tracking").glob("*/tracking_data.csv"))
    fingerprint: dict[str, Any] = {"tracking_csv_count": len(tracking_files)}
    cache_path = data_root / "cache" / "ingame_grade_joined"
    if cache_path.exists():
        fingerprint["ingame_grade_joined_mtime_ns"] = cache_path.stat().st_mtime_ns
    tracking_path = data_root / "nba" / "player_tracking_games.parquet"
    if tracking_path.exists():
        fingerprint["player_tracking_games_rows"] = int(len(pd.read_parquet(tracking_path)))
    return fingerprint


def _load_last_fingerprint(state_path: Path) -> Optional[dict[str, Any]]:
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8")).get("fingerprint")
    except (json.JSONDecodeError, OSError, AttributeError) as exc:
        LOG.warning("Could not read retrain state %s: %s", state_path, exc)
        return None


def _write_state(state_path: Path, fingerprint: Mapping[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"fingerprint": fingerprint}, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@contextmanager
def _clean_argv() -> Iterator[None]:
    """Keep nested module CLIs from seeing this loop's command-line flags."""
    old_argv = sys.argv
    sys.argv = [old_argv[0]]
    try:
        yield
    finally:
        sys.argv = old_argv


def _run_stage(name: str, stage: Callable[[], Any]) -> None:
    try:
        with _clean_argv():
            stage()
    except Exception:
        LOG.exception("Retrain stage failed: %s", name)


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOG.warning("Could not read retrain evidence %s: %s", path, exc)
        return None


def _ab_values(reports_dir: Path) -> tuple[Optional[str], Optional[float]]:
    report = _read_json(reports_dir / "teacher_student_minutes.json")
    pooled = report.get("pooled", {}) if report else {}
    return pooled.get("verdict"), pooled.get("delta")


def _oos_pooled_delta(reports_dir: Path) -> Optional[float]:
    reports = sorted(reports_dir.glob("wp_oos_*.json"), key=lambda path: path.stat().st_mtime_ns)
    report = _read_json(reports[-1]) if reports else None
    if not report:
        return None
    pooled = report.get("pooled")
    if isinstance(pooled, dict):
        return pooled.get("delta")
    values: list[tuple[int, float, float]] = []
    for section in report.get("sports", {}).values():
        result = section.get("walk_forward_isotonic", {}).get("pooled", {})
        before, after, rows = result.get("brier_before"), result.get("brier_after"), result.get("test_ticks")
        if before is not None and after is not None and rows:
            values.append((int(rows), float(before), float(after)))
    if not values:
        return None
    total = sum(rows for rows, _, _ in values)
    return sum(rows * (before - after) for rows, before, after in values) / total


def _append_ledger(reports_dir: Path, fingerprint: Mapping[str, Any]) -> None:
    verdict, delta = _ab_values(reports_dir)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "fingerprint": dict(fingerprint),
        "ab_verdict": verdict,
        "ab_delta": delta,
        "oos_pooled_delta": _oos_pooled_delta(reports_dir),
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    with (reports_dir / "retrain_ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")


def run_loop(
    max_passes: Optional[int] = None,
    data_root: Optional[Path] = None,
    sleep_seconds: int = DEFAULT_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Poll data state, rebuilding and recording evidence after each change."""
    if max_passes is not None and max_passes < 1:
        raise ValueError("max_passes must be positive")
    root = data_root or Path(os.environ.get("NBA_DATA_ROOT", "data"))
    reports_dir = root / "ab_reports"
    state_path = reports_dir / "retrain_state.json"
    passes = 0
    stages = (
        ("tracking_features", tracking_features.main),
        ("tracking_load_state", tracking_load_state.main),
        ("player_embeddings", player_embeddings.main),
        ("teacher_student_ab", teacher_student_ab.main),
        ("wp_diag_oos", wp_diag_oos.main),
    )
    while max_passes is None or passes < max_passes:
        passes += 1
        try:
            fingerprint = fingerprint_data_state(root)
        except Exception:
            LOG.exception("Could not fingerprint data state")
        else:
            if fingerprint != _load_last_fingerprint(state_path):
                for name, stage in stages:
                    _run_stage(name, stage)
                _run_stage(
                    "reforecast_refit",
                    lambda: reforecast_refit.replay_and_refit("retrain_%d" % passes),
                )
                _append_ledger(reports_dir, fingerprint)
                _write_state(state_path, fingerprint)
        if max_passes is None or passes < max_passes:
            sleep(sleep_seconds)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the standing retrain loop, optionally for a bounded test run."""
    parser = argparse.ArgumentParser(description="Poll data and append retrain evidence.")
    parser.add_argument("--max-passes", type=int)
    args = parser.parse_args(argv)
    run_loop(max_passes=args.max_passes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
