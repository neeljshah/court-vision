# Calibration strategy -- lifting four sports from image_px to court_feet

**Date:** 2026-09-02. **Status:** design document only. No code, threshold, or
register row changed. Written for single-problem codex lanes; every lane it
spawns cites `VERIFIER_CONTRACT.md` and self-checks section B.

**Premise (measured, G47 census):** 119 of 187 pod harness reports fail on
`coordinate_contract` and nothing else -- baseball 66/93, basketball 8/12,
football 30/42, soccer 15/25, tennis 0/15. All 119 are LEGITIMATE rejections:
producers correctly declare `image_px`, and image_px can never pass court_feet
under the rung ladder (IMAGE_PX_DECLARED -> METRIC_LOCAL -> COURT_FEET). The
blocker for four of eight sports is CALIBRATION, not tracking quality. Nobody
has ever quality-scored those four sports. Evidence:
`g47_contract_rejection_census_2026-09-02.md`.

---

## 1. Per-sport: what geometry exists, what the module does, what is missing

### 1.1 Soccer (15/25 rejected; 5 pod clips)

**Landmark geometry in a broadcast frame.** The pitch offers a NON-PERIODIC,
uniquely identifiable rectangle: the penalty box (16.5 m deep x 40.32 m wide),
bounded by the goal line, the 16.5 m front line, and two side lines -- four
distinct-role lines whose intersections give four corners, plus the goal-area
box nested inside it and the penalty arc. At midfield: centre circle (9.15 m
radius), halfway line, touchlines. Measured wide-pitch view share on one clip:
**0.65, Wilson 95 pct [0.594, 0.702]** (g34_soccer_view_share_2026-09-02.md,
300 hand-labelled frames). Caveat, one clause: real pitches vary a few metres
around the 105x68 the module hardcodes, so absolute length claims carry a
small unremovable scale uncertainty.

**What already exists.** Soccer has the most complete solve stack of the four:

- `scripts/platformkit/calibration/keypoint_calib.py` defines 15 canonical
  soccer landmarks (4 pitch corners, 8 penalty-box corners, centre circle
  centre/top/bottom) and `solve_homography`.
- `domains/soccer/tracking/geometry.py` has the validated path end to end:
  `_validated_homography` requires >= 5 named landmarks (MIN_LANDMARKS=5) and
  runs leave-one-out held-out validation at MAX_HELDOUT_ERROR_M = 2.0;
  `_stable_homography` adds a temporal calibrator with a 9-update warmup and
  an 8 m inter-frame tolerance gate. Line-family detection, pitch masking,
  and white-marking thinning are built.
- `domains/soccer/tracking/keypoints.py` detects exactly ONE landmark: the
  centre circle, and only when a line passes through its centre. It
  deliberately refuses to name corners (`detect_pitch_corners` returns None).

**What is missing, precisely.** Landmark DETECTION, nothing else. The solver,
validation, and stability machinery are waiting for a provider that names 5+
of the 15 canonical points. The centre circle alone yields three COLLINEAR
points (centre, top, bottom all on the halfway line x = 52.5) -- degenerate
for a planar solve -- so midfield frames are likely unsolvable and the
solvable population is the penalty-box-visible frames. The missing component
is a box-corner provider: identify the goal line, the 16.5 m line, and the two
box side lines by their roles (the box side lines TERMINATE at the goal line
and the 16.5 m line -- the same one-sided extent reasoning that pinned tennis
roles), intersect them for 4-8 named corners, and feed the existing
`_validated_homography`. G09 established the licence route: no shippable
pretrained model exists (sportsfield_release non-commercial, NBJW/PnLCalib
GPL, SoccerNet data research-only); the route is self-labelling from our own
frames bootstrapped by classical solves -- which means the classical
box-corner solve must work first, exactly as tennis's classical solve
preceded its (failed) keypoint model.

### 1.2 Basketball (8/12 rejected; 6 NCAA + 5 WNBA pod clips)

**Landmark geometry in a broadcast frame.** The sideline broadcast camera in a
half-court set shows the paint: a known rectangle bounded by the baseline, the
free-throw line (19 ft up-court), and two lane lines (16 ft apart NBA/WNBA, 12
ft apart NCAA legacy). Also available: the free-throw circle (6 ft radius),
the three-point arc, the near sideline segment, and during transitions the
halfcourt line and centre circle. The paint is aperiodic and its lines have
distinct roles -- structurally the same problem tennis solved, on a quarter of
the geometry. Working against it: a glossy reflective floor, court-coloured
paint fills that vary by venue, ten players occluding a small area, and
constant camera panning (G04: "no court lock on broadcast pans").

