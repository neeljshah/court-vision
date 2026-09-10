"""Sealed court-symmetry arithmetic for G367."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.platformkit.tracking.g334_court_template import COURT_LENGTH_FT, COURT_WIDTH_FT, project


@dataclass(frozen=True)
class Element:
    """A named court-coordinate transform."""

    name: str
    matrix: np.ndarray


IDENTITY = Element("identity", np.eye(3, dtype=float))
MIRROR_X = Element("mirror_x", np.array([[-1.0, 0.0, COURT_WIDTH_FT],
                                           [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]))
ROT180 = Element("rot180", np.array([[-1.0, 0.0, COURT_WIDTH_FT],
                                      [0.0, -1.0, COURT_LENGTH_FT], [0.0, 0.0, 1.0]]))
MIRROR_Y = Element("mirror_y", np.array([[1.0, 0.0, 0.0],
                                           [0.0, -1.0, COURT_LENGTH_FT], [0.0, 0.0, 1.0]]))
GROUP = (IDENTITY, MIRROR_X, ROT180, MIRROR_Y)
NON_IDENTITY = GROUP[1:]


def normalise(matrix: np.ndarray) -> np.ndarray:
    """Return a finite homography in its canonical scale."""
    value = np.asarray(matrix, dtype=float)
    if value.shape != (3, 3) or not np.isfinite(value).all() or abs(value[2, 2]) < 1e-12:
        raise ValueError("invalid homography")
    return value / value[2, 2]


def compose(matrix: np.ndarray, element: Element) -> np.ndarray:
    """Apply a sealed court transform before the feet-to-image map."""
    return normalise(normalise(matrix) @ element.matrix)


def labelled_gap(truth: np.ndarray, candidate: np.ndarray, points: np.ndarray) -> float:
    """Median image-pixel separation over the supplied template points."""
    left, right = project(normalise(truth), points), project(normalise(candidate), points)
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        return float("inf")
    return float(np.median(np.linalg.norm(left - right, axis=1)))


def recovery_modulo_symmetry(truth: np.ndarray, candidate: np.ndarray, points: np.ndarray) -> dict:
    """Labelled and minimum group-composed gaps, retaining every element's value."""
    gaps = {item.name: labelled_gap(truth, compose(candidate, item), points) for item in GROUP}
    name = min(gaps, key=lambda key: (gaps[key], key))
    return {"labelled_gap_px": gaps["identity"], "modulo_gap_px": gaps[name],
            "attaining_element": name, "element_gaps_px": gaps}


def equivalent(first: np.ndarray, second: np.ndarray, points: np.ndarray, threshold_px: float) -> bool:
    """Whether two candidates differ only by a sealed transform within the fixed threshold."""
    return min(labelled_gap(compose(first, item), second, points) for item in GROUP) <= threshold_px
