"""Recompute G230's descriptive tennis physical-plausibility audit."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EXPECTED_HASHES = {
    "tennis_ref01": "77accc8cd83dee040601605a19bd7db592a703b2dd2bdf066fb0f2a8245f567b",
    "tennis_01": "4e0def5dd2a53570d3aba4c5893f9761a8d695e62c16da5d0b60b12ab87c3929",
    "tennis_02": "a2f8147401f85044fa8d0a120d1bf316a497db959b845b520eaad5a58dc2d2cd",
}
COURT_LENGTH_FT, COURT_WIDTH_FT = 78.0, 36.0
SPRINT_REFERENCE_FTPS, GENEROUS_SPEED_REFERENCE_FTPS = 29.0, 58.0
RUNOFF_LENGTH_FT, RUNOFF_WIDTH_FT = 21.0, 12.0


def _quantile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    return {"n": len(values), "median": _quantile(values, 0.5), "p90": _quantile(values, 0.9),
            "p99": _quantile(values, 0.99), "max": max(values) if values else None}


def _outside_distance(x: float, y: float) -> float:
    return math.hypot(max(0.0, -x, x - COURT_LENGTH_FT), max(0.0, -y, y - COURT_WIDTH_FT))


def _beyond_runoff(x: float, y: float) -> bool:
    return x < -RUNOFF_LENGTH_FT or x > COURT_LENGTH_FT + RUNOFF_LENGTH_FT or y < -RUNOFF_WIDTH_FT or y > COURT_WIDTH_FT + RUNOFF_WIDTH_FT


def _load(path: Path) -> tuple[list[dict[str, str]], str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle)), digest


def _table_name(path: Path) -> str:
    stem = path.stem.replace("_tracking_data", "")
    return "tennis_ref01" if stem == "tennis_ref01" else stem


def analyze(path: Path) -> dict[str, Any]:
    rows, digest = _load(path)
    name = _table_name(path)
    if digest != EXPECTED_HASHES[name]:
        raise ValueError(f"SHA-256 mismatch for {path}: {digest}")
    spaces = sorted({row["coordinate_space"] for row in rows})
    if spaces != ["court_feet"]:
        raise ValueError(f"{path} does not exclusively declare court_feet: {spaces}")
    by_class = Counter(row["cls"] for row in rows)
    players = [row for row in rows if row["cls"] == "player"]
    fps_values = {float(row["source_fps"]) for row in players}
    if len(fps_values) != 1:
        raise ValueError(f"{path} has non-constant player source_fps")
    fps = fps_values.pop()
    track_rows: dict[int, list[dict[str, str]]] = defaultdict(list)
    frame_ids: dict[int, set[int]] = defaultdict(set)
    oob_distances: list[float] = []
    oob_boundary_rows = 0
    player_boundary_keys: set[tuple[int, int]] = set()
    for row in players:
        track_rows[int(row["track_id"])].append(row)
        frame_ids[int(row["frame"])].add(int(row["track_id"]))
        distance = _outside_distance(float(row["x"]), float(row["y"]))
        if distance:
            oob_distances.append(distance)
    for observations in track_rows.values():
        observations.sort(key=lambda row: int(row["frame"]))
        player_boundary_keys.add((int(observations[0]["track_id"]), int(observations[0]["frame"])))
        player_boundary_keys.add((int(observations[-1]["track_id"]), int(observations[-1]["frame"])))
    for row in players:
        if _outside_distance(float(row["x"]), float(row["y"])) and (int(row["track_id"]), int(row["frame"])) in player_boundary_keys:
            oob_boundary_rows += 1
    speeds: list[float] = []
    edge_speed_count = short_epoch_speed_count = 0
    speed_over_29 = speed_over_58 = edge_over_29 = short_epoch_over_29 = 0
    nonpositive_gap_count = 0
    actual_gaps: list[int] = []
    for observations in track_rows.values():
        for index, (prior, current) in enumerate(zip(observations, observations[1:]), start=1):
            frame_gap = int(current["frame"]) - int(prior["frame"])
            if frame_gap <= 0:
                nonpositive_gap_count += 1
                continue
            actual_gaps.append(frame_gap)
            speed = math.hypot(float(current["x"]) - float(prior["x"]), float(current["y"]) - float(prior["y"])) * fps / frame_gap
            speeds.append(speed)
            edge = index == 1 or index == len(observations) - 1
            short_epoch = len(observations) <= 2
            edge_speed_count += int(edge)
            short_epoch_speed_count += int(short_epoch)
            if speed > SPRINT_REFERENCE_FTPS:
                speed_over_29 += 1
                edge_over_29 += int(edge)
                short_epoch_over_29 += int(short_epoch)
            speed_over_58 += int(speed > GENEROUS_SPEED_REFERENCE_FTPS)
    frame_count_distribution = Counter(len(ids) for ids in frame_ids.values())
    oob_rows = len(oob_distances)
    runoff_excess = sum(_beyond_runoff(float(row["x"]), float(row["y"])) for row in players)
    return {
        "input": {"path": path.as_posix(), "bytes": path.stat().st_size, "sha256": digest, "rows": len(rows), "coordinate_space_values": spaces, "source_fps": fps},
        "class_rows": dict(sorted(by_class.items())), "eligible_player_rows": len(players),
        "out_of_bounds": {"rows": oob_rows, "fraction": oob_rows / len(players), "distance_ft": _distribution(oob_distances),
                          "beyond_21ft_length_or_12ft_width_runoff_rows": runoff_excess,
                          "boundary_row_cooccurrence": {"oob_rows_at_track_first_or_last_emission": oob_boundary_rows, "fraction": oob_boundary_rows / oob_rows if oob_rows else None}},
        "speed_ft_per_second": {"distribution": _distribution(speeds), "speed_pairs": len(speeds), "nonpositive_frame_gap_pairs_excluded": nonpositive_gap_count,
                                "actual_frame_gap_distribution": _distribution([float(gap) for gap in actual_gaps]),
                                "beyond_29ftps_reference": {"count": speed_over_29, "fraction": speed_over_29 / len(speeds) if speeds else None},
                                "beyond_58ftps_reference": {"count": speed_over_58, "fraction": speed_over_58 / len(speeds) if speeds else None}},
        "player_ids_per_emitted_player_frame": {"frames": len(frame_ids), "distribution": {str(count): frames for count, frames in sorted(frame_count_distribution.items())},
                                                   "more_than_two_frames": sum(frames for count, frames in frame_count_distribution.items() if count > 2)},
        "epoch_boundary_cooccurrence": {"definition": "A track boundary is its first or last emitted player row; a speed edge is the first or last consecutive within-track transition. CSV rows cannot measure the unobserved inter-ID reset interval.",
                                          "speed_pairs_at_track_edge": edge_speed_count, "speed_pairs_in_two_row_or_shorter_track": short_epoch_speed_count,
                                          "beyond_29ftps_at_track_edge": edge_over_29, "beyond_29ftps_in_two_row_or_shorter_track": short_epoch_over_29},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = {"method": {"court_plane_ft": [COURT_LENGTH_FT, COURT_WIDTH_FT], "speed": "distance * declared source_fps / actual consecutive within-track frame gap", "references_are_descriptive_not_gates": [SPRINT_REFERENCE_FTPS, GENEROUS_SPEED_REFERENCE_FTPS]},
              "tables": { _table_name(path): analyze(path) for path in args.inputs}}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
