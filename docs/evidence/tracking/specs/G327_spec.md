GAP G327 | sport all | worktree a21 | log cx_g327_detector_batch_stability
**SCREENING ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only --
`src/tracking/player_detection.py` and `src/tracking/advanced_tracker.py` are HUMAN-GATED. You may
IMPORT and RUN them; you may NOT edit them. Build in `scripts/platformkit/tracking/`. This row
ISOLATES A CAUSE inside an existing call path; it ADOPTS NOTHING, moves no production default,
changes no input size, no confidence and no batch size anywhere in `src/`, and proposes no cutover.
If a fix is implied it is written as a PROPOSED diff and left for a human.**
CONTRACT: `docs/evidence/tracking/VERIFIER_CONTRACT.md` -- read it; self-check against every line of
section B before you report.
VERSION 2026-09-08.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP -- contract S1):**
  - **EVERY DETECTOR ARM RUNS ON THE POD.** The source video, the GPU, the deployed `yolov8n.pt` and
    the CUDA/ultralytics stack the daemon actually uses are all there, and a batch-stability question
    is a property of THAT stack, not of a laptop. Use
    `~/bin/pod_run a21 --ship <harness> --fetch <per-arm CSVs and summary> -- python -m ...`.
  - **THE ARITHMETIC, THE PREMISE RECOMPUTE AND THE MEMO ARE LOCAL**, on the fetched artifacts.
  - **GPU LEASE, SERIALIZED WITH THE RUNNING DAEMON.** `track_daemon` owns the card and **must never
    be stopped, signalled or interrupted.** Read
    `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader` and
    `--query-compute-apps=pid,used_memory --format=csv,noheader` YOURSELF, **report both verbatim,
    and PROCEED ONLY WHEN FREE VRAM IS >= 8192 MiB.** Below that, WAIT and re-probe. **This row stays
    under 4 GB. OPERATIONAL gate, not an evidentiary bar.**
  - **CPU IS THE SCARCE RESOURCE HERE, NOT VRAM.** The pod CPU quota is 27 cores and the daemon
    saturates it (`load average 28.59` at spec time). **The decode stays at 3 games x 40 frames and
    is never widened.** One decode per game feeds every arm.
  - **DISK GUARD:** `v=$(timeout 60 du -sm /workspace | cut -f1); [ -z "$v" ] && v=UNKNOWN` -- report
    verbatim; **empty means UNKNOWN, NEVER 0, and NEVER stop on UNKNOWN.** Stop only on a failed
    `dd conv=fsync` probe. Write into `/workspace/wt/a21` ONLY -- **never the deployed
    `/workspace/nba-ai-system` tree, never the daemon's site-packages, never `data/tracking/`, and
    never overwrite `yolov8n.pt`.**
  - **WALL BUDGET: 1,800 s PER GAME for all arms together.** A game that exceeds it is a BUDGET LIMIT
    for that game, reported as such; the row continues with the games that finished.

**WHY THIS ROW EXISTS.** G324's screening measured that the production `yolov8n` route returns
DIFFERENT boxes from a batch-8 pass than from a single-image pass over the same decoded frames, while
the Apache RTMDet arm's boxes were bit-identical on all three games. That is a property of the
detector call path, not of either model's quality, and **nothing in the program has ever isolated its
cause.** It matters because the daemon route is single-image: if the two paths disagree, then any
future batching of the production route silently changes what the tracker sees, and no existing row
would notice.

