# Data Pipeline — Ingest System Documentation

*Ingest system — download, queue, processing, quality scoring, sync.*

---

## System Architecture

The ingest system manages the full lifecycle of game video acquisition and processing: download, verification, processing queue, quality scoring, and remote sync.

```
Video sources (YouTube, archive.org)
        │
        ▼
ingest_fetch.py (yt-dlp + cookies)
        │
        ▼
SQLite job queue (data/ingest/queue.db)
[status: queued → verified → processing → processed | failed]
        │
        ▼
ingest_process.py (multi-worker pipeline execution)
        │
        ├── unified_pipeline.py (per game)
        │       └── YOLOv8n → homography → tracking → re-ID → features
        │
        ├── data/tracking/GAME_ID.json
        └── data/events/GAME_ID.json
        │
        ▼
ingest_backfill_quality.py
        │
        ▼
Quality scores → queue.db
        │
        ▼
sync_remote.py (push to B2 storage)
```

---

## CLI Reference

### Status Dashboard

```bash
python scripts/ingest_status.py
```

One-screen dashboard showing:
- Queue depth by state
- Games processed / target
- Currently processing (per worker)
- Failed games with error summary
- Quality score distribution

### Download a Game

```bash
# By game ID (NBA API game ID)
python scripts/ingest_fetch.py --game-id 0022401234

# By URL (YouTube, archive.org, direct)
python scripts/ingest_fetch.py --url "https://youtube.com/watch?v=..."

# Download N games from the queue
python scripts/ingest_fetch.py --count 10

# With YouTube cookie auth (doubles success rate for geo-restricted content)
# Auto-detected if data/videos/youtube_cookies.txt exists
```

**YouTube cookies:** Install "Get cookies.txt LOCALLY" Chrome extension; go to youtube.com while logged in; export cookies → save as `data/videos/youtube_cookies.txt`. The fetcher detects this file automatically and passes `--cookies` to yt-dlp.

### Process Games

```bash
# Process up to N games from verified queue, using K parallel workers
python scripts/ingest_process.py --max-games 20 --parallel 4

# Process a specific game
python scripts/ingest_process.py --game-id 0022401234

# Process with GPU (default behavior when CUDA is available)
python scripts/ingest_process.py --max-games 20 --parallel 4 --cuda 0
```

### Quality Scoring

```bash
# Score all processed games
python scripts/ingest_backfill_quality.py

# Score a specific game
python scripts/ingest_backfill_quality.py --game-id 0022401234
```

Quality metrics:
- `ball_valid_pct`: fraction of frames with valid ball tracking
- `player_coverage`: fraction of 10 players with consistent re-ID
- `homography_stability`: temporal stability of homography transform
- `event_completeness`: detected events vs expected (based on box score)

**Quality thresholds:**
- HIGH (all CV features usable): ball_valid ≥ 80%, player_coverage ≥ 80%, hom_stability ≥ 0.90
- MEDIUM (some CV features usable): ball_valid ≥ 50%, player_coverage ≥ 60%
- LOW (API-only fallback): anything below MEDIUM
- BLOCKED: processing failed entirely

### Migrate Legacy Games

```bash
python -m src.ingest.manifest migrate
```

Imports games from the legacy `phase_g_processed.txt` file into the SQLite queue. Run once after fresh setup.

### Remote Sync (B2)

```bash
# Push tracking data and queue to B2
python scripts/sync_remote.py --push

# Pull from B2 (restore after fresh setup)
python scripts/sync_remote.py --pull

# Auto-sync loop (syncs every 5 minutes)
python scripts/sync_remote.py --loop 5
```

Requires B2 credentials in `.env` (`B2_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET`).

### Unstick Stale Jobs

```bash
# Reset any job stuck in 'processing' state for > 2 hours (crashed workers)
python scripts/reset_stale_jobs.py

# Custom timeout
python scripts/reset_stale_jobs.py --hours 3
```

Jobs that crash during processing leave state as 'processing' indefinitely. This script resets them to 'verified' so they can be retried.

---

## Queue Database Schema

`data/ingest/queue.db` — SQLite

```sql
CREATE TABLE games (
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
    status        TEXT NOT NULL DEFAULT 'queued',  -- queued|verified|processing|processed|failed
    reject_reason TEXT,
    attempts      INT DEFAULT 0,
    created_at    TEXT,
    updated_at    TEXT
);
```

Quality metrics (`ball_valid_pct`, `player_coverage`, `homography_stability`) are not
stored columns -- they are computed on-the-fly from tracking CSVs in
`src/ingest/quality.py` and written into `quality_tier`.

Source: `src/ingest/schema.sql`.

---

## Fetch Strategy (Pass System)

The fetcher uses a 3-pass strategy to maximize download success:

**Pass 1:** Direct yt-dlp from YouTube (with cookies if available)
- Success rate: ~60% without cookies, ~80% with cookies
- Bot detection mitigation: android client header (`--extractor-args "youtube:player_client=android"`)

**Pass 2:** Alternate YouTube search (game title → top result → longer clips)
- Falls back when direct link fails
- Filters: minimum duration 1800 seconds (30 min) for full games

**Pass 2.5:** archive.org fallback
- Searches archive.org for NBA game by date + teams
- Availability varies; success rate ~20%

**Pass 3:** Manual queue (alert for human review)
- Logs URL candidates for manual verification
- Used when all automated passes fail

---

## Processing Pipeline Integration

When `ingest_process.py` runs a game, it invokes the unified pipeline:

