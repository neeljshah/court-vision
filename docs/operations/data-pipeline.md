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
[state: pending → downloading → downloaded → verified → processing → processed | failed]
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
    game_id TEXT PRIMARY KEY,
    url TEXT,
    state TEXT,  -- pending|downloading|downloaded|verified|processing|processed|failed
    priority INTEGER DEFAULT 0,
    video_path TEXT,
    quality_score REAL,
    quality_tier TEXT,  -- HIGH|MEDIUM|LOW|BLOCKED
    ball_valid_pct REAL,
    player_coverage REAL,
    error_message TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    processed_at TIMESTAMP
);
```

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

## Current State (Session 40)

- 29 usable games (9 CLEAN + 20 PARTIAL on quality gate) of 75 attempted
- Target: 80 CLEAN
- Next pod run: single RTX 3090, ~7–9 hours, ~$4 budget

After 80 games complete:
1. Backfill quality scores
2. Regenerate prop_residuals.json
3. Retrain Tier 3–4 CV models
4. Validate Δ R² ≥ +0.05 before deployment

---

*See [runpod-runbook.md](runpod-runbook.md) for pod-specific setup. See [cv-pipeline.md](../architecture/cv-pipeline.md) for what the pipeline does with each video.*
