"""
Space Control Model

Computes dynamic spatial control using simplified radial reach models.
Much cheaper than Voronoi simulation — uses vectorized numpy.

Triggered every N frames (sample-based, not every frame).
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

# Court grid for control map (low resolution for speed)
GRID_W = 47   # cells across 94ft court
GRID_H = 25   # cells across 50ft court
FT_PER_CELL_X = 94.0 / GRID_W
FT_PER_CELL_Y = 50.0 / GRID_H

# Player reach model
BASE_REACH_FT = 6.0     # base reach radius
SPEED_REACH_FACTOR = 0.3  # additional reach per ft/s of speed

# Precompute grid cell centers once
_GRID_X, _GRID_Y = np.meshgrid(
    np.linspace(0, 94, GRID_W),
    np.linspace(0, 50, GRID_H),
)
_GRID_POINTS = np.stack([_GRID_X.ravel(), _GRID_Y.ravel()], axis=1)  # (GRID_W*GRID_H, 2)


@dataclass
class SpaceControlSnapshot:
    frame_number: int
    offensive_control: float       # fraction of court controlled by offense
    defensive_control: float       # fraction of court controlled by defense
    contested_space: float         # fraction of court contested
    open_lane_probability: float   # probability of open driving lane
    passing_lane_openness: float   # fraction of passing lanes open
    drive_lane_availability: float


def compute_space_control(
    frame: List[dict],
    frame_number: int,
    ball_team: str = "team_a",
) -> SpaceControlSnapshot:
    """
    Compute space control for a single frame using radial reach model.

    Args:
        frame:      All tracking rows for this frame.
        frame_number: Frame index.
        ball_team:  Which team has the ball ('left' or 'right').

    Returns:
        SpaceControlSnapshot with spatial metrics.
    """
    players = [r for r in frame if r.get("object_type") == "player"]
    ball = next((r for r in frame if r.get("object_type") == "ball"), None)

    if len(players) < 2:
        return SpaceControlSnapshot(frame_number, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)

    offense = [p for p in players if p.get("team") == ball_team]
    defense = [p for p in players if p.get("team") != ball_team and p.get("team") != "ball"]

    if not offense or not defense:
        return SpaceControlSnapshot(frame_number, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)

    # Compute influence of each player on each grid cell
    off_influence = _team_influence(offense)  # (GRID_W*GRID_H,)
    def_influence = _team_influence(defense)

    # Control = team with higher influence at each cell
    off_control_cells = (off_influence > def_influence).sum()
    def_control_cells = (def_influence > off_influence).sum()
    contested_cells = (np.abs(off_influence - def_influence) < 0.1 * np.maximum(off_influence, def_influence)).sum()
    total_cells = GRID_W * GRID_H

    # Open lane: drive lane from ball to basket
    open_lane = _compute_open_lane(ball, defense) if ball else 0.5
    pass_openness = _compute_passing_lane_openness(offense, defense, ball)

    return SpaceControlSnapshot(
        frame_number=frame_number,
        offensive_control=float(off_control_cells / total_cells),
        defensive_control=float(def_control_cells / total_cells),
        contested_space=float(contested_cells / total_cells),
        open_lane_probability=open_lane,
        passing_lane_openness=pass_openness,
        drive_lane_availability=open_lane,
    )


def _team_influence(players: List[dict]) -> np.ndarray:
    """
    Vectorized radial influence of all players on the court grid.
    Returns (GRID_W*GRID_H,) influence array.
    """
    if not players:
        return np.zeros(GRID_W * GRID_H)

    positions = np.array([
        [p.get("x_ft", p["x"]), p.get("y_ft", p["y"])]
        for p in players
    ])  # (N, 2)
    speeds = np.array([p.get("speed", 0) or 0 for p in players])  # (N,)
    radii = BASE_REACH_FT + speeds * SPEED_REACH_FACTOR  # (N,)

    # Distances: (N, GRID_W*GRID_H)
    diff = _GRID_POINTS[np.newaxis, :, :] - positions[:, np.newaxis, :]  # (N, cells, 2)
    dists = np.linalg.norm(diff, axis=2)  # (N, cells)

    # Influence: Gaussian decay from each player's reach radius
    influence = np.exp(-0.5 * (dists / radii[:, np.newaxis]) ** 2)  # (N, cells)

    # Max influence per cell across all players on this team
    return influence.max(axis=0)  # (cells,)


def _compute_open_lane(ball: dict, defenders: List[dict]) -> float:
    """Estimate probability of open driving lane from ball to nearest basket."""
    if not defenders:
        return 1.0

    bx = float(ball.get("x_ft", ball["x"]))
    by = float(ball.get("y_ft", ball["y"]))
    ball_pos = np.array([bx, by])

    basket = np.array([4.75, 25.0] if bx > 47 else [89.25, 25.0])
    lane_dir = basket - ball_pos
    lane_len = np.linalg.norm(lane_dir)
    if lane_len < 0.01:
        return 0.5

    lane_dir_norm = lane_dir / lane_len

    # Check each defender's proximity to the drive lane
    min_lane_clearance = float("inf")
    for d in defenders:
        dpos = np.array([d.get("x_ft", d["x"]), d.get("y_ft", d["y"])])
        to_def = dpos - ball_pos
        # Project defender onto lane direction
        proj = np.dot(to_def, lane_dir_norm)
        if 0 < proj < lane_len:
            # Perpendicular distance to lane
            perp = float(np.linalg.norm(to_def - proj * lane_dir_norm))
            min_lane_clearance = min(min_lane_clearance, perp)

    if min_lane_clearance == float("inf"):
        return 0.9
    return float(min(max(min_lane_clearance / 6.0, 0.0), 1.0))


def _compute_passing_lane_openness(
    offense: List[dict], defense: List[dict], ball: Optional[dict]
) -> float:
    """Average openness of passing lanes from ball handler to receivers."""
    if ball is None or not offense or not defense:
        return 0.5

    bpos = np.array([ball.get("x_ft", ball["x"]), ball.get("y_ft", ball["y"])])
    def_positions = np.array([
        [d.get("x_ft", d["x"]), d.get("y_ft", d["y"])]
        for d in defense
    ])

    openness_scores = []
    for receiver in offense:
        rpos = np.array([receiver.get("x_ft", receiver["x"]), receiver.get("y_ft", receiver["y"])])
        lane = rpos - bpos
        lane_len = float(np.linalg.norm(lane))
        if lane_len < 1.0:
            continue

        lane_norm = lane / lane_len
        to_defs = def_positions - bpos  # (D, 2)
        projs = to_defs @ lane_norm  # (D,)
        valid = (projs > 0) & (projs < lane_len)
        if not valid.any():
            openness_scores.append(1.0)
            continue

        perp_dists = np.linalg.norm(to_defs[valid] - projs[valid, np.newaxis] * lane_norm, axis=1)
        min_perp = float(perp_dists.min())
        openness_scores.append(min(max(min_perp / 5.0, 0.0), 1.0))

    return float(np.mean(openness_scores)) if openness_scores else 0.5
