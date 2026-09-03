GAP G203 | sport wnba | worktree a3 | log g203_decode_determinism_bisect
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ, IMPORT and wrap IN YOUR
OWN MEASUREMENT PROCESS only. Deploy nothing into the pod checkout (B5).

**S1 MACHINE: RUN ON THE POD.** RTX 3090. **Run your jobs SERIALLY and launch nothing else on the pod
while this runs** -- this row is about byte identity and a loaded machine is a confound.

**S3 DEPENDENCY. This is the last standing candidate; four have been eliminated.**
  - **G190**: `cudnn.benchmark = False` makes the DETECTOR bit-exact. Torch seeds add nothing.
  - **G193**: tuner-off is not sufficient for the whole route.
  - **G195**: seeding all six OpenCV RNG sites is not sufficient (arm D: 1,118 / 1,108 / 1,072 rows).
  - **G198**: bypassing the YOLO prefetch cache entirely is not sufficient either -- 0 cache-served,
    400 self-inferred, still not identical across 3 runs.
  - **Orchestrator, this session:** 24 `perf_counter`/`time.time` calls exist across
    `unified_pipeline.py` and `advanced_tracker.py` and **NONE feeds a branch**, so
    wall-clock-dependent control flow is eliminated by inspection.

THE QUESTION: **does the route see the same pixels twice?** If decode is not byte-reproducible then
everything downstream inherits it and no amount of seeding can help. If decode IS byte-identical, the
cause is in stateful logic given identical inputs, which is a completely different search.

WHY IT IS PLAUSIBLE, stated as a hypothesis to falsify rather than confirm:
  - `unified_pipeline.py:144` sets `_BATCH_DECODE = 32` frames per NVDEC batch.
  - `_decord_frame_iter` carries **three** silent `except Exception` handlers (`:188`, `:199`,
    `:214`) and `_decode_loop` carries a fourth (`:283`) which **pushes the EOF sentinel regardless**,
    so a decode failure is indistinguishable from a clean end of video (G201).
  - A silent intermittent fallback between the decord GPU path and the PyAV/cv2 CPU path would give
    different pixels for the same frame index with no error anywhere.
  **"Decode is byte-identical" is a FULL SUCCESS** and eliminates the last enumerated candidate.

METHOD -- two parts, both n=3, fresh process per run:

  PART 1, DECODE IN ISOLATION: iterate the SAME frame range through the route's own decode path
  (`_decord_frame_iter`, imported, never reimplemented) three times in three fresh processes. Record
  the **SHA-256 of every decoded frame's raw bytes**, the frame index it was delivered under, and
  which decoder served it. **Instrument the four silent handlers named above so you can say whether
  any FIRED** -- wrap them from your own process; do not edit `src/`.
  Report: are the per-frame hash SEQUENCES identical across the three runs, yes or no; did any silent
  handler fire; did the decoder path ever change mid-run.

  PART 2, DECODE AS THE ROUTE CONSUMES IT: run the bounded route three times with a wrapper that
  hashes each frame at the point the tracking loop receives it. Same recording. This catches a
  divergence that only appears under real ordering and load.

  **If Part 1 and Part 2 disagree, that disagreement IS the result** -- report it, do not reconcile it.

Report per run: frames hashed, the count whose hash differs from run 1, **the FIRST differing frame
index** (which localises the divergence), and the ELIGIBLE DENOMINATOR named as attempted gameplay
frames, never `--frames`.

**A9:** `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes,
1920x1080, 174,430 frames. `--frames 1200 --no-show --skip-features`.
**A11:** pod SHA-256 for `unified_pipeline.py` and `advanced_tracker.py`; state whether they match the
hashes recorded in the G195 and G198 artifacts.
**B13/Q9:** per-run hash summaries in the artifact. Do NOT paste 1,200 hashes into the memo -- commit
them as a file and quote the comparison.

ACCEPTANCE RULE:
  metric        = identical-or-not per-frame hash sequences across 3 runs in each part; first
                  differing frame index if any; whether any silent decode handler fired
  before        = the route is non-deterministic; RNG, the cuDNN tuner, the prefetch cache and
                  wall-clock branching are all eliminated; whether the route even sees the same pixels
                  twice has never been measured
  bar           = NO pass bar. **"Decode is byte-identical" eliminates the last enumerated candidate
                  and is a FULL SUCCESS.** "Decode differs" identifies the root cause. Both end a long
                  search. Do NOT add seeds, precision changes or any other control -- G190 and G195
                  measured that those do not help, and stacking them destroys attribution.
  n             = 3 runs x 2 parts (EXISTENCE of divergence)
  eye check     = none; this row is about bytes
  must not move = every threshold, `conf`, `imgsz`, the crop, the coordinate contract, every bar and
                  verdict, `src/` (READ ONLY), the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g203_decode_determinism_bisect_2026-09-03.md with both parts, the
first-difference localisation, the silent-handler firing report, code hashes, and a NOT VERIFIED list.
Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest. **If a commit grows an allowlisted file, raise its entry in
`tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12) and run that rail test.**
POD: run there, serially. Never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
