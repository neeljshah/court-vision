# Basketball calibration: what tonight's measurements settled

**Date:** 2026-09-04. **Status:** synthesis of landed rows. **No code, threshold,
gate, bar, verdict or register row is changed here.** Every number below is
quoted from a landed ledger row or recomputed by the orchestrator in master; the
provenance is named inline so a reader can check it.

This amends the standing design document
[`CALIBRATION_STRATEGY_2026-09-02.md`](CALIBRATION_STRATEGY_2026-09-02.md),
which remains correct in its geometry survey and its anti-patterns. **What it can
no longer support is its diagnosis of what basketball is missing.**

---

## 1. The one-paragraph state

**Read section 7 first. It supersedes the conclusion of sections 1-5.** Sections 1-3 are the per-frame
corner-detection story and remain correct: the fitter and court model contribute
zero error, the detector's line geometry is the lever, no in-repo option improves
it, and a human census says the footage is far more solvable (62.36 pct) than our
detectors achieve. **Section 4 then shows those experiments were never what
production uses** -- the court model is anchored to a generic panorama of a
different venue, and the homography acceptance thresholds sit at or below the
mathematical floor. **Section 5's account of three
hand-labelled failures is now CLOSED, not open**: all three failed on
bookkeeping, G236b then located the one G196-validated frame, and **G233d passed
its gate there -- see section 7.** Propagation itself was never the obstacle --
G222 measured direct-to-seed holding across all 1,200 frames tested at a flat
0.26-0.38 px reprojection residual.

---

## 2. What is settled, with provenance

| Claim | Measurement | Row |
|---|---|---|
| The four-point fitter and the court model introduce **zero** error | exact lines through the labelled corners give **17/17 at 0.000000 px** through the same unchanged `solve_line_pairs` and G205 `score_frame` | G217 |
| All of the oracle's error is **detected line geometry** | selected detected lines miss their labelled corners by **median 10.234792 px, max 59.693249 px** over 68 selections | G217 |
| The error is **scatter, not bias** | every role straddles zero under a fixed sign convention; angle and offset both present, neither dominating (median 6.967785 px offset vs 6.856946 px angle); corner error does not track shallowness (rank assoc. **-0.1225**) | G223 |
| **No deterministic correction exists** | a painted-edge-to-centreline shift would need a stable one-signed residual surviving the 11.39 px label floor; there is none | G223 |
| The tennis **top-hat** evidence transfer makes basketball **worse** | oracle **1/17 at 28.841316 px -> 0/17 at 60.048887 px**; proposals fell 1,928.06 -> 367.53/frame, which does not redeem it | G224 |
| The **semantic quad provider** never fires | **0/17, 0/68, and 17/17 ABSTENTIONS** -- it selects no paint quad at all, despite plentiful contours (1,970 / 1,955 / 817 raw) | G227 |
| Line-segment detectors are exhausted | LSD **0/17** (G205, G210b), M-LSD **0/17** reproduced on the pod (G208, G214) | G205/G208/G210b/G214 |
| The footage is **not** the limit | human census: paint **PAINT_SOLVABLE in 1,029/1,650 = 62.36 pct**, Wilson 95 pct [0.6000, 0.6467], spread through every clip | G68D |
| The construct is **not** stacked against us either | all **68** G140 targets are `status = target`, and **all 17 frames carry all four roles** (orchestrator-verified in master) | G140 |

---

## 3. The correction to the standing strategy document

`CALIBRATION_STRATEGY_2026-09-02.md` section 1.2 states that what basketball
lacks is **role assignment** -- that nothing maps candidate line groups to
baseline / free_throw / lane_low / lane_high, and that the tennis pattern of
"orientation split, then role pinning by termination structure" should be built.

**That work should not be funded on the expectation that it will lift the
result, and here is the argument.**

G210b's `oracle_fit` (`g210b_court_fit_untruncated_search.py:114`) already
performs **perfect role assignment**: for each true paint line it picks, from the
detector's own groups, the one whose line passes closest to the two labelled
corners, and then solves from that group's geometry. **Labels are used only to
CHOOSE; the line geometry is the detector's.**

**So the oracle IS the upper bound on any role-assignment method, and the oracle
scores 1/17 at 28.841316 px.** A termination-structure role assigner, however
elegant, is bounded above by a number that already fails. **Role assignment is
not the missing piece. Line accuracy is.**

Note this also corrects a claim I made earlier and have already retracted in the
ledger: the G214 row concluded that "a better line detector cannot lift the
result much", reasoning from the same oracle. **That inference was backwards.**
The oracle bounds *selection*, not *accuracy*, so a more accurate detector is
exactly the thing that could help -- it is simply that every detector we have
tried is not more accurate.

---

## 4. UPDATE, later on 2026-09-04: the architecture, not the detector

**Everything in sections 1-3 stands. What follows was found afterwards and changes where the problem
most likely lives.** Sections 1-3 concluded that detected LINE ACCURACY is the lever. That remains true
of the per-frame corner experiments. **But those experiments were never what production uses.**

### 4.1 The court model is anchored to a panorama of a different venue

| Finding | Evidence | Row |
|---|---|---|
| All six "per-clip" cached panoramas are **byte-identical** to the generic `resources/pano_enhanced.png` | one md5 `408aca74842f9cd4a1be094d0610230d` across football, ncaa_basketball, soccer and three WNBA clips, all `(500, 3698, 3)` | G237-PANO-GENERIC |
| The per-clip build **cannot** succeed | `_pano_valid` (`:843-851`) requires >=2000 px wide and a 3.0-50.0 aspect ratio; a broadcast frame is ~1.88:1 | G237-PANO-GENERIC |
| The generic image is **cached under the per-clip name**, and a cache hit then prevents any retry | `pano = _fb_img` then `cv2.imwrite(out, pano)` (`:975-988`); `_load_pano` returns early on a valid cache (`:861-866`) | G237-PANO-MECHANISM |
| Confirmed at **runtime**, not inferred | a 5-frame run printed `Pano cache hit: pano_wnba__wnba_01.png`, then `_build_court: rectified portrait (1711x3404) - rotated 90 deg -> landscape`, then `Using static Rectify1.npy` | G237-PANO-CONFIRMED |

The code defends this: **`M1` (`Rectify1.npy`) is calibrated for the Short4Mosaicing panorama**, and the
comment warns that a different pano "clusters all players into a ~590px wide strip".

### 4.2 The acceptance thresholds are at or below the mathematical floor

| Constant | Value | Note |
|---|---:|---|
| `_H_MIN_INLIERS` (`:351`) | **5** | comment at `:889`: *"Broadcast frames give 5-7 SIFT inliers vs pano_enhanced"* |
| bootstrap `min_inliers` (`:1306`) | **3** | below the **4** correspondences a homography requires |
| `_H_RESET_INLIERS` (`:354`) | **40** | what the code itself calls a "very clean SIFT match" |
| sanity gate (`:1327`) | **`> 99999`** | inline comment: *"sanity gate disabled"* -- it fires for **no** frame |

**An 8x gap separates "accepted" (5) from "clean" (40), the first homography of every clip is accepted
at 3 and becomes the EMA everything else blends against, and M1 is re-synced from
`_M1_raw_clip @ inv(_M_ema)` on every EMA change (`:1338-1343`), so a poor EMA propagates straight into
the court mapping.**

### 4.3 What this means, stated at the right strength

**IF production really operates in the 5-7 inlier regime its own comments describe, then per-frame corner
detection was never the binding constraint and G194's "DEGENERATE basketball projection" is the design's
expected output rather than a puzzle.** **That is an INFERENCE FROM CODE, not a measurement.** G238 was
written to observe the actual inlier distribution and **could not launch**; a 40-frame probe showed
`cv2.findHomography` is not even reached that early. **So all of 4.2 is what the code ACCEPTS, not what
it receives.** If real matches routinely yield 30+ inliers, these thresholds are harmless.

## 5. The hand-labelled path: three failures, none of them a fair test

| Row | Frame used | Why it failed |
|---|---|---|
| G233 | `wnba__wnba_01_1080p` labels vs `wnba__wnba_01.mp4` | different clip identifiers; no `_1080p` file in the corpus. **My spec error.** |
| G233b | `IB-_u4gW3ds__s14__f028171` at index 28171 | the still is not that frame (frame-accurate MAD 61.33) |
| G233c | same still at the **correct** index 46154 (verified, MAD 1.87) | clean gate failure -- but **G196 never eye-checked this frame** |

