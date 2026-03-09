"""Passing network computation module.

Builds a directed passing network from per-frame possession data.
Determines ball holder each frame by proximity to ball position,
then tracks holder transitions to count passes between players.

No database dependencies — pure computation module.
"""

import math
from features.types import PassingEdge

try:
    import networkx as nx
except ImportError as exc:  # pragma: no cover
    raise ImportError("networkx is required: pip install networkx") from exc


def _nearest_player(frame: list[dict], ball: dict) -> int | None:
    """Return track_id of the player closest to the ball position.

    Args:
        frame: List of player dicts with keys 'track_id', 'x', 'y'.
        ball: Dict with keys 'x', 'y'.

    Returns:
        track_id of nearest player, or None if frame is empty.
    """
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

    Determines the ball holder each frame by proximity to ball position.
    Tracks holder transitions (A→B = pass from A to B) and aggregates
    into PassingEdge objects with counts.

    Args:
        possession_frames: List of per-frame player dicts. Each frame is a list
            of dicts with keys 'track_id', 'x', 'y'.
        game_id: UUID string of the game.
        possession_id: UUID string of the possession.
        ball_frames: Parallel list of ball position dicts ({'x', 'y'}) or None
            if ball is not detected that frame.

    Returns:
        List of PassingEdge, one per unique (from_track_id, to_track_id) pair.
        Count reflects how many times that pass direction was observed.
        Returns [] if no holder changes occurred.
    """
    if len(possession_frames) < 2:
        return []

    edge_counts: dict[tuple[int, int], int] = {}
    current_holder: int | None = None

    for frame, ball in zip(possession_frames, ball_frames):
        if ball is None:
            # No ball detected — holder unchanged
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
    """Wrap passing edges into a directed NetworkX graph.

    Args:
        edges: List of PassingEdge dataclass instances.

    Returns:
        networkx.DiGraph where each edge has a 'weight' attribute equal to the
        pass count. Caller decides whether and how to persist the graph.
    """
    graph = nx.DiGraph()
    for edge in edges:
        graph.add_edge(edge.from_track_id, edge.to_track_id, weight=edge.count)
    return graph
