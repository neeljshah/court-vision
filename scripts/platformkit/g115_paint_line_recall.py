"""Run the frozen G93 paint-line recall protocol on G110-valid rebuilt tiles."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

from scripts.platformkit.g103_g68_tile_recipe import _read_manifest, rebuild
from scripts.platformkit.g93_line_detection_limit import (
    MISS_REASONS as MISS_REASONS_VOCABULARY,
    ROLE_COLOURS,
    ROLES,
    _matches,
    _segments_for,
    wilson_interval,
)


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g115_recall"
MARKS = OUT / "hand_marks.json"
MISS_REASON_FILE = OUT / "miss_reasons.json"
REBUILT_TILES = ROOT / "g103_recall/rebuilt_tiles"
EXCLUSIONS = {
    ("ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss", "2483"),
    ("ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss", "2865"),
    ("ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss", "16235"),
}


def frame_key(row: dict[str, str]) -> str:
    """Return the stable identity shared by all G84/G110/G115 artifacts."""
    return f"{row['clip']}:{row['frame_index']}"


def valid_manifest() -> list[dict[str, str]]:
    """Return the fixed 30-frame G110 same-picture subset, with no replacement."""
    all_rows = _read_manifest()
    identities = {(row["clip"], row["frame_index"]) for row in all_rows}
    if len(all_rows) != 33 or len(identities) != 33 or not EXCLUSIONS <= identities:
        raise ValueError("G115 requires the complete fixed G84 33-frame manifest")
    rows = [row for row in all_rows if (row["clip"], row["frame_index"]) not in EXCLUSIONS]
    if len(rows) != 30 or len({frame_key(row) for row in rows}) != 30:
        raise ValueError("G115 requires exactly 30 unique non-divergent frames")
    return rows


def _load_marks() -> dict[str, dict[str, dict[str, Any]]]:
    with MARKS.open(encoding="ascii") as handle:
        return json.load(handle)["frames"]


def _load_miss_reasons() -> dict[str, str]:
    with MISS_REASON_FILE.open(encoding="ascii") as handle:
        reasons = json.load(handle)["miss_reasons"]
    if not all(reason in MISS_REASONS_VOCABULARY for reason in reasons.values()):
        raise ValueError("G115 miss reason is outside G93's fixed vocabulary")
    return reasons


def _hand_segment(mark: dict[str, Any]) -> tuple[tuple[int, int], tuple[int, int]]:
    first, last = mark["endpoints"]
    return ((int(first[0]), int(first[1])), (int(last[0]), int(last[1])))


def rebuild_valid_tiles() -> None:
    """Pull only G115's 30 allowed tiles from the read-only pod source clips."""
    rebuilt = rebuild(valid_manifest())
    if len(rebuilt) != 30:
        raise ValueError("failed to rebuild all 30 G115 tiles")


def measure() -> tuple[list[dict[str, str]], Counter[str]]:
    """Score pre-recorded human marks under G93's frozen correspondence rule."""
    manifest = valid_manifest()
    marks = _load_marks()
    miss_reasons = _load_miss_reasons()
    expected = {frame_key(row) for row in manifest}
    if set(marks) != expected:
        raise ValueError("hand marks must name exactly the 30 valid G115 frames")
    rows: list[dict[str, str]] = []
    histogram: Counter[str] = Counter()
    expected_miss_keys: set[str] = set()
    for source in manifest:
        key = frame_key(source)
        image_path = REBUILT_TILES / source["tile_filename"]
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        candidates = _segments_for(image)
        frame_marks = marks[key]
        if set(frame_marks) != set(ROLES):
            raise ValueError(f"{key} must mark every frozen G93 role")
        for role in ROLES:
            mark = frame_marks[role]
            visible = bool(mark["visible"])
            row = {
                "clip": source["clip"], "frame_index": source["frame_index"],
                "role": role, "visible": str(visible).lower(), "detected": "",
                "matching_group_indices": "", "miss_reason": "", "endpoints": "",
            }
            if not visible:
                if "endpoints" in mark:
                    raise ValueError(f"non-visible {key} {role} has measurement-only data")
                rows.append(row)
                continue
            hand = _hand_segment(mark)
            matching = [index for index, segment in enumerate(candidates) if _matches(segment, hand)]
            detected = bool(matching)
            reason_key = f"{key}:{role}"
            reason = "" if detected else str(miss_reasons.get(reason_key, ""))
            if not detected and reason not in MISS_REASONS_VOCABULARY:
                raise ValueError(f"missed {key} {role} needs a fixed-vocabulary reason")
            if detected and reason_key in miss_reasons:
                raise ValueError(f"detected {key} {role} cannot have a miss reason")
            if reason:
                histogram[reason] += 1
                expected_miss_keys.add(reason_key)
            row.update({
                "detected": str(detected).lower(),
                "matching_group_indices": ";".join(map(str, matching)),
                "miss_reason": reason,
                "endpoints": json.dumps(mark["endpoints"], separators=(",", ":")),
            })
            rows.append(row)
    if set(miss_reasons) != expected_miss_keys:
        raise ValueError("miss reason file must name every and only missed visible line")
    return rows, histogram


