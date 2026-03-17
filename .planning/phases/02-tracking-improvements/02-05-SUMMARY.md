---
phase: 02-tracking-improvements
plan: "05"
subsystem: data/video
tags: [video-fetcher, loop-processor, yt-dlp, broadcast-clips, dataset]
requirements: [REQ-08b]

dependency_graph:
  requires: ["02-01", "02-02", "02-03", "02-04"]
  provides:
    - src/data/video_fetcher.py::download_batch
    - scripts/loop_processor.py
  affects:
    - data/videos/ (populated with NBA broadcast clips)
    - data/loop_log.jsonl (processing log)
    - data/processed_clips.json (state file)

tech_stack:
  existing:
    - yt-dlp (video downloader — already in env)
  patterns:
    - CURATED_CLIPS dict: label → yt-dlp search query
    - download_batch(): skip-if-present via existing download_clip skip logic
    - loop_processor.py: single-threaded sequential processing, 180s sleep interval

key_files:
  created:
    - scripts/loop_processor.py
  modified:
    - src/data/video_fetcher.py (CURATED_CLIPS: 5 → 8 entries; added download_batch())

decisions:
  - "CURATED_CLIPS replaced with 8 broadcast-angle queries targeting 2024-25 season side-court footage — better for tracker than top-10 highlight reels (close-up angles break homography)"
  - "loop_processor.py uses subprocess.run with --no-capture-output for conda compatibility on Windows; timeout=600s per clip"
  - "processed_clips.json tracks processed filenames (not full paths) so the state file is portable when data/videos/ is moved"
  - "loop_processor.py passes --frames 300 (not full video) for fast iteration during Phase 2 dataset building"
  - "Bot detection fallback: catch RuntimeError from download_clip and print cookie export instructions"

metrics:
  completed: "2026-03-16"
  tasks_completed: 2
  tasks_total: 3 (Task 3 was human verification checkpoint)
  files_created: 1
  files_modified: 1
  videos_in_data_videos: 10 (verified: data/videos/ has 10 clips)
---

# Phase 02 Plan 05: Video Fetcher Batch Download + Loop Processor Summary

**One-liner:** 8 broadcast-angle search queries added to `CURATED_CLIPS`, `download_batch()` helper function, and `scripts/loop_processor.py` recurring pipeline loop — auto-discovers and processes NBA clips every 3 minutes.

## Tasks Completed

| Task | Name | Files |
|------|------|-------|
| 1 | Update `video_fetcher.py` — CURATED_CLIPS + `download_batch()` | src/data/video_fetcher.py |
| 2 | `scripts/loop_processor.py` — 3-minute recurring loop | scripts/loop_processor.py |
| 3 | Human verification (checkpoint) — 5+ clips verified in data/videos/ | — |

## What Was Built

### src/data/video_fetcher.py

**CURATED_CLIPS** updated from 5 to 8 broadcast-angle search queries:
- Warriors, Celtics, Lakers, Thunder, Nuggets, Heat, Bucks, Suns — all 2024-25 season broadcast queries targeting side-court angles suitable for the tracker.

**`download_batch(clips=None, max_clips=5, max_height=720) -> List[str]`**
- Iterates `CURATED_CLIPS` (or a provided dict), calls `download_clip()` per entry.
- Stops after `max_clips` successful downloads.
- Catches `RuntimeError` (yt-dlp bot detection) per clip and continues to next, printing cookie export instructions.
- Returns list of local paths.

### scripts/loop_processor.py

Standalone recurring pipeline script:

- `load_processed() / save_processed()` — read/write `data/processed_clips.json` (state file, tracks processed filenames).
- `discover_clips()` — finds unprocessed `.mp4`/`.mkv`/`.webm` files in `data/videos/`, sorted oldest first.
- `process_clip(clip_path)` — runs `conda run -n basketball_ai python run_clip.py --video <path> --frames 300` via `subprocess.run(timeout=600)`; returns result dict with clip name, success flag, stdout/stderr tail, and UTC timestamp.
- `log_result(result)` — appends one JSON line to `data/loop_log.jsonl`.
- `run_loop(once, download_first)` — main loop: optional download → discover → process → log → sleep 180s.
- CLI: `--once` (single pass), `--download` (download first).

## Verification

```
CURATED_CLIPS: 8 entries ✓
download_batch importable ✓
loop_processor.py --once runs without error ✓
data/videos/ has 10 clips (verified manually) ✓
data/loop_log.jsonl created after --once run ✓
```

## Notes on shot_log_enriched (REQ-08b partial)

`loop_processor.py` does NOT pass `--game-id` automatically, so `shot_log_enriched` is not populated from the loop. To enrich shots, run manually:
```bash
python run_clip.py --video data/videos/<clip>.mp4 --game-id <NBA_GAME_ID> --frames 300
```
Full REQ-08b (enriched shots) requires NBA game ID lookup from video metadata — deferred to Phase 5 (automated game processing).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| CURATED_CLIPS has 8 entries | VERIFIED |
| download_batch() importable | VERIFIED |
| scripts/loop_processor.py runs --once | VERIFIED |
| data/videos/ has 10+ clips | VERIFIED |
| data/loop_log.jsonl created | VERIFIED |
