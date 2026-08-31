"""Aggregate tracking-quality evidence into per-sport repair priorities.

Run: python scripts/platformkit/tracking_brain.py
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

from scripts.platformkit.tracking_harness import SPORTS


REPORTS_DIR = Path("data/tracking_reports")
METRICS = ("coverage", "ball_valid", "jump_p95", "oob")
RULES = {
    "coverage": "detector/coverage: check court-view segmentation + detector confidence",
    "ball_valid": "ball detector upgrade (TrackNet-class)",
    "jump_p95": "homography stability: recalibrate/keyframe cadence",
    "oob": "calibration bounds/projection bug",
}


def _report_path(sport: str, reports_dir: Path) -> Path:
    return reports_dir / sport


def _load_reports(sport: str, reports_dir: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(_report_path(sport, reports_dir).glob("*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(report, dict):
            reports.append(report)
    return reports


def _metric_value(report: dict[str, Any], metric: str) -> float | None:
    key = f"{metric}_pct" if metric in ("coverage", "ball_valid", "oob") else metric
    value = report.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _threshold_margin(metric: str, value: float, cfg: dict[str, Any]) -> float:
    """Return positive when the metric clears its threshold, negative when failing."""
    if metric in ("coverage", "ball_valid"):
        threshold = cfg[f"{metric}_min"]
        return (value - threshold) / threshold
    threshold = cfg[f"{metric}_max"]
    return (threshold - value) / threshold


def scorecard(sport: str, reports_dir: Path = REPORTS_DIR) -> dict[str, Any]:
    """Return aggregate tracking quality for one sport."""
    if sport not in SPORTS:
        raise ValueError(f"Unknown sport: {sport}")
    reports = _load_reports(sport, reports_dir)
    medians = {
        metric: median(values)
        for metric in METRICS
        if (values := [value for report in reports
                       if (value := _metric_value(report, metric)) is not None])
    }
    cfg = SPORTS[sport]
    worst_metric = min(
        medians,
        key=lambda metric: _threshold_margin(metric, medians[metric], cfg),
        default=None,
    )
    trend = {}
    for metric in METRICS:
        values = [value for report in reports
                  if (value := _metric_value(report, metric)) is not None]
        if len(values) >= 10:
            trend[metric] = {
                "last_5": median(values[-5:]),
                "previous_5": median(values[-10:-5]),
            }
    return {
        "games_scored": len(reports),
        "pass_rate": sum(bool(report.get("passed")) for report in reports) / len(reports)
        if reports else 0.0,
        "metric_medians": medians,
        "worst_metric": worst_metric,
        "trend": trend,
    }


def _sports_with_evidence(reports_dir: Path) -> set[str]:
    sports = {path.name for path in reports_dir.iterdir() if path.is_dir()} if reports_dir.exists() else set()
    ledger = reports_dir / "ledger.jsonl"
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                sport = json.loads(line).get("sport")
            except json.JSONDecodeError:
                continue
            if isinstance(sport, str):
                sports.add(sport)
    return sports & SPORTS.keys()


def _skipped_sports(reports_dir: Path) -> set[str]:
    ledger = reports_dir / "ledger.jsonl"
    if not ledger.exists():
        return set()
    skipped = set()
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("status") == "skipped" and entry.get("sport") in SPORTS:
            skipped.add(entry["sport"])
    return skipped


def next_actions(reports_dir: Path = REPORTS_DIR) -> list[dict[str, Any]]:
    """Rank evidence-backed tracking work, with collection gaps first."""
    actions = []
    skipped = _skipped_sports(reports_dir)
    for sport in sorted(_sports_with_evidence(reports_dir)):
        card = scorecard(sport, reports_dir)
        if card["games_scored"] < 10:
            actions.append({"sport": sport, "priority": 1,
                            "reason": f"insufficient games ({card['games_scored']} < 10)",
                            "suggested_action": "run footage queue"})
        if sport in skipped:
            actions.append({"sport": sport, "priority": 2,
                            "reason": "not_implemented tracker",
                            "suggested_action": "implement tracker before quality tuning"})
        if card["worst_metric"]:
            metric = card["worst_metric"]
            actions.append({"sport": sport, "priority": 3,
                            "reason": f"worst metric: {metric}",
                            "suggested_action": RULES[metric]})
    return sorted(actions, key=lambda action: (action["priority"], action["sport"]))


def main() -> None:
    """Print a compact ASCII dashboard for the hourly dispatch loop."""
    sports = sorted(_sports_with_evidence(REPORTS_DIR))
    print("SPORT       GAMES  PASS_RATE  WORST_METRIC")
    for sport in sports:
        card = scorecard(sport)
        print(f"{sport:<11} {card['games_scored']:>5}  {card['pass_rate']:>9.1%}  "
              f"{card['worst_metric'] or '-'}")
    print("\nPRIORITY  SPORT       REASON                                      ACTION")
    for action in next_actions():
        print(f"{action['priority']:>8}  {action['sport']:<11} {action['reason']:<43} "
              f"{action['suggested_action']}")


if __name__ == "__main__":
    main()