def _render(source: dict[str, str], marks: dict[str, dict[str, Any]], rows: list[dict[str, str]]) -> None:
    image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
    if image is None:
        raise FileNotFoundError(source["tile_filename"])
    for index, (first, last) in enumerate(_segments_for(image)):
        cv2.line(image, first, last, (180, 180, 180), 1)
        cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (0, 0, 0), 2)
        cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (255, 255, 255), 1)
    scored = {row["role"]: row for row in rows if row["clip"] == source["clip"] and row["frame_index"] == source["frame_index"]}
    for position, role in enumerate(ROLES):
        mark, colour = marks[role], ROLE_COLOURS[role]
        if not mark["visible"]:
            text = f"{role}: not visible"
        else:
            first, last = _hand_segment(mark)
            cv2.line(image, first, last, colour, 2)
            score = scored[role]
            text = f"{role}: found" if score["detected"] == "true" else f"{role}: miss {score['miss_reason']}"
        cv2.putText(image, text, (8, 42 + 16 * position), cv2.FONT_HERSHEY_SIMPLEX, .42, colour, 1)
    destination = OUT / "renders" / source["tile_filename"]
    if not cv2.imwrite(str(destination), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise ValueError(destination)


def write_artifacts() -> None:
    """Write role-level recall evidence and all 30 judged overlays."""
    rows, histogram = measure()
    OUT.mkdir(exist_ok=True)
    renders = OUT / "renders"
    renders.mkdir(exist_ok=True)
    for path in renders.glob("*.jpg"):
        path.unlink()
    fields = list(rows[0])
    with (OUT / "line_measurements.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary: list[dict[str, str]] = []
    visible_rows = [row for row in rows if row["visible"] == "true"]
    for role in (*ROLES, "overall"):
        subset = visible_rows if role == "overall" else [row for row in visible_rows if row["role"] == role]
        found = sum(row["detected"] == "true" for row in subset)
        low, high = wilson_interval(found, len(subset))
        summary.append({"role": role, "detected": str(found), "visible": str(len(subset)),
                        "recall": f"{found / len(subset):.6f}" if subset else "",
                        "wilson_95_low": f"{low:.6f}" if subset else "",
                        "wilson_95_high": f"{high:.6f}" if subset else ""})
    with (OUT / "recall_summary.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    with (OUT / "miss_reason_histogram.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["miss_reason", "count"])
        writer.writeheader()
        for reason in sorted(MISS_REASONS_VOCABULARY):
            writer.writerow({"miss_reason": reason, "count": histogram[reason]})
    marks = _load_marks()
    for source in valid_manifest():
        _render(source, marks[frame_key(source)], rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="read-only pull of the 30 retained tiles")
    parser.add_argument("--write", action="store_true", help="write scored evidence from local rebuilt tiles")
    arguments = parser.parse_args()
    if arguments.rebuild:
        rebuild_valid_tiles()
        print("rebuilt_tiles=30")
    if arguments.write:
        write_artifacts()
        print("wrote_g115_artifacts")
