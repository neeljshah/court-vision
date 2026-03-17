"""Tests for features/passing_network.py.

Tests cover:
- Basic pass detection (holder changes)
- Edge aggregation (count increments, not duplicate edges)
- Empty possession
- export_network_graph: returns networkx.DiGraph with correct edge weights
"""

import pytest
import math
from features.passing_network import build_passing_network, export_network_graph
from features.types import PassingEdge
import networkx as nx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_player(track_id: int, x: float, y: float) -> dict:
    return {"track_id": track_id, "x": x, "y": y}


def make_ball(x: float, y: float) -> dict:
    return {"x": x, "y": y}


GAME_ID = "game-aaa"
POSS_ID = "poss-111"


# ---------------------------------------------------------------------------
# build_passing_network
# ---------------------------------------------------------------------------

class TestBuildPassingNetworkBasic:

    def test_single_pass_produces_one_edge(self):
        """Track 1 has ball then track 2 has ball → one edge (1→2) with count 1."""
        # Frame 0: track 1 closest to ball at (10, 10), track 2 far away
        frame0 = [make_player(1, 10, 10), make_player(2, 200, 200)]
        ball0 = make_ball(10, 10)  # ball at track 1

        # Frame 1: track 2 closest to ball at (200, 200), track 1 far away
        frame1 = [make_player(1, 10, 10), make_player(2, 200, 200)]
        ball1 = make_ball(200, 200)  # ball moves to track 2

        edges = build_passing_network([frame0, frame1], GAME_ID, POSS_ID, [ball0, ball1])

        assert len(edges) == 1
        assert edges[0].from_track_id == 1
        assert edges[0].to_track_id == 2
        assert edges[0].count == 1

    def test_edge_metadata(self):
        """PassingEdge has correct game_id and possession_id."""
        frame0 = [make_player(1, 0, 0), make_player(2, 100, 100)]
        frame1 = [make_player(1, 0, 0), make_player(2, 100, 100)]

        edges = build_passing_network(
            [frame0, frame1], GAME_ID, POSS_ID,
            [make_ball(0, 0), make_ball(100, 100)]
        )

        assert len(edges) == 1
        assert edges[0].game_id == GAME_ID
        assert edges[0].possession_id == POSS_ID

    def test_returns_list_of_passing_edges(self):
        """Return type is list[PassingEdge]."""
        frame0 = [make_player(1, 0, 0)]
        frame1 = [make_player(1, 0, 0)]
        edges = build_passing_network([frame0, frame1], GAME_ID, POSS_ID, [make_ball(0, 0), make_ball(0, 0)])
        assert isinstance(edges, list)
        for e in edges:
            assert isinstance(e, PassingEdge)

    def test_same_pass_three_times_aggregates_count(self):
        """Same pass repeated 3 times yields count=3, not 3 separate edges."""
        # Sequence: holder oscillates 1→2→1→2→1→2 = 3 passes from 1→2 and 2 passes from 2→1
        frames = []
        balls = []
        positions = [(1, 0, 0, 100, 100), (2, 0, 0, 100, 100),
                     (1, 0, 0, 100, 100), (2, 0, 0, 100, 100),
                     (1, 0, 0, 100, 100), (2, 0, 0, 100, 100)]
        # Frame alternates: ball near track1 then track2
        for i, (holder, x1, y1, x2, y2) in enumerate(positions):
            frames.append([make_player(1, x1, y1), make_player(2, x2, y2)])
            balls.append(make_ball(x1, y1) if holder == 1 else make_ball(x2, y2))

        edges = build_passing_network(frames, GAME_ID, POSS_ID, balls)

        edge_dict = {(e.from_track_id, e.to_track_id): e.count for e in edges}

        # 1→2 transitions: frame 0→1, frame 2→3, frame 4→5 = 3 passes
        assert edge_dict.get((1, 2), 0) == 3
        # 2→1 transitions: frame 1→2, frame 3→4 = 2 passes
        assert edge_dict.get((2, 1), 0) == 2

    def test_no_duplicate_edges_in_result(self):
        """All passes are aggregated; no duplicate (from_id, to_id) pairs."""
        # 5 passes from 1→2
        frames = []
        balls = []
        for i in range(6):
            frames.append([make_player(1, 0, 0), make_player(2, 100, 0)])
            if i % 2 == 0:
                balls.append(make_ball(0, 0))   # near track 1
            else:
                balls.append(make_ball(100, 0)) # near track 2

        edges = build_passing_network(frames, GAME_ID, POSS_ID, balls)
        keys = [(e.from_track_id, e.to_track_id) for e in edges]
        assert len(keys) == len(set(keys)), "Duplicate edges found — aggregation failed"


