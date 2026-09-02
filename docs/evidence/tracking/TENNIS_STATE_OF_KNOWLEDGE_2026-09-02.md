# Tennis tracking: state of knowledge, 2026-09-02

Consolidation document. It creates no new gap, changes no register row, no memo
and no code. It is a read of the tennis rows in
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, `RESULTS_LEDGER.md`, and
the ~25 tennis memos those rows cite, as they stood at the end of 2026-09-02.

## How to read this document

Every number carries its denominator. Where the source gives a confidence
interval it is quoted; where it does not, the document says so rather than
inventing one. Three status words are used strictly:

- **MEASURED** -- a number computed from a named artifact that exists.
- **INFERRED** -- a conclusion reached by elimination or by argument, with no
  direct observation of the thing claimed.
- **UNVERIFIABLE** -- the memo states a number, but the artifact it was computed
  from no longer exists locally or on the pod, so nobody can recompute it. An
  UNVERIFIABLE number is documentary; it is not evidence.

Three recomputations were performed while writing this document, from committed
CSVs, and are labelled `[recomputed here]`. They are recomputations of existing
artifacts, not new lanes, and no lane has verified them.

---

## 1. WHAT WORKS

Each item states the scope it was measured on. Scope is part of the claim.

### 1.1 The court solver's length scale is correct on the frames it accepts

MEASURED (G46, `g46_court_scale_premise_2026-09-02.md`, CLOSED -- FALSIFIED).

- Length ratio (solver 78 ft rectangle against true court length):
  **median 0.9878, n = 91 accepted frames**, mean 0.9884, sd 0.0058, p10 0.9825,
  p90 0.9948, min 0.9664, max 1.0101. The memo reports the distribution rather
  than a confidence interval; quote the sd and percentiles, not a bare median.
- Decisive independent discriminator, immune to any length mislabel: the painted
  width of the line the solver calls "far" is **36.2 ft in 91 of 91 frames**
  (a 36 ft doubles baseline), while the far service line is separately detected
  at 60.0 solver-ft and 26.8 ft wide in **89 of 91**.
- The painted centre service line, which physically ends at 60 ft, reads
  **median 59.49 solver-ft (n = 91, sd 0.24, min 58.64, max 60.43)**.
- Render check: **20 of 20** rendered frames put the 78 ft edge on the painted
  far baseline, 0 of 20 on the far service line.

**Scope.** Four clips, three cameras, ACCEPTED frames only:
`tennis_nyYk2nPZAwY_720p` (Wimbledon grass 1280x720, 46/200 accepted, 40
tabulated), `tennis_459iho5_AFs` (Wimbledon grass 1920x1080, 83/200, 40
tabulated), `tennis_06` (Roland Garros clay 1920x1080, 10/200), and
`tennis_3x3eEWCZmWQ` (640x360, n = 1). Only the two grass clips carry n >= 40,
and G46 records that nyYk and 459iho5 may be the same Wimbledon court. Nothing
here is measured on hard court, and nothing is measured on rejected frames.

**What it does not say.** It does not say the solver is accurate against
surveyed truth -- no hand-labelled corner set exists for tennis (G31 section 6).
It says the specific ~1.3x error that would have invalidated the 5.28 ft anchor
and the G23 pseudo-labels is not present on these clips.

### 1.2 The solver accepts frames on grass and hard court at 1280x720 and above

MEASURED (G57, `g57_tennis_solver_generalization_2026-09-02.md`, MEASURED AND
CLOSED). 9 clips, 200 evenly spaced frames each, 1,800 frames total.

| slice | accepted / n | pct | Wilson 95 pct |
|---|---:|---:|---|
| hard court (2 clips, both 1080p) | 125 / 400 | 31.2 | [26.9, 36.0] |
| grass at 720p and above (4 clips) | 212 / 800 | 26.5 | [23.6, 29.7] |
| 1920x1080, all surfaces | 218 / 800 | 27.2 | [24.3, 30.4] |
| 1280x720, all surfaces | 129 / 600 | 21.5 | [18.4, 25.0] |
| per clip, grass+hard at 720p+ | 28 to 83 / 200 | 14.0 to 41.5 | narrowest [9.9, 19.5], widest [34.9, 48.4] |

Resolution is CAUSAL, not correlational: the same 1,400 frames from seven clips
downscaled to 640x360 with `cv2.INTER_AREA` fall from **347 / 1,400 = 24.8 pct
[22.6, 27.1] to 22 / 1,400 = 1.6 pct [1.0, 2.4]**, four of the seven clips to
exactly zero. The within-content control is sharper still: `nyYk` at 1280x720
accepts 46/200 and the same match, same camera at 640x360 accepts 0/200.

**Denominator caution.** G57's own honest-scope sentence attaches the pooled
347/1400 = 24.8 pct figure to "grass and hard at 720p and above", but that pool
INCLUDES the 10/200 clay clip. Removing it gives
**337 / 1,200 = 28.1 pct, Wilson 95 pct [25.6, 30.7]** `[recomputed here]`.
Quote the per-slice rows above in preference to the pooled figure.

**Scope.** Acceptance is a GATE PASS on a uniform time grid, not geometric
accuracy and not per rally. Hard court is two clips, both blue acrylic
(Melbourne, Cincinnati). The six grass clips may be as few as two or three
distinct court geometries at one venue. `tennis_01` to `tennis_05` were not
measured: their source videos are absent from the pod.

### 1.3 The pipeline is deterministic inside one environment, and tennis is the only sport whose tracking quality has ever been scored

MEASURED, two separate rows.

- G52 (`g52_tennis_reproducibility_2026-09-02.md`, RESOLVED): on the pod,
  **30 of 30 repeats bit-identical** across three modes (gpu_baseline,
  gpu_pinned, cpu_pinned), and frame decode **byte-identical over 10 reads** on
  both probes. Locally the same entry point reproduces the historical control
  column on **4 of 4** ranges. Both machines are internally deterministic.
- G47 (`g47_contract_rejection_census_2026-09-02.md`): of 187 pod harness
  reports, 119 fail on `coordinate_contract` and nothing else -- baseball 66/93,
  basketball 8/12, football 30/42, soccer 15/25, **tennis 0/15**. Tennis is the
  only sport in the program that has ever been scored on tracking quality at
  all; the other four were rejected before coverage, oob, jump or ball_valid
  could say anything.

