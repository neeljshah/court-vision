# G322 attempt 2 -- producer trace: where a box taller than half the frame enters (2026-09-07)
READ-ONLY trace of `src/` at worktree `track-a21`. Nothing under `src/`, `domains/`, `api/`,
`kernel/` or `intel/` was edited. Every line below was re-read from the worktree blob named beside
it, not copied forward from attempt 1:
`src/tracking/advanced_tracker.py` blob `1b3bf72daf98b9b9ee49a9a9114e871d48bd18e6`,
`src/pipeline/unified_pipeline.py` blob `4459712b9fb23e4a7cad40023c48ea2bec0a5443`,
`src/tracking/video_handler.py` blob `19ec13b5bb70b4d1e4ba70a49c44245196544f83`,
`src/tracking/player_detection.py` blob `8d524e313c7ceb8c9476678cff5861c1e6273604`.

## The route, in order
1. `src/pipeline/unified_pipeline.py:1689` -- `frame = frame[TOPCUT:]`, `TOPCUT = 60`
   (`src/tracking/video_handler.py:11`, re-declared `src/tracking/advanced_tracker.py:1825`). The
   detector therefore sees a `(source_height - 60) x source_width` crop: 1020x1920, 660x1280 or
   300x640 for the three resolutions in this corpus. **Every `bbox_*` value in
   `tracking_data.csv` is in that cropped space**, which is why the census also reports the cut
   against `source_height - 60`.
2. `src/tracking/advanced_tracker.py:1225-1228` -- the detection call:
   `self.model(_dimgs, classes=[0], conf=self._fill_conf_threshold, verbose=False, imgsz=_imgsz,
   half=self._use_half, device=_dev)`, with `_imgsz = getattr(self, "_infer_imgsz", self._yolo_imgsz)`
   at `:1188` and `self._yolo_imgsz = int(_cfg.get("yolo_imgsz", 640))` at `:261`. The pose branch at
   `:1216-1219` is the same call with `imgsz=self._pose_imgsz` (`:274`, default 640). **Single class
   (`classes=[0]`, person): there is no class merge on this route.** NMS is ultralytics' default --
   `iou` is never passed, so the default applies; nothing in this repo overrides it.
3. `src/tracking/advanced_tracker.py:1240` -- `boxes_xyxy = yolo_results[0].boxes.xyxy...`, then
   `:1332-1339` builds the detection list:
   `x1, y1, x2, y2 = int(box[0]) ...` / `y1c = max(0, y1); y2c = min(frame.shape[0], y2)` /
   `bbox = (y1 - PAD, x1 - PAD, y2 + PAD, x2 + PAD)`. `PAD = 15`
   (`src/tracking/player_detection.py:20`), so the WRITTEN box is **30 px taller than the detector's
   own box**. The only rejection in this loop is `if bgr_crop.size == 0: continue` (`:1338-1339`).
   CORRECTION AT LANDING (verifier `G322_VERIFY_2026-09-08.md` NEW GAP, codex-sol): that empty-crop
   `continue` is NOT the only rejection in this loop -- `:1355-1356` also skips a box whose
   team-colour classification comes back empty (`if not team: continue`). Neither rejection is a
   size, area, aspect or frame-fraction gate, so the ENTRY POINT determination below is unchanged.
4. **NO SIZE FILTER EXISTS.** `grep -rnE "min_area|MAX_AREA|min_h|MIN_H|max_area|box_h|aspect"` over
   `src/tracking/advanced_tracker.py`, `src/tracking/player_detection.py` and
   `src/pipeline/unified_pipeline.py` returns nothing (re-run 2026-09-07 against the blobs above,
   exit status 1, no output). No height, area, aspect-ratio or frame-fraction gate stands between
   the YOLO call and the CSV writer.
5. `src/tracking/advanced_tracker.py:1409-1424` -- the footpoint that inherits the box:
   `foot_y = y2c  # fallback: bbox bottom` at `:1411`, replaced by the mean ankle keypoint only when
   `ankle_confs > 0.5` (`:1419-1421`). The code's own comment at `:263-264` records that at
   `imgsz=640` ankle confidence is about `0.005` on 640x360 broadcast, so on the 55 640x360 games of
   this census the bbox-bottom fallback is the normal path. `:1426-1432` projects `(head_x, foot_y)`
   through the homography, so an oversized box moves the projected court position by its own error.
