-- Migration 002: Phase C/D tables for self-improving pipeline
-- Apply with: psql -U postgres -d nba_ai -f database/migrations/002_phase_c_tables.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- Add processing status to games table
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE games
    ADD COLUMN IF NOT EXISTS processed_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS status        VARCHAR(20) DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS tracker_version VARCHAR(20),
    ADD COLUMN IF NOT EXISTS video_path    TEXT;

CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);


-- ─────────────────────────────────────────────────────────────────────────────
-- Model versions — tag every prediction with the model that made it
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_versions (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(50) NOT NULL,   -- 'win_probability', 'props_pts', etc.
    version         VARCHAR(20) NOT NULL,   -- 'v1.0', '2026-03-18', etc.
    trained_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    n_training_rows INTEGER,
    features_hash   VARCHAR(64),            -- SHA-256 of feature list
    metrics_json    JSONB,                  -- {"mae": 0.31, "r2": 0.994, ...}
    model_path      TEXT,                   -- path to .pkl or .json
    is_active       BOOLEAN DEFAULT TRUE,   -- current production model
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_model_versions_name ON model_versions(model_name, is_active);


-- ─────────────────────────────────────────────────────────────────────────────
-- Feature vectors — ML feature rows per player per game
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS features (
    id              SERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    player_id       INTEGER,
    season          VARCHAR(10),
    feature_set     VARCHAR(30) DEFAULT 'v1',  -- feature schema version
    features_json   JSONB NOT NULL,
    cv_features     BOOLEAN DEFAULT FALSE,     -- has CV-derived features
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_features_game    ON features(game_id);
CREATE INDEX IF NOT EXISTS idx_features_player  ON features(player_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_features_uniq ON features(game_id, player_id, feature_set);


-- ─────────────────────────────────────────────────────────────────────────────
-- Outcomes — actual stats after game completes (for auto-retrain comparison)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outcomes (
    id              SERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    player_id       INTEGER NOT NULL,
    season          VARCHAR(10),
    stat_name       VARCHAR(20) NOT NULL,   -- 'pts', 'reb', 'ast', etc.
    actual_value    DOUBLE PRECISION NOT NULL,
    predicted_value DOUBLE PRECISION,       -- model prediction at time of recording
    error           DOUBLE PRECISION,       -- actual - predicted
    model_version   VARCHAR(20),
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_outcomes_game    ON outcomes(game_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_player  ON outcomes(player_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_stat    ON outcomes(stat_name);
CREATE INDEX IF NOT EXISTS idx_outcomes_season  ON outcomes(season);


-- ─────────────────────────────────────────────────────────────────────────────
-- CLV log — closing line value per prediction/bet
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clv_log (
    id              SERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    game_date       DATE,
    player_id       INTEGER,
    stat_name       VARCHAR(20),            -- 'pts', 'reb', etc. (NULL for game bets)
    bet_type        VARCHAR(20),            -- 'prop', 'spread', 'total', 'ml'
    our_line        DOUBLE PRECISION,       -- our prediction / line at bet time
    open_line       DOUBLE PRECISION,       -- book opening line
    closing_line    DOUBLE PRECISION,       -- book closing line
    clv             DOUBLE PRECISION,       -- our_line - closing_line (positive = good)
    actual_result   DOUBLE PRECISION,       -- actual game outcome
    won             BOOLEAN,               -- did the bet win?
    kelly_fraction  DOUBLE PRECISION,       -- recommended Kelly bet size
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_clv_game   ON clv_log(game_id);
CREATE INDEX IF NOT EXISTS idx_clv_date   ON clv_log(game_date);
CREATE INDEX IF NOT EXISTS idx_clv_player ON clv_log(player_id);
CREATE INDEX IF NOT EXISTS idx_clv_stat   ON clv_log(stat_name);