Supporting, same class:

- G23 (CLOSED, landed 45b60357f): **2,013 unique pseudo-labelled frames** (from
  2,209 rows; 196 duplicated by two overlapping tennis_10 ranges), verifier
  viewed **40 of 40** holdout renders at per-corner zoom, all four doubles
  corners on the painted intersections in 40/40.
- G18 (CLOSED, c57bcb85e): across 15 sequential ranges x 300 decoded frames on
  3 matches, **0 of 15 ranges failed on jump_p95**, which is what closed the
  linspace sampling artifact. Render-and-look on 12 frames across 4 ranges:
  lines on lines in **12 of 12**.
- G45 (LANDED, de5c6ab46): the ball ground-projection guard contains the
  blow-up. Usable coordinate rows 1,831 -> 449, 2,630 -> 1,700, 2,946 -> 1,572,
  2,395 -> 845, with **zero** remaining values below -1,000 ft or above 84 ft.
  `test_ball.py` 4 passed. This is containment, not correctness (see 2.3).
- G71 (CLOSED, fc780068c): the G59 rejected-code contamination is a measured
  zero -- **0 of 13** pod tennis tracking tables and **0 of 15** tennis harness
  reports fall inside the 02:23:00Z-18:27:55Z window, and no landed memo or
  register row quotes an affected table.

---

## 2. WHAT IS BROKEN, ranked by how much it blocks

### 2.1 Player selection: the adapter fills two slots whether or not two players exist

**Blocks: the coverage gate, every oob number, the G38 jump diagnosis, and any
per-player teacher feature. This is the top blocker.**

Defect size, MEASURED:

- G66 (`g66_player_candidate_labels_2026-09-02.md`, DELIVERED): 210 candidates
  labelled by eye, 70 per clip over all 15 range strata --
  **player 51 / 210 = 24.3 pct [19.0, 30.5]**,
  **non_player_person 155 / 210 = 73.8 pct [67.5, 79.3]**,
  uncertain 4 / 210 = 1.9 pct [0.7, 4.8].
  On the enriched `stride_proxy_gt8` subset (n = 120): non_player_person
  **91 / 120 = 75.8 pct**; the lane's alternative 79.2 pct [71.1, 85.5] counts
  the 4 uncertain as non-player. State which denominator you mean.
- **Both alternative branches are empty: 0 of 210 `duplicate_of_player` and
  0 of 210 `not_a_person`** (each 0.0 pct [0.0, 1.8]).
- G18 render-and-look named specific frames: at tennis_09 f5070 the two emitted
  feet are staff at (46, 50) ft and a ball kid at (34, 41) ft while neither real
  player is emitted; at tennis_10 f255 the emitted far player is the chair
  umpire at (65, 49) ft.

**Cause: ESTABLISHED, by label rather than by elimination.** The wrong picks are
other PEOPLE -- ball kids, line judges, chair umpires, coaches -- not duplicate
detections and not spurious blobs. That makes it a person-CLASSIFICATION
problem.

**But the obvious fixes are both measured failures:**

- G70 (CLOSED AT LIMIT, 2510e5f77): a static-feature classifier scores
  **pooled out-of-fold accuracy 130/206 = 0.631 [0.563, 0.694] against a 0.738
  majority baseline** -- below it, and its 95 pct upper bound is below it.
  Player recall **21/51 = 0.412 [0.288, 0.548]**. Below baseline on every clip
  (tennis_09 0.529 [0.413, 0.641], tennis_10 0.714 [0.599, 0.807], nyYk 720p
  0.652 [0.531, 0.755]). At n = 51 positives with these features, player versus
  bystander is not separable.
- G26 attempt 1 (REJECTED by numbers, 948122992): a stipulated court prior of
  x = [-6, 84], y = [-4, 40] ft drove **oob to 0.0000 on all 15 ranges** and
  selected a real player in **12 of 13** rendered selections, but collapsed pass
  fractions from **5/5, 1/5, 4/5 to 1/5, 0/5, 1/5** -- real players project
  outside the prior.
- G26 attempt 2 (FALSIFIED at step 0, df4d8f5e2): the attempt-1 result did not
  reproduce (0/5, 0/5, 1/5) and solver coverage differed in 7 of 15 ranges. The
  lane correctly refused to fit an envelope. G52 later explained that
  non-reproduction as an ENVIRONMENT difference, not a code defect (see 4.3).

**One caveat the register carries and this document repeats: the "one root
cause" story is PARTIALLY FALSIFIED.** On tennis_02-05,
**oob_rows = 0 of 590 / 2,980 / 4,546 / 1,908 player rows -- zero on every
clip** -- while those same clips carry 46 / 508 / 254 / 370 jumps over 8 ft. So
oob failures and jump instability are separable, and the two-slot design is not
proven to cause both. It does cause the tautological coverage (2.2), which is a
code fact.

### 2.2 The tennis coverage gate is tautological and has never gated anything

**Blocks: every historical tennis PASS verdict is weaker than it reads.**

Defect size, MEASURED (G34 addendum, escalated as G40):

- `harness_metrics.coverage_pct` is **exactly 1.0 on 15 of 15** sequential
  ranges, while honest decoded-frame `solved_frame_coverage` over the same
  ranges runs **0.3967 to 1.0000, median 0.6767**.
- **7 of the 10 PASS ranges have decoded-frame coverage below the 0.90 bar**:
  0.4600, 0.5600, 0.5733, 0.6100, 0.6533, 0.6767, 0.8433. `tennis_10` range
  3585 passes the harness at **46 pct** honest coverage.

**Cause: ESTABLISHED, and it is a code fact.** `tracking_harness.py:37-38` sets
tennis `min_players: 2`; the adapter emits exactly one player per half on every
frame it emits, so numerator equals denominator. Measured across all 9 pod
tennis clips the per-frame player-id histogram is `{2: 8394}` over
**8,394 emitted frames** -- no other value occurs. The audit across all 8 sports
found the defect is NOT systemic: every other sport shows a real spread (npb
0.7975, kbo 0.7820, mlb 0.6430, wnba 0.5146, soccer 0.3905, ncaa_basketball
0.3018, football 0.1884). The gate logic is sound; the tennis adapter's fixed
two-slot design is what makes `min_players: 2` unsatisfiable to fail.

