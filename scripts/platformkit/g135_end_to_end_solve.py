"""Run G135's frozen all-four paint-line reachability check."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import COURT_LINE_SETS, solve_from_lines
from scripts.platformkit.g115_paint_line_recall import REBUILT_TILES, frame_key, valid_manifest
from scripts.platformkit.g134_grouping_stability import _groups, measure


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g135_solve"
ROLES = ("baseline", "free_throw", "lane_left", "lane_right")
ROLE_TO_COURT = {
    "baseline": "baseline",
    "free_throw": "free_throw",
    "lane_left": "lane_low",
    "lane_right": "lane_high",
}
ROLE_FIELDS = (
    "clip", "frame_index", "role", "visible", "stable_detected",
    "stable_group_indices", "qualifying_frame",
)
QUALIFYING_FIELDS = ("clip", "frame_index", "court_standard", "matched_roles", "solve_status")


def qualifying_frames(rows: Iterable[dict[str, str]]) -> list[tuple[str, str]]:
    """Return unique frames with one stable match for every declared paint role."""
    seen: set[tuple[str, str, str]] = set()
    matched: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        role = row["role"]
        key = (row["clip"], row["frame_index"], role)
        if role not in ROLES:
            raise ValueError(f"unexpected paint role: {role}")
        if key in seen:
            raise ValueError(f"duplicate role row: {key}")
        seen.add(key)
        if row["stable_detected"] == "true":
            matched.setdefault(key[:2], set()).add(role)
    return sorted(key for key, roles in matched.items() if roles == set(ROLES))


def court_standard(clip: str) -> str:
    """Map the declared frozen clip family to the existing line-set name."""
    if clip.startswith("ncaa_basketball__"):
        return "ncaa_legacy"
    if clip.startswith("wnba__"):
        return "nba_wnba"
    raise ValueError(f"no declared court standard for {clip}")


def _selected_group_index(row: dict[str, str]) -> int:
    indices = row["stable_group_indices"].split(";")
    if not indices or not indices[0]:
        raise ValueError("qualifying role lacks a stable candidate index")
    return int(indices[0])


def solve_frame(
    source: dict[str, str], role_rows: dict[str, dict[str, str]],
) -> np.ndarray | None:
    """Fit a declared four-line image-to-court H using the existing library."""
    image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
    if image is None:
        raise FileNotFoundError(source["tile_filename"])
    _, _, stable = _groups(image)
    standard = court_standard(source["clip"])
    image_lines = [stable[_selected_group_index(role_rows[role])].line for role in ROLES]
    court_lines = [np.asarray(COURT_LINE_SETS[standard][ROLE_TO_COURT[role]]) for role in ROLES]
    return solve_from_lines(court_lines, image_lines)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_artifacts() -> None:
    """Recompute G134-stable matches and write the G135 terminal evidence."""
    rows, _, _, _ = measure()
    qualifiers = qualifying_frames(rows)
    qualifier_set = set(qualifiers)
    expected = {(source["clip"], source["frame_index"]) for source in valid_manifest()}
    observed = {(row["clip"], row["frame_index"]) for row in rows}
    if observed != expected or len(rows) != len(expected) * len(ROLES):
        raise ValueError("G135 requires exactly four unique role rows for every frozen frame")

    OUT.mkdir(exist_ok=True)
    role_records = [
        {field: row.get(field, "") for field in ROLE_FIELDS[:-1]}
        | {"qualifying_frame": str((row["clip"], row["frame_index"]) in qualifier_set).lower()}
        for row in rows
    ]
    _write_csv(OUT / "frame_role_matches.csv", ROLE_FIELDS, role_records)

    source_by_key = {frame_key(source): source for source in valid_manifest()}
    solve_records: list[dict[str, str]] = []
    for clip, frame_index in qualifiers:
        frame_rows = {row["role"]: row for row in rows if (row["clip"], row["frame_index"]) == (clip, frame_index)}
        homography = solve_frame(source_by_key[f"{clip}:{frame_index}"], frame_rows)
        solve_records.append({
            "clip": clip,
            "frame_index": frame_index,
            "court_standard": court_standard(clip),
            "matched_roles": ";".join(ROLES),
            "solve_status": "converged_requires_external_validation" if homography is not None else "not_converged",
        })
    _write_csv(OUT / "qualifying_frames.csv", QUALIFYING_FIELDS, solve_records)
    summary = {
        "frozen_frames": len(expected),
        "unique_role_rows": len(rows),
        "stable_matched_roles": sum(row["stable_detected"] == "true" for row in rows),
        "all_four_qualifying_frames": len(qualifiers),
        "renders_written": 0,
        "external_distance_measurements": 0,
        "terminal_reason": "no_all_four_frame" if not qualifiers else "see_qualifying_frames",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    print(f"all_four_qualifying_frames={len(qualifiers)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write G135 evidence from frozen local tiles")
    arguments = parser.parse_args()
    if arguments.write:
        write_artifacts()
