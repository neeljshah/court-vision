# Soccer role ground truth -- G17 v3 (2026-09-02)

300 hand-labelled person crops, three classes: `player`, `referee`, `other`.
This is the first role ground truth ever built for this footage. Its purpose
is to measure the CEILING of role classification on this corpus, not to
produce a shipped filter -- that is a separate, later step for the codex
lane that consumes `labels.csv`.

## Files

- `labels.csv` -- the deliverable: `crop_filename,class,source_frame,clip,box_x1,box_y1,box_x2,box_y2` (pixel coords are in the SOURCE FRAME's own resolution, not the crop).
- `crops/` -- the 300 cropped JPEGs, `crop_NNN_<source_frame>.jpg`.
- `crop_manifest.csv` -- same rows as `labels.csv` minus the class column, plus `det_conf` (detector confidence for that box). Written by the pod job before any labelling; `labels.csv` is `crop_manifest.csv` + my class column.
- `per_frame_counts.csv` -- one row per of the 130 candidate source frames: how many crops were drawn from it and how many raw detector boxes were available there. Evidence for the "sampled evenly" claim below.
- `sheets/sheet_01.jpg` .. `sheet_12.jpg` -- the 12 contact sheets (25 tiles each, tile numbers 1-300 matching `labels.csv` row order / `crop_manifest.csv` index) used to hand-label every crop by eye.

## Source frames (130 total, all decoded, none excluded)

- **100 sealed S1 packet frames**: `scripts/platformkit/a1_artifacts/soccer_s1/frames/S1_0001.jpg`..`S1_0036.jpg` (base packet) and `scripts/platformkit/a1_artifacts/soccer_s1/ext_2026-09-01/frames/S1_0037.jpg`..`S1_0100.jpg` (extension packet). These are the same 100 frames scored in `docs/evidence/tracking/soccer_s1_blind_verdict_n100_2026-09-01.md` (the AMBIGUOUS verdict, paired delta -1.23).
- **30 G08 stream-window render frames**: the first and last decoded frame of each of the 5 stream windows per clip, from `docs/evidence/tracking/soccer_stream_packet_2026-09-02/g08_soccer_*/renders/*.jpg` (3 clips x 5 windows x 2 = 30). Filenames: `<clip>_w0{1..5}_{first,last}`.
- Clips: `soccer_AgspyOj5BPk`, `soccer_DdnvC6-PGYY`, `soccer_kSgNjoaqCpI_1080p` (the same 3 clips used throughout S1 and G08).
- No sealed CSV or packet file was modified. All 130 source images were read-only inputs.

## Detection boxes

The sealed S1 CSVs (`detector_counts_separate.csv`, `detector_counts_separate_ext.csv`) hold only per-frame counts, not box coordinates (confirmed by reading their headers before starting). The G08 stream-window CSVs likewise hold only per-window aggregate stats, no per-box data. So per the task's fallback instruction, boxes were produced fresh, ON THE POD, via `scripts/platformkit/detection/deterministic.py:build_soccer_packet_detector()` -- the same pinned deterministic detector path documented in `docs/evidence/tracking/soccer_detector_determinism_2026-09-01.md` (fixed `yolov8n.pt`, `read_packet_frame` JPEG decode, seeded deterministic inference config). One detector process ran once over all 130 source JPEGs; 1670 raw person boxes came back in total. The pod's cv2 (4.14.0) was not touched.

This means the box coordinates in `labels.csv` are a fresh 2026-09-02 detector run, not a re-read of the old sealed 27/100-mismatched columns -- consistent with the determinism note's finding that sealed counts and fresh packet-JPEG counts are not the same statistic.

## Sampling rule

Seed: **20260902**. Target: 300 crops from 130 source frames, drawn round-robin so no frame and no clip dominates:

1. Shuffle the 130 source frames once with `random.Random(20260902)` -- this fixes the frame visiting order for the whole run; it is NOT sorted by frame index, box count, or detector confidence.
2. For each frame, shuffle its own raw detector boxes with `random.Random(20260902 + frame_position_in_shuffled_order)` -- this means which box gets picked first within a frame is independent of box size or confidence.
3. Walk the shuffled frame order repeatedly (pass 1, pass 2, pass 3, ...), taking exactly one not-yet-taken box from every frame that still has one, until 300 crops are collected.

Result (see `per_frame_counts.csv`): every one of the 130 frames contributed at least 1 crop; **78 frames contributed 2, 46 contributed 3, and 6 contributed only 1** (frames where the detector found exactly one box -- mostly broadcast close-up shots). 6x1 + 78x2 + 46x3 = 300. Per-clip totals: `soccer_DdnvC6-PGYY` 102, `soccer_kSgNjoaqCpI_1080p` 102, `soccer_AgspyOj5BPk` 96 -- balanced within 6 crops of each other across the 3 clips.

This satisfies the "never a head slice, never only the frames the detector already handles well" requirement: frame visiting order is seeded-random, not sorted, and in-frame box choice is seeded-random, not confidence-ranked, so crops cannot cluster on the easy end of the detector's confidence distribution or on early frame indices.

## Labelling method

Read every crop by eye across 12 contact sheets (25 tiles/sheet, `sheets/sheet_01.jpg`..`sheet_12.jpg`, tile index = row order in `labels.csv`). Class boundary used (matches the S1 manual-count protocol in `scripts/platformkit/a1_artifacts/soccer_s1/ext_2026-09-01/labeling_protocol_ext.md`):

- **player** -- outfield players and goalkeepers, any kit color, partial/blurred bodies included when a jersey/kit is identifiable as playing attire.
- **referee** -- referees, assistant referees, 4th officials. Distinguishing cues used: solid all-black kit, or yellow-top/black-shorts kit distinct from any team's actual kit+shorts combination in that clip, an official's chest badge, a raised card, or a clear officiating stance/gesture (e.g. tile 92 and 115 show a visible referee badge and a raised yellow card respectively -- the two most confident referee calls in the set).
- **other** -- everyone/everything else: coaches, bench staff, ball kids, photographers, stewards, spectators, and (see below) a handful of detector false positives that are not a person at all.

## Class counts

| class | n | pct |
|---|---:|---:|
| player | 268 | 89.3% |
| other | 25 | 8.3% |
| referee | 7 | 2.3% |
| **total** | **300** | 100% |

**Referees are genuinely rare on this footage: 7/300 (2.3%).** That is itself a finding about the ceiling, not a sampling defect -- broadcast soccer shows 1 center referee + 2 assistants + occasionally a 4th official against ~22 outfield players + subs + staff, so a referee box is a small fraction of any given frame's person boxes, and only 7 of the 300 seeded-random draws landed on one. A 5-fold CV split on this set will put roughly 1-2 referee examples per fold, which is thin; this is reported honestly rather than padded. `other` at 25/300 (8.3%) is a workable minority class but not a large one either.

## Ambiguous cases and how they were called

36 of 300 crops (12%) were genuinely hard to call from the crop alone and are listed here by tile index (matches `labels.csv` row order) with the call made and the reasoning:

- **9, 11** -- called `other`. Tile 9 is mostly an empty goal frame with a tiny dark blob inside; tile 11 is a dark silhouette partly cut off near a goalpost. Neither clearly shows a player's kit; called non-player figures near the goal (steward/staff) rather than players.
- **14, 22** -- called `referee`. Plain grey (14) and yellow-top/white-or-black-shorts (22) kits that did not match either team's kit+shorts combination seen elsewhere in the same clip's tiles.
- **27, 39** -- called `other`. Dark solid tracksuit-style silhouettes on the touchline, not a numbered team kit.
- **40, 164, 197, 201, 239, 257, 260, 271, 286** -- called `other`, but these are **not humans at all**: a soccer ball (40, 164, 257, 271), an advertising hoarding (197, 201, 286), a broadcast graphic overlay block (260), and a yellow card held up in close-up with no player visible in-frame (239). The `soccer` class-15 YOLO detector fired a person box on the object, not a person. 9/300 crops (3%) are this kind of non-person false positive folded into `other` because the task defines only 3 classes -- **the codex lane should treat `other` as a mixed bucket of real non-player humans plus a real, sport-relevant class of detector false-positives-on-objects**, and may want to split these back out if it changes the 5-fold read.
- **60, 89, 194, 236, 267, 288, 289, 294** -- called `player`. Heavily motion-blurred or very tightly cropped bodies where a kit color was visible but partial identity/role cues were not; called player as the majority-consistent default rather than guessing a rarer class without positive evidence for it.
- **68, 250, 252, 264, 274, 299** -- called `other`. Adult figures in plain dark tracksuits, trousers, or gestures inconsistent with active play (68, 252, 264, 274 are walking/standing on the touchline in non-kit clothing; 250 is a tight face close-up mid-gesture that reads as bench/coach, not a play action; 299 wears a yellow top with trousers, not shorts, which is not a playing kit). None show an unambiguous referee badge or card, so they were called `other` rather than `referee`.
- **109, 189** -- called `referee`. Yellow-top/black-shorts kit matching the confident referee calls (92, 115), even though yellow alone is also a team kit color elsewhere in the set (Colombia); the black-shorts pairing (vs. the team's actual blue or grey shorts) was the deciding cue.
- **127, 130, 181, 191, 203, 232, 266** -- 127 called `player` (a tight arm/shoulder crop, most likely a player reaching for a throw-in). 130, 181, 191, 203, 232 called `other` -- indistinct light/motion-blur blobs with no identifiable kit or body shape, most likely lens flare, an advertising board streak, or a barely-visible background figure; treated as non-diagnostic rather than guessed as player. 266 called `other` -- a blurred round white/yellow streak, most likely a fifth ball-in-motion false positive.

## NOT VERIFIED

- **Single observer, no blind re-label.** All 300 labels were made by one Claude instance reading contact sheets once. There was no second independent labeller and no blind re-adjudication pass, unlike the S1 manual-count protocol (which used a documented blinding procedure). Agreement/disagreement with a second labeller is unmeasured.
- **One broadcaster's framing, 3 clips.** All 130 source frames come from the same 3 World-Cup-style broadcast clips already used throughout S1/G08. Kit colors, camera angles, and referee kit conventions specific to this footage (and to this era's officiating kit) may not generalize to other soccer broadcasts.
- **No IoU/box-quality check.** Boxes are the raw fresh YOLOv8n person detections; no manual box-tightness correction was done. A crop can include the box exactly as the detector drew it, including boxes that are loose, tight, or split a person in two.
- **Referee minority-class size.** At 7/300 (2.3%), any 5-fold CV split will have very few referee examples per fold (roughly 1-2). A per-class precision/recall number on `referee` from this set should be read as high-variance, not a stable estimate.
- **`other` is a mixed bucket.** As noted above, ~9/300 (3%) of `other` are non-person object false positives (ball, ad board, card, graphic overlay), not humans in a non-player role. This was not separated into a 4th class because the task specifies exactly 3 classes; it is flagged here so the codex lane can decide whether to filter or re-split it.
- **~12% of labels (36/300) rest on inference from clothing/posture alone**, not a definitive badge, card, or team-roster cross-check; see the ambiguous-case list above for exactly which ones and why each was called the way it was.