Related and separate, same row family (G40, OPEN HIGH, needs adjudication):
`tracking_harness.py:146` uses `n_frames = df["frame"].nunique()`, i.e. frames
that produced at least one row, not decoded frames as the program rail states.
Measured inflation on four tennis clips: **4.90x, 2.77x, 2.53x, 2.74x** (harness
0.1512 / 0.4393 / 0.5999 / 0.3284 versus 0.0309 / 0.1585 / 0.2372 / 0.1200 on
processable frames at stride 3). Those four per-clip numbers are themselves
provisional -- see 4.12.

### 2.3 The ball detector is not detecting the ball

**Blocks: every ball-derived feature -- rally tempo, serve speed, contact-frame
anchoring. Nothing downstream reads ball coordinates today, so it is blocking
future work rather than corrupting current numbers.**

Defect size, MEASURED:

- G39: **0 of 12** evenly spaced renders over the offending set are the tennis
  ball (Wilson 95 pct [0.0, 24.3]). 9 of 12 are the far player's head, body or
  racket; 3 of 12 are crowd, staff or a scoreboard graphic. In 4 of the 12 the
  real yellow ball is plainly visible elsewhere in the same frame.
- G45 corroborated it independently on the same-adapter sibling run: **0 of 8**
  newly rejected candidates are the ball (7 player body/head/racket, 1
  staff/crowd), Wilson 95 pct [0.0, 32.4] `[recomputed here]`.
- Magnitude before the guard: projected ball x reached **106,853.7 ft**
  (tennis_03) against a 78 ft court, single transitions of 126,001.0 and
  760,419.9 ft, and 34 to 70 rows per clip below -1,000 ft.

**Cause: ESTABLISHED for both halves, and the leading hypothesis was
FALSIFIED.**

- Falsified: "a near-singular homography". `cond(H)` is flat to four significant
  figures between well-behaved and blown-up rows -- nyYk 44,665 versus 44,707;
  3x3 21,550 versus 21,550.
- Established: the projection law. `1/|court_x|` tracks the ball pixel's
  distance to the ground plane's vanishing line at **r = 0.9654 (n = 188)** and
  **r = 0.8853 (n = 191)** on two instrumented re-runs.
- Established: the detector's only spatial rule is `y < 2/3 * height`, which on
  a 720-row frame excludes the entire near half of the court (rows 480-619) and
  admits the backdrop wall, crowd and scoreboard. There is no court-region gate,
  no plane gate and no ball-appearance gate.

G45 landed a homography-derived guard, so the output is now contained
(see 1.3). The INPUT is still not a ball, and both must hold before any
ball-derived quantity is trusted.

### 2.4 Clay: the solver finds the near half and never the far baseline

Defect size, MEASURED (G57, G60): **10 / 200 = 5.0 pct [2.7, 9.0]** on
`tennis_06` at 1920x1080. A separate 400-frame grid on the same clip gives
**28 / 400 = 7.0 pct [4.9, 9.9]** (a different grid, not a before/after). Six of
ten rejected frames viewed are pristine full-court 1080p views; the gate fires
at `horizontal_roles` because the far baseline and far service line are never
detected.

**Cause: SUSPECTED, and the leading mechanism has been measured and found
INSUFFICIENT.** G60 (`g60_clay_horizontals_2026-09-02.md`) measured that
**7,806 / 9,454 = 82.6 pct [81.8, 83.3]** of horizontal segments in the clay
decision set lie above the solver-derived court horizon, versus
**1,872 / 14,624 = 12.8 pct [12.3, 13.4]** on a hard-court control. Removing
every one of them lets role assignment pass on **4 / 40 = 10.0 pct [4.0, 23.1]**
clay frames but produces **0 / 40 = 0.0 pct [0.0, 8.8] full solver accepts** --
identical to the hard control, and a change of 0.0 percentage points. White paint
on orange clay carrying less luminance contrast remains a hypothesis, untested.

Note a register/memo divergence: the G60 register row still reads
`OPEN (HIGH)` and names the limit measurement as its FIRST JOB; the memo and
`RESULTS_LEDGER.md` both record it as CLOSED AT LIMIT.

### 2.5 640x360 footage is outside the solver's reach

Defect size, MEASURED (G57): **1 / 400 = 0.2 pct [0.0, 1.4]** on the two
natively 360p clips; pooled with the downscale control,
**23 / 1,800 = 1.3 pct [0.9, 1.9]**.

**Cause: ESTABLISHED as resolution itself**, by the downscale control and the
within-content nyYk pair (46/200 at 720p, 0/200 at 360p on the same match and
camera). The mechanism is visible in the renders: 7 of 14 rejected frames on the
worst clip are clean full-court views where the solver finds all five vertical
clusters and the whole near half, and the far half's paint is roughly one pixel
wide and is not recovered.

Exposure is smaller for tennis than for the corpus as a whole: G27 measures
25 of 61 pod clips (41.0 pct) at 640x360, but only **2 of 9 tennis clips**.
G37 (OPEN, LOW) records that sibling ranking picks the nyYk 720p copy over the
360p one by a 0.030 s duration difference (960.040 versus 960.010), so a 30 ms
wobble would flip it.

### 2.6 The learned keypoint route adds nothing at this label budget

Defect size, MEASURED (G31, CLOSED AT LIMIT): fold 0 (held out tennis_09, 1,713
train / 300 test) **PCK@7px 0.0774, median 17.395 px**; fold 1 (held out
tennis_10, 1,419 / 594) **PCK@7px 0.0355, median 17.475 px**. The
>= 4-keypoints-within-7px solve proxy is **0.0 on both folds**, so
**frames solved by the model and not by the classical solver: zero**.

