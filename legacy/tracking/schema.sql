-- NBA Tracking System Database Schema
-- Requires PostgreSQL with pgcrypto extension

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Games
CREATE TABLE IF NOT EXISTS games (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_date  DATE        NOT NULL,
    home_team  VARCHAR(64) NOT NULL,
    away_team  VARCHAR(64) NOT NULL,
    season     VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Players
CREATE TABLE IF NOT EXISTS players (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(128) NOT NULL,
    team          VARCHAR(64)  NOT NULL,
    jersey_number SMALLINT,
    position      VARCHAR(16),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Tracking coordinates: one row per tracked object per frame
CREATE TABLE IF NOT EXISTS tracking_coordinates (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id           UUID        NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id         UUID        REFERENCES players(id) ON DELETE SET NULL,
    track_id          INTEGER,
    frame_number      INTEGER     NOT NULL,
    timestamp_ms      BIGINT      NOT NULL,
    -- Pixel coordinates (raw broadcast space)
    x                 REAL        NOT NULL,
    y                 REAL        NOT NULL,
    -- Court coordinates in feet (0-94 x 0-50); NULL if homography unavailable
    x_ft              REAL,
    y_ft              REAL,
    velocity_x        REAL,
    velocity_y        REAL,
    speed             REAL,
    direction_degrees REAL,
    object_type       VARCHAR(16) NOT NULL CHECK (object_type IN ('player', 'ball')),
    confidence        REAL,
    team              VARCHAR(16),  -- 'left', 'right', or 'ball'
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Unique: one entry per track per frame per game (enables safe resume)
    UNIQUE (game_id, frame_number, track_id)
);

CREATE INDEX IF NOT EXISTS idx_tracking_game_frame
    ON tracking_coordinates (game_id, frame_number);

CREATE INDEX IF NOT EXISTS idx_tracking_object_type
    ON tracking_coordinates (game_id, object_type, frame_number);

-- Possessions
CREATE TABLE IF NOT EXISTS possessions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id     UUID        NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    team        VARCHAR(64) NOT NULL,
    start_frame INTEGER     NOT NULL,
    end_frame   INTEGER,
    outcome     VARCHAR(32),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Shot logs
CREATE TABLE IF NOT EXISTS shot_logs (
    id                UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id           UUID    NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id         UUID    REFERENCES players(id) ON DELETE SET NULL,
    frame_number      INTEGER NOT NULL,
    x                 REAL    NOT NULL,
    y                 REAL    NOT NULL,
    x_ft              REAL,
    y_ft              REAL,
    shot_type         VARCHAR(32),
    made              BOOLEAN,
    defender_distance REAL,
    shot_angle        REAL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Feature vectors: per-frame spatial metrics
CREATE TABLE IF NOT EXISTS feature_vectors (
    id                    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id               UUID    NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    frame_number          INTEGER NOT NULL,
    timestamp_ms          REAL,
    convex_hull_area      REAL,
    avg_inter_player_dist REAL,
    nearest_defender_dist REAL,
    closing_speed         REAL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, frame_number)
);

-- Detected events: off-ball, pick-and-rolls, etc.
CREATE TABLE IF NOT EXISTS detected_events (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id      UUID        NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    event_type   VARCHAR(64) NOT NULL,
    track_id     INTEGER,
    frame_number INTEGER,
    confidence   REAL,
    metadata     JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Momentum snapshots
CREATE TABLE IF NOT EXISTS momentum_snapshots (
    id                UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id           UUID    NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    segment_id        INTEGER,
    scoring_run       INTEGER,
    possession_streak INTEGER,
    swing_point       BOOLEAN,
    timestamp_ms      REAL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Detected offensive plays
CREATE TABLE IF NOT EXISTS play_detections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    play_type VARCHAR(64) NOT NULL,
    play_start_frame INTEGER NOT NULL,
    play_end_frame INTEGER NOT NULL,
    primary_track_ids INTEGER[],
    confidence REAL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Defensive scheme snapshots per possession
CREATE TABLE IF NOT EXISTS defensive_schemes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    possession_id UUID REFERENCES possessions(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL,
    scheme_label VARCHAR(32),
    switch_frequency REAL,
    help_frequency REAL,
    paint_collapse_frequency REAL,
    weakside_rotation_speed REAL,
    cohesion_score REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Drive events
CREATE TABLE IF NOT EXISTS drive_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    track_id INTEGER,
    start_frame INTEGER NOT NULL,
    end_frame INTEGER,
    drive_angle_to_rim REAL,
    penetration_depth REAL,
    defender_beaten BOOLEAN,
    help_arrival_frames INTEGER,
    outcome VARCHAR(32),
    blow_by_probability REAL,
    drive_kick_probability REAL,
    foul_probability REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Shot creation classification
CREATE TABLE IF NOT EXISTS shot_creation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    shot_log_id UUID REFERENCES shot_logs(id) ON DELETE CASCADE,
    creation_type VARCHAR(32),
    creation_difficulty REAL,
    creation_space REAL,
    creation_time REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rebound positioning snapshots
CREATE TABLE IF NOT EXISTS rebound_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL,
    rebounding_track_id INTEGER,
    rebound_probability REAL,
    positioning_advantage REAL,
    boxout_success BOOLEAN,
    offensive_crash BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lineup synergy snapshots
CREATE TABLE IF NOT EXISTS lineup_synergy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL,
    track_ids INTEGER[],
    spacing_quality REAL,
    ball_movement_score REAL,
    defensive_cohesion REAL,
    offensive_gravity REAL,
    synergy_index REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Game flow snapshots
CREATE TABLE IF NOT EXISTS game_flow (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL,
    momentum_index REAL,
    scoring_run_probability REAL,
    possession_pressure_index REAL,
    comeback_probability REAL,
    offensive_flow_score REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Micro timing events
CREATE TABLE IF NOT EXISTS micro_timing_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    track_id INTEGER,
    frame_number INTEGER NOT NULL,
    event_type VARCHAR(32),
    catch_to_shot_time REAL,
    catch_to_drive_time REAL,
    catch_to_pass_time REAL,
    screen_to_drive_time REAL,
    decision_latency REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
