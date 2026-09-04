"""Join sealed G284 visible-person counts to frozen G267 detector-box records."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean, median
from typing import Any


COURT_X_MAX = 50.0
COURT_Y_MAX = 94.0
G273_PRECISION = 43 / 72


def sha256(path: Path) -> str:
    """Return a file SHA-256 without changing it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integer(value: str) -> int | None:
    """Parse a CSV integer field, preserving blank CANNOT_COUNT fields."""
    return None if value == "" else int(value)


def on_court(detection: dict[str, Any]) -> bool:
    """Apply G270's unchanged inclusive 50-by-94-foot court rectangle."""
    return (
        0.0 <= float(detection["court_x_ft"]) <= COURT_X_MAX
        and 0.0 <= float(detection["court_y_ft"]) <= COURT_Y_MAX
    )


def load_pass_counts(path: Path) -> list[dict[str, Any]]:
    """Load and validate the sealed Pass 1 blind count table."""
    with path.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 61:
        raise ValueError("Pass 1 must have 61 rows")
    parsed = []
    for row in rows:
        status = row["status"]
        players = integer(row["players_visible_on_court"])
        others = integer(row["other_people_on_court"])
        if status not in {"COUNTED", "CANNOT_COUNT"}:
            raise ValueError("invalid count status")
        if (status == "COUNTED") != (players is not None and others is not None):
            raise ValueError("COUNTED/CANNOT_COUNT numeric fields disagree")
        parsed.append({
            "blind_id": int(row["blind_id"]), "source_frame": int(row["source_frame"]),
            "frame_file": row["frame_file"], "count_status": status,
            "players_visible_on_court": players, "other_people_on_court": others,
        })
    if {row["blind_id"] for row in parsed} != set(range(61)):
        raise ValueError("Pass 1 blind IDs must be exactly 0..60")
    if len({row["source_frame"] for row in parsed}) != 61:
        raise ValueError("Pass 1 source frames must be unique")
    return sorted(parsed, key=lambda row: row["blind_id"])


def load_categories(path: Path) -> dict[int, str]:
    """Load G278's committed descriptive court-geometry category by blind ID."""
    with path.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    categories = {int(row["blind_id"]): row["category"] for row in rows}
    if set(categories) != set(range(61)) or len(rows) != 61:
        raise ValueError("G278 categories must cover each G284 blind ID once")
    return categories


def load_detection_counts(path: Path) -> dict[int, tuple[int, int]]:
    """Count finite and G270-on-court G267 detector-box observations by frame."""
    source = json.loads(path.read_text(encoding="ascii"))
    output: dict[int, tuple[int, int]] = {}
    total_finite = 0
    for frame in source["frame_records"]:
        source_frame = int(frame["source_frame"])
        detections = [row for row in frame["detections"] if row["finite"]]
        if source_frame in output:
            raise ValueError("duplicate G267 frame record")
        output[source_frame] = (len(detections), sum(on_court(row) for row in detections))
        total_finite += len(detections)
    expected = source["analysis"]["denominator"]["all_finite_detector_box_feet"]
    if total_finite != expected:
        raise ValueError("G267 finite detector-box denominator mismatch")
    return output


