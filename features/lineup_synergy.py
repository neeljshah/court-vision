"""
Lineup Synergy Features

Analyzes 5-man lineup dynamics.
Sampled every 60 frames to minimize compute.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

SAMPLE_RATE = 60  # frames between samples
THREE_PT_DIST = 22.0
GRAVITY_RADIUS = 15.0  # ft — defender must be within this to "respect" a player


@dataclass
class LineupSynergySnapshot:
    frame_number: int
    track_ids: List[int]
    spacing_quality: float
    ball_movement_score: float
    defensive_cohesion: float
    offensive_gravity: float
    synergy_index: float


def compute_lineup_synergy(
    frames_by_number: Dict[int, List[dict]],
    sorted_frames: List[int],
    pass_counts: Optional[Dict[Tuple[int, int], int]] = None,
) -> List[LineupSynergySnapshot]:
    """
    Sample lineup synergy every SAMPLE_RATE frames.

    Args:
        frames_by_number: All tracking frames.
        sorted_frames:    Sorted list of frame numbers in this window.
        pass_counts:      Optional passing network edge counts for ball movement score.

    Returns:
        List of LineupSynergySnapshot.
    """
    snapshots = []
    sampled = sorted_frames[::SAMPLE_RATE]

    for fn in sampled:
        frame = frames_by_number.get(fn, [])
        players = [r for r in frame if r.get("object_type") == "player"]

        if len(players) < 4:
            continue

        track_ids = [p["track_id"] for p in players]
        positions = np.array([[p.get("x_ft", p["x"]), p.get("y_ft", p["y"])] for p in players])

        spacing = _compute_spacing(positions)
        cohesion = _compute_defensive_cohesion(players)
        gravity = _compute_offensive_gravity(players, frame)
        ball_movement = _compute_ball_movement(track_ids, pass_counts)

        synergy = float(spacing * 0.3 + cohesion * 0.25 + gravity * 0.25 + ball_movement * 0.2)

        snapshots.append(LineupSynergySnapshot(
            frame_number=fn,
            track_ids=track_ids,
            spacing_quality=spacing,
            ball_movement_score=ball_movement,
            defensive_cohesion=cohesion,
            offensive_gravity=gravity,
            synergy_index=synergy,
        ))

    return snapshots


def _compute_spacing(positions: np.ndarray) -> float:
    """Spacing quality: how well spread are players? Higher = better."""
    if len(positions) < 2:
        return 0.5
    # Pairwise distances
    n = len(positions)
    dists = []
    for i in range(n):
        for j in range(i+1, n):
            dists.append(float(np.linalg.norm(positions[i] - positions[j])))
    avg_dist = float(np.mean(dists))
    # Optimal spacing ~15-18ft; normalize
    return float(min(avg_dist / 18.0, 1.0))


def _compute_defensive_cohesion(players: List[dict]) -> float:
    """How organized are defenders? Based on speed variance."""
    speeds = [float(p.get("speed", 0) or 0) for p in players]
    if len(speeds) < 2:
        return 0.5
    variance = float(np.var(speeds))
    # Low variance = more synchronized movement = more cohesive
    return float(max(0, 1.0 - variance / 100.0))


def _compute_offensive_gravity(players: List[dict], frame: List[dict]) -> float:
    """How much defensive attention does this lineup attract?"""
    if not players:
        return 0.0
    # Players outside 3pt line attract more gravity
    gravity_count = sum(
        1 for p in players
        if float(np.linalg.norm(
            np.array([p.get("x_ft", p["x"]), p.get("y_ft", p["y"])]) -
            np.array([4.75 if p.get("x_ft", p["x"]) < 47 else 89.25, 25.0])
        )) > THREE_PT_DIST
    )
    return float(gravity_count / max(len(players), 1))


def _compute_ball_movement(
    track_ids: List[int],
    pass_counts: Optional[Dict[Tuple[int, int], int]],
) -> float:
    """Ball movement quality from passing network."""
    if pass_counts is None:
        return 0.5
    lineup_passes = sum(
        count for (a, b), count in pass_counts.items()
        if a in track_ids and b in track_ids
    )
    # Normalize: 20+ passes = excellent ball movement
    return float(min(lineup_passes / 20.0, 1.0))