**What already exists.** `domains/basketball/tracking/line_calibration.py`:
LSD segment detection, collinear-fragment grouping into candidate physical
lines (`candidate_line_groups`), COURT_LINE_SETS for both rule sets
(`nba_wnba`, `ncaa_legacy` -- the caller must name the league, as football's
`field_level` does), and `solve_from_lines`, which fits H from 4+ named line
correspondences via their pairwise intersections, plus `line_residual` for
per-line misfit. The module's own docstring states the gap: it fits "only
after a caller has identified all four physical lines." No caller exists.

**What is missing, precisely.** Three things:

1. **Role assignment.** Nothing maps candidate line groups to
   baseline / free_throw / lane_low / lane_high. The tennis pattern applies:
   orientation split, then role pinning by termination structure (lane lines
   end at the baseline and free-throw line; the free-throw line ends at the
   lane lines) plus an independent consistency landmark. A pure cross-ratio
   match is weaker here than in tennis -- typically only 2-3 lines per
   direction are in frame -- so the extent/termination evidence has to carry
   more of the load.
2. **Independent validation.** After a 4-line solve, at least one landmark not
   used in the fit must confirm it (candidates: the free-throw circle radius
   projecting to 6 ft, the projected paint width matching the declared rule
   set, or a fifth line when visible). Tennis's `far_right_consistency` gate
   is the template. Remember heldout_validation_blindspot_2026_09_01: a
   held-out residual on the SAME structure cannot catch a global swap or
   scale; the check must be a physically different feature.
3. **Persistence.** The basketball rejection string names it exactly: "no
   persisted per-frame homography or equivalent court anchor is available."
   The producer must write a per-frame calibration sidecar (or stamp rows
   court_feet with the frame's fresh solve) and, critically, must emit
   NOTHING on unsolved frames -- G42 measured a 145.7x inflation from a stale
   homography carried across unsolved frames, and the fix (fail closed per
   frame) is the honest behaviour.

### 1.3 Football (30/42 rejected; 9 pod clips)

**Landmark geometry in a broadcast frame.** Rich but PERIODIC and locally
identical: yard lines every 5 yd, hash marks every 1 yd in two rows (NFL rows
18.5 ft apart, NCAA 40 ft -- the rows cannot self-identify their separation),
sidelines/solid border, and painted numerals every 10 yd with direction
arrows. A yard line at the 20 is pixel-identical to one at the 60. The
absolute-identity problem is exactly what tennis never had, because tennis
sees its whole court and football never does.

**What already exists.** `domains/football/tracking/geometry.py` is the most
built module of the four and it DELIBERATELY fails closed:
`detect_yard_line_family` (LSD in a grass-support ROI, family clustering,
pencil-uniformity gate), `_hash_row_lines`, a general `line_homography`
solver, `field_spec` requiring a caller-named league, a numeral-height scale
check (`nfl_numeral_scale_error_pct`), and `PaintedYardAnchorProvider` (OCR
numeral + adjacent painted arrow, because "40" occurs at both ends of the
field). `homography_from_yard_lines` currently returns
`independent_scale_unavailable` in ALL cases, by design -- naming two hash
rows (60, 100) would assume the scale, "the coordinate laundering this
adapter must avoid." `line_probe.py` exists to measure evidence fractions
per clip before any solve.

**What is missing, and it is measured-dead classically.** The post-OCR
decision memo (FOOTBALL_POST_OCR_DECISION_2026-09-01.md) closed classical
registration with numbers: numerals DETECT at 100 pct of field views but READ
at 12.39 pct valid-parse (best of a four-variant preprocessing sweep, 444
crops); frames with >= 2 numerals naming different yard lines: 13/74 against
a pre-registered gate of 30/74. The other three scale sources scored worse
(adjacent yard-line pairs at two depths 1/60, hash row + sideline 0/60,
white border 8/60); the cross-ratio family gate scored 0 in all four
conditions and the rigid solve 0/175. The single kept re-entry: a
REAL-LABELLED 5-way numeral classifier (10/20/30/40/50) behind a
pre-registered accuracy gate -- the binomial sizing says per-crop accuracy
must roughly double (0.124 -> ~0.22) to pass the frame gate. That is a
learning project with a labelling cost, not a geometry lane. Until it clears
its gate, football stays at IMAGE_PX_DECLARED and that is the honest state.

### 1.4 Baseball (66/93 rejected; 29 pod clips -- kbo, mlb, npb)

**Landmark geometry in a broadcast frame.** The dominant, gated shot is the
CENTRE-FIELD pitch view, looking almost straight down the pitch axis. The
identifiable ground-plane landmarks -- rubber (24 in), mound circle (18 ft
diameter), home plate, batter's boxes -- all lie in a narrow band ALONG that
axis: near-collinear in the image, with extreme long-lens foreshortening in
depth. Foul lines and base paths are cropped or occluded from this view.
There is no ground-plane rectangle of known extent in the pitch view. Four
non-collinear correspondences do not exist to find.

**What already exists.** `domains/baseball/tracking/geometry.py` measures
exactly what the view supports and nothing more: the mound's LATERAL pixels
per foot at the mound row, explicitly "deliberately never used to project
depth into feet." A two-reference gate (mound chord 18 ft vs rubber 24 in,
same image row, 10 pct agreement) validates the scale on 9/36 pitch segments
(25.0 pct) and 73/332 pitch-view frames (22.0 pct) on day footage; night is
0/6, CLOSED AT LIMIT (G10, G32, G33, G53). G64: the segment decision set
itself does not reproduce exactly (30 vs 32 segments), still unattributed.

