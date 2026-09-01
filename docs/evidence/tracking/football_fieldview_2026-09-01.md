# Football field-view gate at IMAGE_PX_DECLARED -- build and re-measurement

**Date:** 2026-09-01. **Lane:** T4b-FOOTBALL-FIELDVIEW.
**Follows:** `docs/evidence/tracking/football_imagepx_snap_2026-09-01.md` (lane T4),
which measured hand-verified snap precision **3/20 = 15.0%** and diagnosed the
cause: whole-frame motion energy measures the camera, and football has no
field-view test at this rung. This lane built that test and re-measured.

## Verdict

**REJECT.** The field-view gate works as a shot classifier. It does not rescue
the snap detector.

| Claim | Before (T4, ungated) | After (this lane, gated) |
|---|---|---|
| Hand-verified snap precision | **3/20 = 15.0%** [5.2, 36.0] | **4/30 = 13.3%** [5.3, 29.7] |
| Detections not on live football | 13/20 = 65.0% [43.3, 81.9] | **7/30 = 23.3%** [11.8, 40.9] |
| Precision conditional on live football | 3/7 = 42.9% [15.8, 75.0] | 4/23 = 17.4% [7.0, 37.1] |
| Median inter-snap gap (A / B) | 7.9 s / 8.0 s | 21.5 s / 26.4 s |
| Detections kept (A / B) | 83 / 83 | 25 / 22 |

Brackets are 95% Wilson intervals. The gate does exactly the job it was built
for -- it cut the share of detections that were never looking at football from
65% to 23%, and it pulled detection density from ~4x too fast to roughly the
real 30-40 s play cycle. **Snap precision did not improve**: 15.0% -> 13.3%,
intervals almost entirely overlapping, and the point estimate moved the wrong
way.

The reason is visible in the failure decomposition. Removing camera cuts to
close-ups exposed the *other* failure the T4 memo had already named and which
the tiny ungated conditional sample (n=7) had hidden: on a live wide field
view, a broadcast camera pans with the ball carrier, so the motion energy stays
high through the whole play and the quiet-then-step rule re-arms on lulls
*inside* a play. 19 of the 30 gated detections landed on live football at the
wrong moment. The honest conditional precision is 17%, not the 43% that seven
samples suggested.

**Whole-frame motion energy is not a snap detector on a broadcast feed, and a
field-view precondition does not make it one.** No threshold was moved after
seeing any result.

## What was built

| Artifact | Path |
|---|---|
| Module | `scripts/platformkit/tracking/football_fieldview.py` (212 LOC) |
| Test | `scripts/platformkit/tracking/test_football_fieldview.py` (8 tests) |
| Gate + gated snaps, game A | `docs/evidence/tracking/football_fieldview_2026-09-01/gameA_alabama_georgia_gated_snaps.json` |
| Gate + gated snaps, game B | `docs/evidence/tracking/football_fieldview_2026-09-01/gameB_20pezoC5jRQ_gated_snaps.json` |
| Seeded detection sample | `.../snaps_sample_manifest.json` |
| Detection montages (30) | `.../snaps_sheet{1..6}.jpg` |
| Full-resolution re-reads (6 borderline) | `.../borderline_sheet{1,2}.jpg` |
| Blind gate-accuracy sheet + labels | `.../gate_frames_blind.jpg`, `.../gate_frames_labels.json` |

The gate is four cheap image statistics on a 320-px-wide frame -- turf-green
ratio in HSV, the largest set of long near-parallel Hough segments (yard
lines), Canny edge density (a full-frame graphic card is flat), and a
whole-frame grey jump for shot cuts -- plus shot-level hysteresis. It reads no
numbers, solves no homography and claims no scale. Every emitted row is stamped
`coordinate_space=image_px` / `observation=observed` / `calibration=none`
through `scripts/platformkit/coordinate_provenance` and carries the boolean in
an `is_field_view` column, so the harness still refuses to score it as field
geometry.

`football_snap.py` changed in exactly one way: `detect_snaps` now takes an
optional `gate` mask and skips candidates outside it. **No detector constant
moved.** This is a precondition on the input shot, not a gate on the metric's
own bound, so it is not the `tautological_gates_2026_09_01` pattern -- but it is
new code with its own measurement, which is why it got one.