**G196 eye-checked only 5 of 17 frames** (indices 0, 4, 8, 12, 16): **3 YES** -- `sRtHQbywiTE__s03__f006925`,
`wnba__wnba_01_1080p__s01__f001600`, `wnba__wnba_07__s08__f016801` -- and **2 INDETERMINATE**. Its table
entry for G233c's frame reads `yes | 0.000e+00 | 0.000e+00`, which is the **round-trip residual**: a
self-fit that is trivially zero, the same trap as G217's 17/17 control, **not** an eye-check verdict.

**All three validated frames come from clip identifiers absent from the corpus; the one clip present was
rated INDETERMINATE. So the geometry has never been tested on a frame anyone confirmed.** G236 showed
labels are recoverable by re-indexing (its still sits at frame **46154**, delta **+17,983**, match ratio
**0.037** to the scan median over a full 205,444-frame decode). **G236b is running the fair test.**

## 6. What is genuinely open


1. **A trained model.** Untried for basketball. Any such row **must cite G31**,
   which closed a trained calibration path AT LIMIT for tennis, and say why
   basketball differs. G214 established the licence and packaging rails that
   blocked zero-shot learned detectors: ELSED needs an OpenCV dev package absent
   from a shared pod image, HAWP pulls LGPL-3.0 `easydict`, and DeepLSD and KpSFR
   have `LICENCE-UNVERIFIED` weights.
2. **Labelling plus propagation.** G196 showed four hand-labelled corners project
   correctly with the three-point arc landing out-of-sample, so a seed works.
   G215 showed chained propagation holds about **50 frames** (10.88 px drift at
   50, 38.47 at 100, 187.77 at 300) and decays from an ordinary camera pan alone.
   **At 50 frames a one-hour 30 fps clip needs roughly 2,000 hand labels, which
   is not viable. G222 is measuring whether direct-to-seed matching removes the
   compounding**; that number decides whether this path is open or closed.
3. **Why the quad provider abstains.** G227 left the rejecting gate explicitly
   NOT VERIFIED. **G229 is measuring it now.** If a single gate is binding with a
   small margin, the "closed at limit" verdict on that candidate should be
   amended; if no candidate is near any gate, the closure is strengthened.

---

## 5. A separate blocker that is not calibration at all

**Basketball has never been scored by the harness once.** G207's census:
`wnba` 0 scored / 2 EXCLUDED, `ncaa_basketball` 0 scored / 1 EXCLUDED, all for
**noncanonical columns** -- while football scored 3, kbo 8, mlb 12, npb 3,
soccer 3 and tennis 3. The legacy table emits `frame, timestamp, player_id,
team, x_position, ...` and declares **no `coordinate_space`, no
`calibration_provenance`, no `projection_status`**, so the harness cannot audit
its frame of reference. **Even a solved homography would not have made those
tables scorable.** G226 built a basketball adapter emitting the canonical schema
with honest `image_px` provenance; G226b then found it **absent from the pod**,
with `POD_GIT_PRESENT=no` and no incremental deploy path. That deployment is
held as a gated decision.

---

---

## 7. RESOLVED, 2026-09-04: seeded calibration works, and the horizon is open

**G233d is the first basketball court coordinates this programme has produced.**

Sections 1-5 were written while every seeded attempt had failed. **G236b closed
the gap** by locating the one G196 **eye-validated** still inside a corpus video:
`wnba__wnba_01_1080p__s01__f001600` appears in `wnba__wnba_01.mp4` at zero-based
frame **19599** (refined MAD **0.903** against a stride-5 scan median of
**40.66**). **G233d seeded there and PASSED**, judged on the independent near
three-point curve and a visible sideline -- never on the four fitted corners.

| quantity | G233d value |
|---|---|
| gate at distance 0 | **PASS** on independent geometry |
| contiguous frames held | **all 1,200 tested** (to source frame 20799) |
| direct matches / inliers | 452-1,863 / 421-1,848 |
| inlier ratio | 0.839901-0.991948 |
| RMS residual | **0.299365-0.702623 px** |
| in-court fraction by band | 0.828-0.918 |
| labels per hour | `ceil(108000/1200) = 90` -- **a floor, not a rate** |

### 7.1 Why section 4's architecture finding and this result agree

Section 4 argued the legacy route matches broadcast frames against a generic
panorama of a **different venue**, yielding 5-7 SIFT inliers. **G233d matching
WITHIN the same clip got 421-1,848 -- roughly one hundred times more.** That is
independent corroboration of section 4's diagnosis from the opposite direction:
the features were always there; the reference geometry was foreign.

### 7.2 The ~50-frame ceiling was an artifact of the instrument

G215's ~50-frame validity figure came from **chained** frame-to-frame
composition, where error compounds multiplicatively; a smooth pan alone destroyed
it. G222 and G233d match **DIRECTLY against the seed**, so nothing compounds.
Same footage, same labels, roughly 24x the horizon. **Do not quote "one
calibration per ~50 frames" as a requirement any more.**

### 7.3 What is still NOT true

- **Automatic calibration remains 0 of 17.** This path consumes a hand label.
  Every classical in-repo automatic route is closed on measurement: G217 (fitter
  contributes zero error), G223 (scatter), G224 (top-hat made it worse,
  28.84 -> 60.05 px), G227 (quad provider abstains 17/17), G229 (best margin
  0.534 of bar).
- **1,200 frames is where the run stopped, not where it broke.** The horizon is
  unmeasured.
- **Plausibility is necessary, never sufficient.** The in-court fraction counts
  officials, bench and spectators; G225 found one frame with 19 raw boxes and 2
  visibly on-court players.
- **One clip, one seed, one camera, one labeller, one eye judgement.** G140's p90
  label repeatability is 11.39 px.

### 7.4 The three rows now open against this

| row | question | outcome |
|---|---|---|
| **G241** | how far does the seed hold CONTIGUOUSLY? | **NOT VALIDATED, stopped on a control I mis-specified.** Its by-product matters: the propagation GEOMETRY reproduced bit-exactly (zero unequal records over 1,200 frames), while 808 of 1,201 DETECTOR records differed. Re-issued as **G241b** with the control narrowed to geometry. |
| **G242** | does a distant frame re-acquire DIRECTLY from the same seed? | **ACCEPT, and the result is a negative -- see 7.5.** Yes on same-end views out to +154,401 frames, but G222's acceptance rule accepted 89/89 including replays, graphics and the wrong hoop end. |
| **G241b** | the same question with the control narrowed to geometry | **ANSWERED -- see 7.6. The unit is the CAMERA SHOT, and the first shot ends at distance 4,000.** |
| **G243** | does any of this work on AMATEUR footage? | **FALSIFIED: the named clip existed nowhere, and the corpus was 9 clips of pure professional broadcast.** My premise error. |
| **G245** | acquire amateur footage, since there was none | **ACCEPT.** `basketball__amateur_jh3fnwMi7dM.mp4` landed: 1280x720, 3,601 frames, 120.1 s, high-school coaches camera, near-fixed, arcs at both ends and the centre circle visible. |
| **G243b** | amateur calibration against the real clip | RUNNING, with a new clustered-vs-spread label-geometry arm. |
| **G244** | does ANY diagnostic separate a correct court from a wrong one? | **ANSWERED: NO -- see 7.7.** |
| **G246** | WHY did the amateur gate fail? | **ANSWERED: all eight labelled pixels were the wrong features -- see 7.9.** |
| **G247** | does the projected quad's SHAPE separate them? | **ANSWERED: NO -- see 7.8. Every invalid map is a well-formed quad.** |

### 7.7 G244: no match diagnostic separates a correct court from a wrong one

G244 blind-labelled all 89 of G242's overlays VALID / INVALID / CANNOT JUDGE and
**committed those labels in a separate, earlier commit before reading any
diagnostic** -- the ordering is verifiable in git history. Then it measured the
overlap:

| diagnostic | INVALID range | VALID inside it | VALID range | INVALID inside it |
|---|---|---:|---|---:|
| matches | 114-652 | 25/27 | 130-2000 | 24/28 |
| inliers | 86-620 | 25/27 | 100-2000 | 24/28 |
| inlier ratio | 0.709677-0.950920 | 25/27 | 0.624309-1.000000 | **28/28** |
| RMS px | 0.318691-1.247066 | 25/27 | 0.000000-0.696784 | 26/28 |

**The classes interpenetrate on every diagnostic.** Slightly different medians are
not evidence.

**The abrupt-drop idea from 7.6 also failed.** G241b's two cut drops were 128 and
165 matches, but ordinary single-frame drops across that span run **-283 to 170** --
an ordinary drop of 170 exceeds both cuts. Not separable, in-sample on two cuts.