**What is missing -- and the honest answer is that it cannot be supplied from
this view.** A court_feet homography from the centre-field pitch view is
structurally ill-posed: the available correspondences are near-collinear, so
any planar solve is degenerate or wildly ill-conditioned regardless of
detector quality. This is a "this sport cannot be calibrated from this
camera" finding, not a solver gap. Two honest routes exist, neither a
homography lane: (a) advance baseball to METRIC_LOCAL, the middle rung --
the validated lateral px/ft at the mound row IS a metric-local calibration
and already passes its own gate on ~22-25 pct of day pitch-view frames;
whether the harness contract will score metric_local rows is a contract
question for the harness owner, not settled by the G47 census (which only
established that image_px cannot pass). (b) If court_feet is ever truly
wanted, it must come from a DIFFERENT shot class (the high-home wide view
between pitches, where mound, plate, foul lines, and base paths form a real
quadrilateral); the share of that shot class in our corpus is unmeasured and
the current pitch-view gate selects against it. Do not fund (b) until (a)
and the two higher-ranked sports have landed.

---

## 2. Tractability ranking

1. **Soccer -- most tractable.** The entire solve/validation/stability stack
   is already built and gated (>=5 landmarks, leave-one-out at 2.0 m,
   temporal calibrator); one component is missing (a penalty-box corner
   provider); the target rectangle is aperiodic with self-identifying roles;
   and the enabling denominator is already measured (wide share 0.65). One
   missing detector away from court_feet, on a known fraction of frames.
2. **Basketball -- close second.** The paint is a known aperiodic rectangle
   and the 4-line solver plus both rule-set tables exist; but role
   assignment, an independent validation landmark, AND sidecar persistence
   all have to be built, the corpus is the smallest (8 rejected reports),
   and broadcast panning plus floor gloss are unquantified risks. Same shape
   of problem as soccer, more missing pieces, less measured ground truth.
3. **Football -- hard, and classically closed.** Geometry detection works;
   absolute line identity is the blocker and every classical route to it is
   measured-dead (OCR read 12.39 pct, cross-ratio 0/4 conditions, solve
   0/175). Not structurally impossible -- one readable numeral pair per
   scene unlocks everything, and the re-entry gate is already sized
   (per-crop accuracy ~2x) -- but it requires a labelled-data learning
   project, not a geometry lane. Fund after soccer and basketball land.
4. **Baseball -- hardest, and structurally impossible from the dominant
   camera.** The centre-field pitch view contains no non-degenerate set of
   ground-plane correspondences; no detector improvement changes that. The
   honest program is METRIC_LOCAL (partially validated already), plus an
   unfunded question about the high-home shot class. Say this plainly in
   any roadmap: baseball court_feet is not blocked on effort; it is blocked
   on physics of the camera angle.

---

## 3. First measurements for the top two (LIMIT measurements, before any solver)

Both follow the G34 census pattern, which is the program's proven method:
fixed arithmetic-stride sampling over the WHOLE clip, contact sheets with
burned-in frame indices, every tile viewed by a human, Wilson intervals. No
detector runs. No solver exists yet, so nothing can be circular.

### 3.1 Soccer: penalty-box solvability share

