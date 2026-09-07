GAP G306 | sport wnba | worktree a11 | log g306_seeded_shot_end_atlas | BLOCKED-ON G304
**BLOCKED-ON G304: DO NOT START UNTIL THE SEALED E1 PACKET HAS LANDED ON MASTER AND ITS MANIFEST
SHA256 IS READABLE.** If G304 reported a shortfall or INSTRUMENT NOT VALIDATED, this row does not run:
say so and stop. **Quote the G304 manifest SHA256 in your memo.**
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check against every line of
section B before you report.
**ROUTE 1 OF 3, ATTEMPT 1. SCRATCH MEASUREMENT ONLY. `src/`, `domains/` and `kernel/` are READ and
IMPORT only.** Build in `scripts/platformkit/tracking/` (**additive only; <= 300 LOC per file**).
**PROPOSE NO PRODUCTION CHANGE AND NO PRODUCTION WIRING. A registration result never translates into
the ledger passed field.**
SOURCE: `docs/research/astra_tracking_registration_2026-09-07.md` Route 1 and G-ASTRA-REG-1, applied as
written. Every number below is quoted from it and may NOT be moved.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **THE MATCHING RUNS ON THE POD** -- the full-resolution frames and the GPU are there. Ship and run
    with `~/bin/pod_run a11 --ship <paths> --fetch <per-frame CSVs, H matrices, summaries, renders> --
    <cmd>`. **THE SCORING ARITHMETIC IS LOCAL**, on the fetched artifacts.
  - **GATE ON THE RESOURCE, NOT A LANE COUNT.** Read `nvidia-smi --query-compute-apps=pid,used_memory
    --format=csv,noheader` yourself and proceed if free VRAM exceeds what your run needs.
    **THE GPU LEASE IS SERIALIZED: one route at a time. G306, G307 and G308 may NOT hold it
    concurrently.** Never interrupt a running row; never kill anything on the pod.
  - **3,600-SECOND WALL STOP ON EVERY POD RUN**, isolated scratch under `/workspace/wt/a11`, never the
    deployed `/workspace/nba-ai-system` tree. **Record peak VRAM, peak RSS and actual scratch bytes.**
    The card is an **RTX 3090, 24 GB VRAM**; **the host's 1 TB RAM does not enlarge GPU memory and does
    not establish a disk quota.** **Avoid whole-volume walks:** `v=$(timeout 60 du -sm /workspace |
    cut -f1); [ -z "$v" ] && v=UNKNOWN` -- report v verbatim, **NEVER stop on UNKNOWN**; stop only on a
    failed `dd conv=fsync` probe. **Delete no corpus source and no bridge partial download.**