```python
from src.pipeline.unified_pipeline import UnifiedPipeline

pipeline = UnifiedPipeline(
    video_path=video_path,
    game_id=game_id,
    output_dir='data/tracking/',
    events_dir='data/events/',
    max_frames=None,  # process entire video
    stride=2,  # process every 2nd frame (30fps → 15fps equivalent)
    batch_size=12,  # YOLO batch size
    n_workers=1,  # per-game workers (parallelism is at game level)
)
pipeline.run()
```

Output: `data/tracking/GAME_ID.json` + `data/events/GAME_ID.json`

---

## Data Persistence Strategy

**Local (development):** All tracking and event data in `data/tracking/` and `data/events/`.

**Remote (B2 + RunPod sync):** After each pod run, sync tracking data to B2 bucket and pull to local. The queue DB tracks what has been processed so re-runs skip already-done games.

**Git:** Do NOT commit tracking JSON files (multi-GB). They are in `.gitignore`. Only commit the queue DB state files.

**Critical files to always sync after pod runs:**
- `data/tracking/*.json` (tracking output)
- `data/events/*.json` (event records)
- `data/ingest/queue.db` (processing state)
- `data/phase_g_processed.txt` (legacy processed list)

---

## Current State (as of 2026-07-15, via `python scripts/ingest_status.py`)

- 307 games total: 81 processed, 200 queued, 26 verified
- Quality tiers: 9 CLEAN, 20 PARTIAL, 46 REJECT (29 usable on quality gate)
- Target: 80 CLEAN
- Next pod run: single RTX 3090, ~7–9 hours, ~$4 budget

After 80 games complete:
1. Backfill quality scores
2. Regenerate prop_residuals.json
3. Retrain Tier 3–4 CV models
4. Validate Δ R² ≥ +0.05 before deployment

---

---

## Multi-Sport Platform Ingest and Capture Daemons

The sections above cover Track 1 (CV video ingest). The sport-blind platform adds
a second ingest surface: keyless statistical + market data for NBA, MLB, soccer,
and tennis, plus two always-on price-capture daemons. All of it is PAPER /
measurement only -- the daemons record prices, never place orders, and no $-edge
is claimed. `data/` is gitignored and local-only.

### Source provenance contract

Each `domains/<sport>/ingest_manifest.py` maps every corpus stem to a `leak_class`
(pre_game / in_game / post_game / reference) and an `sla_minutes` freshness
target. This is the authoritative ingest contract; a builder asserts a feature
only reads a `pre_game` / `reference` source. Derived `asof_*` corpora are
leak-free by construction (snapshot-before-update,
`scripts/platformkit/asof_common.py`). Full per-sport tables:
[../DATA.md](../DATA.md) and [../data_schema.md](../data_schema.md).

### Freshness SLA and staleness handling

- **Manifest SLA** -- refresh-recency target per source (schedule 1440 min, odds
  120 min, MLB pitchers 240 min, NBA in-game linescores 10 min; `None` for
  derived/reference corpora).
- **Runtime guard** (`odds_provider/freshness.py`) -- a quote is FRESH within
  `max_age_sec` of capture; per-market defaults: moneyline/spread 900 s, total
  1800 s, prop 3600 s. An unknown/unparseable timestamp degrades to "unknown" and
  is treated as NOT fresh (conservative). Pure functions, never raise.

### Pregame line/close capture daemon

```bash
# phase-aware cadence (FAST near tip, SLOW otherwise)
python -m scripts.platformkit.odds_provider.line_snapshot_daemon

# fixed interval / explicit sports
python -m scripts.platformkit.odds_provider.line_snapshot_daemon --interval 60 --sports nba,mlb
```

Cadence: 60 s while any game is within 45 min of tip (so a tick lands inside the
30-min lock window = the true close), 900 s otherwise. Output:
`data/cache/line_history/<sport>/<date>.jsonl`. The last at-lock tick IS the
close -- there is no separate "mark" step.

### In-play (live) capture daemon

```bash
# liveness-aware cadence over keyless venues
python -m scripts.platformkit.odds_provider.inplay_snapshot_daemon

# explicit sports / fast interval
python -m scripts.platformkit.odds_provider.inplay_snapshot_daemon --sports nba,mlb,soccer_intl --interval 5
```

Cadence: 5 s while >= 1 game is live (any sport), 120 s idle, exponential backoff
(capped 300 s) on repeated all-sport errors. Liveness is decided venue-natively
from each tick's own commence/close stamps -- **never** via an ESPN id cross-join
(ESPN `event_id` != Kalshi/Polymarket ids; that join previously gated out every
real live tick). Output:
`data/cache/inplay_history/<sport>/<date>.jsonl` + a `_freshness.json` sidecar.

### Operational invariants (binding)

- **Atomic writes** -- both daemons write to a tmp file then `os.replace` over the
  target, so a reader never sees a partial line and a mid-write crash leaves the
  prior file intact.
- **Per-sport isolation** -- a feed/parse error on one sport is caught and logged;
  the loop keeps capturing the other sports. The daemons never raise out of their
  public API.
- **Never fabricate** -- a missing/out-of-range price is skipped, never guessed.
- **Freshness advances only on success** -- a failed poll leaves `_freshness.json`
  untouched so a supervisor/UI can detect a dead feed.
- **ID crosswalk verified, not assumed** -- cross-feed joins (team-name +
  commence-time, `team_resolver.py` / `market_join.py`) must have coverage
  verified; unmatched rows are omitted.

See also: [../DATA.md](../DATA.md) - [../DATA_OUTPUTS.md](../DATA_OUTPUTS.md) -
[../data_schema.md](../data_schema.md) -
[../KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md) - [../INDEX.md](../INDEX.md)

---

*See [runpod-runbook.md](runpod-runbook.md) for pod-specific setup. See [cv-pipeline.md](../architecture/cv-pipeline.md) for what the pipeline does with each video.*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
