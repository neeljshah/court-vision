"""Generate and fail-closed-score G119 direct local corner proposals."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import cv2


ROOT = Path("docs/evidence/tracking")
G111 = ROOT / "g111_basketball_reach"
OUT = ROOT / "g119_corners"
CANONICAL_WIDTH = 640
TITLE_BAND_PIXELS = 34
MATCH_TOLERANCE_PIXELS = 16.0
MAX_CORNERS = 180
QUALITY_LEVEL = 0.008
MIN_DISTANCE = 8.0
BLOCK_SIZE = 5
HARRIS_K = 0.04
VISIBLE_ROLES = (
    "paint_near_baseline_left_corner",
    "paint_near_baseline_right_corner",
    "paint_near_free_throw_left_corner",
    "paint_near_free_throw_right_corner",
)
RENDER_SLOTS = {2, 7, 12, 17}


def _visible_roles(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(role for role in row["point_features"].split(";") if role in VISIBLE_ROLES)


def _load_labels() -> list[dict[str, str]]:
    with (G111 / "frame_labels.csv").open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    keys = {(row["clip"], row["source_frame"], row["slot"]) for row in rows}
    if len(rows) != 220 or len(keys) != 220:
        raise ValueError("G111 must contain 220 unique frame labels")
    return rows


def _canonical_image(render: Path) -> Any:
    image = cv2.imread(str(render))
    if image is None:
        raise ValueError(f"missing G111 render: {render}")
    if image.shape[0] <= TITLE_BAND_PIXELS:
        raise ValueError(f"render too short for title crop: {render}")
    court = image[TITLE_BAND_PIXELS:, :]
    height = round(court.shape[0] * CANONICAL_WIDTH / court.shape[1])
    return cv2.resize(court, (CANONICAL_WIDTH, height), interpolation=cv2.INTER_AREA)


def _propose(image: Any) -> list[tuple[int, int]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    corners = cv2.goodFeaturesToTrack(
        gray,
        maxCorners=MAX_CORNERS,
        qualityLevel=QUALITY_LEVEL,
        minDistance=MIN_DISTANCE,
        blockSize=BLOCK_SIZE,
        useHarrisDetector=True,
        k=HARRIS_K,
    )
    if corners is None:
        return []
    return [(round(float(point[0][0])), round(float(point[0][1]))) for point in corners]


def _target_from_label(row: dict[str, str], role: str) -> tuple[float, float]:
    x_field, y_field = f"{role}_x", f"{role}_y"
    if not row.get(x_field) or not row.get(y_field):
        raise ValueError(f"G111 lacks committed coordinate for {role} on {row['clip']}:{row['source_frame']}")
    return float(row[x_field]), float(row[y_field])


def _matches(proposals: list[tuple[int, int]], target: tuple[float, float]) -> bool:
    return any(math.dist(proposal, target) <= MATCH_TOLERANCE_PIXELS for proposal in proposals)


def _score(labels: list[dict[str, str]], proposals: dict[tuple[str, str, str], list[tuple[int, int]]]) -> list[dict[str, str]]:
    """Score only coordinate-bearing committed labels; otherwise fail closed."""
    results: list[dict[str, str]] = []
    for row in labels:
        key = (row["clip"], row["source_frame"], row["slot"])
        for role in _visible_roles(row):
            target = _target_from_label(row, role)
            results.append({
                "clip": row["clip"], "source_frame": row["source_frame"], "slot": row["slot"],
                "role": role, "detected": str(_matches(proposals[key], target)).lower(),
            })
    return results


def _write_render(row: dict[str, str], proposals: list[tuple[int, int]]) -> str:
    image = _canonical_image(G111 / row["render"])
    for rank, (x, y) in enumerate(proposals[:30], start=1):
        cv2.drawMarker(image, (x, y), (255, 0, 255), cv2.MARKER_CROSS, 9, 1)
        cv2.putText(image, str(rank), (x + 3, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 0, 0), 2)
        cv2.putText(image, str(rank), (x + 3, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (255, 255, 255), 1)
    name = f"{row['clip']}__s{int(row['slot']):02d}__f{int(row['source_frame']):06d}.jpg"
    output = OUT / "renders" / name
    if not cv2.imwrite(str(output), image):
        raise ValueError(f"cannot write {output}")
    return f"renders/{name}"


def write_artifacts() -> None:
    """Write raw direct proposals and refuse an unsupported recall score."""
    labels = _load_labels()
    OUT.mkdir(exist_ok=True)
    render_dir = OUT / "renders"
    render_dir.mkdir(exist_ok=True)
    for path in render_dir.glob("*.jpg"):
        path.unlink()
    proposal_rows: list[dict[str, str]] = []
    proposals: dict[tuple[str, str, str], list[tuple[int, int]]] = {}
    for row in labels:
        key = (row["clip"], row["source_frame"], row["slot"])
        found = _propose(_canonical_image(G111 / row["render"]))
        proposals[key] = found
        for rank, (x, y) in enumerate(found, start=1):
            proposal_rows.append({
                "clip": row["clip"], "source_frame": row["source_frame"], "slot": row["slot"],
                "rank": str(rank), "x": str(x), "y": str(y), "source_render": row["render"],
            })
        if int(row["slot"]) in RENDER_SLOTS:
            _write_render(row, found)
    with (OUT / "proposals.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(proposal_rows[0]))
        writer.writeheader()
        writer.writerows(proposal_rows)
    visible_count = sum(len(_visible_roles(row)) for row in labels)
    coordinate_columns = sorted(
        field for field in labels[0] if field.endswith("_x") or field.endswith("_y")
    )
    validation = {
        "g111_label_rows": len(labels),
        "unique_frame_keys": len(proposals),
        "visible_corner_role_denominator": visible_count,
        "coordinate_columns_present": coordinate_columns,
        "localisation_tolerance_canonical_pixels": MATCH_TOLERANCE_PIXELS,
        "proposal_rows": len(proposal_rows),
        "render_count": len(list(render_dir.glob("*.jpg"))),
        "scoring_status": "NOT_VALIDATED",
        "reason": "G111 commits role visibility but no target pixel coordinates; recall would be circular.",
    }
    (OUT / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="ascii")
    try:
        _score(labels, proposals)
    except ValueError as error:
        (OUT / "score_blocker.txt").write_text(str(error) + "\n", encoding="ascii")
    else:
        raise ValueError("expected G111 coordinate contract failure did not occur")
    print(f"g119 proposals={len(proposal_rows)} visible_roles={visible_count} score=NOT_VALIDATED")


if __name__ == "__main__":
    write_artifacts()
