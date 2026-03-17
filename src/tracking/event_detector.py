"""
event_detector.py — Stateful per-frame basketball event classifier.

Events: "shot" | "pass" | "dribble" | "none"

Pass events fire retroactively on the frame the ball left the passer
(once the receiver picks it up and confirms the pass).
"""

from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

_PASS_MAX_FRAMES  = 20    # max frames for a possession transfer to count as pass
_PASS_MIN_VEL     = 6.0   # min 2D ball velocity (px/frame) to call a pass
_SHOT_MIN_VEL     = 5.0   # min ball velocity to call a shot attempt
_DRIBBLE_MAX_VEL  = 14.0  # ball velocity below this near handler = dribble
_DRIBBLE_MAX_DIST = 70    # max ball-to-handler 2D distance (px) for dribble


class EventDetector:
    """
    Stateful per-frame event classifier for basketball tracking.

    Call update() once per frame with the ball position and player tracks.
    Returns the event label for that frame.

    Events fire on the frame the action begins:
      - pass:   frame when ball left the passer (set retroactively)
      - shot:   frame when ball left the shooter
      - dribble: every frame the handler has the ball and is dribbling
      - none:   all other frames
    """

    def __init__(self, map_w: int, map_h: int) -> None:
        """
        Args:
            map_w: width of the 2D court map in pixels
            map_h: height of the 2D court map in pixels
        """
        self.map_w = map_w
        self.map_h = map_h
        # NBA basket positions: ~6.5% and ~93.5% from left baseline, centred
        self._baskets: List[Tuple[int, int]] = [
            (int(0.065 * map_w), int(0.5 * map_h)),
            (int(0.935 * map_w), int(0.5 * map_h)),
        ]

        self._prev_ball:        Optional[Tuple[float, float]] = None
        self._ball_vel:         float = 0.0
        self._pixel_vel_used:   bool  = False
        self._possessor:        Optional[int] = None   # player_id currently holding ball
        self._loss_frame: Optional[int] = None   # frame at which possession was lost
        self._ball_buf:   deque = deque(maxlen=30)

        # Retroactive overrides: frame_idx → event string
        # Written when a pass is confirmed by the receiver picking up the ball.
        self._pending: Dict[int, str] = {}

    def update(
        self,
        frame_idx: int,
        ball_pos: Optional[Tuple[float, float]],
        frame_tracks: List[dict],
        pixel_vel: float = 0.0,
    ) -> str:
        """
        Process one frame and return the event label.

        Args:
            frame_idx:    Current frame index.
            ball_pos:     (x2d, y2d) of ball in 2D court coords, or None.
            frame_tracks: List of player dicts with keys:
                          player_id, team, x2d, y2d, has_ball (bool).
        Returns:
            Event string: "shot" | "pass" | "dribble" | "none"
        """
        if ball_pos is not None and self._prev_ball is not None:
            self._ball_vel = float(np.hypot(
                ball_pos[0] - self._prev_ball[0],
                ball_pos[1] - self._prev_ball[1],
            ))
        else:
            self._ball_vel = 0.0

        if ball_pos is not None:
            self._ball_buf.append((frame_idx, ball_pos[0], ball_pos[1]))

        possessor_id  = None
        possessor_pos = None
        for t in frame_tracks:
            if t.get("has_ball"):
                possessor_id  = t["player_id"]
                possessor_pos = (float(t["x2d"]), float(t["y2d"]))
                break

        # Use pixel-space velocity when available (more reliable than 2D-court vel)
        self._pixel_vel_used = pixel_vel > 0.0
        if self._pixel_vel_used:
            self._ball_vel = pixel_vel

        event = self._classify(frame_idx, ball_pos, possessor_id, possessor_pos)

        self._prev_ball = ball_pos
        self._possessor = possessor_id

        return self._pending.pop(frame_idx, event)

    # ── internal ─────────────────────────────────────────────────────────

    def _classify(
        self,
        frame_idx: int,
        ball_pos: Optional[Tuple[float, float]],
        possessor_id: Optional[int],
        possessor_pos: Optional[Tuple[float, float]],
    ) -> str:
        """Core state-machine classifier."""
        prev_id = self._possessor

        # ── Possession changed ────────────────────────────────────────────
        if possessor_id != prev_id:

            if prev_id is not None and possessor_id is None:
                # Ball left a player — potential shot or turnover
                self._loss_frame = frame_idx
                return self._evaluate_shot(ball_pos)

            if prev_id is None and possessor_id is not None:
                # Player gained ball — confirm pass if within window
                if (self._loss_frame is not None
                        and frame_idx - self._loss_frame <= _PASS_MAX_FRAMES):
                    self._pending[self._loss_frame] = "pass"
                self._loss_frame = None
                return "none"

            if prev_id is not None and possessor_id is not None:
                # Steal / direct hand-off
                self._loss_frame = None
                if self._ball_vel >= _PASS_MIN_VEL:
                    return "pass"
                return "none"

        # ── Stable possession ─────────────────────────────────────────────
        if (possessor_id is not None
                and ball_pos is not None
                and possessor_pos is not None):
            dist = float(np.hypot(
                ball_pos[0] - possessor_pos[0],
                ball_pos[1] - possessor_pos[1],
            ))
            if dist <= _DRIBBLE_MAX_DIST and self._ball_vel <= _DRIBBLE_MAX_VEL:
                return "dribble"

        # ── Ball in flight, nobody has it ────────────────────────────────
        if possessor_id is None and self._loss_frame is not None:
            if frame_idx - self._loss_frame > _PASS_MAX_FRAMES:
                self._loss_frame = None   # nobody caught it — clear pending state

        return "none"

    def _evaluate_shot(self, ball_pos: Optional[Tuple[float, float]]) -> str:
        """Return 'shot' if ball is moving fast enough toward a basket.

        When pixel-space velocity is active, single-frame court coordinates are
        noisy due to homography jitter during fast motion.  Instead of skipping
        the direction check entirely (which caused fast passes to be mislabeled
        as shots), we use the last 3 frames of the court-coordinate trajectory
        buffer to compute a more stable direction vector.
        """
        if ball_pos is None or self._ball_vel < _SHOT_MIN_VEL:
            return "none"
        if self._prev_ball is None:
            return "none"

        in_bounds = (
            0 <= ball_pos[0] <= self.map_w
            and 0 <= ball_pos[1] <= self.map_h
            and 0 <= self._prev_ball[0] <= self.map_w
            and 0 <= self._prev_ball[1] <= self.map_h
        )
        if not in_bounds:
            # Court projection out of range — can't determine direction; allow.
            return "shot"

        nearest = min(
            self._baskets,
            key=lambda b: np.hypot(ball_pos[0] - b[0], ball_pos[1] - b[1]),
        )

        # When pixel velocity is active, use a multi-frame average origin from
        # _ball_buf (court coords) to reduce homography noise.
        if self._pixel_vel_used and len(self._ball_buf) >= 3:
            recent = list(self._ball_buf)[-3:]
            origin_x = sum(r[1] for r in recent) / len(recent)
            origin_y = sum(r[2] for r in recent) / len(recent)
        else:
            origin_x, origin_y = self._prev_ball

        dx_ball   = ball_pos[0] - origin_x
        dy_ball   = ball_pos[1] - origin_y
        dx_basket = nearest[0]  - ball_pos[0]
        dy_basket = nearest[1]  - ball_pos[1]

        if dx_ball * dx_basket + dy_ball * dy_basket > 0:
            return "shot"
        return "none"
