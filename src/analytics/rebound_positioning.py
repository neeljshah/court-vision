"""
Rebound Positioning Model

Estimates rebound probability per player using trajectory and positioning.
Triggered only when a shot event is detected.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

BOXOUT_DIST = 4.0        # ft — defender within this of offensive player = boxout
CRASH_SPEED = 8.0        # ft/s — offensive player crashing the boards
REBOUND_ZONE_DIST = 15.0 # ft from basket = rebound zone


@dataclass
class ReboundSnapshot:
    frame_number: int
    track_id: int
    rebound_probability: float
    positioning_advantage: float
    boxout_success: bool
    offensive_crash: bool


def estimate_rebound_positioning(
    shot_frame: int,
    frames_by_number: Dict[int, List[dict]],
    shot_x_ft: float,
    shot_y_ft: float,
    fps: float = 30.0,
) -> List[ReboundSnapshot]:
    """
    Estimate rebound probabilities at the moment of a shot.

    Args:
        shot_frame:       Frame number of the shot event.
        frames_by_number: All tracking frames.
        shot_x_ft:        Shot x coordinate in court feet.
        shot_y_ft:        Shot y coordinate in court feet.
        fps:              Video frame rate.

    Returns:
        List of ReboundSnapshot — one per player near the basket.
    """
    frame = frames_by_number.get(shot_frame, [])
    players = [r for r in frame if r.get("object_type") == "player"]
    ball = next((r for r in frame if r.get("object_type") == "ball"), None)

    shot_pos = np.array([shot_x_ft, shot_y_ft])
    basket = np.array([4.75, 25.0] if shot_x_ft > 47 else [89.25, 25.0])

    # Only consider players in rebound zone
    rebound_players = []
    for p in players:
        ppos = np.array([p.get("x_ft", p["x"]), p.get("y_ft", p["y"])])
        if float(np.linalg.norm(ppos - basket)) < REBOUND_ZONE_DIST:
            rebound_players.append(p)

    if not rebound_players:
        return []

    snapshots = []
    total_weight = 0.0
    weights = []

    for p in rebound_players:
        ppos = np.array([p.get("x_ft", p["x"]), p.get("y_ft", p["y"])])
        dist_to_basket = float(np.linalg.norm(ppos - basket))
        speed = float(p.get("speed", 0) or 0)

        # Weight: closer to basket + moving toward it = more likely to rebound
        basket_dir = basket - ppos
        if np.linalg.norm(basket_dir) > 0.01 and speed > 0:
            vel = np.array([p.get("velocity_x", 0) or 0, p.get("velocity_y", 0) or 0])
            cos_toward = float(np.dot(vel, basket_dir) /
                               (np.linalg.norm(vel) * np.linalg.norm(basket_dir) + 0.01))
        else:
            cos_toward = 0.0

        weight = max(0.01, (1.0 / max(dist_to_basket, 1.0)) + max(0, cos_toward) * 0.3)
        weights.append(weight)
        total_weight += weight

    # Normalize to probabilities
    for p, w in zip(rebound_players, weights):
        ppos = np.array([p.get("x_ft", p["x"]), p.get("y_ft", p["y"])])
        prob = w / max(total_weight, 0.01)
        dist_to_basket = float(np.linalg.norm(ppos - basket))
        speed = float(p.get("speed", 0) or 0)

        # Positioning advantage: how much better positioned vs others of same team
        same_team = [q for q in rebound_players
                     if q.get("team") == p.get("team") and q["track_id"] != p["track_id"]]
        if same_team:
            same_dists = [float(np.linalg.norm(
                np.array([q.get("x_ft", q["x"]), q.get("y_ft", q["y"])]) - basket
            )) for q in same_team]
            positioning_advantage = float(np.mean(same_dists)) - dist_to_basket
        else:
            positioning_advantage = 0.0

        # Boxout detection
        opp_team = [q for q in rebound_players if q.get("team") != p.get("team")]
        boxout = any(
            float(np.linalg.norm(
                np.array([q.get("x_ft", q["x"]), q.get("y_ft", q["y"])]) - ppos
            )) < BOXOUT_DIST
            for q in opp_team
        )

        # Offensive crash
        offensive_crash = speed > CRASH_SPEED

        snapshots.append(ReboundSnapshot(
            frame_number=shot_frame,
            track_id=p["track_id"],
            rebound_probability=prob,
            positioning_advantage=positioning_advantage,
            boxout_success=boxout,
            offensive_crash=offensive_crash,
        ))

    return snapshots
