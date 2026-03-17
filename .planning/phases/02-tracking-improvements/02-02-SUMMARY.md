---
phase: 02-tracking-improvements
plan: "02"
subsystem: tracking/re-id
tags: [re-id, hsv, jersey-ocr, k-means, tiebreaker, tracking]
dependency_graph:
  requires: [02-01]
  provides: [REID_TIE_BAND, 99-dim appearance embedding, jersey tiebreaker in _reid, reset_slot on eviction]
  affects: [src/tracking/advanced_tracker.py]
tech_stack:
  added: []
  patterns: [conditional import guards, injectable buffer attribute, EMA-compatible embedding extension]
key_files:
  created: []
  modified:
    - src/tracking/advanced_tracker.py
decisions:
  - "Used players[slot].previous_bb is not None as occupancy check (no _slots dict exists)"
  - "Made _jersey_buf injectable via None default rather than constructor arg to avoid coupling"
metrics:
  duration: ~10 min
  completed: 2026-03-16
  tasks_completed: 1/1
  files_modified: 1
---

# Phase 2 Plan 02: HSV Re-ID Upgrade (k-means + jersey tiebreaker) Summary

**One-liner:** Added `_jersey_buf` injectable attribute and `reset_slot()` guard to `_activate_slot()` so stale jersey votes never carry over when a tracker slot is reassigned to a new player.

## What Was Done

Most of this plan's changes were already present in `advanced_tracker.py` from prior work:

- `REID_TIE_BAND = 0.05` constant at module level
- `_HAS_OCR` / `_HAS_VOTING` conditional import guards at top of file
- `_compute_appearance()` returning 99-dim vector (96 HSV histogram + 3 k-means cluster) when `jersey_ocr` is importable, 96-dim fallback otherwise
- `_reid()` accepting `confirmed_jerseys: Optional[Dict[int, int]]` kwarg with jersey-number tiebreaker logic for matches within `REID_TIE_BAND`

Two items were missing and were added in this plan:

### Change 1 — `self._jersey_buf` in `__init__`

```python
self._jersey_buf: Optional[object] = None  # set externally after construction
```

Defaults to `None`. The pipeline injects a shared `JerseyVotingBuffer` instance after construction without requiring it at construction time. This avoids coupling the tracker's constructor to the OCR subsystem.

### Change 2 — `reset_slot()` call in `_activate_slot()`

```python
# Reset jersey voting state for evicted slot (RESEARCH.md Pitfall 3)
if (_HAS_VOTING
        and hasattr(self, "_jersey_buf")
        and self._jersey_buf is not None
        and self.players[slot].previous_bb is not None):
    self._jersey_buf.reset_slot(slot)
```

Placed at the start of `_activate_slot()`, before any slot-assignment logic. The condition `players[slot].previous_bb is not None` is the occupancy check (equivalent to the plan's `slot in self._slots` — the tracker stores occupancy via `previous_bb`, not a separate set). Skips gracefully when `_jersey_buf` is not set or `_HAS_VOTING` is False.

## Deviations from Plan

**1. [Rule 1 - Bug] Occupancy check uses `previous_bb` not `self._slots`**
- **Found during:** Task 1 implementation
- **Issue:** Plan specified `if slot in self._slots` but `AdvancedFeetDetector` has no `_slots` dict. Slot occupancy is tracked via `players[slot].previous_bb is not None`.
- **Fix:** Used `self.players[slot].previous_bb is not None` as the occupancy predicate — semantically identical (a slot is occupied iff its player has a known bbox).
- **Files modified:** `src/tracking/advanced_tracker.py`
- **Commit:** 3ca58cc

## Verification Results

```
tests/test_phase2.py::test_kmeans_color_descriptor PASSED
tests/test_phase2.py::test_reid_with_jersey_tiebreaker PASSED
2 passed in 3.34s
```

Both targeted tests pass. `test_tracker.py` also collected 0 errors (no items in that file were collected in this run due to fixture requirements, consistent with pre-existing behavior).

## Self-Check: PASSED

- `src/tracking/advanced_tracker.py` exists: FOUND
- Commit 3ca58cc exists: FOUND
- `REID_TIE_BAND` at module level: FOUND (line 49)
- `self._jersey_buf = None` in `__init__`: FOUND (line 215)
- `reset_slot` call in `_activate_slot`: FOUND (line 243)
- `confirmed_jerseys` tiebreaker in `_reid`: FOUND (lines 337-344)
- `_compute_appearance` returns 99-dim when OCR available: FOUND (lines 132-136)
