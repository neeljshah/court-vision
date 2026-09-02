"""Read-only G74 geometric off-frame evidence collection."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


TABLE_PATH = "/workspace/nba-ai-system/data/tracking/test720_4MoMewm2j-o/tracking_data.csv"
RUN_LOG_PATH = "/workspace/nba-ai-system/data/tracking/test720_4MoMewm2j-o/run.log"


def is_off_frame(bbox: tuple[float, float, float, float], width: int, height: int) -> tuple[bool, list[str]]:
    """Return whether a bbox is geometrically outside [0,width] x [0,height]."""
    x1, y1, x2, y2 = bbox
    low_x, high_x = min(x1, x2), max(x1, x2)
    low_y, high_y = min(y1, y2), max(y1, y2)
    reasons = []
    if low_x < 0:
        reasons.append("x_min_lt_0")
    if high_x > width:
        reasons.append("x_max_gt_width")
    if low_y < 0:
        reasons.append("y_min_lt_0")
    if high_y > height:
        reasons.append("y_max_gt_height")
    return bool(reasons), reasons


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Compute the two-sided Wilson interval for a binomial proportion."""
    if trials == 0:
        return (0.0, 0.0)
    proportion = successes / trials
    denominator = 1 + z * z / trials
    center = (proportion + z * z / (2 * trials)) / denominator
    radius = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * trials)) / trials) / denominator
    lower = 0.0 if successes == 0 else max(0.0, center - radius)
    upper = 1.0 if successes == trials else min(1.0, center + radius)
    return (lower, upper)


