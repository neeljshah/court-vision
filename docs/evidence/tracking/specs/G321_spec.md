GAP G321 | sport wnba | worktree a6 | log cx_g321_semantic_provider_abstention
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check against every line of
section B before you report.
**CAUSE-NAMING AND MEASUREMENT ONLY. NO FITTING, NO HOMOGRAPHY CLAIM, NO REGISTRATION, NO PREDICTION,
NO DETECTOR RUN AND NO MODEL RATER IN THIS ROW.** `src/`, `domains/` and `kernel/` are READ and IMPORT
only. Build in `scripts/platformkit/tracking/` (not human-gated; additive only; <= 300 LOC per file).
**THIS ROW DOES NOT UNBLOCK G306, G307 OR G308 AND DOES NOT REOPEN G304, which is CLOSED AT LIMIT
after two attempts.** A cause named here is not a fix, and an emission is not a correct landmark.

PREMISE (step 0) -- THREE BINDING BEFORE-CONDITIONS. Measure all three FIRST, print all three, and
run nothing else until they are in the memo.

  **P1 -- THE ABSTENTION REPRODUCES.** G304 attempt 2 measured `semantic 0` proposals on 63 of 63
  eligible native-1080p frames (`g304_proposal_verify_build_2026-09-07.md`, per-arena 174/174 and
  204/204). Run `domains.basketball.tracking.keypoints.BasketballKeypointProvider().detect(frame)`
  **UNMODIFIED, with its default `min_edge_support=0.16`**, on all 24 G296 formula frames and print
  the per-frame key count. **A non-zero detection on any frame is PREMISE PARTIALLY FALSIFIED -- a
  VALID result (Q8): report it with the frame indices and continue, because the row's question is the
  gate, not the count.** A non-zero count on ALL 24 is PREMISE FALSE: write the memo, commit, stop.

  **P2 -- WHAT THE 113 POINTS ACTUALLY ARE.** `docs/evidence/tracking/g296_ground_truth_2026-09-07.csv`
  carries 186 rows, 113 of them non-`dropped` (28 `adjudicated_A`, 84 `adjudicated_B`, 1 `agreed`)
  over 16 of the 24 frames. Its columns are `frame_id,player_ordinal,x,y,source,distance_px,note` and
  its notes read like `B at sole of green shoe` and `base of white shoe at court line`. **PRINT the
  header and five verbatim notes drawn EVENLY across the file.** If these are PLAYER FOOT-CONTACT
  points and not named court markings -- which is what the schema says -- then the register row's
  "proposal within 8 px of a named landmark" **IS NOT A LANDMARK RECALL**, and the following sentence
  goes in the memo VERBATIM: *"The 113 G296 points are adjudicated player foot-contact positions, not
  named court markings; a court-landmark proposal within 8 px of one of them is a proposal sitting on
  a PLAYER, so the 8 px count is a DEFECT count, never a hit count, and this row therefore establishes
  NO landmark recall for any provider."* The verdict then rests on clause 6b, and **the 8 px count is
  still computed and reported for every cell, as the on-player diagnostic it is.**

  **P3 -- THE VOCABULARY CEILING, BY ARITHMETIC, BEFORE ANY IMAGE IS OPENED.**
  `scripts/platformkit/tracking/g304_proposals.py:SEMANTIC_MAP` maps six provider keys onto FIVE
  distinct G304 vocabulary names (`LANE_BASE_L`, `LANE_BASE_R`, `FT_LINE_L`, `FT_LINE_R`, `KEY_TOP`)
  spanning TWO marking structures (`lane_boundary`, `free_throw_line`); `center_circle` is
  deliberately unmapped. Print those two counts from the live dict, never from this sentence. **If the
  map yields < 6 names or < 3 structures, then NO gate repair whatsoever can make the semantic family
  ALONE fill an E1 frame under G304's >= 6-names-over->= 3-structures rule, and the row must say so
  before it relaxes anything** -- and must then report the RAW provider emission (up to four lane
  corners plus up to three circle keys) separately, so attempt 3 learns whether the ceiling is THE MAP
  or THE GATE. **These are two different defects and the memo names which one it measured.**

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **ENTIRELY LOCAL CPU. NO POD, NO GPU, NO `pod_run`, NO GPU LEASE, NO POD FRAME EXTRACTION.**
    The G296 source is on this box: **`data/videos/bridge/wnba_01.f137.mp4`, h264 1920x1080,
    2,841,750,689 bytes, sha256 `f2421bc24e5cbb28f41fa79f9ea755b2eeff4daebd48dc5496cc97e5617cf9d3`**
    -- the orchestrator recomputed that hash on 2026-09-07 and it matches the file named by
    `g296_merge_2026-09-07.md` section 1. **Confirm the hash yourself (A9) before decoding.** Only if
    it fails byte identity may frames be extracted on the pod per the G304 packet memo, to `/tmp/g321/`
    and back by `scp`, **never touching `track_daemon`, its stage or `/workspace/nba-ai-system`.**
  - The 24 frame indices are the sealed G296 formula `round(i * 174429 / 23)` for `i` in `0..23`
    (0, 7584, 15168, 22752, ... 174429), cross-checked against
    `g296_merge_artifact/frame_identity.json`. Decode them yourself and record each decode's SHA-256.
  - **ONE BROADCAST, ONE ARENA (`wnba_01`, transcribed as Gateway Center). That is this row's LIMIT
    and it is stated in the verdict line, not buried.** Nothing measured here generalises to
    `wnba_04`, to Climate Pledge, or to any other arena, sport or resolution.
  - **NO DISK GUARD REQUIRED** -- this row writes frames, JSON, CSV and <= 6 JPEGs, never corpus
    video. **Delete no corpus source and no bridge partial download.** Report bytes added.