6. `src/tracking/advanced_tracker.py:1160-1165` -- at the top of EVERY frame,
   `self.players[slot].previous_bb = self._kf_pred[slot]`; a matched track gets the detection box
   back at `:626` (`p.previous_bb = det["bbox"]`). `src/pipeline/unified_pipeline.py:2030` writes
   `"bbox": p.previous_bb` into the track record, `:2691` reads it and `:2723-2726` writes
   `bbox_x1..bbox_y2`. So an UNMATCHED (coasting) row carries a Kalman prediction, not a detection.

## The determination: primarily (a); (b) contributes via PAD; (c) is confined to the off-frame tail
The spec asked for (a) detector-emitted, (b) grown after detection, or (c) a coordinate-space
mismatch. The census answers with numbers, over 107 games and 412,124 observations:
- **(a) is primary.** Pooled, the `> 0.5` share is **44609/230102 (~1.9387e-1) on MATCHED rows and
  35451/182022 (~1.9476e-1) on COASTING rows** -- statistically the same box-height distribution on
  both sides of the match, and the matched share exceeds the coasting share in 41 of 107 games.
  That equality is what constant-size coasting predicts: `_make_kf` (`:104-127`) keeps `w` and `h`
  CONSTANT in the transition matrix (only `cx, cy` carry velocity), so a coasting box cannot grow
  taller -- it can only carry forward the size the detector last emitted. Coasting is therefore a
  carrier, not a producer. ATTEMPT-1 NOTE, stated rather than buried: on the smaller 71-game corpus
  the matched share was the higher of the two; on 107 games the two are level. The structural
  argument (constant `w`, `h`) is what carries (a), not the sign of that difference.
- **(b) contributes, and is bounded.** Removing the `PAD` (30 px) drops the pooled share from
  **80060/412124 (~1.9426e-1) to 66195/412124 (~1.6062e-1)**. On a 640x360 source, 30 px is about
  8 pct of frame height, so PAD is a material but minority contributor.
- **(c) is REJECTED for the bulk and REAL in the off-frame tail.** The 20 rendered panels confirm
  the post-TOPCUT reading: in every panel whose box bounds an identifiable person, the `y + 60`
  rectangle bounds that person and the no-offset rectangle sits 60 px above them. But
  `max(bbox_y2)` exceeds `source_height` in **102 of 107 games** (up to 3,620.49 on a 1,080-high
  frame, `g220c_jh3fnwMi7dM`). Those are the coasting rows of step 6 drifting off-frame at constant
  velocity, plus PAD -- a tail, not a units defect on the bulk. Both readings are reported and no
  rule was moved.

## ENTRY POINT, pinned
`src/tracking/advanced_tracker.py:1225-1228` emits person boxes of any size on any shot, and
`src/tracking/advanced_tracker.py:1332-1339` admits every one of them to the track list -- there is
no size gate in the route (item 4) -- after which `PAD` adds 30 px at `:1336` and
`src/tracking/advanced_tracker.py:1411` turns the box bottom into the footpoint. The detector is
behaving correctly on close-up shots (5 of 20 panels are one genuinely close player); it is the
ABSENCE of a shot-type or box-size gate downstream, not a detector fault, that lets those rows reach
the table beside wide-shot rows and be treated identically by everything reading `bbox_y2`.

## NOT VERIFIED here
No frame was re-decoded through the tracker; this trace reads source and CSV output only. The
`imgsz` and `conf` actually used by the pod daemon were not read from a pod run record -- they are
the code defaults (`640`, `self._fill_conf_threshold`) and could be overridden by `_cfg`. The
matched/coasting split is inferred from `confidence == 1.0` meaning `lost_age == 0`; it is not read
from a per-row match flag, because the CSV writes none. Whether a size gate would improve any
downstream number is NOT measured and is not claimed.
