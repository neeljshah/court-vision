# Fable adjudication of the architecture plan: the keystone is REFUTED

Adversarial review requested by the orchestrator 2026-09-03 and recorded in full
as an adjudication. **The plan's central architectural claim does not survive.**
Two of its load-bearing citations were independently re-verified by the
orchestrator before this record was written; both hold exactly.

## What is WITHDRAWN from `TRACKING_ARCHITECTURE_PLAN_2026-09-03.md`

### 1. The keystone ("calibration first collapses three failure classes")

**Refuted by the prior day's ledger, which the plan did not cite.**

- **Tennis already emits `court_feet` and passes ZERO rows.** `RESULTS_LEDGER.md:57`
  (G38, 2026-09-02): 9 runs over 8 clips, `jump_p95` over bar on 8/9, coverage
  under bar on 6/9, `oob` over bar on 4/9. Satisfying the coordinate contract does
  not move a row toward passing; it moves it to the gates tennis has been failing
  all week. The plan counted 29 coordinate-contract failures as if they were 29
  rows one fix from passing. They are 29 rows that fail FAST
  (`tracking_harness.py:219` returns before any quality gate), which MASKS what
  they would fail on next.
- **Soccer has a measured footage ceiling, not a solver gap.** G91: four canonical
  landmarks visible in **0 of 100** frames. A homography needs four
  correspondences.
- **The learned-keypoint step was already tried and CLOSED AT LIMIT.**
  `RESULTS_LEDGER.md:55` (G31, 2026-09-02): a learned court-keypoint model scored
  PCK@7px of 0.077 and 0.035, median error 17.4 px, and "Frames solved by the
  model AND NOT by the classical: ZERO on both folds." The plan proposed exactly
  this method for basketball without citing G31.
- **G140 is not a training set.** 68 targets over **17 frames** with a p90 label
  repeatability of 11.39 px, from a census with 66.7 pct blind agreement. The
  plan's "No new labelling is needed to start" is withdrawn as the single most
  concrete over-read in the document.

### 2. The SOTA comparison, on two of three components

- **Association: I described one sport's adapter and called it the stack.** The
  plan quoted the tennis adapter's per-half heuristics. The BASKETBALL route
  already runs per-track Kalman filters (`advanced_tracker.py:104`), Hungarian
  assignment (`:210`), an appearance model (`:150`, `:184`), ByteTrack-style
  matching (`:886`) and OSNet re-ID (`:1066`). That IS tracking-by-detection with
  appearance. "A generation behind on association" is **false for the core sport**.
- **Detection: the measured cause is SELECTION, not the detector.** G189: the raw
  detector emitted **15 person boxes, three times out of three**, at frame 474
  where roughly ten players are visible; the route kept 2 or 3. G188: 6 on-court
  players retained from 11 raw. G17 soccer: of 300 labelled crops, **89.3 pct are
  players**. My "emitting spectators is correct behaviour for the model we are
  running" is true and irrelevant: a person detector is supposed to emit every
  person; the SELECTOR is supposed to keep players. **Reframing a selector bug we
  own as a detector generation gap was externalisation and is withdrawn.**
- **The tennis root cause is one line.** `domains/tennis/tracking/adapter.py:191`
  keys selection on box AREA, so the largest box per half wins and the foreground
  chair umpire wins. That matches G18 and G38 exactly and the plan never mentioned
  it.

### 3. The determinism spread I have been quoting

"Five identical runs, 40 pct" folds in G187 and G188, which ran on a pod code
state G188 itself says "cannot be named". **The verified figure is the n=3 spread
of 1,246 to 1,360 = 9 pct.** The route is still non-deterministic and step 0 is
still right, but the 40 pct number must be quoted as spanning an unverifiable code
state. Corrected here and wherever else I have used it.

## What is NEW and more important than anything the plan proposed

### The harness's own coverage metric is B1-circular

`scripts/platformkit/tracking_harness.py:234` sets
`n_frames = int(df["frame"].nunique())` and `:250` computes coverage as
`(per_frame >= cfg["min_players"]).sum() / n_frames`.

