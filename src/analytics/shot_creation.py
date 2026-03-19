"""
Shot Creation Analysis

Classifies how each shot was generated using possession context.
Runs once per detected shot event.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

CATCH_SHOOT_DRIBBLES = 1
TRANSITION_HALFCOURT_FRAMES = 120  # 4s at 30fps
CUT_SPEED_THRESHOLD = 12.0
SCREEN_PROXIMITY = 7.0


@dataclass
class ShotCreation:
    creation_type: str  # self_created / screen_created / drive_created / cut_created / transition_created / off_rebound_created
    creation_difficulty: float  # 0-1
    creation_space: float       # feet of space at creation
    creation_time: float        # seconds from possession start


def classify_shot_creation(
    shot_frame: int,
    shooter_track_id: int,
    possession_start_frame: int,
    frames_by_number: Dict[int, List[dict]],
    fps: float = 30.0,
) -> ShotCreation:
    """
    Classify how a shot was created by looking back through possession history.
    """
    creation_time = (shot_frame - possession_start_frame) / fps

    frame = frames_by_number.get(shot_frame, [])
    shooter = next(
        (p for p in frame if p.get("track_id") == shooter_track_id
         and p.get("object_type") == "player"),
        None,
    )
    if shooter is None:
        return ShotCreation("self_created", 0.5, 5.0, creation_time)

    shooter_pos = np.array([shooter.get("x_ft", shooter["x"]),
                             shooter.get("y_ft", shooter["y"])])
    shooter_speed = float(shooter.get("speed", 0) or 0)

    # Check space at shot moment
    others = [p for p in frame
              if p.get("object_type") == "player" and p.get("track_id") != shooter_track_id]
    if others:
        dists = [float(np.linalg.norm(
            np.array([p.get("x_ft", p["x"]), p.get("y_ft", p["y"])]) - shooter_pos
        )) for p in others]
        creation_space = float(min(dists))
    else:
        creation_space = 15.0

    # Transition: possession started recently and offense moving fast
    if creation_time < TRANSITION_HALFCOURT_FRAMES / fps:
        poss_frames = [
            fn for fn in range(possession_start_frame, shot_frame + 1)
            if fn in frames_by_number
        ]
        if poss_frames:
            early_frame = frames_by_number.get(poss_frames[0], [])
            early_speeds = [p.get("speed", 0) or 0 for p in early_frame
                            if p.get("object_type") == "player"]
            if early_speeds and float(np.mean(early_speeds)) > 12.0:
                difficulty = max(0.1, 1.0 - creation_space / 15.0)
                return ShotCreation("transition_created", difficulty, creation_space, creation_time)

    # Drive-created: shooter was moving fast toward basket before shot
    if shooter_speed > 8.0:
        difficulty = 0.5 + shooter_speed / 30.0 * 0.3
        return ShotCreation("drive_created", min(difficulty, 0.9), creation_space, creation_time)

    # Cut-created: player was moving at cut speed in frames before shot
    look_back = min(10, shot_frame - possession_start_frame)
    for fn in range(shot_frame - look_back, shot_frame):
        prev_frame = frames_by_number.get(fn, [])
        prev_shooter = next(
            (p for p in prev_frame if p.get("track_id") == shooter_track_id), None
        )
        if prev_shooter and (prev_shooter.get("speed", 0) or 0) > CUT_SPEED_THRESHOLD:
            return ShotCreation("cut_created", 0.4, creation_space, creation_time)

    # Screen-created: another player was very close and stationary nearby before shot
    for fn in range(max(possession_start_frame, shot_frame - 20), shot_frame):
        prev_frame = frames_by_number.get(fn, [])
        prev_shooter = next(
            (p for p in prev_frame if p.get("track_id") == shooter_track_id), None
        )
        if prev_shooter is None:
            continue
        prev_pos = np.array([prev_shooter.get("x_ft", prev_shooter["x"]),
                              prev_shooter.get("y_ft", prev_shooter["y"])])
        for p in prev_frame:
            if p.get("object_type") != "player" or p.get("track_id") == shooter_track_id:
                continue
            ppos = np.array([p.get("x_ft", p["x"]), p.get("y_ft", p["y"])])
            if (float(np.linalg.norm(ppos - prev_pos)) < SCREEN_PROXIMITY and
                    (p.get("speed", 0) or 0) < 3.0):
                difficulty = max(0.2, 1.0 - creation_space / 15.0)
                return ShotCreation("screen_created", difficulty, creation_space, creation_time)

    # Default: self-created
    difficulty = max(0.2, 1.0 - creation_space / 15.0)
    return ShotCreation("self_created", difficulty, creation_space, creation_time)
