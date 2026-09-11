"""G387 deterministic known-position band controls for the sealed native tiles."""
from __future__ import annotations

import math
import random
from pathlib import Path

from scripts.platformkit.tracking.g387_tiles import TILE_HEIGHT, TILE_OFFSETS, TILE_WIDTH

SEED = 387
LENGTH = 240.0
ANGLES = (0.0, 30.0, 60.0)


def known_points(opaque_ids: list[str]) -> list[dict[str, str]]:
    """Create one sealed control per opaque context with fixed endpoint ordering."""
    if len(opaque_ids) != 30 or len(set(opaque_ids)) != 30:
        raise ValueError("controls require exactly 30 unique opaque contexts")
    ordered = list(opaque_ids)
    random.Random(SEED).shuffle(ordered)
    rows = []
    for index, opaque_id in enumerate(ordered):
        tile_index = index % len(TILE_OFFSETS)
        offset_x, offset_y = TILE_OFFSETS[tile_index]
        angle = math.radians(ANGLES[index % len(ANGLES)])
        dx, dy = LENGTH * math.cos(angle) / 2, LENGTH * math.sin(angle) / 2
        cx, cy = offset_x + TILE_WIDTH / 2, offset_y + TILE_HEIGHT / 2
        rows.append({"opaque_id": opaque_id, "tile_index": str(tile_index + 1),
                     "x1": "%.3f" % (cx - dx), "y1": "%.3f" % (cy - dy),
                     "x2": "%.3f" % (cx + dx), "y2": "%.3f" % (cy + dy),
                     "mid_x": "%.3f" % cx, "mid_y": "%.3f" % cy,
                     "angle_degrees": "%.1f" % math.degrees(angle)})
    return rows


def inject(tile_path: Path, output_path: Path, point: dict[str, str]) -> None:
    """Draw the sealed black underlay and white band on one native-coordinate tile."""
    import cv2

    image = cv2.imread(str(tile_path), cv2.IMREAD_COLOR)
    if image is None or image.shape[:2] != (TILE_HEIGHT, TILE_WIDTH):
        raise ValueError("control background is not a fixed native tile")
    ox, oy = TILE_OFFSETS[int(point["tile_index"]) - 1]
    p1 = (round(float(point["x1"]) - ox), round(float(point["y1"]) - oy))
    p2 = (round(float(point["x2"]) - ox), round(float(point["y2"]) - oy))
    cv2.line(image, p1, p2, (0, 0, 0), 10, cv2.LINE_AA)
    cv2.line(image, p1, p2, (255, 255, 255), 6, cv2.LINE_AA)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image):
        raise RuntimeError("could not write control image")
