# G325 -- producer trace: where a box wholly outside the frame comes from (2026-09-07)
ATTEMPT 2. READ-ONLY trace of `src/` at worktree `track-a6`, base master `946d73a79`. Nothing
under `src/`, `domains/`, `api/`, `kernel/` or `intel/` was edited. Every line number below was
re-read against that blob for this attempt, and the counts are the 122-game re-census.

## The two routes a written box can take
1. **MATCHED (a detection box).** `src/tracking/advanced_tracker.py:1332-1336` reads the YOLO box,
   `x1, y1, x2, y2 = int(box[0]) ...`, and writes `bbox = (y1 - PAD, x1 - PAD, y2 + PAD, x2 + PAD)`
   with `PAD = 15` (`src/tracking/player_detection.py:20`). The clamped copies `x1c/y1c/x2c/y2c` on
   `:1334-1335` are used ONLY for the crop and the footpoint; they are never written back into
   `bbox`. On a match, `src/tracking/advanced_tracker.py:626` assigns that box to the track:
   `p.previous_bb = det["bbox"]`.
2. **COASTING (a Kalman prediction).** At the top of EVERY frame,
   `src/tracking/advanced_tracker.py:1160-1165` overwrites every track's box with the filter's
   prediction: `self._kf_pred[slot] = _kf_predict_bbox(kf)` then
   `self.players[slot].previous_bb = self._kf_pred[slot]`. A track that is not matched this frame
   keeps that value; `:1535` and `:1563` increment its `lost_age` and `:1538` / `:1566` evict it only
   at `MAX_LOST = 90` frames (`:75`), so a lost track can coast for up to 90 frames.

## Which of the two the row carries, readable from the table
`src/pipeline/unified_pipeline.py:2025` writes the `confidence` column as
`conf = max(0.0, 1.0 - self.feet_det._lost_ages.get(slot, 0) / 15)`, and `:2030` writes
`"bbox": p.previous_bb` into the same record. So `confidence == 1.0` means `lost_age == 0`, i.e. the
box came from route 1; `confidence < 1.0` means `lost_age >= 1`, i.e. the box is the route-2
prediction. The census uses `confidence >= 0.999` for MATCHED. **The flag therefore EXISTS** and the
spec's `NOT DETERMINABLE` outcome does not apply.

## Why route 1 CANNOT produce a wholly-outside box (a structural bound, then the measurement)
Ultralytics returns boxes clipped to the image, so `0 <= x1 < x2 <= frame_w` and
`0 <= y1 < y2 <= frame_h`. `PAD` only WIDENS the written box, to `[x1 - 15, x2 + 15]` and
`[y1 - 15, y2 + 15]`. Hence `bbox_x2 = x2 + 15 >= 15 > 0` and
`bbox_x1 = x1 - 15 <= frame_w - 15 < frame_w`, and the same vertically: **no matched row can satisfy
any of the four wholly-outside inequalities.** The census confirms the bound exactly --
**0 of 269,174 matched observations are wholly outside, against 23,408 of 210,984 coasting ones
(~1.1095e-01 of the coasting rows).**

## Why route 2 CAN, and does
`_kf_predict_bbox` (`src/tracking/advanced_tracker.py:132-137`) returns
`(cy - h/2, cx - w/2, cy + h/2, cx + w/2)` from the raw filter state, **with no clamp of any kind**,
and `_make_kf`'s transition matrix (`:104-127`, rows at `:109-116`) advances `cx, cy` by `vx, vy`
each frame while holding `w, h` CONSTANT. A lost track is therefore a fixed-size rectangle
translating at whatever velocity the filter last estimated, for up to 90 frames, with nothing
stopping it at the frame border. Measured extremes across the corpus: `min(bbox_x2) = -7720.8` and
`max(bbox_x1) = 9590.2` on frames at most 1920 px wide, `min(bbox_y2) = -3207.5` and
`max(bbox_y1) = 3407.8` on frames at most 1080 px tall.
A word-boundary search for a clamp on the write path finds none: the only `max(0, ...)` /
`min(frame.shape, ...)` pairs in `advanced_tracker.py` are `:536-539` (a local crop tensor for the
re-ID stage, never written back) and `:1334-1335` (the crop copies above). Nothing between
`:1165` and the CSV writer touches the coordinates.

## The write path, and what the register row got wrong about it
`src/pipeline/unified_pipeline.py:2030` puts `p.previous_bb` into the track record; `:2691` reads it
back (`bbox = track["bbox"]  # stored as (y1, x1, y2, x2)`); `:2723-2726` demuxes it into the four
CSV columns (`"bbox_x1": bbox[1]`, `"bbox_y1": bbox[0]`, `"bbox_x2": bbox[3]`, `"bbox_y2": bbox[2]`)
-- correctly, so the census inequalities read the axes they name. The rows reach disk through
`_checkpoint_csv` (`:3929`, field list `:3968`) and `_export_csv` (`:4020`).
**`scripts/platformkit/track_daemon_done.py` is NOT the writer.** It fsyncs the finished table
(`:42-60`) and reads it for adjudication (`:186-218`); it appends no row and edits no cell. The
G325 register row's phrase "track_daemon_done.py's writer" points at the wrong file, and any drop
belongs in the `unified_pipeline.py` row build, not in the daemon.

## The determination: (b), a Kalman prediction drifting past the border unclamped
The spec asked for (a) detector-emitted, (b) an unclamped coasting prediction, or (c) a units defect
in the `frame_w` / `frame_h` the census divides by.
- **(a) is REJECTED**, by the structural bound above and by 0 of 269,174 matched rows.
- **(b) is the producer**, at `100` pct: all 23,408 wholly-outside rows carry the coasting flag.
- **(c) is REJECTED.** The table's own `source_height` agrees with the ledger's in 122 of 122 games,
  so the height is not in doubt; the `frame_w` from the ledger's `source_resolution` is the only
  unchecked input, and it cannot explain the vertical cases (5,321 rows with `bbox_y2 <= 0` and
  4,330 with `bbox_y1 >= frame_h`) or the magnitudes above. The TOPCUT choice moves the count by
  742 rows out of 23,408 (23,408 primary vs 22,666 under the naive `source_height`), which is the
  whole size of the units question here.

## The consumer that makes it matter
`src/tracking/advanced_tracker.py:1411` sets `foot_y = y2c`, the box bottom, whenever the ankle
keypoint fails its 0.5 confidence test, and `:1426-1432` projects that footpoint through the
homography. A box with no pixels in the frame still yields a footpoint, a projected court position
and a team label -- the team-colour reject at `:1341-1356` runs on the CROP, and G323 measured that
these boxes pass it.

## NOT VERIFIED here
No frame was decoded and no image was looked at; this trace reads source and CSV output only. The
ultralytics clipping property is a documented library behaviour asserted here, not re-measured --
but the census's 0-of-269,174 matched count is an independent empirical check of the same bound.
`imgsz` and `conf` actually used by the pod daemon were not read from a pod run record. Whether
dropping these rows would improve any downstream number is NOT measured and is not claimed.
