GAP G298 | sport wnba | worktree a6 | log g298_detector_capacity_and_input_resolution
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only --
`src/tracking/player_detection.py` is HUMAN-GATED. You may IMPORT and RUN it; you may NOT edit it.**
Build in `scripts/platformkit/tracking/`. **Propose NO production change; this row measures an
alternative, it does not adopt one.**

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **ALL THREE DETECTION ARMS RUN ON THE POD** -- the source video, the GPU and the weights are there.
    Use **`~/bin/pod_run a6 --ship <harness> --fetch <per-arm detection CSVs and summaries> -- <cmd>`**.
  - **THE ARITHMETIC IS LOCAL**, on the CSVs fetched back.
  - **GATE: FREE VRAM, NOT A LANE COUNT.** Another row is using the GPU. **The card is 24,576 MiB and was
    346 MiB used at 2026-09-04 21:55, so there is ample headroom; a second YOLO process fits.** **Read
    `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader` yourself and PROCEED IF free
    VRAM exceeds what your run needs, which for yolov8x at imgsz 1920 batch 1 is a few GB.** **Do NOT hold
    for a free lane, do NOT interrupt a running row, and do NOT kill anything on the pod.** Report your
    reading. **This is an OPERATIONAL gate, not an evidentiary bar.**
  - **DISK GUARD:** `du -sm /workspace` is a MooseFS NETWORK walk -- **empty means UNKNOWN, NEVER 0, and
    NEVER stop on UNKNOWN.** **The only stopping condition is a FAILED `dd conv=fsync` probe on the pod.**
    `yolov8x.pt` is about 130 MB and ultralytics auto-downloads it; **write it into YOUR scratch under
    `/workspace/wt/a6`, NEVER into the deployed `/workspace/nba-ai-system` tree.** **Delete no corpus
    source and neither bridge partial download.** Report bytes you added and freed.

**READ FIRST:** the G285b memo and ledger row, the G284 memo, and the G273-VS-G285b-RECONCILED ledger row.
**Do NOT read any blind verdict file; this row has NO eye labels at all.**

**WHY THIS ROW EXISTS -- THE PROGRAMME HAS SPENT DAYS MEASURING THAT DETECTION IS BROKEN AND HAS NEVER
ASKED WHETHER THE CONFIGURATION IS THE REASON.**
Read from the human-gated source (do not edit it): `src/tracking/player_detection.py` sets
**`self._infer_imgsz = 640`** and calls the model with **`classes=[0], conf=0.3, imgsz=640`**, on a
**1920x1080** broadcast. **That is a 3x linear, 9x area downscale before detection.** The weight is
**`yolov8n`** -- the NANO variant, the smallest in the family -- and the source comment justifying it says
**"yolov8x is slower to load and only marginally better for tracking"**, **with no measurement cited
anywhere in the repo.**
Against that configuration the programme measured **locate-then-match recall of 3/143 = 0.021 at 25 px,
7/143 = 0.049 at 50 px and 17/143 = 0.119 at 100 px** (G285b). **A player 150 px tall at 1080p is 50 px
tall at 640.** **Small-object detection is exactly where a nano model at a 9x area downscale is expected to
fail, and nobody has checked.**

THE QUESTION: **how much of the measured detection failure is the CONFIGURATION rather than the task?**

