"""Pick-and-roll detection from tracking frame sequences (FE-04).

Identifies PnR events by examining a sliding window of frames: a slow player
(screener) within SCREEN_DISTANCE of a fast player (ball handler) in the middle
frame, followed by the handler moving away (distance > SCREEN_DISTANCE) in the
final frame. Pure Python — no numpy or external dependencies.
"""

import math
from features.types import PickAndRollEvent

# ---------------------------------------------------------------------------
# Detection constants
# ---------------------------------------------------------------------------

PNR_WINDOW_FRAMES: int = 5       # minimum frames needed to detect a PnR
SCREEN_DISTANCE: float = 80.0    # px — handler-screener max proximity at contact
SCREENER_MAX_SPEED: float = 40.0 # px/s — screener must be slower than this
HANDLER_MIN_SPEED: float = 80.0  # px/s — ball handler must be faster than this


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    """Euclidean distance between two 2-D points."""
    dx = ax - bx
    dy = ay - by
    return math.sqrt(dx * dx + dy * dy)


def _get_player(frame: list[dict], track_id: int) -> dict | None:
    """Return the player dict with the given track_id from a frame, or None."""
    for p in frame:
        if p["track_id"] == track_id:
            return p
    return None


def detect_pick_and_roll(
    frame_sequence: list[list[dict]],
    game_id: str,
) -> list[PickAndRollEvent]:
    """Detect pick-and-roll events in a frame window.

    Algorithm:
    1. Require at least ``PNR_WINDOW_FRAMES`` frames; return ``[]`` otherwise.
    2. Identify handler candidates (speed > HANDLER_MIN_SPEED) and screener
       candidates (speed < SCREENER_MAX_SPEED) in the middle frame.
    3. For each handler-screener pair where the distance at the middle frame is
       within SCREEN_DISTANCE, check that they are more than SCREEN_DISTANCE
       apart in the last frame (handler moved off the screen).
    4. When multiple screeners qualify for the same handler, keep the closest
       one in the middle frame.
    5. Deduplicate: emit at most one event per (handler, screener) pair per call.

    Args:
        frame_sequence: List of frames (each is a list of player state dicts).
            Must contain at least ``PNR_WINDOW_FRAMES`` frames.
        game_id: UUID string identifying the game.

    Returns:
        List of ``PickAndRollEvent`` instances. May be empty.
    """
    if len(frame_sequence) < PNR_WINDOW_FRAMES:
        return []

    # Use only the last PNR_WINDOW_FRAMES frames
    window = frame_sequence[-PNR_WINDOW_FRAMES:]
    mid_idx = len(window) // 2
    mid_frame = window[mid_idx]
    last_frame = window[-1]

    # Collect candidate handler and screener track IDs from the middle frame
    handler_candidates: list[dict] = [
        p for p in mid_frame if p.get("speed", 0.0) > HANDLER_MIN_SPEED
    ]
    screener_candidates: list[dict] = [
        p for p in mid_frame if p.get("speed", 0.0) < SCREENER_MAX_SPEED
    ]

    if not handler_candidates or not screener_candidates:
        return []

    emitted_pairs: set[tuple[int, int]] = set()
    events: list[PickAndRollEvent] = []

    for handler in handler_candidates:
        h_id = handler["track_id"]
        hx, hy = handler["x"], handler["y"]

        # Find all screeners within SCREEN_DISTANCE at middle frame
        close_screeners = [
            s for s in screener_candidates
            if s["track_id"] != h_id
            and _dist(hx, hy, s["x"], s["y"]) <= SCREEN_DISTANCE
        ]

        if not close_screeners:
            continue

        # Pick the closest screener to the handler
        best_screener = min(
            close_screeners,
            key=lambda s: _dist(hx, hy, s["x"], s["y"]),
        )
        s_id = best_screener["track_id"]

        # Deduplicate
        pair = (h_id, s_id)
        if pair in emitted_pairs:
            continue

        # Verify separation in last frame: handler must be > SCREEN_DISTANCE from screener
        handler_last = _get_player(last_frame, h_id)
        screener_last = _get_player(last_frame, s_id)

        if handler_last is None or screener_last is None:
            continue

        separation = _dist(
            handler_last["x"], handler_last["y"],
            screener_last["x"], screener_last["y"],
        )
        if separation <= SCREEN_DISTANCE:
            continue

        # PnR confirmed — record from middle frame metadata
        emitted_pairs.add(pair)
        events.append(
            PickAndRollEvent(
                game_id=game_id,
                ball_handler_track_id=h_id,
                screener_track_id=s_id,
                frame_number=mid_frame[0]["frame_number"] if mid_frame else mid_idx,
                timestamp_ms=mid_frame[0]["timestamp_ms"] if mid_frame else float(mid_idx * 100),
            )
        )

    return events
