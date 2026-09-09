"""G362 synthetic court raster: the known-H fixture the recovery test runs on.

Nothing here touches broadcast footage. The raster is painted from the LANDED G334 template
(`g334_court_template.template_polylines`) under a matrix chosen once and fixed, so the recovery
test compares a fit against a truth that is known by construction rather than by a label.

The negative fixture is the honest counterpart: texture with no straight marking long enough to
form two orientation families, which is what a crowd or a title card looks like to the detector.
"""
from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.tracking.g334_court_template import (
    HALF_COURT_QUAD, project, template_polylines,
)

cv2.setNumThreads(1)

# The sealed fixture: a 1280x720 raster and one broadcast-like feet-to-image quad. The destination
# corners give about 18 px per foot across the baseline, inside the G334 scale gate's 4..60 band.
SYNTH_SHAPE = (720, 1280)
SYNTH_QUAD = np.array([(180.0, 690.0), (1100.0, 690.0), (960.0, 200.0), (320.0, 200.0)],
                      dtype=np.float32)
FLOOR_VALUE = 46
LINE_VALUE = 232


def known_matrix() -> np.ndarray:
    """The fixture's feet-to-image homography, normalised by its (2, 2) element."""
    matrix = cv2.getPerspectiveTransform(HALF_COURT_QUAD, SYNTH_QUAD)
    return matrix / matrix[2, 2]


def render_court(matrix: np.ndarray | None = None, shape=SYNTH_SHAPE) -> np.ndarray:
    """Paint the template polylines into a blank raster under `matrix`.

    Lines are one pixel wide and anti-aliased so the painted intensity centre sits on the geometric
    line rather than half a pixel off it; a thicker or aliased stroke would put a fixed sub-pixel
    bias between the painter and the detector and that bias would then be charged to the fitter.
    """
    matrix = known_matrix() if matrix is None else matrix
    image = np.full((shape[0], shape[1], 3), FLOOR_VALUE, dtype=np.uint8)
    for polyline in template_polylines():
        points = project(matrix, polyline)
        if not np.isfinite(points).all():
            continue
        scaled = np.round(points * 16.0).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(image, [scaled], False, (LINE_VALUE,) * 3, 1, cv2.LINE_AA, shift=4)
    return image


def render_crowd(shape=SYNTH_SHAPE) -> np.ndarray:
    """A no-marking fixture: deterministic blobs, no straight run long enough to be a stroke."""
    rng = np.random.default_rng(362)
    image = np.full((shape[0], shape[1], 3), 90, dtype=np.uint8)
    for _ in range(600):
        centre = (int(rng.integers(0, shape[1])), int(rng.integers(0, shape[0])))
        radius = int(rng.integers(3, 11))
        colour = tuple(int(v) for v in rng.integers(20, 220, size=3))
        cv2.circle(image, centre, radius, colour, -1, cv2.LINE_AA)
    return image


def reprojection_median(truth: np.ndarray, fitted: np.ndarray, points: np.ndarray) -> float:
    """Median pixel distance between the two matrices' images of `points`.

    This is the recovery-test quantity: it asks whether the fit puts the court where the truth put
    it, over the whole template, and it is scale-free in the sense that it never inspects residuals
    against the very lines the fit consumed (contract B8).
    """
    a, b = project(truth, points), project(fitted, points)
    finite = np.isfinite(a).all(axis=1) & np.isfinite(b).all(axis=1)
    if not finite.any():
        return float("inf")
    return float(np.median(np.linalg.norm(a[finite] - b[finite], axis=1)))


def demo() -> None:
    """Self-check: the fixture paints inside the frame and the crowd fixture paints no long line."""
    court = render_court()
    assert court.shape == (SYNTH_SHAPE[0], SYNTH_SHAPE[1], 3)
    assert int((court[:, :, 0] > FLOOR_VALUE + 40).sum()) > 2000, "court raster is blank"
    quad = project(known_matrix(), HALF_COURT_QUAD)
    assert quad[:, 0].min() >= 0.0 and quad[:, 0].max() <= SYNTH_SHAPE[1], "quad leaves the frame"
    assert reprojection_median(known_matrix(), known_matrix(), HALF_COURT_QUAD) == 0.0
    assert render_crowd().shape == court.shape
    print("g362_synth demo OK")


if __name__ == "__main__":
    demo()
