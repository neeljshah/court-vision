"""Exact coordinate transforms reserved for the future G409 observer replay."""
from __future__ import annotations

from fractions import Fraction
from typing import Iterable

Box = tuple[Fraction, Fraction, Fraction, Fraction]


def as_fraction_box(values: Iterable[int | float | Fraction]) -> Box:
    """Convert an xyxy box to exact rational components."""
    box = tuple(Fraction(value) for value in values)
    if len(box) != 4:
        raise ValueError("bbox-must-have-four-components")
    return box  # type: ignore[return-value]


def crop_xyxy(box: Box, origin_x: int, origin_y: int) -> Box:
    """Map native xyxy coordinates into a crop without fitting an offset."""
    x1, y1, x2, y2 = box
    return x1 - origin_x, y1 - origin_y, x2 - origin_x, y2 - origin_y


def uncrop_xyxy(box: Box, origin_x: int, origin_y: int) -> Box:
    """Map crop xyxy coordinates back into the native coordinate system."""
    x1, y1, x2, y2 = box
    return x1 + origin_x, y1 + origin_y, x2 + origin_x, y2 + origin_y


def xyxy_to_yxyx(box: Box) -> Box:
    """Convert the explicit xyxy tuple order to yxyx."""
    x1, y1, x2, y2 = box
    return y1, x1, y2, x2


def yxyx_to_xyxy(box: Box) -> Box:
    """Convert the explicit yxyx tuple order to xyxy."""
    y1, x1, y2, x2 = box
    return x1, y1, x2, y2


def resize_and_pad_xyxy(
    box: Box, scale: Fraction, pad_x: Fraction, pad_y: Fraction
) -> Box:
    """Apply an executed scale and padding transform with rational arithmetic."""
    if scale <= 0:
        raise ValueError("nonpositive-scale")
    x1, y1, x2, y2 = box
    return x1 * scale + pad_x, y1 * scale + pad_y, x2 * scale + pad_x, y2 * scale + pad_y