**Cause: ESTABLISHED as model error, with a competing explanation FALSIFIED.**
The heatmap is 160x90 against 1920x1080, so one cell is exactly 12.0 source px
and the 7 px bar is 0.58 of a cell -- a real risk that the bar was untestable.
Quadratic sub-pixel refinement on the same checkpoints moved the median under
1 px in OPPOSITE directions on the two folds (17.395 -> 16.874,
17.475 -> 18.281) and left the solve proxy at 0.0. The error is 1.45 heatmap
cells, above the quantisation floor.

Two corrections travel with this row: it is a **2-fold** experiment, not 3
(`tennis_keypoint_train.py:190` takes folds 0 and 1 only; nyYk is never held
out), and the encoder defaults to torchvision `ResNet18_Weights.IMAGENET1K_V1`,
which this program flags research-only.

### 2.7 An unexplained 1.2 pct systematic bias in court length

Defect size, MEASURED (G58, OPEN MEDIUM): the ratio **0.9878, n = 91, sd
0.0058** reproduces G46 exactly and the sign is consistent across all four
clips.

**Cause: NOT ESTABLISHED. All three named hypotheses were tested and
falsified.** (a) Line centre versus inward edge: killed by the eye check -- all
7 paired 16x renders show the far fitted baseline on the EXTERIOR paint edge,
the opposite side the mechanism requires -- and a 2-inch line-edge model
predicts 0.9957, not 0.9878, so it is the wrong size as well as the wrong side.
(b) Lens distortion: survives only weakly; ratio-versus-centre-y r = -0.302 and
ratio-versus-court-height r = -0.295 at **n = 7**, with the direction
inconsistent within clips. (c) A wrong court-dimension constant: singles and
doubles share the same 78 ft length, so it predicts 1.000.

No correction has been applied and none may be until a cause is named.

### 2.8 Two harness defects that make the tennis jump evidence unreadable

- G82 (OPEN, HIGH): **`jump_p95` structurally excludes the tail it exists to
  catch.** 40-foot teleports at up to 5 pct of all steps leave jump_p95 pinned
  at 0.60 with verdict PASS; it only trips at 6 pct. Separately
  `groupby.diff()` differences consecutive ROWS, not FRAMES, so a clean path and
  one with ten 40-ft teleports across a 200-frame hole both report 0.6, PASS.
  This is the metric G38's entire diagnosis rests on.
- G83 (OPEN, HIGH, cheap): **G48's remediation field is dead in production.**
  `jump_p95_ft_per_s` needs `metadata['frame_stride']`; `adapter_run.py:124`,
  the only caller that passes metadata at all, hands over probe_media's dict
  which has no stride. `sampling_interval_s` is None and
  `sampling_interval_reason` reads "frame stride unavailable" on every real run.

### 2.9 Evidence durability

G54 (OPEN, HIGH, cheap) and G62. Two named tennis claims are already
unrecoverable because their artifacts lived only in `/tmp` or were overwritten
(see 3.3 and 4.13). G62 records that
`tennis_player_select_limit_2026-09-04/report.json` -- the artifact behind the
G52 reproducibility claim -- has exactly two top-level keys, `bounds` and
`matches`: no host, no timestamp, no library versions. That is why the G26b
local-versus-pod confusion took three passes to see.

---

## 3. WHAT IS UNKNOWN, AND WHY

### 3.1 Not yet measured (a lane could answer these)

- **Whether any tennis geometry claim replicates off grass.** The 5.28 ft
  classical anchor, the G46 length ratio and the G23 pseudo-labels were all
  measured on grass clips. G57 states this explicitly: whether they replicate on
  hard court "is now a cheap, answerable question, and it is NOT answered here".
- **Whether accepted frames on clay or at 360p are geometrically correct.** The
  10 accepted clay frames and the single accepted 360p frame have never been
  checked for correctness at all; acceptance is a gate pass, not accuracy.
- **Acceptance conditional on live play.** Every acceptance rate in G57 is per
  frame on a uniform time grid. A clip accepting 5 pct of uniform frames could
  still solve every rally. Not measured.
- **`tennis_01` to `tennis_05` acceptance, resolution and duration.** Source
  videos absent from the pod; G42's ~4x length difference is inferred from the
  emitted frame span (max frame 28,770 versus 7,500), not from ffprobe.
- **The one-variable cv2 test.** Pinning cv2 to 4.14.0 locally and changing
  nothing else. G52 names it as the decisive test and records that it has not
  been run.
- **G78B: the 32 uncertain `tennis_09` rows.** No resolved artifact exists for
  that clip.
- **Any tennis error against hand-labelled corner truth.** No hand-annotated
  corner set exists, so PCK numbers and the 5.28 ft anchor measure distillation
  fidelity and self-consistency, not accuracy against truth (G31 section 6,
  research-plan row T5).
- **Whether the same stale-homography fix (f16b3863a) hit soccer.** G42 examined
  tennis only; the commit touched the soccer adapter too.

### 3.2 Measured, and the answer was inconclusive

- **The y-gate disagreement, 52 pct versus 78 pct.** See section 5 of this
  document. G44B lists "Resolution of the 52 pct versus 78 pct in-gate
  disagreement" under NOT VERIFIED. It decides whether the spatial gate is the
  main recall loss or a minor one.
- **The 1.2 pct length residual (G58).** Three hypotheses, all falsified; the
  surviving one survives only because n = 7 cannot kill it.
- **Clay (G60).** The leading mechanism is real and strongly concentrated
  (82.6 pct versus 12.8 pct) but insufficient: 0/40 full accepts.
- **Player versus bystander (G70).** The classifier is below the majority
  baseline, which IS an answer at this n and with these features. What is
  inconclusive is whether more labels, motion features or image features would
  change it -- the memo makes no causal claim either way. Its own planning
  arithmetic: about 93 positives, i.e. roughly 383 candidates at G66's 24.3 pct
  prevalence, would pin player recall to +/- 0.10.
- **G26 attempt 2.** Stopped on a falsified premise; the falsification itself
  later turned out to be an environment artifact (4.3), so it settled nothing
  about the selector.

### 3.3 Cannot be measured with this corpus

- **The G38 endpoint join.** G38's evidence is on tennis_02-05; G66's labels are
  on tennis_09, tennis_10 and nyYk 720p. There is no clip overlap, the G38 raw
  tables are gone locally and on the pod, and the three labelled clips retain
  **zero** selected-player tracking tables. Observed stride-adjacent >8 ft
  selected-player pairs: **n = 0**. No fraction and no Wilson interval is
  constructible. G38B is NOT VALIDATED on exactly this limit.
