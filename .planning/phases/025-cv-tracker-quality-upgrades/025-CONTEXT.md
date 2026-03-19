# Phase 2.5: CV Tracker Quality Upgrades - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning
**Source:** PRD Express Path (broadcast-detection-ocr spec)

<domain>
## Phase Boundary

This phase delivers two targeted fixes for broadcast footage tracking:
1. **Part A — Detection**: Lower confidence threshold for broadcast footage where players appear smaller/more distant. Add `broadcast_mode` flag so threshold auto-adjusts.
2. **Part B — Jersey OCR**: Fix EasyOCR producing 0 player names by adding CLAHE contrast enhancement, brightness normalisation, 2x resize pass, and confidence threshold filtering.

Out of scope: pose estimation, per-clip homography, ByteTrack, optical flow, YOLOv8x, OSNet re-ID (those are later 2.5 sub-items).

</domain>

<decisions>
## Implementation Decisions

### Part A — Detection (tracker_config.py + player_detection.py + advanced_tracker.py)
- Add `broadcast_mode: bool = True` to `TrackerConfig` defaults in `tracker_config.py`
- When `broadcast_mode=True`, use `conf_threshold=0.35` instead of `0.50`
- Add diagnostic function `count_detections_on_frame(frame_bgr) -> int` in `player_detection.py`
  - Returns detection count at conf=0.35 vs 0.50 (used in tests, no real video needed)
- `_conf_threshold` in `advanced_tracker.py` must respect the broadcast_mode flag

### Part B — Jersey OCR (jersey_ocr.py)
- Before EACH EasyOCR pass, apply in order:
  1. CLAHE contrast enhancement (cv2.createCLAHE)
  2. Brightness normalisation (histogram stretch)
  3. 2x resize of crop before OCR (small crops are the main failure mode)
- Only accept OCR result when easyocr confidence > 0.6 (currently accepts all results including noise)
- Add a THIRD OCR pass on the 2x-resized crop

### Testing
- All tests must work without real video — use synthetic images
- Test: feed a synthetic white-on-black "23" image through OCR pipeline, assert number is recognised
- Tests for `count_detections_on_frame()` using a mock/stub (no real video)
- pytest tests/ -q must be green

### Constraints
- Do NOT touch: rectify_court.py, unified_pipeline.py, court_detector.py
- No video processing, no run_clip.py, no yt-dlp
- Tests only for validation: pytest tests/ -q

### Claude's Discretion
- CLAHE parameters (clipLimit, tileGridSize) — use sensible defaults (clipLimit=2.0, tileGridSize=(8,8))
- Whether to apply preprocessing in-place or return new array
- Test file location (tests/ directory, follow existing pattern)
- How to mock YOLO in count_detections_on_frame tests

</decisions>

<specifics>
## Specific Ideas

**Files to modify:**
- `src/tracking/tracker_config.py` — add `broadcast_mode: bool = True`
- `src/tracking/player_detection.py` — add `count_detections_on_frame(frame_bgr) -> int`
- `src/tracking/jersey_ocr.py` — CLAHE + 2x resize + confidence filter
- `src/tracking/advanced_tracker.py` — wire `_conf_threshold` to `broadcast_mode`

**Key numbers:**
- Old conf_threshold: 0.50
- New broadcast conf_threshold: 0.35
- OCR confidence gate: > 0.6
- Resize factor: 2x
- Target detection count: ~10 players/frame (currently averaging 5)

</specifics>

<deferred>
## Deferred Ideas

- Pose estimation (YOLOv8-pose ankle keypoints) — Phase 2.5-01
- Per-clip homography fix (ISSUE-017) — Phase 2.5-02
- ByteTrack / StrongSORT replacement — Phase 2.5-03
- Optical flow between detections — Phase 2.5-04
- YOLOv8x upgrade — Phase 2.5-05
- OSNet deep re-ID — Phase 2.5-06
- Ball arc + height estimation — Phase 2.5-07
- Player height prior for depth estimation — Phase 2.5-08

</deferred>

---

*Phase: 025-cv-tracker-quality-upgrades*
*Context gathered: 2026-03-17 via PRD Express Path*