### Pre-registered constants (fixed on the synthetic test, never moved)

`GREEN_MIN=0.25`, `GREEN_STRONG=0.45`, `LINE_MIN=2`, `PARALLEL_DEG=15`,
`LONG_LINE_FRAC=0.25`, `EDGE_MIN=0.015`, `CUT_MEAN=25.0`,
`MIN_SCENE_FRAMES=15`, `CUT_GUARD_FRAMES=15`. Echoed into each
`*_gated_snaps.json`.

A frame is raw field view when it is at least 25% turf, has real edge content,
and either shows two long near-parallel lines or is at least 45% turf. A *shot*
is field view when it survives a cut, lasts at least 15 frames, and a majority
of its frames pass; the 15 frames either side of a shot boundary are never
accepted, because that boundary is precisely where a camera cut fakes a snap.

## Synthetic proof

```
python -m pytest scripts/platformkit/tracking/test_football_fieldview.py -q
8 passed in 4.07s
python -m pytest scripts/platformkit/tracking/test_football_snap.py -q
5 passed in 2.76s   (T4 regression: unchanged)
```

Four synthetic shot types the real broadcast actually mixes: a wide field view
(turf, near-parallel yard lines, players) passes; a flat navy studio card, a
textured warm sideline crowd, and a **flat green card** all fail. The flat green
card is the case only the edge-density test can reject -- it has turf colour and
no structure -- so it isolates that feature rather than letting green ratio do
all the work. Two more tests pin the hysteresis: a crowd-to-field cut is found
at the right frame with both guard bands closed, and an 8-frame field flash
between two crowd shots is rejected outright.

## Real-footage re-measurement

Same two verified broadcasts as T4 -- the other four local `football_*` clips
are volleyball (ingest mislabel, documented in the T4 memo).

```
python -m scripts.platformkit.tracking.football_fieldview data/videos/reference/football.mp4 \
  --out-dir docs/evidence/tracking/football_fieldview_2026-09-01 --tag gameA_alabama_georgia
python -m scripts.platformkit.tracking.football_fieldview \
  /c/Users/neelj/nba-track-a3/data/footage_corpus/football__football_20pezoC5jRQ_360p_source.mp4 \
  --out-dir docs/evidence/tracking/football_fieldview_2026-09-01 --tag gameB_20pezoC5jRQ

gameA_alabama_georgia: 28771 frames, 1273 scenes, field_view 55.5%, snaps 83 -> 25
gameB_20pezoC5jRQ:     28772 frames, 1836 scenes, field_view 45.0%, snaps 83 -> 22
```

The ungated count reproduces T4's 83/83 exactly, which is the check that the
one-decode composition did not perturb the detector.

The 2.8 MB per-frame `*_fieldview_image_px.csv` tables were kept out of the
repo; the commands above regenerate them.

### Gate accuracy -- 15/20 = 75.0% [53.1, 88.8]

Twenty frames drawn uniformly at random (`default_rng(31)`, ten per game) over
every frame of both clips, rendered **without the gate verdict**
(`gate_frames_blind.jpg`), judged by eye, and only then compared against
`gate_frames_labels.json`. Four false accepts, one false reject:

| # | Frame | Gate | Truth | Failure |
|---|---|---|---|---|
| 02 | A 2265 | field view | sideline bench shot | turf still fills the lower frame |
| 04 | A 13594 | field view | player close-up (Gurley) | blurred background is 52% turf |
| 07 | A 16469 | field view | kicker medium close-up | same |
| 13 | B 10190 | field view | dissolve through a crowd graphic | green 2%, but the *shot* majority passed -- a dissolve produces no hard cut, so the hysteresis smoothed across it |
| 03 | A 10189 | not field view | live wide play | green 23%, just under `GREEN_MIN`; white and red kit plus shadow |

The dominant error is structural, not a threshold: **a close-up shot filmed on
the field is still mostly green**, so a colour-and-lines test cannot separate
"pointed at the field" from "standing on the field". A scale-free shot-type
classifier would need object scale -- how big a helmet is in frame -- which is
the piece a solved registration would have given for free.

### Snap precision -- 4/30 = 13.3% [5.3, 29.7]