- **Independent recomputation of G44's aggregates.**
  `g44b_label_artifact_status_2026-09-02.json` records
  `"published_g44_per_frame_labels_present": false` with the source video
  present both locally and on the pod. G44's 32/50 and 16/31 are documentary
  values only.
- **Any image-space measurement on tennis_02-05.** Source videos deleted from
  the pod; only download logs and 450-frame 960x540 overlay demos remain.
- **A second clay venue.** None exists in the corpus and none was acquired, so
  "the solver fails on clay" cannot be separated from "the solver fails on this
  Roland Garros broadcast's grade, sponsor band or camera".
- **Non-blue hard courts.** The two hard clips are both blue acrylic with a
  light surround. Green, grey and other paints are absent from the corpus.
- **Reconstruction of the G26b local runs.** The report.json carries no
  environment at all and G62 deliberately did not retrofit one, on the grounds
  that no provenance field may be invented.
- **Re-ingest of 360p tennis siblings at higher resolution.** G27 is BLOCKED on
  an ACCESS LIMIT: current cookies expose no HLS 300/301 and DASH sections
  return 403.

---

## 4. CLAIMS RETRACTED OR REVERSED, WHICH MUST NEVER BE RE-QUOTED

This is the most important section. Each entry quotes the retraction and names
what replaced it.

### 4.1 "Tennis tracking collapsed by three orders of magnitude" -- REVERSED

Original framing (G42, filed as a HIGH regression): healthy tables on
2026-09-01 06:04-07:39 (tennis_01 9,548 rows, tennis_02 2,422, tennis_03 5,611,
tennis_04 7,493, tennis_05 4,304) versus degenerate tables 17:14-21:22
(tennis_07 9, tennis_09 5, tennis_06 1, tennis_10 1, tennis_459iho5_AFs 1).

Retraction, register G42: **"CAUSE ESTABLISHED 2026-09-02 and the framing
REVERSES -- the collapse was the FIX working. f16b3863a stopped the adapter
reusing a stale homography on an unsolved frame; the pre-fix tables were
inflated 145.7x by carried-over calibration (docs/TRACKING.md:34). The
degenerate tables are the HONEST ones."**

Replaced by: the decisive artifact is the CSV header width -- every healthy
table has 5 columns and every degenerate table has 9, and the four extra columns
are written by `write_csv` in the tennis adapter, so the daemon provably was not
running the same code at 06:04 and 17:14. The 145.7x is `0.976 / 0.0067`, i.e.
recorded coverage 0.976 was 99.3 pct carried-over calibration against an honest
0.0067. Ruled out with evidence: daemon settings (24 active in both windows),
model/weights path, and the 2700 s timeout as the cause of the final row counts.

### 4.2 "cv2 5 caused the 5-row tennis_09 table" -- RETRACTED

Retraction, `RESULTS_LEDGER.md`: **"the claim that the 5-row tennis_09 table was
CAUSED by cv2 5 is FALSE and is retracted... NO tracking table was written while
cv2 5 was installed and the corpus took ZERO damage."** The
`opencv_python-5.0.0.93` dist-info was created 2026-09-02 13:33 and replaced at
14:41, a 68-minute window; the newest tracking table of any sport is mlb at
2026-09-02 01:29, which predates it.

Replaced by: G42's stale-calibration fix as the cause of the degenerate window,
and G55's 2,700 s job budget as the reason tennis stopped producing long runs.
What survives untouched: cv2 5 really does return `HoughLinesP` as (N,4) and
every `[:, 0, :]` site raises IndexError under it, so the G41 shape hardening
stands on its own merit. What was wrong was attributing an existing symptom
to it.

### 4.3 "The tennis pipeline is not reproducible run to run" -- FALSE

Retraction, register G52: **"RESOLVED 2026-09-02. The original text is FALSE and
must never be quoted."**

Replaced by: the pipeline is deterministic in BOTH environments; the two runs
simply came from different ones. The pod is bit-identical 30/30; running the
same ranges locally on master's code reproduces the G26b **control** column on
**4 of 4** ranges (5715 0.6100, 43830 0.5600, 33105 0.9900, 41985 0.5733) while
the pod reproduces the **treatment** column. The G26b control and treatment were
one LOCAL run and one POD run compared as though they shared an environment.

**Standing consequence: every tennis before/after comparison that mixed a local
run with a pod run is invalid, including the G26 acceptance rule that tried to
hold coverage constant as a control. G26's two attempts must not be re-quoted as
a controlled comparison.** Still open and small: the environments differ in cv2
(4.11.0 local, 4.14.0 pod), OS and Python version simultaneously, so the
specific factor is not isolated.

### 4.4 "The rejected player selector was moving solver coverage" -- FALSIFIED

This was G52's own replacement hypothesis, and it was the more actionable one.
The control arm deployed master's `adapter.py` and removed `player_select.py`
from the filesystem entirely, then re-ran the same ranges: **"Removing the
rejected selector did not restore a single value. The selector is not the
cause."** Every changed range still returned the treatment value.

### 4.5 "The court solver labels the far SERVICE line as the far BASELINE" -- FALSIFIED

Original (G39 section 4, read off 12 renders of one clip by one observer, and
listed by G39 itself under NOT VERIFIED): a ~1.3x scale error on the
court-length axis of every tennis `court_feet` measurement.

Retraction, register G46: **"CLOSED -- FALSIFIED 2026-09-02."** The premise
predicts a length ratio of 1.30; the measurement is 0.9878 over n = 91. Painted
width shows the far line is a 36.2 ft doubles baseline in 91/91 while the far
service line is separately found at 60.0 solver-ft and 26.8 ft wide in 89/91.
20/20 renders put the 78 ft edge on the painted baseline. Nothing projects near
116 ft in any frame of any clip.

Replaced by: an explanation of why the original read was plausible -- the net's
top tape is 3 ft off-plane at 39 ft and its camera ray meets the ground at
roughly 54 solver-feet, within about ten image rows of the far service line --
and by G58, which inherits the small unexplained 1.2 pct residual.

