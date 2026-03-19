"""
Defensive Scheme Detection

Infers defensive structures from player spacing and movement patterns.
Uses spatial geometry — no frame-by-frame scanning.
Triggered once per possession window.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

PAINT_X = (19.0, 75.0)
PAINT_Y = (10.0, 40.0)
ZONE_SPACING_THRESHOLD = 15.0  # ft — zone defenders spread wider than man
MAN_ASSIGNMENT_DIST = 8.0      # ft — defender within this = guarding player
SWITCH_SPEED = 8.0             # ft/s — defender moving toward new assignment
HELP_DIST_THRESHOLD = 12.0     # ft — weakside help position
BLITZ_SPEED = 14.0             # ft/s — both defenders rushing ball handler
PAINT_COLLAPSE_DIST = 6.0      # ft — defender leaving assignment toward paint


@dataclass
class DefensiveSchemeSnapshot:
    frame_number: int
    scheme_label: str
    switch_frequency: float
    help_frequency: float
    paint_collapse_frequency: float
    weakside_rotation_speed: float
    cohesion_score: float


def analyze_defensive_scheme(
    frames_by_number: Dict[int, List[dict]],
    possession_frames: List[int],
    sample_rate: int = 5,
) -> List[DefensiveSchemeSnapshot]:
    """
    Analyze defensive scheme over a possession.

    Samples every sample_rate frames to reduce compute.
    Returns one snapshot per sampled frame.
    """
    snapshots = []
    sampled = possession_frames[::sample_rate]

    for fn in sampled:
        frame = frames_by_number.get(fn, [])
        players = [r for r in frame if r.get("object_type") == "player"]
        ball = next((r for r in frame if r.get("object_type") == "ball"), None)

        if len(players) < 4 or ball is None:
            continue

        scheme = _classify_scheme(players, ball)
        switch_freq = _estimate_switch_frequency(players, ball)
        help_freq = _estimate_help_frequency(players, ball)
        paint_collapse = _estimate_paint_collapse(players, ball)
        rotation_speed = _estimate_rotation_speed(players)
        cohesion = _compute_cohesion(players)

        snapshots.append(DefensiveSchemeSnapshot(
            frame_number=fn,
            scheme_label=scheme,
            switch_frequency=switch_freq,
            help_frequency=help_freq,
            paint_collapse_frequency=paint_collapse,
            weakside_rotation_speed=rotation_speed,
            cohesion_score=cohesion,
        ))

    return snapshots


def _pos(row: dict) -> np.ndarray:
    return np.array([row.get("x_ft", row["x"]), row.get("y_ft", row["y"])], dtype=float)


def _classify_scheme(players: List[dict], ball: dict) -> str:
    """Classify man/zone/hybrid using defender spacing."""
    positions = np.array([_pos(p) for p in players])
    n = len(positions)
    if n < 4:
        return "unknown"

    # Average nearest-neighbor distance for defenders
    dists = []
    for i in range(n):
        others = np.linalg.norm(positions - positions[i], axis=1)
        others[i] = np.inf
        dists.append(np.min(others))

    avg_nn = float(np.mean(dists))

    # Zone: defenders evenly spaced at zone positions
    # Man: defenders clustered near offensive players (tighter spacing variance)
    spacing_var = float(np.var(dists))

    if avg_nn > ZONE_SPACING_THRESHOLD and spacing_var < 20:
        return "zone"
    elif avg_nn < MAN_ASSIGNMENT_DIST * 1.5:
        return "man_to_man"
    elif spacing_var > 30:
        return "hybrid_zone"
    else:
        return "man_to_man"


def _estimate_switch_frequency(players: List[dict], ball: dict) -> float:
    """Players moving toward new assignments = switching."""
    ball_pos = _pos(ball)
    switching = sum(
        1 for p in players
        if (p.get("speed", 0) or 0) > SWITCH_SPEED and
           float(np.linalg.norm(_pos(p) - ball_pos)) < 15.0
    )
    return min(switching / max(len(players), 1), 1.0)


def _estimate_help_frequency(players: List[dict], ball: dict) -> float:
    """Defenders not near ball but positioned in help lanes."""
    ball_pos = _pos(ball)
    helping = sum(
        1 for p in players
        if float(np.linalg.norm(_pos(p) - ball_pos)) > HELP_DIST_THRESHOLD and
           abs(float(_pos(p)[0]) - float(ball_pos[0])) < 20.0
    )
    return min(helping / max(len(players), 1), 1.0)


def _estimate_paint_collapse(players: List[dict], ball: dict) -> float:
    """Defenders moving toward paint = collapsing."""
    paint_center = np.array([47.0, 25.0])
    collapsing = sum(
        1 for p in players
        if float(np.linalg.norm(_pos(p) - paint_center)) < PAINT_COLLAPSE_DIST * 2
    )
    return min(collapsing / max(len(players), 1), 1.0)


def _estimate_rotation_speed(players: List[dict]) -> float:
    """Average speed of weakside defenders."""
    speeds = [(p.get("speed", 0) or 0) for p in players]
    if not speeds:
        return 0.0
    return float(np.mean(sorted(speeds)[:len(speeds)//2]))


def _compute_cohesion(players: List[dict]) -> float:
    """How structured/organized the defense looks (low variance = organized)."""
    if len(players) < 3:
        return 0.5
    positions = np.array([_pos(p) for p in players])
    centroid = positions.mean(axis=0)
    dists = np.linalg.norm(positions - centroid, axis=1)
    variance = float(np.var(dists))
    # Lower variance = more cohesive; normalize to 0-1
    return float(max(0, 1.0 - variance / 200.0))
