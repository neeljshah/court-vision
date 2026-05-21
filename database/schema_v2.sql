-- ─────────────────────────────────────────────────────────────────────────────
-- NBA AI System — Multi-Sport Data Lake (Schema v2, additive layer)
--
-- This file defines ONLY NEW tables not present in schema.sql.
-- It MUST NOT redefine teams / players / games / odds / shots.
--
-- Design goals:
--   • Multi-sport: every table carries a `sport` TEXT discriminator.
--   • PKs are composite-natural, or a single ingester-supplied TEXT id — no
--     SERIAL / GENERATED IDENTITY, so the DDL applies cleanly on BOTH
--     PostgreSQL 14+ AND the SQLite 3.x fallback.
--   • Portable column types only: TEXT, INTEGER, REAL, BOOLEAN, TIMESTAMP.
--     Timestamp defaults use CURRENT_TIMESTAMP (standard SQL, both backends).
--     JSON payload columns use TEXT here; on PostgreSQL swap TEXT → JSONB.
--   • Every statement uses IF NOT EXISTS for idempotent re-runs.
--
-- Apply with:
--   psql -U postgres -d nba_ai -f database/schema_v2.sql
-- or via:
--   python scripts/migrate_v2.py
-- ─────────────────────────────────────────────────────────────────────────────


-- ─────────────────────────────────────────────────────────────────────────────
-- Sports registry
-- One row per sport this system ingests data for.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sports (
    sport           TEXT PRIMARY KEY,          -- 'nba', 'nfl', 'mlb', 'nhl', 'ncaab'
    display_name    TEXT NOT NULL,
    active          BOOLEAN DEFAULT TRUE,
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- portable: works on PostgreSQL + SQLite
);

CREATE INDEX IF NOT EXISTS idx_sports_active ON sports(active);


