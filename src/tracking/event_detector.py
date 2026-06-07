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
_PIXEL_SHOT_VEL       = 6.5   # Bug 30 fix 2026-05-28: 8.0→6.5 — current threshold rejects Curry/Lillard fast releases. Belt-and-suspenders gates (handler_in_range, cos≥0.75, debounce) still active.
_PIXEL_SHOT_VEL_PAINT = 3.0   # Bug 30 fix 2026-05-28: 4.0→3.0 — Jokic floaters / hooks fall under 4.0 px/frame at broadcast zoom.


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
        # R13: align with pipeline `_BASKET_L/R = (0.045, 0.955)` — was (0.065, 0.935),
        # a 2-ft mismatch that suppressed near-basket triggers.
        self._baskets: List[Tuple[int, int]] = [
            (int(0.045 * map_w), int(0.5 * map_h)),
            (int(0.955 * map_w), int(0.5 * map_h)),
        ]

        # fps / stride — set via configure(); defaults match original 60fps design
        self._fps:    float = 60.0
        self._stride: int   = 1
        # fps/stride-aware pass window and pixel-vel threshold (set in configure())
        self._PASS_MAX_FRAMES: int   = _PASS_MAX_FRAMES
        self._PIXEL_SHOT_VEL:  float = _PIXEL_SHOT_VEL

        self._prev_ball:        Optional[Tuple[float, float]] = None
        self._ball_vel:         float = 0.0
        self._pixel_vel_used:   bool  = False
        self._possessor:        Optional[int] = None   # player_id currently holding ball
        self._last_ball_y_pixel: Optional[float] = None   # raw image-space y coord of ball
        self._last_frame_height: Optional[int]   = None   # raw frame height in pixels
        self._last_ball_frame:  int = -999   # frame index of last non-None ball_pos
        # Rolling history of DETECTED ball y positions: (frame_idx, ball_y_pixel).
        # Only appended when ball_y_pixel is not None — persists across undetected frames.
        # Used by upward-velocity shot detector instead of single-frame _prev_ball_y_pixel.
        self._ball_y_hist: deque = deque(maxlen=60)   # ~6s at 10fps processed
        self._loss_frame: Optional[int] = None   # frame at which possession was lost
        self._possession_held_frames: int = 0  # frames current possessor has held ball
        self._ball_loss_streak: int = 0         # consecutive frames ball detection has been None
        self._ball_buf:   deque = deque(maxlen=30)
        # Ball pixel-space y buffer for dribble floor-bounce detection.
        # Stores recent ball_y_pixel values (raw image y, increases downward).
        # Bounce signature: ball was falling (vy > 0) then rising/stationary (vy ≤ 0).
        self._bvybuf:     deque = deque(maxlen=8)   # R10: 3→8; survives stride-3 jitter

        # Handler vel-toward-basket history: last 10 processed frames.
        # Used by both shot detectors to require the ball-handler was actually
        # approaching the basket before a "shot" is fired.  Positive = toward.
        self._handler_vtb_buf: deque = deque(maxlen=10)

        # Retroactive overrides: frame_idx → event string
        # Written when a pass is confirmed by the receiver picking up the ball.
        self._pending: Dict[int, str] = {}

        # ── Rich event accumulator (screen/cut/drive/closeout/rebound) ────
        # Append-only; consumer should read and clear `events` each frame.
        self.events: List[dict] = []

        # Per-player position history: player_id → deque of (frame, x, y, speed)
        # P13 2026-05-29: maxlen 15 → 30. Prior cap at ~1.5s of history was
        # bottlenecking closeout (P8 wants 1.5s+), steal (P10 widened to 1.5s),
        # and screen-set detections (which look at multi-second player approach).
        # 3s of history at stride=3 fps=30 = 30 entries; memory cost negligible.
        self._phist: Dict[int, deque] = defaultdict(lambda: deque(maxlen=30))

        # Dribble count: resets on every possession change
        self._dribble_count: int = 0

        # Drive streak: player_id → consecutive frames above drive speed
        self._drive_streak: Dict[int, int] = defaultdict(int)
        self._drive_start:  Dict[int, Tuple[float, float]] = {}
        # P22 (2026-05-30): per-player tolerated sub-threshold-frame count so a
        # drive survives 1-2 frame velocity dips (gather step / hesitation /
        # contact) instead of resetting on every dip. Prior reset-on-dip logic
        # emitted only ~3.8 drives/game vs NBA ~50.
        self._drive_miss: Dict[int, int] = defaultdict(int)
        self._DRIVE_MISS_TOL: int = 2

        # Screen debounce: (pid_a, pid_b) → last frame a screen was logged
        self._screen_last: Dict[Tuple[int, int], int] = {}
        # Help defense rotation debounce: (defender_id, handler_id) → last frame fired
        self._help_rotation_last: Dict[Tuple[int, int], int] = {}
        # R17: cut event debounce per player (1s window suppresses 10-20x multi-fire on the same cut)
        self._cut_last: Dict[int, int] = {}

        # Shot debounce: minimum frames between consecutive shot detections.
        # Initialized to -(DEBOUNCE+1) so frame 0 can always trigger a shot.
        # Now 8.0s to reduce over-detection (raised from 3.5s).
        self._last_shot_frame: int = -(int(8.0 * self._fps) + 1)  # = -481 at 60fps
        # R13: track last shooter for tip-in window (debounce override when shooter changes)
        self._last_shot_shooter: Optional[int] = None

        # Court scale (pixels per foot, approximate from basket span)
        _span = 0.87 * map_w            # ~80.5 ft between baskets in pixels
        self._ft: float = _span / 80.5  # px per foot

        # Distance thresholds in court pixels (static — not fps-dependent)
        self._SCREEN_DIST    = 3.0 * self._ft   # 3 ft
        self._CLOSEOUT_FAR   = 8.0 * self._ft   # R10: 6→8 ft (homography jitter ±1-2 ft RMS)
        self._CLOSEOUT_NEAR  = 4.0 * self._ft   # R10: 3→4 ft

        # fps-dependent thresholds — recomputed by configure(); defaults = 60fps
        # 8 mph → ft/s → ft/abs-frame (at fps) → px/abs-frame
        self._DRIVE_SPEED    = (3.1 * 5280.0 / 3600.0 / self._fps) * self._ft
        # 8.0 seconds between shots in absolute frame count (raised from 3.5s to reduce
        # over-detection; NBA shot clock is 24s so 8s minimum between attempts is safe)
        self._SHOT_DEBOUNCE: int = int(8.0 * self._fps)

        # ── R16 missing-event detectors: steal / block / rebound / post_up ──
        # Per-event debounce state (initialized to large negative so first frame can fire).
        self._steal_last:   Dict[Tuple[int, int], int] = {}    # (thief, victim) → frame
        self._block_last:   int = -10_000                       # last frame a block fired
        # Pending shots awaiting rebound resolution.
        # List of dicts: {shot_frame, shooter_id, shooter_team, basket}
        self._pending_shots: List[dict] = []
        self._rebound_last_shot: int = -1                       # last shot_frame settled
        self._post_up_last: Dict[int, int] = {}                 # handler_id → last fire frame
        # Cumulative frames each handler has spent in the post-up window for the
        # CURRENT qualifying streak; reset whenever they break the conditions.
        self._post_up_streak: Dict[int, int] = defaultdict(int)
        # Team membership cache (player_id → team) — populated each frame for cross-method use.
        self._team_of: Dict[int, str] = {}

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
        # 8.0s between shots in absolute frame count (raised from 3.5s)
        self._SHOT_DEBOUNCE = int(8.0 * self._fps)
        # fps/stride-aware pass window: 2.0s real-time in processed frames
        self._PASS_MAX_FRAMES = max(_PASS_MAX_FRAMES, int(2.0 * self._fps / self._stride))
        # pixel-vel shot threshold scales with stride (larger stride → larger per-frame displacement)
        self._PIXEL_SHOT_VEL = _PIXEL_SHOT_VEL * self._stride

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
        # Compute velocity gap BEFORE updating _last_ball_frame.
        _ball_gap = frame_idx - self._last_ball_frame  # frames since last detection
        _large_gap = _ball_gap > 20                    # gap too wide for reliable velocity
        if ball_pos is not None and self._prev_ball is not None:
            if _large_gap:
                # Velocity across a large gap is meaningless (could be teleport artifact).
                # Zero it out and clear _prev_ball so direction check is skipped.
                self._ball_vel = 0.0
                self._prev_ball = None
            else:
                self._ball_vel = float(np.hypot(
                    ball_pos[0] - self._prev_ball[0],
                    ball_pos[1] - self._prev_ball[1],
                )) / max(1, _ball_gap)
        else:
            self._ball_vel = 0.0

        if ball_pos is not None:
            self._ball_buf.append((frame_idx, ball_pos[0], ball_pos[1]))
            self._last_ball_frame = frame_idx

        # Track ball pixel-y for dribble bounce confirmation
        self._bvybuf.append(ball_y_pixel)

        # ── FIX 2: Handler vel-toward-basket guard (10-frame window) ─────
        # Compute the ball-handler's velocity toward the nearest basket using
        # the PREVIOUS frame's history (before _update_player_hist for this frame).
        # Appended to _handler_vtb_buf every frame; shot detectors require any
        # of the last 10 frames to show the handler moving toward the basket.
        _handler_vtb_now = 0.0
        for _t in frame_tracks:
            if _t.get("has_ball"):
                _hist = list(self._phist[_t["player_id"]])
                if len(_hist) >= 2:
                    _, _x1, _y1, _ = _hist[-2]
                    _, _x2, _y2, _ = _hist[-1]
                    _dx, _dy = _x2 - _x1, _y2 - _y1
                    _nb = min(self._baskets,
                              key=lambda b, x=_x2, y=_y2: np.hypot(x - b[0], y - b[1]))
                    _dbx, _dby = _nb[0] - _x2, _nb[1] - _y2
                    _nd = np.hypot(_dbx, _dby) + 1e-6
                    _handler_vtb_now = (_dx * _dbx + _dy * _dby) / _nd
                break
        self._handler_vtb_buf.append(_handler_vtb_now)
        # Guard: block shot only when handler was *consistently sprinting away* from
        # basket (max vtb < -1.0).  Stationary handlers (vtb=0) and approaching
        # handlers (vtb>0) both pass.  Filters ball bounces where the only tracked
        # "handler" was actively running away at the moment of the bounce.
        # Bug 30 fix 2026-05-28: -1.0 → -2.0 — step-back jumpers have vtb ≈ -1.5
        # for ~5 frames during the gather. Pixel-vel + ball_y_pixel + cos-sim are
        # hard barriers against outlet passes (cos-sim < 0 to basket).
        _handler_toward_basket = (
            max(self._handler_vtb_buf, default=0.0) > -2.0
        )

        # ── Direct upward-velocity shot detector ─────────────────────────
        # Hough+CSRT keeps the ball "possessed" even during the shot arc,
        # so the possession state-machine can't fire.  Fire directly when the
        # ball is moving fast upward in pixel space — the clearest signature
        # of a shot release that isn't a lob pass.
        #
        # Conditions (all must hold):
        #   1. pixel_vel > threshold (ball moving fast)
        #   2. ball between 15-80% of frame height (not scoreboard/baseline)
        #   3. debounce cleared (8s)
        # _y_drop / _ref_y rise check removed — fails for long frame gaps;
        # pixel_vel > threshold already ensures the ball is actually moving fast.

        # R11: gate the pixel-velocity fast-path. Previously this branch fired
        # on any fast upward ball motion with NO possessor / court-position /
        # direction check — causing 2.1x over-detection (357 shots vs ~170
        # expected on game 0022500119). Add three gates:
        #   A: recent possessor exists (real shot just left a player's hands)
        #   B: handler within 30 ft of nearest basket (court coords)
        #   C: handler was approaching basket (existing _handler_toward_basket)
        _possessor_now = next((t for t in frame_tracks if t.get("has_ball")), None)
        _recent_handler = (_possessor_now is not None) or (self._possessor is not None)
        _handler_in_range = False
        _hdist_px = float("inf")
        if _possessor_now is not None:
            _hx = float(_possessor_now.get("x2d", 0))
            _hy = float(_possessor_now.get("y2d", 0))
            _nb = min(self._baskets, key=lambda b: np.hypot(_hx - b[0], _hy - b[1]))
            _hdist_px = float(np.hypot(_hx - _nb[0], _hy - _nb[1]))
            # Bug 30 fix 2026-05-28: 30 → 32 ft. Curry/Lillard/Trae take logo
            # threes from 28-32 ft; the prior cap silently rejected them.
            _handler_in_range = _hdist_px <= 32.0 * self._ft
        elif self._possessor is not None:
            # No live possessor this frame — allow but only if state-machine had one recently
            _handler_in_range = True

        # R13: paint relaxation. When handler is within 6 ft of basket, lower the
        # pixel-vel bar (layups/dunks have lower release velocity at broadcast zoom),
        # accept stationary handlers (vtb≈0 under the rim), and allow second shot
        # within 1.5s if shooter changed (tip-ins).
        _in_paint = _handler_in_range and _hdist_px <= 6.0 * self._ft
        _pv_thr = (_PIXEL_SHOT_VEL_PAINT * self._stride) if _in_paint \
                  else max(8.0, self._PIXEL_SHOT_VEL * 0.6)
        _tip_window = int(1.5 * self._fps)
        _is_tipin = (
            _possessor_now is not None
            and self._last_shot_shooter is not None
            and _possessor_now["player_id"] != self._last_shot_shooter
            and frame_idx - self._last_shot_frame < _tip_window
        )
        _debounce_ok = (frame_idx - self._last_shot_frame >= self._SHOT_DEBOUNCE) or _is_tipin

        if (pixel_vel > _pv_thr
                and ball_y_pixel is not None
                and frame_height is not None
                and ball_y_pixel > frame_height * 0.15       # not scoreboard artifact at top
                and ball_y_pixel < frame_height * 0.75       # reject floor-level balls
                and _recent_handler                          # R11: gate A
                and _handler_in_range                        # R11: gate B
                and (_handler_toward_basket or _in_paint)    # R11/R13: vtb~0 under basket OK
                and _debounce_ok):                           # R13: tip-in override
            self._last_shot_frame = frame_idx
            if _possessor_now is not None:
                self._last_shot_shooter = _possessor_now["player_id"]
            self._prev_ball_y_pixel = ball_y_pixel
            self._prev_ball = ball_pos
            # R16: refresh team cache so block/rebound have it, then fire block
            # detection on the SAME frame and queue the shot for rebound polling.
            self._team_of = {
                t["player_id"]: t.get("team", "")
                for t in frame_tracks if "player_id" in t
            }
            self._detect_block(frame_idx, frame_tracks, ball_pos)
            self._register_pending_shot(frame_idx, frame_tracks, ball_pos)
            return "shot"
        self._prev_ball_y_pixel = ball_y_pixel if ball_y_pixel is not None else getattr(self, "_prev_ball_y_pixel", None)

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

        # R16: refresh team cache (used by steal / block / rebound / post_up).
        self._team_of = {
            t["player_id"]: t.get("team", "")
            for t in frame_tracks if "player_id" in t
        }

        event = self._classify(frame_idx, ball_pos, possessor_id, possessor_pos)

        # Shot-triggered rich events (use self._possessor = shooter before update)
        if event == "shot":
            self._detect_closeout(frame_idx, frame_tracks)
            self._detect_rebound_positions(frame_idx, frame_tracks)
            # R16: block + queue for later rebound polling
            self._detect_block(frame_idx, frame_tracks, ball_pos)
            self._register_pending_shot(frame_idx, frame_tracks, ball_pos)

        # When gap was ≤20 frames and ball_pos is not None, record new position.
        # Large-gap case: _prev_ball already cleared to None above.
        if ball_pos is not None and not _large_gap:
            self._prev_ball = ball_pos
        elif ball_pos is None:
            self._prev_ball = None
        # else: _large_gap → _prev_ball already set to None in vel block above
        self._possessor = possessor_id

        # Per-frame rich events (run after possessor update)
        self._detect_screens(frame_idx, frame_tracks)
        self._detect_cuts(frame_idx, frame_tracks)
        self._detect_drives(frame_idx, frame_tracks)
        self._detect_help_defense(frame_idx, frame_tracks)
        # R16: post-up + rebound polling (run every frame)
        self._detect_post_up(frame_idx, frame_tracks)
        self._detect_rebound(frame_idx, frame_tracks, ball_pos)

        # Prune stale _pending entries (retroactive writes whose target frame has
        # already been consumed). Prevents unbounded growth on long game sequences.
        _stale_cutoff = frame_idx - self._PASS_MAX_FRAMES - 1
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
                # Pass handler-toward-basket flag so direction path can also
                # reject events where the handler was sprinting away from basket.
                _htb = max(self._handler_vtb_buf, default=0.0) > -1.0
                return self._evaluate_shot(ball_pos, frame_idx, handler_toward_basket=_htb)

            if prev_id is None and possessor_id is not None:
                # Player gained ball — confirm pass if within window
                self._ball_loss_streak = 0
                self._dribble_count = 0
                if (self._loss_frame is not None
                        and frame_idx - self._loss_frame <= self._PASS_MAX_FRAMES):
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
                # R16: tag steal when ball changes hands across teams AND the new
                # possessor closed in from >6 ft within the last 8 frames AND the
                # ball was moving fast enough that it wasn't a passive pickup.
                if self._detect_steal(frame_idx, prev_id, possessor_id):
                    return "steal"
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
                # R10: Replace the strict 3-of-3 OR all-None dead-zone gate. The old
                # gate fired on neither branch when CSRT had partial loss (mixed
                # None/value buffer) — which is the COMMON case — so dribble_count
                # was structurally ≈0. New strategy:
                #  1. Look for any falling→rising oscillation in the last 8 non-None
                #     samples (strict bounce signature, jitter-tolerant).
                #  2. Cadence fallback as DEFAULT when no strict bounce — 1.5s at
                #     current fps/stride, regardless of CSRT state.
                # Capped at 24 (24-second shot clock physical ceiling).
                _bounce = False
                _by_valid = [v for v in self._bvybuf if v is not None]
                if len(_by_valid) >= 3:
                    _diffs = np.diff(_by_valid)
                    for _i in range(len(_diffs) - 1):
                        if _diffs[_i] > 0.2 and _diffs[_i + 1] <= 0.0:
                            _bounce = True
                            break
                if not _bounce and self._possession_held_frames > 0:
                    _cadence = max(1, int(1.5 * self._fps / max(1, self._stride)))
                    if (self._possession_held_frames % _cadence == 0
                            and self._dribble_count < 24):
                        _bounce = True
                if _bounce:
                    self._dribble_count = min(24, self._dribble_count + 1)
                return "dribble"

        # ── Ball in flight, nobody has it ────────────────────────────────
        if possessor_id is None and self._loss_frame is not None:
            if frame_idx - self._loss_frame > self._PASS_MAX_FRAMES:
                self._loss_frame = None   # nobody caught it — clear pending state

        return "none"

    def _evaluate_shot(
        self,
        ball_pos: Optional[Tuple[float, float]],
        frame_idx: int = 0,
        handler_toward_basket: bool = True,
    ) -> str:
        """Return 'shot' if ball is moving fast enough toward a basket.

        When pixel-space velocity is active, single-frame court coordinates are
        noisy due to homography jitter during fast motion.  Instead of skipping
        the direction check entirely (which caused fast passes to be mislabeled
        as shots), we use the last 3 frames of the court-coordinate trajectory
        buffer to compute a more stable direction vector.

        Args:
            handler_toward_basket: Set False when handler was sprinting away from
                the basket in the last 10 frames — suppresses outlet-pass misfires.
        """
        # Noise gate: velocities > 120 px/frame are tracking jumps, not real shots.
        _NOISE_VEL = 120.0
        if self._ball_vel > _NOISE_VEL:
            return "none"

        if self._ball_vel < _SHOT_MIN_VEL:
            return "none"

        # Debounce: set by configure() — 5s of absolute frames at source fps.
        if frame_idx - self._last_shot_frame < self._SHOT_DEBOUNCE:
            return "none"

        # Handler must not have been sprinting away from basket (blocks outlet passes).
        if not handler_toward_basket:
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

        # R13: paint exception — when ball is <6 ft from basket, the direction
        # vector (basket - ball) collapses and the cos-similarity gate degenerates
        # (always fails). Accept on ball-velocity magnitude alone in that band so
        # layups/dunks/tip-ins aren't structurally rejected.
        _b2basket = float(np.hypot(dx_basket, dy_basket))
        if _b2basket < 6.0 * self._ft and np.hypot(dx_ball, dy_ball) >= _SHOT_MIN_VEL:
            self._last_shot_frame = frame_idx
            return "shot"
        # cos>0.75 ≈ within 41° of direct basket line — tight enough to reject most
        # passes and arm raises while keeping corner 3s and pull-ups (raised 0.5→0.75).
        if dx_ball * dx_basket + dy_ball * dy_basket > 0.75 * (np.hypot(dx_ball, dy_ball) * _b2basket + 1e-6):
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

    def _was_stationary(self, player_id: int, hold_frames: int, stationary_thresh: float) -> bool:
        """R17: True if player_id's speed has stayed below `stationary_thresh`
        for the last `hold_frames` processed frames. Used by _detect_screens
        to require a sustained set (≥0.6s) instead of a single-frame anchor.
        """
        hist = self._phist.get(player_id)
        if not hist or len(hist) < hold_frames:
            return False
        recent = list(hist)[-hold_frames:]
        return all(p[3] < stationary_thresh for p in recent)

    def _detect_screens(
        self, frame_idx: int, frame_tracks: List[dict]
    ) -> None:
        """Log screen_set when a cross-team pair converges and one stays stationary.

        R17: thresholds are now stride-aware (1.5/3.0 px/frame at stride=1 are
        ~5 ft/s = walking pace, firing on routine motion). Debounce raised
        30→3s, and the stationary player must hold position for ≥0.6s — this
        eliminates the 30x over-detection rate observed in baseline (3,629
        screen_set events on game 0022500119 vs NBA-typical 80-120).
        """
        STATIONARY = 0.5 * self._stride   # stride-aware: ~0.5 px/source-frame
        MOVING     = 4.0 * self._stride
        DEBOUNCE   = max(90, int(3.0 * self._fps / max(1, self._stride)))   # 3s
        _HOLD      = max(6,  int(0.6 * self._fps / max(1, self._stride)))   # 0.6s hold

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

                # R17: require the stationary player to have held position for ≥0.6s.
                # Single-frame "stationary" was a major false-positive source.
                if (si < STATIONARY and sj > MOVING
                        and self._was_stationary(ti["player_id"], _HOLD, STATIONARY)):
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
                elif (sj < STATIONARY and si > MOVING
                        and self._was_stationary(tj["player_id"], _HOLD, STATIONARY)):
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

        R17: raised MIN_DISP 4.0→10.0 px (~5 ft, was firing on idle steps),
        tightened cos gate -0.0 → -0.3 (require sharper direction reversal),
        added per-player 1s debounce (genuine cuts span 10-20 frames; each was
        counted 10-20 times). Eliminated 200x over-detection (19,347 cuts on
        game 0022500119 vs NBA-typical 80-100).
        """
        possessors = {t["player_id"] for t in frame_tracks if t.get("has_ball")}
        MIN_DISP = 10.0  # ~5 ft displacement per 5-frame window (px)
        # P9 fix 2026-05-29: frame_idx is RAW frames, so debounce must be raw too.
        # Prior `int(fps / stride)` evaluated to ~10 -> max(15,10)=15 raw frames = 0.5s,
        # not the documented 1s. Measured 63K cuts across 38 games (1660/game) vs
        # NBA-typical 100-200/game. Raise debounce to 2s (60 raw @ 30fps) to align with
        # genuine NBA off-ball cuts (which space at 3-5s minimum).
        DEBOUNCE = int(2.0 * self._fps)

        for t in frame_tracks:
            if t.get("team") == "referee" or t["player_id"] in possessors:
                continue
            if frame_idx - self._cut_last.get(t["player_id"], -999) < DEBOUNCE:
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
            if cos_a < -0.3 and self._toward_basket(v2x, v2y, pts[-1][1], pts[-1][2]):
                self.events.append(
                    {"type": "cut", "player_id": t["player_id"], "frame": frame_idx}
                )
                self._cut_last[t["player_id"]] = frame_idx

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
                self._drive_miss[pid] = 0
            else:
                # P22: tolerate brief dips — keep an active streak alive for up to
                # _DRIVE_MISS_TOL sub-threshold frames; only finalize once exceeded.
                if self._drive_streak.get(pid, 0) > 0:
                    self._drive_miss[pid] += 1
                    if self._drive_miss[pid] <= self._DRIVE_MISS_TOL:
                        continue
                    if self._drive_streak.get(pid, 0) >= 5:
                        sx, _ = self._drive_start.get(pid, (x, x))
                        self.events.append({
                            "type": "drive", "player_id": pid,
                            "start_x": float(sx), "end_x": float(x),
                        })
                    self._drive_streak[pid] = 0
                    self._drive_miss[pid] = 0

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
            # R10: widen lookback 10 frames → 1.5s window. Closeouts complete
            # 5-30 frames AFTER release; the 10-frame fixed window was ~1s at
            # stride=3 and missed nearly every legitimate closeout.
            _lookback = max(5, int(1.5 * self._fps / max(1, self._stride)))
            dist_now  = float(np.hypot(pts[-1][1] - sx, pts[-1][2] - sy))
            _idx_then = -min(_lookback, len(pts))
            dist_then = float(np.hypot(pts[_idx_then][1] - sx,
                                       pts[_idx_then][2] - sy))
            # P8 (2026-05-29): original criterion `dist_then > 8ft AND dist_now < 4ft`
            # was so tight that 0 closeout events were emitted across 38 games (vs
            # NBA reality where ~20-30% of perimeter shots have a defender closeout).
            # Two paths now:
            #   (a) STRICT: defender was beyond FAR and is now inside NEAR (preserved)
            #   (b) DELTA:  defender closed at least 3 ft AND is now within 6 ft of
            #               shooter (catches the more common 7ft→4ft closeout pattern)
            _strict = dist_then > self._CLOSEOUT_FAR and dist_now < self._CLOSEOUT_NEAR
            _delta_ft = (dist_then - dist_now) / max(1.0, self._ft)
            _now_ft   = dist_now / max(1.0, self._ft)
            _delta_path = _delta_ft >= 3.0 and _now_ft <= 6.0
            if _strict or _delta_path:
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

    # ── R16: missing event detectors (steal / block / rebound / post_up) ───

    def _detect_steal(
        self, frame_idx: int, victim_id: int, thief_id: int
    ) -> bool:
        """Return True (and append a "steal" event) when possession flipped to
        a defender who closed in from >6 ft within the last 8 processed frames.

        Conditions:
          1. Thief and victim are on different teams (defensive takeaway).
          2. Thief was ≥6 ft away within the last 8 frames (approached fast).
          3. Ball velocity at takeaway ≥ _PASS_MIN_VEL (not a passive pickup).
          4. Per-pair debounce of 1.0s prevents the same flip firing twice.
        """
        t_team = self._team_of.get(thief_id, "")
        v_team = self._team_of.get(victim_id, "")
        if not t_team or not v_team or t_team == v_team or "referee" in (t_team, v_team):
            return False

        thief_hist = self._phist.get(thief_id)
        victim_hist = self._phist.get(victim_id)
        if not thief_hist or not victim_hist or len(thief_hist) < 2:
            return False

        # Closure check: thief was >6 ft from victim somewhere in the last 8
        # processed frames AND is now within steal range.
        tx_now, ty_now = thief_hist[-1][1], thief_hist[-1][2]
        vx_now, vy_now = victim_hist[-1][1], victim_hist[-1][2]
        STEAL_RANGE = 6.0 * self._ft
        CLOSE_FROM  = 6.0 * self._ft

        # P10 fix 2026-05-29: lookback was `min(8, ...)` = 0.8s @ stride=3 fps=30.
        # Steals 97/38 games = 2.5/game vs NBA reality ~8/game. Widen to ~1.5s
        # (15 processed frames @ stride=3 fps=30) to catch closeouts that develop
        # over a longer approach. Debounce already prevents double-counting.
        _LOOKBACK = max(8, int(1.5 * self._fps / max(1, self._stride)))
        lookback = list(thief_hist)[-min(_LOOKBACK, len(thief_hist)):]
        # Match each thief sample to the closest-in-time victim sample.
        vlist = list(victim_hist)
        was_far = False
        for f_t, xt, yt, _ in lookback:
            # nearest victim sample by frame index
            closest = min(vlist, key=lambda v: abs(v[0] - f_t))
            d_then = float(np.hypot(xt - closest[1], yt - closest[2]))
            if d_then > CLOSE_FROM:
                was_far = True
                break
        if not was_far:
            return False

        d_now = float(np.hypot(tx_now - vx_now, ty_now - vy_now))
        if d_now > STEAL_RANGE:
            return False

        # Ball must have been moving (not a quiet floor pickup).
        if self._ball_vel < _PASS_MIN_VEL:
            return False

        # Debounce per (thief, victim) pair — 1.0s of processed frames.
        deb = max(15, int(1.0 * self._fps / max(1, self._stride)))
        key = (thief_id, victim_id)
        if frame_idx - self._steal_last.get(key, -10_000) < deb:
            return False
        self._steal_last[key] = frame_idx

        self.events.append({
            "type":      "steal",
            "frame":     frame_idx,
            "thief_id":  thief_id,
            "victim_id": victim_id,
            "thief_team":  t_team,
            "victim_team": v_team,
        })
        return True

    def _detect_block(
        self,
        frame_idx: int,
        frame_tracks: List[dict],
        ball_pos: Optional[Tuple[float, float]],
    ) -> None:
        """Append a "block" event when a defender is within 3 ft of the shooter
        at release AND the ball direction reverses sharply (cos < -0.5) within
        the next 8 processed frames.

        Called on the same frame as the shot.  The reversal check uses the
        ball velocity history available in `_ball_buf`: we compare the pre-shot
        direction (entries before frame_idx) against the immediate post-shot
        direction (entries at/after frame_idx).
        """
        # Debounce: at most one block per 1.0s.
        deb = max(15, int(1.0 * self._fps / max(1, self._stride)))
        if frame_idx - self._block_last < deb:
            return

        shooter_id = self._last_shot_shooter if self._last_shot_shooter is not None \
                     else self._possessor
        if shooter_id is None:
            return
        shooter_team = self._team_of.get(shooter_id, "")
        if not shooter_team or shooter_team == "referee":
            return
        shist = self._phist.get(shooter_id)
        if not shist:
            return
        sx, sy = shist[-1][1], shist[-1][2]

        # Find a defender (opposite team) within 3 ft of the shooter at release.
        BLOCK_RANGE = 3.0 * self._ft
        blocker = None
        for t in frame_tracks:
            team = t.get("team", "")
            if team == shooter_team or team == "referee":
                continue
            pid = t["player_id"]
            if pid == shooter_id:
                continue
            d = float(np.hypot(float(t.get("x2d", 0)) - sx,
                               float(t.get("y2d", 0)) - sy))
            if d <= BLOCK_RANGE:
                blocker = (pid, team, d)
                break
        if blocker is None:
            return

        # Direction-reversal check using recent ball trajectory in _ball_buf.
        # Need at least 4 samples spanning before/after the shot.
        buf = list(self._ball_buf)
        if len(buf) < 4:
            return
        # pre-shot direction: last 3 samples ending at-or-before frame_idx
        pre = [b for b in buf if b[0] <= frame_idx][-3:]
        # post-shot direction: first 3 samples at-or-after frame_idx
        post = [b for b in buf if b[0] >= frame_idx][:3]
        if len(pre) < 2 or len(post) < 2:
            # Not enough post-shot samples yet — fall back to ball_pos vs prev_ball.
            if ball_pos is None or self._prev_ball is None:
                return
            pre_dx = ball_pos[0] - self._prev_ball[0]
            pre_dy = ball_pos[1] - self._prev_ball[1]
            # No post-direction available yet → defer.
            # (Block will simply not fire on this exact frame; that's acceptable.)
            return
        pre_dx = pre[-1][1] - pre[0][1]
        pre_dy = pre[-1][2] - pre[0][2]
        post_dx = post[-1][1] - post[0][1]
        post_dy = post[-1][2] - post[0][2]
        pre_mag = float(np.hypot(pre_dx, pre_dy))
        post_mag = float(np.hypot(post_dx, post_dy))
        if pre_mag < 1e-3 or post_mag < 1e-3:
            return
        cos_a = (pre_dx * post_dx + pre_dy * post_dy) / (pre_mag * post_mag + 1e-9)
        if cos_a >= -0.5:
            return

        pid, team, d = blocker
        self._block_last = frame_idx
        self.events.append({
            "type":          "block",
            "frame":         frame_idx,
            "blocker_id":    pid,
            "blocker_team":  team,
            "shooter_id":    shooter_id,
            "shooter_team":  shooter_team,
            "blocker_dist":  round(d, 1),
        })

    def _register_pending_shot(
        self,
        frame_idx: int,
        frame_tracks: List[dict],
        ball_pos: Optional[Tuple[float, float]],
    ) -> None:
        """Queue a shot so _detect_rebound can resolve it ~30 frames later."""
        shooter_id = self._last_shot_shooter if self._last_shot_shooter is not None \
                     else self._possessor
        if shooter_id is None:
            return
        shooter_team = self._team_of.get(shooter_id, "")
        if not shooter_team or shooter_team == "referee":
            return
        bx, by = ball_pos if ball_pos is not None else (self.map_w / 2, self.map_h / 2)
        basket = self._nearest_basket(float(bx), float(by))
        self._pending_shots.append({
            "shot_frame":   frame_idx,
            "shooter_id":   shooter_id,
            "shooter_team": shooter_team,
            "basket":       basket,
        })

    def _detect_rebound(
        self,
        frame_idx: int,
        frame_tracks: List[dict],
        ball_pos: Optional[Tuple[float, float]],
    ) -> None:
        """Resolve a pending shot ~1s after release: find the closest player to
        the ball, classify offensive vs defensive based on team match with shooter.

        Fires once per shot — drains the entry from _pending_shots on emit
        (or after a hard timeout to avoid leaks).
        """
        if not self._pending_shots:
            return
        # 30 source-frames after the shot in PROCESSED frames.
        target_lag = max(10, int(30.0 / max(1, self._stride)))
        # Hard timeout: 5s in processed frames — abandon unresolved shots.
        timeout = max(60, int(5.0 * self._fps / max(1, self._stride)))

        keep: List[dict] = []
        for shot in self._pending_shots:
            age = frame_idx - shot["shot_frame"]
            if age < target_lag:
                keep.append(shot)
                continue
            if age > timeout:
                # Drop — don't keep, don't emit.
                continue
            if frame_idx == shot["shot_frame"]:
                keep.append(shot)
                continue

            # Resolve: find the player closest to the ball (or to the basket
            # when ball is missing) and classify by team.
            ref_x, ref_y = (
                (float(ball_pos[0]), float(ball_pos[1]))
                if ball_pos is not None
                else (float(shot["basket"][0]), float(shot["basket"][1]))
            )
            best_pid: Optional[int] = None
            best_team: Optional[str] = None
            best_d = float("inf")
            MAX_RANGE = 12.0 * self._ft  # ignore players >12 ft from ball
            for t in frame_tracks:
                team = t.get("team", "")
                if team == "referee" or not team:
                    continue
                d = float(np.hypot(float(t.get("x2d", 0)) - ref_x,
                                   float(t.get("y2d", 0)) - ref_y))
                if d < best_d:
                    best_d = d
                    best_pid = t["player_id"]
                    best_team = team
            if best_pid is None or best_d > MAX_RANGE:
                # No nearby player — emit "team rebound" (loose), don't refire.
                self.events.append({
                    "type":       "rebound",
                    "subtype":    "team_rebound",
                    "frame":      frame_idx,
                    "shot_frame": shot["shot_frame"],
                    "shooter_id": shot["shooter_id"],
                    "player_id":  None,
                    "team":       None,
                })
                self._rebound_last_shot = shot["shot_frame"]
                continue

            subtype = (
                "offensive_rebound"
                if best_team == shot["shooter_team"]
                else "defensive_rebound"
            )
            self.events.append({
                "type":       "rebound",
                "subtype":    subtype,
                "frame":      frame_idx,
                "shot_frame": shot["shot_frame"],
                "shooter_id": shot["shooter_id"],
                "player_id":  best_pid,
                "team":       best_team,
                "dist_to_ball": round(best_d, 1),
            })
            self._rebound_last_shot = shot["shot_frame"]

        self._pending_shots = keep

    def _detect_post_up(
        self, frame_idx: int, frame_tracks: List[dict]
    ) -> None:
        """Emit "post_up" when the ball-handler stays within 8 ft of the basket
        for ≥2.0s, with vtb < 0 (backing down — moving AWAY from basket) AND an
        opponent defender within 5 ft.

        Streak is accumulated in _post_up_streak[handler_id]; resets the moment
        the handler breaks any of the gates.  Debounce: one post_up per handler
        per 5.0s once they qualify.
        """
        POST_DIST = 8.0 * self._ft       # within 8 ft of basket
        DEF_DIST  = 5.0 * self._ft       # opponent within 5 ft
        STREAK    = max(30, int(2.0 * self._fps / max(1, self._stride)))
        DEBOUNCE  = max(STREAK * 2, int(5.0 * self._fps / max(1, self._stride)))

        active_handlers = set()
        for t in frame_tracks:
            if not t.get("has_ball"):
                continue
            team = t.get("team", "")
            if not team or team == "referee":
                continue
            pid = t["player_id"]
            active_handlers.add(pid)

            x = float(t.get("x2d", 0))
            y = float(t.get("y2d", 0))
            bx, by = self._nearest_basket(x, y)
            d_basket = float(np.hypot(x - bx, y - by))

            # Velocity toward basket (negative = backing AWAY).
            hist = self._phist.get(pid)
            vtb = 0.0
            if hist and len(hist) >= 2:
                px, py = hist[-2][1], hist[-2][2]
                dx, dy = x - px, y - py
                nb = self._nearest_basket(x, y)
                dbx, dby = nb[0] - x, nb[1] - y
                nd = float(np.hypot(dbx, dby)) + 1e-6
                vtb = (dx * dbx + dy * dby) / nd

            # Nearest opposing defender distance.
            min_def = float("inf")
            for o in frame_tracks:
                o_team = o.get("team", "")
                if o_team == team or o_team == "referee" or not o_team:
                    continue
                od = float(np.hypot(float(o.get("x2d", 0)) - x,
                                    float(o.get("y2d", 0)) - y))
                if od < min_def:
                    min_def = od

            if d_basket <= POST_DIST and vtb < 0.0 and min_def <= DEF_DIST:
                self._post_up_streak[pid] += 1
            else:
                self._post_up_streak[pid] = 0
                continue

            if self._post_up_streak[pid] >= STREAK:
                last = self._post_up_last.get(pid, -10_000)
                if frame_idx - last >= DEBOUNCE:
                    self._post_up_last[pid] = frame_idx
                    self.events.append({
                        "type":      "post_up",
                        "frame":     frame_idx,
                        "player_id": pid,
                        "team":      team,
                        "dist_to_basket": round(d_basket, 1),
                        "defender_dist":  round(min_def, 1),
                        "duration_frames": int(self._post_up_streak[pid]),
                    })
                    # Reset streak after firing so we require another 2s
                    # before the same player can fire again.
                    self._post_up_streak[pid] = 0

        # Reset streak for any handler who is no longer in possession.
        for pid in list(self._post_up_streak.keys()):
            if pid not in active_handlers:
                self._post_up_streak[pid] = 0