**So as of now there is NO automatic validity signal at all, and every "it held"
claim in this programme is carried by renders alone.** One check remains untested:
the SHAPE of the projected quad. G244 could not compute it because **G242 persisted
no per-frame homography (0/89) and no ordered corners (0/89)** -- a retention gap,
not a negative, now issued as G247. **The retention lesson is general: persist the
matrix, not only its summary statistics.**

### 7.6 G241b: the operational unit is the CAMERA SHOT, not a frame count

**The corrected control PASSED exactly** -- all 1,200 post-seed geometry records equal
record-for-record, zero unequal pairs, all maps finite. Extending to a predeclared
10,000-frame target then produced the programme's first named failure horizon.

**The direct matcher stays finite through all 10,000 frames. The EYE CHECK fails at
distance 4,000.** Renders at 0, 1,000, 2,000 and 3,000 follow the independent painted
arc and sidelines; at 4,000 the broadcast has cut to a tight player close-up, no
painted court remains, and the projected court is visibly off. The 9,000 and 10,000
renders are also unusable.

**The cause is named and independently corroborated.** A hard scene inventory found 15
`scene > 0.40` cut candidates over the span. The first close-up transition matches a
candidate at about distance 3,876, and **the match series then drops abruptly in a
single frame -- 310 at distance 3,932 to 182 at 3,933 -- falling to 81 near 4,440.** A
second abrupt drop appears at distance 9,823 (327 to 162). **This is a cut followed by
sustained loss of seed-view overlap, NOT G215's chained-pan decay** -- and G241b was
not chaining.

**Labels per hour: `ceil(108000/4000) = 27` for that observed first shot.** It is the
repeated-span arithmetic for one shot, not a corpus-wide rate. **The `ceil(108000/10000)
= 11` figure describes finite direct-map persistence only and is NOT an operational
labelling claim**, because the eye check had already failed at 4,000.

**Consequence for the programme:** a hand label covers **a camera shot**, so the cost of
calibrating a game scales with its edit rate, not its length. That reframes the whole
labelling-throughput question -- and it makes automatic cut detection, not automatic
calibration, the cheapest available lever. The single-frame collapse at both cuts is
why G244 now also asks whether that drop is separable from ordinary variation.

### 7.5 G242: match acceptance is NOT geometry validity

**This is the most consequential result of the night and it constrains every
other row here.** G242 sampled the whole game at stride 2000 and matched 89
frames directly against the G233d seed. **G222's unchanged acceptance rule
accepted 89 of 89 -- 1.000000.** Opening all 89 overlays showed the accepted set
was 52 normal court views, 29 tight player/bench/crowd views, 6 replay/overhead
and 2 graphic/partial. **Frame 8000 is the other hoop end, where the projected
court plainly misses the paint, and it passed.**

**So inlier count, inlier ratio and RMS residual have never been shown to
indicate that a court is correct.** RMS is the most misleading of the three: it
measures fit to the matched features, which the wrong hoop end also has.

**What survives, and it is substantial:** judged on independent painted geometry
and never on the fitted corners, the court visibly agrees at the seed and at
same-end views 74000, 122000 and **174000 -- +154,401 frames from the seed.**
One hand label really does re-acquire a correct court across an entire game on
same-end views. **What is missing is any automatic way to know which frames those
are.** Until G244 answers that, **every "it held for N frames" claim in this
document is carried by its RENDERS alone**, and must be stated that way.

G242's literal `ceil(30*3600/174430) = 1` label per hour is **arithmetic only and
is not a usable rate**, because the same rule accepts visibly invalid maps.

**A separate and unrelated result:** G240 hashed three fresh basketball-adapter
runs and found the emitted tables **byte-identical** (SHA-256
`979b0e2e...49df75`, 64,171 rows each), with zero differing row positions in
every pair. Three runs on one clip in one configuration is an existence check,
not a determinism proof -- but it is the programme's first repeatable measurement
path, and it is stronger than G225's equal row counts.

---

## 7.8 The validity question is CLOSED for hand-built signals

Three rows tested three independent signal families against the same blind labels,
and **none separates a visibly correct court from a visibly wrong one.**

| family | row | result |
|---|---|---|
| the acceptance rule | G242 | accepts **89/89**, including replays, graphics, close-ups and the wrong hoop end |
| match statistics and dynamics | G244 | matches, inliers, ratio, RMS all interpenetrate; cut drops (128, 165) sit inside ordinary variation (-283 to 170) |
| projected-quad shape | G247 | seven pre-registered checks, all overlapping |

**G247's control reproduced G242 exactly -- 89/89, zero mismatches -- so this is a
clean measurement, not a flaky one.** And its most informative line is a negative
about the mechanism itself: **no INVALID map inverted, lost convexity, changed
corner order, or placed a projected corner outside the image.** A homography onto
a close-up or a graphic is still a perfectly well-formed, convex, correctly-wound,
in-bounds quad of plausible area.

**Consequence, stated plainly: there is currently NO automatic validity signal, and
every "it held for N frames" claim in this programme is carried by renders alone.**
That is expensive -- it means a human must look.

**What remains untested is the one thing the eye actually does:** ask whether the
projected court LINES land on real painted lines in the image. Every signal tested
so far is a property of the match or of the matrix; none looks at whether the
projection agrees with the picture. **That is G248.** If it also fails, the honest
conclusion is that a hand-built statistic will not do this and the programme needs
a trained model or a different instrument.

## 7.9 The amateur-footage chain: four rows, and the goal is still open

| row | outcome |
|---|---|
| **G243** | FALSIFIED -- I named a clip that existed nowhere. **The corpus was 9 clips, all professional broadcast: the any-footage goal had no test material at all.** |
| **G245** | ACCEPT -- acquired `basketball__amateur_jh3fnwMi7dM.mp4`, a high-school coaches camera, 1280x720, 3,601 frames, 120.1 s, near-fixed, arcs at both ends and the centre circle visible. |
| **G243b** | CLOSED AT LIMIT -- both seed gates FAILED, under three labellings whose spread was inside G140's p90. |
| **G246** | **The cause was bad labels, not the footage.** All eight labelled pixels were NOT the features their roles claimed; two were occluded by a coach and a player. Exhaustive enumeration of every correspondence and axis convention found no repair. |
| **G243c** | CLOSED AT LIMIT -- with identity verification required first, **no eligible seed frame exists in the clip.** |

**The methodological finding is the durable one.** G243b's three labellings agreed
to about 10 px, inside G140's 11.39 px p90 -- **and all three were consistently
wrong.** In G246's words: *"Repeating an incorrect point within 11.39 px can be
repeatable without identifying the intended feature."* **Label repeatability is
precision, never identity, and this programme has been leaning on it as though it
were both.** The check that does establish identity is a committed zoomed crop at
each labelled pixel, before the fit.

**And G243c's blockers all name the same feature class.** Frames 660, 840, 3300 and
3525 failed because *"players occupy the line intersections"* -- the lane and
free-throw geometry, which is exactly where basketball players stand. **The four
court corners, which players almost never occupy, have never been checked.** That
is G249, and if they are visible an eligible frame may already exist in the footage
we have.

---

## 7.10 CLOSED: no hand-built signal indicates court validity (four rows, four families)

**G248 completed the sweep.** Its four pre-registered projected-line/image-agreement
signals -- edge-response contrast against perpendicular controls, line-detector
agreement, marking contrast, and coverage -- **none separates** the classes.

| signal family | row | result |
|---|---|---|
| the acceptance rule | G242 | accepts **89/89** |
| match statistics and dynamics | G244 | all interpenetrate; cut drops inside ordinary variation |
| projected-quad shape | G247 | seven checks, all overlapping; every invalid map is a well-formed quad |
| projected-line vs image structure | G248 | four signals, all overlapping |

**Stated at full strength: there is no available hand-built automatic validity
signal. Every "it held for N frames" claim in this programme is carried by renders
alone.** The next instrument has to be a trained model or a different sensor, not
another hand-built statistic.

**One number in G248 is unexplained and may explain all four negatives at once.**
Edge-response contrast is **negative for the VALID class** (median -47.33) and
almost identical for INVALID (-45.15). On frames a human called correct, the
projected lines sit on *less* edge structure than nearby control points. **If the
projections were landing on painted lines that should be positive.** The hypothesis
-- **eye-valid but not pixel-accurate** -- is what G252 tests, and the programme has
never measured how accurate a "valid" calibration actually is.

