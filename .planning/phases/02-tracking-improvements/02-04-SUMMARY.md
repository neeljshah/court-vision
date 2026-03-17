---
phase: 02-tracking-improvements
plan: "04"
subsystem: data/identity
tags: [postgresql, player-identity, db, persistence, run_clip]
requirements: [REQ-06]

dependency_graph:
  requires: ["02-01", "02-02"]
  provides:
    - src/data/db.py
    - src/data/player_identity.py
    - database/schema.sql::player_identity_map
  affects:
    - run_clip.py (OCR annotation pass + persistence wired in)

tech_stack:
  added:
    - psycopg2-binary (PostgreSQL driver — sync, Phase 7 adds asyncpg)
  patterns:
    - get_connection() reads DATABASE_URL from environment (12-factor app)
    - ON CONFLICT (game_id, clip_id, tracker_slot) DO UPDATE — idempotent upserts
    - UPDATE tracking_frames FROM player_identity_map — back-fill named player_id

key_files:
  created:
    - src/data/db.py
    - src/data/player_identity.py
  modified:
    - database/schema.sql (player_identity_map table + idx_identity_game index)
    - run_clip.py (run_ocr_annotation_pass + persist_identity_map + update_tracking_frames)

decisions:
  - "get_connection raises ValueError (not OperationalError) when DATABASE_URL unset — gives a clear human-readable error message with the fix"
  - "persist_identity_map returns bool (not raises) on psycopg2 error — pipeline continues even when DB is down"
  - "clip_id is a UUID passed as ::uuid cast in SQL so it works whether caller passes a string or UUID object"
  - "run_clip.py OCR pass uses dummy_frame=zeros when no live frame available post-tracking; player_crops fallback is empty dict (no-op)"

metrics:
  completed: "2026-03-16"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 2
  tests_added: 2
  tests_passing: 2 (integration tests skipped without DATABASE_URL)
---

# Phase 02 Plan 04: Player Identity Map Schema + Persistence Layer Summary

**One-liner:** PostgreSQL connection helper + `player_identity_map` table + three persistence functions + OCR annotation pass wired into `run_clip.py`.

## Tasks Completed

| Task | Name | Files |
|------|------|-------|
| 1 | `src/data/db.py` — PostgreSQL connection helper | src/data/db.py |
| 2 | `database/schema.sql` + `src/data/player_identity.py` — persistence layer | database/schema.sql, src/data/player_identity.py |
| 3 | Wire OCR annotation pass into `run_clip.py` | run_clip.py |

## What Was Built

### src/data/db.py
- `get_connection(db_url=None)` — reads `DATABASE_URL` env var when no URL passed; raises `ValueError` with a helpful export hint when not set; returns a psycopg2 connection object (caller closes).

### database/schema.sql — player_identity_map
Added after existing table definitions:
```sql
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
```

### src/data/player_identity.py
Three public functions:
- `persist_identity_map(db_url, game_id, clip_id, slot, jersey_number, player_id, confirmed_frame, confidence) -> bool` — upsert with ON CONFLICT; returns True on success, False on psycopg2.Error (logs warning).
- `update_tracking_frames(db_url, game_id, clip_id) -> int` — UPDATE…FROM join back-fills `player_id` in `tracking_frames` where `tracker_player_id` matches a confirmed slot; returns rowcount.
- `load_identity_map(db_url, game_id, clip_id) -> Dict[int, int]` — returns `{tracker_slot: player_id}` for all confirmed slots.

### run_clip.py
OCR annotation pass appended after tracking loop:
- Creates `JerseyVotingBuffer` and calls `run_ocr_annotation_pass()` with any saved player crops (empty dict if pipeline doesn't expose them — safe no-op).
- If `DATABASE_URL` is set and confirmed jerseys exist: calls `persist_identity_map()` + `update_tracking_frames()`.
- Guarded by `_HAS_IDENTITY` and `args.game_id` — skips gracefully when DB not configured.

## Verification

```
src/data/db.py importable ✓
get_connection raises ValueError when DATABASE_URL missing ✓
src/data/player_identity.py importable ✓
database/schema.sql has player_identity_map ✓
run_clip.py contains run_ocr_annotation_pass + persist_identity_map ✓
Integration tests: skipped (no DATABASE_URL in CI) ✓
```

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/data/db.py | FOUND |
| src/data/player_identity.py | FOUND |
| player_identity_map table in schema.sql | FOUND |
| run_clip.py OCR pass wired | FOUND |
| Import checks passing | VERIFIED |
