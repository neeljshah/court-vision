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
METRICS = ("coverage", "ball_valid", "jump_max", "oob")
RULES = {
    "coverage": "detector/coverage: check court-view segmentation + detector confidence",
    "ball_valid": "ball detector upgrade (TrackNet-class)",
    "jump_max": "homography stability: recalibrate/keyframe cadence",
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
    if metric == "jump_max":
        # G90: old report rows retain only the predecessor field. A current
        # row's explicit null is meaningful and must not be masked by p95.
        value = report["jump_max"] if "jump_max" in report else report.get("jump_p95")
    else:
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


def _coordinate_profile(report: dict[str, Any]) -> str:
    """Return a report's declared profile, preserving legacy court-feet reports."""
    declared = report.get("coordinate_profile", report.get("coordinate_space"))
    if isinstance(declared, str) and declared:
        return declared
    verdict = report.get("verdict")
    return "metric_local" if isinstance(verdict, str) and verdict.endswith("_METRIC_LOCAL") else "court_feet"


def _profile_scorecard(reports: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Return legacy scorecard fields for reports sharing one coordinate profile."""
    medians = {
        metric: median(values)
        for metric in METRICS
        if (values := [value for report in reports
                       if (value := _metric_value(report, metric)) is not None])
    }
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


def _scorecards_by_profile(reports: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Aggregate reports separately for every coordinate profile."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        grouped.setdefault(_coordinate_profile(report), []).append(report)
    return {profile: _profile_scorecard(group, cfg) for profile, group in sorted(grouped.items())}


def scorecard(sport: str, reports_dir: Path = REPORTS_DIR) -> dict[str, Any]:
    """Return profile-scoped aggregate tracking quality for one sport."""
    if sport not in SPORTS:
        raise ValueError(f"Unknown sport: {sport}")
    scoped = _scorecards_by_profile(_load_reports(sport, reports_dir), SPORTS[sport])
    # Retain the exact legacy object for court-feet-only corpora. It has no
    # rendered headline; main() supplies the explicit court_feet label.
    if set(scoped) <= {"court_feet"}:
        return scoped.get("court_feet", _profile_scorecard([], SPORTS[sport]))
    headline_profile = "court_feet" if "court_feet" in scoped else next(iter(scoped))
    return {
        "coordinate_profile": headline_profile,
        **scoped[headline_profile],
        "coordinate_profiles": {
            profile: {"coordinate_profile": profile, **card}
            for profile, card in scoped.items()
        }
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
        if "coordinate_profiles" in card:
            card = card["coordinate_profiles"].get("court_feet")
            if card is None:
                continue
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
    print("SPORT       PROFILE       GAMES  PASS_RATE  WORST_METRIC")
    for sport in sports:
        card = scorecard(sport)
        scoped = card.get("coordinate_profiles", {"court_feet": card})
        for profile, profile_card in scoped.items():
            print(f"{sport:<11} {profile:<13} {profile_card['games_scored']:>5}  "
                  f"{profile_card['pass_rate']:>9.1%}  {profile_card['worst_metric'] or '-'}")
    print("\nPRIORITY  SPORT       REASON                                      ACTION")
    for action in next_actions():
        print(f"{action['priority']:>8}  {action['sport']:<11} {action['reason']:<43} "
              f"{action['suggested_action']}")


if __name__ == "__main__":
    main()
