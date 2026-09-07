GAP G308 | sport wnba | worktree a9 | log g308_court_rtmpose_landmarks | BLOCKED-ON G304
**BLOCKED-ON G304: DO NOT START UNTIL THE SEALED E1 PACKET HAS LANDED ON MASTER AND ITS MANIFEST
SHA256 IS READABLE.** If G304 reported a shortfall or INSTRUMENT NOT VALIDATED, this row does not run:
say so and stop. **Quote the G304 manifest SHA256 in your memo.**
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check against every line of
section B before you report.
**ROUTE 3 OF 3, ATTEMPT 1. SCRATCH MEASUREMENT ONLY. `src/`, `domains/` and `kernel/` are READ and
IMPORT only.** Build in `scripts/platformkit/tracking/` (**additive only; <= 300 LOC per file**).
**PROPOSE NO PRODUCTION CHANGE AND NO PRODUCTION WIRING. A registration result never translates into
the ledger passed field.**
SOURCE: `docs/research/astra_tracking_registration_2026-09-07.md` Route 3 and G-ASTRA-REG-3, applied as
written. Every number below is quoted from it and may NOT be moved.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **TRAINING AND INFERENCE RUN ON THE POD.** Ship and run with `~/bin/pod_run a9 --ship <paths>
    --fetch <per-frame landmark CSVs, confidences, H matrices, summaries, renders> -- <cmd>`.
    **THE SCORING ARITHMETIC IS LOCAL.** **SYNTHETIC RENDERING AND ANNOTATION STAGING ARE LOCAL.**
  - **GATE ON THE RESOURCE, NOT A LANE COUNT.** Read `nvidia-smi --query-compute-apps=pid,used_memory
    --format=csv,noheader` yourself. **THE GPU LEASE IS SERIALIZED: G306, G307 and G308 may NOT hold it
    concurrently.** Never interrupt a running row; never kill anything on the pod.
  - **3,600-SECOND WALL STOP**, isolated scratch under `/workspace/wt/a9`, never the deployed
    `/workspace/nba-ai-system` tree. **Record peak VRAM, peak RSS and actual scratch bytes.** **RTX
    3090, 24 GB VRAM; the host's 1 TB RAM does not enlarge GPU memory or establish a disk quota.**
    **Avoid whole-volume walks:** `v=$(timeout 60 du -sm /workspace | cut -f1); [ -z "$v" ] &&
    v=UNKNOWN` -- report v verbatim, **NEVER stop on UNKNOWN**; stop only on a failed `dd conv=fsync`
    probe. **Delete no corpus source and no bridge partial download.**

