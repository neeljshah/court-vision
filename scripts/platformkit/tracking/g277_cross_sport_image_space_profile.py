"""Summarize landed image_px track records for G277 without replaying tracking."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
SPORTS = ("ncaa_basketball", "football", "soccer", "tennis", "wnba", "kbo", "mlb", "npb")
SPEED_KEYS = ("speed_median", "speed_p90", "speed_p99", "speed_p999", "speed_max")
METRIC_KEYS = (
    "step_count", *SPEED_KEYS, "track_count", "track_length_median_frames",
    "track_length_p90_frames", "track_shorter_than_5_fraction",
    "track_length_median_seconds", "track_length_p90_seconds",
)
REQUIRED_FIELDS = {"frame", "track_id", "cls", "x", "y", "coordinate_space", "observation", "calibration", "source_fps", "source_height", "source_duration"}
def percentile(values: list[float], q: float) -> float | None:
    """Return the linearly interpolated q quantile of nonempty values."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
def sport_of(name: str) -> str:
    """Return the declared sport prefix from a tracking-run directory name."""
    for sport in SPORTS:
        if name == sport or name.startswith(f"{sport}_"):
            return sport
    return "unknown"
def exclusion_reason(name: str) -> str | None:
    """Identify the fifteen named non-footage detector/hash variants."""
    if name.startswith("g172_"):
        return "g172 detector/hash variant on the same footage"
    if re.match(r"^g225_yolov8[ns m]_r[123]_".replace(" ", ""), name):
        return "g225 YOLOv8 detector variant on the same footage"
    if name.startswith("g226c_"):
        return "g226c detector/hash variant on the same footage"
    if name.startswith("g239_"):
        return "g239 detector/hash variant on the same footage"
    if re.match(r"^g240_.*_r[123](?:_|$)", name):
        return "g240 detector/hash variant on the same footage"
    return None
def _number(row: dict[str, str], name: str) -> float:
    value = row.get(name, "")
    if value == "":
        raise ValueError(f"missing {name}")
    return float(value)
def _file_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": path.as_posix(), "bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _provenance_fields(value: Any, prefix: str = "", depth: int = 0) -> dict[str, Any]:
    """Extract bounded version/time/pipeline scalars from a JSON provenance record."""
    found: dict[str, Any] = {}
    if depth > 2 or not isinstance(value, dict):
        return found
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            found.update(_provenance_fields(item, name, depth + 1))
        elif isinstance(item, (str, int, float, bool)) and any(token in key.lower() for token in ("version", "tracker", "pipeline", "detector", "model", "created", "time", "date", "commit", "sha")):
            found[name] = item
    return dict(list(found.items())[:20])