**PREMISE (step 0, RE-MEASURED BEFORE ANY RUN -- contract Q8/S2). THE PREMISE AS ORIGINALLY WRITTEN
IS PARTLY FALSIFIED AND THE SPEC CARRIES THE CORRECTED FORM:**
  - **G324's evidence is NOT ON MASTER.** Commit `6dc55b929` was REJECTED by the verifier
    (`docs/evidence/tracking/G324_VERIFY_2026-09-08.md`, `76772791f`, on the import gate's unlabeled
    version probe) and never landed. `docs/evidence/tracking/g324_artifact/` **does not exist on
    master**; it exists only on branch `track-a2` at `6dc55b929`. **State this in the memo. Do NOT
    land, copy or re-commit any G324 file under this row** -- that is G324's fix pass to land, and
    duplicating it here would collide with it.
  - **THE COMMITTED G324 CSVs CARRY THE SINGLE-IMAGE PASS ONLY.** All six raw box CSVs have header
    `frame_index,x1,y1,x2,y2,score,class` and, by `g324_arms.py:measure`, hold `run_single`'s rows;
    the batch-8 rows were computed, compared and DISCARDED. **So the per-frame count deltas and the
    single-vs-batch IoU-matched agreement CANNOT be recomputed from any committed artifact.** The
    premise is therefore CARRIED AS AN INHERITED SUMMARY, cited and labelled INHERITED, never
    recomputed and never presented as this row's measurement:
      `g324_summary.json`, ARM Y (production `yolov8n`), `batch_vs_single`:
        `wnba__wnba_01_1080p` identical_box_counts **true**, max_abs_coord_delta_px **310.5**
        `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p` identical_box_counts **true**,
          max_abs_coord_delta_px **861.0**
        `wnba__wnba_06` identical_box_counts **false**, max_abs_coord_delta_px **null**
      ARM R (RTMDet): identical_box_counts **true** and max_abs_coord_delta_px **0.0** on all three.
    **That comparison is per-index and unmatched** (`g324_arms.py:batch_vs_single` subtracts the two
    box arrays in emission order), so a pure reordering and a genuinely different detection are
    indistinguishable in it. **This row exists to replace that summary with a matched measurement,
    and MUST say that the inherited figure could not be reproduced from artifacts because the batch
    rows were never written.**
  - **WHAT THIS ROW DOES NOT DO.** RTMDet is NOT re-run: it is out of scope, its stack is not
    installed in this worktree, and its role in the premise is only to show the effect is not
    universal. **Say that rather than implying an RTMDet control ran here.**
  - **THE PRODUCTION CALL PATH IS ALREADY RECORDED AND IS INHERITED, NOT RE-DERIVED** (G303,
    landed `b27d89028`, `g303_artifact/g303_report.json:step0`): the route feeds the detector a
    `uint8` array of shape `[1020, 1920, 3]` -- a `TOPCUT = 60` crop region of the native 1080p frame,
    NOT the full frame -- with `classes=[0]`, `verbose=False`, `imgsz=640`, `half=True`, `device=0`,
    and ultralytics preprocesses that into a `[1, 3, 352, 640]` `torch.float16` tensor. The route's
    own `_fill_conf_threshold` is **0.22** where the register carries 0.3; `_infer_imgsz = 640`.
    **This row runs at the route's OWN 0.22, because the question is what the daemon route does, and
    it states that choice and its conflict with the registered 0.3 in the verdict line.** G303 also
    recorded `arm_P_byte_identical_repeat = true` on a single-image repeat, which step 4 re-measures
    rather than assumes (contract B11).