**METHOD (step 1) -- in this order, and never out of it:**
  1. **SEAL THE PREREG ALONE, BEFORE ANY MEASUREMENT (Q1).** One commit containing only
     `docs/evidence/tracking/g321_prereg_2026-09-07.md`, carrying: the 24 frame indices and their
     decode SHA-256s, the source SHA-256, the full relaxation grid of clause 5 with every constant,
     the 8.0 px one-to-one matching rule, the clause-7 bars verbatim, and a SHA-256 seal over its own
     LF-normalized bytes above the seal line. **No number measured after this commit may change a
     grid cell, a threshold or a bar.** The P1/P2/P3 premise measurements run AFTER this commit.
  2. **TRACE THE GATE READ-ONLY AND NAME EVERY CONDITION AS `file:line`.** The chain to walk is
     `keypoints.py:detect` -> `_paint` -> `_candidate_quads` -> `_ordered_quad` -> `_line_support`,
     then `_name_paint` and `_circle_landmarks`. Enumerate EVERY rejecting condition in it -- the
     Canny thresholds, the 120 px perimeter floor, the `approxPolyDP` epsilon, the exactly-four-vertex
     test, the 400 px^2 and convexity tests, the `0.006 * w * h` area floor, the `0.15 * height`
     minimum-side floor, the `min_edge_support` floor, and in the circle path the `solve_homography`
     null return and the 3.0-unit canonical distance test. **Also state whether ANY exception is
     swallowed and whether any import is missing** -- a swallowed error and a threshold are different
     causes and the memo says which it found. **NO EDIT to `domains/` or `src/`, not even a comment.**
  3. **BUILD A PARAMETERISED SHADOW WITH A FIDELITY PIN.** `domains/` may not be tuned, so the grid
     runs against a re-implementation of the same chain in
     `scripts/platformkit/tracking/g321_semantic_gate.py` whose every constant is an argument.
     **At the BASELINE cell the shadow's returned dict must equal the real provider's dict EXACTLY on
     all 24 frames** (same keys, coordinates within 1e-6, same confidences). **A single mismatch means
     the shadow is not the provider: the row STOPS and reports that, and no relaxation number is
     quoted.** The equality is asserted in the per-file test, not only in prose.
  4. **INSTRUMENT AND PUBLISH THE FUNNEL.** For each of the 24 frames record the survivor count after
     EVERY stage named in clause 2, as a committed 24-row CSV with one column per stage. **THE KILLING
     FILTER IS THE FIRST STAGE WHOSE SURVIVOR COUNT IS ZERO, and it is identified by that table, never
     by reading the source.** Report it as `file:line`, its constant, the number of frames it zeroes,
     and the survivor count entering it. **If two stages zero the same frames, both are named and the
     memo says the cause is not unique.**
  5. **THE RELAXATION GRID -- PREREGISTERED, ONE FILTER AT A TIME, NO TUNING ON THE OUTCOME.** Ten
     cells, each differing from R0 in EXACTLY ONE constant; no cell combines two relaxations and no
     eleventh cell may be added after a result is seen.
       R0  BASELINE, every constant as shipped (`min_edge_support` 0.16)
       R1  `min_edge_support` 0.16 -> 0.08
       R2  `min_edge_support` 0.16 -> 0.02
       R3  area floor `0.006 * w * h` -> `0.002 * w * h`
       R4  minimum side `0.15 * height` -> `0.05 * height`
       R5  `approxPolyDP` epsilon `0.025 * perimeter` -> `0.050 * perimeter`
       R6  vertex test `len(approx) == 4` -> `4 <= len(approx) <= 6`, reduced by `minAreaRect`
       R7  contour perimeter floor 120.0 -> 60.0
       R8  `_ordered_quad` convexity test dropped (its 400 px^2 area floor kept)
       R9  contour SOURCE: `Canny(GaussianBlur(gray))` -> the G304 painted-marking mask
           (`court_marking_mask`: HSV V > 170 AND S < 60, closed 3x3), everything else unchanged
     Every cell runs on ALL 24 frames. **No frame is dropped from any cell for any reason** -- a frame
     that yields nothing yields zero and stays in every denominator (B1).
  6. **MEASURE, PER CELL AND PER FRAME, and publish the whole 10 x 24 table, not a summary:**
     6a. `n_raw_keys` the provider's own key count, and `n_mapped_names` / `n_structures` after
         `SEMANTIC_MAP` -- **the structural quantities the E1 frame rule is written in.**
     6b. `n_named_landmarks` -- the count used by the clause-7 bar, defined as **DISTINCT mapped
         vocabulary names emitted on the frame**, spanning `n_structures` distinct marking structures.
     6c. `n_on_player` -- emitted points within **8.0 px** of one of the 113 adjudicated G296 points
         under a **one-to-one** assignment computed per frame (Hungarian on the euclidean cost matrix,
         radius 8.0 px, no re-use of a truth point). **Under P2 this is a DEFECT count, and the memo
         states that on the same line as the number.**
     6d. `n_false_proposals` -- emitted mapped proposals that are not confirmed by any committed
         ground truth. **No named-court-landmark truth exists on these frames**, so this equals the
         raw emission count; report it as such and say plainly that the absence of truth, not the
         provider's quality, is what leaves every emission unconfirmed.
  7. **VERDICT, in exactly these tokens, with the numbers on the same line:**
     **CAUSE NAMED** -- the clause-4 table identifies a stage that zeroes the funnel on **>= 20 of the
     24 frames**, reported as `file:line` plus its constant plus its per-frame survivor counts. Fewer
     than 20 is **CAUSE NOT UNIQUE** and the row reports the distribution instead of a cause.
     **PROVIDER REPAIRABLE** -- **some SINGLE cell R1-R9 reaches `n_named_landmarks >= 6` spanning
     `n_structures >= 3` on `>= 12 of the 24 frames`, with `n_false_proposals <= 12` on every one of
     those frames.** No combination of cells and no post-hoc constant may be used to reach it.
     **NOT REPAIRABLE** -- otherwise, and attempt 3 needs a different proposer or human annotation.
     **If P3 shows the map yields < 6 names or < 3 structures, PROVIDER REPAIRABLE is UNREACHABLE BY
     ARITHMETIC and the verdict is `NOT REPAIRABLE THROUGH THE G304 MAP` with the raw-emission table
     alongside it** -- that is a statement about `SEMANTIC_MAP`, a file in a SAFE area, and it does not
     refute the provider. **PROVIDER REPAIRABLE IS AN EMISSION RESULT, NEVER A CORRECTNESS ONE:** any
     memo carrying it also carries the P2 sentence and the words "no landmark recall is established".

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = (i) the 24-row stage-survivor funnel table with the killing filter named as
                  `file:line`; (ii) the 10 x 24 cell table carrying `n_raw_keys`, `n_mapped_names`,
                  `n_structures`, `n_named_landmarks`, `n_on_player`, `n_false_proposals`;
                  (iii) the R0 shadow-vs-provider exact-equality check on all 24 frames
  before        = **the semantic family emitted 0 proposals on 63 of 63 eligible frames in G304
                  attempt 2** (`g304_proposal_verify_build_2026-09-07.md`), with no cause recorded
                  beyond "consistent with the abstention G227 already measured"
  bar           = **CAUSE NAMED** requires a stage zeroing >= 20 of 24 frames, named `file:line` with
                  its constant. **PROVIDER REPAIRABLE** requires ONE cell of R1-R9 with
                  `n_named_landmarks >= 6` AND `n_structures >= 3` on **>= 12 of the 24 frames** AND
                  `n_false_proposals <= 12` on each of those frames. Anything else is **NOT
                  REPAIRABLE**. **A shortfall is a VALID result, not a failure of this row; no bar may
                  be lowered and none of these numbers may be restated by any consumer (Q3).**
  n             = **24 frames (CONSTRUCT -- every frame enumerated by the sealed G296 formula, none
                  sampled), 113 adjudicated points over 16 of those 24, 10 grid cells, 240 cell-frame
                  observations, 1 broadcast, 1 arena.** Name every denominator in the verdict line.
  eye check     = **<= 6 headless overlay JPEGs, <= 300 KB each, EVENLY SPACED over the 24 frames by
                  index (i = 0, 4, 9, 13, 18, 23), NEVER a head slice (A3/B7)**, each drawing the R0
                  emission and the best cell's emission on the same frame so a reader can see whether
                  the quad sits on the painted lane. Committed with the memo.
  must not move = `src/`, `domains/`, `kernel/` (READ and IMPORT ONLY -- **not one character, not one
                  comment, not one default argument**); `scripts/platformkit/tracking/
                  g304_proposals.py` and its `SEMANTIC_MAP`; the G304 prereg seals
                  (`78f1a4f2...41335`, `3d60dcda...2696`) and the G304 CLOSED AT LIMIT verdict; the
                  G296 ground-truth CSV, its merge prereg seal `dcfa4d4b...b5d5` and its 113/24
                  counts; the E1 packet manifest and its frame-good rule (p90 <= 12 px AND max <= 24
                  px); `scripts/platformkit/tracking_harness.py` and CONFIG_VERSIONS `2026-09-01-v1`;
                  every ledger `passed` field; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
                  (the orchestrator owns it); `data/` and `vault/` (never staged)
