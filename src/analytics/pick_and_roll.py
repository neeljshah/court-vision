"""Pick-and-roll detection from tracking frame sequences.

Identifies PnR events by examining a sliding window of frames: a slow player
(screener) within SCREEN_DISTANCE of a fast player (ball handler) in the middle
frame, followed by the handler moving away in the final frame.
Pure Python — no numpy or external dependencies.
"""

import math
from src.analytics.spatial_types import PickAndRollEvent

PNR_WINDOW_FRAMES: int = 5
SCREEN_DISTANCE: float = 6.0
SCREENER_MAX_SPEED: float = 3.0
HANDLER_MIN_SPEED: float = 8.0


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    dx = ax - bx
    dy = ay - by
    return math.sqrt(dx * dx + dy * dy)


def _get_player(frame: list[dict], track_id: int) -> dict | None:
    for p in frame:
        if p["track_id"] == track_id:
            return p
    return None


def detect_pick_and_roll(
    frame_sequence: list[list[dict]],
    game_id: str,
) -> list[PickAndRollEvent]:
    """Detect pick-and-roll events in a frame window.

    Args:
        frame_sequence: List of frames (each is a list of player state dicts).
            Must contain at least PNR_WINDOW_FRAMES frames.
        game_id: UUID string identifying the game.

    Returns:
        List of PickAndRollEvent instances. May be empty.
    """
    if len(frame_sequence) < PNR_WINDOW_FRAMES:
        return []

    window = frame_sequence[-PNR_WINDOW_FRAMES:]
    mid_idx = len(window) // 2
    mid_frame = window[mid_idx]
    last_frame = window[-1]

    handler_candidates = [p for p in mid_frame if p.get("speed", 0.0) > HANDLER_MIN_SPEED]
    screener_candidates = [p for p in mid_frame if p.get("speed", 0.0) < SCREENER_MAX_SPEED]

    if not handler_candidates or not screener_candidates:
        return []

    emitted_pairs: set[tuple[int, int]] = set()
    events: list[PickAndRollEvent] = []

    for handler in handler_candidates:
        h_id = handler["track_id"]
        hx, hy = handler["x"], handler["y"]

        close_screeners = [
            s for s in screener_candidates
            if s["track_id"] != h_id
            and _dist(hx, hy, s["x"], s["y"]) <= SCREEN_DISTANCE
        ]
        if not close_screeners:
            continue

        best_screener = min(close_screeners, key=lambda s: _dist(hx, hy, s["x"], s["y"]))
        s_id = best_screener["track_id"]
        pair = (h_id, s_id)
        if pair in emitted_pairs:
            continue

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
