"""Diagnose directional structure in committed tennis court-feet tables."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


COURT_LENGTH_FT = 78.0
COURT_WIDTH_FT = 36.0
EXPECTED_COUNTS = {"tennis_ref01": 1861, "tennis_01": 19437, "tennis_02": 1637}
EXPECTED_HASHES = {
    "tennis_ref01": "77accc8cd83dee040601605a19bd7db592a703b2dd2bdf066fb0f2a8245f567b",
    "tennis_01": "4e0def5dd2a53570d3aba4c5893f9761a8d695e62c16da5d0b60b12ab87c3929",
    "tennis_02": "a2f8147401f85044fa8d0a120d1bf316a497db959b845b520eaad5a58dc2d2cd",
}
EDGE_NAMES = ("x_lt_0", "x_gt_78", "y_lt_0", "y_gt_36")


def _table_name(path: Path) -> str:
    return path.stem.replace("_tracking_data", "")


def _quantile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    return {
        "n": len(values),
        "min": min(values) if values else None,
        "p10": _quantile(values, 0.10),
        "median": _quantile(values, 0.50),
        "p90": _quantile(values, 0.90),
        "max": max(values) if values else None,
    }


def _edges(x: float, y: float) -> tuple[str, ...]:
    return tuple(
        name for name, exceeded in zip(
            EDGE_NAMES, (x < 0.0, x > COURT_LENGTH_FT, y < 0.0, y > COURT_WIDTH_FT)
        ) if exceeded
    )


def _fraction(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _breakdown(rows: list[dict[str, str]], fields: tuple[str, ...]) -> dict[str, dict[str, float | int]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = " | ".join(row[field] if row[field] else "(blank)" for field in fields)
        groups[key].append(row)
    return {
        key: {
            "eligible_player_rows": len(group),
            "out_of_bounds_rows": sum(bool(_edges(float(row["x"]), float(row["y"]))) for row in group),
            "out_of_bounds_fraction": _fraction(
                sum(bool(_edges(float(row["x"]), float(row["y"]))) for row in group), len(group)
            ),
        }
        for key, group in sorted(groups.items())
    }


def _scale_fit(rows: list[dict[str, str]]) -> dict[str, float | int | None]:
    """Minimize post-division OOB count; choose the smallest tied positive k."""
    ratios = [
        ratio
        for row in rows
        for value, bound in ((float(row["x"]), COURT_LENGTH_FT), (float(row["y"]), COURT_WIDTH_FT))
        if value > 0.0
        for ratio in (value / bound,)
    ]
    if not ratios:
        return {"best_k": None, "residual_out_of_bounds_rows": len(rows), "residual_out_of_bounds_fraction": 1.0}
    # Positive coordinates can only move inward as k increases; negative values
    # remain outside. Therefore the largest positive coordinate/boundary ratio is
    # the smallest positive k achieving the global minimum without a quadratic scan.
    best_k = max(ratios)
    minimum = sum(bool(_edges(float(row["x"]) / best_k, float(row["y"]) / best_k)) for row in rows)
    return {
        "best_k": best_k,
        "residual_out_of_bounds_rows": minimum,
        "residual_out_of_bounds_fraction": _fraction(minimum, len(rows)),
        "tie_break": "smallest positive coordinate/boundary ratio attaining the minimum",
    }


def _by_track(rows: list[dict[str, str]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["track_id"]].append(row)
    by_track = {
        track_id: {
            "eligible_player_rows": len(group),
            "out_of_bounds_rows": sum(bool(_edges(float(row["x"]), float(row["y"]))) for row in group),
            "out_of_bounds_fraction": _fraction(
                sum(bool(_edges(float(row["x"]), float(row["y"]))) for row in group), len(group)
            ),
        }
        for track_id, group in sorted(groups.items(), key=lambda item: int(item[0]))
    }
    fractions = [float(item["out_of_bounds_fraction"]) for item in by_track.values()]
    return {
        "summary": {
            "tracks": len(by_track),
            "fraction_distribution": _distribution(fractions),
            "clean_tracks": sum(value == 0.0 for value in fractions),
            "all_out_of_bounds_tracks": sum(value == 1.0 for value in fractions),
            "mixed_tracks": sum(0.0 < value < 1.0 for value in fractions),
        },
        "by_track_id": by_track,
    }


def _frame_deciles(by_frame: dict[int, dict[str, int]]) -> list[dict[str, float | int | None]]:
    frames = sorted(by_frame)
    if not frames:
        return []
    first, last = frames[0], frames[-1]
    width = (last - first + 1) / 10.0
    bins = [{"start_frame": math.floor(first + index * width), "end_frame": math.floor(first + (index + 1) * width) - 1,
             "eligible_player_rows": 0, "out_of_bounds_rows": 0} for index in range(10)]
    bins[-1]["end_frame"] = last
    for frame, value in by_frame.items():
        index = min(9, int((frame - first) / width))
        bins[index]["eligible_player_rows"] += value["eligible_player_rows"]
        bins[index]["out_of_bounds_rows"] += value["out_of_bounds_rows"]
    for value in bins:
        value["out_of_bounds_fraction"] = _fraction(value["out_of_bounds_rows"], value["eligible_player_rows"])
    return bins


def _by_frame(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[int, dict[str, int]] = defaultdict(lambda: {"eligible_player_rows": 0, "out_of_bounds_rows": 0})
    for row in rows:
        value = grouped[int(row["frame"])]
        value["eligible_player_rows"] += 1
        value["out_of_bounds_rows"] += int(bool(_edges(float(row["x"]), float(row["y"]))))
    fractions = [_fraction(value["out_of_bounds_rows"], value["eligible_player_rows"]) for value in grouped.values()]
    return {
        "summary": {
            "source_frame_count": len(grouped),
            "fraction_distribution": _distribution([float(value) for value in fractions if value is not None]),
            "clean_source_frames": sum(value == 0.0 for value in fractions),
            "all_out_of_bounds_source_frames": sum(value == 1.0 for value in fractions),
            "mixed_source_frames": sum(value is not None and 0.0 < value < 1.0 for value in fractions),
        },
        "ten_equal_source_frame_span_bins": _frame_deciles(grouped),
        "by_source_frame": {str(frame): value for frame, value in sorted(grouped.items())},
    }


def analyze(path: Path) -> dict[str, Any]:
    """Analyze one committed tracking CSV after enforcing its identity contract."""
    name = _table_name(path)
    if name not in EXPECTED_HASHES:
        raise ValueError(f"unknown G231 input: {path}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_HASHES[name]:
        raise ValueError(f"SHA-256 mismatch for {path}: {digest}")
    rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
    if len(rows) != EXPECTED_COUNTS[name]:
        raise ValueError(f"row count mismatch for {path}: {len(rows)}")
    spaces = sorted({row["coordinate_space"] for row in rows})
    if spaces != ["court_feet"]:
        raise ValueError(f"coordinate-space mismatch for {path}: {spaces}")
    players = [row for row in rows if row["cls"] == "player"]
    outside = [row for row in players if _edges(float(row["x"]), float(row["y"]))]
    joint = Counter(" + ".join(_edges(float(row["x"]), float(row["y"]))) for row in outside)
    edges = Counter(edge for row in outside for edge in _edges(float(row["x"]), float(row["y"])))
    return {
        "input": {
            "path": path.as_posix(), "bytes": len(raw), "sha256": digest, "rows": len(rows),
            "coordinate_space_values": spaces,
            "source_fps_values": sorted({row["source_fps"] for row in rows}),
            "source_height_values": sorted({row["source_height"] for row in rows}),
        },
        "class_rows": dict(sorted(Counter(row["cls"] for row in rows).items())),
        "eligible_denominator": {"definition": "rows where cls == player", "rows": len(players)},
        "out_of_bounds": {
            "rows": len(outside), "fraction": _fraction(len(outside), len(players)),
            "edge_marginals": {edge: edges[edge] for edge in EDGE_NAMES},
            "edge_joint_distribution": dict(sorted(joint.items())),
        },
        "scale_fit": _scale_fit(players),
        "per_track": _by_track(players),
        "per_source_frame": _by_frame(players),
        "by_calibration_provenance": _breakdown(players, ("calibration_provenance",)),
        "by_projection_status": _breakdown(players, ("projection_status",)),
        "by_calibration_provenance_and_projection_status": _breakdown(players, ("calibration_provenance", "projection_status")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = {
        "method": {
            "court_plane_ft": [COURT_LENGTH_FT, COURT_WIDTH_FT],
            "scale_fit": "divide both coordinates by positive k; minimize player out-of-bounds count; use the smallest tied boundary-ratio k. This monotone objective cannot move a negative coordinate inside, so its residual is descriptive, not independent validation.",
            "scope": "descriptive diagnosis only; no gate, threshold, or production change",
        },
        "tables": {_table_name(path): analyze(path) for path in args.inputs},
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
