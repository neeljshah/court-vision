"""G387 pixel-adjudication cards: paired traces plus nine audited positions.

One card per real context: the native context at half scale with both reported
traces, and three 4x zoom panels at the first, middle, and last audited position.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from scripts.platformkit.tracking import g387_tiles  # noqa: E402

OUT = REPO / "docs/evidence/tracking/g387_paint_localization_controls_2026-09-11"
CACHE = Path(r"C:\Users\neelj\AppData\Local\Temp\g387_native")
PANEL = 96
ZOOM = 4
TERRA_BGR = (0, 255, 255)
SOL_BGR = (255, 0, 255)


def audit_points(row: dict[str, str]) -> list[tuple[float, float]]:
    """Return the nine evenly spaced audited positions, endpoints included."""
    x1, y1, x2, y2 = (float(row["x"]), float(row["y"]), float(row["x2"]), float(row["y2"]))
    return [(x1 + (x2 - x1) * n / 8.0, y1 + (y2 - y1) * n / 8.0) for n in range(9)]


def _panel(image, point: tuple[float, float]):
    import cv2
    import numpy as np

    half = PANEL // 2
    cx, cy = int(round(point[0])), int(round(point[1]))
    canvas = np.zeros((PANEL, PANEL, 3), dtype=image.dtype)
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(image.shape[1], cx + half), min(image.shape[0], cy + half)
    if x1 > x0 and y1 > y0:
        canvas[y0 - (cy - half):y1 - (cy - half), x0 - (cx - half):x1 - (cx - half)] = image[y0:y1, x0:x1]
    return cv2.resize(canvas, (PANEL * ZOOM, PANEL * ZOOM), interpolation=cv2.INTER_NEAREST)


def build(opaque_ids: list[str]) -> None:
    import cv2
    import numpy as np

    terra = {}
    sol = {}
    for name, store in (("terra", terra), ("sol", sol)):
        for row in g387_tiles.read_csv(OUT / ("ratings_real_%s.csv" % name)):
            store.setdefault(row["opaque_id"], []).append(row)
    out_dir = OUT / "adjudication_cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    for opaque_id in opaque_ids:
        image = cv2.imread(str(CACHE / "tiles" / (opaque_id + "_context.png")), cv2.IMREAD_COLOR)
        overlay = image.copy()
        panels = []
        for rows, colour in ((terra.get(opaque_id, []), TERRA_BGR), (sol.get(opaque_id, []), SOL_BGR)):
            for row in rows:
                if row["state"] != "VISIBLE":
                    continue
                pts = audit_points(row)
                cv2.line(overlay, (int(pts[0][0]), int(pts[0][1])), (int(pts[8][0]), int(pts[8][1])), colour, 1)
                for point in pts:
                    cv2.circle(overlay, (int(round(point[0])), int(round(point[1]))), 3, colour, 1)
                panels.extend(_panel(image, pts[index]) for index in (0, 4, 8))
        card = cv2.resize(overlay, (960, 540), interpolation=cv2.INTER_AREA)
        if panels:
            strip = np.hstack(panels[:6])
            scale = card.shape[1] / strip.shape[1]
            strip = cv2.resize(strip, (card.shape[1], int(strip.shape[0] * scale)), interpolation=cv2.INTER_NEAREST)
            card = np.vstack([card, strip])
        cv2.imwrite(str(out_dir / (opaque_id + "_adj.jpg")), card, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    print("cards=%d" % len(opaque_ids))


if __name__ == "__main__":
    build(sys.argv[1:])