### 4.6 "The tennis solver collapses off grass" -- CORRECTED

Original (G57's premise, read off G46 section 7): nyYk 720p grass 46/200,
459iho5 1080p grass 83/200, but tennis_06 1080p clay 10/200 and 3x3 360p 1/200.

Retraction, G57: the four numbers reproduce exactly, but **"the 'grass only'
framing is wrong and should be retired."** Register G57: **"MEASURED AND CLOSED
2026-09-02, framing corrected -- NOT grass-only."**

Replaced by: hard court is the second-best surface at 125/400 = 31.2 pct
[26.9, 36.0], and holding resolution at 720p+ grass is 212/800 = 26.5 pct
[23.6, 29.7], indistinguishable from hard. The tennis lane is a
HIGH-RESOLUTION lane. The real limits are clay (5.0 pct [2.7, 9.0]) and 640x360
(1.3 pct [0.9, 1.9]).

### 4.7 "The ball blow-up is a near-singular homography" -- FALSIFIED

Original leading hypothesis, carried by G38 section 2 and the G39 register row.

Retraction, G39: **"CAUSE ESTABLISHED, and the leading hypothesis is FALSIFIED.
The homography is not near-singular."** `cond(H)` is flat to four significant
figures between well-behaved and blown-up rows (nyYk 44,665 versus 44,707;
3x3 21,550 versus 21,550) and does not discriminate at all. Stale calibration is
ruled out too: every emitted ball row carries `solved` or
`camera_lock_drift_checked` provenance.

Replaced by: a detection failure (0/12 renders are the ball) amplified by an
unguarded ground-plane projection of off-plane pixels, with the projection law
confirmed at r = 0.9654 (n = 188) and r = 0.8853 (n = 191).

### 4.8 "Players in the same frames stay within 82.93 ft" -- NOT SUPPORTED

Original: G38 section 5, used to argue the ball blow-up was isolated.

Retraction, G39 section 1: **"'players in the SAME frames stay within 82.93 ft'
is not what the tables say: 82.93 ft is the clip-wide player maximum. In the
frames where the ball exceeds 500 ft there are zero player rows on tennis_02,
_03 and _05, and two on tennis_04."** Across all four clips, **1 of 727** rows
with |x| > 500 shares a frame with a player pair.

### 4.9 "72.7 pct uncertain is the honest headline; it bounds every recall claim anyone can ever make" -- RETRACTED, AND THE REPLACEMENT IS ALSO NOT YET SAFE TO QUOTE

Original (G65 register row): 109 of 150 labels (72.7 pct [65.0, 79.2]) were
explicitly uncertain, framed as the detectability limit of broadcast footage.

Retraction, register G78: **"This retracts the framing I recorded on G65...
On the evidence of the first chunk that is wrong -- the ball IS labellable, it
just needs more zoom than attempt 2 used."** G78C resolved **29 of 30**
previously-uncertain nyYk rows to ball-visible after tiled 2x views; exactly 1
survives as genuinely uncertain (96.7 pct [83.3, 99.4] `[recomputed here]` from
`g65_ball_labels/resolved/tennis__tennis_nyYk2nPZAwY_720p.csv`).

**But the projection attached to that retraction has not held, and must not be
quoted either.** The register row projects "if the rate holds, the visible count
goes from 41 of 150 to roughly 145 of 150". A second chunk artifact,
`g65_ball_labels/resolved/tennis__tennis_10.csv` (47 rows, written after the
register row), resolves only **13 of 47 = 27.7 pct [16.9, 41.8]**
`[recomputed here]`; the other 34 are recorded as "motion blur after tiled 2x
review". Pooled over the two landed chunks the resolution rate is
**42 of 77 = 54.5 pct [43.5, 65.2]**, and the running visible total is
**83 of 150 = 55.3 pct [47.3, 63.1]**, not 145. G78's own text already warned
"Do NOT yet quote a pooled figure"; that warning is now backed by a measurement.
G78B (tennis_09, 32 rows) has no artifact yet. **Neither G65's 72.7 pct framing
nor G78's ~145/150 projection is quotable today.**

### 4.10 "0.897 coverage, harness PASS" as the tennis flagship -- RESTATED

Original (G05/G18 headline, `RESULTS_LEDGER.md`): sequential range 15300-15600,
0/31 -> 270/301 = 0.897, harness PASS.

Restatement, G34 section 5: `coverage_pct` is exactly 1.0 on 15 of 15 ranges and
the tennis coverage gate cannot fail. **"The claim '0.897 coverage, harness
PASS' should be read as '0.897 solve coverage, and the harness passed it on oob,
jump and ball_valid, with the coverage gate inert'."** The 0.897 itself is a
`solved_frame_coverage` and is honest; the PASS beside it carried no
information. Seven of the ten PASS ranges have decoded-frame coverage below the
0.90 bar.

### 4.11 "One root cause ties G26, G38 and the G40 tautology together" -- PARTIALLY FALSIFIED

Original: the same-night hypothesis that the two-slot adapter design causes the
tautological coverage, the oob failures and the jump instability.

Retraction, `RESULTS_LEDGER.md`: **"oob_rows = 0 of 590 / 2,980 / 4,546 / 1,908
player rows -- ZERO on every clip -- while those same clips carry 46 / 508 /
254 / 370 big jumps over 8 ft... clips with many jumps and zero oob prove the
two failures are separable."**

Replaced by: on those clips every oversized jump happens entirely inside the
court bounds, so the partner is a wrong ON-COURT candidate (baseline ball kid,
line judge, or a duplicate detection of the same player), not a courtside person
pulled in from outside the box. The two-slot design still explains the
tautological coverage, which is unaffected.

### 4.12 G38's own jump numbers -- PROVISIONAL, AND NOW UNVERIFIABLE

Retraction, `RESULTS_LEDGER.md`: **"tennis_01 to tennis_05 are PRE-FIX tables,
so their rows include positions projected through a STALE homography and stamped
as fresh. Every measurement I took from them today inherits that."** Named as
affected: the G38 jump_p95 diagnosis (median 0.5 ft, p95 10-37 ft, the 10-29 ft
band, the stride-adjacent split 65.4 / 64.3 / 56.7 pct) and the G34 per-clip
denominator table (0.1512 / 0.4393 / 0.5999 / 0.3284 versus 0.0309 / 0.1585 /
0.2372 / 0.1200). **"The numbers must be re-measured on post-fix tables before
any of them is quoted again."**

Compounding it, G38B then established that those tables are gone locally and on
the pod, so on those clips the numbers cannot be re-measured at all: they are
**UNVERIFIABLE**, not merely provisional. G38's structural VERDICT (the per-half
slot choice is unstable) is believed to stand and is independently supported by
G66's labels on different clips; its percentages are not quotable. G34's
denominator finding is a code fact and is unaffected.