def quantile(values: list[float], proportion: float) -> float:
    """Return linearly interpolated quantile for a non-empty value sequence."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values: list[float]) -> dict[str, float | int]:
    """Summarize per-frame ratios without discarding their spread."""
    if not values:
        return {"n": 0}
    return {
        "n": len(values), "min": min(values), "q25": quantile(values, 0.25),
        "median": median(values), "mean": mean(values), "q75": quantile(values, 0.75), "max": max(values),
    }


def summarize(rows: list[dict[str, Any]], categories: dict[int, str]) -> dict[str, Any]:
    """Compute denominated aggregate, per-frame, category, and recount summaries."""
    counted = [row for row in rows if row["count_status"] == "COUNTED"]
    player_total = sum(row["players_visible_on_court"] for row in counted)
    other_total = sum(row["other_people_on_court"] for row in counted)
    finite_total = sum(row["finite_detection_count"] for row in counted)
    court_total = sum(row["on_court_detection_count"] for row in counted)
    per_player = [row["on_court_boxes_per_visible_player"] for row in counted]
    per_person = [row["on_court_boxes_per_visible_person"] for row in counted]
    category_summary: dict[str, dict[str, Any]] = {}
    for category in sorted(set(categories.values())):
        subset = [row for row in rows if categories[row["blind_id"]] == category]
        usable = [row for row in subset if row["count_status"] == "COUNTED"]
        players = sum(row["players_visible_on_court"] for row in usable)
        others = sum(row["other_people_on_court"] for row in usable)
        boxes = sum(row["on_court_detection_count"] for row in usable)
        category_summary[category] = {
            "all_sample_frames": len(subset), "counted_frames": len(usable),
            "cannot_count_frames": len(subset) - len(usable), "visible_players": players,
            "visible_other_people": others, "on_court_detector_boxes": boxes,
            "boxes_per_visible_player": boxes / players if players else None,
            "boxes_per_visible_person": boxes / (players + others) if players + others else None,
        }
    return {
        "sample": {"all_frames": len(rows), "counted_frames": len(counted), "cannot_count_frames": len(rows) - len(counted)},
        "detector_box_denominators": {
            "all_61_frames_finite_boxes": sum(row["finite_detection_count"] for row in rows),
            "all_61_frames_on_court_boxes": sum(row["on_court_detection_count"] for row in rows),
            "counted_frames_finite_boxes": finite_total, "counted_frames_on_court_boxes": court_total,
        },
        "visible_people_denominators": {"players": player_total, "other_people": other_total, "all_visible_people": player_total + other_total},
        "raw_box_to_visible_person_ratios": {
            "aggregate_boxes_per_visible_player": court_total / player_total,
            "aggregate_boxes_per_visible_person": court_total / (player_total + other_total),
            "per_frame_boxes_per_visible_player": distribution(per_player),
            "per_frame_boxes_per_visible_person": distribution(per_person),
        },
        "precision_adjusted_assumption": {
            "g273_sampled_detector_box_precision": G273_PRECISION,
            "expected_player_boxes": court_total * G273_PRECISION,
            "expected_player_boxes_per_visible_player": court_total * G273_PRECISION / player_total,
            "expected_player_boxes_per_visible_person": court_total * G273_PRECISION / (player_total + other_total),
        },
        "by_g278_geometry_category_descriptive_only": category_summary,
    }


def recount_agreement(pass_rows: list[dict[str, Any]], recount_path: Path) -> dict[str, Any]:
    """Compare the post-commit fresh recount to sealed Pass 1 values."""
    with recount_path.open(newline="", encoding="ascii") as handle:
        recount = list(csv.DictReader(handle))
    by_id = {row["blind_id"]: row for row in pass_rows}
    joined = []
    for row in recount:
        original = by_id[int(row["blind_id"])]
        status = row["status"]
        players, others = integer(row["players_visible_on_court"]), integer(row["other_people_on_court"])
        if (status == "COUNTED") != (players is not None and others is not None):
            raise ValueError("recount status/count mismatch")
        joined.append((original, status, players, others))
    numeric = [row for row in joined if row[0]["count_status"] == "COUNTED" and row[1] == "COUNTED"]

    def agreement(field: str, recount_index: int) -> dict[str, int]:
        differences = [abs(row[0][field] - row[recount_index]) for row in numeric]
        return {"n": len(differences), "exact": sum(value == 0 for value in differences), "within_one": sum(value <= 1 for value in differences)}

    combined = [(first["players_visible_on_court"] + first["other_people_on_court"], players + others)
                for first, status, players, others in joined if first["count_status"] == "COUNTED" and status == "COUNTED"]
    return {
        "recount_frames": len(joined), "countability_status_exact": sum(first["count_status"] == status for first, status, _, _ in joined),
        "player_count": agreement("players_visible_on_court", 2),
        "other_people_count": agreement("other_people_on_court", 3),
        "all_visible_people_count": {"n": len(combined), "exact": sum(left == right for left, right in combined), "within_one": sum(abs(left - right) <= 1 for left, right in combined)},
    }


def build(pass_path: Path, category_path: Path, g267_path: Path, recount_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join all committed sources and return the reproducible evidence tables."""
    pass_rows, categories, detections = load_pass_counts(pass_path), load_categories(category_path), load_detection_counts(g267_path)
    for row in pass_rows:
        finite, on_court_count = detections[row["source_frame"]]
        players, others = row["players_visible_on_court"], row["other_people_on_court"]
        people = None if players is None else players + others
        row.update({
            "g278_court_geometry_category": categories[row["blind_id"]], "finite_detection_count": finite,
            "on_court_detection_count": on_court_count, "visible_people_total": people,
            "on_court_boxes_per_visible_player": None if players is None else on_court_count / players,
            "on_court_boxes_per_visible_person": None if people is None else on_court_count / people,
        })
    summary = summarize(pass_rows, categories)
    summary["recount_agreement"] = recount_agreement(pass_rows, recount_path)
    summary["inputs"] = {str(path): {"bytes": path.stat().st_size, "sha256": sha256(path)} for path in (pass_path, category_path, g267_path, recount_path)}
    return pass_rows, summary


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Write the required machine-readable per-frame joined table."""
    fields = ["blind_id", "source_frame", "frame_file", "count_status", "g278_court_geometry_category", "players_visible_on_court", "other_people_on_court", "visible_people_total", "finite_detection_count", "on_court_detection_count", "on_court_boxes_per_visible_player", "on_court_boxes_per_visible_person"]
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass-counts", type=Path, required=True)
    parser.add_argument("--categories", type=Path, required=True)
    parser.add_argument("--g267", type=Path, required=True)
    parser.add_argument("--recount", type=Path, required=True)
    parser.add_argument("--per-frame-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    rows, summary = build(args.pass_counts, args.categories, args.g267, args.recount)
    write_csv(rows, args.per_frame_output)
    args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("Wrote %s and %s" % (args.per_frame_output, args.summary_output))


if __name__ == "__main__":
    main()
