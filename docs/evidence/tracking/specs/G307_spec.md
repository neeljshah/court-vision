GAP G307 | sport wnba | worktree a8 | log g307_native_pixel_semantic_lines | BLOCKED-ON G304
**BLOCKED-ON G304: DO NOT START UNTIL THE SEALED E1 PACKET HAS LANDED ON MASTER AND ITS MANIFEST
SHA256 IS READABLE.** If G304 reported a shortfall or INSTRUMENT NOT VALIDATED, this row does not run:
say so and stop. **Quote the G304 manifest SHA256 in your memo.**
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check against every line of
section B before you report.
**ROUTE 2 OF 3, ATTEMPT 1. SCRATCH MEASUREMENT ONLY. `src/`, `domains/` and `kernel/` are READ and
IMPORT only.** Build in `scripts/platformkit/tracking/` (**additive only; <= 300 LOC per file**).
**PROPOSE NO PRODUCTION CHANGE AND NO PRODUCTION WIRING. A registration result never translates into
the ledger passed field.**
SOURCE: `docs/research/astra_tracking_registration_2026-09-07.md` Route 2 and G-ASTRA-REG-2, applied as
written. Every number below is quoted from it and may NOT be moved.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **TRAINING AND INFERENCE RUN ON THE POD.** Ship and run with `~/bin/pod_run a8 --ship <paths>
    --fetch <per-frame CSVs, probabilities summary, H matrices, line residuals, renders> -- <cmd>`.
    **THE SCORING ARITHMETIC IS LOCAL.** **ANNOTATION STAGING IS LOCAL** (see PREMISE part 3).
  - **GATE ON THE RESOURCE, NOT A LANE COUNT.** Read `nvidia-smi --query-compute-apps=pid,used_memory
    --format=csv,noheader` yourself. **THE GPU LEASE IS SERIALIZED: G306, G307 and G308 may NOT hold it
    concurrently.** Never interrupt a running row; never kill anything on the pod.
  - **3,600-SECOND WALL STOP**, isolated scratch under `/workspace/wt/a8`, never the deployed
    `/workspace/nba-ai-system` tree. **Record peak VRAM, peak RSS and actual scratch bytes.** **RTX
    3090, 24 GB VRAM; the host's 1 TB RAM does not enlarge GPU memory or establish a disk quota.**
    **Avoid whole-volume walks:** `v=$(timeout 60 du -sm /workspace | cut -f1); [ -z "$v" ] &&
    v=UNKNOWN` -- report v verbatim, **NEVER stop on UNKNOWN**; stop only on a failed `dd conv=fsync`
    probe. **Delete no corpus source and no bridge partial download.**

