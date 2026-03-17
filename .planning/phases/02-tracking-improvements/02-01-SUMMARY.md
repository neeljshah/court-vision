---
phase: 02-tracking-improvements
plan: "01"
subsystem: tracking/identity
tags: [ocr, jersey-number, player-identity, re-id, nba-api, tdd]
requirements: [REQ-04, REQ-05]

dependency_graph:
  requires: []
  provides:
    - src/tracking/jersey_ocr.py
    - src/tracking/player_identity.py
    - src/data/nba_stats.py::fetch_roster
  affects:
    - src/tracking/advanced_tracker.py (future: call run_ocr_annotation_pass per frame)
    - src/data/nba_enricher.py (future: use fetch_roster to resolve player names)

tech_stack:
  added:
    - easyocr==1.7.2 (jersey number OCR — lazy-init GPU reader)
    - scikit-learn==1.7.2 (KMeans for dominant color clustering)
  patterns:
    - TDD red-green cycle per task
    - Singleton pattern for easyocr.Reader
    - Sliding-window voting buffer (deque, maxlen=CONFIRM_THRESHOLD)
    - NBA API JSON cache (existing _safe/_load/_save pattern in nba_stats.py)

key_files:
  created:
    - src/tracking/jersey_ocr.py
    - src/tracking/player_identity.py
    - tests/test_phase2.py
    - tests/conftest.py
  modified:
    - src/data/nba_stats.py (added fetch_roster function)

decisions:
  - "EasyOCR dual-pass (normal + inverted binary) chosen to handle both dark-number-on-light and light-number-on-dark jerseys"
  - "JerseyVotingBuffer uses deque(maxlen=CONFIRM_THRESHOLD) so streak detection is O(1) — no explicit counter needed"
  - "KMeans small-crop fallback (<600 pixels) uses mean HSV to avoid sklearn convergence crash on near-duplicate pixels"
  - "fetch_roster caches with string keys (JSON limitation) and converts back to int on load"

metrics:
  duration: "6 minutes"
  completed: "2026-03-16"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 1
  tests_added: 5
  tests_passing: 5
---

# Phase 02 Plan 01: Jersey OCR Foundation Summary

**One-liner:** EasyOCR singleton + CLAHE preprocessing + KMeans color descriptor + multi-frame voting buffer + `fetch_roster()` cached NBA API call for named player identification.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | jersey_ocr.py — OCR reader + preprocessing + k-means | 7b99380 | src/tracking/jersey_ocr.py |
| 2 | player_identity.py + fetch_roster() | a1e67fb | src/tracking/player_identity.py, src/data/nba_stats.py |

## What Was Built

### src/tracking/jersey_ocr.py
Four public functions forming the OCR and color-clustering pipeline:

- `get_reader()` — lazy-init EasyOCR singleton (GPU, English digits, `verbose=False`)
- `preprocess_crop()` — slices jersey zone (20%-70% of bbox height), upscales to 64px, applies CLAHE + adaptive threshold
- `read_jersey_number()` — dual-pass OCR on normal and inverted binary images; accepts first result with confidence >= 0.65 in range 0-99; wraps entire body in try/except, never raises
- `dominant_hsv_cluster()` — k-means (k=3) on upper 70% of crop; falls back to mean HSV color when crop < 600 pixels to avoid sklearn crash

### src/tracking/player_identity.py
- `JerseyVotingBuffer` — sliding deque per slot (maxlen=CONFIRM_THRESHOLD=3). `record()` appends a read; confirms when all entries are the same non-None integer. `reset_slot()` clears both vote history and confirmed state.
- `run_ocr_annotation_pass()` — frame-level integration helper; skips OCR except every SAMPLE_EVERY_N=5 frames; returns `{slot: confirmed_number_or_None}` for all provided crops

### src/data/nba_stats.py — fetch_roster()
Added after `fetch_game_ids`. Calls `CommonTeamRoster` endpoint, skips entries where NUM is empty or non-numeric (with printed count), caches result as JSON with string keys, converts back to int keys on load.

## Verification

All 5 plan-specified tests pass:

```
tests/test_phase2.py::test_ocr_reader_init        PASSED
tests/test_phase2.py::test_jersey_number_extraction PASSED
tests/test_phase2.py::test_voting_buffer           PASSED
tests/test_phase2.py::test_kmeans_color_descriptor PASSED
tests/test_phase2.py::test_roster_lookup           PASSED
5 passed in 6.83s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] easyocr not installed in basketball_ai env**
- **Found during:** Task 1 GREEN phase
- **Issue:** `import easyocr` raised `ModuleNotFoundError`
- **Fix:** `conda run -n basketball_ai pip install easyocr` (installed easyocr 1.7.2 + dependencies)
- **Commit:** 7b99380

**2. [Rule 3 - Blocking] scikit-learn not installed in basketball_ai env**
- **Found during:** Task 1 GREEN phase (second run)
- **Issue:** `from sklearn.cluster import KMeans` raised `ModuleNotFoundError`
- **Fix:** `conda run -n basketball_ai pip install scikit-learn` (installed scikit-learn 1.7.2)
- **Commit:** 7b99380

**3. [Deviation - Test file replaced by tool] Initial test file (class-based) was replaced**
- Tests were written as pytest classes initially then replaced by a fixture-based stub file created by the tool (matching the plan's `test_ocr_reader_init` / `test_voting_buffer` function name IDs)
- The final test file uses standalone functions with `pytest.importorskip` guards, consistent with the conftest.py fixture infrastructure

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/tracking/jersey_ocr.py | FOUND |
| src/tracking/player_identity.py | FOUND |
| tests/test_phase2.py | FOUND |
| tests/conftest.py | FOUND |
| Commit 7b99380 (jersey_ocr.py) | FOUND |
| Commit a1e67fb (player_identity + fetch_roster) | FOUND |
| 5 tests passing | VERIFIED |
