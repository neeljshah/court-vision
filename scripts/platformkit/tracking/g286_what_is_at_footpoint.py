"""Prepare blind G286 footpoint crops, then unblind their sealed labels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from scripts.platformkit.tracking.g285b_locate_then_match import read_locations

CROP_WIDTH, CROP_HEIGHT = 512, 640
BLIND_SEED = 28620260904
EXPECTED_PLAYER_PRESENT = 79
VERDICTS = (
    "LOCATED_FEET",
    "LOCATED_BODY_NOT_FEET",
    "BARE_COURT_OR_FLOOR",
    "DIFFERENT_PERSON",
    "SOMETHING_ELSE",
    "CANNOT_JUDGE",
)
DIRECTIONS = ("ABOVE", "BELOW", "LEFT", "RIGHT")


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file without modifying it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def crop(image: np.ndarray, x: float, y: float) -> np.ndarray:
    """Return G273's 512x640 native-pixel crop centred on a footpoint."""
    left, top = round(x) - CROP_WIDTH // 2, round(y) - CROP_HEIGHT // 2
    padded = cv2.copyMakeBorder(image, CROP_HEIGHT, CROP_HEIGHT, CROP_WIDTH,
                                CROP_WIDTH, cv2.BORDER_CONSTANT)
    return padded[top + CROP_HEIGHT:top + 2 * CROP_HEIGHT,
                  left + CROP_WIDTH:left + 2 * CROP_WIDTH].copy()