### 4.13 G44's 64 pct and 52 pct -- UNVERIFIABLE

Not retracted as wrong, but no longer evidence. G44B: **"the original G44
per-frame labels did not survive, so they cannot be independently
recomputed."** `g44b_label_artifact_status_2026-09-02.json` records
`published_g44_per_frame_labels_present: false` while confirming the source
video is present both locally and on the pod. Quote 32/50 and 16/31 as
documentary values from `g44_ball_detectability_limit_2026-09-02.md`, never as
a measurement anyone can check.

### 4.14 "Tennis tables written under rejected pod code are contaminated" -- MEASURED TO ZERO

Original (G59): **"Any tennis table the pod has produced since 02:23 UTC carries
that behaviour, so tennis coverage and oob figures measured on pod tables after
that time describe the REJECTED selector rather than master."**

Superseded by G71, which measured the window 2026-09-02 02:23:00Z to 18:27:55Z
and found **0 of 13** pod tennis tracking tables (184 total), **0 of 15** tennis
harness reports (187 total) and **no** landed memo or register row quoting an
affected table. The likely reason the window is empty is G55: tennis runs in
that period were being killed at the 2,700 s budget with rows = 0. Two open
defects happened to cancel, and neither is thereby fixed.

### 4.15 Three register-level beliefs about G31 that were wrong

From the 2026-09-03 worktree re-measurement and the G31 memo:

- "T3 is leave-one-match-out over 3 folds" -- **wrong**. The trainer accepts
  folds 0 and 1 only; nyYk is never held out. It is a 2-fold result.
- "The trainer is UNCOMMITTED in a6" (memory `tracking_week_program_2026_09_01`
  and `.planning/NOW.md`) -- **wrong**. It is committed as b78d8cb46, and a
  worktree sync on that belief would have been resolved the wrong way.
- "The 7 px bar may be untestable because of heatmap quantisation" --
  **falsified** by the sub-pixel probe (see 2.6).

### 4.16 "G48's sampling-interval remediation landed" -- WRONG AS RECORDED

Register G83: **"G48 landed the field and I recorded it as landed; it has never
once carried a value in production... A landed field that is always null is not
a landed fix, and the register should not have said so without checking a real
run."**

---

## 5. THE LIVE DISAGREEMENT: 52 pct versus 78 pct in the y-gate

Both sides, neither picked.

**The 78 pct side (G65).** Of 41 eye-confirmed visible balls,
**32 fall inside `y < 2/3 * height` = 78.0 pct, Wilson 95 pct [63.3, 88.0]**.
Denominator: 150 seeded, evenly spaced frames drawn from continuous rally-view
windows on three clips -- `tennis_09` (1920x1080), `tennis_10` (1920x1080) and
`tennis_nyYk2nPZAwY_720p` (1280x720), 50 each. Method: court-band crop at 1.3x
plus a tiled 2x fallback. **Recomputable, and I recomputed it: 150 rows, 41
visible, 109 uncertain, 32/41 in gate, exactly as published**
`[recomputed here from g65_ball_labels/labels.csv]`.

**The 52 pct side (G44).** Of 31 classified sightings,
**16 fall inside `y < 480` = 52 pct**, checked against a drawn reference line
rather than inferred. Denominator: 50 confirmed live-rally frames on ONE clip,
`tennis_nyYk2nPZAwY_720p`, sampled from two rally windows totalling 1,920
frames, with 14 of 64 sampled frames excluded as not live rally and 1 of 32
sightings left unclassified. **Not recomputable: the per-frame labels do not
exist (4.13).**

**What is and is not comparable.** The two are not the same quantity. G44
conditions on confirmed live-rally frames on a single 720p clip; G65 uses all
sampled rally-window frames across three clips, two of them 1080p. G44's
concentration finding is also specific and would be lost in a pooled number:
nine consecutive sampled frames from one sustained baseline rally were all
ball-visible and all excluded. The corresponding G65 caution is that 41/150 must
never be differenced against G44's 64 pct.

**What the newer labels say.** Recomputing the in-gate share over G65's 41
positives plus the two landed G78 chunks gives
**64 of 83 = 77.1 pct, Wilson 95 pct [67.0, 84.8]**, and it splits sharply by
clip: nyYk 720p **43/49 = 87.8 pct [75.8, 94.3]**, tennis_09
**12/18 = 66.7 pct [43.7, 83.7]**, tennis_10 **9/16 = 56.2 pct [33.2, 76.9]**
`[recomputed here]`. That is consistent with 78 pct and inconsistent with 52 pct
on the SAME clip G44 measured, which is the sharpest form of the conflict. It
does not resolve it, because the two label sets condition on different frame
populations and G44's cannot be inspected.

**Why it matters.** G44B states it plainly: this is the difference between the
spatial gate being the main recall loss and a minor one, so it decides whether
a gate fix is worth building at all. G44's own combined ceiling of
0.64 x 0.52 ~= 33 pct of rally frames rests on the 52 pct figure; at 78 pct the
same arithmetic gives ~50 pct, and both are ceilings above a detector currently
measured at 0 of 12 correct.

---

## 6. THE CRITICAL PATH: one week, ordered

Each item names what it unblocks. Items 1-3 are sequenced; 4-6 can run beside
them.

