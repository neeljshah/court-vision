"""Create G75 image-only role-assignment evidence from existing G68 sheets."""
from __future__ import annotations

import csv
from pathlib import Path

import cv2

from domains.basketball.tracking.line_calibration import (
    CandidateLineGroup,
    assign_paint_roles,
    candidate_line_group_details,
    detect_lsd_segments,
)


ROOT = Path("docs/evidence/tracking")
G68 = ROOT / "g68_paint_census"
OUT = ROOT / "g75_role_assignment"
HELD_OUT = {
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds",
    "ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss",
    "wnba__wnba_01", "wnba__wnba_02", "wnba__wnba_04", "wnba__wnba_05",
}
COLORS = {"baseline": (0, 0, 255), "free_throw": (0, 255, 0),
          "lane_low": (255, 0, 0), "lane_high": (0, 255, 255)}


def _league(clip: str) -> str:
    return "ncaa_legacy" if clip.startswith("ncaa_") else "nba_wnba"


def _tile(clip: str, row: int) -> tuple[int, int, int, int, object]:
    sheet = cv2.imread(str(G68 / "contact_sheets" / clip / f"sheet_{row // 25:02d}.jpg"))
    if sheet is None:
        raise FileNotFoundError(clip)
    height, width = sheet.shape[:2]
    cell_w, cell_h = width // 5, height // 5
    tile = row % 25
    y, x = divmod(tile, 5)
    return x * cell_w, y * cell_h, cell_w, cell_h, sheet


def _line_endpoints(group: CandidateLineGroup, width: int, height: int) -> tuple[tuple[int, int], tuple[int, int]]:
    x0, y0 = group.anchor
    vx, vy = group.direction
    first, last = group.extent
    return ((round(x0 + first * vx), round(y0 + first * vy)),
            (round(x0 + last * vx), round(y0 + last * vy)))


def _samples() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for label_path in sorted((G68 / "labels").glob("*.csv")):
        clip = label_path.stem
        if clip.endswith("_1080p"):
            continue
        with label_path.open(newline="") as handle:
            labels = list(csv.DictReader(handle))
        solvable = [(index, item) for index, item in enumerate(labels) if item["label"] == "PAINT_SOLVABLE"]
        for slot in range(5):
            row_index, item = solvable[round(slot * (len(solvable) - 1) / 4)]
            rows.append({"clip": clip, "frame_index": item["frame_index"],
                         "sheet_row": str(row_index), "league": _league(clip),
                         "split": "held_out" if clip in HELD_OUT else "tune"})
    return rows


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "candidate_previews").mkdir(exist_ok=True)
    (OUT / "renders").mkdir(exist_ok=True)
    for directory in (OUT / "candidate_previews", OUT / "renders"):
        for stale in directory.glob("*.jpg"):
            stale.unlink()
    manifest = _samples()
    with (OUT / "sample_manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest[0].keys())
        writer.writeheader()
        writer.writerows(manifest)
    assignments: list[dict[str, str]] = []
    for item in manifest:
        x, y, width, height, sheet = _tile(item["clip"], int(item["sheet_row"]))
        image = sheet[y:y + height, x:x + width].copy()
        candidates = candidate_line_group_details(detect_lsd_segments(image, 28.0), 5.0, 10.0)
        for index, group in enumerate(candidates):
            first, last = _line_endpoints(group, width, height)
            cv2.line(image, first, last, (255, 255, 255), 1)
            cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .35, (0, 0, 0), 2)
            cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .35, (255, 255, 255), 1)
        name = f"{item['clip']}__f{item['frame_index']}.jpg"
        cv2.imwrite(str(OUT / "candidate_previews" / name), image)
        roles = assign_paint_roles(candidates, item["league"], "left")
        row = dict(item)
        row.update({role: "" for role in COLORS})
        if roles is not None:
            ids = {id(group): index for index, group in enumerate(candidates)}
            for role, group in roles.items():
                row[role] = str(ids[id(group)])
        assignments.append(row)
        if item["split"] == "held_out":
            render = sheet[y:y + height, x:x + width].copy()
            if roles is not None:
                for role, group in roles.items():
                    first, last = _line_endpoints(group, width, height)
                    cv2.line(render, first, last, COLORS[role], 2)
                    cv2.putText(render, role, first, cv2.FONT_HERSHEY_SIMPLEX, .35, COLORS[role], 1)
            cv2.imwrite(str(OUT / "renders" / name), render)
    fields = list(manifest[0].keys()) + list(COLORS)
    with (OUT / "per_frame_assignments.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(assignments)


if __name__ == "__main__":
    main()