class TestBuildPassingNetworkEdgeCases:

    def test_empty_possession_returns_empty_list(self):
        """Empty frame list → []."""
        edges = build_passing_network([], GAME_ID, POSS_ID, [])
        assert edges == []

    def test_single_frame_returns_empty_list(self):
        """Single frame — no holder change possible → []."""
        edges = build_passing_network(
            [[make_player(1, 0, 0)]], GAME_ID, POSS_ID, [make_ball(0, 0)]
        )
        assert edges == []

    def test_none_ball_frame_keeps_holder_unchanged(self):
        """If ball is None for a frame, holder is unchanged — no spurious edge."""
        frame0 = [make_player(1, 0, 0), make_player(2, 100, 0)]
        frame1 = [make_player(1, 0, 0), make_player(2, 100, 0)]
        frame2 = [make_player(1, 0, 0), make_player(2, 100, 0)]

        # Ball visible in frame 0 (near track 1), None in frame 1, then near track 2 in frame 2
        edges = build_passing_network(
            [frame0, frame1, frame2],
            GAME_ID, POSS_ID,
            [make_ball(0, 0), None, make_ball(100, 0)]
        )
        # Should detect pass 1→2 when ball finally appears near track 2
        assert len(edges) == 1
        assert edges[0].from_track_id == 1
        assert edges[0].to_track_id == 2

    def test_no_holder_change_returns_empty_list(self):
        """Same player holds ball every frame → no edges."""
        frames = [[make_player(1, 0, 0), make_player(2, 100, 0)] for _ in range(5)]
        balls = [make_ball(0, 0) for _ in range(5)]
        edges = build_passing_network(frames, GAME_ID, POSS_ID, balls)
        assert edges == []

    def test_single_player_no_edges(self):
        """Only one player — can't pass to anyone → []."""
        frames = [[make_player(1, 0, 0)] for _ in range(3)]
        balls = [make_ball(0, 0) for _ in range(3)]
        edges = build_passing_network(frames, GAME_ID, POSS_ID, balls)
        assert edges == []

    def test_all_none_balls_returns_empty_list(self):
        """All frames have None ball → no holder, no edges."""
        frames = [[make_player(1, 0, 0), make_player(2, 100, 0)] for _ in range(3)]
        edges = build_passing_network(frames, GAME_ID, POSS_ID, [None, None, None])
        assert edges == []


# ---------------------------------------------------------------------------
# export_network_graph
# ---------------------------------------------------------------------------

class TestExportNetworkGraph:

    def test_returns_digraph(self):
        """export_network_graph returns a networkx.DiGraph."""
        edges = [PassingEdge(GAME_ID, POSS_ID, 1, 2, 3)]
        graph = export_network_graph(edges)
        assert isinstance(graph, nx.DiGraph)

    def test_edge_weight_equals_count(self):
        """Edge weight in graph matches PassingEdge.count."""
        edges = [PassingEdge(GAME_ID, POSS_ID, 1, 2, 5)]
        graph = export_network_graph(edges)
        assert graph[1][2]["weight"] == 5

    def test_multiple_edges_in_graph(self):
        """Multiple edges all appear in the graph."""
        edges = [
            PassingEdge(GAME_ID, POSS_ID, 1, 2, 3),
            PassingEdge(GAME_ID, POSS_ID, 2, 3, 1),
            PassingEdge(GAME_ID, POSS_ID, 3, 1, 2),
        ]
        graph = export_network_graph(edges)
        assert graph.has_edge(1, 2)
        assert graph.has_edge(2, 3)
        assert graph.has_edge(3, 1)
        assert graph[3][1]["weight"] == 2

    def test_empty_edges_returns_empty_graph(self):
        """Empty edge list → empty DiGraph."""
        graph = export_network_graph([])
        assert isinstance(graph, nx.DiGraph)
        assert graph.number_of_edges() == 0
        assert graph.number_of_nodes() == 0

    def test_directionality_is_preserved(self):
        """Graph is directed: edge 1→2 does not imply edge 2→1."""
        edges = [PassingEdge(GAME_ID, POSS_ID, 1, 2, 1)]
        graph = export_network_graph(edges)
        assert graph.has_edge(1, 2)
        assert not graph.has_edge(2, 1)
