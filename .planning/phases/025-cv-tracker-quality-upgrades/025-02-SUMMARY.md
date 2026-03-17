---
phase: "2.5"
plan: "02"
subsystem: "CV Tracker / Jersey OCR"
tags: [ocr, preprocessing, brightness-normalisation, upscale]
dependency_graph:
  requires: []
  provides: [jersey_ocr.preprocess_crop.brightness_norm, jersey_ocr.read_jersey_number.2x_pass]
  affects: [src/tracking/jersey_ocr.py, src/tracking/advanced_tracker.py]
tech_stack:
  added: []
  patterns: [histogram-stretch, multi-pass-ocr]
key_files:
  created: []
  modified:
    - src/tracking/jersey_ocr.py
decisions:
  - "Added cv2.normalize histogram stretch between CLAHE and adaptive threshold for consistent brightness range"
  - "Added 3rd OCR pass on 2x-upscaled image using INTER_CUBIC to recover small broadcast crops under 32px wide"
  - "_OCR_CONF_MIN kept at 0.65 — already exceeds minimum 0.60 requirement"
metrics:
  duration: "5 minutes"
  completed_date: "2026-03-17"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
---

# Phase 2.5 Plan 02: Jersey OCR Brightness Normalisation + 2x Resize Pass Summary

**One-liner:** EasyOCR dual-pass upgraded to triple-pass with histogram stretch preprocessing — targets 0-jersey-number rows in 29K tracking records caused by low-contrast and small-crop failures.

## What Was Built

Two targeted improvements to `src/tracking/jersey_ocr.py`:

### Task B1 — Brightness Normalisation in preprocess_crop()

Added a histogram stretch step between CLAHE and adaptive threshold:

```python
# Brightness normalisation — histogram stretch to full 0-255 range
e_min, e_max = int(enhanced.min()), int(enhanced.max())
if e_max > e_min:
    enhanced = cv2.normalize(enhanced, None, 0, 255, cv2.NORM_MINMAX)
```

This ensures CLAHE output — which may be compressed into a narrow intensity band — always spans the full 0-255 range before binarization. Particularly effective on murky or washed-out broadcast frames.

### Task B2 — 3rd OCR Pass on 2x-Resized Crop in read_jersey_number()

Added a third OCR pass immediately after the inverted pass:

```python
# Third pass: 2x upscale — small broadcast crops (< 32px wide) fail at native size
h2x, w2x = preprocessed.shape[0] * 2, preprocessed.shape[1] * 2
resized_2x = cv2.resize(preprocessed, (w2x, h2x), interpolation=cv2.INTER_CUBIC)
results_2x = reader.readtext(resized_2x, **ocr_kwargs)

for results in (results_normal, results_inverted, results_2x):
```

EasyOCR struggles with crops narrower than ~32px. The 2x upscale with INTER_CUBIC gives the digit glyphs more pixels to detect, recovering reads that the native-resolution passes miss.

## Verification

```
python -c "from src.tracking.jersey_ocr import preprocess_crop, read_jersey_number; import numpy as np; r = preprocess_crop(np.zeros((120,60,3), dtype='uint8')); assert r.ndim == 2; print('OK')"
```
Output: `OK`

## Commits

| Hash | Description |
|------|-------------|
| 8fc30f8 | feat(025-02): add brightness normalisation + 2x resize OCR pass in jersey_ocr |

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- [x] `src/tracking/jersey_ocr.py` exists and is modified
- [x] commit 8fc30f8 exists
- [x] preprocess_crop() contains `cv2.normalize` call
- [x] read_jersey_number() iterates over `(results_normal, results_inverted, results_2x)`
- [x] `_OCR_CONF_MIN` unchanged at 0.65
- [x] import check passes cleanly