def read_points(path: Path, locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read every finite G267 footpoint record for the 15 located frames."""
    frames = {int(row["source_frame"]) for row in locations}
    source = json.loads(path.read_text(encoding="ascii"))
    records = {int(row["source_frame"]): row for row in source["frame_records"]}
    rows: list[dict[str, Any]] = []
    for frame in sorted(frames):
        marker_index = 0
        for detection in records[frame]["detections"]:
            if detection["finite"]:
                rows.append({"source_frame": frame, "marker_index": marker_index,
                             "track_id": int(detection["track_id"]),
                             "foot_x_px": float(detection["foot_x_px"]),
                             "foot_y_px": float(detection["foot_y_px"])})
                marker_index += 1
    return rows


def inside_crop(point: dict[str, Any], location: dict[str, Any]) -> bool:
    """Test the G273 half-open 512x640 crop neighbourhood."""
    return (abs(point["foot_x_px"] - location["foot_x_px"]) <= CROP_WIDTH / 2
            and abs(point["foot_y_px"] - location["foot_y_px"]) <= CROP_HEIGHT / 2)


def direction(point: dict[str, Any], location: dict[str, Any]) -> str:
    """Describe footpoint direction from the located feet in image coordinates."""
    dx = point["foot_x_px"] - location["foot_x_px"]
    dy = point["foot_y_px"] - location["foot_y_px"]
    if abs(dy) >= abs(dx):
        return "BELOW" if dy > 0 else "ABOVE"
    return "RIGHT" if dx > 0 else "LEFT"


def select(locations: list[dict[str, Any]], points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair every footpoint with its nearest sealed located foot in its crop."""
    by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in locations:
        by_frame[int(row["source_frame"])].append(row)
    selected: list[dict[str, Any]] = []
    for point in points:
        candidates = [row for row in by_frame[point["source_frame"]] if inside_crop(point, row)]
        if candidates:
            located = min(candidates, key=lambda row: math.hypot(
                point["foot_x_px"] - row["foot_x_px"], point["foot_y_px"] - row["foot_y_px"]))
            selected.append({**point, "player_id": located["player_id"],
                             "located_foot_x_px": located["foot_x_px"],
                             "located_foot_y_px": located["foot_y_px"],
                             "offset_direction": direction(point, located)})
    if len(selected) != EXPECTED_PLAYER_PRESENT:
        raise RuntimeError("player-present selection is %d, expected %d" %
                           (len(selected), EXPECTED_PLAYER_PRESENT))
    return selected


def map_hash(rows: list[dict[str, Any]]) -> str:
    """Hash the identity-bearing mapping before any unblinding output exists."""
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def blind_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply the preregistered independent random presentation order."""
    indexes = list(range(len(rows)))
    random.Random(BLIND_SEED).shuffle(indexes)
    return [{**rows[original], "blind_index": index + 1}
            for index, original in enumerate(indexes)]


def render(frames: Path, rows: list[dict[str, Any]], output: Path) -> None:
    """Render the two-marker blind crops from the committed source JPEGs."""
    render_dir = output / "blind_renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    frame_files = {int(row["source_frame"]): row["frame_file"]
                   for row in csv.DictReader((output / "frame_files.csv").open(encoding="ascii"))}
    for row in rows:
        image = cv2.imread(str(frames / frame_files[row["source_frame"]]), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (1080, 1920):
            raise RuntimeError("missing or non-1920x1080 frame %s" % row["source_frame"])
        tile = crop(image, row["foot_x_px"], row["foot_y_px"])
        cx, cy = CROP_WIDTH // 2, CROP_HEIGHT // 2
        lx = round(row["located_foot_x_px"] - (round(row["foot_x_px"]) - cx))
        ly = round(row["located_foot_y_px"] - (round(row["foot_y_px"]) - cy))
        cv2.drawMarker(tile, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 21, 2, cv2.LINE_AA)
        cv2.circle(tile, (cx, cy), 8, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.drawMarker(tile, (lx, ly), (0, 255, 255), cv2.MARKER_DIAMOND, 17, 2, cv2.LINE_AA)
        cv2.circle(tile, (lx, ly), 6, (0, 255, 255), 1, cv2.LINE_AA)
        path = render_dir / ("blind_%03d.jpg" % row["blind_index"])
        if not cv2.imwrite(str(path), tile, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise RuntimeError("could not write " + str(path))


def review_boards(output: Path, count: int) -> None:
    """Make four-crop blind review boards without exposing source identities."""
    board_dir = output / "blind_review_boards"
    board_dir.mkdir(parents=True, exist_ok=True)
    for start in range(1, count + 1, 4):
        images = [cv2.imread(str(output / "blind_renders" / ("blind_%03d.jpg" % index)))
                  for index in range(start, min(start + 4, count + 1))]
        board = np.zeros((CROP_HEIGHT * 2, CROP_WIDTH * 2, 3), dtype=np.uint8)
        for offset, image in enumerate(images):
            row, col = divmod(offset, 2)
            board[row * CROP_HEIGHT:(row + 1) * CROP_HEIGHT,
                  col * CROP_WIDTH:(col + 1) * CROP_WIDTH] = image
        if not cv2.imwrite(str(board_dir / ("blind_%03d_%03d.jpg" %
                                             (start, start + len(images) - 1))), board,
                           [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise RuntimeError("could not write blind review board")


def prepare(args: argparse.Namespace) -> None:
    """Create blind-only material; do not emit source identity or summary counts."""
    locations = read_locations(args.located_feet)
    points = read_points(args.g267, locations)
    selected = blind_order(select(locations, points))
    args.output.mkdir(parents=True, exist_ok=True)
    frame_files = {row["source_frame"]: row["frame_file"] for row in locations}
    with (args.output / "frame_files.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=("source_frame", "frame_file"))
        writer.writeheader(); writer.writerows({"source_frame": key, "frame_file": value}
                                             for key, value in sorted(frame_files.items()))
    identity_rows = [{key: row[key] for key in ("blind_index", "source_frame", "marker_index", "track_id",
                     "foot_x_px", "foot_y_px", "player_id", "located_foot_x_px", "located_foot_y_px",
                     "offset_direction")} for row in selected]
    commitment = {"blind_seed": BLIND_SEED, "classified_detector_box_population": len(selected),
                  "unblind_map_sha256": map_hash(identity_rows),
                  "crop_policy": "512x640 native-pixel crop centred on the G267 footpoint, matching G273",
                  "marker_policy": "red cross plus red ring: detector footpoint at crop centre; yellow diamond plus ring: sealed located player feet",
                  "verdict_values": list(VERDICTS), "direction_values": list(DIRECTIONS)}
    (args.output / "blind_order_commitment.json").write_text(json.dumps(commitment, indent=2) + "\n", encoding="ascii")
    with (args.output / "blind_presentation_order.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=("blind_index", "render")); writer.writeheader()
        writer.writerows({"blind_index": row["blind_index"], "render": "blind_renders/blind_%03d.jpg" % row["blind_index"]} for row in selected)
    with (args.output / "blind_verdicts.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=("blind_index", "verdict", "free_text", "offset_direction")); writer.writeheader()
        writer.writerows({"blind_index": row["blind_index"], "verdict": "", "free_text": "", "offset_direction": row["offset_direction"]} for row in selected)
    render(args.frames, selected, args.output)
    review_boards(args.output, len(selected))


def unblind(args: argparse.Namespace) -> dict[str, Any]:
    """Verify the committed labels, expose identities, and write additive summary data."""
    locations = read_locations(args.located_feet)
    selected = blind_order(select(locations, read_points(args.g267, locations)))
    identity_rows = [{key: row[key] for key in ("blind_index", "source_frame", "marker_index", "track_id",
                     "foot_x_px", "foot_y_px", "player_id", "located_foot_x_px", "located_foot_y_px",
                     "offset_direction")} for row in selected]
    commitment = json.loads((args.output / "blind_order_commitment.json").read_text(encoding="ascii"))
    if map_hash(identity_rows) != commitment["unblind_map_sha256"]:
        raise RuntimeError("unblind map does not match committed blind order")
    with (args.output / "blind_verdicts.csv").open(newline="", encoding="ascii") as handle:
        labels = {int(row["blind_index"]): row for row in csv.DictReader(handle)}
    if set(labels) != set(range(1, len(selected) + 1)):
        raise RuntimeError("blind verdict ids are incomplete")
    for index, row in labels.items():
        if row["verdict"] not in VERDICTS or row["offset_direction"] not in DIRECTIONS:
            raise RuntimeError("invalid blind label at %d" % index)
        if row["verdict"] == "SOMETHING_ELSE" and not row["free_text"]:
            raise RuntimeError("SOMETHING_ELSE requires free text at %d" % index)
        if row["verdict"] != "SOMETHING_ELSE" and row["free_text"]:
            raise RuntimeError("free text only applies to SOMETHING_ELSE at %d" % index)
    rows = [{**row, **labels[row["blind_index"]]} for row in selected]
    raw_counts = Counter(row["verdict"] for row in rows)
    counts = {name: raw_counts[name] for name in VERDICTS}
    directions = Counter(row["offset_direction"] for row in rows)
    args.output.joinpath("unblind_map.json").write_text(json.dumps(identity_rows, indent=2) + "\n", encoding="ascii")
    with (args.output / "classified_rows.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    input_rows = []
    frame_names = {int(row["source_frame"]): row["frame_file"] for row in locations}
    for _, frame_name in sorted(frame_names.items()):
        frame = args.frames / frame_name
        input_rows.append({"input_kind": "frame", "absolute_path": str(frame.resolve()),
                           "bytes": frame.stat().st_size, "resolution_px": "1920x1080"})
    for kind, path, resolution in (("located_feet", args.located_feet, "csv"),
                                   ("g267_footpoints", args.g267, "json")):
        input_rows.append({"input_kind": kind, "absolute_path": str(path.resolve()),
                           "bytes": path.stat().st_size, "resolution_px": resolution})
    with (args.output / "input_manifest.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(input_rows[0])); writer.writeheader()
        writer.writerows(input_rows)
    summary = {"classified_detector_box_population": len(rows), "counts": counts,
               "fractions": {name: counts[name] / len(rows) for name in VERDICTS},
               "direction_counts": dict(directions),
               "direction_fractions": {name: directions[name] / len(rows) for name in DIRECTIONS},
               "recomputed_player_present": len(rows),
               "total_finite_detector_footpoints": len(read_points(args.g267, locations))}
    args.output.joinpath("measurement_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "unblind"))
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--located-feet", type=Path, required=True)
    parser.add_argument("--g267", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args); print("prepared blind G286 material")
    else:
        print(json.dumps(unblind(args), sort_keys=True))


if __name__ == "__main__":
    main()
