"""G392 eye-check overlays: every control, every rater, in even archived order."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g392_prepare as prepare
from scripts.platformkit.tracking import g392_score as score

PER_SHEET = 6
SCALE = 1.0


def _draw(image, truth_row: dict[str, str], points, cv2):
    offset = (int(truth_row["offset_x"]), int(truth_row["offset_y"]))
    first = (int(round(float(truth_row["x1"]) - offset[0])), int(round(float(truth_row["y1"]) - offset[1])))
    second = (int(round(float(truth_row["x2"]) - offset[0])), int(round(float(truth_row["y2"]) - offset[1])))
    cv2.line(image, first, second, (0, 255, 0), 1, cv2.LINE_AA)
    for index, point in enumerate(points or []):
        local = (int(round(point[0] - offset[0])), int(round(point[1] - offset[1])))
        cv2.drawMarker(image, local, (0, 0, 255), cv2.MARKER_CROSS, 18, 1)
        cv2.putText(image, "p%d" % (index + 1), (local[0] + 6, local[1] - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1, cv2.LINE_AA)
    return image


def build(truth: Path, images: Path, out_root: Path, sheets: Path, control_set: str) -> dict[str, int]:
    """Render one card per control per rater and even six-up contact sheets."""
    import cv2
    import numpy as np

    rows = tiles.read_csv(truth)
    sheets.mkdir(parents=True, exist_ok=True)
    made = {}
    for rater in prepare.RATERS:
        directory = out_root / ("%s_%s" % (control_set, rater))
        cards = []
        for row in rows:
            image = cv2.imread(str(images / row["image"]), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("control image missing: %s" % row["image"])
            payload = score.read_response(directory, row["control_id"])
            points = None
            if payload is not None:
                points, _ok = score.native_points(
                    payload, (int(row["offset_x"]), int(row["offset_y"])))
            card = _draw(image.copy(), row, points, cv2)
            label = "%s %s %s" % (row["control_id"], rater, "ANSWERED" if points else "MISSING")
            cv2.putText(card, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 0), 1, cv2.LINE_AA)
            cards.append(card)
        for start in range(0, len(cards), PER_SHEET):
            chunk = cards[start:start + PER_SHEET]
            grid = np.vstack([np.hstack(chunk[index:index + 3]) for index in range(0, len(chunk), 3)])
            name = "%s_%s_sheet_%02d.jpg" % (control_set, rater, start // PER_SHEET + 1)
            cv2.imwrite(str(sheets / name), grid, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        made[rater] = len(cards)
    return made


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--sheets", type=Path, required=True)
    parser.add_argument("--set", dest="control_set", required=True)
    args = parser.parse_args()
    made = build(args.truth, args.images, args.out_root, args.sheets, args.control_set)
    print(json.dumps(made, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