**PREMISE (step 0) -- BINDING BEFORE-CONDITION, all four parts, ALL BEFORE ANY GPU USE. Any failure =>
PREMISE FALSE, write the memo, commit, stop. That is a valid result and earns its own register row.**
  1. **Reproduce G217's controls exactly: the 17/17 zero-error algebra control AND the 1/17
     detected-line control** (`g217_oracle_error_decomposition_2026-09-04.md`). The oracle-selected
     detected groups miss their intended labelled paint lines by **median 10.2347919059155 px** across
     all **68** role-frame selections, and the detected-line branch sits at **28.841315992648475 px**
     median maximum corner error. **Reproduce, do not re-derive from prose.**
  2. **LICENCE PIN, BINDING:** **Apache-2.0 MMDetection RTMDet backbone**
     (https://github.com/open-mmlab/mmdetection) **plus a project-owned dense head**. **Use an
     EXPLICITLY APPROVED backbone checkpoint, or train from scratch and LABEL that weaker
     initialization. Do NOT infer checkpoint rights from the code licence.** No TVCalib, Sportlight or
     KaliCalib (all BLOCKED). **A source, label or licence mismatch => PREMISE FALSE before GPU use.**
  3. **STAGE THE 80/20 ANNOTATION PACKET -- ITS STAGING IS PART OF THIS PREMISE, NOT A LATER STEP.**
     **80 independently annotated training frames and 20 development frames, from broadcasts SEPARATE
     from E1.** **NO E1 arena or frame, NO G140 test label, and NO pseudo-label derived from a rejected
     or invalid H may enter training.** Prove the disjointness by source SHA256 and frame index, not by
     filename. Staging is **LOCAL**; only the staged tensors go to the pod.
  4. **Everything is staged BEFORE the pod hour** -- frames, reviewed annotations, licensed
     checkpoints, runnable code and dependencies. **Missing prerequisites produce PREMISE FALSE without
     claiming that the model failed.** Say that sentence.

**CHANGE (step 1) -- the native semantic head plus its paired resolution ablation. Nothing else.**
  - Train **a small dense head for NAMED visible painted boundaries, sidelines and arcs**, which must
    **distinguish painted strokes from logos, bodies and overlays**. **Keep 768x768 tiles at NATIVE
    scale, with a SEPARATE low-resolution full-frame context branch for role identity; merge
    probabilities in ORIGINAL pixel coordinates.**
  - **Fit centreline geometry to SUPPORTED SEMANTIC PIXELS; do NOT snap to untyped Canny responses.**
    **FREEZE G210's solver and the league dimensions for the four-line arm.** **This row changes the
    EVIDENCE feeding the fitter -- it is not another top-hat, grouping threshold or role-search retry,
    and the benefit from native pixels REMAINS A HYPOTHESIS until this measures it.**
  - **TWO PAIRED ARMS, IDENTICAL architecture, optimizer, sample order and seed.**
    **ARM A downsamples the full scene to 640-wide BEFORE crop construction. ARM B retains native
    detail with a MATCHED field of view. That is the ONLY difference; do not add a third.**
  - **Choose the LAST SCHEDULED CHECKPOINT, never the best E1 epoch.** **Score both arms on E0 AND
    E1.** **E0 = all 17 G140 frames / 68 targets at native sizes; report its 12 native-1080p frames
    SEPARATELY without dropping the other five. E0 is repeatedly inspected development/regression
    material -- a success on it is FEASIBILITY EVIDENCE ONLY, never a held-out success.**
  - **Log role-specific line residuals AS WELL AS actual named-map errors** -- they are different
    claims. **Persist probabilities, lines, H, uncertainty and abstentions.** **Retain raw projected
    coordinates and every rejection reason; grade BEFORE any bounds-based deletion.**
  - **COMPUTE BUDGET, inside the 3,600 s wall:** single 3090, **AMP, batch <= 2**; **each of the two
    arms <= 300 optimizer updates and <= 20 min**; 5 min control, 10 min evaluation, 5 min archive.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-frame named held-out reprojection error against the **fixed six correspondences**
                  of the sealed G304 packet, per arm; the accepted/abstained decision on all 60 rows,
                  per arm; and the **median named-line error** per arena, per arm
  before        = G217's controls: real detected-line search **1/17**, algebra control **17/17**,
                  selected lines missing labelled endpoints by median **10.2347919059155 px** over
                  **68** role-frame selections. **No native semantic head has ever been measured on
                  basketball; the memo states it has no measured basketball performance.**
  bar           = **ALL THREE, or REJECT:**
                  (i) **ARM B passes the shared E1 rule** -- **frame-good = correct shot/end
                  orientation, finite H, and named held-out error p90 <= 12 px AND max <= 24 px in
                  original 1920x1080 pixels** on the fixed six correspondences (never nearest arbitrary
                  edges, candidate-chosen points, fitted corners or a censored window); **>= 16/20
                  frame-good in EACH arena**; **<= 1/10 accepted negatives in EACH arena**; **no
                  accepted wrong-end map and ZERO false acceptances among the 40 eligible frames**;
                  **abstentions on eligible frames COUNT AS FAILURES**;
                  (ii) **B exceeds A's good-frame count by >= 4/40**;
                  (iii) **B reduces median named-line error by >= 25% in EACH arena.**
                  **SPLIT VERDICT, MANDATORY: if B passes the geometry (i) WITHOUT the paired gains
                  (ii) and (iii), then native semantic fitting is FEASIBLE but the proposed RESOLUTION
                  MECHANISM IS FALSIFIED -- report BOTH conclusions separately.** **If training exceeds
                  the fixed budget, record BUDGET LIMIT: an undertrained negative does NOT disprove
                  semantic detection in general.**
  n             = 60 sealed rows (40 eligible + 20 negatives) x 2 arms across 2 arenas, plus E0's 17
                  frames / 68 targets (12 native-1080p reported separately). **Name every denominator.**
                  These are **small-sample screening bars, not population guarantees**; report **all
                  per-frame errors and counts** and **make no significance claim from correlated
                  pixels**
  eye check     = **renders of all 40 eligible frames for ARM B** with the fitted lines and projected
                  court overlaid, plus all 20 negatives, plus **>= 8 EVENLY SPACED paired A-vs-B
                  comparison renders** -- no head slice. Look explicitly for paint-vs-logo confusion
  must not move = the sealed G304 packet and its manifest SHA256; the frame-good rule and every bar
                  above; **G210's solver and the league dimensions**; the G140 labels and E0;
                  `scripts/platformkit/tracking_harness.py` and CONFIG_VERSIONS `2026-09-01-v1`;
                  `src/`, `domains/`, `kernel/` (READ and IMPORT ONLY); every existing threshold and
                  verdict; the deployed `/workspace/nba-ai-system` tree; the corpus and every bridge
                  partial download; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  **FREEZE:** code, checkpoint and config are frozen BEFORE E1. **No test-time label access, no
  threshold sweep, no oracle selection, and no post-result frame substitution.**
NON-TAUTOLOGY: the metric covers all 40 eligible and all 20 negative frames in both arms and excludes
none. **Every missing role is retained AS A FAILURE, never dropped from the denominator.** If excluding
the failing frames is what makes the number good, say so and report REJECT yourself.

ATTEMPT 2 (the memo's limit measurement, on a **DIFFERENT sealed packet, labels disjoint**): **replace
the predictions with INDEPENDENTLY TRACED visible semantic masks, keeping the line fitting and the
scorer FIXED.** **If the mask-oracle maps fail E1, this parameterization and visibility regime is
insufficient. If they pass while the learned maps fail, close this training recipe at its measured
data/compute limit.** Attempt 2 may not become another tuning cycle.

REUSE (do not rebuild these): **G115** painted-line annotations for development, **G140/E0** for
regression, **G217** decomposition, **G210** solver, **G229** abstention taxonomy. **No pseudo-label
from a rejected H.** **G31 already failed learned tennis calibration; this route earns a test only by
changing SUPERVISION to verified semantic pixels and preserving detail, NOT by adding capacity --
state that.**
EXPECTED FAILURE MODES to report if seen, not to discover: tile context cannot distinguish paint from
decoration, full-line labels inherit identity errors, or the network memorizes training-court
appearance.

EVIDENCE: `docs/evidence/tracking/g307_native_pixel_semantic_lines_2026-09-07.md` with the G304
manifest SHA256, the G217 control reproduction, the 80/20 disjointness proof by SHA256 and frame index,
the exact licence pin for every weight and dependency, the paired A/B table on E0 and E1 with
**uncensored** per-frame errors, the role-specific line residuals reported separately from the named-map
errors, every GPU and disk probe verbatim, peak VRAM/RSS, scratch bytes added and freed, wall time, and
a **NOT VERIFIED list** that at minimum carries: that E0 success is feasibility evidence only, that no
whole-broadcast yield was measured, that no player or ball correctness was measured, and that nothing
here bears on unseen arenas.
**REQUIRED EVIDENCE DURABILITY:** the summary JSON, all 60 rows per arm, every H matrix and every
per-frame error go under `docs/evidence/`; renders may stay local, the numbers may not.
**RE-EMITTED TABLES: preserve the FULL column set**, including `frame_width` and `frame_height`.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: exactly one new per-file test, **importing full package paths** (`scripts.platformkit.
tracking....`), run as a single file only -- **NEVER a full pytest.** It must pin: the crop-inverse and
coordinate round-trip; a **known line-noise recovery**; a **holdout-loader denial** (any attempt to read
an E1 frame or a G140 test label during training must raise); that **every missing role is retained as
a failure**; and **wrong-role and missing-frame negative controls**. **If a commit grows an allowlisted
file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
POD: heavy compute only; own nohup setsid nice job, unique /tmp log, never kill anything, no git on the
pod, **no scp of any module until the verifier accepts** -- report the files you would deploy.
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK:** poll your own pod jobs in a blocking loop; never end waiting.
