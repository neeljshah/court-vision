"""Compute G285b footpoint recall from pre-committed human foot locations."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

RADII = (25.0, 50.0, 100.0)
PRIMARY_RADIUS = 50.0
Z_95 = 1.959963984540054


def on_court(detection: dict[str, Any]) -> bool:
    """Apply G270's unchanged inclusive footpoint rectangle."""
    return (bool(detection["finite"]) and 0.0 <= float(detection["court_x_ft"]) <= 50.0
            and 0.0 <= float(detection["court_y_ft"]) <= 94.0)


def wilson(successes: int, denominator: int) -> list[float]:
    """Return the two-sided 95 percent Wilson interval."""
    if denominator <= 0:
        raise ValueError("Wilson denominator must be positive")
    proportion = successes / denominator
    z2 = Z_95 * Z_95
    centre = (proportion + z2 / (2 * denominator)) / (1 + z2 / denominator)
    half = Z_95 * math.sqrt((proportion * (1 - proportion) + z2 / (4 * denominator)) / denominator)
    half /= 1 + z2 / denominator
    return [centre - half, centre + half]


def read_locations(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    seen = set()
    for row in rows:
        row["source_frame"] = int(row["source_frame"])
        row["foot_x_px"] = float(row["foot_x_px"])
        row["foot_y_px"] = float(row["foot_y_px"])
        key = (row["source_frame"], row["player_id"])
        if key in seen:
            raise ValueError("duplicate located player: %s" % (key,))
        seen.add(key)
        if not (0 <= row["foot_x_px"] < 1920 and 0 <= row["foot_y_px"] < 1080):
            raise ValueError("located foot outside 1920x1080: %s" % (key,))
    if not rows:
        raise ValueError("no located feet")
    return rows


def evenly_spaced_indices(count: int, take: int = 15) -> list[int]:
    """Return inclusive round-half-up indices across an ordered population."""
    if count < take:
        raise ValueError("population is smaller than requested sample")
    return [math.floor(i * (count - 1) / (take - 1) + 0.5) for i in range(take)]


def read_counted_frames(path: Path, location_frames: set[int]) -> dict[int, dict[str, str]]:
    with path.open(newline="", encoding="ascii") as handle:
        counted = [row for row in csv.DictReader(handle) if row["count_status"] == "COUNTED"]
    counted.sort(key=lambda row: int(row["source_frame"]))
    expected = {int(counted[index]["source_frame"]) for index in evenly_spaced_indices(len(counted))}
    if len(counted) != 54 or location_frames != expected:
        raise ValueError("located frames are not the predeclared 15-of-54 evenly spaced selection")
    return {int(row["source_frame"]): row for row in counted if int(row["source_frame"]) in location_frames}


def read_footpoints(path: Path, frames: set[int]) -> list[dict[str, Any]]:
    source = json.loads(path.read_text(encoding="ascii"))
    records = {int(row["source_frame"]): row for row in source["frame_records"]}
    points: list[dict[str, Any]] = []
    for source_frame in sorted(frames):
        if source_frame not in records:
            raise ValueError("missing G267 source frame: %s" % source_frame)
        marker_index = 0
        for detection in records[source_frame]["detections"]:
            if on_court(detection):
                points.append({"source_frame": source_frame, "marker_index": marker_index,
                               "track_id": int(detection["track_id"]),
                               "foot_x_px": float(detection["foot_x_px"]),
                               "foot_y_px": float(detection["foot_y_px"])})
                marker_index += 1
    return points


def minimum_distance(row: dict[str, Any], candidates: list[dict[str, Any]]) -> float:
    if not candidates:
        return math.inf
    return min(math.hypot(row["foot_x_px"] - candidate["foot_x_px"],
                          row["foot_y_px"] - candidate["foot_y_px"]) for candidate in candidates)


def match_frame(locations: list[dict[str, Any]], points: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    """Return each located-foot and footpoint nearest-neighbour distance in one frame."""
    return ([minimum_distance(row, points) for row in locations],
            [minimum_distance(row, locations) for row in points])


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> None:
    locations = read_locations(args.located_feet)
    by_frame_locations: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in locations:
        by_frame_locations[row["source_frame"]].append(row)
    frames = read_counted_frames(args.per_frame_join, set(by_frame_locations))
    points = read_footpoints(args.g267, set(frames))
    by_frame_points: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in points:
        by_frame_points[row["source_frame"]].append(row)

    player_rows: list[dict[str, Any]] = []
    point_rows: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []
    matched_players = {radius: 0 for radius in RADII}
    unmatched_points = {radius: 0 for radius in RADII}
    for source_frame in sorted(frames):
        located = by_frame_locations[source_frame]
        footpoints = by_frame_points[source_frame]
        player_distances, point_distances = match_frame(located, footpoints)
        for row, distance in zip(located, player_distances):
            output = dict(row, min_footpoint_distance_px=distance)
            for radius in RADII:
                matched = distance <= radius
                output["matched_at_%dpx" % radius] = matched
                matched_players[radius] += int(matched)
            player_rows.append(output)
        for row, distance in zip(footpoints, point_distances):
            output = dict(row, min_located_foot_distance_px=distance)
            for radius in RADII:
                unmatched = distance > radius
                output["unmatched_at_%dpx" % radius] = unmatched
                unmatched_points[radius] += int(unmatched)
            point_rows.append(output)
        output = {"source_frame": source_frame, "frame_file": frames[source_frame]["frame_file"],
                  "located_players": len(located),
                  "g284_sealed_visible_players": int(frames[source_frame]["players_visible_on_court"]),
                  "g270_on_court_footpoints": len(footpoints)}
        for radius in RADII:
            output["matched_players_at_%dpx" % radius] = sum(distance <= radius for distance in player_distances)
            output["unmatched_footpoints_at_%dpx" % radius] = sum(distance > radius for distance in point_distances)
        frame_rows.append(output)

    player_fields = ["source_frame", "frame_file", "player_id", "foot_x_px", "foot_y_px", "core_tile",
                     "min_footpoint_distance_px"] + ["matched_at_%dpx" % radius for radius in RADII]
    point_fields = ["source_frame", "marker_index", "track_id", "foot_x_px", "foot_y_px",
                    "min_located_foot_distance_px"] + ["unmatched_at_%dpx" % radius for radius in RADII]
    frame_fields = list(frame_rows[0])
    write_csv(args.player_output, player_fields, player_rows)
    write_csv(args.footpoint_output, point_fields, point_rows)
    write_csv(args.per_frame_output, frame_fields, frame_rows)
    summary = {"primary_radius_px": PRIMARY_RADIUS, "sensitivity_radii_px": list(RADII),
               "sampled_frames": len(frame_rows), "located_visible_players": len(player_rows),
               "g284_sealed_visible_players": sum(int(row["g284_sealed_visible_players"]) for row in frame_rows),
               "g270_on_court_footpoints": len(point_rows), "radii": {}}
    for radius in RADII:
        summary["radii"][str(int(radius))] = {
            "matched_located_players": matched_players[radius],
            "located_player_recall": matched_players[radius] / len(player_rows),
            "located_player_recall_wilson_95": wilson(matched_players[radius], len(player_rows)),
            "unmatched_footpoints": unmatched_points[radius],
            "unmatched_footpoint_rate": unmatched_points[radius] / len(point_rows),
        }
    args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--located-feet", type=Path, required=True)
    parser.add_argument("--per-frame-join", type=Path, required=True)
    parser.add_argument("--g267", type=Path, required=True)
    parser.add_argument("--player-output", type=Path, required=True)
    parser.add_argument("--footpoint-output", type=Path, required=True)
    parser.add_argument("--per-frame-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