**PREMISE (step 0) -- BINDING BEFORE-CONDITION, all five parts, ALL BEFORE ANY GPU USE. Any failure =>
PREMISE FALSE, write the memo, commit, stop. That is a valid result and earns its own register row.**
  1. **Stage the approved backbone and a CUSTOM COURT-ROLE SCHEMA.** **A stock person-pose checkpoint
     does NOT predict court landmarks.** **Transfer ONLY an approved backbone; train the court head and
     the visibility outputs explicitly.**
  2. **Stage 2,000 PROJECT-OWNED procedural synthetic examples**, excluding textures from the E1
     arenas. Rendered at **1080p** court markings under **sampled nonsingular homographies**, with
     **line-width, blur and compression variation and occluding shapes**.
  3. **Use the SAME real 80/20 training/development split as G307**, and **E1 UNTOUCHED**. Prove
     disjointness by source SHA256 and frame index, not by filename.
  4. **DOCUMENT HOW THE SUPERVISION DIFFERS FROM G31.** **G31's near-zero training loss with a zero
     solve proxy warns directly against tiny-set memorization
     (`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md:352`); synthetic success cannot override
     it.** **Visible-role identity and label uncertainty must pass the annotation contract; a stock
     human-joint head or synthetic-only validation does NOT satisfy this premise.**
  5. **LICENCE PIN, BINDING:** **Apache-2.0 MMPose**
     (https://github.com/open-mmlab/mmpose/blob/main/LICENSE) with the
     [custom dataset interface](https://mmpose.readthedocs.io/en/latest/advanced_guides/customize_datasets.html).
     **Synthetic assets and labels MUST be project-owned. Exact pretrained-weight permission is a
     BINDING PREREQUISITE -- an Apache/MIT project notice alone does not settle off-repository
     checkpoint or broadcast-data rights.** **No blocked calibration model or checkpoint: TVCalib,
     Sportlight and KaliCalib remain BLOCKED.** **Missing prerequisites produce PREMISE FALSE without
     claiming that the model failed.** Say that sentence.

**CHANGE (step 1) -- court-role and visibility outputs under a bounded schedule. Nothing else.**
  - **Replace human-joint semantics with NAMED COURT INTERSECTIONS AND ARC LANDMARKS plus visibility
    confidence**, using the custom dataset and output head.
  - **Train synthetic-then-real.** **This needs NO supplied camera intrinsics: estimate an eight-DOF
    planar H.** **Synthetic rendering supplies TRAINING LABELS, never a substitute for real held-out
    validation.**
  - **Use full-scene context plus native crops; PERSIST every crop and resize inverse.**
  - **Require >= 4 spatially independent, CORRECTLY NAMED visible correspondences.** **REFUSE an
    ill-conditioned solve and REPORT its rejection: confidence alone can establish neither rank nor the
    difference between the two symmetric court ends.**
  - **Output ONE named prediction per role -- never an unrestricted proposal cloud.** (G205 scored
    nearest generic proposals, not named correspondence correctness; this row must not repeat that.)
  - **BEFORE E1, PIN the last checkpoint and the confidence threshold from DEVELOPMENT data only.**
  - **Retain raw projected coordinates and every rejection reason; grade BEFORE any bounds-based
    deletion.**
  - **COMPUTE BUDGET, inside the 3,600 s wall:** **AMP, batch <= 2**; 5 min control, **15 min synthetic
    warmup (<= 300 updates)**, **25 min real adaptation (<= 300 updates)**, 10 min evaluation, 5 min
    archive.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-frame named held-out reprojection error against the **fixed six correspondences**
                  of the sealed G304 packet; the accepted/abstained decision on all 60 rows; and the
                  **share of correct role identities among visible predicted landmarks on E1**,
                  measured with **one-to-one named correspondences**
  before        = **no court-landmark pose model has ever been measured on this footage.** The memo
                  states RTMPose court transfer has **no measured basketball performance**, and G298
                  measured neither it nor its permissive replacement. The nearest in-repo facts: the
                  semantic quad provider abstains **17/17** (**0/68** corners, best joint margin
                  **0.534**), M-LSD at 512x512 repeats **0/17**, and G210b's real search is **0/17**
  bar           = **BOTH, or REJECT:**
                  (i) **the shared E1 rule** -- **frame-good = correct shot/end orientation, finite H,
                  and named held-out error p90 <= 12 px AND max <= 24 px in original 1920x1080 pixels**
                  on the fixed six correspondences (never nearest arbitrary edges, candidate-chosen
                  points, fitted corners or a censored window); **>= 16/20 frame-good in EACH arena**;
                  **<= 1/10 accepted negatives in EACH arena**; **no accepted wrong-end map and ZERO
                  false acceptances among the 40 eligible frames**; **abstentions on eligible frames
                  COUNT AS FAILURES**;
                  (ii) **>= 90% correct role identities among visible predicted landmarks on E1**, by
                  one-to-one named correspondence.
                  **With the LAST SCHEDULED CHECKPOINT and NO E1 tuning. An incomplete schedule =>
                  BUDGET LIMIT.** **A synthetic-holdout success with an E1 failure is a DOMAIN-TRANSFER
                  REJECT, not progress toward a registered broadcast -- report it in those words.**
                  **Report localization CONDITIONAL ON CORRECT IDENTITY separately**, so a good number
                  on the frames it named correctly is never read as a registration result
  n             = 60 sealed rows (40 eligible + 20 negatives) across 2 arenas, 240 held-out
                  correspondences, 2,000 synthetic examples, 80 real training + 20 development frames.
                  **Name every denominator.** These are **small-sample screening bars, not population
                  guarantees**; report **all per-frame errors and counts** and **make no significance
                  claim from correlated pixels**
  eye check     = **renders of all 40 eligible frames** with the named predicted landmarks and the
                  projected court overlaid, plus all 20 negatives, plus **>= 8 EVENLY SPACED synthetic
                  validation renders** -- no head slice. Look explicitly for **hallucinated hidden
                  corners and symmetric role swaps**
  must not move = the sealed G304 packet and its manifest SHA256; the frame-good rule and every bar
                  above; the G307 80/20 split; **G196's league geometry** and **G140's role contract**;
                  `scripts/platformkit/tracking_harness.py` and CONFIG_VERSIONS `2026-09-01-v1`;
                  `src/`, `domains/`, `kernel/` (READ and IMPORT ONLY); every existing threshold and
                  verdict; the deployed `/workspace/nba-ai-system` tree; the corpus and every bridge
                  partial download; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  **FREEZE:** code, checkpoint and config are frozen BEFORE E1. **No test-time label access, no
  threshold sweep, no oracle selection, and no post-result frame substitution.**
NON-TAUTOLOGY: the metric covers all 40 eligible and all 20 negative frames and excludes none. **A role
the network declines to predict is a FAILURE on that frame, not an omission** -- the identity share is
reported over visible predicted landmarks AND the visible-landmark count itself is published, so a 90%
share earned by predicting almost nothing is visible to the reader. If excluding the failing frames is
what makes the number good, say so and report REJECT yourself.

ATTEMPT 2 (the memo's limit measurement, on a **DIFFERENT sealed packet**): **substitute INDEPENDENTLY
VERIFIED native keypoints for the network outputs, retaining the visibility policy, the solver and the
independent scoring.** **This distinguishes label-set OBSERVABILITY from learned LOCALIZATION. If the
oracle fails, the landmark set and conditioning are the limit; if it passes, close this learned recipe
at its data/compute limit.** **No third optimizer sweep.**

REUSE (do not rebuild these): **G196** league geometry, **G140** role contract, **G233d's verified
seed**, **G296b** extraction and visibility conventions -- **G296b's player coordinates are NOT court
training labels.**
EXPECTED FAILURE MODES to report if seen, not to discover: the synthetic-to-real appearance gap,
hallucinated hidden corners, symmetric role swaps, and localization noise amplified by clustered
landmarks.

EVIDENCE: `docs/evidence/tracking/g308_court_rtmpose_landmarks_2026-09-07.md` with the G304 manifest
SHA256, the exact licence pin for every weight, asset and dependency, the G31 supervision-difference
statement, the synthetic-vs-real split proof by SHA256 and frame index, the pinned checkpoint and
confidence threshold with the development data that set them, the full 60-row decision table with
**uncensored** per-frame errors, the one-to-one role-identity table with the visible-landmark count,
localization conditional on correct identity reported separately, every rejected ill-conditioned solve
with its reason, every GPU and disk probe verbatim, peak VRAM/RSS, scratch bytes added and freed, wall
time, and a **NOT VERIFIED list** that at minimum carries: that synthetic holdout performance is not
evidence of broadcast registration, that no whole-broadcast yield was measured, that no player or ball
correctness was measured, and that nothing here bears on unseen arenas or long-horizon identity.
**REQUIRED EVIDENCE DURABILITY:** the summary JSON, all 60 rows, every H matrix, every landmark
prediction with its confidence and every per-frame error go under `docs/evidence/`; renders may stay
local, the numbers may not.
**RE-EMITTED TABLES: preserve the FULL column set**, including `frame_width` and `frame_height`.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: exactly one new per-file test, **importing full package paths** (`scripts.platformkit.
tracking....`), run as a single file only -- **NEVER a full pytest.** It must pin: a **synthetic H
ground-truth** recovery; **degenerate/collinear landmarks MUST ABSTAIN**; a **reflected court end MUST
FAIL**; crop-inverse accuracy; a **hidden-role hallucination check** (an occluded landmark must not be
emitted as visible); and **one-to-one correspondence** enforcement (no role predicted twice). **If a
commit grows an allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the
SAME commit (contract A12).**
POD: heavy compute only; own nohup setsid nice job, unique /tmp log, never kill anything, no git on the
pod, **no scp of any module until the verifier accepts** -- report the files you would deploy.
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK:** poll your own pod jobs in a blocking loop; never end waiting.
