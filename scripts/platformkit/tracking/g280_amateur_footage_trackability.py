"""Run and profile G280's unchanged basketball image-space production route."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = (
    "frame", "track_id", "cls", "x", "y", "coordinate_space", "observation",
    "calibration", "source_fps", "source_height", "source_duration",
)
ROUTE_FILES = (
    "domains/basketball/tracking/adapter.py",
    "scripts/platformkit/adapter_run.py",
    "scripts/platformkit/detection/shim.py",
)


def digest(path: Path) -> str:
    """Return an input or route SHA-256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantiles(values: list[float]) -> dict[str, float | None]:
    """Return G280's linear-interpolated distribution summary."""
    if not values:
        return {name: None for name in ("median", "p90", "p99", "p999", "max")}
    series = pd.Series(values, dtype="float64")
    return {
        "median": float(series.quantile(0.5, interpolation="linear")),
        "p90": float(series.quantile(0.9, interpolation="linear")),
        "p99": float(series.quantile(0.99, interpolation="linear")),
        "p999": float(series.quantile(0.999, interpolation="linear")),
        "max": float(series.max()),
    }


def source_facts(video: Path, tracking_root: Path) -> dict[str, Any]:
    """Verify G280's source identity and exhaustively search the tracking store."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(video)],
        check=True, capture_output=True, text=True,
    )
    metadata = json.loads(probe.stdout)
    stream = metadata["streams"][0]
    matches: list[str] = []
    for path in sorted(tracking_root.rglob("*")):
        if video.name in path.name:
            matches.append(str(path))
            continue
        if not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                matched = any(video.name.encode("ascii") in block
                              for block in iter(lambda: handle.read(1_048_576), b""))
            if matched:
                matches.append(str(path))
        except OSError:
            continue
    return {
        "source_path": str(video), "source_name": video.name,
        "source_bytes": video.stat().st_size, "source_width": int(stream["width"]),
        "source_height": int(stream["height"]), "source_fps": stream["r_frame_rate"],
        "source_duration_seconds": float(metadata["format"]["duration"]),
        "source_frame_count": int(stream["nb_frames"]),
        "tracking_store": str(tracking_root), "tracking_store_filename_matches": matches,
        "tracking_store_filename_match_count": len(matches),
    }


def disk_guard(workspace: Path) -> dict[str, Any]:
    """Measure /workspace and prove scratch writes before any artifact write."""
    used = subprocess.run(["du", "-sm", "/workspace"], check=True, capture_output=True,
                          text=True).stdout.split()[0]
    probe = workspace / ".g280_dd_probe"
    subprocess.run(["dd", "if=/dev/zero", "of=" + str(probe), "bs=1M", "count=1",
                    "conv=fsync", "status=none"], check=True)
    size = probe.stat().st_size
    probe.unlink()
    if size != 1_048_576:
        raise RuntimeError("dd probe byte count was not 1048576")
    return {"workspace_du_mb": int(used), "dd_probe_bytes": size,
            "dd_probe_removed": True}


def preflight(video: Path, tracking_root: Path, output: Path) -> dict[str, Any]:
    """Run the required pod-side guard, then persist source-premise facts."""
    guard = disk_guard(Path("/workspace/wt/a5"))
    result = {"disk_guard": guard, **source_facts(video, tracking_root)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return result


def run_production(video: Path, output: Path, root: Path) -> dict[str, Any]:
    """Import and run adapter_run's exact default basketball production path."""
    from domains.basketball.tracking.adapter import BasketballAdapter, write_csv
    from scripts.platformkit.adapter_run import _source_metadata
    from scripts.platformkit.tracking_timebase import sampling_plan

    source_metadata = _source_metadata(str(video))
    plan = sampling_plan(source_metadata.get("frame_rate"))
    adapter = BasketballAdapter()
    rows = adapter.process_video(
        video, max_frames=30_000, stride=plan.stride, player_only=True, image_space=True,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    write_csv(rows, output)
    report = {
        "route": "scripts.platformkit.adapter_run default basketball invocation; imported adapter path",
        "route_files_sha256": {name: digest(root / name) for name in ROUTE_FILES},
        "detector_model_environment": os.environ.get("CV_DETECTOR_MODEL"),
        "adapter_options": {"max_frames": 30_000, "stride": plan.stride,
                            "player_only": True, "image_space": True},
        "source_metadata": source_metadata,
        "rows": int(len(rows)), "columns": list(rows.columns),
        "adapter_metadata": adapter.last_metadata, "csv_sha256": digest(output),
    }
    output.with_name("run_manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    return report


def profile(path: Path) -> dict[str, Any]:
    """Compute G277's unchanged consecutive-source-frame image profile."""
    frame = pd.read_csv(path)
    missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        raise ValueError("missing required tracking schema fields: " + ",".join(missing))
    if frame.empty:
        return {"csv": str(path), "csv_sha256": digest(path), "detection_count": 0,
                "track_count": 0, "step_count": 0, "speed": quantiles([]),
                "track_length_frames": quantiles([]), "track_length_seconds": quantiles([]),
                "track_shorter_than_5_fraction": None, "schema_columns": list(frame.columns)}
    source_fps = sorted(set(float(value) for value in frame["source_fps"].dropna()))
    source_height = sorted(set(int(value) for value in frame["source_height"].dropna()))
    if len(source_fps) != 1 or len(source_height) != 1:
        raise ValueError("source fps and height must each be constant within a run")
    players = frame.loc[frame["cls"].eq("player")].copy()
    players = players.sort_values(["track_id", "frame"], kind="mergesort")
    lengths = players.groupby("track_id", sort=False).size()
    prior = players.groupby("track_id", sort=False)[["frame", "x", "y"]].shift()
    consecutive = players["frame"].sub(prior["frame"]).eq(1)
    speeds = (players.loc[consecutive, "x"].sub(prior.loc[consecutive, "x"]).pow(2)
              .add(players.loc[consecutive, "y"].sub(prior.loc[consecutive, "y"]).pow(2))
              .pow(0.5).div(source_height[0]).mul(source_fps[0]).tolist())
    lengths_list = [float(value) for value in lengths.tolist()]
    return {
        "csv": str(path), "csv_sha256": digest(path), "schema_columns": list(frame.columns),
        "detection_count": int(len(players)), "all_row_count": int(len(frame)),
        "track_count": int(len(lengths)), "step_count": len(speeds),
        "speed_unit": "frame_heights_per_second",
        "speed_formula": "sqrt(dx^2+dy^2)/source_height*source_fps on consecutive source-frame same-track_id steps",
        "speed": quantiles(speeds), "track_length_frames": quantiles(lengths_list),
        "track_length_seconds": quantiles([value / source_fps[0] for value in lengths_list]),
        "track_shorter_than_5_fraction": (float((lengths < 5).mean()) if len(lengths) else None),
        "source_fps": source_fps[0], "source_height": source_height[0],
        "coordinate_space_values": sorted(frame["coordinate_space"].dropna().unique().tolist()),
        "calibration_values": sorted(frame["calibration"].dropna().unique().tolist()),
    }


def analyze(paths: list[Path], output: Path) -> list[dict[str, Any]]:
    """Write the required machine-readable per-run measurement summary."""
    rows = [profile(path) for path in paths]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="ascii")
    with output.with_suffix(".csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=("run", "detection_count", "track_count", "step_count",
                                                     "speed_median", "speed_p90", "speed_p99", "speed_p999",
                                                     "speed_max", "track_length_median_frames",
                                                     "track_length_p90_frames", "track_shorter_than_5_fraction"))
        writer.writeheader()
        for index, row in enumerate(rows, 1):
            writer.writerow({"run": "run_%d" % index, "detection_count": row["detection_count"],
                             "track_count": row["track_count"], "step_count": row["step_count"],
                             **{"speed_" + key: row["speed"][key] for key in ("median", "p90", "p99", "p999", "max")},
                             "track_length_median_frames": row["track_length_frames"]["median"],
                             "track_length_p90_frames": row["track_length_frames"]["p90"],
                             "track_shorter_than_5_fraction": row["track_shorter_than_5_fraction"]})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    check = sub.add_parser("preflight")
    check.add_argument("--video", type=Path, required=True)
    check.add_argument("--tracking-root", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--video", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--root", type=Path, default=Path("."))
    summary = sub.add_parser("analyze")
    summary.add_argument("--inputs", type=Path, nargs="+", required=True)
    summary.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = (preflight(args.video, args.tracking_root, args.output) if args.action == "preflight" else
              run_production(args.video, args.output, args.root) if args.action == "run" else
              analyze(args.inputs, args.output))
    print(json.dumps(result if isinstance(result, dict) else {"run_count": len(result)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
