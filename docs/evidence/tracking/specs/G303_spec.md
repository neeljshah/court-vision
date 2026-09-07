GAP G303 | sport wnba | worktree a12 | log g303_production_resolution_recall | BLOCKED-ON G296a
**BLOCKED-ON G296a: DO NOT START UNTIL PASS A HAS LANDED ON MASTER AND
`scripts/platformkit/tracking/g296_merge_locators.py` STOPS PRINTING `WAITING`.** If it still prints
`WAITING`, STOP IMMEDIATELY and report `BLOCKED-ON G296a` -- do NOT substitute pass B alone, do NOT build
your own locations, and do NOT proceed on G285b's older set.
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only --
`src/tracking/player_detection.py` is HUMAN-GATED. You may IMPORT and RUN it; you may NOT edit it.**
Build in `scripts/platformkit/tracking/`. **Propose NO production change; this row measures the route as
it actually runs, it does not adopt an alternative.**
CONTRACT: `docs/evidence/tracking/VERIFIER_CONTRACT.md` -- read it; self-check against every line of
section B before you report.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **BOTH DETECTION ARMS RUN ON THE POD** -- the GPU and the weights are there. Use
    **`~/bin/pod_run a12 --ship <harness> --fetch <per-arm detection CSVs and summaries> -- <cmd>`**.
    **The 24 G296 frames are COMMITTED ARTIFACTS, so ship them; do NOT re-extract them and do NOT open the
    source video.**
  - **THE ARITHMETIC IS LOCAL**, on the CSVs fetched back.
  - **GATE: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader` EMPTY, or free VRAM
    above what your run needs.** Report your reading verbatim. **Do NOT gate on a lane count, do NOT hold
    for a free lane, do NOT interrupt a running row, and do NOT kill anything on the pod.** OPERATIONAL
    gate, not an evidentiary bar. **If the pod is still being bootstrapped, or `resources/` is absent, or
    `opencv-python-headless` is version 5, STOP and report BLOCKED.**
  - **DISK GUARD:** `v=$(timeout 60 du -sm /workspace | cut -f1); [ -z "$v" ] && v=UNKNOWN` -- report v
    verbatim; **empty means UNKNOWN, NEVER 0, and NEVER stop on UNKNOWN.** The only stopping condition is
    a FAILED `dd conv=fsync` probe. **Delete no corpus source and neither bridge partial download.**

**READ FIRST:** `g298_detector_capacity_and_input_resolution_2026-09-04.md` (landed `ace539619`), the
G296a and G296b memos, and `scripts/platformkit/tracking/g296_merge_locators.py`.

**WHY THIS ROW EXISTS -- NOTHING YET ACTS ON THE MOST ACTIONABLE RESULT THE PROGRAMME HAS.**
G298 measured that **input resolution, not model capacity, is the dominant detector defect**: production
runs `yolov8n` at `imgsz=640` on 1920x1080, a 9x area downscale. But G298 measured it on **15 frames from
G285b's SINGLE-LOCATOR set, all inside frames 19599-23399** -- a span G278 measured to be friendlier than
its own clip (0.836 against 0.656 court-bearing, p = 0.0078). **So the most actionable number in the
programme rests on one rater and one unrepresentative span, and G298's own memo says so.** G296 exists
precisely to remove both limits: **24 clip-wide frames located independently by TWO passes with a measured
agreement figure.** Nobody has re-measured the resolution effect against it.

**AND THERE IS A SECOND, UNMEASURED THING: NOBODY HAS CHECKED WHAT THE PRODUCTION ROUTE ACTUALLY FEEDS THE
MODEL.** `self._infer_imgsz = 640` is what the SOURCE says. Whether the frame reaching the model is
1920x1080 letterboxed to 640, already resized upstream, or something else, is an assumption nobody has
instrumented. **G194 found basketball projecting through a degenerate static matrix because a fallback
branch nobody had traced was the live one; do not repeat that by trusting a constant.**

THE QUESTION: **at the production route's ACTUAL input resolution, what is recall on a clip-wide,
two-pass-agreed ground-truth set -- and how much does 1920 buy there?**

METHOD:
  1. **STEP 0, PREMISE, BINDING: MEASURE the input the production route actually hands the detector.**
     Import the gated `player_detection.py` path unchanged and instrument it from OUTSIDE (a wrapper, a
     hook or a monkeypatch in YOUR harness -- **never an edit to `src/`**) to record the shape and dtype
     of the tensor or array the model is called with, on **at least 3 of the 24 G296 frames**. **Report
     the measured shape verbatim.** **If the measured input is NOT the 640 the source constant implies,
     SAY SO PLAINLY, use the MEASURED value as ARM P for the rest of the row, and note that G298's ARM A
     described a setting rather than the route.** **If you cannot instrument it without editing `src/`,
     STOP and report PREMISE UNMEASURABLE -- do not guess and do not edit.**
  2. **BUILD THE GROUND-TRUTH SET FROM BOTH PASSES.** Run `g296_merge_locators.py`; report the Jaccard
     agreement, the median and p90 pass-A-to-pass-B offset, and the consensus count. **The PRIMARY
     denominator is the CONSENSUS set** (points both passes located, within the merge script's own
     tolerance). **Also report, as SECONDARY denominators, pass-A-only and pass-B-only located players.**
     **Report all three every time you report a recall figure; never quote one alone.**
  3. **TWO ARMS ON EXACTLY THE 24 COMMITTED G296 FRAMES.**
     - **ARM P -- PRODUCTION AS MEASURED IN STEP 0:** `yolov8n`, the measured input size, `classes=[0]`,
       `conf=0.3`.
     - **ARM R -- RESOLUTION ONLY:** `yolov8n`, `imgsz=1920`, same `classes` and `conf`.
     **The ONLY difference between P and R is input resolution. State that and do not add a second
     difference.** **CONFIRM DETERMINISM: run ARM P twice and report whether the detections are
     byte-identical; if not, say so and treat each arm as ONE draw.**
  4. **RECALL, at the predeclared tolerances 25, 50 and 100 px**: for each arm and each tolerance, how
     many consensus located feet have a detection footpoint within that distance, **with the consensus
     count named as the denominator every time.** **Use the production footpoint convention -- the
     bottom-centre of the box -- and state it.**
  5. **THE COMPARISON IS PAIRED** -- the same frames and the same located feet in both arms -- **so use
     McNEMAR's exact test on the per-foot detected/not indicator between P and R. An unpaired
     two-proportion test would be WRONG here; say why.** Nominal p, said to be nominal, **no multiplicity
     correction across the three tolerances -- say that too.**
  6. **ALSO REPORT PER ARM: total detection count, detections per frame, and the median distance from each
     consensus located foot to the nearest detection.** **A recall gain bought by emitting far more boxes
     is not a better detector; report the counts so a reader can see which happened.**
  7. **REPORT THE SPAN CONTRAST EXPLICITLY:** G298's 15 frames were all inside 19599-23399; these 24 are
     clip-wide. **State whether the resolution effect measured here is LARGER, SMALLER or
     INDISTINGUISHABLE from G298's, and say plainly that this is a comparison across two different frame
     sets, two different locator sets and two different tolerance denominators -- it is NOT a replication
     and must not be called one.**
  8. **Do NOT edit `src/`, do NOT change any production default, do NOT propose a filter, threshold, gate,
     retrain or an `imgsz` change, and do NOT move any bar.** **Do NOT delete or overwrite `yolov8n.pt`
     anywhere on the pod.** **State plainly that this row measures the route and an alternative input
     size, and adopts neither.**

**HONEST LIMITATIONS to state, not discover:** **The ground truth is TWO MODEL LOCATORS, not a human. Two
model locators agreeing measures REPRODUCIBILITY, never CORRECTNESS, and both can be wrong in the same
way. Say that in those words.** **G296b rated only 26/163 = 0.160 of its own player locations `confident`;
any recall figure computed against this set inherits an approximately 0.83-approximate positional basis
and must say so.** **A detector that finds players the locators missed is scored as WRONG here** -- that
bounds every recall figure from above and below. **ONE clip, ONE shot per frame, one draw per arm; 24
frames is clip-wide but thin.** **This row measures NO timing, so it cannot say a larger input size is
practical -- only whether it detects more.** **Recall is not precision.**

ACCEPTANCE RULE:
  metric        = the measured production input shape from step 0, verbatim; the merge output (Jaccard
                  agreement, median and p90 offset, consensus count, pass-A-only and pass-B-only counts);
                  the two arms' exact settings with the single-difference design stated; the ARM P
                  determinism check; per-arm recall at 25/50/100 px against the CONSENSUS denominator with
                  that denominator named, plus both secondary denominators; the McNemar exact paired test
                  P-vs-R with nominal p and the no-correction statement; per-arm detection counts,
                  per-frame counts and median nearest-detection distance; and the LARGER / SMALLER /
                  INDISTINGUISHABLE statement against G298 with its not-a-replication caveat
  before        = G298 (ace539619) measured input resolution to be the dominant detector defect, but on
                  15 frames from a SINGLE-locator set entirely inside frames 19599-23399, a span G278
                  measured friendlier than its own clip (0.836 vs 0.656, p = 0.0078); and the production
                  route's ACTUAL detector input has never been instrumented -- `imgsz=640` is a source
                  constant, not a measurement
  bar           = **NO pass bar.** **A large ARM R gain on the clip-wide consensus set STRENGTHENS G298's
                  attribution; a small or absent gain WEAKENS it and means G298's headline was
                  span-specific -- which is the more important outcome to report honestly. A step-0
                  finding that the route does not feed 640 at all is a FULL SUCCESS on its own and may be
                  reported even if the arms cannot then be run.**
  n             = 24 frames; the consensus located-foot count as the primary denominator with pass-A-only
                  and pass-B-only as secondaries; 2 arms; 3 tolerances; 1 clip; 1 draw per arm; 2 MODEL
                  locators -- name every denominator in the verdict line and state that the ground truth
                  is two MODEL locators, not a human
  eye check     = 6 EVENLY SPACED frames of the 24 (no head slice) rendered with the consensus located
                  feet and both arms' detections overlaid, committed with the memo
  must not move = `src/` and `domains/` (READ and IMPORT ONLY, `player_detection.py` HUMAN-GATED);
                  production defaults and `_infer_imgsz`; `yolov8n.pt` on the pod; the deployed
                  `/workspace/nba-ai-system` tree; G296a's and G296b's committed locations, counts and
                  confidence labels; G298's counts and verdict; G285b's located feet; every threshold and
                  verdict; the corpus and both bridge partial downloads
EVIDENCE: `docs/evidence/tracking/g303_production_resolution_recall_2026-09-07.md` with the step-0
instrumentation output verbatim, the merge output, per-arm settings, the determinism check, the recall
table with all three denominators, the paired tests, the count table, the span-contrast statement, every
GPU and disk probe verbatim, bytes added and freed, and a **NOT VERIFIED** list naming at minimum: no
human ground truth, the 0.160-confident basis, one clip, and that recall is not precision.
**REQUIRED EVIDENCE DURABILITY:** commit under `docs/evidence/` the per-arm detection CSVs, the consensus
set actually used, and the summary JSON -- everything a verifier needs to recompute every number without
the pod.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO, by APPENDING one line -- NEVER rewrite that
file.** Commit BEFORE reporting (A7). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: a per-file test for the harness, pasted -- **pin the 24 frame indices against `round(i * 174429 /
23)` for i = 0..23, pin the three tolerances, pin that the footpoint convention is the bottom-centre of
the box, and pin that the primary denominator is the CONSENSUS count.** **NEVER a full pytest.** **If a
commit grows an allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the
SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
