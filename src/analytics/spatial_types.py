"""Shared dataclass type contracts for all spatial feature modules.

These types define the canonical output shapes produced by each feature module
and consumed by downstream models and analytics layers.

Single source of truth — do not duplicate these in features/.
"""

from dataclasses import dataclass


@dataclass
class SpacingMetrics:
    """Per-frame spatial spacing metrics for a possession."""

    game_id: str
    possession_id: str
    frame_number: int
    convex_hull_area: float
    avg_inter_player_distance: float
    timestamp_ms: float


@dataclass
class DefensivePressure:
    """Defensive pressure on a specific tracked player in a frame."""

    game_id: str
    track_id: int
    frame_number: int
    nearest_defender_distance: float
    closing_speed: float
    timestamp_ms: float


@dataclass
class OffBallEvent:
    """A detected off-ball movement event for a tracked player."""

    game_id: str
    track_id: int
    frame_number: int
    event_type: str
    confidence: float
    timestamp_ms: float


@dataclass
class PickAndRollEvent:
    """A detected pick-and-roll event between two tracked players."""

    game_id: str
    ball_handler_track_id: int
    screener_track_id: int
    frame_number: int
    timestamp_ms: float


@dataclass
class PassingEdge:
    """A directed passing connection between two players in a possession."""

    game_id: str
    possession_id: str
    from_track_id: int
    to_track_id: int
    count: int


@dataclass
class MomentumSnapshot:
    """Momentum state snapshot for a game segment."""

    game_id: str
    segment_id: int
    scoring_run: int
    possession_streak: int
    swing_point: bool
    timestamp_ms: float
