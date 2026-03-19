-- Migration 001: Make game_id nullable in tracking_frames
--
-- Allows pipeline runs without --game-id to still persist tracking rows to
-- PostgreSQL (game_id = NULL).  Rows can be linked to a game retroactively
-- by updating game_id once the game ID is known.
--
-- Apply with:
--   psql -U postgres -d nba_ai -f database/migrations/001_tracking_nullable_game_id.sql

ALTER TABLE tracking_frames ALTER COLUMN game_id DROP NOT NULL;

-- Index to quickly find unlinked rows (for retroactive enrichment)
CREATE INDEX IF NOT EXISTS idx_frames_unlinked
    ON tracking_frames(clip_id)
    WHERE game_id IS NULL;
