"""
Drive Analysis Engine

Detects driving actions from tracking data and computes drive mechanics.
Event-triggered: only processes when a player shows drive-like movement.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import math
import numpy as np

DRIVE_SPEED_MIN    = 10.0   # ft/s to qualify as a drive
DRIVE_DIST_MIN     = 8.0    # ft penetration to qualify
BASKET_LEFT        = np.array([4.75, 25.0])
BASKET_RIGHT       = np.array([89.25, 25.0])
HELP_ARRIVAL_FPS   = 30.0


@dataclass
class DriveEvent:
    track_id: int
    start_frame: int
    end_frame: int
    drive_angle_to_rim: float
    penetration_depth: float
    defender_beaten: bool
    help_arrival_frames: Optional[int]
    outcome: str
    blow_by_probability: float
    drive_kick_probability: float
    foul_probability: float


def detect_drives(
    frames_by_number: Dict[int, List[dict]],
    sorted_frames: List[int],
    fps: float = 30.0,
) -> List[DriveEvent]:
    """
    Scan tracking data for drive events.

    Uses per-track trajectory analysis — only called once per possession.
    """
    drives: List[DriveEvent] = []

    # Build per-track position history
    track_history: Dict[int, List[Tuple[int, np.ndarray, float]]] = {}
    for fn in sorted_frames:
        for p in frames_by_number.get(fn, []):
            if p.get("object_type") != "player":
                continue
            tid = p["track_id"]
            pos = np.array([p.get("x_ft", p["x"]), p.get("y_ft", p["y"])])
            spd = float(p.get("speed", 0) or 0)
            track_history.setdefault(tid, []).append((fn, pos, spd))

    for tid, history in track_history.items():
        if len(history) < 4:
            continue

        i = 0
        while i < len(history) - 4:
            seg = history[i:i+6]
            avg_spd = float(np.mean([s for _, _, s in seg]))
            if avg_spd < DRIVE_SPEED_MIN:
                i += 1
                continue

            start_pos = seg[0][1]
            end_pos = seg[-1][1]
            displacement = float(np.linalg.norm(end_pos - start_pos))
            if displacement < DRIVE_DIST_MIN:
                i += 1
                continue

            # Is player moving toward a basket?
            basket = BASKET_LEFT if float(start_pos[0]) > 47.0 else BASKET_RIGHT
            move_vec = end_pos - start_pos
            basket_vec = basket - start_pos

            if np.linalg.norm(move_vec) < 0.01:
                i += 1
                continue

            cos_angle = float(np.dot(move_vec, basket_vec) / (
                np.linalg.norm(move_vec) * max(np.linalg.norm(basket_vec), 0.01)
            ))
            if cos_angle < 0.4:
                i += 1
                continue  # not moving toward basket

            # Compute drive angle to rim
            angle_rad = float(math.atan2(
                float(basket[1] - start_pos[1]),
                float(basket[0] - start_pos[0])
            ))
            drive_angle = float(math.degrees(angle_rad))

            # Penetration depth
            penetration = float(np.linalg.norm(basket - end_pos))
            max_possible = float(np.linalg.norm(basket - start_pos))
            depth = float(max(0, max_possible - penetration))

            # Check defender beaten
            start_fn = seg[0][0]
            end_fn = seg[-1][0]
            defender_beaten, help_frames = _check_defender_beaten(
                frames_by_number, start_fn, end_fn, tid, end_pos
            )

            # Outcome probabilities from drive mechanics
            blow_by = min(0.2 + avg_spd / 30.0 * 0.5, 0.85) if defender_beaten else 0.2
            drive_kick = min(0.3 + depth / 20.0 * 0.4, 0.75) if help_frames and help_frames < 8 else 0.25
            foul_prob = min(0.1 + avg_spd / 25.0 * 0.2 + (0.15 if defender_beaten else 0), 0.45)

            drives.append(DriveEvent(
                track_id=tid,
                start_frame=start_fn,
                end_frame=end_fn,
                drive_angle_to_rim=drive_angle,
                penetration_depth=depth,
                defender_beaten=defender_beaten,
                help_arrival_frames=help_frames,
                outcome="drive",
                blow_by_probability=blow_by,
                drive_kick_probability=drive_kick,
                foul_probability=foul_prob,
            ))
            # Skip past this drive window to avoid overlapping detections
            i += 6

    return drives


def _check_defender_beaten(
    frames_by_number: Dict[int, List[dict]],
    start_fn: int,
    end_fn: int,
    track_id: int,
    end_pos: np.ndarray,
) -> Tuple[bool, Optional[int]]:
    """Check if primary defender was beaten and when help arrived."""
    start_frame = frames_by_number.get(start_fn, [])
    end_frame = frames_by_number.get(end_fn, [])

    driver_start = next(
        (p for p in start_frame if p.get("track_id") == track_id and p.get("object_type") == "player"),
        None,
    )
    if driver_start is None:
        return False, None

    driver_start_pos = np.array([driver_start.get("x_ft", driver_start["x"]),
                                  driver_start.get("y_ft", driver_start["y"])])

    # Find nearest defender at start
    defenders_start = [p for p in start_frame
                       if p.get("object_type") == "player" and p.get("track_id") != track_id]
    if not defenders_start:
        return True, None

    primary_def_id = min(
        defenders_start,
        key=lambda p: float(np.linalg.norm(
            np.array([p.get("x_ft", p["x"]), p.get("y_ft", p["y"])]) - driver_start_pos
        ))
    )["track_id"]

    # Find that defender at end
    primary_def_end = next(
        (p for p in end_frame if p.get("track_id") == primary_def_id), None
    )
    if primary_def_end is None:
        return True, None

    def_end_pos = np.array([primary_def_end.get("x_ft", primary_def_end["x"]),
                             primary_def_end.get("y_ft", primary_def_end["y"])])

    # Defender beaten if driver got past them (closer to basket at end)
    driver_end_basket_dist = float(np.linalg.norm(end_pos - np.array([4.75 if end_pos[0] < 47 else 89.25, 25.0])))
    def_end_basket_dist = float(np.linalg.norm(def_end_pos - np.array([4.75 if def_end_pos[0] < 47 else 89.25, 25.0])))

    beaten = driver_end_basket_dist < def_end_basket_dist - 3.0

    # Find help defender arrival
    help_arrival = None
    if beaten:
        for fn in range(start_fn, end_fn + 1):
            frame = frames_by_number.get(fn, [])
            help_defs = [p for p in frame
                         if p.get("object_type") == "player"
                         and p.get("track_id") not in (track_id, primary_def_id)]
            for hd in help_defs:
                hpos = np.array([hd.get("x_ft", hd["x"]), hd.get("y_ft", hd["y"])])
                if float(np.linalg.norm(hpos - end_pos)) < 6.0:
                    help_arrival = fn - start_fn
                    break
            if help_arrival is not None:
                break

    return beaten, help_arrival
