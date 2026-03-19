"""Passing network computation from possession tracking data.

Builds a directed passing network by tracking ball holder transitions.
Pure computation — no database dependencies.
"""

import math
from src.analytics.spatial_types import PassingEdge

try:
    import networkx as nx
except ImportError as exc:  # pragma: no cover
    raise ImportError("networkx is required: pip install networkx") from exc


def _nearest_player(frame: list[dict], ball: dict) -> int | None:
    """Return track_id of the player closest to the ball position."""
    if not frame:
        return None
    bx, by = ball["x"], ball["y"]
    best_id = None
    best_dist = float("inf")
    for player in frame:
        dist = math.hypot(player["x"] - bx, player["y"] - by)
        if dist < best_dist:
            best_dist = dist
            best_id = player["track_id"]
    return best_id


def build_passing_network(
    possession_frames: list[list[dict]],
    game_id: str,
    possession_id: str,
    ball_frames: list[dict | None],
) -> list[PassingEdge]:
    """Build a passing network from a sequence of possession frames.

    Args:
        possession_frames: List of per-frame player dicts.
        game_id: UUID string of the game.
        possession_id: UUID string of the possession.
        ball_frames: Parallel list of ball position dicts or None.

    Returns:
        List of PassingEdge, one per unique (from, to) pair with count.
    """
    if len(possession_frames) < 2:
        return []

    edge_counts: dict[tuple[int, int], int] = {}
    current_holder: int | None = None

    for frame, ball in zip(possession_frames, ball_frames):
        if ball is None:
            continue
        holder = _nearest_player(frame, ball)
        if holder is None:
            continue
        if current_holder is not None and holder != current_holder:
            key = (current_holder, holder)
            edge_counts[key] = edge_counts.get(key, 0) + 1
        current_holder = holder

    return [
        PassingEdge(
            game_id=game_id,
            possession_id=possession_id,
            from_track_id=from_id,
            to_track_id=to_id,
            count=count,
        )
        for (from_id, to_id), count in edge_counts.items()
    ]


def export_network_graph(edges: list[PassingEdge]) -> "nx.DiGraph":
    """Wrap passing edges into a directed NetworkX graph."""
    graph = nx.DiGraph()
    for edge in edges:
        graph.add_edge(edge.from_track_id, edge.to_track_id, weight=edge.count)
    return graph
