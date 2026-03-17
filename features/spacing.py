"""Player spacing metrics computation module (FE-01).

Computes per-frame spatial spacing metrics from a list of player (x, y) positions.
Pure computation — no database dependencies.
"""
import itertools
import math

from scipy.spatial import ConvexHull, QhullError

from features.types import SpacingMetrics


def compute_spacing(
    player_positions: list[tuple[float, float]],
    game_id: str,
    possession_id: str,
    frame_number: int,
    timestamp_ms: float,
) -> SpacingMetrics:
    """Compute convex hull area and average inter-player distance for a frame.

    Args:
        player_positions: List of (x, y) tuples for all on-court players.
        game_id: UUID of the game.
        possession_id: UUID of the current possession.
        frame_number: Video frame index.
        timestamp_ms: Frame timestamp in milliseconds.

    Returns:
        SpacingMetrics dataclass with computed spatial metrics and passed-through metadata.
    """
    n = len(player_positions)

    # Convex hull area — requires at least 3 non-collinear points
    hull_area = 0.0
    if n >= 3:
        try:
            hull_area = ConvexHull(player_positions).volume  # .volume = area in 2D
        except QhullError:
            # Points are collinear or otherwise degenerate
            hull_area = 0.0

    # Average pairwise distance
    avg_dist = 0.0
    if n >= 2:
        distances = [
            math.hypot(a[0] - b[0], a[1] - b[1])
            for a, b in itertools.combinations(player_positions, 2)
        ]
        avg_dist = sum(distances) / len(distances)

    return SpacingMetrics(
        game_id=game_id,
        possession_id=possession_id,
        frame_number=frame_number,
        convex_hull_area=hull_area,
        avg_inter_player_distance=avg_dist,
        timestamp_ms=timestamp_ms,
    )
