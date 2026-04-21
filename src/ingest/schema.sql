CREATE TABLE IF NOT EXISTS games (
    game_id       TEXT PRIMARY KEY,
    date          TEXT,
    home          TEXT,
    away          TEXT,
    source        TEXT,
    source_url    TEXT,
    sha256        TEXT,
    duration_s    REAL,
    codec         TEXT,
    fps           REAL,
    quality_tier  TEXT,
    status        TEXT NOT NULL DEFAULT 'queued',
    reject_reason TEXT,
    attempts      INT DEFAULT 0,
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     TEXT NOT NULL REFERENCES games(game_id),
    source      TEXT,
    attempt     INT,
    status      TEXT,
    error       TEXT,
    started_at  TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id      TEXT,
    stage        TEXT,
    level        TEXT,
    payload_json TEXT,
    ts           TEXT
);

CREATE INDEX IF NOT EXISTS idx_games_status       ON games(status);
CREATE INDEX IF NOT EXISTS idx_games_quality_tier ON games(quality_tier);
CREATE INDEX IF NOT EXISTS idx_events_game_ts     ON events(game_id, ts);