## 7.11 CLOSED: point-based calibration of amateur footage, on five sources

| row | result |
|---|---|
| **G249** | Court corners are **never occluded when in frame (0/61 across all four)** -- the hypothesis was right. But **both near corners are outside the image in 61/61 frames**: camera framing, not players. |
| **G250** | **Zero same-frame four-point candidates** across 20 inventoried features. Largest usable set: **three points, all collinear on the centre line.** Cross-frame combination invalid because the camera pans. |
| **G251** | **4 of 4 further sources rejected.** Three because foreground crowd, bench or scorer table hides the camera-side boundary; one -- the only whole-court view -- because a multi-use gym's overlapping markings made point identity ambiguous. |

**The cause is structural, not incidental: amateur cameras sit on the near sideline,
so near-side geometry is systematically hidden by crowd, benches and cropping.**
Acquiring more sources of that shape will not help, which is why G251's screen-out
rate is the useful number rather than a disappointment.

**G250's acquisition criterion is now the gate for any future amateur source:** a
camera must show, in one frame, at least four distinct named unoccluded painted
intersections spanning two dimensions of the court, including some near-side
geometry -- and the review must report the four-point quadrilateral area fraction
and the minimum point-to-other-three distance, rejecting a near-zero spread.

**What this does NOT close.** A homography has 8 degrees of freedom; **a line
correspondence gives 2 constraints and a conic gives 5.** The amateur clip reliably
shows the far sideline, the centre line and the centre circle -- **2 lines + 1 conic
= 9 constraints**, sufficient in principle from exactly the geometry that is
available. **That is G253**, and it runs a lines-only positive control on G233d's
validated WNBA seed first: if it cannot reproduce a known-good calibration on clean
broadcast footage, it closes cheaply and nothing is lost.

---

## 7.12 How accurate is a "valid" calibration? 5 px median, 19 px p90

**G252 put the programme's first number on this.** Every calibration verdict here
had been a binary eye judgement. On the 27 eye-VALID frames, the nearest strong
image edge is a **median 5 px** from the projected marking, **p90 19 px**, inside
a 24-px search (larger offsets censored by construction).

**The median sits inside G140's 11.39 px label-repeatability scale; the p90
exceeds it**, so the upper tail is not hand-label noise alone. G252 correctly
declined to decompose further.

**This one number plausibly explains all four validity negatives at once.** A
projection off by 5-19 px looks right at overlay scale while missing a thin
painted line, so every pixel-precise statistic in 7.10 was measuring the wrong
thing. **When quoting the seeded path, say "eye-valid at roughly 5 px median /
19 px p90", not "accurate".**

## 7.13 The first non-broadcast calibration -- and a route closed beside it

**G253 calibrated the amateur clip from LINES AND A CONIC, where no four points
exist.** A homography has 8 DOF; a line gives 2 constraints and a conic 5. Fitting
only the far sideline, centre line and centre circle -- the geometry that IS
reliably visible -- produced a court that **passes its gate on the WITHHELD
left-end arc and painted-end markings.** Degeneracy diagnostics are clean: line
angle 87.6 deg, observed conic fraction 0.58, Jacobian condition 40.4.

**The positive control is why it is credible.** A lines-only fit on G233d's
validated WNBA seed reproduced the published map to **2.849 px median / 4.344 px
max -- over 231 of 634 sampled points, those both in frame and shared.** Over all
634 the p90 is 280 px: expected off-frame divergence, not failure. **Quote that
denominator with the claim.**

**RETRACTED IN PART -- G255 HAS NOW RUN AND THE AMATEUR PASS IS NOT REPLICATED.**
G255 blind-judged the same render on the same withheld geometry, committing its
verdicts before reading G253's, and returned **CANNOT JUDGE**: the arc and
painted-end evidence is *"too faint, occluded, and visually ambiguous at this
render scale to support a PASS or a FAIL"*. **Two labellers, one frame --
disagreement, not replication.** The offsets agree: the amateur withheld geometry
measures **median 12.0 px / p90 18.0 over 80 samples**, against the control's
**median 5.0 px / p90 16.0 over 689** -- **more than twice the WNBA median.**

**So "the first calibration of non-broadcast footage" must NOT be claimed. It is
UNRESOLVED, not refuted.**

**What survives is the more important half: THE METHOD IS REPLICATED.** G255
independently called the WNBA lines-only control **PASS**, agreeing with G253, and
that control has an objective anchor. **Line-and-conic calibration is validated on
broadcast footage; only its amateur application is open.**

**The process failure was mine.** G253 reported its amateur result honestly as
one-labeller, one-frame eye evidence; **I promoted it to a headline before it was
checked.** The check cost one cheap row. **Any eye-gated result that becomes a
headline must be independently re-judged first.**

**The transferable lesson: when four identifiable points do not exist, count
CONSTRAINTS, not points.** Lines and conics survive occlusion and cropping far
better than the intersections they define.

### 7.13a G254: refinement improved its own number and broke the calibration

Refining G233d's seed against detected edges moved the pooled offset from
**5/18 px to 4/17 px -- and the refined court FAILS the independent eye gate**,
visibly displaced above the painted end markings. **A lower residual is not a
better map**, and only re-running the gate on withheld geometry caught it.

**And the basin is narrow: 13 of 43 perturbed starts converge, and ZERO
non-identity translate/rotate/scale starts do.** That was the question worth
asking -- if the basin were wide, an approximate automatic guess could be refined
into a good one. **It is not. "Get roughly close, then refine" is closed as a
route to automatic calibration on this evidence.**

---

## 7.14 THE GENERALISATION RESULT: one clip out of four footage classes is fittable

This is the most important thing measured tonight, and it only became visible once
the method was carried to other footage.

| footage | result |
|---|---|
| **WNBA broadcast** | **WORKS.** Seeded 4-point (G233d) and lines-only (G253 control, independently re-judged PASS by G255). |
| **NCAA broadcast** | **0/300** frames with an identifiable centre-circle conic -- the permanent centre logo replaces the painted circumference, 0.00 identifiable arc (G264). **0/300** with four identifiable painted lines; **1/300** with three (G265). |
| **Amateur basketball** | **0** usable four-point sets across 20 inventoried features; largest set 3 collinear points (G250). Near court corners in frame **0/61** (G249). **4 of 4** further sources screened out (G251). |
| **Broadcast soccer** | **0/1,195** complete penalty/goal-area rectangles (G259). **0** four-edge and **0** three-edge penalty boxes (G261). **0/1,195** with circle + halfway line + both touchlines (G263). The one-touchline DOF shortcut is mathematically false (G262). |

**The WNBA clip is the exception, not the rule.** Every positive calibration result
this programme has ever produced comes from that single clip.

### 7.14a Three distinct causes, none of them detector quality

1. **Camera framing.** The near-side boundary is systematically absent -- near court
   corners 0/61 in amateur basketball, the near touchline missing in every soccer
   candidate. Cameras sit on one side, so that side's geometry falls outside the
   frame or behind crowd, benches and scorer tables.
2. **Occlusion.** Players stand precisely on the lane and free-throw intersections
   that four-point methods want -- that blocked every G243c candidate.
3. **Court decoration.** A painted centre logo can replace the geometry outright,
   which is what closed NCAA's conic route.

**None of these is a detector problem, a resolution problem, or a tuning problem.**
They are properties of how sport is filmed and how courts are painted.

### 7.14b Why this points at a learned model, with evidence rather than assertion

Every lane tonight refused to fit when features were ambiguous, and **that
discipline was correct** -- G246 showed that fitting unverified points produces a
confident, precise, completely wrong court with a residual of exactly zero.

**But identity-first hand fitting requires each individual feature to be
unambiguous, and real footage usually cannot supply four of those in one frame.**
A learned calibration model has no such requirement: it integrates weak, partial and
individually ambiguous evidence across the whole image, which is exactly the
regime these four footage classes present.

**So the closures above are not a dead end; they are the specification for what has
to replace hand fitting.** And tonight also built the instruments to evaluate a
replacement honestly: a pixel-accuracy baseline (7.12), a measured eye-gate
resolution (7.7-7.8), a blind-ladder gate that a single look cannot fake (G257,
now standard in every new spec), and four independently closed hand-built validity
families (7.10) so no one re-runs them.

---

## 7.15 DEFINITIVE: no hand-built signal detects a court error below 40 px, and the eye does better

G260 re-ran the displacement ladder with the design G258 should have had: **paired
within-frame**, every one of **35 pre-enumerated frames** measured unperturbed and
at each rung, so scene content cancels inside each difference. No frames excluded.