METHOD:
  1. **RUN THREE ARMS ON EXACTLY THE SAME FRAMES -- the 15 frames carrying G285b's hand-located feet.**
     Take the frame list from
     `docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv`. **Report the frame
     list and confirm the count.**
     - **ARM A -- PRODUCTION AS-IS:** `yolov8n`, `imgsz=640`, `classes=[0]`, `conf=0.3`. **Import and run
       the gated `player_detection.py` path if you can do so without editing it; if you cannot, replicate
       those exact settings and SAY that you replicated rather than imported.**
     - **ARM B -- RESOLUTION ONLY:** `yolov8n`, `imgsz=1920`, same `classes` and `conf`.
     - **ARM C -- CAPACITY ON TOP:** `yolov8x`, `imgsz=1920`, same `classes` and `conf`.
     **The ONLY difference between A and B is input resolution; the only difference between B and C is
     model capacity. State that design and do not add a fourth difference.**
  2. **CONFIRM DETERMINISM before comparing anything.** Run ARM A twice and report whether the detections
     are byte-identical. **G241 found the research TRACKING route non-deterministic (808 of 1,201 records
     differed); single-frame detection is expected to be deterministic, but VERIFY it rather than assume,
     and if it is not, say so and treat every arm as one draw.**
  3. **THE MEASUREMENT HAS NO EYE LABELS: it is recall against G285b's committed located feet.** For each
     arm and each predeclared tolerance **25, 50 and 100 px**, report **how many of the 143 located feet
     have a detection footpoint within that distance**, with **143 named as the eligible denominator every
     time.** **Use the same footpoint convention as the production path (the bottom-centre of the box) and
     state it.**
  4. **THE COMPARISON IS PAIRED -- the same frames and the SAME located feet in every arm -- so use
     McNEMAR's exact test on the per-foot detected/not indicator between A and B, and between B and C.**
     **An unpaired two-proportion test would be WRONG here; say why.** Nominal p, said to be nominal, with
     **no multiplicity correction across the three tolerances -- say that too.**
  5. **ALSO REPORT, PER ARM: the total detection count, detections per frame, and the median distance from
     each located foot to the nearest detection.** **A recall gain bought by simply emitting far more
     boxes is not the same as a better detector: report the count so a reader can see which happened.**
  6. **ANSWER IN ONE SENTENCE WITH NUMBERS: how much of the 0.119 recall gap is input resolution, and how
     much is model capacity?** **A large ARM B gain means the production 640 downscale is the dominant
     defect and the fix is an inference setting. A large additional ARM C gain means model capacity
     matters too. LITTLE GAIN IN EITHER means the task is genuinely hard on this footage and the
     configuration is exonerated -- and that is the most important outcome to report honestly, because it
     would mean the programme's detection findings are about the PROBLEM and not about a careless setting.
     ALL THREE ARE FULL SUCCESSES.**
  7. **Do NOT edit `src/`, do NOT change any production default, do NOT propose a filter, threshold, gate
     or retrain, and do NOT move any bar.** **Do NOT delete or overwrite `yolov8n.pt` anywhere on the
     pod.** **State plainly that this row measures an alternative configuration and adopts nothing.**

**HONEST LIMITATIONS to state, not discover:** **The ground truth is 143 foot observations on 15 frames
from a SINGLE MODEL LOCATOR (G285b), not a human, and it is the same locator whose judgements the
programme's other rows rest on** -- so this row measures agreement with that locator, and **a detector
that finds players the locator missed will be scored as WRONG.** **Say that in those words**; it bounds
every recall figure here from above and below. **All 15 frames lie inside frames 19599-23399, and G278
measured that span friendlier than its own clip (0.836 against 0.656, p = 0.0078), so nothing here may be
quoted clip-wide.** ONE clip, ONE shot. **A bigger model at a higher input size is SLOWER, and this row
measures NO timing** -- so it cannot say the alternative is practical, only whether it detects more.
**Recall is not precision: a bigger model may also emit more false boxes, which is why step 5 is
mandatory.**

ACCEPTANCE RULE:
  metric        = the 15-frame list; the three arms' exact settings with the A-B and B-C single-difference
                  design stated; the ARM A determinism check; per-arm recall at 25/50/100 px against 143
                  located feet with the denominator named; McNemar exact paired tests A-vs-B and B-vs-C
                  with nominal p and the no-correction statement; per-arm detection counts, per-frame
                  counts and median nearest-detection distance; and the one-sentence attribution
  before        = production runs yolov8n at imgsz 640 on 1920x1080 -- a 9x area downscale on the smallest
                  model in the family, justified in a source comment by an unmeasured assertion -- and
                  locate-then-match recall against that configuration is 0.021 / 0.049 / 0.119
  bar           = **NO pass bar.** **A large ARM B gain puts the defect in an inference setting. A large
                  ARM C gain adds model capacity. LITTLE GAIN IN EITHER exonerates the configuration and
                  means the programme's detection findings are about the problem, which is the most
                  important outcome to state honestly. ALL are full successes.**
  n             = 15 frames, 143 located feet, 3 arms, 3 tolerances, 1 clip, 1 span, 1 shot, 1 locator --
                  name every denominator in the verdict line and name the single-model-locator ground truth
  eye check     = NONE. This row has no eye labels and no blind judging; it is arithmetic against a
                  committed coordinate set. **Say that rather than implying validation.**
  must not move = `src/` and `domains/` (READ and IMPORT ONLY, `player_detection.py` HUMAN-GATED);
                  production defaults; `yolov8n.pt` on the pod; the deployed `/workspace/nba-ai-system`
                  tree; G285b's located feet and counts; G284's counts; every threshold and verdict; the
                  corpus and both bridge partial downloads
EVIDENCE: `docs/evidence/tracking/g298_detector_capacity_and_input_resolution_2026-09-04.md` with the
frame list, per-arm settings, the determinism check, the recall table, the paired tests, the count table,
the one-sentence attribution, every GPU and disk probe verbatim, bytes added and freed, and a NOT VERIFIED
list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7). **Do
NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: a per-file test for the harness, pasted -- **pin the 143-foot denominator, the three tolerances, and
that the footpoint convention is the bottom-centre of the box.** **NEVER a full pytest.** **If a commit
grows an allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME
commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
