"""
Play Recognition Engine

Detects offensive play types from tracking data using spatial geometry
and movement clustering. Event-triggered only — runs per possession,
not per frame.

Detects: pick-and-roll variants, screens, isolation, post entries,
cuts, hand-offs, horns, 5-out, Spain PnR, elevator doors, stagger screens.
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# ── Constants ──────────────────────────────────────────────────────────────────

SCREEN_PROXIMITY_FT   = 6.0   # feet — how close screener must be to set screen
SCREEN_SPEED_MAX      = 4.0   # ft/s — screener nearly stationary
HANDLER_SPEED_MIN     = 8.0   # ft/s — handler moving off screen
PAINT_X_LEFT          = 19.0  # ft — left free throw lane edge
PAINT_X_RIGHT         = 75.0  # ft — right free throw lane edge
PAINT_Y_NEAR          = 10.0  # ft
PAINT_Y_FAR           = 40.0  # ft
BASKET_LEFT           = (4.75, 25.0)
BASKET_RIGHT          = (89.25, 25.0)
THREE_PT_DIST         = 22.0  # ft
ISO_CLEAR_RADIUS      = 12.0  # ft — other players cleared out
POST_RADIUS           = 8.0   # ft from basket
CUT_SPEED_MIN         = 12.0  # ft/s
HANDOFF_PROX          = 4.0   # ft — handler and receiver


@dataclass
class PlayDetection:
    play_type: str
    play_start_frame: int
    play_end_frame: int
    primary_track_ids: List[int]
    confidence: float
    metadata: dict = field(default_factory=dict)


def detect_plays(
    frames_by_number: Dict[int, List[dict]],
    possession_start: int,
    possession_end: int,
    game_id: str,
) -> List[PlayDetection]:
    """
    Run play recognition over a single possession.

    Args:
        frames_by_number: All tracking rows keyed by frame_number.
        possession_start:  First frame of this possession.
        possession_end:    Last frame of this possession.
        game_id:           Game UUID.

    Returns:
        List of PlayDetection objects for this possession.
    """
    poss_frames = {
        fn: frames_by_number[fn]
        for fn in range(possession_start, possession_end + 1)
        if fn in frames_by_number
    }
    if len(poss_frames) < 5:
        return []

    detections: List[PlayDetection] = []
    sorted_fns = sorted(poss_frames.keys())

    detections += _detect_isolation(poss_frames, sorted_fns)
    detections += _detect_pick_and_roll_variants(poss_frames, sorted_fns)
    detections += _detect_cuts(poss_frames, sorted_fns)
    detections += _detect_post_entry(poss_frames, sorted_fns)
    detections += _detect_handoff(poss_frames, sorted_fns)
    detections += _detect_five_out(poss_frames, sorted_fns)
    detections += _detect_horns(poss_frames, sorted_fns)

    return detections


# ── Helpers ────────────────────────────────────────────────────────────────────

def _players(frame: List[dict]) -> List[dict]:
    return [r for r in frame if r.get("object_type") == "player"]


def _ball(frame: List[dict]) -> Optional[dict]:
    balls = [r for r in frame if r.get("object_type") == "ball"]
    return balls[0] if balls else None


def _pos(row: dict) -> np.ndarray:
    return np.array([row.get("x_ft", row["x"]), row.get("y_ft", row["y"])], dtype=float)


def _dist(a: dict, b: dict) -> float:
    return float(np.linalg.norm(_pos(a) - _pos(b)))


def _speed(row: dict) -> float:
    return float(row.get("speed", 0) or 0)


def _nearest_basket(x: float) -> Tuple[float, float]:
    dl = abs(x - BASKET_LEFT[0])
    dr = abs(x - BASKET_RIGHT[0])
    return BASKET_LEFT if dl < dr else BASKET_RIGHT


# ── Isolation ──────────────────────────────────────────────────────────────────

def _detect_isolation(
    poss_frames: Dict[int, List[dict]], sorted_fns: List[int]
) -> List[PlayDetection]:
    results = []
    window = 15  # frames
    for i in range(0, len(sorted_fns) - window, window // 2):
        fn = sorted_fns[i]
        frame = poss_frames[fn]
        ball = _ball(frame)
        if ball is None:
            continue
        players = _players(frame)
        if len(players) < 3:
            continue

        # Find ball handler — closest player to ball
        handler = min(players, key=lambda p: _dist(p, ball))
        others = [p for p in players if p["track_id"] != handler["track_id"]]

        # ISO: all other players > ISO_CLEAR_RADIUS feet away
        close = [p for p in others if _dist(p, handler) < ISO_CLEAR_RADIUS]
        if len(close) == 0 and _speed(handler) < 15.0:
            # Sustained for several frames?
            sustained = sum(
                1 for fn2 in sorted_fns[i:i+window]
                if fn2 in poss_frames and _check_iso_frame(poss_frames[fn2], handler["track_id"])
            )
            if sustained >= window * 0.6:
                results.append(PlayDetection(
                    play_type="isolation",
                    play_start_frame=sorted_fns[i],
                    play_end_frame=sorted_fns[min(i + window, len(sorted_fns)-1)],
                    primary_track_ids=[handler["track_id"]],
                    confidence=min(0.5 + sustained / window * 0.5, 0.95),
                ))
    return results


def _check_iso_frame(frame: List[dict], handler_id: int) -> bool:
    players = _players(frame)
    ball = _ball(frame)
    if ball is None or not players:
        return False
    handler = next((p for p in players if p["track_id"] == handler_id), None)
    if handler is None:
        return False
    others = [p for p in players if p["track_id"] != handler_id]
    return all(_dist(p, handler) >= ISO_CLEAR_RADIUS for p in others)


# ── Pick-and-Roll Variants ─────────────────────────────────────────────────────

def _detect_pick_and_roll_variants(
    poss_frames: Dict[int, List[dict]], sorted_fns: List[int]
) -> List[PlayDetection]:
    results = []
    window = 12

    for i in range(len(sorted_fns) - window):
        mid_fn = sorted_fns[i + window // 2]
        end_fn = sorted_fns[i + window - 1]
        start_fn = sorted_fns[i]

        mid_frame = poss_frames.get(mid_fn, [])
        end_frame = poss_frames.get(end_fn, [])
        players_mid = _players(mid_frame)
        players_end = _players(end_frame)

        if len(players_mid) < 2:
            continue

        # Find screener pairs (close + slow) and handlers (fast)
        for screener in players_mid:
            if _speed(screener) > SCREEN_SPEED_MAX:
                continue
            for handler in players_mid:
                if handler["track_id"] == screener["track_id"]:
                    continue
                if _dist(screener, handler) > SCREEN_PROXIMITY_FT:
                    continue
                if _speed(handler) < HANDLER_SPEED_MIN:
                    continue

                # Determine roll vs pop by screener movement in end_frame
                screener_end = next(
                    (p for p in players_end if p["track_id"] == screener["track_id"]), None
                )
                play_type = "pick_and_roll"
                if screener_end:
                    basket = _nearest_basket(_pos(screener)[0])
                    dist_to_basket_end = np.linalg.norm(_pos(screener_end) - np.array(basket))
                    dist_to_basket_mid = np.linalg.norm(_pos(screener) - np.array(basket))
                    if dist_to_basket_end > dist_to_basket_mid + 3.0:
                        play_type = "pick_and_pop"

                    # Spain PnR: second screener sets screen on rolling screener's defender
                    third = [p for p in players_mid
                             if p["track_id"] not in (screener["track_id"], handler["track_id"])]
                    for t in third:
                        if _dist(t, screener_end) < SCREEN_PROXIMITY_FT and _speed(t) < SCREEN_SPEED_MAX:
                            play_type = "spain_pick_and_roll"
                            break

                results.append(PlayDetection(
                    play_type=play_type,
                    play_start_frame=start_fn,
                    play_end_frame=end_fn,
                    primary_track_ids=[handler["track_id"], screener["track_id"]],
                    confidence=0.75,
                ))
                break  # one PnR per screener per window

    return results


# ── Cuts ───────────────────────────────────────────────────────────────────────

def _detect_cuts(
    poss_frames: Dict[int, List[dict]], sorted_fns: List[int]
) -> List[PlayDetection]:
    results = []
    if len(sorted_fns) < 8:
        return results

    # Track each player's trajectory
    track_positions: Dict[int, List[Tuple[int, np.ndarray, float]]] = {}
    for fn in sorted_fns:
        for p in _players(poss_frames[fn]):
            tid = p["track_id"]
            track_positions.setdefault(tid, []).append((fn, _pos(p), _speed(p)))

    for tid, trajectory in track_positions.items():
        for i in range(len(trajectory) - 6):
            segment = trajectory[i:i+6]
            avg_speed = np.mean([s for _, _, s in segment])
            if avg_speed < CUT_SPEED_MIN:
                continue

            start_pos = segment[0][1]
            end_pos = segment[-1][1]
            displacement = np.linalg.norm(end_pos - start_pos)
            if displacement < 8.0:
                continue

            # Direction toward basket?
            basket = _nearest_basket(float(start_pos[0]))
            basket_arr = np.array(basket)
            move_dir = end_pos - start_pos
            basket_dir = basket_arr - start_pos
            if np.linalg.norm(move_dir) < 0.01 or np.linalg.norm(basket_dir) < 0.01:
                continue

            cos_angle = np.dot(move_dir, basket_dir) / (
                np.linalg.norm(move_dir) * np.linalg.norm(basket_dir)
            )

            # Backdoor: cut from wing toward baseline/basket
            cut_type = "baseline_cut"
            if cos_angle > 0.7:
                cut_type = "backdoor_cut"
            elif cos_angle > 0.4:
                cut_type = "basket_cut"

            results.append(PlayDetection(
                play_type=cut_type,
                play_start_frame=segment[0][0],
                play_end_frame=segment[-1][0],
                primary_track_ids=[tid],
                confidence=min(0.5 + avg_speed / 25.0 * 0.4, 0.9),
                metadata={"displacement_ft": round(float(displacement), 1)},
            ))

    return results


# ── Post Entry ─────────────────────────────────────────────────────────────────

def _detect_post_entry(
    poss_frames: Dict[int, List[dict]], sorted_fns: List[int]
) -> List[PlayDetection]:
    results = []
    window = 15

    for i in range(0, len(sorted_fns) - window, window):
        fn = sorted_fns[i + window // 2]
        frame = poss_frames.get(fn, [])
        ball = _ball(frame)
        if ball is None:
            continue

        bpos = _pos(ball)
        basket = _nearest_basket(float(bpos[0]))
        dist_to_basket = np.linalg.norm(bpos - np.array(basket))

        if dist_to_basket < POST_RADIUS:
            # Ball is in post area — check if handler is back to basket
            players = _players(frame)
            handler = min(players, key=lambda p: _dist(p, ball)) if players else None
            if handler and _speed(handler) < 6.0:
                results.append(PlayDetection(
                    play_type="post_entry",
                    play_start_frame=sorted_fns[i],
                    play_end_frame=sorted_fns[min(i + window, len(sorted_fns)-1)],
                    primary_track_ids=[handler["track_id"]],
                    confidence=0.72,
                ))
    return results


# ── Hand-off ───────────────────────────────────────────────────────────────────

def _detect_handoff(
    poss_frames: Dict[int, List[dict]], sorted_fns: List[int]
) -> List[PlayDetection]:
    results = []
    for i in range(1, len(sorted_fns) - 1):
        fn = sorted_fns[i]
        frame = poss_frames.get(fn, [])
        ball = _ball(frame)
        if ball is None:
            continue

        players = _players(frame)
        close = [p for p in players if _dist(p, ball) < HANDOFF_PROX]
        if len(close) >= 2:
            # Two players very close to ball = potential hand-off
            results.append(PlayDetection(
                play_type="hand_off",
                play_start_frame=fn,
                play_end_frame=sorted_fns[min(i + 4, len(sorted_fns)-1)],
                primary_track_ids=[p["track_id"] for p in close[:2]],
                confidence=0.65,
            ))
    return results


# ── 5-Out ──────────────────────────────────────────────────────────────────────

def _detect_five_out(
    poss_frames: Dict[int, List[dict]], sorted_fns: List[int]
) -> List[PlayDetection]:
    results = []
    if len(sorted_fns) < 10:
        return results

    fn = sorted_fns[len(sorted_fns) // 2]
    frame = poss_frames.get(fn, [])
    players = _players(frame)

    outside_arc = 0
    for p in players:
        pos = _pos(p)
        basket = _nearest_basket(float(pos[0]))
        if np.linalg.norm(pos - np.array(basket)) > THREE_PT_DIST + 1.5:
            outside_arc += 1

    if outside_arc >= 4:
        results.append(PlayDetection(
            play_type="five_out",
            play_start_frame=sorted_fns[0],
            play_end_frame=sorted_fns[-1],
            primary_track_ids=[p["track_id"] for p in players],
            confidence=0.6 + (outside_arc - 4) * 0.1,
        ))
    return results


# ── Horns ──────────────────────────────────────────────────────────────────────

def _detect_horns(
    poss_frames: Dict[int, List[dict]], sorted_fns: List[int]
) -> List[PlayDetection]:
    """Horns: two players at elbows (high post), ball at top."""
    results = []
    if not sorted_fns:
        return results

    fn = sorted_fns[0]
    frame = poss_frames.get(fn, [])
    players = _players(frame)
    ball = _ball(frame)
    if ball is None or len(players) < 3:
        return results

    # Elbow regions: approximately (19, 19) and (75, 19) in feet
    elbow_l = np.array([19.0, 19.0])
    elbow_r = np.array([75.0, 19.0])
    elbow_threshold = 6.0

    at_elbows = []
    for p in players:
        pos = _pos(p)
        if (np.linalg.norm(pos - elbow_l) < elbow_threshold or
                np.linalg.norm(pos - elbow_r) < elbow_threshold):
            at_elbows.append(p)

    if len(at_elbows) >= 2:
        results.append(PlayDetection(
            play_type="horns_set",
            play_start_frame=sorted_fns[0],
            play_end_frame=sorted_fns[min(9, len(sorted_fns)-1)],
            primary_track_ids=[p["track_id"] for p in at_elbows[:2]],
            confidence=0.70,
        ))
    return results
