GAP G198 | sport wnba | worktree a3 | log g198_prefetch_frame_misalignment
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ, IMPORT and wrap it IN
YOUR OWN MEASUREMENT PROCESS only. Edit nothing; deploy nothing into the pod checkout (B5).

**S1 MACHINE: RUN ON THE POD.** RTX 3090. The local box is 16 GB with other lanes live.

**S3 DEPENDENCY.** Three landed rows, all ACCEPT:
  - **G190**: `cudnn.benchmark = False` makes the DETECTOR bit-exact. Torch seeds added nothing.
  - **G193**: tuner-off is NOT sufficient for the whole route.
  - **G195**: seeding OpenCV's global RNG is ALSO not sufficient. Arm D (tuner off + `cv2.setRNGSeed`)
    gave 1,118 / 1,108 / 1,072 player rows. **Every RNG hypothesis is now eliminated.**

THE MECHANISM, read out of the code by the orchestrator and quoted so you can falsify it (S2):
  - `src/pipeline/unified_pipeline.py:1673` -- `ok, frame, _fi = _prefetcher.read()` at the TOP of the
    loop. So while frame `k` is being processed, `k` has already left the queue and the queue HEAD is
    `k+1`.
  - `src/pipeline/unified_pipeline.py:1899-1903` -- later in that SAME iteration, and only
    `if not self.feet_det._yolo_result_buf`, it calls `_prefetcher.peek(7)` and passes those frames to
    `prefetch_yolo`.
  - `src/pipeline/unified_pipeline.py:301-311` -- `peek` is **NON-BLOCKING**: it snapshots
    `list(self._q.queue)[:n]` under the mutex and returns however many happen to be buffered, 0 to 8.
    **It returns bare frames and DISCARDS `_fi`, the frame index.**
  - `src/tracking/advanced_tracker.py:409-454` -- `prefetch_yolo` runs YOLO on those frames on a
    background thread and `extend`s `self._yolo_result_buf`, a `deque(maxlen=16)`, **with no frame
    identity attached**.
  - `src/tracking/advanced_tracker.py:1194-1200` -- `get_players_pos` joins the thread, then if the
    buffer is non-empty does `yolo_results, _run_pose = self._yolo_result_buf.popleft()` and uses it
    for the CURRENT frame.

**THE HYPOTHESIS, stated so you can falsify it:** the detections applied to frame `k` were computed on
a DIFFERENT frame, normally `k+1`; and WHICH frames are served from cache depends on how many frames
the decode thread had buffered when `peek` fired, which is a thread race. If true this is (1) the
residual non-determinism that survived G190 and G195, and (2) a systematic association error on every
cached frame, independent of determinism.
**If the evidence says otherwise, report that.** "The offset is 0 on every frame" is a FULL SUCCESS
and would kill the hypothesis cleanly. Do not go looking for a way to make it true.

METHOD -- instrument in your own process, then two arms, **3 runs each, fresh process per run**:

  PART 1, INSTRUMENTED CONTROL (3 runs, route unchanged apart from your wrappers):
  Wrap `_FramePrefetcher.peek`, `AdvancedTracker.prefetch_yolo` and `AdvancedTracker.get_players_pos`
  to record per call:
    a. how many frames `peek` actually returned (**the distribution over the whole run, not an
       example**);
    b. the `frame_idx` being processed, and the frame index the served detections came from. `peek`
       throws the index away, so you must recover it yourself -- read `self._q.queue` inside your
       `peek` wrapper BEFORE calling through, and carry those indices alongside the cached results in
       YOUR OWN parallel structure. **Do not modify the production deque.**
    c. per frame, whether it was served from cache or ran its own inference.
  Report: the **distribution of the offset** (served-frame minus processed-frame) over all frames, the
  count of cache-served vs self-inferred frames, and whether those two counts are identical across the
  3 runs. **State the offset distribution as a whole-run histogram (S2), never as a first-rows sample.**

  PART 2, BYPASS ARM (3 runs): in your measurement process only, make `prefetch_yolo` a no-op
  (`lambda *a, **k: None`). The cache is then never populated, `_has_cached` is always False, and every
  frame runs inference **on itself**. Combine with `cudnn.benchmark = False` (G190's established
  setting) and nothing else. **Add no seeds, no FP32, no threshold changes** -- G190 and G195 measured
  that those do not help, and stacking them would destroy the attribution.
  Report the same per-run record as G195 used, and state plainly: **are the 3 runs identical?**

Report per run, both parts: player rows, distinct player-row frames, distinct attempted gameplay
frames (**the ELIGIBLE DENOMINATOR -- name it, never `--frames`**), and survivor tuples at source
frames 474 and 1377, so this is directly comparable to the G195 table.

**A9:** `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes,
1920x1080, 174,430 frames. `--frames 1200 --no-show --skip-features`.
**A11:** record pod SHA-256 for `unified_pipeline.py` and `advanced_tracker.py` and state whether they
match the hashes recorded in the G195 artifact.
**B13/Q9:** per-run and per-frame records in the artifact, not just a summary.

**HONEST LIMITATIONS you must state rather than discover:** the bypass arm removes batching, so it
will be SLOWER; that is expected and is not a finding. Determinism in the bypass arm shows the cache
path is the source, it does NOT by itself prove the +1 offset is the mechanism -- Part 1 is what
measures the offset. And a deterministic bypass arm is **not** evidence that tracking quality
improves; that is a separate row.

ACCEPTANCE RULE:
  metric        = the whole-run offset distribution and cache-served counts (Part 1); identical-or-not
                  across 3 runs (Part 2)
  before        = the route is non-deterministic with the tuner off and OpenCV seeded; every RNG
                  hypothesis is eliminated; the cache path is enumerated but unmeasured
  bar           = NO pass bar. **"The bypass arm is deterministic" identifies the cause and points at
                  a fix. "The bypass arm still varies" eliminates the cache and is equally valuable.**
                  "The offset is always 0" falsifies the misalignment half cleanly. All are full
                  successes. Do NOT stack extra controls to manufacture agreement.
  n             = 3 runs x 2 arms (EXISTENCE of variance, plus a whole-run offset distribution)
  eye check     = none; G189 established single-run renders are not evidence here
  must not move = every threshold, `conf`, `imgsz`, the crop, the coordinate contract, every bar and
                  verdict, `src/` (READ ONLY), the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g198_prefetch_frame_misalignment_2026-09-03.md with the offset
histogram, the per-run tables for both arms, code hashes, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest.
POD: run the six jobs there, sequentially. Never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
