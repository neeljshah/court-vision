"""
Micro Timing Model

Captures decision latency and event timing from tracking data.
Computes catch-to-action times, decision probabilities, and offensive flow.
Triggered on catch/screen/drive events.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

CATCH_PROXIMITY_FT = 4.0   # ft — player must be this close to ball to have "caught" it
SHOT_SPEED_THRESHOLD = 50.0  # ft/s — ball moving fast = shot
PASS_SPEED_THRESHOLD = 25.0  # ft/s — ball moving moderately = pass
DRIVE_SPEED = 10.0           # ft/s — player moving toward basket


@dataclass
class MicroTimingEvent:
    track_id: int
    frame_number: int
    event_type: str
    catch_to_shot_time: Optional[float]
    catch_to_drive_time: Optional[float]
    catch_to_pass_time: Optional[float]
    screen_to_drive_time: Optional[float]
    decision_latency: float
    drive_decision_prob: float
    pass_decision_prob: float
    shot_decision_prob: float


def compute_micro_timing(
    frames_by_number: Dict[int, List[dict]],
    sorted_frames: List[int],
    fps: float = 30.0,
) -> List[MicroTimingEvent]:
    """
    Detect catch events and measure time to next decision.
    Only processes frames where ball changes possession proximity.
    """
    events: List[MicroTimingEvent] = []
    prev_holder: Optional[int] = None
    catch_frame: Optional[int] = None

    for fn in sorted_frames:
        frame = frames_by_number.get(fn, [])
        ball = next((r for r in frame if r.get("object_type") == "ball"), None)
        if ball is None:
            continue

        ball_pos = np.array([ball.get("x_ft", ball["x"]), ball.get("y_ft", ball["y"])])
        players = [r for r in frame if r.get("object_type") == "player"]

        if not players:
            continue

        # Identify current ball holder
        current_holder = None
        min_dist = float("inf")
        for p in players:
            ppos = np.array([p.get("x_ft", p["x"]), p.get("y_ft", p["y"])])
            d = float(np.linalg.norm(ppos - ball_pos))
            if d < CATCH_PROXIMITY_FT and d < min_dist:
                min_dist = d
                current_holder = p["track_id"]

        # Detect catch event (ball changed hands)
        if current_holder is not None and current_holder != prev_holder:
            catch_frame = fn

        if catch_frame is not None and current_holder is not None:
            frames_since_catch = fn - catch_frame
            time_since_catch = frames_since_catch / fps

            holder_row = next((p for p in players if p["track_id"] == current_holder), None)
            if holder_row is None:
                prev_holder = current_holder
                continue

            holder_speed = float(holder_row.get("speed", 0) or 0)
            ball_speed = float(ball.get("speed", 0) or 0)

            # Detect what action was taken
            if ball_speed > SHOT_SPEED_THRESHOLD and time_since_catch < 3.0:
                catch_to_shot = time_since_catch
                events.append(_build_event(
                    current_holder, fn, "catch_and_shoot",
                    catch_to_shot=catch_to_shot,
                    decision_latency=time_since_catch,
                    fps=fps,
                ))
                catch_frame = None

            elif holder_speed > DRIVE_SPEED and time_since_catch < 2.0:
                events.append(_build_event(
                    current_holder, fn, "catch_and_drive",
                    catch_to_drive=time_since_catch,
                    decision_latency=time_since_catch,
                    fps=fps,
                ))
                catch_frame = None

            elif ball_speed > PASS_SPEED_THRESHOLD and time_since_catch < 4.0:
                events.append(_build_event(
                    current_holder, fn, "catch_and_pass",
                    catch_to_pass=time_since_catch,
                    decision_latency=time_since_catch,
                    fps=fps,
                ))
                catch_frame = None

        prev_holder = current_holder

    return events


def _build_event(
    track_id: int,
    frame_number: int,
    event_type: str,
    catch_to_shot: Optional[float] = None,
    catch_to_drive: Optional[float] = None,
    catch_to_pass: Optional[float] = None,
    screen_to_drive: Optional[float] = None,
    decision_latency: float = 0.0,
    fps: float = 30.0,
) -> MicroTimingEvent:
    # Decision probabilities from timing heuristics
    fast = decision_latency < 0.5
    shot_prob = 0.5 if catch_to_shot is not None else (0.3 if fast else 0.15)
    drive_prob = 0.5 if catch_to_drive is not None else (0.35 if fast else 0.2)
    pass_prob = 0.5 if catch_to_pass is not None else (0.35 if fast else 0.65)

    total = shot_prob + drive_prob + pass_prob
    return MicroTimingEvent(
        track_id=track_id,
        frame_number=frame_number,
        event_type=event_type,
        catch_to_shot_time=catch_to_shot,
        catch_to_drive_time=catch_to_drive,
        catch_to_pass_time=catch_to_pass,
        screen_to_drive_time=screen_to_drive,
        decision_latency=decision_latency,
        drive_decision_prob=drive_prob / total,
        pass_decision_prob=pass_prob / total,
        shot_decision_prob=shot_prob / total,
    )
