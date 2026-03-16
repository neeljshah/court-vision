-- NBA AI System — PostgreSQL Schema
-- Apply with: psql -U postgres -d nba_ai -f database/schema.sql
-- Requires PostgreSQL 14+ (uses JSONB, generated columns)

-- ─────────────────────────────────────────────────────────────────────────────
-- Extensions
-- ─────────────────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- for fuzzy player name search


-- ─────────────────────────────────────────────────────────────────────────────
-- Teams
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS teams (
    team_id         INTEGER PRIMARY KEY,        -- NBA API team_id
    abbreviation    VARCHAR(5) NOT NULL UNIQUE,
    full_name       VARCHAR(100) NOT NULL,
    city            VARCHAR(50) NOT NULL,
    conference      VARCHAR(4) NOT NULL,        -- 'East' / 'West'
    division        VARCHAR(20),
    arena_lat       DOUBLE PRECISION,
    arena_lon       DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- Players
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS players (
    player_id       INTEGER PRIMARY KEY,        -- NBA API person_id
    first_name      VARCHAR(50) NOT NULL,
    last_name       VARCHAR(50) NOT NULL,
    full_name       VARCHAR(100) GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED,
    jersey_number   SMALLINT,
    position        VARCHAR(10),                -- 'PG','SG','SF','PF','C','G','F','G-F','F-C'
    team_id         INTEGER REFERENCES teams(team_id),
    height_inches   SMALLINT,
    weight_lbs      SMALLINT,
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);
CREATE INDEX IF NOT EXISTS idx_players_name ON players USING GIN(full_name gin_trgm_ops);


-- ─────────────────────────────────────────────────────────────────────────────
-- Games
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS games (
    game_id         VARCHAR(20) PRIMARY KEY,    -- NBA API game_id (e.g. "0022300001")
    season          VARCHAR(10) NOT NULL,       -- '2024-25'
    game_date       DATE NOT NULL,
    home_team_id    INTEGER NOT NULL REFERENCES teams(team_id),
    away_team_id    INTEGER NOT NULL REFERENCES teams(team_id),
    home_score      SMALLINT,
    away_score      SMALLINT,
    home_won        BOOLEAN,
    status          VARCHAR(20) DEFAULT 'scheduled',  -- scheduled/live/final
    arena_city      VARCHAR(50),

    -- Schedule context (pre-game features)
    home_rest_days          SMALLINT,
    away_rest_days          SMALLINT,
    home_back_to_back       BOOLEAN DEFAULT FALSE,
    away_back_to_back       BOOLEAN DEFAULT FALSE,
    home_second_of_3_in_4   BOOLEAN DEFAULT FALSE,
    away_second_of_3_in_4   BOOLEAN DEFAULT FALSE,
    home_travel_miles       REAL,
    away_travel_miles       REAL,

    -- Pre-game model outputs
    model_home_win_prob     REAL,               -- 0.0 – 1.0
    model_spread            REAL,               -- positive = home favoured by N pts
    model_total             REAL,               -- projected total points

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
CREATE INDEX IF NOT EXISTS idx_games_home ON games(home_team_id);
CREATE INDEX IF NOT EXISTS idx_games_away ON games(away_team_id);
CREATE INDEX IF NOT EXISTS idx_games_season ON games(season);


-- ─────────────────────────────────────────────────────────────────────────────
-- Tracking frames
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tracking_frames (
    id              BIGSERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    clip_id         UUID DEFAULT uuid_generate_v4(),  -- groups frames from same clip file
    frame_number    INTEGER NOT NULL,
    timestamp_sec   REAL NOT NULL,              -- seconds from video start
    player_id       INTEGER REFERENCES players(player_id),
    tracker_player_id INTEGER,                 -- anonymous slot ID from tracker (0-9)
    team_id         INTEGER REFERENCES teams(team_id),
    x_pos           REAL,                       -- 2D court x (pixels, ~3200 wide)
    y_pos           REAL,                       -- 2D court y (pixels, ~1800 tall)
    speed           REAL,                       -- pixels/frame
    acceleration    REAL,
    ball_possession BOOLEAN DEFAULT FALSE,
    event           VARCHAR(20),                -- 'dribble','pass','shot','none'
    confidence      REAL,                       -- tracker confidence 0-1
    team_spacing    REAL,                       -- convex hull area of team (px²)
    paint_count_own SMALLINT,
    paint_count_opp SMALLINT,
    tracker_version VARCHAR(20),

    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_frames_game ON tracking_frames(game_id);
CREATE INDEX IF NOT EXISTS idx_frames_clip ON tracking_frames(clip_id);
CREATE INDEX IF NOT EXISTS idx_frames_player ON tracking_frames(player_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Possessions
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS possessions (
    id              BIGSERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    possession_id   INTEGER NOT NULL,           -- sequential within clip
    clip_id         UUID,
    team_id         INTEGER REFERENCES teams(team_id),
    start_frame     INTEGER,
    end_frame       INTEGER,
    duration_sec    REAL,
    avg_spacing     REAL,                       -- convex hull area
    defensive_pressure REAL,                   -- 0-1
    drive_attempts  SMALLINT DEFAULT 0,
    shot_attempted  BOOLEAN DEFAULT FALSE,
    fast_break      BOOLEAN DEFAULT FALSE,
    result          VARCHAR(20),                -- 'made','missed','turnover','foul','endofperiod'
    outcome_score   SMALLINT DEFAULT 0,         -- +2, +3, 0 (miss/to), +1 (ft made)
    vtb             REAL,                       -- value through ball-handler

    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_possessions_game ON possessions(game_id);
CREATE INDEX IF NOT EXISTS idx_possessions_team ON possessions(team_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Shots
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shots (
    id              BIGSERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    possession_id   BIGINT REFERENCES possessions(id),
    player_id       INTEGER REFERENCES players(player_id),
    tracker_player_id INTEGER,
    team_id         INTEGER REFERENCES teams(team_id),
    shot_x          REAL,                       -- court x at shot moment
    shot_y          REAL,
    court_zone      VARCHAR(20),                -- 'paint','mid_range','corner_3','above_break_3'
    defender_distance REAL,                     -- nearest defender in court px
    team_spacing    REAL,
    shot_quality    REAL,                       -- model output 0-1 (xFG)
    made            BOOLEAN,                    -- from NBA API enrichment
    shot_type       VARCHAR(20),                -- 'jump_shot','layup','dunk','hook'
    period          SMALLINT,
    game_clock_sec  REAL,

    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_shots_game ON shots(game_id);
CREATE INDEX IF NOT EXISTS idx_shots_player ON shots(player_id);
CREATE INDEX IF NOT EXISTS idx_shots_zone ON shots(court_zone);


-- ─────────────────────────────────────────────────────────────────────────────
-- Lineups
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lineups (
    id              BIGSERIAL PRIMARY KEY,
    team_id         INTEGER NOT NULL REFERENCES teams(team_id),
    season          VARCHAR(10) NOT NULL,
    player_ids      INTEGER[],                  -- sorted array of 5 player_ids
    player_names    TEXT[],                     -- corresponding names
    minutes         REAL,
    net_rating      REAL,
    off_rating      REAL,
    def_rating      REAL,
    pace            REAL,
    efg_pct         REAL,
    tov_pct         REAL,
    oreb_pct        REAL,
    plus_minus      REAL,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (team_id, season, player_ids)
);
CREATE INDEX IF NOT EXISTS idx_lineups_team_season ON lineups(team_id, season);


-- ─────────────────────────────────────────────────────────────────────────────
-- Odds
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS odds (
    id              BIGSERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    bookmaker       VARCHAR(30) NOT NULL,       -- 'draftkings','fanduel','betmgm', etc.
    market          VARCHAR(30) NOT NULL,       -- 'h2h','spread','totals'
    home_odds       REAL,                       -- American odds (e.g. -110)
    away_odds       REAL,
    spread          REAL,                       -- home spread (e.g. -3.5)
    total           REAL,                       -- over/under total
    is_closing      BOOLEAN DEFAULT FALSE,      -- True if this is the closing line
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_odds_game ON odds(game_id);
CREATE INDEX IF NOT EXISTS idx_odds_closing ON odds(game_id, is_closing) WHERE is_closing = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- Predictions
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS predictions (
    id              BIGSERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    model_name      VARCHAR(50) NOT NULL,       -- 'xgb_pregame_v1', 'lstm_live_v2', etc.
    model_version   VARCHAR(20),
    prediction_type VARCHAR(30) NOT NULL,       -- 'win_prob','spread','total','player_prop'
    player_id       INTEGER REFERENCES players(player_id),  -- for prop predictions
    prop_market     VARCHAR(30),                -- 'points','rebounds','assists'
    value           REAL NOT NULL,              -- predicted value (prob or points)
    confidence_lo   REAL,                       -- 5th percentile
    confidence_hi   REAL,                       -- 95th percentile
    edge            REAL,                       -- model_implied_prob - market_implied_prob
    star_rating     SMALLINT,                   -- 1, 2, or 3 stars
    predicted_at    TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    actual_value    REAL,                       -- filled after game completes
    correct         BOOLEAN                     -- filled after game completes
);
CREATE INDEX IF NOT EXISTS idx_predictions_game ON predictions(game_id);
CREATE INDEX IF NOT EXISTS idx_predictions_model ON predictions(model_name);
CREATE INDEX IF NOT EXISTS idx_predictions_type ON predictions(prediction_type);
CREATE INDEX IF NOT EXISTS idx_predictions_player ON predictions(player_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Player season stats (NBA API — used as model features)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS player_season_stats (
    id              BIGSERIAL PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    season          VARCHAR(10) NOT NULL,
    team_id         INTEGER REFERENCES teams(team_id),
    games_played    SMALLINT,
    minutes_per_game REAL,
    points          REAL,
    rebounds        REAL,
    assists         REAL,
    steals          REAL,
    blocks          REAL,
    turnovers       REAL,
    fg_pct          REAL,
    fg3_pct         REAL,
    ft_pct          REAL,
    ts_pct          REAL,
    usage_rate      REAL,
    off_rating      REAL,
    def_rating      REAL,
    net_rating      REAL,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (player_id, season, team_id)
);
CREATE INDEX IF NOT EXISTS idx_player_stats_season ON player_season_stats(player_id, season);


-- ─────────────────────────────────────────────────────────────────────────────
-- Team season stats (opponent features)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS team_season_stats (
    id              BIGSERIAL PRIMARY KEY,
    team_id         INTEGER NOT NULL REFERENCES teams(team_id),
    season          VARCHAR(10) NOT NULL,
    games_played    SMALLINT,
    wins            SMALLINT,
    losses          SMALLINT,
    win_pct         REAL,
    off_rating      REAL,
    def_rating      REAL,
    net_rating      REAL,
    pace            REAL,
    efg_pct         REAL,
    efg_pct_allowed REAL,
    tov_pct         REAL,
    tov_pct_forced  REAL,
    oreb_pct        REAL,
    dreb_pct        REAL,
    ft_rate         REAL,
    points_per_game REAL,
    opp_points_per_game REAL,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (team_id, season)
);
CREATE INDEX IF NOT EXISTS idx_team_stats_season ON team_season_stats(team_id, season);


-- ─────────────────────────────────────────────────────────────────────────────
-- Views
-- ─────────────────────────────────────────────────────────────────────────────

-- Game context view — joins schedule + team stats for ML feature extraction
CREATE OR REPLACE VIEW v_game_features AS
SELECT
    g.game_id,
    g.season,
    g.game_date,
    g.home_team_id,
    g.away_team_id,
    g.home_won,

    -- Home team context
    g.home_rest_days,
    g.home_back_to_back,
    g.home_second_of_3_in_4,
    g.home_travel_miles,

    -- Away team context
    g.away_rest_days,
    g.away_back_to_back,
    g.away_second_of_3_in_4,
    g.away_travel_miles,

    -- Home team season stats
    hs.off_rating     AS home_off_rating,
    hs.def_rating     AS home_def_rating,
    hs.net_rating     AS home_net_rating,
    hs.pace           AS home_pace,
    hs.efg_pct        AS home_efg_pct,
    hs.win_pct        AS home_win_pct,

    -- Away team season stats
    as2.off_rating    AS away_off_rating,
    as2.def_rating    AS away_def_rating,
    as2.net_rating    AS away_net_rating,
    as2.pace          AS away_pace,
    as2.efg_pct       AS away_efg_pct,
    as2.win_pct       AS away_win_pct,

    -- Differentials (positive = home advantage)
    (hs.net_rating - as2.net_rating)  AS net_rating_diff,
    (hs.off_rating - as2.def_rating)  AS home_off_vs_away_def,
    (as2.off_rating - hs.def_rating)  AS away_off_vs_home_def,

    -- Model outputs
    g.model_home_win_prob,
    g.model_spread

FROM games g
LEFT JOIN team_season_stats hs  ON hs.team_id = g.home_team_id AND hs.season = g.season
LEFT JOIN team_season_stats as2 ON as2.team_id = g.away_team_id AND as2.season = g.season;


-- ─────────────────────────────────────────────────────────────────────────────
-- Player Identity Map (Phase 2)
-- Maps anonymous tracker slots to named NBA players per game clip
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS player_identity_map (
    id              BIGSERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    clip_id         UUID NOT NULL,
    tracker_slot    SMALLINT NOT NULL,
    jersey_number   SMALLINT,
    player_id       INTEGER REFERENCES players(player_id),
    confirmed_frame INTEGER,
    confidence      REAL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (game_id, clip_id, tracker_slot)
);
CREATE INDEX IF NOT EXISTS idx_identity_game ON player_identity_map(game_id);


-- Shot quality view — joins shots + player info for model training
CREATE OR REPLACE VIEW v_shot_features AS
SELECT
    s.id,
    s.game_id,
    s.player_id,
    p.full_name  AS player_name,
    s.team_id,
    s.shot_x,
    s.shot_y,
    s.court_zone,
    s.defender_distance,
    s.team_spacing,
    s.shot_quality,
    s.made,
    s.period,
    s.game_clock_sec,
    g.home_team_id,
    g.away_team_id,
    (s.team_id = g.home_team_id) AS is_home_team
FROM shots s
JOIN games g ON g.game_id = s.game_id
LEFT JOIN players p ON p.player_id = s.player_id;