- **Metric.** `box_solvable_share` = frames where a human judges ALL FOUR
  penalty-box lines (goal line, 16.5 m line, both box side lines) discernible
  with enough extent to fit lines, divided by ALL sampled decoded frames.
  Secondary labels per tile, each exclusive: BOX_SOLVABLE / WIDE_NO_BOX /
  NON_WIDE. Report per clip and pooled, each with a Wilson 95 pct interval.
- **Denominator.** All sampled decoded frames of each clip -- never "wide
  frames only" and never "frames a detector accepted." The wide share falls
  out of the same labels as a cross-check against G34's 0.65.
- **Sampling.** All 5 pod soccer clips. Per clip: stride =
  total_frames // 300, indices 0, s, 2s, ... (300 tiles) -- the exact
  arithmetic sequence G34 used, reproducible from total_frames and N with no
  RNG. 1,500 tiles total. Runs on the pod (footage is pod-only,
  FOOTAGE_CORPUS_INVENTORY.md); artifacts written under
  docs/evidence/tracking/, never /tmp (G54).
- **Eye check.** Every one of the 1,500 tiles viewed and labelled (that IS
  the measurement). Then a seeded (seed recorded in the memo) random 20-tile
  subsample of BOX_SOLVABLE re-read at full resolution to confirm the 320 px
  tile judgment, per the football borderline-sheet precedent.
- **Decision rule.** If pooled box_solvable_share is below ~0.10, the
  box-corner route calibrates too little of the broadcast to change the
  harness picture and the lane reports that limit honestly before anyone
  writes a solver.

### 3.2 Basketball: paint-rectangle solvability share

- **Metric.** `paint_solvable_share` = frames where all four lane lines of
  ONE paint (baseline, free-throw line, both lane sides) are discernible
  with fittable extent, over ALL sampled decoded frames. Secondary exclusive
  labels: PAINT_SOLVABLE / COURT_NO_PAINT (live court view, paint not
  fittable -- pans, midcourt) / NON_COURT. Per clip x league (NCAA vs WNBA)
  and pooled, Wilson intervals. The NCAA/WNBA split matters because the rule
  set (lane width) is caller-declared and the two corpora may differ in
  camera style.
- **Denominator.** All sampled decoded frames. The COURT_NO_PAINT share is
  itself the first honest measurement of the panning problem G04 named.
- **Sampling.** All distinct-content basketball clips on the pod (6 NCAA + 5
  WNBA per the inventory; dedupe resolution siblings by content hash first --
  the G28/G30 lesson). Per clip: stride = total_frames // 150, 150 tiles;
  ~1,650 tiles total. Pod-run, same census tooling.
- **Eye check.** All tiles viewed and labelled; seeded 20-tile full-res
  re-read of PAINT_SOLVABLE tiles, as above.
- **Decision rule.** If PAINT_SOLVABLE pools below ~0.10, or if the solvable
  frames cluster into a handful of static half-court stretches (the sheets
  make this visible), the per-frame paint route is a limit result and the
  role-assignment lane does not get written.

---

## 4. What tennis actually does, and what transfers

`domains/tennis/tracking/court_lines.py` earns its acceptance five ways:

