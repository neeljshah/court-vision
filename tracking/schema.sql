-- NBA Tracking System Database Schema
-- Requires PostgreSQL with pgcrypto extension for gen_random_uuid()

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Games table: one row per game
CREATE TABLE IF NOT EXISTS games (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_date     DATE        NOT NULL,
    home_team     VARCHAR(64) NOT NULL,
    away_team     VARCHAR(64) NOT NULL,
    season        VARCHAR(16) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Players table: one row per player
CREATE TABLE IF NOT EXISTS players (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR(128) NOT NULL,
    team           VARCHAR(64)  NOT NULL,
    jersey_number  SMALLINT,
    position       VARCHAR(16),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Tracking coordinates: one row per detected object per frame
CREATE TABLE IF NOT EXISTS tracking_coordinates (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id           UUID        NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id         UUID        REFERENCES players(id) ON DELETE SET NULL,  -- nullable for ball
    frame_number      INTEGER     NOT NULL,
    timestamp_ms      BIGINT      NOT NULL,
    x                 REAL        NOT NULL,
    y                 REAL        NOT NULL,
    velocity_x        REAL,
    velocity_y        REAL,
    speed             REAL,
    direction_degrees REAL,
    object_type       VARCHAR(16) NOT NULL CHECK (object_type IN ('player', 'ball')),
    confidence        REAL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Composite index for the primary query pattern: fetch all objects in a frame range for a game
CREATE INDEX IF NOT EXISTS idx_tracking_game_frame
    ON tracking_coordinates (game_id, frame_number);

-- Possessions table: one row per possession
CREATE TABLE IF NOT EXISTS possessions (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id      UUID        NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    team         VARCHAR(64) NOT NULL,
    start_frame  INTEGER     NOT NULL,
    end_frame    INTEGER,
    outcome      VARCHAR(32),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Shot logs table: one row per shot attempt
CREATE TABLE IF NOT EXISTS shot_logs (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id           UUID        NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id         UUID        NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    frame_number      INTEGER     NOT NULL,
    x                 REAL        NOT NULL,
    y                 REAL        NOT NULL,
    shot_type         VARCHAR(32),
    made              BOOLEAN     NOT NULL,
    defender_distance REAL,
    shot_angle        REAL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
