"""Off-ball movement event detection for NBA tracking data.

Classifies per-player off-ball actions (cut, screen, drift) from the most
recent frame in a sliding window of player state dicts.
Pure Python — no external dependencies beyond standard library.
"""

import math
from src.analytics.spatial_types import OffBallEvent

# Detection thresholds (court-feet units; speed in ft/s)
# NBA reference: max sprint ~32 ft/s, hard cut ~14+ ft/s, screener ~0-3 ft/s

CUT_SPEED_THRESHOLD: float = 14.0
SCREEN_SPEED_THRESHOLD: float = 3.0
SCREEN_PROXIMITY: float = 5.0
DRIFT_SPEED_MIN: float = 4.0
DRIFT_SPEED_MAX: float = 10.0

_BASKET_X: float = 94.0


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    dx = ax - bx
    dy = ay - by
    return math.sqrt(dx * dx + dy * dy)


def _moving_toward_basket(player: dict) -> bool:
    vx: float = player.get("velocity_x", 0.0)
    return vx > 0.0


def _is_away_from_ball(player: dict, ball_pos: dict) -> bool:
    bpx = player["x"] - ball_pos["x"]
    bpy = player["y"] - ball_pos["y"]
    vx: float = player.get("velocity_x", 0.0)
    vy: float = player.get("velocity_y", 0.0)
    cross = bpx * vy - bpy * vx
    dot = bpx * vx + bpy * vy
    speed = player.get("speed", 0.0)
    if speed == 0.0:
        return False
    lateral_fraction = abs(cross) / (math.sqrt(bpx * bpx + bpy * bpy + 1e-9) * speed)
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
        frame_sequence: Sliding window of recent frames (only last frame used).
        game_id: UUID string identifying the game.
        ball_pos: Current ball position {'x': float, 'y': float} or None.

    Returns:
        List of OffBallEvent instances (may be empty).
    """
    if not frame_sequence:
        return []

    current_frame: list[dict] = frame_sequence[-1]
    if not current_frame:
        return []

    events: list[OffBallEvent] = []

    # Screen detection pre-pass
    screener_candidates: set[int] = set()
    for i, p in enumerate(current_frame):
        if p.get("speed", 0.0) >= SCREEN_SPEED_THRESHOLD:
            continue
        for j, q in enumerate(current_frame):
            if i == j:
                continue
            if q.get("speed", 0.0) <= SCREEN_SPEED_THRESHOLD:
                continue
            if _dist(p["x"], p["y"], q["x"], q["y"]) <= SCREEN_PROXIMITY:
                screener_candidates.add(p["track_id"])
                break

    # Per-player classification: cut > screen > drift
    for player in current_frame:
        speed: float = player.get("speed", 0.0)
        track_id: int = player["track_id"]
        frame_number: int = player.get("frame_number", 0)
        timestamp_ms: float = player.get("timestamp_ms", 0.0)

        event_type: str | None = None
        confidence: float = 0.0

        if speed > CUT_SPEED_THRESHOLD and _moving_toward_basket(player):
            event_type = "cut"
            confidence = min(1.0, speed / (CUT_SPEED_THRESHOLD * 2.0))
        elif track_id in screener_candidates:
            event_type = "screen"
            confidence = 0.8
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
