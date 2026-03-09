"""Shared dataclass type contracts for all Phase 2 feature engineering modules.

These types define the canonical output shapes produced by each feature module
and consumed by downstream models and analytics layers.
"""

from dataclasses import dataclass


@dataclass
class SpacingMetrics:
    """Per-frame spatial spacing metrics for a possession.

    Attributes:
        game_id: UUID of the game.
        possession_id: UUID of the possession.
        frame_number: Video frame index.
        convex_hull_area: Area of the convex hull formed by all on-court players
            (in court coordinate units squared). Always >= 0.
        avg_inter_player_distance: Mean pairwise distance between all players.
        timestamp_ms: Frame timestamp in milliseconds.
    """

    game_id: str
    possession_id: str
    frame_number: int
    convex_hull_area: float
    avg_inter_player_distance: float
    timestamp_ms: float


@dataclass
class DefensivePressure:
    """Defensive pressure on a specific tracked player in a frame.

    Attributes:
        game_id: UUID of the game.
        track_id: DeepSORT track ID of the player being pressured.
        frame_number: Video frame index.
        nearest_defender_distance: Distance to the nearest opposing player.
        closing_speed: Rate of change of defender distance. Negative means closing
            in (defender approaching); positive means opening up (defender retreating).
        timestamp_ms: Frame timestamp in milliseconds.
    """

    game_id: str
    track_id: int
    frame_number: int
    nearest_defender_distance: float
    closing_speed: float
    timestamp_ms: float


@dataclass
class OffBallEvent:
    """A detected off-ball movement event for a tracked player.

    Attributes:
        game_id: UUID of the game.
        track_id: DeepSORT track ID of the player performing the event.
        frame_number: Video frame index where the event was detected.
        event_type: Category of off-ball action. One of: 'cut', 'screen', 'drift'.
        confidence: Model confidence score for the detection (0.0 to 1.0).
        timestamp_ms: Frame timestamp in milliseconds.
    """

    game_id: str
    track_id: int
    frame_number: int
    event_type: str
    confidence: float
    timestamp_ms: float


@dataclass
class PickAndRollEvent:
    """A detected pick-and-roll event between two tracked players.

    Attributes:
        game_id: UUID of the game.
        ball_handler_track_id: DeepSORT track ID of the player handling the ball.
        screener_track_id: DeepSORT track ID of the player setting the screen.
            Must be distinct from ball_handler_track_id.
        frame_number: Video frame index where the event was detected.
        timestamp_ms: Frame timestamp in milliseconds.
    """

    game_id: str
    ball_handler_track_id: int
    screener_track_id: int
    frame_number: int
    timestamp_ms: float


@dataclass
class PassingEdge:
    """A directed passing connection between two players in a possession.

    Attributes:
        game_id: UUID of the game.
        possession_id: UUID of the possession.
        from_track_id: DeepSORT track ID of the passer.
        to_track_id: DeepSORT track ID of the receiver.
        count: Number of times this passing edge occurred. Always >= 1.
    """

    game_id: str
    possession_id: str
    from_track_id: int
    to_track_id: int
    count: int


@dataclass
class MomentumSnapshot:
    """Momentum state snapshot for a game segment.

    Attributes:
        game_id: UUID of the game.
        segment_id: Integer index of the time segment (e.g., 2-minute windows).
        scoring_run: Net point differential during the current run (positive or negative).
        possession_streak: Number of consecutive possessions won by the leading team.
        swing_point: True if this segment represents a momentum shift event.
        timestamp_ms: Timestamp of the snapshot in milliseconds.
    """

    game_id: str
    segment_id: int
    scoring_run: int
    possession_streak: int
    swing_point: bool
    timestamp_ms: float
