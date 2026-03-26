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
# Pixel-space shot fallback: fire when pixel_vel exceeds this threshold AND
# ball is in upper half of frame.  8.0 px/frame ≈ a shot at ~18+ ft/s at
# broadcast zoom on non-strided clips; strided clips (2× velocity) fire at
# 4+ real px/frame.  Lowered 18.0→12.0→8.0 — passes detection gate
# (possession-loss + upper-half) keeps false-positive rate low.
_PIXEL_SHOT_VEL   = 8.0


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

        Call configure(fps, stride) after construction (from UnifiedPipeline.run())
        to set fps-correct thresholds.  Defaults assume 60 fps, stride=1.
        """
        self.map_w = map_w
        self.map_h = map_h
        # NBA basket positions: ~6.5% and ~93.5% from left baseline, centred
        self._baskets: List[Tuple[int, int]] = [
            (int(0.065 * map_w), int(0.5 * map_h)),
            (int(0.935 * map_w), int(0.5 * map_h)),
        ]

        # fps / stride — set via configure(); defaults match original 60fps design
        self._fps:    float = 60.0
        self._stride: int   = 1

        self._prev_ball:        Optional[Tuple[float, float]] = None
        self._ball_vel:         float = 0.0
        self._pixel_vel_used:   bool  = False
        self._possessor:        Optional[int] = None   # player_id currently holding ball
        self._last_ball_y_pixel: Optional[float] = None   # raw image-space y coord of ball
        self._last_frame_height: Optional[int]   = None   # raw frame height in pixels
        self._loss_frame: Optional[int] = None   # frame at which possession was lost
        self._possession_held_frames: int = 0  # frames current possessor has held ball
        self._ball_loss_streak: int = 0         # consecutive frames ball detection has been None
        self._ball_buf:   deque = deque(maxlen=30)
        # Ball pixel-space y buffer for dribble floor-bounce detection.
        # Stores recent ball_y_pixel values (raw image y, increases downward).
        # Bounce signature: ball was falling (vy > 0) then rising/stationary (vy ≤ 0).
        self._bvybuf:     deque = deque(maxlen=3)   # last 3 ball_y_pixel values

        # Retroactive overrides: frame_idx → event string
        # Written when a pass is confirmed by the receiver picking up the ball.
        self._pending: Dict[int, str] = {}

        # ── Rich event accumulator (screen/cut/drive/closeout/rebound) ────
        # Append-only; consumer should read and clear `events` each frame.
        self.events: List[dict] = []

        # Per-player position history: player_id → deque of (frame, x, y, speed)
        self._phist: Dict[int, deque] = defaultdict(lambda: deque(maxlen=15))

        # Dribble count: resets on every possession change
        self._dribble_count: int = 0

        # Drive streak: player_id → consecutive frames above drive speed
        self._drive_streak: Dict[int, int] = defaultdict(int)
        self._drive_start:  Dict[int, Tuple[float, float]] = {}

        # Screen debounce: (pid_a, pid_b) → last frame a screen was logged
        self._screen_last: Dict[Tuple[int, int], int] = {}
        # Help defense rotation debounce: (defender_id, handler_id) → last frame fired
        self._help_rotation_last: Dict[Tuple[int, int], int] = {}

        # Shot debounce: minimum frames between consecutive shot detections.
        # Initialized to -(DEBOUNCE+1) so frame 0 can always trigger a shot.
        # Raised 1.5s→3.0s: real shots are ~30-80s apart; 1.5s allowed pump fakes
        # to re-fire immediately after a genuine shot debounce window closed.
        self._last_shot_frame: int = -(int(3.0 * self._fps) + 1)  # = -181 at 60fps

        # Court scale (pixels per foot, approximate from basket span)
        _span = 0.87 * map_w            # ~80.5 ft between baskets in pixels
        self._ft: float = _span / 80.5  # px per foot

        # Distance thresholds in court pixels (static — not fps-dependent)
        self._SCREEN_DIST    = 3.0 * self._ft   # 3 ft
        self._CLOSEOUT_FAR   = 6.0 * self._ft   # 6 ft
        self._CLOSEOUT_NEAR  = 3.0 * self._ft   # 3 ft

        # fps-dependent thresholds — recomputed by configure(); defaults = 60fps
        # 8 mph → ft/s → ft/abs-frame (at fps) → px/abs-frame
        self._DRIVE_SPEED    = (3.1 * 5280.0 / 3600.0 / self._fps) * self._ft
        # 3.0 seconds between shots in absolute frame count (raised from 1.5s)
        self._SHOT_DEBOUNCE: int = int(3.0 * self._fps)

    @property
    def dribble_count(self) -> int:
        """Current dribble count for the active possession."""
        return self._dribble_count

    def configure(self, fps: float, stride: int = 1) -> None:
        """Recalculate fps- and stride-dependent thresholds.

        Call once from UnifiedPipeline.run() after fps and stride are known.

        Args:
            fps:    Source video frames-per-second (e.g. 30.0 or 60.0).
            stride: Frame stride used by the prefetcher (typically 1 or 3).
        """
        self._fps    = max(1.0, float(fps))
        self._stride = max(1, int(stride))
        # Drive speed: 8 mph in court px per absolute video frame
        self._DRIVE_SPEED   = (3.1 * 5280.0 / 3600.0 / self._fps) * self._ft
        # Shot debounce: 3.0 s between shots expressed in absolute frame count
        self._SHOT_DEBOUNCE = int(3.0 * self._fps)

    def update(
        self,
        frame_idx: int,
        ball_pos: Optional[Tuple[float, float]],
        frame_tracks: List[dict],
        pixel_vel: float = 0.0,
        ball_y_pixel: Optional[float] = None,
        frame_height: Optional[int] = None,
    ) -> str:
        """
        Process one frame and return the event label.

        Args:
            frame_idx:    Current frame index.
            ball_pos:     (x2d, y2d) of ball in 2D court coords, or None.
            frame_tracks: List of player dicts with keys:
                          player_id, team, x2d, y2d, has_ball (bool).
            pixel_vel:    Ball velocity in raw image pixels/frame (from ball tracker).
            ball_y_pixel: Ball y-coordinate in raw image space (for upper-half check).
            frame_height: Raw frame height in pixels (for upper-half check).
        Returns:
            Event string: "shot" | "pass" | "dribble" | "none"
        """
        self._last_ball_y_pixel = ball_y_pixel
        self._last_frame_height = frame_height
        if ball_pos is not None and self._prev_ball is not None:
            self._ball_vel = float(np.hypot(
                ball_pos[0] - self._prev_ball[0],
                ball_pos[1] - self._prev_ball[1],
            ))
        else:
            self._ball_vel = 0.0

        if ball_pos is not None:
            self._ball_buf.append((frame_idx, ball_pos[0], ball_pos[1]))

        # Track ball pixel-y for dribble bounce confirmation
        self._bvybuf.append(ball_y_pixel)

        # ── Direct upward-velocity shot detector ─────────────────────────
        # Hough+CSRT keeps the ball "possessed" even during the shot arc,
        # so the possession state-machine can't fire.  Fire directly when the
        # ball is moving fast upward in pixel space — the clearest signature
        # of a shot release that isn't a lob pass.
        #
        # Conditions (all must hold):
        #   1. pixel_vel > 12 px/processed-frame  (raised from 6: pump fakes and
        #      arm raises rarely exceed 12px/frame; real shot releases do)
        #   2. ball_y_pixel decreased by > 8 px   (raised from 5: more confident upward move)
        #   3. vertical fraction > 0.65 — upward component is ≥65% of total velocity.
        #      Lob passes travel diagonally (large horizontal component), shots are
        #      nearly vertical at release.  Raised from 0.50 to cut diagonal passes.
        #   4. ball between 15-60% of frame height — shot releases happen in the
        #      upper portion of the frame; 0.60 upper bound cuts waist-height passes.
        #      Raised lower from 10%→15%, lowered upper from 80%→60%.
        #   5. debounce cleared
        _prev_y = getattr(self, "_prev_ball_y_pixel", None)
        if (pixel_vel > 12.0
                and _prev_y is not None
                and ball_y_pixel is not None
                and frame_height is not None
                and (ball_y_pixel - _prev_y) < -8          # ball moved UP (y decreases)
                and abs(ball_y_pixel - _prev_y) / (pixel_vel + 1e-6) > 0.65  # mostly vertical
                and ball_y_pixel > frame_height * 0.15     # not scoreboard artifact at top
                and ball_y_pixel < frame_height * 0.60     # not waist/floor level
                and frame_idx - self._last_shot_frame >= self._SHOT_DEBOUNCE):
            self._last_shot_frame = frame_idx
            self._prev_ball_y_pixel = ball_y_pixel
            self._prev_ball = ball_pos
            return "shot"
        self._prev_ball_y_pixel = ball_y_pixel

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
        self._detect_help_defense(frame_idx, frame_tracks)

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
                # Ball left a player — evaluate as shot/pass immediately.
                # NOTE: _ball_loss_streak was a 3-frame jitter guard added in session 3
                # but was structurally broken: after the first loss self._possessor=None,
                # so subsequent no-possessor frames enter the stable branch and never
                # re-increment the streak.  _evaluate_shot was permanently disabled.
                # Removed; the pixel fallback (lines 176-187) handles jitter already.
                _MIN_HOLD_FRAMES = 2  # require ≥2 frames of possession (prevents single-frame noise)
                held = self._possession_held_frames
                self._possession_held_frames = 0
                self._ball_loss_streak = 0
                if held < _MIN_HOLD_FRAMES:
                    return "none"
                self._loss_frame = frame_idx
                return self._evaluate_shot(ball_pos, frame_idx)

            if prev_id is None and possessor_id is not None:
                # Player gained ball — confirm pass if within window
                self._ball_loss_streak = 0
                self._dribble_count = 0
                if (self._loss_frame is not None
                        and frame_idx - self._loss_frame <= _PASS_MAX_FRAMES):
                    self._pending[self._loss_frame] = "pass"
                self._loss_frame = None
                self._possession_held_frames = 1
                return "none"

            if prev_id is not None and possessor_id is not None:
                # Steal / direct hand-off
                self._ball_loss_streak = 0
                self._dribble_count = 0
                self._loss_frame = None
                self._possession_held_frames = 1
                if self._ball_vel >= _PASS_MIN_VEL:
                    return "pass"
                return "none"

        # ── Stable possession ─────────────────────────────────────────────
        if possessor_id is not None:
            self._ball_loss_streak = 0
            self._possession_held_frames += 1
        else:
            self._possession_held_frames = 0

        if (possessor_id is not None
                and ball_pos is not None
                and possessor_pos is not None):
            dist = float(np.hypot(
                ball_pos[0] - possessor_pos[0],
                ball_pos[1] - possessor_pos[1],
            ))
            if dist <= _DRIBBLE_MAX_DIST and self._ball_vel <= _DRIBBLE_MAX_VEL:
                # Require floor-bounce confirmation: ball_y_pixel must have been
                # falling (vy_prev > 1.0, i.e. y increasing downward in image space)
                # and now rising/stationary (vy_curr ≤ 0).  This rejects stationary
                # ball-handling, tips, and shot releases from inflating dribble_count.
                _bounce = False
                _by = list(self._bvybuf)
                if (len(_by) >= 3
                        and _by[-3] is not None
                        and _by[-2] is not None
                        and _by[-1] is not None):
                    _vy_prev = _by[-2] - _by[-3]   # falling → positive (y down)
                    _vy_curr = _by[-1] - _by[-2]
                    _bounce  = _vy_prev > 1.0 and _vy_curr <= 0.0
                elif len(_by) >= 2 and _by[-2] is not None and _by[-1] is not None:
                    # Two-frame fallback: at least check current frame is not falling
                    _bounce = (_by[-1] - _by[-2]) <= 0.0
                if _bounce:
                    self._dribble_count += 1
                return "dribble"

        # ── Ball in flight, nobody has it ────────────────────────────────
        if possessor_id is None and self._loss_frame is not None:
            if frame_idx - self._loss_frame > _PASS_MAX_FRAMES:
                self._loss_frame = None   # nobody caught it — clear pending state

        return "none"

    def _evaluate_shot(self, ball_pos: Optional[Tuple[float, float]], frame_idx: int = 0) -> str:
        """Return 'shot' if ball is moving fast enough toward a basket.

        When pixel-space velocity is active, single-frame court coordinates are
        noisy due to homography jitter during fast motion.  Instead of skipping
        the direction check entirely (which caused fast passes to be mislabeled
        as shots), we use the last 3 frames of the court-coordinate trajectory
        buffer to compute a more stable direction vector.
        """
        # Noise gate: velocities > 150 px/frame are tracking jumps, not real shots.
        _NOISE_VEL = 150.0
        if self._ball_vel > _NOISE_VEL:
            return "none"

        if self._ball_vel < _SHOT_MIN_VEL:
            return "none"

        # Debounce: set by configure() — 1.5s of absolute frames at source fps.
        if frame_idx - self._last_shot_frame < self._SHOT_DEBOUNCE:
            return "none"

        # When 2D court position is unavailable, we cannot verify direction toward
        # basket — skip rather than fire a low-confidence shot.  The upward-velocity
        # detector at the top of update() already handles ball-in-arc frames.
        if ball_pos is None:
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
            # Court projection out of range — can't determine direction; skip.
            return "none"

        nearest = min(
            self._baskets,
            key=lambda b: np.hypot(ball_pos[0] - b[0], ball_pos[1] - b[1]),
        )

        # Backcourt guard: reject shots from center-court band (xn 0.40-0.60)
        # Mirrors _court_zone "backcourt" definition; real shots don't come from midcourt
        _xn = ball_pos[0] / max(self.map_w, 1)
        if 0.40 < _xn < 0.60:
            return "none"

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
            self._last_shot_frame = frame_idx
            return "shot"

        # Pixel-space fallback removed: if the court-coord direction check says
        # the ball is NOT moving toward the basket, trust it — don't override
        # with pixel velocity alone.  The fallback was firing on chest passes,
        # outlet passes, and arm raises that happen to be fast at waist height,
        # causing 5-15x shot over-detection.  The upward-velocity detector
        # (top of update()) already handles shots the state-machine misses.
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
            # Divide by stride so speed is in px/abs-frame regardless of stride.
            # _DRIVE_SPEED and STATIONARY/MOVING thresholds are all px/abs-frame.
            speed = (
                float(np.hypot(x - hist[-1][1], y - hist[-1][2])) / self._stride
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
                    _i_has = ti.get("has_ball", False)
                    _j_has = tj.get("has_ball", False)
                    if _i_has or _j_has:
                        _pnr_action = "pick_and_roll"
                        _bh_id = ti["player_id"] if _i_has else tj["player_id"]
                        _sc_id = tj["player_id"] if _i_has else ti["player_id"]
                    else:
                        _pnr_action = "off_ball_screen"
                        _bh_id = None
                        _sc_id = None
                    self.events.append({
                        "type": "screen_set", "x": xi, "y": yi, "frame": frame_idx,
                        "ball_handler_id": _bh_id, "screener_id": _sc_id,
                        "screen_action": _pnr_action,
                    })
                    self._screen_last[key] = frame_idx
                elif sj < STATIONARY and si > MOVING:
                    _i_has = ti.get("has_ball", False)
                    _j_has = tj.get("has_ball", False)
                    if _i_has or _j_has:
                        _pnr_action = "pick_and_roll"
                        _bh_id = ti["player_id"] if _i_has else tj["player_id"]
                        _sc_id = tj["player_id"] if _i_has else ti["player_id"]
                    else:
                        _pnr_action = "off_ball_screen"
                        _bh_id = None
                        _sc_id = None
                    self.events.append({
                        "type": "screen_set", "x": xj, "y": yj, "frame": frame_idx,
                        "ball_handler_id": _bh_id, "screener_id": _sc_id,
                        "screen_action": _pnr_action,
                    })
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
                # Convert px/abs-frame → ft/abs-frame → ft/s → mph
                mph = (avg_speed / max(1.0, self._ft)) * self._fps * 3600.0 / 5280.0
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

    def _detect_help_defense(
        self, frame_idx: int, frame_tracks: List[dict]
    ) -> None:
        """Log help_rotation when a defender moves from >12ft to <6ft of handler in ~10 frames.

        Only fires when self._possessor is not None (someone has the ball).
        Debounced: same (defender_id, handler_id) pair suppressed for 45 frames.
        """
        if self._possessor is None:
            return

        handler_hist = self._phist.get(self._possessor)
        if not handler_hist:
            return
        hx, hy = handler_hist[-1][1], handler_hist[-1][2]

        handler_team = next(
            (t.get("team") for t in frame_tracks if t["player_id"] == self._possessor),
            None,
        )
        if handler_team is None:
            return

        DIST_FAR  = 12.0 * self._ft  # 12 ft in court px
        DIST_NEAR =  6.0 * self._ft  #  6 ft in court px
        LOOKBACK  = 10
        DEBOUNCE  = 45

        for t in frame_tracks:
            if t.get("team") == handler_team or t.get("team") == "referee":
                continue
            def_id = t["player_id"]
            dhist  = self._phist.get(def_id)
            if not dhist:
                continue

            dist_now = float(np.hypot(dhist[-1][1] - hx, dhist[-1][2] - hy))
            if dist_now >= DIST_NEAR:
                continue  # not close enough now

            hist_list = list(dhist)
            old_entry = hist_list[-min(LOOKBACK, len(hist_list))]
            dist_then = float(np.hypot(old_entry[1] - hx, old_entry[2] - hy))
            if dist_then <= DIST_FAR:
                continue  # wasn't far enough back

            key = (def_id, self._possessor)
            if frame_idx - self._help_rotation_last.get(key, -999) < DEBOUNCE:
                continue

            self._help_rotation_last[key] = frame_idx
            self.events.append({
                "type":          "help_rotation",
                "defender_id":   def_id,
                "handler_id":    self._possessor,
                "rotation_dist": round(dist_now, 1),
            })
