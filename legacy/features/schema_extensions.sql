-- Feature engineering schema extensions for the NBA AI system.
-- All tables use IF NOT EXISTS guards so this file is safe to run multiple times.

-- feature_vectors: per-frame spatial features (spacing + defensive pressure)
CREATE TABLE IF NOT EXISTS feature_vectors (
    id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id                  UUID        NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    possession_id            UUID        REFERENCES possessions(id) ON DELETE SET NULL,
    frame_number             INTEGER     NOT NULL,
    timestamp_ms             BIGINT      NOT NULL,
    convex_hull_area         REAL,
    avg_inter_player_dist    REAL,
    nearest_defender_dist    REAL,
    closing_speed            REAL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fv_game_frame
    ON feature_vectors (game_id, frame_number);

-- detected_events: tagged off-ball and pick-and-roll events
CREATE TABLE IF NOT EXISTS detected_events (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id      UUID        NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    track_id     INTEGER     NOT NULL,
    frame_number INTEGER     NOT NULL,
    event_type   VARCHAR(32) NOT NULL,  -- 'cut','screen','drift','pick_and_roll'
    confidence   REAL,
    metadata     JSONB,                 -- extra fields e.g. screener_track_id
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_de_game_type
    ON detected_events (game_id, event_type);

-- momentum_snapshots: per-segment momentum state
CREATE TABLE IF NOT EXISTS momentum_snapshots (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id           UUID        NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    segment_id        INTEGER     NOT NULL,
    scoring_run       INTEGER     NOT NULL DEFAULT 0,
    possession_streak INTEGER     NOT NULL DEFAULT 0,
    swing_point       BOOLEAN     NOT NULL DEFAULT FALSE,
    timestamp_ms      BIGINT      NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