**The sign-agreement count across the 35 frames is what decides it** -- chance is
17.5:

| signal | sign agreement at 10 px | verdict |
|---|---:|---|
| **Coverage** | **35/35** | **detects at 40 px**, monotone |
| Edge response | 20/35 | none -- non-monotone |
| LSD agreement | 24/35 | none -- non-monotone |
| Marking contrast | 20/35 | none -- non-monotone |
| Offset p90 | 0/35 usable | none |
| Quad area / aspect / outside fraction | 0/35 | structurally insensitive |

**Only coverage has a consistent sign, and even it needs 40 px.** Coverage is the
fraction of projected curve still inside the image -- so it detects a large
displacement because geometry falls off-frame, which is a crude geometric effect,
not a validity signal.

**So the machine's best is 40 px while the eye (7.7) resolves 20 px. THE HUMAN IS
BETTER THAN EVERY HAND-BUILT SIGNAL WE HAVE.** That is the exact opposite of
G258's withdrawn 10 px claim, whose control had zero variance by construction --
edge response, the signal it named, agrees in sign on only 20 of 35 frames at
10 px, which is chance.

**This closes the validity question against KNOWN ground truth**, not merely
against noisy eye labels, and it is the strongest form the negative can take. With
7.10 it means: **there is no automatic validity signal, hand-built statistics are
exhausted, and the next instrument must be learned.**

---

## 7.16 THE PRIORITY REVERSAL: association, not calibration, is the binding defect

**Everything above is about obtaining a map. G267 measured what the map is FOR**,
and the answer reorders the programme.

Projecting detector boxes through **G233d's validated map** across 3,801 frames of
one shot -- 30,071 finite box feet, 98 emitted association IDs, 29,973 consecutive
same-ID steps:

| quantity | value |
|---|---|
| **same-ID steps above 40 ft/s** | **4,090 / 29,973 = 0.136** |
| p99 step speed | **700.118 ft/s** |
| max step speed | **100,457.241 ft/s** |
| max inter-detection distance | **3,269.030 ft on a 94-ft court** |
| exactly coincident pairs | **2** |

**13.6 pct of tracked steps are physically impossible, through a calibration we
had just validated.** And **physics needs no eye gate** -- which matters enormously
given 7.7 and 7.15, where the eye resolves 20 px and no hand-built signal beats it.

**It is not the geometry.** 48.0 pct of implausible steps coincide with an
association-ID discontinuity, 53.9 pct with a >100 px image jump, 1,723 with
neither. G267 correctly refused to assign cause, **but the shape points at
detection and identity association.** Identity is validated nowhere in this
programme.

**So the honest reordering: calibration is now roughly good enough (5 px median /
19 px p90) and is NO LONGER what stands between this system and usable tracking.
Association is.** That is a better problem: it is measurable without a human,
cheap to recompute, and drivable -- **the implausible-step fraction is the
objective quality metric every eye-gated row in this document lacked.**

**Caveats that travel with it:** the population is detector boxes, not
authenticated players -- officials, bench, spectators and duplicates included
(G225 found 19 boxes yielding 2 visibly on-court people). One clip, one shot, one
arena, and **one draw of a non-deterministic detector** (G241). A plausible
distribution would be necessary, never sufficient.

---

## 7.17 The 13.6 pct figure, tested against my own doubt: it is 10.5 pct on court

I reported 13.6 pct as an end-to-end quality figure, then noticed G267's own
Jacobian table (0.016-0.079 ft/px on court) rules out on-court pixel error as the
source of its extremes -- 100,457 ft/s at 30 fps needs about 3,348 ft in one frame.
**The natural suspicion was that the figure was dominated by off-court boxes
projecting near the homography's unbounded horizon.** G270 tested it.

| partition | steps | above 40 ft/s |
|---|---:|---:|
| both endpoints ON court | 23,783 | **0.105** |
| one endpoint crossing the boundary | 1,001 | **0.765** |
| both endpoints off court | 5,189 | 0.157 |

**The suspicion was right in shape and wrong in size.** Boundary-crossing steps are
overwhelmingly implausible, exactly as the horizon hypothesis predicts -- **but they
are only about 1,000 of 29,973 steps.** **61.3 pct of all impossible steps have BOTH
endpoints inside the court.**

**So the correct on-court figure is 10.5 pct, not 13.6 pct** -- a modest revision,
not a retraction, and **the defect is real and it is on the court.** Neither figure
is a tracking-quality score for authenticated people: the denominator is detector
boxes including officials, bench and spectators, and identity is unvalidated
everywhere in this programme.

---

## 7.18 THE COMPLETE DIAGNOSTIC CHAIN: the detector's boxes jump

G271 closed the last two open questions about the 10.5 pct on-court
implausibility, and the chain is now complete.

**Systemic, not concentrated.** Of 98 emitted ids, the worst 5 give **20.8 pct** of
on-court impossible steps and the worst 10 give **35.5 pct**; **19 have zero, so
79 of 98 (80.6 pct) are affected.** Discarding a few bad tracks buys nothing.

**The box moved -- it is not a projection artifact.**

| descriptive bin | share of on-court impossible steps |
|---|---:|
| image displacement **above 83 px** (box-jump) | **1,454 / 2,507 = 0.580** |
| 17-83 px (indeterminate) | 835 / 2,507 = 0.333 |
| below 17 px (projection-amplified) | 218 / 2,507 = 0.087 |

**83+ px in ONE frame on a 1920-wide image is the box landing on a different
body.**

### The chain, every link measured, none of it eye-gated

1. **Calibration is fine** -- 5 px median / 19 px p90 (7.12).
2. **Association cannot repair the implausibility** -- constraining it only
   fragments tracks, 98 to 139 ids (G269).
3. **It is not off-court projection** -- 61.3 pct of impossible steps are fully on
   court (7.17).
4. **It is not a handful of bad tracks** -- 79 of 98 ids affected (G271).
5. **The detector's boxes jump 83+ px between frames on the same id** (G271).

**So the binding defect on tracking quality sits UPSTREAM of every calibration
question in this document.** That is the single most useful thing tonight
produced, and unlike everything in 7.1-7.15 **it is measurable without a human
eye** -- which matters precisely because 7.7 and 7.15 showed the eye resolves only
20 px and no hand-built signal beats it.

**What is NOT established:** which of detection motion, association, wrong-person
or duplicate boxes, map error, or real movement causes any individual jump. G271
refused to allocate a single cause and anyone quoting it must too. Identity is
unvalidated everywhere in this programme, and the population is detector boxes --
officials, bench and spectators included -- not authenticated players.

---

## 7.19 WHAT THE WHOLE CHAIN ACTUALLY RESTS ON, stated so nobody has to rediscover it

Everything in sections 7.16 to 7.18 -- the priority reversal, the 10.5 pct
on-court implausible-step figure, the 79-of-98 id spread, the 58 pct with 83+ px
image displacement, and the 50 pct not-a-person share -- was measured on
**ONE camera shot, source frames 19599 to 23399, of ONE clip,
`wnba__wnba_01.mp4`, in ONE arena, from ONE draw of a non-deterministic
detector, with ONE labeller on the eye-judged parts.**

That is not a hedge added at the end. It is the single largest open risk in the
programme, and two rows are open against it right now:

| row | what it removes | what it cannot remove |
|---|---|---|
| **G273** | that the 50 pct not-a-person rate comes from a **biased subsample** -- jump steps are exactly where non-people would concentrate. It samples ALL retained detections, unconditioned. | still one clip, one shot, one labeller |
| **G274** | that the whole profile is a property of **one camera shot** rather than of the system | still one clip, one arena |

### The corpus limits how far this can go, and the limit is structural

Verified on the pod, 2026-09-04: the corpus is **10 clips**, of which
**only three are basketball-family** -- `wnba__wnba_01`, one NCAA clip, and a
23 MB amateur clip. The rest are tennis, MLB/baseball and soccer.

**`wnba__wnba_01.mp4` is the only clip in the corpus with a validated
calibration map.** Section 7.14 established that hand-fitted calibration does not
generalise, for camera reasons rather than algorithmic ones. So:

- **Every COURT-SPACE measure -- including the 40 ft/s plausibility test that
  the entire chain is built on -- is confined to this one clip** until somebody
  produces a second hand label. There is no way around that with the current
  corpus.
- **Every IMAGE-SPACE measure is map-free and does port to other clips.** That
  is the only route to a cross-clip result that exists today.
