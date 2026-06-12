"""kernel.config.speed — SpeedConfig: sport-agnostic movement-speed thresholds.

Replaces all hard-coded speed / fps literals that currently live in
``player_defensive_pressure.py``, ``space_control.py``, and similar modules.

SPEC reference: BUILD_BACKLOG P0-D-006 / KERNEL_ARCHITECTURE §2 & §5.

Adding a sport = supplying a ``SpeedConfig`` instance in
``domains/<sport>/config.py``.  The kernel never contains NBA literals — those
live in ``domains/nba/config.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class SpeedConfig:
    """Immutable movement-speed specification for any sport.

    All speed-threshold comparisons in ``kernel/spatial/`` and
    ``kernel/features/`` accept this object instead of hard-coded numeric
    literals, so the same kernel code works for any sport whose domain adapter
    supplies a matching ``SpeedConfig``.

    Parameters
    ----------
    video_fps:
        Native frame rate of the video source in frames per second.
        Used to convert real-world ft/s (or unit/s) thresholds to the
        per-frame distances needed by frame-differential tracker code.
        Common values: 24.0, 25.0, 29.97, 30.0, 60.0.
    thresholds_ft_s:
        Mapping of named movement-category labels to their minimum
        real-world threshold speeds in *feet per second* (or the
        surface unit shared with ``CourtConfig.unit`` when paired).
        The kernel treats this as an opaque lookup table — it never
        hard-codes key names.

        NBA canonical example::

            {
                "drive_min": 10.0,   # ft/s  player driving to the basket
                "cut_min":   14.0,   # ft/s  off-ball cut
            }

    screen_dist_ft:
        Maximum distance in feet (or surface unit) within which a
        stationary player is considered to be setting a screen.
        NBA: 6.0 ft.  Used by ``kernel/spatial/screen_detector.py``.
    """

    video_fps: float
    thresholds_ft_s: Dict[str, float] = field(default_factory=dict)
    screen_dist_ft: float = 0.0

    # ------------------------------------------------------------------
    # Per-frame conversion
    # ------------------------------------------------------------------

    def per_frame(self, threshold_ft_s: float) -> float:
        """Convert a real-world speed threshold to a per-frame distance.

        Frame-differential trackers compare pixel displacements between
        consecutive frames.  After homography the displacements are in
        feet (or the surface unit), so comparisons are made against this
        per-frame distance rather than a ft/s threshold.

        The formula is::

            ft_per_frame = threshold_ft_s / video_fps

        This is the exact inverse of the displacement→speed conversion:
        ``speed_ft_s = ft_per_frame * video_fps``.

        Parameters
        ----------
        threshold_ft_s:
            A speed threshold in feet per second (or the surface unit per
            second).  May be any positive float, including values not
            present in ``thresholds_ft_s`` — the method is a pure numeric
            conversion, not a lookup.

        Returns
        -------
        float
            Distance in feet (or surface unit) that corresponds to the
            threshold speed over exactly one frame at ``video_fps``.

        Raises
        ------
        ZeroDivisionError
            If ``video_fps`` is 0.  Callers should ensure a positive fps.

        Examples
        --------
        NBA drive threshold at 30 fps::

            SpeedConfig(video_fps=30.0, ...).per_frame(10.0)
            # → 10.0 / 30.0 = 0.3333… ft/frame
        """
        return threshold_ft_s / self.video_fps

    def per_frame_named(self, name: str) -> float:
        """Look up a named threshold from ``thresholds_ft_s`` and convert it.

        A convenience wrapper around :meth:`per_frame` for named entries.

        Parameters
        ----------
        name:
            Key in ``thresholds_ft_s``.

        Returns
        -------
        float
            ``per_frame(thresholds_ft_s[name])``.

        Raises
        ------
        KeyError
            If *name* is not present in ``thresholds_ft_s``.
        """
        return self.per_frame(self.thresholds_ft_s[name])
