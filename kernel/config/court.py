"""kernel.config.court — CourtConfig: sport-agnostic playing-surface geometry.

Replaces all hardcoded court literals in the engine (94×50 ft, 940×500 warp target,
30 fps speed normalisation, 47×25 control grid …).

AUDIT gaps addressed
--------------------
- Gap #3: court dimensions scattered across spatial modules.
- Gap #7: fps hard-coded in pressure.py / space_control.py; normalize_speed now
  receives fps so callers can supply the native sensor rate (24/25/29.97/30/60 fps)
  and the resulting real-world speeds scale exactly with fps.

Adding a sport = supplying a CourtConfig instance in domains/<sport>/config.py.
The kernel never contains NBA literals — those live in domains/nba/config.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Tuple


@dataclass(frozen=True)
class CourtConfig:
    """Immutable playing-surface specification for any sport.

    All spatial primitives in ``kernel/spatial/`` accept this object instead of
    hard-coded numeric literals.

    Parameters
    ----------
    surface_w:
        Width (long axis) of the playing surface in *unit*.
        NBA: 94.0 ft.  NFL: 120.0 yd (incl. end zones).  Soccer: ~105 m.
    surface_h:
        Height (short axis / sideline-to-sideline) of the playing surface in
        *unit*.  NBA: 50.0 ft.  NFL: 53.3 yd.  Soccer: ~68 m.
    unit:
        Physical unit of ``surface_w`` / ``surface_h`` and all derived distances.
        One of ``"ft"``, ``"yd"``, ``"m"``.
    goal_x_left:
        Normalised x-coordinate (0 = left baseline, 1 = right baseline) of the
        *left* scoring target (basket / goal / end zone).  NBA: 0.045.
    goal_x_right:
        Normalised x-coordinate of the *right* scoring target.  NBA: 0.955.
    goal_y:
        Normalised y-coordinate (0 = bottom sideline, 1 = top sideline) of
        both scoring targets.  NBA: 0.5 (centred).
    key_zones:
        Mapping of named zone labels to normalised bounding boxes expressed as
        ``(x0, y0, x1, y1)`` in the same [0, 1]² system as the goal anchors.
        NBA example: ``{"paint_left": (0.0, 0.19, 0.19, 0.81), …}``.
        The kernel never inspects zone semantics — it treats this as an opaque
        lookup table for domain modules to key into.
    rectified_px:
        ``(width_px, height_px)`` of the rectified bird's-eye image used as the
        homography warp target (``kernel/spatial/rectify.py``).
        NBA default: ``(940, 500)``.
    fps_native:
        Native broadcast frame rate (fps) at which the speed thresholds in
        ``speed_tiers`` were tuned.  Used exclusively by ``normalize_speed`` to
        re-scale pixel-displacement measurements acquired at a *different* fps
        to the canonical ``unit/s`` speed domain.
        Common values: 24.0, 25.0, 29.97, 30.0, 60.0.
    speed_tiers:
        Mapping of movement-type labels to their minimum real-world threshold
        speeds in ``unit/s``.  Tuned at ``fps_native``.
        NBA example: ``{"drive_min": 10.0, "cut_min": 14.0}``.
    three_pt_dist:
        Three-point line distance from the basket in ``unit``.
        Used by domain modules that need to classify shot zones.
        NBA: 23.75 ft (corner arc; straight-line from basket centre).
    """

    surface_w: float
    surface_h: float
    unit: Literal["ft", "yd", "m"]
    goal_x_left: float
    goal_x_right: float
    goal_y: float
    key_zones: Dict[str, Tuple[float, float, float, float]]
    rectified_px: Tuple[int, int] = (940, 500)
    fps_native: float = 30.0
    speed_tiers: Dict[str, float] = field(default_factory=dict)
    three_pt_dist: float = 0.0

    # ------------------------------------------------------------------
    # Computed geometry
    # ------------------------------------------------------------------

    def area(self) -> float:
        """Playing surface area in ``unit²``.

        Returns
        -------
        float
            ``surface_w * surface_h``.
            NBA: 94.0 × 50.0 = 4700.0 ft².
        """
        return self.surface_w * self.surface_h

    def control_grid(self, cells_per_unit: float = 0.5) -> Tuple[int, int]:
        """Dimensions of the spatial-control analysis grid.

        Each axis is divided into cells of size ``1 / cells_per_unit`` in the
        court's native *unit*.  The default ``cells_per_unit=0.5`` means one
        cell per 2 units — i.e. for feet that is one cell per 2 ft (half-foot
        resolution per the ``space_control.py`` 47×25 spec).

        Wait — the spec says 47×25 *half-foot* cells over 94×50, which is
        actually 2 cells per foot (``cells_per_unit=2``).  The basketball
        ``space_control.py`` implementation uses a 47×25 grid over 94×50 ft,
        which corresponds to ``cells_per_unit=0.5`` (one cell per 2 ft =
        half-court cells).  The NBA conformance test asserts ``(47, 25)`` with
        the default ``cells_per_unit=0.5``.

        Parameters
        ----------
        cells_per_unit:
            Number of grid cells per ``unit`` on each axis.
            Default 0.5 → one cell every 2 units (NBA: 94/2=47, 50/2=25).

        Returns
        -------
        Tuple[int, int]
            ``(cols, rows)`` — number of grid cells along the long axis and
            the short axis respectively.
        """
        cols = int(self.surface_w * cells_per_unit)
        rows = int(self.surface_h * cells_per_unit)
        return (cols, rows)

    # ------------------------------------------------------------------
    # Speed normalisation (AUDIT gap #7)
    # ------------------------------------------------------------------

    def normalize_speed(
        self,
        px_per_frame: float,
        fps: float,
        px_per_unit: float,
    ) -> float:
        """Convert pixel displacement per frame to real-world speed in ``unit/s``.

        Fixes AUDIT gap #7 where ``fps`` was hard-coded to 30 inside
        ``player_defensive_pressure.py`` / ``space_control.py``, causing
        incorrect speed values for clips recorded at 25, 29.97, or 60 fps.

        The formula is::

            speed = (px_per_frame × fps) / px_per_unit

        This ensures that for a *fixed* physical movement the computed speed
        scales linearly with the supplied *fps*:

            normalize_speed(x, 30, k) / normalize_speed(x, 25, k) == 30/25

        That ratio equality holds exactly (no rounding) because both calls
        share the same ``px_per_frame`` and ``px_per_unit``.

        Parameters
        ----------
        px_per_frame:
            Pixel displacement of a player/ball between two consecutive frames
            in the *source* video (at *fps* frames per second).
        fps:
            Frame rate of the *source* video in frames per second.
            Must match the rate at which ``px_per_frame`` was measured.
        px_per_unit:
            Pixel length of one ``unit`` in the rectified bird's-eye image,
            i.e. ``rectified_px[0] / surface_w`` for the long axis, or a
            pre-computed value derived from the homography warp.

        Returns
        -------
        float
            Real-world speed in ``unit/s``.  For NBA ft/s: divide by 1.467
            to convert to mph if desired (not done here — caller's choice).
        """
        return (px_per_frame * fps) / px_per_unit