NON-TAUTOLOGY: every cell runs on ALL 24 frames and **no frame is excluded after the grid is sealed**
(B1). The killing filter is read off the survivor table, not chosen; a stage that zeroes nothing
cannot be named the cause however plausible it reads. `n_false_proposals` is reported as an emission
count with its missing denominator stated, never silently omitted to flatter a cell (B9).

**IF THE FIX LIVES IN `domains/` OR `src/` -- and clause 2 will most likely put it in
`domains/basketball/tracking/keypoints.py` -- THE DELIVERABLE IS A PROPOSED DIFF UNDER
`docs/research/organization-sprint/PROPOSED-g321-*.md` AND THE ROW STOPS. A human applies it.**
No feature flag is flipped ON. Nothing is deployed to the pod (B5).

EVIDENCE: `docs/evidence/tracking/g321_semantic_provider_abstention_2026-09-07.md`, **line 1 the
verdict** with every denominator, **<= 60 lines**, carrying: the source and per-frame decode SHA-256s,
the P1/P2/P3 premise results with the P2 sentence verbatim, the traced gate as `file:line`, the
survivor funnel, the 10-cell relaxation table, the shadow fidelity result, bytes added, time spent,
the artifact SHA-256s, and a **NOT VERIFIED list** carrying at minimum: that ONE broadcast and ONE
arena were measured, that the arena identity is TRANSCRIBED and not confirmed by eye, that the 113
points are player feet and therefore **no landmark recall is established for any provider**, that the
shadow is a re-implementation and not the shipped provider, and that this row measures NO
registration, NO calibration and NO tracking quality whatsoever.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO, APPENDED WITH A SINGLE `>>` -- never a
whole-file rewrite (17 rows across 9 gap ids were destroyed that way).** Commit BEFORE reporting (A7).
TEST: exactly one new per-file test, importing full package paths
(`scripts.platformkit.tracking.g321_semantic_gate`), run as a single file only -- **NEVER a full
pytest.** It must pin: the R0-shadow-equals-provider rule on a synthetic frame, the 10 named grid
cells with their constants, the 8.0 px one-to-one matching rule (including that a truth point is
never re-used), the >= 6-names-over->= 3-structures frame rule, the >= 12-of-24 and <= 12-false bars,
and the `SEMANTIC_MAP` name/structure counts from clause P3. **If a commit grows an allowlisted file,
raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (A12).**
COMMIT: explicit pathspec only; prereg ALONE first, then harness + artifacts + overlays + memo + test
+ ledger row. **Make EVERY commit before you finish.** ASCII stdout. **NEVER PARK.**

## VERSION 2026-09-07

First version. Written from the G304 attempt-2 closure
(`g304_proposal_verify_attempt2_2026-09-07.md`, `g304_proposal_verify_build_2026-09-07.md`), which
closed the E1 packet CLOSED AT LIMIT with 0 of 756 proposals jointly accepted and recorded, as its
own NEXT STEP, that "a working semantic-line proposer ... the gap this attempt actually exposed" is
the only remaining non-human route. The orchestrator verified before dispatch (S2): the G296 source
is LOCAL at the sha256 quoted above, so no pod work is required; the G296 ground-truth CSV carries
186 rows of which 113 are non-`dropped` over 16 of 24 frames and its schema is `player_ordinal`-keyed
foot positions, which is why P2 is a binding premise rather than an assumption; and `SEMANTIC_MAP`
carries six keys over five names and two structures, which is why P3 is measured before any image is
opened. **G304 stays CLOSED AT LIMIT and G306-G308 stay BLOCKED whatever this row returns.**
