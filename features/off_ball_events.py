"""Off-ball movement event detection for NBA tracking data (FE-03).

Classifies per-player off-ball actions (cut, screen, drift) from the most
recent frame in a sliding window of player state dicts. No external dependencies
beyond the standard library.
"""

import math
from features.types import OffBallEvent

# ---------------------------------------------------------------------------
# Detection thresholds
# ---------------------------------------------------------------------------

CUT_SPEED_THRESHOLD: float = 200.0    # px/s — minimum speed to classify as cut
SCREEN_SPEED_THRESHOLD: float = 30.0  # px/s — maximum speed for screener candidate
SCREEN_PROXIMITY: float = 60.0        # px — maximum distance to a "faster" player for screen
DRIFT_SPEED_MIN: float = 30.0         # px/s — lower bound for drift speed range
DRIFT_SPEED_MAX: float = 100.0        # px/s — upper bound for drift speed range

# Right-side basket in standard pixel space; court-calibration deferred to future phase.
_BASKET_X: float = 470.0


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    """Euclidean distance between two 2-D points."""
    dx = ax - bx
    dy = ay - by
    return math.sqrt(dx * dx + dy * dy)


def _moving_toward_basket(player: dict) -> bool:
    """Return True when the player's net x-velocity is toward the right basket.

    'Toward basket' means the x-component of velocity is positive (moving right
    toward x=470). Players currently to the right of the basket are excluded.
    """
    vx: float = player.get("velocity_x", 0.0)
    return vx > 0.0


def _is_away_from_ball(player: dict, ball_pos: dict) -> bool:
    """Return True when the player is drifting laterally *away* from the ball.

    Strategy: compute the cross product of the ball-to-player vector and the
    velocity vector. A non-zero cross product indicates lateral motion relative
    to the ball-player axis. We additionally require the dot product is not
    strongly negative (i.e., the player isn't running directly toward the ball).

    For drift we need:
    - Speed in [DRIFT_SPEED_MIN, DRIFT_SPEED_MAX]  (checked by caller)
    - Player is moving with a lateral component away from the ball

    The cross product |bp × v| > 0 ensures meaningful lateral motion.
    We also check the dot product to exclude cases where the player is
    heading straight toward the ball (which would be a pass-cut, not drift).
    """
    bpx = player["x"] - ball_pos["x"]
    bpy = player["y"] - ball_pos["y"]
    vx: float = player.get("velocity_x", 0.0)
    vy: float = player.get("velocity_y", 0.0)

    # 2-D cross product magnitude (scalar z-component)
    cross = bpx * vy - bpy * vx
    # Dot product of ball-to-player and velocity
    dot = bpx * vx + bpy * vy

    speed = player.get("speed", 0.0)
    if speed == 0.0:
        return False

    # Require meaningful lateral component: |cross| / speed > 0.3 (30% of motion is lateral)
    lateral_fraction = abs(cross) / (math.sqrt(bpx * bpx + bpy * bpy + 1e-9) * speed)

    # Player moving away from or laterally relative to ball (dot >= -speed/2 excludes
    # strong approach toward ball)
    moving_toward_ball = dot < -(speed * 0.5 * math.sqrt(bpx * bpx + bpy * bpy + 1e-9))
    if moving_toward_ball:
        return False

    return lateral_fraction > 0.3


def detect_off_ball_events(
    frame_sequence: list[list[dict]],
    game_id: str,
    ball_pos: dict | None,
) -> list[OffBallEvent]:
    """Detect off-ball movement events in the most recent frame of a sequence.

    Classification priority (highest → lowest): cut > screen > drift.
    At most one event is emitted per player per call.

    Args:
        frame_sequence: Sliding window of recent frames. Each element is a list of
            player state dicts for that frame. Only ``frame_sequence[-1]`` is used.
        game_id: UUID string identifying the game.
        ball_pos: Current ball position ``{'x': float, 'y': float}`` or ``None``.

    Returns:
        List of ``OffBallEvent`` instances (may be empty).
    """
    if not frame_sequence:
        return []

    current_frame: list[dict] = frame_sequence[-1]
    if not current_frame:
        return []

    events: list[OffBallEvent] = []

    # --- Screen detection pre-pass: for each player, find if a *meaningfully*
    #     faster player is within SCREEN_PROXIMITY. "Meaningfully faster" means
    #     the nearby player's speed exceeds SCREEN_SPEED_THRESHOLD (i.e., it is
    #     itself moving, not just slightly less stationary). O(n²) — typical
    #     NBA frame has ≤10 players.
    screener_candidates: set[int] = set()
    for i, p in enumerate(current_frame):
        p_speed = p.get("speed", 0.0)
        if p_speed >= SCREEN_SPEED_THRESHOLD:
            continue  # too fast to be a screener
        for j, q in enumerate(current_frame):
            if i == j:
                continue
            q_speed = q.get("speed", 0.0)
            # The nearby player must be actively moving (above threshold), not
            # just relatively faster than the (also slow) screener candidate.
            if q_speed <= SCREEN_SPEED_THRESHOLD:
                continue
            dist = _dist(p["x"], p["y"], q["x"], q["y"])
            if dist <= SCREEN_PROXIMITY:
                screener_candidates.add(p["track_id"])
                break

    # --- Per-player classification with priority: cut > screen > drift
    for player in current_frame:
        speed: float = player.get("speed", 0.0)
        track_id: int = player["track_id"]
        frame_number: int = player.get("frame_number", 0)
        timestamp_ms: float = player.get("timestamp_ms", 0.0)

        event_type: str | None = None
        confidence: float = 0.0

        # Priority 1: Cut
        if speed > CUT_SPEED_THRESHOLD and _moving_toward_basket(player):
            event_type = "cut"
            # Confidence proportional to speed, capped at 1.0
            confidence = min(1.0, speed / (CUT_SPEED_THRESHOLD * 2.0))

        # Priority 2: Screen
        elif track_id in screener_candidates:
            event_type = "screen"
            confidence = 0.8

        # Priority 3: Drift
        elif DRIFT_SPEED_MIN <= speed <= DRIFT_SPEED_MAX and ball_pos is not None:
            if _is_away_from_ball(player, ball_pos):
                event_type = "drift"
                confidence = 0.6

        if event_type is not None:
            events.append(
                OffBallEvent(
                    game_id=game_id,
                    track_id=track_id,
                    frame_number=frame_number,
                    event_type=event_type,
                    confidence=confidence,
                    timestamp_ms=timestamp_ms,
                )
            )

    return events
