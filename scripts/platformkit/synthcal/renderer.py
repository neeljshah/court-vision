"""Rule-geometry synthetic court renderer; it uses no external image assets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np


@dataclass(frozen=True)
class CourtSpec:
    name: str
    size: tuple[float, float]
    lines: tuple[tuple[tuple[float, float], tuple[float, float]], ...]
    points: dict[str, tuple[float, float]]


def _line(a: tuple[float, float], b: tuple[float, float]):
    return (a, b)


def _tennis() -> CourtSpec:
    p = {(f"corner_{x}_{y}"): (x, y) for x in (0., 78.) for y in (0., 36.)}
    p.update({f"singles_{x}_{y}": (x, y) for x in (0., 78.) for y in (4.5, 31.5)})
    p.update({f"service_{x}_{y}": (x, y) for x in (18., 60.) for y in (4.5, 31.5)})
    p.update({f"t_{x}": (x, 18.) for x in (18., 60.)})
    lines = [_line((0, 0), (78, 0)), _line((0, 36), (78, 36)),
             _line((0, 0), (0, 36)), _line((78, 0), (78, 36)),
             _line((0, 4.5), (78, 4.5)), _line((0, 31.5), (78, 31.5)),
             _line((18, 4.5), (18, 31.5)), _line((60, 4.5), (60, 31.5)),
             _line((18, 18), (60, 18))]
    return CourtSpec("tennis", (78., 36.), tuple(lines), p)


def _soccer() -> CourtSpec:
    p = {f"box_{x}_{y}": (x, y) for x in (0., 16.5, 88.5, 105.) for y in (13.84, 54.16)}
    p["centre"] = (52.5, 34.)
    lines = [_line((0, 0), (105, 0)), _line((0, 68), (105, 68)),
             _line((0, 0), (0, 68)), _line((105, 0), (105, 68)),
             _line((52.5, 0), (52.5, 68)), _line((0, 13.84), (16.5, 13.84)),
             _line((16.5, 13.84), (16.5, 54.16)), _line((16.5, 54.16), (0, 54.16)),
             _line((105, 13.84), (88.5, 13.84)), _line((88.5, 13.84), (88.5, 54.16)),
             _line((88.5, 54.16), (105, 54.16))]
    return CourtSpec("soccer", (105., 68.), tuple(lines), p)


def _basketball() -> CourtSpec:
    p = {f"lane_{x}_{y}": (x, y) for x in (0., 19., 75., 94.) for y in (17., 33.)}
    p["centre"] = (47., 25.)
    lines = [_line((0, 0), (94, 0)), _line((0, 50), (94, 50)),
             _line((0, 0), (0, 50)), _line((94, 0), (94, 50)),
             _line((47, 0), (47, 50)), _line((0, 17), (19, 17)),
             _line((19, 17), (19, 33)), _line((19, 33), (0, 33)),
             _line((94, 17), (75, 17)), _line((75, 17), (75, 33)),
             _line((75, 33), (94, 33))]
    return CourtSpec("basketball", (94., 50.), tuple(lines), p)


SPECS = {spec.name: spec for spec in (_tennis(), _soccer(), _basketball())}


def court_keypoints(sport: str) -> dict[str, tuple[float, float]]:
    """Return immutable named rule-geometry points in feet (tennis/basketball) or metres."""
    return dict(SPECS[sport].points)


def _template(spec: CourtSpec, scale: int = 10) -> tuple[np.ndarray, np.ndarray]:
    width, height = (int(spec.size[0] * scale), int(spec.size[1] * scale))
    image = np.full((height + 1, width + 1, 3), (42, 118, 54), np.uint8)
    for a, b in spec.lines:
        cv2.line(image, tuple(np.rint(np.multiply(a, scale)).astype(int)),
                 tuple(np.rint(np.multiply(b, scale)).astype(int)), (238, 238, 235), 2)
    source = np.float32(((0, 0), (width, 0), (width, height), (0, height)))
    return image, source


def _camera_quad(rng: np.random.Generator, sport: str, width: int, height: int) -> np.ndarray:
    if sport == "tennis":
        cx, cy, top, bottom = width * rng.uniform(.48, .52), height * rng.uniform(.38, .50), rng.uniform(.18, .40), rng.uniform(.72, 1.08)
        near, far = width * rng.uniform(.52, .82), width * rng.uniform(.18, .43)
    else:
        cx, cy, top, bottom = width * rng.uniform(.46, .54), height * rng.uniform(.34, .47), rng.uniform(.16, .32), rng.uniform(.77, 1.12)
        near, far = width * rng.uniform(.88, 1.25), width * rng.uniform(.60, .98)
    quad = np.float32(((cx - far / 2, cy - top * height / 2), (cx + far / 2, cy - top * height / 2),
                       (cx + near / 2, cy + bottom * height / 2), (cx - near / 2, cy + bottom * height / 2)))
    roll = rng.uniform(-.045, .045)
    rotation = np.array(((np.cos(roll), -np.sin(roll)), (np.sin(roll), np.cos(roll))))
    return ((quad - (cx, cy)) @ rotation.T + (cx, cy)).astype(np.float32)


def render_sample(sport: str, seed: int | None = None, shape: tuple[int, int] = (1280, 720)) -> dict[str, object]:
    """Render one augmentation and return BGR image, named pixels, and visibility."""
    rng, spec = np.random.default_rng(seed), SPECS[sport]
    width, height = shape
    template, source = _template(spec)
    destination = _camera_quad(rng, sport, width, height)
    homography = cv2.getPerspectiveTransform(source, destination)
    base = rng.normal(rng.uniform(35, 120), rng.uniform(8, 28), (height, width, 3)).clip(0, 255).astype(np.uint8)
    warped = cv2.warpPerspective(template, homography, (width, height), borderValue=(0, 0, 0))
    mask = cv2.warpPerspective(np.full(template.shape[:2], 255, np.uint8), homography, (width, height)) > 0
    base[mask] = warped[mask]
    for _ in range(int(rng.integers(3, 12))):
        x, y = int(rng.integers(0, width)), int(rng.integers(0, height))
        w, h = int(rng.integers(12, 75)), int(rng.integers(25, 150))
        cv2.rectangle(base, (x, y), (x + w, y + h), tuple(map(int, rng.integers(10, 100, 3))), -1)
    base = cv2.GaussianBlur(base, (0, 0), rng.uniform(.0, 1.8))
    base = cv2.convertScaleAbs(base, alpha=rng.uniform(.72, 1.30), beta=rng.uniform(-28, 28))
    quality = int(rng.integers(35, 96)); ok, encoded = cv2.imencode(".jpg", base, [cv2.IMWRITE_JPEG_QUALITY, quality])
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR) if ok else base
    metric = np.float32(list(spec.points.values())).reshape(1, -1, 2) * 10
    pixels = cv2.perspectiveTransform(metric, homography)[0]
    visible = ((pixels[:, 0] >= 0) & (pixels[:, 0] < width) & (pixels[:, 1] >= 0) & (pixels[:, 1] < height)).astype(np.uint8)
    return {"image": image, "points": pixels.astype(np.float32), "visible": visible,
            "names": tuple(spec.points), "homography": homography}