def _provenance(run_dir: Path) -> dict[str, Any]:
    candidates = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "tracking_data.csv":
            continue
        lowered = path.name.lower()
        if any(token in lowered for token in ("manifest", "config", "metadata", "version", "time")) or path.suffix.lower() in {".json", ".yaml", ".yml", ".toml", ".ini"}:
            item = _file_record(path)
            item["path"] = path.relative_to(run_dir).as_posix()
            if path.suffix.lower() == ".json":
                try:
                    item["provenance_scalars"] = _provenance_fields(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    item["provenance_scalars"] = {"parse": "unavailable"}
            candidates.append(item)
    return {"tracking_csv": _file_record(run_dir / "tracking_data.csv"), "candidate_files": candidates}


def schema_check(path: Path) -> tuple[list[str], list[str]]:
    """Return the CSV header and required-field omissions without reading data rows."""
    with path.open(newline="", encoding="utf-8") as handle:
        fields = csv.reader(handle).__next__()
    return fields, sorted(REQUIRED_FIELDS.difference(fields))


def categorical_check(path: Path) -> tuple[int, dict[str, list[str] | None]]:
    """Read only per-run cls/observation categories for comparability checks."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        values = {field: set() if reader.fieldnames and field in reader.fieldnames else None for field in ("cls", "observation")}
        rows = 0
        for row in reader:
            rows += 1
            for field, found in values.items():
                if found is not None:
                    found.add(row[field])
    return rows, {field: sorted(found) if found is not None else None for field, found in values.items()}


def analyse_csv(path: Path, run_name: str) -> dict[str, Any]:
    """Stream one landed CSV and calculate run-level image-space summaries."""
    speeds: list[float] = []
    lengths: Counter[str] = Counter()
    prior: dict[str, tuple[int, float, float]] = {}
    values: dict[str, set[str]] = defaultdict(set)
    rows = duplicate_track_frames = nonmonotonic = invalid_numeric_rows = 0
    last_global_frame = -math.inf
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not REQUIRED_FIELDS.issubset(reader.fieldnames):
            raise ValueError(f"unexpected schema in {path}")
        for row in reader:
            rows += 1
            for field in ("cls", "observation", "coordinate_space", "calibration", "source_fps", "source_height", "source_duration"):
                values[field].add(row[field])
            track_id = row["track_id"]
            try:
                frame, x, y = int(float(row["frame"])), _number(row, "x"), _number(row, "y")
                fps, height = _number(row, "source_fps"), _number(row, "source_height")
                if fps <= 0 or height <= 0:
                    raise ValueError("nonpositive source metadata")
            except ValueError:
                invalid_numeric_rows += 1
                prior.pop(track_id, None)
                continue
            if frame < last_global_frame:
                nonmonotonic += 1
            last_global_frame = max(last_global_frame, frame)
            lengths[track_id] += 1
            previous = prior.get(track_id)
            duplicate_track_frames += previous is not None and frame == previous[0]
            if previous is not None and frame - previous[0] == 1:
                speeds.append(math.hypot(x - previous[1], y - previous[2]) / height * fps)
            prior[track_id] = (frame, x, y)
    try:
        fps_values = sorted(float(value) for value in values["source_fps"])
    except ValueError:
        fps_values = []
    frame_lengths = [float(value) for value in lengths.values()]
    fps = fps_values[0] if len(fps_values) == 1 else None
    result: dict[str, Any] = {
        "run": run_name, "sport": sport_of(run_name), "rows": rows, "step_count": len(speeds),
        "analysis_status": "comparable" if not invalid_numeric_rows else "data_incomplete",
        "invalid_numeric_required_rows": invalid_numeric_rows,
        "speed_median": percentile(speeds, 0.5), "speed_p90": percentile(speeds, 0.9),
        "speed_p99": percentile(speeds, 0.99), "speed_p999": percentile(speeds, 0.999),
        "speed_max": max(speeds) if speeds else None, "track_count": len(frame_lengths),
        "track_length_median_frames": percentile(frame_lengths, 0.5),
        "track_length_p90_frames": percentile(frame_lengths, 0.9),
        "track_shorter_than_5_fraction": sum(value < 5 for value in frame_lengths) / len(frame_lengths) if frame_lengths else None,
        "track_length_median_seconds": percentile([value / fps for value in frame_lengths], 0.5) if fps else None,
        "track_length_p90_seconds": percentile([value / fps for value in frame_lengths], 0.9) if fps else None,
        "metadata_values": {key: sorted(value) for key, value in values.items()},
        "cls_values": sorted(values["cls"]), "observation_values": sorted(values["observation"]),
        "frame_order_nonmonotonic_rows": nonmonotonic, "duplicate_track_frame_rows": duplicate_track_frames,
    }
    if invalid_numeric_rows:
        for key in METRIC_KEYS:
            result[key] = None
    return result


def placements(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Place each WNBA run in the included-run empirical distributions."""
    rows = []
    for run in runs:
        if run["sport"] != "wnba":
            continue
        for metric in METRIC_KEYS:
            value = run[metric]
            population = sorted(item[metric] for item in runs if item[metric] is not None)
            if value is None:
                continue
            lower = sum(item < value for item in population) + 1
            upper = sum(item <= value for item in population)
            rows.append({"run": run["run"], "metric": metric, "value": value, "population_n": len(population), "ascending_rank_low": lower, "ascending_rank_high": upper, "percentile_low": 100 * lower / len(population), "percentile_high": 100 * upper / len(population)})
    return rows


def sport_aggregation(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return medians of run-level statistics, not a quality ranking."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[run["sport"]].append(run)
    return [{"sport": sport, "run_count": len(items), **{metric: percentile([item[metric] for item in items if item[metric] is not None], 0.5) for metric in METRIC_KEYS}} for sport, items in sorted(grouped.items())]


def guard_workspace(workspace: Path, probe_dir: Path) -> dict[str, Any]:
    """Run the mandatory pod-side du and fsync write/remove guard."""
    before = int(subprocess.check_output(["du", "-sm", str(workspace)], text=True).split()[0])
    probe = probe_dir / ".g277_fsync_probe.bin"
    completed = subprocess.run(["dd", "if=/dev/zero", f"of={probe}", "bs=1M", "count=1", "conv=fsync", "status=none"], check=False, capture_output=True, text=True)
    freed = probe.stat().st_size if probe.exists() else 0
    if probe.exists():
        probe.unlink()
    after = int(subprocess.check_output(["du", "-sm", str(workspace)], text=True).split()[0])
    if completed.returncode:
        raise RuntimeError(f"disk guard failed rc={completed.returncode}: {completed.stderr.strip()}")
    return {"workspace": str(workspace), "du_sm_before": before, "du_sm_after": after, "probe_bytes_written_and_removed": freed, "probe_returncode": completed.returncode, "bytes_freed": freed}


def active_lane_worktrees() -> dict[str, list[int]]:
    """Census other Python lane CWDs; caller and its ancestor chain are excluded."""
    excluded: set[int] = set()
    current = os.getpid()
    while current and current not in excluded:
        excluded.add(current)
        try:
            current = int((Path(f"/proc/{current}/stat").read_text().split(") ", 1)[1].split()[1]))
        except (FileNotFoundError, IndexError, ValueError):
            break
    lanes: dict[str, list[int]] = defaultdict(list)
    for item in Path("/proc").iterdir():
        if not item.name.isdigit() or int(item.name) in excluded:
            continue
        try:
            executable = os.path.basename(os.readlink(item / "exe"))
            cwd = os.readlink(item / "cwd")
        except OSError:
            continue
        if executable.startswith("python") and re.fullmatch(r"/workspace/wt/a\d+", cwd):
            lanes[cwd].append(int(item.name))
    return {cwd: sorted(pids) for cwd, pids in sorted(lanes.items())}


def csv_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = ("run", "sport", "analysis_status", "schema_missing_fields", "invalid_numeric_required_rows", "cls_values", "observation_values", "rows", *METRIC_KEYS, "frame_order_nonmonotonic_rows", "duplicate_track_frame_rows")
    return [{key: run.get(key) for key in keys} for run in runs]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-root", type=Path, default=Path("data/tracking"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    arguments = parser.parse_args()
    lanes = active_lane_worktrees()
    if len(lanes) >= 2:
        raise RuntimeError(f"hold rule: two other lane worktrees active: {sorted(lanes)}")
    guard = guard_workspace(arguments.workspace, arguments.output_dir.parent)
    footage_runs, comparable_runs, excluded = [], [], []
    for csv_path in sorted(arguments.tracking_root.glob("*/tracking_data.csv")):
        name = csv_path.parent.name
        reason = exclusion_reason(name)
        if reason:
            excluded.append({"run": name, "reason": reason, "provenance": _provenance(csv_path.parent)})
        else:
            fields, missing = schema_check(csv_path)
            if missing:
                rows, checks = categorical_check(csv_path)
                footage_runs.append({"run": name, "sport": sport_of(name), "analysis_status": "schema_incompatible", "schema_missing_fields": missing, "header": fields, "rows": rows, "cls_values": checks["cls"], "observation_values": checks["observation"], "provenance": _provenance(csv_path.parent)})
                continue
            item = analyse_csv(csv_path, name)
            item["provenance"] = _provenance(csv_path.parent)
            footage_runs.append(item)
            if item["analysis_status"] == "comparable":
                comparable_runs.append(item)
    if not footage_runs and not excluded:
        raise FileNotFoundError(f"no tracking_data.csv below {arguments.tracking_root}")
    arguments.output_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "purpose": "G277 landed-record cross-sport image_px profile; no tracker or detector replayed",
        "normalization_formula": "sqrt(dx^2 + dy^2) / source_height * source_fps on consecutive-frame same-track_id steps",
        "quantile_method": "linear interpolation on sorted run-local values",
        "track_length_definition": "number of observed detector-box rows per track_id; seconds = rows/source_fps when fps is constant within run",
        "disk_guard": guard, "other_active_python_lane_worktrees": lanes,
        "route_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "footage_runs": footage_runs, "excluded_runs": excluded, "footage_run_count": len(footage_runs), "comparable_run_count": len(comparable_runs), "excluded_count": len(excluded),
        "sport_aggregation_run_level_medians": sport_aggregation(comparable_runs), "wnba_placements": placements(comparable_runs),
    }
    (arguments.output_dir / "g277_per_run_summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = csv_rows(footage_runs)
    with (arguments.output_dir / "g277_per_run_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["run"])
        writer.writeheader(); writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
