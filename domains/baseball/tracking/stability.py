"""Scale stabilization for calibrated baseball pitch-view tracking."""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from typing import Any


class ScaleStabilizer:
    """Smooth pitch-view calibration values without blending camera segments."""

    def __init__(self, alpha: float = 0.15) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha
        self.segment_id: object | None = None
        self.pixels_per_foot: float | None = None
        self.plate_centerline: float | None = None
        self._scale_history: deque[float] = deque(maxlen=10)

    def reset(self, segment_id: object) -> None:
        """Start a new pitch-view segment, discarding prior camera calibration."""
        if segment_id == self.segment_id:
            return
        self.segment_id = segment_id
        self.pixels_per_foot = None
        self.plate_centerline = None
        self._scale_history.clear()

    def update(self, pixels_per_foot: float, plate_centerline: float) -> tuple[float, float]:
        """Update and return the EMA-smoothed scale and plate centerline."""
        if pixels_per_foot <= 0.0:
            raise ValueError("pixels_per_foot must be positive")
        if self.pixels_per_foot is None:
            self.pixels_per_foot = float(pixels_per_foot)
            self.plate_centerline = float(plate_centerline)
        else:
            weight = self.alpha
            self.pixels_per_foot += weight * (float(pixels_per_foot) - self.pixels_per_foot)
            self.plate_centerline += weight * (float(plate_centerline) - self.plate_centerline)
        self._scale_history.append(self.pixels_per_foot)
        return self.pixels_per_foot, self.plate_centerline

    @property
    def is_stable(self) -> bool:
        """Whether the latest ten smoothed scales vary by less than five percent."""
        if len(self._scale_history) < self._scale_history.maxlen:
            return False
        mean_scale = sum(self._scale_history) / len(self._scale_history)
        return (max(self._scale_history) - min(self._scale_history)) / mean_scale < 0.05


def _row_key(row: Mapping[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        if name in row:
            return name
    raise ValueError("Row is missing one of: %s" % ", ".join(names))


def stabilize_rows(
    rows: Iterable[Mapping[str, Any]], stabilizer: ScaleStabilizer
) -> list[dict[str, Any]]:
    """Smooth calibration fields and retain only rows from stable pitch-view periods.

    Rows must provide scale and plate-centerline fields.  ``pixels_per_foot``
    (or ``px_per_foot``/``scale``) and ``plate_centerline`` (or ``plate_x``)
    are accepted to keep this utility independent of an adapter schema.
    """
    emitted: list[dict[str, Any]] = []
    for row in rows:
        scale_key = _row_key(row, ("pixels_per_foot", "px_per_foot", "scale"))
        center_key = _row_key(row, ("plate_centerline", "plate_x", "plate_center_x"))
        if "segment_id" in row:
            stabilizer.reset(row["segment_id"])
        scale, centerline = stabilizer.update(float(row[scale_key]), float(row[center_key]))
        if stabilizer.is_stable:
            stabilized = dict(row)
            stabilized[scale_key] = scale
            stabilized[center_key] = centerline
            emitted.append(stabilized)
    return emitted