- **But a raw pixel threshold does NOT port.** Clips differ in resolution and
  zoom, so "83 px" means different things in different clips. A cross-clip row
  must normalise (frame diagonal, say) and compare distribution shape, or it is
  comparing nothing.

### The consequence for how these numbers may be quoted

Until G274 reports, **no figure in sections 7.16 to 7.18 may be described as a
property of the tracking system.** They are properties of a measured shot. The
distinction is not pedantic: if G274 finds a different profile in a second shot,
the correct reading becomes that the defect depends on framing or play context,
and the first shot's numbers would be actively misleading as system-wide claims.

**A "no valid map exists for a second shot" result from G274 is a full success**
and would itself be the finding: that the chain cannot be extended at all without
new hand labels, which converts a measurement problem into a labelling one.

---

---

## 7.20 THE DETECTOR'S USEFUL YIELD IS 0.597, AND THE SECOND SHOT HAS NO COURT

Two rows landed on 2026-09-04 that together close section 7.19's two open risks
and reshape what the chain means.

### G273: what fraction of retained detections is even a person

An **unconditioned** sample -- 72 retained detections, one drawn from each of 72
contiguous frame bins across the G267 span, covering 72 distinct source frames
and 41 emitted ids, selected with **no** speed, jump, association, position or id
condition -- classified blind in a randomised order committed before un-blinding:

| category | count | fraction |
|---|---:|---:|
| **(a) PLAYER on the court of play** | **43 / 72** | **0.597** |
| (b) PERSON, not a player in play | 9 / 72 | 0.125 |
| **(c) NOT A PERSON** | **15 / 72** | **0.208** |
| (d) CANNOT JUDGE | 5 / 72 | 0.069 |
| **(b) + (c): boxes that arguably should never enter tracking** | **24 / 72** | **0.333** |

**The detector's useful yield is 0.597.** One retained detection in five is not a
person at all. This is the first time the programme has measured detector
precision on anything other than a single frame (G225: 19 boxes, 2 visibly
on-court people).

### The comparison against G272b has to be bracketed, and the bracket matters

G272b's **0.500** counts steps where **one or both** of **two** footpoint crops
showed no person. G273's **0.208** is a **single-crop** rate. **Pairing them
directly implies a 2.40x concentration that the data do not support.**

The right baseline is the rate at which an *unconditioned* step shows a
non-person at one or both endpoints, and that was never measured, so it can only
be bracketed:

- **endpoints independent:** `1 - (1 - 0.208)^2 = 0.373`
- **endpoints perfectly correlated** (a track sitting persistently on or off a
  person): `0.208`

Real tracks are positively correlated frame to frame, so the truth lies inside
**[0.208, 0.373]**. G272b's 0.500 **exceeds the top of that range**, so the
concentration is real -- **but the honest ratio is 1.34x to 2.40x, not 2.40x.**
**G276 is open to measure the endpoint correlation directly and collapse the
bracket**, presenting both endpoints of every step in one pooled blind order so
the labeller cannot see the pairing.

### G274: the replication cannot be done, and that is the finding

The adjacent distinct camera shot, source frames **23476-24127** (652 frames,
bracketed by `scene > 0.40` cuts at 23475 and 24128), is **a tight player
close-up with no painted court.** Direct-to-seed matching against the 19599 seed
nonetheless returned **0.285-1.434 px RMS with up to 350 inliers**, and at the
independent mid-shot frame 23599 **116 matches, 60 inliers, 0.569 px RMS** -- with
the projected court running across a player's body.

**The lane ran no detector inference at all: 0 new boxes, 0 ids, 0 steps.** It
stopped, which the spec named in advance as a full success.

Two consequences, and the second is larger than the first:

1. **The G267/G270/G271 profile is NOT EVALUATED across a cut.** It is neither
   replicated nor refuted, and **it may not be called a property of the tracking
   system.** It remains a property of one measured shot.
2. **Sub-pixel reprojection residual is worthless as a validity signal.** This is
   the fifth independent failure (after G242 acceptance, G244 match statistics,
   G247 quad shape, G248 line/image agreement), and the most striking, because
   0.569 px RMS is precisely the statistic a naive pipeline would trust most.

### What this leaves open

**G275** censuses the whole 174,430-frame clip for how much of it shows enough
painted court to be a calibration candidate at all -- reported explicitly as an
**upper bound**, with a blind re-judge for label agreement. If that fraction is
low, court-space tracking addresses only a small slice of broadcast footage, and
that reframes the programme rather than the clip.

---

---

## 7.21 THE MAP-ELIGIBLE CEILING IS NOT THE BINDING CONSTRAINT: about two thirds of the clip is court-bearing

G274 found the shot adjacent to the studied span was a close-up with no painted
court, which raised the possibility that court-bearing footage is rare and that
the whole court-space programme addresses only a sliver of broadcast video.
**G275 censused the whole clip and the answer is the opposite, and better.**

A uniform sample of **180 frames across all 174,430** (stride 969.06, each
extracted by an independent `ffmpeg -ss` seek, the clip never decoded in one
pass), classified blind in a randomised order committed before un-blinding:

| category | count | fraction |
|---|---:|---:|
| **(a) two or more painted lines AND a visible intersection** | **118 / 180** | **0.656** |
| (b) court surface visible, but not that | 11 / 180 | 0.061 |
| **(c) no painted court surface at all** | **50 / 180** | **0.278** |
| (d) cannot judge | 1 / 180 | 0.006 |

**Roughly two thirds of this clip's runtime is court-geometry-bearing.** Close-ups
and graphics like G274's second shot are real and account for **0.278** of
runtime, but they do not dominate. **The ceiling on court-space tracking in this
clip is set by whether an (a) frame can actually be calibrated, not by how much
(a) footage exists.**

### (a) is NECESSARY, NOT SUFFICIENT -- this bound is one-directional

Category (a) says painted geometry is visible. **It does not say a map would
fit, or that a fitted map would be correct.** Four independent signal families
failed to separate a valid court from an invalid one (section 7.10), the eye
resolves only 20 px (G257), and **G274 produced 0.569 px RMS on a frame with no
court in it at all.** So **0.656 is the MOST footage that could ever be
calibrated**, and the realised fraction can only be lower.

### Two design flaws of mine bound how precisely it may be quoted

Both were reported by the lane, unprompted, and both are faults in my spec:

1. **The studied-span question was unanswerable by construction.** I asked
   whether frames 19599-23399 are unusually court-bearing while specifying a
   uniform 969-frame stride, so that 3,801-frame span could receive at most
   **3.92 samples.** It received four (three (a), one (c)). **The question stays
   OPEN and needs a stratified re-sample.**
2. **The 40/40 re-judge agreement tests the easy boundary.** I required a
   re-judge but did not require it to be stratified; the draw contained 29 (a)
   and 11 (c) and **no (b) at all.** So agreement is measured on (a) against
   (c) -- painted lines against crowd -- which is visually trivial. **The
   boundary that sets the headline, (a) against (b), is untested.**

**Consequence: 0.656 has a measured CEILING and no measured FLOOR.** It could rise
to at most `(118+11+1)/180 = 0.722` if every (b) and (d) frame were really (a);
it has no lower bound, because an unmeasured (a)/(b) error rate could move any
number of the 118 (a) labels down. **Quote it as "about two thirds, upper-bounded
at 0.722", never as a precise 0.656.**

**None of this disturbs the counts, the sealed protocol or the confusion table,
which are sound.** The central finding stands: **court-bearing footage is
plentiful in this clip, so the binding constraint is calibration validity and the
detector, not footage availability.**

---

---

## 7.22 THE CHAIN'S SPAN IS NOT A SAMPLE OF THE CLIP -- and that bounds every figure in 7.16 to 7.18

G278 closed the two sub-questions G275's spec could not answer, and the first
result is the most consequential thing measured today.

### The studied span is measurably friendlier than the clip

