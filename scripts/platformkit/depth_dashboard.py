"""Collect and trend sport-specific tracking depth over completed games.

This measures observed tracking coverage only.  It makes no accuracy, edge,
or ROI claim.  Run with ``python scripts/platformkit/depth_dashboard.py``.
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

import pandas as pd

from scripts.platformkit.tracking_harness import SPORTS

LEDGER_PATH = Path("data/tracking_reports/depth_ledger.jsonl")
SPORT_MODULES = {
    "tennis": "domains.tennis.tracking.quality_probe",
    "soccer": "domains.soccer.tracking.quality_probe",
    "baseball": "domains.baseball.tracking.quality_probe",
    "basketball_nba": "domains.basketball_nba.tracking.quality_probe",
}

# Minimum operational depth floors. Percent metrics use 0..100; ratios use 0..1.
# Shared coverage/player/ball concepts reference SPORTS below (percent probes
# multiply the harness ratio by 100); adapter-only metrics use probe B floors.
SPORT_THRESHOLDS: dict[str, dict[str, float]] = {
    "tennis": {"pct_frames_two_players": 100.0 * SPORTS["tennis"]["coverage_min"],
                "pct_frames_ball": 100.0 * SPORTS["tennis"]["ball_valid_min"],
                "median_rally_length_frames": 10.0,
                "court_coverage_sqft_by_player_min": 10.0},
    "soccer": {"pct_frames_accepted_homography": 100.0 * SPORTS["soccer"]["coverage_min"],
                "median_players_per_accepted_frame": float(SPORTS["soccer"]["min_players"]),
                "pitch_view_segment_coverage": SPORTS["soccer"]["coverage_min"],
                "pressing_proxy_coverage": SPORTS["soccer"]["ball_valid_min"]},
    "baseball": {"pitch_view_frame_pct": SPORTS["baseball"]["coverage_min"],
                  "pitches_detected": float(SPORTS["baseball"]["min_players"]),
                  "scale_stability_rate": 0.50,
                  "command_meter_coverage": 0.50},
    "basketball_nba": {
        "pct_frames_ge_8_players": SPORTS["basketball"]["coverage_min"],
        "pct_frames_homography_valid": SPORTS["basketball"]["coverage_min"],
        "ball_row_coverage": SPORTS["basketball"]["ball_valid_min"],
        "jersey_number_fill_rate": 0.50,
        "team_assignment_fill_rate": 0.80,
    },
}
THRESHOLDS = SPORT_THRESHOLDS
def _sport_from_path(path: Path) -> str | None:
    parts = {part.lower() for part in path.parts}
    for sport in SPORT_MODULES:
        if sport in parts:
            return sport
    if "nba" in parts or "basketball" in parts:
        return "basketball_nba"
    return None


def _load_module(sport: str) -> Any | None:
    try:
        return importlib.import_module(SPORT_MODULES[sport])
    except (ImportError, ModuleNotFoundError):
        return None
def _as_dict(report: Any) -> dict[str, Any]:
    if isinstance(report, Mapping):
        return dict(report)
    for method in ("to_dict", "as_dict"):
        if hasattr(report, method):
            return dict(getattr(report, method)())
    if hasattr(report, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(report)
    raise TypeError("depth probe returned neither a mapping nor a report object")
def _numeric_metrics(report: Mapping[str, Any]) -> dict[str, float | int]:
    output: dict[str, float | int] = {}
    for name, value in report.items():
        if name in {"depth_grade", "grade"} or isinstance(value, bool):
            continue
        if isinstance(value, Mapping):
            numbers = [float(item) for item in value.values()
                       if isinstance(item, (int, float)) and not isinstance(item, bool)
                       and math.isfinite(float(item))]
            if numbers:
                output[name + "_min"] = min(numbers)
            continue
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            output[name] = value
    return output
def _metadata_index(root: Path) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    if not root.exists():
        return result
    for path in root.rglob("*.json"):
        if path.name == LEDGER_PATH.name:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items = [payload] if isinstance(payload, Mapping) else []
        for item in items:
            game_id = item.get("game_id")
            sport = item.get("sport") or _sport_from_path(path)
            if game_id is None and path.stem.lower() in {"metadata", "report", "quality"}:
                game_id = path.parent.name
            if game_id is None and path.stem.lower() not in {"summary", "index"}:
                game_id = path.stem
            if sport is None:
                sport = _sport_from_path(path.parent)
            metadata = item.get("metadata", item)
            if game_id is not None and sport in SPORT_MODULES and isinstance(metadata, Mapping):
                result[(sport, str(game_id))] = metadata
    return result
def _tracking_games(root: Path) -> dict[tuple[str, str], Path]:
    games: dict[tuple[str, str], Path] = {}
    if not root.exists():
        return games
    for path in root.rglob("tracking_data.csv"):
        sport = _sport_from_path(path) or "basketball_nba"
        games[(sport, path.parent.name)] = path
    return games
def _probe(sport: str, csv_path: Path | None, metadata: Mapping[str, Any]) -> dict[str, Any] | None:
    module = _load_module(sport)
    if module is None:
        return None
    try:
        if sport == "baseball":
            return _as_dict(module.probe_quality(metadata))
        if csv_path is None:
            return None
        if sport == "tennis":
            return _as_dict(module.quality_report_csv(csv_path))
        rows = pd.read_csv(csv_path)
        if sport == "soccer":
            return _as_dict(module.probe_tracking_depth(rows, metadata))
        return _as_dict(module.quality_probe(csv_path, sport="nba"))
    except (OSError, KeyError, TypeError, ValueError, pd.errors.ParserError):
        return None
def collect(reports_root: str | Path, tracking_root: str | Path) -> list[dict[str, Any]]:
    """Probe every discoverable game and append normalized rows to the ledger."""
    reports_root, tracking_root = Path(reports_root), Path(tracking_root)
    metadata = _metadata_index(reports_root)
    games = _tracking_games(tracking_root)
    games.update({key: None for key in metadata if key not in games})
    rows: list[dict[str, Any]] = []
    for (sport, game_id), csv_path in sorted(games.items()):
        report = _probe(sport, csv_path, metadata.get((sport, game_id), {}))
        if not report:
            continue
        grade = report.get("depth_grade", report.get("grade", "C"))
        row: dict[str, Any] = {"sport": sport, "game_id": game_id,
                               "depth_grade": str(grade),
                               "scored_at": datetime.now(timezone.utc).isoformat()}
        row.update(_numeric_metrics(report))
        rows.append(row)
    if rows:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER_PATH.open("a", encoding="ascii") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=True, allow_nan=False) + "\n")
    return rows
def _read_ledger(ledger: str | Path | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(ledger, (str, Path)):
        path = Path(ledger)
        if not path.exists():
            return []
        output = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                output.append(json.loads(line))
        return output
    if isinstance(ledger, Mapping):
        return [dict(item) for values in ledger.values() for item in values]
    return [dict(item) for item in ledger]
def _latest_games(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for item in rows:
        if "sport" not in item or "game_id" not in item:
            continue
        key = (str(item["sport"]), str(item["game_id"]))
        if key not in latest or str(item.get("scored_at", "")) >= str(latest[key].get("scored_at", "")):
            latest[key] = dict(item)
    return sorted(latest.values(), key=lambda item: str(item.get("scored_at", "")))
def trend(ledger: str | Path | Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Summarize grade mix, five-game medians, change, and the next fix."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in _latest_games(_read_ledger(ledger)):
        grouped.setdefault(str(row["sport"]), []).append(row)
    output: dict[str, dict[str, Any]] = {}
    for sport, games in sorted(grouped.items()):
        current = games[-5:]
        previous = games[-10:-5]
        metric_names = sorted({key for row in games for key, value in row.items()
                               if key not in {"sport", "game_id", "depth_grade", "scored_at"}
                               and isinstance(value, (int, float)) and not isinstance(value, bool)})

        def medians(items: list[dict[str, Any]]) -> dict[str, float]:
            return {name: float(median([float(row[name]) for row in items if name in row]))
                    for name in metric_names if any(name in row for row in items)}

        last, prior = medians(current), medians(previous)
        thresholds = SPORT_THRESHOLDS.get(sport, {})
        candidates = [(threshold - last[name], (threshold - last[name]) / abs(threshold), name,
                       last[name], threshold)
                      for name, threshold in thresholds.items()
                      if name in last and last[name] < threshold]
        bottleneck = None
        if candidates:
            _, relative, name, value, threshold = max(
                candidates, key=lambda item: (item[1], item[0], item[2]))
            bottleneck = {"metric": name, "value": value, "threshold": threshold,
                          "shortfall": threshold - value, "relative_shortfall": relative}
        output[sport] = {
            "current_grade_distribution": dict(sorted(Counter(row.get("depth_grade", "C") for row in games).items())),
            "last_5_medians": last,
            "previous_5_medians": prior,
            "median_change": {name: last[name] - prior[name] for name in last if name in prior},
            "bottleneck": bottleneck,
        }
    return output
def render_dashboard(summary: Mapping[str, Mapping[str, Any]]) -> str:
    """Render a compact ASCII-only dashboard."""
    lines = ["TRACKING DEPTH OVER TIME"]
    for sport, report in summary.items():
        grades = ", ".join(f"{key}={value}" for key, value in report["current_grade_distribution"].items())
        lines.append(f"\n{sport.upper()}  GRADES: {grades or 'none'}")
        lines.append("LAST5 MEDIANS: " + json.dumps(report["last_5_medians"], ensure_ascii=True, sort_keys=True))
        lines.append("PREV5 MEDIANS: " + json.dumps(report["previous_5_medians"], ensure_ascii=True, sort_keys=True))
        bottleneck = report["bottleneck"]
        lines.append("NEXT-FIX: " + (str(bottleneck["metric"]) if bottleneck else "none (all measured metrics meet thresholds)"))
    return "\n".join(lines)
def main() -> int:
    parser = argparse.ArgumentParser(description="Trend tracking depth for every available sport.")
    parser.add_argument("--reports-root", type=Path, default=Path("data/tracking_reports"))
    parser.add_argument("--tracking-root", type=Path, default=Path("data/tracking"))
    args = parser.parse_args()
    collect(args.reports_root, args.tracking_root)
    print(render_dashboard(trend(LEDGER_PATH)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