-- ─────────────────────────────────────────────────────────────────────────────
-- Box scores  (one row per player per game, any sport)
-- game_id / player_id are natural text IDs — no hard FK into NBA-specific tables
-- so that non-NBA sports can share this table without referential errors.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS box_scores (
    sport           TEXT    NOT NULL,
    game_id         TEXT    NOT NULL,          -- matches games.game_id for NBA rows
    player_id       TEXT    NOT NULL,          -- text so non-NBA IDs (e.g. 'NFL-123') fit
    team_id         TEXT,
    game_date       TEXT,                      -- ISO date string 'YYYY-MM-DD'
    season          TEXT,

    -- Core stat block (null-safe — missing stats stay NULL)
    minutes         REAL,
    points          INTEGER,
    rebounds        INTEGER,
    assists         INTEGER,
    steals          INTEGER,
    blocks          INTEGER,
    turnovers       INTEGER,
    fouls           INTEGER,
    fg_made         INTEGER,
    fg_attempted    INTEGER,
    fg3_made        INTEGER,
    fg3_attempted   INTEGER,
    ft_made         INTEGER,
    ft_attempted    INTEGER,
    plus_minus      REAL,

    -- Sport-specific overflow (TEXT here; use JSONB on PostgreSQL)
    extras          TEXT,                      -- JSON payload for sport-specific stats

    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (sport, game_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_box_sport       ON box_scores(sport);
CREATE INDEX IF NOT EXISTS idx_box_game        ON box_scores(sport, game_id);
CREATE INDEX IF NOT EXISTS idx_box_player      ON box_scores(sport, player_id);
CREATE INDEX IF NOT EXISTS idx_box_game_date   ON box_scores(game_date);
CREATE INDEX IF NOT EXISTS idx_box_season      ON box_scores(season);


-- ─────────────────────────────────────────────────────────────────────────────
-- Play-by-play  (one row per discrete event in a game)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS play_by_play (
    sport           TEXT    NOT NULL,
    game_id         TEXT    NOT NULL,
    event_num       INTEGER NOT NULL,          -- monotonically increasing within a game

    period          INTEGER,
    clock_display   TEXT,                      -- '10:24' — raw string from source
    clock_seconds   REAL,                      -- normalized seconds remaining in period

    event_type      TEXT,                      -- 'shot','foul','turnover','rebound','sub',...
    event_desc      TEXT,                      -- raw description from source API
    player_id       TEXT,                      -- primary actor
    player_id_2     TEXT,                      -- secondary actor (e.g. assister)
    team_id         TEXT,

    home_score      INTEGER,
    away_score      INTEGER,

    -- Location (court coordinates, sport-specific scale)
    loc_x           REAL,
    loc_y           REAL,

    -- Enrichment flags
    is_scoring      BOOLEAN DEFAULT FALSE,
    shot_made       BOOLEAN,
    shot_value      INTEGER,                   -- 1, 2, or 3

    -- Overflow payload (TEXT here; use JSONB on PostgreSQL)
    extras          TEXT,

    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (sport, game_id, event_num)
);

CREATE INDEX IF NOT EXISTS idx_pbp_sport       ON play_by_play(sport);
CREATE INDEX IF NOT EXISTS idx_pbp_game        ON play_by_play(sport, game_id);
CREATE INDEX IF NOT EXISTS idx_pbp_player      ON play_by_play(sport, player_id);
CREATE INDEX IF NOT EXISTS idx_pbp_event_type  ON play_by_play(event_type);


-- ─────────────────────────────────────────────────────────────────────────────
-- Odds lines  (multi-sport, time-series market prices)
-- Extends rather than replaces the existing NBA-specific `odds` table.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS odds_lines (
    id              TEXT PRIMARY KEY,       -- ingester-supplied UUID (portable across PostgreSQL + SQLite)
    sport           TEXT    NOT NULL,
    game_id         TEXT    NOT NULL,
    bookmaker       TEXT    NOT NULL,          -- 'draftkings','fanduel','betmgm', etc.
    market          TEXT    NOT NULL,          -- 'h2h','spread','totals'

    -- Price columns (American odds)
    home_odds       REAL,
    away_odds       REAL,
    draw_odds       REAL,                      -- for soccer / hockey

    spread_home     REAL,                      -- home spread (e.g. -3.5)
    spread_away     REAL,
    total_over      REAL,
    total_under     REAL,

    is_opening      BOOLEAN DEFAULT FALSE,
    is_closing      BOOLEAN DEFAULT FALSE,

    recorded_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_odds_lines_sport    ON odds_lines(sport);
CREATE INDEX IF NOT EXISTS idx_odds_lines_game     ON odds_lines(sport, game_id);
CREATE INDEX IF NOT EXISTS idx_odds_lines_book     ON odds_lines(bookmaker);
CREATE INDEX IF NOT EXISTS idx_odds_lines_closing  ON odds_lines(sport, game_id, is_closing);
CREATE INDEX IF NOT EXISTS idx_odds_lines_recorded ON odds_lines(recorded_at);


-- ─────────────────────────────────────────────────────────────────────────────
-- Prop lines  (player proposition market prices, any sport)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prop_lines (
    id              TEXT PRIMARY KEY,
    sport           TEXT    NOT NULL,
    game_id         TEXT    NOT NULL,
    player_id       TEXT    NOT NULL,
    bookmaker       TEXT    NOT NULL,
    market          TEXT    NOT NULL,          -- 'points','rebounds','assists','passing_yards',...

    line            REAL    NOT NULL,          -- e.g. 24.5
    over_odds       REAL,                      -- American odds for over
    under_odds      REAL,                      -- American odds for under

    is_opening      BOOLEAN DEFAULT FALSE,
    is_closing      BOOLEAN DEFAULT FALSE,

    recorded_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prop_lines_sport    ON prop_lines(sport);
CREATE INDEX IF NOT EXISTS idx_prop_lines_game     ON prop_lines(sport, game_id);
CREATE INDEX IF NOT EXISTS idx_prop_lines_player   ON prop_lines(sport, player_id);
CREATE INDEX IF NOT EXISTS idx_prop_lines_market   ON prop_lines(market);
CREATE INDEX IF NOT EXISTS idx_prop_lines_closing  ON prop_lines(sport, game_id, player_id, is_closing);
CREATE INDEX IF NOT EXISTS idx_prop_lines_recorded ON prop_lines(recorded_at);


-- ─────────────────────────────────────────────────────────────────────────────
-- Prop outcomes  (settled actual values, links to prop_lines for CLV calc)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prop_outcomes (
    sport           TEXT    NOT NULL,
    game_id         TEXT    NOT NULL,
    player_id       TEXT    NOT NULL,
    market          TEXT    NOT NULL,          -- must match prop_lines.market

    actual_value    REAL    NOT NULL,
    closing_line    REAL,                      -- best closing line at settlement
    result          TEXT,                      -- 'over','under','push','dnp'
    clv             REAL,                      -- model_line - closing_line (+ = good)

    settled_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (sport, game_id, player_id, market)
);

CREATE INDEX IF NOT EXISTS idx_prop_outcomes_sport   ON prop_outcomes(sport);
CREATE INDEX IF NOT EXISTS idx_prop_outcomes_game    ON prop_outcomes(sport, game_id);
CREATE INDEX IF NOT EXISTS idx_prop_outcomes_player  ON prop_outcomes(sport, player_id);
CREATE INDEX IF NOT EXISTS idx_prop_outcomes_market  ON prop_outcomes(market);


-- ─────────────────────────────────────────────────────────────────────────────
-- Injuries  (player availability log, multi-sport)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS injuries (
    id              TEXT PRIMARY KEY,
    sport           TEXT    NOT NULL,
    player_id       TEXT    NOT NULL,
    team_id         TEXT,
    game_id         TEXT,                      -- NULL if not game-specific
    report_date     TEXT    NOT NULL,          -- ISO date 'YYYY-MM-DD'

    status          TEXT    NOT NULL,          -- 'out','doubtful','questionable','probable','active'
    injury_type     TEXT,                      -- 'knee','ankle','illness', etc.
    detail          TEXT,                      -- raw note from source
    source          TEXT,                      -- 'rotoworld','espn','nba_api'

    recorded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_injuries_sport       ON injuries(sport);
CREATE INDEX IF NOT EXISTS idx_injuries_player      ON injuries(sport, player_id);
CREATE INDEX IF NOT EXISTS idx_injuries_game        ON injuries(sport, game_id);
CREATE INDEX IF NOT EXISTS idx_injuries_date        ON injuries(report_date);
CREATE INDEX IF NOT EXISTS idx_injuries_status      ON injuries(status);


-- ─────────────────────────────────────────────────────────────────────────────
-- News items  (headlines / injury reports / transaction feed, any sport)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news_items (
    id              TEXT PRIMARY KEY,
    sport           TEXT    NOT NULL,
    player_id       TEXT,                      -- NULL if team/league news
    team_id         TEXT,
    game_id         TEXT,                      -- NULL if not game-specific

    headline        TEXT    NOT NULL,
    body            TEXT,
    source          TEXT,                      -- 'rotoworld','espn','twitter'
    url             TEXT,
    sentiment       REAL,                      -- -1.0 … 1.0 (model output)
    impact          TEXT,                      -- 'injury','suspension','trade','lineup'

    published_at    TIMESTAMP,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_news_sport      ON news_items(sport);
CREATE INDEX IF NOT EXISTS idx_news_player     ON news_items(sport, player_id);
CREATE INDEX IF NOT EXISTS idx_news_team       ON news_items(sport, team_id);
CREATE INDEX IF NOT EXISTS idx_news_published  ON news_items(published_at);
CREATE INDEX IF NOT EXISTS idx_news_impact     ON news_items(impact);


-- ─────────────────────────────────────────────────────────────────────────────
-- Scraper runs  (ingester resumability log)
-- One row per scraper execution.  `last_key` stores the last successfully
-- ingested cursor (game_id, date, offset, etc.) so incremental scrapers can
-- pick up where they left off without re-fetching already-written rows.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scraper_runs (
    id              TEXT PRIMARY KEY,
    sport           TEXT    NOT NULL,
    source          TEXT    NOT NULL,          -- 'nba_api','odds_api','rotoworld', etc.
    run_type        TEXT    DEFAULT 'full',    -- 'full' | 'incremental'

    run_started_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_finished_at TIMESTAMP,

    status          TEXT    DEFAULT 'running', -- 'running','success','partial','error'
    rows_written    INTEGER DEFAULT 0,
    last_key        TEXT,                      -- resume cursor (game_id, date, page, etc.)

    -- Error details on failure
    error_message   TEXT,

    -- Metadata / configuration snapshot (TEXT here; use JSONB on PostgreSQL)
    run_config      TEXT
);

CREATE INDEX IF NOT EXISTS idx_scraper_sport    ON scraper_runs(sport);
CREATE INDEX IF NOT EXISTS idx_scraper_source   ON scraper_runs(sport, source);
CREATE INDEX IF NOT EXISTS idx_scraper_status   ON scraper_runs(status);
CREATE INDEX IF NOT EXISTS idx_scraper_started  ON scraper_runs(run_started_at);