METHOD:
  1. **PREMISE, LOCAL, BEFORE ANY POD WORK.** Print the four facts above with their commit shas and
     file:line citations, and print the six inherited `batch_vs_single` values verbatim from
     `g324_summary.json` read out of `git show 6dc55b929:...`. **Print the exact reason the
     coordinate-level recompute is impossible** (batch rows never written) rather than reporting a
     number you did not compute. **A falsified premise is a VALID result (contract Q8); this one is
     partly falsified and the row continues, because the CONSTRUCT below generates the missing data
     itself.**
  2. **CONSTRUCT -- 3 games x 40 frames x every arm, one decode.**
     **THE THREE GAMES AND THEIR FRAME LISTS ARE INHERITED FROM G324 VERBATIM** (readable-anchor
     rule: the last index is the MEASURED last decodable index found by binary search on the real
     cv2 seek path, never ffprobe's `nb_frames`), sealed in the prereg with the SHA-256 of each
     comma-joined list:
       `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01_1080p.mp4`, 308,078,882 B,
         1920x1080, anchor 18000, list sha256
         `686426bf125bead05e0139c781bb0447917ed7f109ec4d2f7902b86be636d862`
       `.../ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4`, 328,260,234 B, 1920x1080,
         anchor 17982, list sha256
         `0302a5e3e691ef63831173d06db87804635511bb929e048ccd0fcdf9dddd0036`
       `.../wnba__wnba_06.mp4`, 430,058,965 B, 1920x1080, anchor 28673, list sha256
         `937eea3183390b25fdbb10cded43e0888d3b90bf0ae5f7826d6d9b0d19fcd024`
     **Print full pod path, BYTE SIZE, width, height, fps and duration per source at run time and
     compare them with these sealed values (contract A9); a mismatch is FATAL, never adjusted.**
     **The decode happens ONCE per game and every arm sees byte-identical decoded frames** -- assert
     that by hashing the decoded array stack once and reusing it. A failed read is FATAL, never
     dropped. **Every frame goes through the PRODUCTION call path exactly as the daemon route uses
     it**: import the human-gated detector class unedited, apply `TOPCUT`, and call it with the
     inherited kwargs above at the route's own `imgsz`, `half` and confidence. **If you cannot import
     it, replicate those exact settings and SAY you replicated.**
     **RECORD PER FRAME PER ARM:** box count; every box as `x1,y1,x2,y2,score,class`; **the
     letterboxed input tensor shape and dtype ACTUALLY FED**, captured by wrapping the ultralytics
     predictor `preprocess` (reuse G303's `Capture` proxy by import -- it is landed on master at
     `scripts/platformkit/tracking/g303_recall_vs_resolution.py`; **do NOT import `g324_arms.py`,
     which is not on master**); and **the NMS input order**, recorded as the emission order of the
     boxes together with their scores, so a verifier can see whether a reorder alone explains a delta.
  3. **ISOLATION ARMS, ONE FACTOR AT A TIME, ALL PREREGISTERED BEFORE ANY RUN.** Baseline arms are
     `single`, `batch-2`, `batch-8` at the route's own settings. The isolation arms each change
     EXACTLY ONE thing from the batch-8 baseline and are run on the same frames:
       **ARM PAD** -- the batch is padded to the SAME letterboxed shape the single-image pass used
         (`[1, 3, 352, 640]`), so a per-batch dynamic shape cannot vary.
       **ARM FP32** -- `half=False`, everything else unchanged.
       **ARM NMSORD** -- the returned boxes are sorted by `(score DESC, x1, y1, x2, y2)` on BOTH the
         single and the batch side before comparison, which removes emission order as an explanation
         without touching the model.
     **Each arm reports whether batch-8 becomes bit-identical to the single-image pass, per frame.**
     **ARM NMSORD is a COMPARISON-SIDE arm, not a model change: if it alone restores identity, the
     cause is ORDERING and the boxes were never different.** Say that in those words.
  4. **RUN-TO-RUN DETERMINISM OF THE DAEMON ROUTE.** The single-image pass is run TWICE on the same
     decoded frames in the same process. **Bit-identical on 120/120 frames means the daemon route is
     DETERMINISTIC on this construct; anything less means it is NOT, and the count is reported as
     `<k>/120` either way.** G303 saw a byte-identical repeat and this step re-measures it rather
     than citing it (contract B11).
  5. **AGREEMENT ARITHMETIC, LOCAL.** For every arm pair (single vs each of batch-2, batch-8 and each
     isolation arm) report, **per frame and summed with its denominator**: the box COUNT DELTA, and
     the **IoU >= 0.5 one-to-one matched agreement share in BOTH directions**, greedy by descending
     IoU, stated as greedy. **A zero-box frame stays in the denominator and is NEVER dropped**; state
     the zero-box frame count per arm. Report **bit-identity separately from IoU agreement**: two box
     sets can match at IoU >= 0.5 in both directions and still not be bit-identical, and the verdict
     below turns on bit-identity, not on agreement.
  6. **VERDICT RULE, SEALED BEFORE ANY NUMBER.**
       **CAUSE PINNED** iff EXACTLY ONE isolation arm restores bit-identity with the single-image pass
         on **>= 110 of 120 frames** (3 games x 40) while the batch-8 baseline does not, and that arm
         is NAMED. Two arms clearing the bar is **NOT PINNED (CONFOUNDED)** and is reported as such.
       **NOT PINNED** otherwise, including when no arm clears the bar. **NOT PINNED is a VALID
         RESULT and a full success of this row** -- it says the cause is not among the three factors
         preregistered, which is information.
       **DETERMINISTIC** iff the repeated single-image pass is bit-identical on **120/120** frames;
         otherwise NOT DETERMINISTIC with its `<k>/120`.
     **No bar here is ever moved (contract Q3).** 110/120 and 120/120 are sealed in the prereg.
  7. **LABEL THE WHOLE ROW SCREENING. THERE IS NO GROUND TRUTH HERE.** This row cannot say which pass
     is CORRECT -- only whether they AGREE. A pinned cause is a mechanism, not a defect ranking, and
     **no claim about detection quality, recall, precision, registration or accuracy may be made.**
     Say that in those words.
  8. **THE PRODUCTION ROUTE MUST BE UNTOUCHED:** report **SHA-256 of `src/tracking/player_detection.py`,
     `src/tracking/advanced_tracker.py` and the pod `yolov8n.pt` BEFORE and AFTER**, and show they are
     identical.

**HONEST LIMITATIONS to state, not discover:** ONE corpus, three clips, 120 frames, one GPU, one
driver, one ultralytics version, one seed. **Three factors are preregistered and they are not the
only three possible** -- cuDNN kernel selection by batch shape, reduced-precision reduction order and
non-deterministic CUDA reductions are all unexamined here, so NOT PINNED means "not among these
three", never "no cause exists". The card is shared with a running daemon, so a determinism result is
measured under contention and a NEGATIVE determinism result could reflect that contention.
Bit-identity is a strict criterion: a sub-pixel float difference fails it while changing no detection.

ACCEPTANCE RULE:
  metric        = the premise block (four inherited facts with shas and file:line, the six inherited
                  `batch_vs_single` values, and the stated reason the coordinate recompute is
                  impossible); per game per arm: box count, zero-box frame count, bit-identity vs
                  single, box count delta vs single, both-way IoU >= 0.5 one-to-one agreement shares,
                  the letterboxed tensor shape and dtype actually fed, and the emission order --
                  each with its decoded-frame denominator; the repeat-single bit-identity count out of
                  120; the isolation table; the SCREENING statement; the source byte sizes and the pod
                  harness route SHA-256s; the committed raw box CSVs for EVERY arm
  before        = G324 measured, on a per-index unmatched comparison whose batch rows were never
                  written and whose commit was REJECTED and is not on master, that the production
                  `yolov8n` route's batch-8 boxes differ from its single-image boxes (one game
                  changed its box count; per-index deltas of 310.5 px and 861.0 px on the other two)
                  while RTMDet's were bit-identical at 0.0 px. No cause has ever been isolated, no
                  matched comparison exists, and the daemon route's run-to-run repeatability has been
                  observed once (G303) and never re-measured
  bar           = **VERDICT BARS ONLY: CAUSE PINNED needs exactly one isolation arm at >= 110/120;
                  DETERMINISTIC needs 120/120. Neither bar is ever moved.** **There is NO pass bar on
                  any agreement share or count delta. NOT PINNED is a FULL SUCCESS. NOT DETERMINISTIC
                  is a FULL SUCCESS.** The only failure is an unmeasured or unlabelled number.
  n             = 3 games x 40 decoded frames = 120 frames; x {single, single-repeat, batch-2,
                  batch-8, PAD, FP32, NMSORD} = 840 arm-frames; 1 corpus, 1 GPU, 1 seed -- name every
                  denominator in the verdict line
  eye check     = NONE. No renders and no eye labels; this row is arithmetic over box coordinates and
                  tensor shapes. **Say that rather than implying validation.**
  must not move = `src/`, `domains/`, `api/`, `kernel/`, `intel/` (READ/IMPORT ONLY;
                  `player_detection.py` and `advanced_tracker.py` HUMAN-GATED and SHA-256-pinned
                  before/after); production defaults; `data/registry/`; the pod `yolov8n.pt`; the
                  deployed `/workspace/nba-ai-system` tree; the daemon's site-packages;
                  `data/tracking/`; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`; the three
                  games, their 40-frame lists and their anchors; IoU 0.5; batch sizes 2 and 8; the
                  route's own `imgsz` 640, `half` and 0.22; the 110/120 and 120/120 bars
NON-TAUTOLOGY: every decoded frame in the declared list is in every denominator, **including frames
where the detector emits zero boxes** -- a zero-box frame counts and is NOT dropped, and two zero-box
frames ARE bit-identical and count as such. State the zero-box frame count per arm. The isolation arms
are scored against the SAME single-image reference, not against each other. **Bit-identity is computed
from the committed coordinates, so a verifier can recompute every cell of the isolation table from the
CSVs alone.**
EVIDENCE: `docs/evidence/tracking/g327_detector_batch_stability_2026-09-08.md` (<= 60 lines) -- **the
memo MUST live at exactly this path** -- with **line 1 the VERDICT (CAUSE PINNED or NOT PINNED, plus
DETERMINISTIC yes/no, each with its 120-frame denominator)**, the premise block, the per-arm agreement
and bit-identity table, the captured tensor shape/dtype per arm, the SCREENING statement, every GPU
and disk probe verbatim, the pod log tail, the before/after SHA-256 pairs, source byte sizes, pod
harness route SHA-256s, artifact SHA-256s, elapsed time, and a NOT VERIFIED list. **Copy the summary
JSON and the raw box CSVs for EVERY arm under `docs/evidence/tracking/g327_artifact/` for durability.**
**If a fix is implied, write it as a PROPOSED diff at `docs/evidence/tracking/PROPOSED_g327_<name>.md`
and declare that as a deviation from the contract's `docs/research/` location, which is gitignored and
therefore cannot carry a durable proposal. Apply nothing.**
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO (one append only, `>>`, never a rewrite
of any historical row).**
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: exactly one new per-file test on the batching / comparison / raw-row code this row adds, over
SYNTHETIC boxes and a synthetic detector -- pin that chunking covers every frame with a short last
chunk, that bit-identity is TRUE for an identical pair and FALSE for a one-ulp difference, that a
REORDERED box set is reported NOT bit-identical by the baseline comparison and bit-identical by the
NMSORD arm, that both-way IoU >= 0.5 one-to-one agreement is asymmetric when the counts differ, and
that a zero-box frame stays in the denominator and counts as bit-identical against another zero-box
frame. **The test must pass ON MASTER after landing.** Run only that file with
`--confcutdir=tests/platformkit`. **NEVER a full pytest.**
COMMIT: explicit pathspec, in the worktree. **Sealed PREREG committed ALONE before any run or
measurement** (frame anchors and their hashes, the arms, the IoU rule, the 110/120 and 120/120 bars,
the repeat rule, and the exact inherited call path), then harness + tests, then artifacts + memo +
PROPOSED + ledger row. No forced git operation of any kind. **Commit BEFORE reporting (A7).**
ASCII stdout. Vocabulary follows contract Q6; automated scan required.
**NEVER PARK:** poll your own pod job in a blocking loop; never end waiting.

---
**ATTEMPT 2 -- VERSION 2026-09-08b (orchestrator amendment after the attempt-1 REJECT, verify memo
`G327_VERIFY_2026-09-08.md`, candidate 668b9929b).** The rule above names immutable G324 games/lists/anchors
(:192-197). Those sources no longer exist on the pod: the corpus is a rotating queue (the volume guard prunes
ledgered sources; 119 -> 85 files in 40 min on 2026-09-08) and two freshly sealed clips were deleted before
their own run. A prereg therefore cannot seal filenames. Binding for attempt 2, on top of the rule above:
  1. **SOURCE RULE + SNAPSHOT.** The prereg seals (a) the measured absence of every G324 source on the pod
     (`ls`/`find` output committed as a raw artifact, not a summary), (b) the selection rule, (c) the
     realised clips, and (d) the per-frame SHA-256 of the 120 decoded frames (3 games x 40) BEFORE the
     scored run. The scored run reads ONLY those snapshotted frames (never the corpus), so the realised
     sample is fixed for the rest of the row. This is a declared widening of :192-197 authorised by the
     orchestrator; attempt 1's rule-based pick was itself pre-registered, so it is not outcome-contaminated.
  2. **RAW CSV FOR EVERY ARM, CSV-ONLY RECONSTRUCTION.** Each of the 7 arms writes its own raw CSV at run
     time, including `nmsord` as its own emitted rows (not derived post hoc from `batch8`), and EVERY
     evaluated frame appears in every arm's CSV -- a frame with zero boxes is written as an explicit row
     (`n_boxes=000000`, empty box fields). Bit-identity and agreement are recomputed from the CSVs alone;
     no value may come from `g327_summary.json`.
  3. **PER-GAME / PER-ARM TABLE** of agreement and bit-identity (:206-211) in the memo, plus the verbatim
     process and disk probe output the rule requires (an artifact file if it does not fit the 60 lines,
     named in the memo with its sha256).
  4. **CORRECTIONS carried:** "bit-exact" -> "coordinate-exact" wherever full bit-identity (incl. score and
     class) is not what was measured; the 181 / 139 / 282 count; the memo must not cite a path absent from
     the candidate tree (cite G324's verify memo by commit and path on the branch that holds it).
  5. All 7 arms, 120 frames, the >= 110/120 bar, and the DETERMINISTIC 120/120 single-repeat check stay
     byte-identical. New prereg `g327_prereg_2026-09-08d.md` sealed alone (embedded `SEAL sha256 <hex>` last
     line). Memo `g327_detector_batch_stability_attempt2_2026-09-08.md` (<= 60 lines), one ledger `>>` row.
     Attempt-1 memo, preregs and verify memo are frozen.