| population | category (a) frames | fraction |
|---|---:|---:|
| **studied span 19599-23399** (61 fresh frames, stride 62-63) | **51 / 61** | **0.836** |
| **clip-wide** (G275's 180 frames, stride 969) | **118 / 180** | **0.656** |

Pooled p = 0.7012, SE = 0.0678, **z = 2.662, nominal two-sided p = 0.0078**,
uncorrected for the many comparisons in this programme. The within-span 95 pct
Wilson interval is [0.724, 0.908].

### What follows, stated precisely and no further

Court-space measurement is only possible where a map can exist, which is (a)
footage. **The chain's span is 0.836 (a); the clip is 0.656 (a). The chain's
population is therefore NOT the clip's population, and any clip-wide
extrapolation of the 13.6 pct all-steps or 10.5 pct on-court implausible-step
figures is unsupported.**

**What does NOT follow: the direction of the effect.** It is tempting to argue
the chain was measured under favourable conditions and so understates the defect.
**That inference is not available.** Nobody has measured tracking quality in
low-court-visibility footage, and G274 established that in the adjacent close-up
shot **no map exists at all**, so it cannot be measured there in court space.
**The span is unrepresentative on a measured axis; the sign of the consequence is
unknown.** Anyone quoting 10.5 pct must attach the span, not the clip.

### The (a)/(b) boundary is perfectly repeatable, and my ceiling was too loose

The stratified re-judge included **all 11** first-pass (b) frames plus 20 (a) and
9 (c): **40/40 agreement, with zero a->b (0/20) and zero b->a (0/11)
transitions.**

This tightens the bound in one direction and supplies the first floor:

- **Ceiling.** My G275-DESIGN-LIMITS row put it at `(118+11+1)/180 = 0.722` by
  allowing every (b) and (d) frame to be really (a). **All 11 (b) frames
  re-judged as (b)**, so only the single un-rejudged (d) survives:
  **`119/180 = 0.661`.**
- **Floor.** The Wilson lower bound on the 20/20 a->a repeatability is 0.8389,
  giving `(118 * 0.8389)/180 = 0.550`.

So 0.656 sits inside **[0.550, 0.661]** -- and that is a **repeatability-only
bound, not a correctness interval.** **40/40 does not confirm the figure**: both
passes can be consistently wrong in the same way, and a category (a) frame still
carries no evidence that a map would fit, since G274 produced 0.569 px RMS on a
frame containing no court at all.

### Net effect on the programme

Section 7.21's headline survives -- **court-bearing footage is plentiful, so
footage availability is not the binding constraint** -- but 7.19's "one shot"
caveat is now sharper than a caveat. **It is a measured mismatch between the
population the chain was measured on and the population it is quoted about.**

---

---

## 7.23 IDENTITY IS THE HEALTHY AXIS: purity 0.935 at one second, and most swaps revert

G281 asked the question every memo in this chain had deferred: **when a track id
persists for one second, is it still on the same person?** It is the first
positive identity evidence the programme has produced.

**Two sealed blind passes.** Pass 1 measured person-ness with all 160+ crops
pooled into one randomised order so the **pairing was hidden**; Pass 2 judged
identity on the subset where both endpoints were people, necessarily showing the
two crops together -- which is precisely why person-ness had to be measured
first with the pairing concealed. Both orders were committed before un-blinding.

**The funnel, every denominator named:**

`20,551 pre-on-court pairs -> 15,207 eligible -> 80 sampled from 59 ids ->
62 both-endpoints-person -> 46 judgeable -> 43 SAME / 3 DIFFERENT`

**Purity = 43 / 46 = 0.935, 95 pct Wilson [0.825, 0.978]**, with 16 CANNOT JUDGE
held separate and the rate never quoted against the 80 sampled pairs.

### Combined with G272b, this bounds transient swapping

Neither row could establish this alone:

| direction | quantity | value |
|---|---|---:|
| from G281 | per-frame **NET** identity change, `1 - 0.9348^(1/30)` | **0.225 pct** |
| from G272b x G279 | steps **involving** a swap, `0.1875 x 0.1054` | **1.98 pct** |
| ratio | swap events per net change | **8.8x** (3.1x at the Wilson lower purity bound) |

**Swap events outnumber net identity changes by at least about 3x and probably
nearer 9x, so the great majority of swaps REVERT -- the track leaves a person and
returns within the second.** G281's spec named this in advance as invisible to an
endpoint-only design; the two rows together now bound it.

**It is a lower bound, not an estimate.** The arithmetic assumes swaps occur only
in above-40-ft/s jump steps, the only population G272b sampled. Swaps elsewhere
make the ratio **larger**, so the conclusion strengthens.

### This resolves the apparent tension in sections 7.16 to 7.18

A 0.935 purity beside a 10.5 pct physically-impossible-step rate is **not** a
contradiction. G272b's split was **50 pct not-a-person, 29 pct footpoint
localisation, 19 pct identity swap** -- identity was always the smallest of the
three defect modes. **G281 confirms from an independent direction that identity
is the comparatively healthy axis, and that the binding defect remains detection
precision and footpoint localisation** (G273: only 0.597 of retained detections
are a player on the court of play).

### What 0.935 may not be used for

- **Endpoint-only judgement bounds purity from ABOVE.** A track that drifts onto
  a third person and back inside the second is scored SAME.
- **One second is ONE horizon.** Purity at 3 s or 10 s is a different and
  probably worse number that nothing here measures.
- **Not clip-wide.** Per section 7.22 the span is measurably friendlier than the
  clip (0.836 against 0.656, p = 0.0078).
- **Fragmentation is not covered, and cannot be measured on this artifact.** Only
  **6** termination-to-restart candidate pairs exist at the loosest setting
  (45 frames, 600 px) and none tighter, because ids here are long-lived (98 ids,
  median 124 rows) and **drift rather than restart** -- which is a purity failure,
  the thing G281 measures, not a fragmentation one.
- One clip, one shot, one arena, one labeller, one non-deterministic draw.

---

---

## 7.24 SETTLED: detection fails on BOTH axes, and recall is the worse one

G284 measured the axis nobody had touched. Precision was already known; recall
sat in G273's own NOT VERIFIED list, untouched by any row.

**A sealed blind count with no detections shown**, then joined to G267's records:

| quantity | value |
|---|---:|
| visibly on-court **players** counted, 54 judgeable frames | **524** |
| other visibly on-court people | 47 |
| G270-on-court **detector boxes** in those frames | **365** |
| raw boxes per visible player | **0.697** |
| **expected PLAYER-boxes per visible player**, applying G273's 0.597 | **0.416** |
| recount agreement | **22/23 exact**, 22/23 within one |

### The two numbers together settle the programme's priority

**Precision 0.597** -- only three in five retained boxes are a player on the court
of play. **Recall bounded at 0.416** -- fewer than half the visible players get a
player-box. **Detection fails on both axes, and the recall side is worse.**

This is consistent with everything measured tonight and finally orders it.
G272b split the defect as **50 pct not-a-person, 29 pct footpoint localisation,
19 pct identity swap**. G281 then measured identity purity at **0.935** and
showed most swaps revert. **So association and identity are the comparatively
healthy axes; detection is where the loss is -- now measured rather than
inferred.**

### 0.416 is an UPPER bound, and all three inflation sources make reality worse

1. **No per-person matching.** Ten people and five boxes is consistent with five
   found once each, or three found twice and two missed. The ratio bounds the
   fraction found **only if duplicates are negligible** -- and they are: **0.33
   pct of 121,926 same-frame pairs are within 1 ft** in court space, 0.21 pct
   within 20 px in image space.
2. **Occluded people cannot be counted** by labeller or detector alike, so the
   denominator is *visible* players. That **inflates** apparent recall.
3. **It assumes G273's precision transfers** to the on-court subset, which is
   unverified.

**So "recall is 0.416" must never be said.** It is an upper bound on a fraction
found, under three named assumptions, from one shot of one clip with one
labeller -- and per section 7.22 that span is measurably friendlier than the clip
(0.836 against 0.656, p = 0.0078), so **it may not be quoted clip-wide.**

### A hypothesis closed in passing

**Over-counting by duplicate boxes explains none of this.** The detector is not
stacking boxes on one person -- **it is missing people and inventing non-people
at the same time.** That is a different and harder problem than a
threshold or a de-duplication rule, and no row should spend a cycle on
duplicates again.

---

---

## 7.25 SUSPENDED: the recall thread cannot be reconciled with G273, and section 7.24 must be re-read

Section 7.24 concluded that detection fails on **both** axes. **The recall half of
that conclusion is now suspended.** The precision half is untouched.

### The contradiction

| row | design | result |
|---|---|---|
| **G273** | blind, sealed; 512x640 crop at full resolution centred on each footpoint | **15/72 = 0.208 NOT A PERSON** -- about four in five detections have something person-like at their location |
| **G285b** | locate-then-match; Pass A coordinates sealed before any detection access; no human judges any tolerance | **7/143 = 0.049 recall at 50 px**; 81/88 footpoints match no located player |

**Both blind, both sealed, disagreeing by roughly an order of magnitude.**
G285b's design specifically removed the fault that invalidated G285 -- the eye
only locates, the computer matches -- **and the answer barely moved, 0.0076 to
0.049.** So the judgement-scale artifact was real but was not the main cause.

### Four diagnostics: three causes ruled out, one real but insufficient

1. **Coordinate space -- not the cause.** Frames are 1920x1080; G267 declares
   1920x1080 with `foot_x` 16.7..1900.5 and `foot_y` 50.4..1063.5.
2. **Global frame-index offset -- not the cause.** Mean nearest-footpoint
   distance is 175-253 px at every offset in +/-63, **with no minimum at zero.**
   If footpoints sat on players, offset 0 would be sharply better.
3. **Per-frame frame-index offset -- not the cause.** Searching +/-120 per frame
   gives scattered best offsets (+76, -83, +31, +120, -107, ...) and **even the
   best of 241 candidates leaves 52-216 px** -- chance improvement, not
   misalignment.
4. **Systematic vertical offset -- REAL but insufficient.** Median x agrees
   (located 899.0, detector 880.5) while **median y differs by +147.1 px**, the
   detector lower in **12 of 15** frames. **But removing the per-frame median-y
   offset barely helps: 0.056 to 0.063 at 50 px.** **The two point sets are
   different positions, not offset ones.**

### What is suspended and what stands

**Suspended -- all three rest on joining committed frames to per-frame detection
records, and that join is what is in question:** G284's **0.416** upper bound,
G285's rejected **0.0076**, and G285b's **0.049**. **None may be quoted as a
recall figure.**

**Untouched -- none of these uses that join:** G273's **0.597** precision,
G272b's defect split, G276b's endpoint baseline, G279's threshold curve, G281's
**0.935** identity purity.

**So section 7.24's priority claim now rests on precision alone.** Detection
precision at 0.597 remains measured and poor; **whether recall is also poor is
no longer established either way.**

### The next step is one picture, not more statistics

Render a single frame at full resolution, in tiles, with **located players in one
colour and detector footpoints in another.** A human will see in seconds what
four numerical diagnostics could not settle: whether the footpoints are on people
at all.

---

---

## 7.26 RESOLVED: the contradiction was a tolerance mismatch, and it corrects how 0.597 must be read

Section 7.25 suspended the recall thread over an apparent order-of-magnitude
contradiction between G273 and G285b. **It was not a contradiction.** The two
rows measured quantities whose spatial tolerances differ by roughly 10x, and the
resolution needed no new lane -- only committed data.

### The test

G273's criterion was a **512x640 crop centred on the footpoint**: a person
anywhere within **+/-256 px horizontally and +/-320 px vertically**. G285b's was
**within 50 px**. Applying G273's actual box to G285b's sealed located-player
coordinates over the same 15 frames:

| direction | result | compare |
|---|---:|---|
| footpoints with a located player inside a 512x640 crop | **79 / 112 = 0.705** | G273 measured **0.792** |
| located players with a footpoint inside such a box | **114 / 143 = 0.797** | -- |

**These agree within sampling noise**, and the residual gap is expected: G285b
located **players only**, while G273 counted **any person**.

### What the footpoints actually do

Distance from each footpoint to the nearest located player's feet, n = 112:

| min | p25 | **median** | p75 | p90 | max |
|---:|---:|---:|---:|---:|---:|
| 10.0 | 106.2 | **243.3** | 360.4 | 484.8 | 798.3 |

within 25 px **0.036** · 50 px **0.071** · 100 px **0.205** · 200 px **0.411** ·
320 px **0.661**

**A detection typically has a player somewhere in its neighbourhood but sits
about 240 px from that player's feet.**

### The correction, and it is to my own reading

**G273's `43/72 = 0.597` "PLAYER on the court of play" does NOT mean the
detection is ON a player. It means a player was visible in a 512x640
neighbourhood.** That criterion is **localisation-blind**, and I quoted it in
sections 7.20 and 7.24, in the evidence packet and inside G284's arithmetic as
though it certified position. **It does not.**

### Consequences

1. **The recall thread is unsuspended, reframed.** G285b's 0.049 at 50 px is a
   legitimate **localisation** measure, not a refutation of G273.
2. **G284's 0.416 is withdrawn as a recall bound.** It multiplied a count by
   0.597 on the assumption that 0.597 certified position.
3. **This independently corroborates G272b**, which attributed **29 pct of jump
   steps to footpoint localisation.** Localisation is now measured as bad in
   absolute terms, not merely as a defect category.
4. **The +147 px systematic vertical offset** found in section 7.25 is a symptom
   of the same thing and needs no separate explanation.

**Unchanged:** G273's counts and protocol -- only their interpretation is
corrected -- along with G272b's split, G276b's baseline, G279's curve and G281's
0.935 purity.

---

---

## 7.27 THE ROBUSTNESS SET IS COMPLETE: the headline figure survives all four checks

The programme's most-quoted tracking numbers -- **13.6 pct of all finite same-ID
steps and 10.5 pct of both-endpoints-on-court steps above 40 ft/s** -- have now
been tested from four independent directions.

| check | row | result |
|---|---|---|
| **cut point** | G279 | **robust.** On-court 12.0 pct at 35 ft/s, 10.5 at 40, 9.6 at 45; no cliff. At 60 ft/s -- 1.47x Bolt's peak -- **7.6 pct of on-court steps still exceed the bar.** |
| **span** | G278 | **NOT representative.** The studied span is 0.836 court-bearing against 0.656 clip-wide (z = 2.662, p = 0.0078), so the figure may not be quoted clip-wide. |
| **second shot** | G274 | **unmappable.** The adjacent shot is a close-up with no painted court; direct-to-seed matching returned 0.569 px RMS on it anyway. |
| **detector draw** | G282 | **reproduces.** See below. |

### The detector-draw check, and how it was obtained

G282 consumed four lane cycles without producing a measurement -- twice through
faults in my own spec (a stale-census concurrency gate, a disk guard in the write
path) and once through pod saturation. **The answer came from an orphaned
process**: G282c launched the route four times while diagnosing a helper,
declared its own run invalid rather than cherry-picking, and left the pod
processes alive. One completed and wrote a full artifact, which I fetched before
the worktree could be reset.

**Exactly one artifact exists, so no selection among draws was possible.**

| denominator | draw 1 (G267) | draw 2 | difference |
|---|---:|---:|---:|
| all finite same-ID steps | 4,090 / 29,973 = **0.136456** | 4,104 / 29,961 = **0.136978** | **+0.000522** |
| both endpoints on court | 2,507 / 23,783 = **0.105411** | 2,514 / 23,761 = **0.105804** | **+0.000393** |

The draw is genuinely different -- **30,062 detections against 30,071, and 101
emitted track ids against 98** -- with the same route sha256 set, span, seed and
published map. **The rate reproduces to within five ten-thousandths on both
denominators.**

### A units error caught before it became a false result

My first recomputation returned **0.111966**, which would have read as a
non-reproduction. **I had required a frame gap of exactly 1, while G267 and G279
count consecutive OBSERVATIONS of a track regardless of gap** -- 26,517 steps
under my definition against 29,961 under theirs. Recomputing in the reference's
own units reproduced the artifact's internal figure exactly, which is what
confirmed the definition.

**This is the second time tonight that comparing two quantities in different
units nearly produced a false finding**, after the G273-versus-G285b tolerance
mismatch. Same lesson, different disguise.

### What the completed set does and does not license

**Does:** the 13.6 and 10.5 pct figures are a property of the system under a
fixed map and span, robust to the threshold and reproducible across detector
draws.

**Does not:** they remain **span-specific** (G278), **not clip-wide**, and
**reproducible is not correct.** Two draws bound nothing about variance -- no
spread is computed and G267's figure remains the sole reference. And the
detection defect underneath them is unchanged: **0.295 of detections have no
player in a 512x640 neighbourhood, and of the 0.705 that do, the footpoint sits a
median 172 px from that player's feet.**

---

## NOT VERIFIED

- Whether a trained basketball calibration model would work; nothing was trained
  or evaluated, and the licence/packaging rails from G214 still apply.
- Whether direct-to-seed propagation extends the horizon (G222, in flight).
- Which gate rejects in the quad provider (G229, in flight).
- Whether the basketball adapter emits a canonical table on real footage; it has
  unit tests only and has never run on a clip.
- Every number here is from a small exhaustive construct of **17 frames** with
  **single-source eye labels** whose p90 repeatability is **11.39 px**. The 12 px
  threshold sits at that floor. These measure these frames, not a rate.
- G68D's 62.36 pct is a **human** solvability judgement on 1,650 sampled tiles
  from 11 clips; it is not a claim that any automatic method could reach it.
