"""Offline re-scoring for canonical tracking CSVs after harness changes."""
from __future__ import annotations

import importlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from scripts.platformkit.tracking_harness import DEFAULT_CONFIG_VERSION, evaluate


_DOMAIN_ALIASES = {"basketball": "basketball_nba", "wnba": "basketball_nba"}
_LOWER_IS_BETTER = {"n_duplicate_frame_track_rows", "jump_p95", "oob_pct"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _prior_report(reports_root: Path, game_id: str) -> tuple[dict[str, Any], Path | None]:
    matches = sorted(reports_root.glob("*/{}.json".format(game_id)))
    if not matches:
        return {}, None
    return _read_json(matches[0]), matches[0]


def _sport_for(game_id: str, prior: Mapping[str, Any], sports_map: Mapping[str, str]) -> str:
    sport = sports_map.get(game_id) or prior.get("sport")
    if not isinstance(sport, str) or not sport:
        raise ValueError("sport unavailable for {}; add it to sports_map".format(game_id))
    return sport


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "as_dict"):
        return value.as_dict()
    return value


def _depth_probe(csv_path: Path, sport: str, prior: Mapping[str, Any]) -> Any | None:
    """Run an adapter probe when its optional module and compatible API exist."""
    domain = _DOMAIN_ALIASES.get(sport, sport)
    try:
        probe = importlib.import_module("domains.{}.tracking.quality_probe".format(domain))
    except (ImportError, ModuleNotFoundError):
        return None
    rows = pd.read_csv(csv_path)
    metadata = prior.get("source_metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    try:
        if hasattr(probe, "quality_probe"):
            return _json_value(probe.quality_probe(csv_path, sport=sport))
        if hasattr(probe, "quality_report_csv"):
            return _json_value(probe.quality_report_csv(csv_path))
        if hasattr(probe, "quality_report"):
            return _json_value(probe.quality_report(rows))
        if hasattr(probe, "probe_tracking_depth"):
            return _json_value(probe.probe_tracking_depth(rows, metadata))
        if hasattr(probe, "probe_quality"):
            return _json_value(probe.probe_quality(metadata))
    except (KeyError, TypeError, ValueError, OSError, pd.errors.ParserError):
        return None
    return None


def _metric_deltas(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, float]:
    return {
        key: round(float(value) - float(previous[key]), 6)
        for key, value in current.items()
        if key in previous and isinstance(value, (int, float))
        and not isinstance(value, bool) and isinstance(previous[key], (int, float))
        and not isinstance(previous[key], bool)
    }


def _improvement(metric: str, delta: float) -> float:
    return -delta if metric in _LOWER_IS_BETTER else delta


def _print_summary(total: int, passing: int, failing: int,
                   improvements: list[tuple[float, str, str, float]]) -> None:
    print("games rescored={}".format(total))
    print("newly passing={}".format(passing))
    print("newly failing={}".format(failing))
    best = sorted(improvements, reverse=True)[:3]
    text = ", ".join("{} {}={:+.4f}".format(game, metric, delta)
                     for _, game, metric, delta in best if _ > 0)
    print("biggest metric improvements={}".format(text or "none"))


def rescore_all(tracking_root: str | Path, reports_root: str | Path,
                sports_map: Mapping[str, str]) -> dict[str, int]:
    """Re-evaluate every local tracking CSV and append report-change evidence."""
    tracking = Path(tracking_root)
    reports = Path(reports_root)
    ledger_path = reports / "rescore_ledger.jsonl"
    reports.mkdir(parents=True, exist_ok=True)
    total = newly_passing = newly_failing = 0
    improvements: list[tuple[float, str, str, float]] = []

    with ledger_path.open("a", encoding="utf-8") as ledger:
        for csv_path in sorted(tracking.glob("*/tracking_data.csv")):
            game_id = csv_path.parent.name
            previous, _ = _prior_report(reports, game_id)
            sport = _sport_for(game_id, previous, sports_map)
            report = asdict(evaluate(pd.read_csv(csv_path), sport))
            depth = _depth_probe(csv_path, sport, previous)
            if depth is not None:
                report["depth_probe"] = depth
            destination = reports / sport / "{}.json".format(game_id)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n",
                                   encoding="utf-8")
            deltas = _metric_deltas(previous, report)
            before, after = bool(previous.get("passed")), bool(report["passed"])
            ledger.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(), "game_id": game_id,
                "sport": sport, "config_version": DEFAULT_CONFIG_VERSION,
                "metric_deltas": deltas, "passed_before": before, "passed_after": after,
            }, ensure_ascii=True) + "\n")
            total += 1
            newly_passing += int(not before and after)
            newly_failing += int(before and not after)
            improvements.extend((_improvement(metric, delta), game_id, metric, delta)
                                for metric, delta in deltas.items())
    _print_summary(total, newly_passing, newly_failing, improvements)
    return {"games_rescored": total, "newly_passing": newly_passing,
            "newly_failing": newly_failing}