**PREMISE (step 0) -- BINDING BEFORE-CONDITION, all four parts. Any failure => PREMISE FALSE, write the
memo, commit, stop. That is a valid result and earns its own register row.**
  1. **Reproduce G233d's native seed identity AND its independent geometry.** The seed is at **source
     frame 19599** (G233d; G236b carries the source identity). Reproduction means the same frame, the
     same native bytes and the same geometry -- not a similar frame.
  2. **Verify the two E1 videos exist as the declared ORIGINAL 1080p bytes. An `_1080p` filename, a
     derivative or a historical frame index is INSUFFICIENT.** Re-check the SHA256s sealed by G304
     against the files you actually decode. **Any mismatch => PREMISE FALSE, stop.**
  3. **Stage at most two earlier seeds per broadcast (one per court end), EXCLUDED FROM E1**, plus the
     **sealed manual shot/end intervals**. Record annotation time, seed count and the permitted camera
     intervals. **No reseeding after any score is seen.**
  4. **Everything is staged BEFORE the pod hour** -- frames, reviewed annotations, licensed
     checkpoints, runnable code and dependencies. **Missing prerequisites produce PREMISE FALSE without
     claiming that the model failed.** Say that sentence.
  **LICENCE PIN:** existing project code plus **Apache-2.0 OpenCV**; **TransNetV2 is optional and MIT**
  (https://github.com/soCzech/TransNetV2/blob/master/LICENSE). **Only already-approved checkpoint bytes
  may run. No TVCalib, no Sportlight, no KaliCalib (all BLOCKED), and no historical Ultralytics
  dependency is introduced.** Pin the exact code, weight and dependency licences for THIS run; an
  Apache/MIT project notice alone does not settle off-repository checkpoint or broadcast-data rights.

**CHANGE (step 1) -- a scratch direct-to-seed atlas. The smallest thing that answers the question.**
  - **Compose `H(image -> court) = H(seed -> court) * H(image -> seed)`. Preserve the matrix and its
    direction EXPLICITLY in every emitted row.** Match each frame **directly to a seed; never chain H
    indefinitely.** **Reject loss of overlap instead of extrapolating.**
  - **Shot/end eligibility is a DISCLOSED MANUAL INPUT for this route.** Declare it as such.
    **TransNetV2 may supply cut candidates and reset state, but it does NOT decide live/replay, court
    visibility, court end, or absolute calibration validity.** **Because the interval labels are
    disclosed inputs, their rejection of negatives is NOT automatic view-classifier evidence** --
    test registration independently on the eligible frames and say this in the memo.
  - **Within each permitted shot, seed selection uses IMAGE FEATURES ONLY, locked before any
    withheld-landmark scoring. Never select the seed with the smallest test error.**
  - **Retain raw H, raw projected coordinates, every rejection and its reason. Grade BEFORE any
    bounds-based deletion** -- clipping or filtering to the court bounds makes an OOB success circular.
  - **No generic panorama** (its cached reference imagery comes from another venue), **no chained map,
    no production wiring, no adoption of anything.**
  - **COMPUTE BUDGET, inside the 3,600 s wall:** 5 min identity/control, **35 min direct matching on
    <= 1,200 staged frames**, 15 min scoring/renders, 5 min archive. **No calibration training.**

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-frame named held-out reprojection error against the **fixed six correspondences**
                  of the sealed G304 packet, plus the accepted/abstained decision on all 60 rows, plus
                  the two cut tests, plus the seed ledger
  before        = **no route has ever produced a named held-out registration result on E1, because E1
                  did not exist.** The nearest in-repo facts: G210b real search is **0/17** and its
                  label-assisted oracle **1/17**; selected lines miss their labelled endpoints by
                  median **10.235 px**, max **59.693 px**; M-LSD at 512x512 repeats **0/17** on the pod;
                  the semantic quad provider abstains **17/17** with best joint margin **0.534**
  bar           = **ALL of the following, or REJECT:**
                  (i) **frame-good = correct shot/end orientation, finite H, and named held-out
                  reprojection error p90 <= 12 px AND max <= 24 px in original 1920x1080 pixels**,
                  computed on the fixed six correspondences -- never nearest arbitrary edges,
                  candidate-chosen points, fitted corners, or a censored search window;
                  (ii) **>= 16/20 frame-good in EACH arena**;
                  (iii) **<= 1/10 accepted negatives in EACH arena**;
                  (iv) **NO accepted wrong-end map, and ZERO false acceptances among the 40 eligible
                  frames** (an accepted map that fails geometry IS a false acceptance);
                  (v) **abstentions on eligible frames COUNT AS FAILURES**;
                  (vi) **<= 4 seeds total**, every one excluded from E1, with no reseeding;
                  (vii) **BOTH cut tests pass**: on **100 consecutive frames straddling each of two
                  frozen shot cuts**, **no projected court output after a cut into an ineligible
                  interval**;
                  (viii) **every eligible-frame map was computed from an EARLIER seed in its declared
                  setup**;
                  (ix) all of it **inside 3,600 s**.
                  **Otherwise reject, or name the resource/instrument limit.**
  n             = 60 sealed rows (40 eligible + 20 negatives) across 2 arenas + 200 cut-test frames
                  (2 x 100) + <= 4 seeds. **Name every denominator in the verdict line.** These are
                  **small-sample screening bars, not population guarantees**; report **all per-frame
                  errors and counts** and **make no significance claim from correlated pixels**
  eye check     = **renders of all 40 eligible frames** with the projected court overlaid, plus all 20
                  negatives, plus **>= 8 frames EVENLY SPACED across each 100-frame cut span** -- no
                  head slice. A wrong-end map is visible to the eye; look for it explicitly
  must not move = the sealed G304 packet and its manifest SHA256; the frame-good rule and every bar
                  above; `scripts/platformkit/tracking_harness.py` and CONFIG_VERSIONS
                  `2026-09-01-v1`; `src/`, `domains/`, `kernel/` (READ and IMPORT ONLY); every existing
                  threshold and verdict; the deployed `/workspace/nba-ai-system` tree; the corpus and
                  every bridge partial download; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  **FREEZE:** code, checkpoint and config are frozen BEFORE E1. **No test-time label access, no
  threshold sweep, no oracle selection, no seed correction, and no post-result frame substitution.**
NON-TAUTOLOGY: the metric covers all 40 eligible and all 20 negative frames and excludes none.
**Manual atlas validity does NOT validate automatic shot/end eligibility, and a pass here is an
honestly scoped registered segment, not full-game automatic registration -- those remain separate
problems. Say both.**

ATTEMPT 2 (the memo's limit measurement, on a **DIFFERENT sealed packet**): **independently verify ONE
seed per eligible shot, holding matching and scoring FIXED**, and measure the achievable geometric
yield and the labels required per shot. **If even that oracle seed budget fails E1, this propagation
route is CLOSED AT LIMIT for this scope. If it passes, the limit is annotation and reacquisition COST
-- it does NOT mean automatic calibration is solved.** Attempt 2 may not become another tuning cycle.

REUSE (do not rebuild these): **G233d's seed at source frame 19599**, **G236b** source identity,
**G222** direct matcher, **G241b** shot horizon, **G242/G244** negative renders, **G253/G255**
independent markings.
EXPECTED FAILURE MODES to report if seen, not to discover: insufficient seed-view overlap, off-plane
features, wrong-end symmetry, an unseen zoom or camera setup, and seeds that are only approximately
accurate at native scale.

EVIDENCE: `docs/evidence/tracking/g306_seeded_shot_end_atlas_2026-09-07.md` with the G304 manifest
SHA256, the G233d reproduction, the seed ledger (which seed served which frame, and that it preceded
it), the full 60-row decision table with **uncensored** per-frame errors, both cut-test tables, every
GPU and disk probe verbatim, peak VRAM/RSS, scratch bytes added and freed, wall time, and a
**NOT VERIFIED list** that at minimum carries: that the manual interval labels are disclosed inputs and
therefore not view-classifier evidence, that whole-broadcast yield was not measured, that no player or
ball correctness was measured, and that nothing here bears on unseen arenas or long-horizon identity.
**REQUIRED EVIDENCE DURABILITY:** the summary JSON, all 60 sampled rows, every H matrix and every
per-frame error go under `docs/evidence/`; renders may stay local, the numbers may not.
**RE-EMITTED TABLES: preserve the FULL column set**, including `frame_width` and `frame_height`.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: exactly one new per-file test, **importing full package paths** (`scripts.platformkit.
tracking....`), run as a single file only -- **NEVER a full pytest.** It must pin: a synthetic
H-direction/axis check; **a wrong-end reflection MUST FAIL**; same-shot independent landmarks must
pass; an ineligible-cut span emits **abstention rows**; and empty frames **preserve attempts** rather
than vanishing from the denominator. **If a commit grows an allowlisted file, raise its entry in
`tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
POD: heavy compute only; own nohup setsid nice job, unique /tmp log, never kill anything, no git on the
pod, **no scp of any module until the verifier accepts** -- report the files you would deploy.
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK:** poll your own pod jobs in a blocking loop; never end waiting.