1. **Shadow-invariant evidence.** White top-hat ("thin and brighter than
   surroundings") replaced an absolute brightness mask that lost lines in
   hard shadow. TRANSFERABLE: directly useful for basketball's glossy floor;
   soccer already has an adaptive-threshold analog; football's green-ROI LSD
   is a different but adequate evidence path.
2. **Role assignment by projective invariants.** Cross ratios of line
   positions pick which five verticals are the court, instead of ordinal
   position. PARTIALLY transferable: it worked because tennis line spacings
   are distinct and aperiodic. It is measured-DEAD for football (0 in all
   four conditions -- periodic lines are the exact degenerate case) and only
   weakly available to basketball/soccer (usually too few coplanar lines in
   frame for a discriminative ratio).
3. **One-sided termination windows.** Sidelines end at baselines; the centre
   service line ends at the service lines; occlusion only shortens extent,
   so the bound is safe against false rejection. TRANSFERABLE AS A PATTERN:
   lane lines end at the baseline/FT line; soccer box side lines end at the
   goal line and 16.5 m line. This, not cross ratios, should carry role
   assignment in both new sports.
4. **An independent extra correspondence as the accept gate.** The four-anchor
   fit must PREDICT the far-right corner where the image independently shows
   it (plus depth-order and skew gates), and every rejection names its gate.
   FULLY transferable and mandatory -- it is the anti-self-fit (B8) defence.
   Soccer's leave-one-out machinery approximates it but remember: a held-out
   landmark of the same structure passed a wrong-scale grid at 5.7e-05 ft
   (heldout_validation_blindspot); the confirming feature must be physically
   different from the fitted ones.
5. **Fail closed per frame, gate named.** No stale homography ever carries to
   an unsolved frame (the G42 lesson: carryover inflated tables 145.7x).
   FULLY transferable; the basketball sidecar design must inherit it.

**The one thing that does not transfer at all:** tennis sees its ENTIRE court
in a rally frame, so global identity is free. Every other sport views a
partial field, so identity must come from a uniquely identifiable
substructure (soccer's box, basketball's paint) or a symbolic read
(football's numerals). That is the deep reason for the ranking.

**And tennis is not solved.** Frame acceptance is 31.2 pct hard / 17.8 pct
grass (26.5 at 720p+) and 5.0 pct clay (the far baseline is never found under
white-on-orange contrast plus ~250 spurious horizontals, G60); 640x360 kills
every surface (downscale control: 24.8 -> 1.6 pct, proven causal, G57); and a
consistent-sign 1.2 pct court-length residual remains unexplained (G58). Hold
it up as the working REFERENCE for method, never as a finished capability.

---

## 5. Anti-patterns, binding on every calibration lane

Each of these has already burned this program once. They are restated here so
a lane cannot claim novelty.

1. **No hand-drawn per-clip rectangles or per-clip manual correspondences.**
   A homography fit to human-clicked points on the clip being scored is a
   tautology, not a calibration; it measures the human, and it cannot run on
   the next clip.
2. **Never fit and score on the same frames** (B8, the G23 rule). A solver's
   residual against the points it consumed is not evidence. Accept gates use
   correspondences the fit never saw, and any learned component evaluates on
   a held-out MATCH, not held-out frames of the same rallies (the G31
   lesson).
3. **No denominator conditioned on the outcome** (B1, B9, G40). "Share of
   frames that solve, among frames the solver accepted" is the tautological
   coverage bug. Every share in this document is quoted against ALL sampled
   decoded frames, and the excluded set is always named and counted.
4. **Every claim needs a render someone actually looked at, sampled EVENLY**
   (A3, B7). Head slices are how G11 v1 reported 0.93 where the honest number
   was 0.78. The census stride formula and seeded subsamples above exist for
   exactly this reason; record the seed and the index formula in the memo.
5. **No coordinate laundering.** Naming two hash rows (60, 100), assuming a
   pitch is exactly 105x68, or letting a keypoint network hide an identity
   ambiguity in its weights are all the same act: importing the answer as an
   assumption. Football's geometry module refuses this by design; every new
   solver inherits the refusal. A scale must be PROVEN by an independent
   in-image reference or the frame fails closed.
6. **No stale calibration carryover** (G42). Unsolved frame emits nothing.
7. **No synthetic-only zero-shot geometry** (synthcal: 78.019 ft median on
   real frames against the 5.28 ft classical baseline it had to beat).
   Synthetic pretraining is admissible only with real-labelled fine-tuning
   and a pre-registered gate, per the football re-entry design.
8. **Thresholds never move after seeing a result** (B10, Q3). A bar found
   unmeetable is reported CLOSED AT LIMIT, never lowered. The two decision
   rules in section 3 are stated BEFORE the measurements run.
9. **Evidence survives the pod** (G54) **and records its environment** (G62):
   artifacts under docs/evidence/tracking/, never only /tmp, with host,
   timestamp, code revision, and library versions in the memo.
10. **Dedupe corpora by content hash, not filename** (G30), and quote clip
    denominators from FOOTAGE_CORPUS_INVENTORY.md, running frame-decoding
    lanes where the footage actually is: the pod.

---

## NOT VERIFIED

- Whether the harness coordinate contract would score METRIC_LOCAL baseball
  rows is a contract question not settled by G47; it only established that
  image_px cannot pass.
- The high-home baseball shot-class share is unmeasured; the "structurally
  impossible" verdict applies to the centre-field pitch view the current
  gate selects, which is the dominant and currently only gated view.
- The 0.65 soccer wide share is one clip (Belgium-USA 2014); the section 3.1
  census re-measures it across all five clips as a byproduct.
- No number in section 3 exists yet; the decision rules are pre-registered
  here so they cannot move after measurement.