**Frames where the tracker emitted NOTHING are excluded from the denominator.**
The metric is computed after excluding the rows that would fail it, which is the
contract's own B1, the first automatic-reject condition, sitting inside the
harness that adjudicates every row. G34 measured the inflation at **4.9x** on
2026-09-02 and flagged it "on the critical path, not a nicety". It was not acted
on, and the plan explicitly listed denominator work as NOT on the critical path.

**Orchestrator verification: both quoted lines were read directly and are exactly
as stated.** So was `scripts/run_clip.py:580-585`, whose own comment reads that
ft_x/ft_y are the image fraction affinely rescaled, "NOT a homography, even though
a per-clip one is solved in memory and discarded."

### Basketball does not need a new calibrator to become scorable

It already solves a per-clip homography (`unified_pipeline.py:330, 708, 1034`) and
projects to the 2D court (`advanced_tracker.py:1425`), then persists an affine
rescale instead. **Basketball's coordinate-contract failure is a PERSISTENCE
choice, not a calibration gap.** Whether that solved homography is any good is
unmeasured, and G140 exists to measure exactly that via G119's procedure.

## Adjudicated sequencing, replacing the plan's

0. **Determinism** shipped as ENVIRONMENT and seeds in the spec command line, not
   an `src/` edit, because a deploy would collide with B5. Seed everything
   seedable first (including `src/tracking/color_reid.py:77-79`, `cv2.kmeans` with
   no `cv2.setRNGSeed`), then measure the residual FP16 spread. FP32 is NOT the
   mode: switching precision changes the system under measurement.
1. **Fix the harness denominator.** Coverage over segmented gameplay frames, the
   segmenter independent of tracking outcome, the excluded set named. This makes
   coverage HARDER, which Q3 explicitly permits.
2. **Basketball only. Score the EXISTING homography** against G140's 68 targets
   via G119. If it is within the 11.39 px floor, persist the projected coordinates
   and the rows become scorable **with no new model**.
3. **Basketball selection**: polygon filter on projected feet plus confidence
   retention; same row tries `yolo_imgsz` 960 or 1280 (`unified_pipeline.py:1007`
   notes players are ~25 px at the current 640). Measure survivors against the 15
   raw boxes at frame 474.
4. **Daemon OFF for baseball, football, soccer**; mark NO-BENCHMARK with a
   G91-style visibility census as the reopening condition. Tennis frozen as
   reference. The daemon has burned **128.6 compute-hours**, 83 of them on sports
   that cannot pass by configuration.
5. Learned calibration, detector swap (on LICENCE grounds, kept separate from the
   quality argument) and association changes only after one basketball row passes
   on the fixed denominator. Any learned-calibration spec must cite G31.

## Contract v2, as adjudicated

**CUT:** A8 (fold into B11), A10 (no incident behind it), B12 (conflicts with Q8,
where a falsified premise is a VALID result, not a reject), B13 (duplicates Q9),
S3 (fold into S2).

**KEEP:** A9, B11, S1, S2, D2, D4.

**KEEP WITH EDITS:** D1 becomes "`git log master..<branch>` non-empty means
unlanded", one line, catching both incidents. D3's trigger becomes mtime plus a
CPU check, NOT 10 minutes of silence: G186 records a legitimate 22-minute decode
at 99 pct CPU that D3 as written would have declared dead at minute 10.

**ADD:** A11 CODE IDENTITY (every pod row records route-file hashes or the deploy
manifest hash); S4 NAME THE LEDGER AND FIELD; S5 ONE ROW, ONE LANE (G182 was
double-dispatched); D5 NO DEPLOY WHILE A POD MEASUREMENT LANE IS LIVE; H1 NAMED
DENOMINATOR (coverage and ball_valid divide by decoded or segmented frames, named
in the artifact, never by the count of frames that happen to have rows).

## The thing the plan missed entirely

**A gameplay / shot-type segmenter, as the FIRST component and the definer of the
denominator.** Every eye check today (G182 5/5, G184 5/5, G185 5/5) shows the
modal frame is a close-up, crowd or graphic. A broadcast practitioner classifies
shot type before anything else. The pieces exist already
(`domains/tennis/tracking/segmenter.py`, `unified_pipeline.py:1003` gameplay
cache, G34's hand census). The plan never used the word.
