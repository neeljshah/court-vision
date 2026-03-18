"""
event_detector.py — Stateful per-frame basketball event classifier.

Events: "shot" | "pass" | "dribble" | "none"

Pass events fire retroactively on the frame the ball left the passer
(once the receiver picks it up and confirms the pass).
"""

from collections import defaultdict, deque
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

        # ── Rich event accumulator (screen/cut/drive/closeout/rebound) ────
        # Append-only; consumer should read and clear `events` each frame.
        self.events: List[dict] = []

        # Per-player position history: player_id → deque of (frame, x, y, speed)
        self._phist: Dict[int, deque] = defaultdict(lambda: deque(maxlen=15))

        # Drive streak: player_id → consecutive frames above drive speed
        self._drive_streak: Dict[int, int] = defaultdict(int)
        self._drive_start:  Dict[int, Tuple[float, float]] = {}

        # Screen debounce: (pid_a, pid_b) → last frame a screen was logged
        self._screen_last: Dict[Tuple[int, int], int] = {}

        # Court scale (pixels per foot, approximate from basket span)
        _span = 0.87 * map_w            # ~80.5 ft between baskets in pixels
        self._ft: float = _span / 80.5  # px per foot

        # Distance thresholds in court pixels
        self._SCREEN_DIST    = 3.0 * self._ft   # 3 ft
        self._CLOSEOUT_FAR   = 6.0 * self._ft   # 6 ft
        self._CLOSEOUT_NEAR  = 3.0 * self._ft   # 3 ft
        # 8 mph → ft/s → ft/frame (30fps) → px/frame
        self._DRIVE_SPEED    = (8.0 * 5280.0 / 3600.0 / 30.0) * self._ft

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

        # Update player position history before classification
        self._update_player_hist(frame_idx, frame_tracks)

        event = self._classify(frame_idx, ball_pos, possessor_id, possessor_pos)

        # Shot-triggered rich events (use self._possessor = shooter before update)
        if event == "shot":
            self._detect_closeout(frame_idx, frame_tracks)
            self._detect_rebound_positions(frame_idx, frame_tracks)

        self._prev_ball = ball_pos
        self._possessor = possessor_id

        # Per-frame rich events (run after possessor update)
        self._detect_screens(frame_idx, frame_tracks)
        self._detect_cuts(frame_idx, frame_tracks)
        self._detect_drives(frame_idx, frame_tracks)

        # Prune stale _pending entries (retroactive writes whose target frame has
        # already been consumed). Prevents unbounded growth on long game sequences.
        _stale_cutoff = frame_idx - _PASS_MAX_FRAMES - 1
        for _k in [k for k in self._pending if k < _stale_cutoff]:
            del self._pending[_k]

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

    # ── Rich event helpers ────────────────────────────────────────────────

    def _update_player_hist(
        self, frame_idx: int, frame_tracks: List[dict]
    ) -> None:
        """Append each player's current position + speed to their history deque."""
        for t in frame_tracks:
            if t.get("team") == "referee":
                continue
            pid = t["player_id"]
            x, y = float(t.get("x2d", 0)), float(t.get("y2d", 0))
            hist = self._phist[pid]
            speed = (
                float(np.hypot(x - hist[-1][1], y - hist[-1][2]))
                if hist else 0.0
            )
            hist.append((frame_idx, x, y, speed))

    def _nearest_basket(self, x: float, y: float) -> Tuple[int, int]:
        """Return the basket (x, y) nearest to the given court position."""
        return min(self._baskets, key=lambda b: np.hypot(x - b[0], y - b[1]))

    def _toward_basket(
        self, dx: float, dy: float, x: float, y: float
    ) -> bool:
        """Return True if velocity (dx, dy) from (x, y) is directed toward nearest basket."""
        bx, by = self._nearest_basket(x, y)
        return (dx * (bx - x) + dy * (by - y)) > 0.0

    def _detect_screens(
        self, frame_idx: int, frame_tracks: List[dict]
    ) -> None:
        """Log screen_set when a cross-team pair converges and one stays stationary.

        Fires when two players from different teams are within SCREEN_DIST and one
        has near-zero speed while the other is still moving.
        """
        STATIONARY = 1.5   # px/frame
        MOVING     = 3.0   # px/frame
        DEBOUNCE   = 30    # min frames between screen events for same pair

        for i, ti in enumerate(frame_tracks):
            if ti.get("team") == "referee":
                continue
            hi = self._phist.get(ti["player_id"])
            if not hi:
                continue
            xi, yi, si = hi[-1][1], hi[-1][2], hi[-1][3]

            for tj in frame_tracks[i + 1:]:
                if tj.get("team") == "referee" or tj.get("team") == ti.get("team"):
                    continue
                hj = self._phist.get(tj["player_id"])
                if not hj:
                    continue
                xj, yj, sj = hj[-1][1], hj[-1][2], hj[-1][3]

                if float(np.hypot(xi - xj, yi - yj)) > self._SCREEN_DIST:
                    continue

                key = (min(ti["player_id"], tj["player_id"]),
                       max(ti["player_id"], tj["player_id"]))
                if frame_idx - self._screen_last.get(key, -999) < DEBOUNCE:
                    continue

                if si < STATIONARY and sj > MOVING:
                    self.events.append(
                        {"type": "screen_set", "x": xi, "y": yi, "frame": frame_idx}
                    )
                    self._screen_last[key] = frame_idx
                elif sj < STATIONARY and si > MOVING:
                    self.events.append(
                        {"type": "screen_set", "x": xj, "y": yj, "frame": frame_idx}
                    )
                    self._screen_last[key] = frame_idx

    def _detect_cuts(
        self, frame_idx: int, frame_tracks: List[dict]
    ) -> None:
        """Log cut when a player without the ball changes direction >90° toward basket.

        Compares direction over frames [-10..-5] versus [-5..0].  Minimum speed
        filter avoids false positives from stationary jitter.
        """
        possessors = {t["player_id"] for t in frame_tracks if t.get("has_ball")}
        MIN_DISP = 4.0  # min displacement magnitude per 5-frame window (px)

        for t in frame_tracks:
            if t.get("team") == "referee" or t["player_id"] in possessors:
                continue
            hist = self._phist.get(t["player_id"])
            if not hist or len(hist) < 10:
                continue
            pts = list(hist)
            v1x = pts[-5][1] - pts[-10][1]
            v1y = pts[-5][2] - pts[-10][2]
            v2x = pts[-1][1] - pts[-5][1]
            v2y = pts[-1][2] - pts[-5][2]
            if np.hypot(v1x, v1y) < MIN_DISP or np.hypot(v2x, v2y) < MIN_DISP:
                continue
            cos_a = float(np.clip(
                (v1x * v2x + v1y * v2y)
                / (np.hypot(v1x, v1y) * np.hypot(v2x, v2y) + 1e-9),
                -1.0, 1.0,
            ))
            if cos_a < 0.0 and self._toward_basket(v2x, v2y, pts[-1][1], pts[-1][2]):
                self.events.append(
                    {"type": "cut", "player_id": t["player_id"], "frame": frame_idx}
                )

    def _detect_drives(
        self, frame_idx: int, frame_tracks: List[dict]
    ) -> None:
        """Log drive when ball handler exceeds drive speed toward basket for 5+ frames."""
        for t in frame_tracks:
            if not t.get("has_ball") or t.get("team") == "referee":
                continue
            pid = t["player_id"]
            hist = self._phist.get(pid)
            if not hist or len(hist) < 2:
                continue
            x, y = hist[-1][1], hist[-1][2]
            speed = hist[-1][3]
            vx, vy = x - hist[-2][1], y - hist[-2][2]
            if speed >= self._DRIVE_SPEED and self._toward_basket(vx, vy, x, y):
                if self._drive_streak[pid] == 0:
                    self._drive_start[pid] = (x, y)
                self._drive_streak[pid] += 1
            else:
                if self._drive_streak.get(pid, 0) >= 5:
                    sx, _ = self._drive_start.get(pid, (x, x))
                    self.events.append({
                        "type": "drive", "player_id": pid,
                        "start_x": float(sx), "end_x": float(x),
                    })
                self._drive_streak[pid] = 0

    def _detect_closeout(
        self, frame_idx: int, frame_tracks: List[dict]
    ) -> None:
        """Log closeout when a defender accelerates from >6ft to <3ft of shooter.

        Called immediately after a shot is classified, before self._possessor is
        updated — so self._possessor is the player who released the ball.
        """
        shooter_id = self._possessor
        if shooter_id is None:
            return
        shooter_team = next(
            (t.get("team") for t in frame_tracks if t["player_id"] == shooter_id),
            None,
        )
        if shooter_team is None:
            return
        shist = self._phist.get(shooter_id)
        if not shist:
            return
        sx, sy = shist[-1][1], shist[-1][2]

        for t in frame_tracks:
            if t.get("team") == shooter_team or t.get("team") == "referee":
                continue
            def_id = t["player_id"]
            dhist = self._phist.get(def_id)
            if not dhist or len(dhist) < 5:
                continue
            pts = list(dhist)
            dist_now  = float(np.hypot(pts[-1][1] - sx, pts[-1][2] - sy))
            dist_then = float(np.hypot(pts[-min(10, len(pts))][1] - sx,
                                       pts[-min(10, len(pts))][2] - sy))
            if dist_then > self._CLOSEOUT_FAR and dist_now < self._CLOSEOUT_NEAR:
                avg_speed = float(np.mean([pts[-i][3]
                                           for i in range(1, min(6, len(pts) + 1))]))
                # Convert px/frame → mph
                mph = (avg_speed / max(1.0, self._ft)) * 30.0 * 3600.0 / 5280.0
                self.events.append({
                    "type": "closeout",
                    "defender_id": def_id,
                    "closeout_speed": round(mph, 2),
                })

    def _detect_rebound_positions(
        self, frame_idx: int, frame_tracks: List[dict]
    ) -> None:
        """Record crash angle, crash speed, and box-out status at shot release.

        Called at the moment of shot detection so positions reflect pre-shot state.
        """
        bref = self._prev_ball if self._prev_ball is not None else (
            self.map_w / 2, self.map_h / 2
        )
        bx, by = self._nearest_basket(float(bref[0]), float(bref[1]))

        for t in frame_tracks:
            if t.get("team") == "referee":
                continue
            pid = t["player_id"]
            hist = self._phist.get(pid)
            if not hist or len(hist) < 2:
                continue
            x, y     = hist[-1][1], hist[-1][2]
            vx, vy   = x - hist[-2][1], y - hist[-2][2]
            crash_angle = float(np.degrees(np.arctan2(vy, vx))) if (vx or vy) else 0.0
            crash_speed = hist[-1][3]
            p_team = t.get("team", "")
            p_dist = float(np.hypot(x - bx, y - by))
            # box_out: player between an opponent and the basket
            box_out = any(
                float(np.hypot(s.get("x2d", x) - bx, s.get("y2d", y) - by)) > p_dist
                for s in frame_tracks
                if s.get("team") not in (p_team, "referee")
                and float(np.hypot(s.get("x2d", 0) - x,
                                   s.get("y2d", 0) - y)) < self._SCREEN_DIST * 2
            )
            self.events.append({
                "type": "rebound_position",
                "player_id": pid,
                "crash_angle": round(crash_angle, 1),
                "crash_speed": round(crash_speed, 2),
                "box_out": bool(box_out and self._toward_basket(vx, vy, x, y)),
            })