**1. Let the tennis adapter emit fewer than two players.**
Today it emits exactly one per half on every frame it emits -- histogram
`{2: 8394}` across 8,394 emitted frames on 9 clips. This single design choice
makes the coverage gate mathematically unable to fail, and is the mechanism that
forces a courtside person into a slot when a real player is not detected.
G34 section 6 already names it: "the honest fix and it is an adapter change, not
a harness change". `domains/tennis/tracking/adapter.py` is not under the
human-gated tree.
*Unblocks:* the coverage gate becomes live (G40, G34); oob and jump become
interpretable rather than artifacts of a forced fill; G26 gets a meaningful
acceptance criterion for the first time. Costs nothing downstream because tennis
already fails every clip-level verdict.

**2. Produce post-fix selected-player tracking tables for clips G66 labelled.**
Right now `tennis_09`, `tennis_10` and `nyYk_720p` have **zero** retained
selected-player tables locally and on the pod, and G38's own clips are gone.
Four separate rows are stuck on this single missing input.
*Unblocks:* G38 (endpoint join, n = 0 today); G38B; G26's acceptance comparison,
which must now be run entirely within ONE environment per G52; and any
re-measurement of the G38 percentages that 4.12 forbids quoting. Precondition
already satisfied: G73 raised the job budget to 12,000 s, above the pre-budget
tennis median of 7,513.5 s (n = 6) that the old 2,700 s budget was killing.
Rule that must travel with it: copy the tables under `docs/evidence/` before the
lane reports (G54), and preserve the full column set, not the subset the lane
needs.

**3. Finish G78 and settle the y-gate disagreement on its own denominator.**
One chunk remains (tennis_09, 32 rows). Then report the in-gate share on the
fully resolved set, per clip and pooled, with Wilson intervals, and state
explicitly that G44's 52 pct is documentary because its labels are gone.
*Unblocks:* G44B's held-out recall and precision, which needs 100 resolved
positives for a 50/50 split; today the running total is 83 of 150 with one chunk
outstanding. It also decides whether item 4 is worth building.

**4. Only then, change the ball detector's spatial rule and add an appearance
gate.** Not before item 3, because a gate fix sized on the wrong number trades
one error for another, and not before there are known non-ball labels, because
precision cannot otherwise be scored without fabricating it.
*Unblocks:* every ball-derived teacher feature (rally tempo, serve speed,
contact-frame anchoring), and re-opens the G43 adjudication on whether
`ball_in_bounds_pct` should gate. The projection half of this is already done
and landed (G45).

**5. Pass the stride that `adapter_run` already computes into `metadata`
(G83).** One line. `sampling_interval_s` is currently None on every real run.
*Unblocks:* G48's actual purpose -- comparing a SPEED rather than a raw distance
across clips whose sampling interval varies by 25 pct -- and it is a
precondition for any honest reading of jump on the new tables from item 2. Then
adjudicate G82, which is the harder question: `jump_p95` cannot see the tail it
exists to catch, and a threshold change needs adjudication rather than a lane.

**6. Run the one-variable cv2 test.** Pin cv2 to 4.14.0 locally, change nothing
else, re-run the four nyYk ranges.
*Unblocks:* cross-environment comparison generally. Until it is run, no local
number and no pod number may be differenced, which currently invalidates the
cheapest form of every before/after experiment tennis wants to run.

**7. Replicate the geometry claims on hard court.** Run the G46 length-ratio
probe and the 5.28 ft anchor on `tennis_09` and `tennis_10`. G57 names this as
cheap and unanswered, and `tennis_09` alone accepts 78 frames -- more than any
single clip G46 used.
*Unblocks:* the scope sentence on every tennis geometry number, all of which
currently say "grass".

**Deliberately NOT on the critical path this week:**

- **Clay (G60).** The leading mechanism has been measured and is insufficient
  (0/40 full accepts after removing 82.6 pct of horizontals), it is one clip at
  one venue, and no second clay source exists in the corpus. Anything built here
  would be fitted and scored on the same broadcast.
- **A learned keypoint model (G31).** Closed at limit; the student adds nothing
  the classical solver does not already provide, and the licence-clean variant
  was never trained. The unlock is hand-labelled corner truth (research row T5),
  which is a corpus problem, not a modelling one.
- **360p re-ingest (G27).** BLOCKED on an access limit -- no fresh cookie jar,
  no alternate client. Only 2 of 9 tennis clips are affected.

---

## 7. Divergences found while writing this document

Recorded so a later reader is not confused; nothing was changed.

- The **G60 register row still reads `OPEN (HIGH)`** and names the limit
  measurement as its FIRST JOB, while `g60_clay_horizontals_2026-09-02.md` and
  `RESULTS_LEDGER.md` both record it as CLOSED AT LIMIT with the measurement
  done.
- The **G78 register row says "2 of 3 chunks still running"**, but
  `g65_ball_labels/resolved/tennis__tennis_10.csv` (47 rows, 13 visible) exists
  on disk and was written after that row. Its rate contradicts the row's
  projection (4.9). No lane has verified it.
- **G57's honest-scope sentence pools the clay clip** into a figure it attributes
  to grass and hard court (1.2, above).

## 8. Artifact status at write time

Present locally and readable: `g57_data/` (10), `g57_renders/` (30),
`g57_scripts/` (3), `g46_renders/` (20), `g46_scripts/` (2), `g58_renders/` (8)
plus `g58_measurement.json`, `g60_renders/` (10) plus
`g60_clay_horizontals_2026-09-02.json`, `g39_renders/` (12), `g45_renders/` (8),
`g65_ball_labels/` (labels.csv, 170 renders, 2 resolved CSVs),
`g66_player_candidate_labels/` (labels.csv, 210 renders), `g70_classifier/` (6),
`g52_reproducibility/` (10), `tennis_sequential_plan_2026-09-01/` (3 JSONs plus
overlays), `tennis_keypoint_heldout_2026-09-02/` (10),
`g59_rejected_pod_code/` (3).

Absent, and the reason a claim is marked UNVERIFIABLE above: G44's per-frame
labels (both locally and on the pod); the tennis_02-05 tracking tables and their
source videos; the `/tmp/tennis-camera-lock-master` overlay behind G05's 0.1018
and G34's 0.4167 (durability audit marks both AT_RISK); 7 of 9 paths cited by
`g42_tennis_collapse_cause_2026-09-02.md`.
