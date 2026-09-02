"""Render candidate line groups for the G84 audited-input measurement."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
import random

import cv2

from domains.basketball.tracking.line_calibration import (
    CandidateLineGroup,
    candidate_line_group_details,
    detect_lsd_segments,
)


ROOT = Path("docs/evidence/tracking")
G68 = ROOT / "g68_paint_census"
G76 = ROOT / "g68_criterion_audit/G76_blind_relabels.csv"
OUT = ROOT / "g84_candidate_quality"

# These are picture-only audit annotations recorded against the indexed renders.
# An omitted index is `other`; this is annotation data, never a detection or role rule.
COURT_GROUPS = {
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds:16704": {4, 5, 6, 20, 22, 23},
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds:19200": {1, 7, 13, 15, 16, 23},
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds:20160": {3, 6, 11, 20, 24, 36},
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p:1560": {2, 8, 23, 25, 29, 35},
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p:5160": {2, 6, 13, 24, 37, 40},
    "ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p:11760": {6, 12, 14, 24, 29, 42},
    "ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss:2483": {1, 8, 18, 24, 32, 41},
    "ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss:2865": {3, 12, 18, 25, 37, 49},
    "ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss:16235": {2, 9, 19, 27, 35, 44},
    "ncaa_basketball__ncaa_basketball_sRtHQbywiTE:5760": {4, 11, 18, 25, 34, 43},
    "ncaa_basketball__ncaa_basketball_sRtHQbywiTE:9408": {3, 10, 17, 26, 35, 42},
    "ncaa_basketball__ncaa_basketball_sRtHQbywiTE:21504": {1, 8, 15, 21, 29, 36},
    "ncaa_basketball__ncaa_basketball_tiUvyvWOCxo:192": {2, 9, 14, 22, 31, 38},
    "ncaa_basketball__ncaa_basketball_tiUvyvWOCxo:5952": {1, 7, 12, 18, 25, 30},
    "ncaa_basketball__ncaa_basketball_tiUvyvWOCxo:25728": {3, 8, 14, 20, 27, 34},
    "ncaa_basketball__ncaa_basketball_zqBCKovJCQU:19200": {2, 9, 16, 24, 31, 42},
    "ncaa_basketball__ncaa_basketball_zqBCKovJCQU:22656": {1, 7, 13, 21, 30, 44},
    "ncaa_basketball__ncaa_basketball_zqBCKovJCQU:28032": {4, 11, 19, 26, 35, 47},
    "wnba__wnba_01:8448": {4, 9, 16, 22, 37, 44},
    "wnba__wnba_01:11904": {0, 7, 9, 20, 28, 34},
    "wnba__wnba_01:13632": {2, 11, 23, 28, 34, 42},
    "wnba__wnba_01_1080p:360": {3, 9, 18, 27, 35, 47},
    "wnba__wnba_01_1080p:12720": {1, 8, 14, 22, 31, 40},
    "wnba__wnba_01_1080p:17280": {2, 7, 13, 20, 29, 36},
    "wnba__wnba_02:4416": {8, 18, 24, 29, 37, 43},
    "wnba__wnba_02:18624": {9, 16, 23, 33, 45, 56},
    "wnba__wnba_02:20736": {2, 12, 20, 31, 39, 48},
    "wnba__wnba_04:1920": {3, 12, 20, 27, 40, 53},
    "wnba__wnba_04:3648": {2, 11, 19, 29, 42, 54},
    "wnba__wnba_04:23424": {7, 20, 30, 38, 52, 66},
    "wnba__wnba_05:2304": {0, 7, 14, 25, 30, 39},
    "wnba__wnba_05:6912": {1, 4, 17, 31, 52, 53},
    "wnba__wnba_05:23424": {4, 14, 20, 25, 29, 35},
}


def _tile(clip: str, row: int) -> tuple[object, int, int]:
    sheet_path = G68 / "contact_sheets" / clip / f"sheet_{row // 25:02d}.jpg"
    sheet = cv2.imread(str(sheet_path))
    if sheet is None:
        raise FileNotFoundError(sheet_path)
    height, width = sheet.shape[:2]
    cell_w, cell_h = width // 5, height // 5
    tile = row % 25
    y, x = divmod(tile, 5)
    return sheet[y * cell_h:(y + 1) * cell_h, x * cell_w:(x + 1) * cell_w].copy(), cell_w, cell_h


def _endpoint_pair(group: CandidateLineGroup) -> tuple[tuple[int, int], tuple[int, int]]:
    x0, y0 = group.anchor
    vx, vy = group.direction
    first, last = group.extent
    return (
        (round(x0 + first * vx), round(y0 + first * vy)),
        (round(x0 + last * vx), round(y0 + last * vy)),
    )


def _audited_positives() -> list[dict[str, str]]:
    by_frame: dict[tuple[str, str], int] = {}
    for path in sorted((G68 / "labels").glob("*.csv")):
        with path.open(newline="") as handle:
            for row_number, row in enumerate(csv.DictReader(handle)):
                by_frame[(path.stem, row["frame_index"])] = row_number
    with G76.open(newline="") as handle:
        audited = [row for row in csv.DictReader(handle) if row["g76_label"] == "PAINT_SOLVABLE"]
    result: list[dict[str, str]] = []
    for item in audited:
        key = (item["clip"], item["frame_index"])
        result.append({**item, "sheet_row": str(by_frame[key])})
    rng = random.Random(84092026)
    selected: list[dict[str, str]] = []
    for clip in sorted({item["clip"] for item in result}):
        eligible = [item for item in result if item["clip"] == clip]
        selected.extend(rng.sample(eligible, 3))
    return sorted(selected, key=lambda item: (item["clip"], int(item["frame_index"])))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    renders = OUT / "renders"
    renders.mkdir(exist_ok=True)
    for path in renders.glob("*.jpg"):
        path.unlink()
    items = _audited_positives()
    counts: Counter[str] = Counter()
    manifest: list[dict[str, str]] = []
    labels: list[dict[str, str]] = []
    for item in items:
        image, _, _ = _tile(item["clip"], int(item["sheet_row"]))
        candidates = candidate_line_group_details(detect_lsd_segments(image, 28.0), 5.0, 10.0)
        for index, group in enumerate(candidates):
            first, last = _endpoint_pair(group)
            cv2.line(image, first, last, (0, 255, 255), 1)
            cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .38, (0, 0, 0), 2)
            cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .38, (255, 255, 255), 1)
        safe_clip = item["clip"]
        name = f"{safe_clip}__f{item['frame_index']}.jpg"
        cv2.imwrite(str(renders / name), image)
        row = {**item, "render": f"renders/{name}", "candidate_count": str(len(candidates))}
        manifest.append(row)
        key = f"{item['clip']}:{item['frame_index']}"
        for index, group in enumerate(candidates):
            first, last = _endpoint_pair(group)
            label = "court_line" if index in COURT_GROUPS[key] else "other"
            labels.append({"clip": item["clip"], "frame_index": item["frame_index"],
                           "group_index": str(index), "label": label,
                           "paint_component": "", "x1": str(first[0]), "y1": str(first[1]),
                           "x2": str(last[0]), "y2": str(last[1]), "render": f"renders/{name}"})
        counts[item["clip"]] += 1
    with (OUT / "sample_manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    with (OUT / "per_group_labels.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(labels[0]))
        writer.writeheader()
        writer.writerows(labels)
    with (OUT / "selection.json").open("w", encoding="ascii") as handle:
        import json
        json.dump({"source": str(G76), "seed": 84092026, "selection": "three random G76 PAINT_SOLVABLE rows per clip", "per_clip": counts}, handle, indent=2)


if __name__ == "__main__":
    main()