def evenly_spaced(items: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Select up to count items across the full ordered population, not its head."""
    if len(items) <= count:
        return items
    positions = [(2 * index + 1) * len(items) // (2 * count) for index in range(count)]
    return [items[position] for position in positions]


def _remote(config: Path, host: str, source: str) -> dict[str, Any]:
    encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
    command = f"echo {encoded} | base64 -d | python3"
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-F", str(config), host, command],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"remote evidence probe failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _measurement_source() -> str:
    return f'''
import csv, hashlib, json, math, os, re
import cv2
TABLE = {TABLE_PATH!r}
LOG = {RUN_LOG_PATH!r}
with open(LOG, encoding="utf-8", errors="replace") as handle:
    match = re.search(r" Video : (.+)", handle.read())
if not match:
    raise RuntimeError("run.log does not name the source video")
recorded_video = match.group(1).strip()
candidates = [recorded_video, os.path.join("/workspace/nba-ai-system/data/videos/full_games", os.path.basename(recorded_video))]
video, width, height = "", 0, 0
for candidate in candidates:
    capture = cv2.VideoCapture(candidate)
    candidate_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    candidate_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()
    if candidate_width > 0 and candidate_height > 0:
        video, width, height = candidate, candidate_width, candidate_height
        break
if width <= 0 or height <= 0:
    raise RuntimeError(f"cannot read frame bounds from any known copy of {{recorded_video}}")
frame_bounds_source = "recorded input path in run.log" if video == recorded_video else "same-named archived full-games copy; recorded input path in run.log was unavailable"
with open(TABLE, "rb") as handle:
    table_sha256 = hashlib.sha256(handle.read()).hexdigest()
with open(TABLE, newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    columns = reader.fieldnames or []
    flags = []
    for source_row, raw in enumerate(reader, start=1):
        values = [raw.get(name, "") for name in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")]
        try:
            bbox = tuple(float(value) for value in values)
            if not all(math.isfinite(value) for value in bbox):
                raise ValueError("non-finite")
            x1, y1, x2, y2 = bbox
            low_x, high_x, low_y, high_y = min(x1,x2), max(x1,x2), min(y1,y2), max(y1,y2)
            reasons = []
            if low_x < 0: reasons.append("x_min_lt_0")
            if high_x > width: reasons.append("x_max_gt_width")
            if low_y < 0: reasons.append("y_min_lt_0")
            if high_y > height: reasons.append("y_max_gt_height")
            evaluable, off_frame = True, bool(reasons)
        except (TypeError, ValueError):
            x1 = y1 = x2 = y2 = None
            evaluable, off_frame, reasons = False, False, ["bbox_missing_or_nonfinite"]
        flags.append({{
            "source_row": source_row, "frame": raw.get("frame", ""), "track_id": raw.get("player_id", ""),
            "bbox_x1": x1, "bbox_y1": y1, "bbox_x2": x2, "bbox_y2": y2,
            "geometry_evaluable": evaluable, "off_frame": off_frame, "off_frame_reasons": ";".join(reasons),
        }})
coast_names = {{"is_coast", "coasted", "coast", "detection_matched", "matched_to_detection", "predicted_only", "is_prediction", "tracker_state", "track_status", "observation_type", "association_status"}}
coast_fields = [column for column in columns if column.lower() in coast_names]
print(json.dumps({{
    "table_path": TABLE, "table_sha256": table_sha256, "source_video": video, "recorded_input_video": recorded_video,
    "frame_width": width, "frame_height": height, "frame_bounds_source": frame_bounds_source, "row_count": len(flags),
    "column_count": len(columns), "columns": columns, "coast_fields": coast_fields, "flags": flags,
}}, separators=(",", ":")))
'''


def _render_source(selection: list[dict[str, Any]], source_video: str) -> str:
    encoded_selection = json.dumps(selection, separators=(",", ":"))
    return f'''
import base64, json
import cv2
selection = json.loads({encoded_selection!r})
capture = cv2.VideoCapture({source_video!r})
images = []
for row in selection:
    capture.set(cv2.CAP_PROP_POS_FRAMES, int(float(row["frame"])))
    ok, image = capture.read()
    if not ok:
        raise RuntimeError(f"cannot decode frame {{row['frame']}}")
    x1, y1, x2, y2 = (round(float(row[name])) for name in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))
    height, width = image.shape[:2]
    low_x, high_x, low_y, high_y = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
    visible = low_x < width and high_x >= 0 and low_y < height and high_y >= 0
    if visible:
        cv2.rectangle(image, (max(0, low_x), max(0, low_y)), (min(width - 1, high_x), min(height - 1, high_y)), (0, 0, 255), 3)
    else:
        marker = (0 if high_x < 0 else width - 1 if low_x >= width else max(0, min(width - 1, (low_x + high_x) // 2)), 0 if high_y < 0 else height - 1 if low_y >= height else max(0, min(height - 1, (low_y + high_y) // 2)))
        cv2.drawMarker(image, marker, (0, 0, 255), cv2.MARKER_TILTED_CROSS, 36, 3)
    label = f"row={{row['source_row']}} frame={{row['frame']}} track={{row['track_id']}} bbox=({{x1}},{{y1}},{{x2}},{{y2}})"
    cv2.putText(image, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise RuntimeError("jpeg encoding failed")
    images.append({{"source_row": row["source_row"], "jpeg_b64": base64.b64encode(encoded.tobytes()).decode("ascii")}})
capture.release()
print(json.dumps({{"images": images}}, separators=(",", ":")))
'''


def _summary(flags: Iterable[dict[str, Any]], measurement: dict[str, Any]) -> dict[str, Any]:
    rows = list(flags)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["track_id"])].append(row)

    def report(unit: list[dict[str, Any]]) -> dict[str, Any]:
        off = sum(bool(row["off_frame"]) for row in unit)
        evaluable = sum(bool(row["geometry_evaluable"]) for row in unit)
        low, high = wilson_interval(off, len(unit))
        return {
            "rows": len(unit), "geometry_evaluable_rows": evaluable, "off_frame_rows": off,
            "off_frame_fraction": off / len(unit) if unit else 0.0,
            "wilson_95": [low, high],
        }

    return {
        "scope": "one tracking table and its one source clip only",
        "definition": "A row is off-frame when its bbox's minimum x or y is below 0, or its maximum x exceeds frame width or maximum y exceeds frame height.",
        "frame_bounds": {"width": measurement["frame_width"], "height": measurement["frame_height"], "source": "cv2.VideoCapture of " + measurement["frame_bounds_source"]},
        "source": {key: measurement[key] for key in ("table_path", "table_sha256", "source_video", "recorded_input_video", "row_count", "column_count")},
        "pure_coast": {"evaluable": bool(measurement["coast_fields"]), "candidate_fields": measurement["coast_fields"], "reason": "No detection/match/coast-status field is present." if not measurement["coast_fields"] else "Inspect candidate fields before interpreting."},
        "pooled": report(rows),
        "per_track": {track: report(unit) for track, unit in sorted(grouped.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0])},
    }


def collect(output: Path, ssh_config: Path, host: str, render_count: int) -> None:
    """Collect durable flags, summary, and read-only rendered evidence."""
    measurement = _remote(ssh_config, host, _measurement_source())
    flags = measurement.pop("flags")
    summary = _summary(flags, measurement)
    flagged = [row for row in flags if row["off_frame"]]
    selection = evenly_spaced(flagged, render_count)
    if len(selection) < render_count:
        raise RuntimeError(f"only {{len(selection)}} flagged rows; need {{render_count}} renders")
    rendered = _remote(ssh_config, host, _render_source(selection, measurement["source_video"]))["images"]
    output.mkdir(parents=True, exist_ok=True)
    renders = output / "renders"
    renders.mkdir(exist_ok=True)
    with (output / "per_row_flags.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flags[0]))
        writer.writeheader()
        writer.writerows(flags)
    for image in rendered:
        target = renders / f"offframe_row_{int(image['source_row']):05d}.jpg"
        target.write_bytes(base64.b64decode(image["jpeg_b64"]))
    selection_payload = {"method": "12 midpoint-spaced rows across the complete ordered flagged-row set (no head slice)", "flagged_row_count": len(flagged), "selected_rows": selection, "render_files": [f"renders/offframe_row_{int(row['source_row']):05d}.jpg" for row in selection]}
    (output / "render_selection.json").write_text(json.dumps(selection_payload, indent=2) + "\n", encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--host", default="pod")
    parser.add_argument("--render-count", type=int, default=12)
    args = parser.parse_args()
    collect(args.output, args.ssh_config, args.host, args.render_count)


if __name__ == "__main__":
    main()
