"""
possession_classifier.py — Per-possession type and metric tracker.

Classifies each possession into one of seven types using court geometry,
player velocities, and spatial relationships — no ML required.

Possession types
----------------
    fast_break   — attackers outnumber defenders in frontcourt
    transition   — defender(s) not yet back in their own half
    double_team  — 2+ defenders within ~4 ft of ball handler
    drive        — ball handler moving fast toward basket
    paint_touch  — ball in the paint lane
    post_up      — ball handler slow, near the block
    half_court   — default

Also computes per-possession accumulation metrics:
    possession_duration_sec, shot_clock_est, paint_touches, off_ball_distance

Public API
----------
    PossessionClassifier(fps=30, map_w=940, map_h=500)
    .update(players, ball_pos, frame_num) -> dict

Player dict keys expected: player_id, x, y, speed, team, has_ball
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

# ── Court geometry thresholds (normalised 0-1 × map_w/map_h) ─────────────────
_PAINT_XN        = 0.15    # xn < this (or > 1 - this) = near baseline
_PAINT_YN_LO     = 0.28    # lane lower bound (normalised y)
_PAINT_YN_HI     = 0.72    # lane upper bound (normalised y)
_BLOCK_XN        = 0.08    # xn this close to baseline = post/block area
_DRIVE_VEL_PX    = 3.5     # px/frame toward basket = drive  (matches pipeline constant)
_POST_VEL_MAX    = 2.0     # px/frame max to classify as post-up (backing down slowly)
_DBL_TEAM_RAD_N  = 0.044   # normalised radius (~4 ft at 940-px map) = double-team
_FAST_BRK_ADV    = 1       # attacker surplus in frontcourt to call fast break

SHOT_CLOCK_MAX   = 24.0    # seconds


class PossessionClassifier:
    """
    Stateful per-possession type and metric classifier.

    Call .update() once per tracked frame.  State resets automatically when
    the possessing team changes.

    Args:
        fps:   Video frame rate (default 30).
        map_w: 2D court map width  in pixels (default 940).
        map_h: 2D court map height in pixels (default 500).
    """

    def __init__(
        self,
        fps: float = 30.0,
        map_w: int = 940,
        map_h: int = 500,
    ) -> None:
        self.fps   = fps
        self.map_w = map_w
        self.map_h = map_h

        self._poss_start:  Optional[int] = None
        self._poss_team:   Optional[str] = None
        self._paint_n:     int           = 0
        self._in_paint:    bool          = False
        self._off_dist:    float         = 0.0
        self._prev_offball: Dict[int, Tuple[float, float]] = {}

    # ── public ────────────────────────────────────────────────────────────

    def update(
        self,
        players: List[Dict],
        ball_pos: Optional[Tuple[float, float]],
        frame_num: int,
    ) -> Dict:
        """
        Classify possession for this frame and return metrics.

        Args:
            players:   List of dicts with keys:
                       player_id (int), x (float), y (float),
                       speed (float, px/frame), team (str), has_ball (bool).
            ball_pos:  (x, y) ball position in 2D court coords, or None.
            frame_num: Current frame index.

        Returns:
            Dict with keys: possession_type (str), possession_duration_sec (float),
            shot_clock_est (float), paint_touches (int), off_ball_distance (float).
        """
        handler   = next((p for p in players if p.get("has_ball")), None)
        curr_team = handler["team"] if handler else None

        # Reset accumulators when possession changes
        if curr_team != self._poss_team:
            self._poss_start     = frame_num
            self._poss_team      = curr_team
            self._paint_n        = 0
            self._in_paint       = False
            self._off_dist       = 0.0
            self._prev_offball   = {}

        if self._poss_start is None:
            self._poss_start = frame_num

        dur_frames = max(0, frame_num - self._poss_start)
        dur_sec    = round(dur_frames / self.fps, 2)

        # ── Paint touch tracking ──────────────────────────────────────────
        if ball_pos and self._in_paint_zone(ball_pos):
            if not self._in_paint:
                self._paint_n  += 1
                self._in_paint  = True
        else:
            self._in_paint = False

        # ── Off-ball distance accumulation ────────────────────────────────
        if curr_team and handler:
            off_ball = [p for p in players
                        if p["team"] == curr_team and not p.get("has_ball")]
            for p in off_ball:
                pid  = p["player_id"]
                prev = self._prev_offball.get(pid)
                if prev:
                    self._off_dist += float(np.hypot(
                        p["x"] - prev[0], p["y"] - prev[1]
                    ))
                self._prev_offball[pid] = (float(p["x"]), float(p["y"]))

        poss_type = self._classify(players, ball_pos, handler)
        sc_est    = max(0.0, SHOT_CLOCK_MAX - dur_sec)

        return {
            "possession_type":        poss_type,
            "possession_duration_sec": dur_sec,
            "shot_clock_est":         round(sc_est, 1),
            "paint_touches":          self._paint_n,
            "off_ball_distance":      round(self._off_dist, 1),
        }

    # ── internal helpers ──────────────────────────────────────────────────

    def _norm(self, x: float, y: float) -> Tuple[float, float]:
        """Normalise (x, y) to [0, 1] range."""
        return x / max(self.map_w, 1), y / max(self.map_h, 1)

    def _in_paint_zone(self, pos: Tuple[float, float]) -> bool:
        """Return True if position is inside the paint lane on either side."""
        xn, yn = self._norm(*pos)
        return (
            (xn < _PAINT_XN or xn > 1.0 - _PAINT_XN)
            and _PAINT_YN_LO < yn < _PAINT_YN_HI
        )

    def _classify(
        self,
        players: List[Dict],
        ball_pos: Optional[Tuple[float, float]],
        handler: Optional[Dict],
    ) -> str:
        """Return possession-type string for this frame."""
        if ball_pos is None or not players:
            return "half_court"

        off_team = handler["team"] if handler else None
        offense  = [p for p in players if p["team"] == off_team]
        defense  = [p for p in players
                    if p["team"] not in (off_team, "referee")]

        # ── Fast break: attackers outnumber defenders in frontcourt ───────
        if handler:
            hxn, _ = self._norm(handler["x"], handler["y"])
            # "Frontcourt" = same half as the ball handler
            radius = 0.40   # within 40% of map_w of handler
            att_n  = sum(1 for p in offense
                         if abs(self._norm(p["x"], p["y"])[0] - hxn) < radius)
            def_n  = sum(1 for p in defense
                         if abs(self._norm(p["x"], p["y"])[0] - hxn) < radius)
            if att_n > def_n + _FAST_BRK_ADV:
                return "fast_break"

        # ── Transition: defender still on wrong side of half-court ────────
        if handler:
            ball_xn, _ = self._norm(ball_pos[0], ball_pos[1])
            attack_left = ball_xn < 0.5
            for dp in defense:
                dxn, _ = self._norm(dp["x"], dp["y"])
                if attack_left and dxn > 0.55:
                    return "transition"
                if not attack_left and dxn < 0.45:
                    return "transition"

        # ── Double team: 2+ defenders within radius of handler ───────────
        if handler:
            rad_px = _DBL_TEAM_RAD_N * self.map_w
            close  = sum(
                1 for dp in defense
                if np.hypot(handler["x"] - dp["x"], handler["y"] - dp["y"]) < rad_px
            )
            if close >= 2:
                return "double_team"

        # ── Paint area sub-types ──────────────────────────────────────────
        if self._in_paint_zone(ball_pos):
            if handler:
                xn, _  = self._norm(handler["x"], handler["y"])
                near_block = xn < _BLOCK_XN or xn > 1.0 - _BLOCK_XN
                if near_block and handler.get("speed", 0.0) < _POST_VEL_MAX:
                    return "post_up"
            return "paint_touch"

        # ── Drive: handler moving fast ────────────────────────────────────
        if handler and handler.get("speed", 0.0) > _DRIVE_VEL_PX:
            return "drive"

        return "half_court"