Fifteen detections per game drawn by a seeded uniform sample over the whole
gated detection list (`default_rng(23)`), never by confidence rank -- picking the
most confident would be the `impossibility_claims_selection_bias_2026_09_01`
error. Each rendered as a three-panel montage at t-0.6 / t / t+0.7 and read
frame by frame; the six rows where the call was close were re-rendered at full
resolution across five offsets (t-0.8 .. t+0.8) and re-read before scoring.
Tolerance is the memo's +/- 0.5 s.

**Hits: #09 (A f18862), #12 (A f21075), #16 (B f331), #27 (B f18222).** All four
show the same thing: a set formation, then the line firing off, then the play
under way. #16 and #27 are the tightest -- the snap lands inside the window but
not at its centre -- and both are counted as hits, which makes 13.3% the
optimistic reading.

Decomposition of the 30:

- **4 genuine snaps.**
- **19 landed on live football at the wrong moment** -- the line was already
  engaged at t-0.8 (mid-play re-arm), the play was ending, or the wide shot held
  between plays with no snap in the window. This is now the dominant failure and
  the gate cannot touch it: these ARE field views.
- **7 were not live football**: a ball-spot close-up (#15), a full-screen roster
  graphic over a stadium aerial (#18), a referee huddle (#19), three player
  close-ups filmed on the field (#03, #20, #21) and a scoreboard numeral (#30).
  Six of the seven are the close-up-on-green failure the blind gate sample
  already predicted.

## What is NOT verified

- **Recall on real footage was still not measured**, so the football memo's
  primary gate (>= 70% of hand-marked snaps within +/- 0.5 s, n >= 30 marks
  across >= 2 games) remains only half-exercised. The gate can only *lower*
  recall -- it deletes 68% of detections, and one blind-sample frame shows it
  deleting a live wide play -- so this REJECT does not depend on it. **13.3% is
  precision and must never be reported as the memo's gate.**
- **The shuffled null control was not run on real footage** -- it needs the same
  hand-marked ground truth. Synthetic only, unchanged from T4.
- **Gate accuracy is n=20 by one reader**, no second annotator and no adjudication
  of the borderline calls (#07 kicker, #09 tight live play, #11 near-empty field).
  The 95% interval runs from 53% to 89%.
- No separation of scrimmage snaps from kickoffs, punts and extra points.
- Both clips are 640x360; the 1080p Wave 6H control is still pod-only. Yard-line
  Hough counts are resolution-sensitive and were not tested at 1080p.
- `data/videos/bridge/football_mqQsnKyLXlY.mp4` remains unverified, not cleared.
- The gate was **not** measured against any downstream use other than snaps.

## Recommendation

Do not tune `GREEN_MIN`, `CUT_MEAN` or the window lengths and re-run; the T4
memo pre-registered that as the banned move and this measurement does not
contradict it. Two separable findings:

1. **The snap detector stays rejected.** The remaining failure is temporal, not
   spatial: motion energy cannot tell the start of a play from a lull inside one
   when the camera pans with the ball. Fixing that needs a signal that is quiet
   *during* a play -- formation structure, player-count stability, or a
   line-of-scrimmage estimate -- none of which exist at `IMAGE_PX_DECLARED`.
2. **The gate itself is a modest, honest win worth keeping** as an input
   precondition for any future football work at this rung: 75% frame accuracy,
   and it removes roughly two thirds of non-football shots. Its known ceiling is
   the close-up-filmed-on-turf case, which colour and lines cannot resolve.

Football stays a preserved `image_px` corpus with no validated snap signal,
which is where the decision memo already put it.

## Sources

- `docs/evidence/tracking/football_imagepx_snap_2026-09-01.md` (T4, the 3/20 baseline)
- `docs/research/organization-sprint/FOOTBALL_POST_OCR_DECISION_2026-09-01.md`
- `scripts/platformkit/coordinate_provenance.py` (the declaration stamper)
- `scripts/platformkit/teacher_feature_gate.py` (`IMAGE_PX_DECLARED`)
- Memories: `tautological_gates_2026_09_01`,
  `impossibility_claims_selection_bias_2026_09_01`,
  `adapter_corpus_mismatch_2026_09_01`
