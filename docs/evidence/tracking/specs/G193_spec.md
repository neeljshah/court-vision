GAP G193 | sport wnba | worktree a3 | log g193_route_determinism_with_tuner_off
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: you may READ, IMPORT and
wrap it IN YOUR OWN MEASUREMENT PROCESS, but you must NOT edit any file under it, and you must NOT
copy anything into the pod checkout (B5).

**S1 MACHINE: RUN ON THE POD.** RTX 3090, 24 GB. The local box is 16 GB with other lanes live; two
RAM guards fired there today on this programme.

**S3 DEPENDENCY.** Two landed rows, both ACCEPT:
  - **G189**: the full `run_clip.py` route is non-deterministic. Three fresh runs of one command on
    one file gave **1,246 / 1,360 / 1,247** player rows (n=3 spread 9 pct).
  - **G190**: in the DETECTOR isolated on one frame, `cudnn.benchmark = False` ALONE makes the box
    tensor bit-exact across three fresh processes. Seeds add nothing (tuner-off+seeded was
    byte-identical to tuner-off). FP32 is stable but produces DIFFERENT values, so it changes the
    system under measurement and is NOT to be used.

THE QUESTION: **does turning the cuDNN tuner off make the WHOLE ROUTE deterministic, or does the
stateful tracker still vary?** G190 settled the detector; the tracker is unmeasured. This decides
whether quality measurement is unblocked, so it is the highest-value open row.

THE OBSTACLE, and the sanctioned way around it. `src/pipeline/unified_pipeline.py:657` sets
`torch.backends.cudnn.benchmark = True` inside `UnifiedPipeline.__init__`, so simply setting the flag
False in a preamble is OVERWRITTEN when the pipeline is constructed. You must therefore wrap, not
pre-set. **The sanctioned pattern is the one G182 used: wrap the method IN THE MEASUREMENT PROCESS
ONLY.** For example, import the module, keep a reference to the original `__init__`, and install a
replacement that calls the original and then sets `torch.backends.cudnn.benchmark = False` before
returning. State plainly in the memo that this is a measurement-process wrapper and that no file was
edited or deployed. If you find a cleaner way that also touches nothing, use it and say what it was.

METHOD:
  1. Run the route **3 times, tuner ON** (unmodified, the control) and **3 times, tuner OFF** (your
     wrapper), each into its own `--data-dir`, all six on the pod:

         python3 scripts/run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 \
             --frames 1200 --no-show --skip-features --data-dir <fresh>

  2. For each of the six runs report: player rows, distinct player-row frames, distinct attempted
     gameplay frames (**the ELIGIBLE DENOMINATOR -- name it, never the `--frames` argument**), and
     the survivor tuples at source frames 474 and 1377.
  3. **State whether the three tuner-OFF runs are identical to each other**, on row count AND on the
     two frames' survivor sets. That is the deliverable.

**A9 EXACT SOURCE:** `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`,
2,931,985,407 bytes, 1920x1080, 174,430 frames. NOT the 1280x720 `g130_recensus/` derivative -- two
different videos answer to `wnba_01`.
**A11 CODE IDENTITY:** record the SHA-256 of `unified_pipeline.py` and `advanced_tracker.py` as they
exist on the pod. The pod is not a git checkout and its files have drifted from master before.
**B13/Q9:** store PER-RUN records in the artifact, not just a summary table.

ACCEPTANCE RULE:
  metric        = identical-or-not across 3 tuner-OFF runs, on rows and on the two frames' survivor
                  sets; with the 3 tuner-ON runs as the control in the same table
  before        = the route varies (G189, 9 pct on n=3); the detector alone is fixable (G190); the
                  tracker's contribution is unmeasured
  bar           = NO pass bar. **"Tuner off is NOT sufficient for the route" is a FULL SUCCESS** and
                  is the more informative outcome: it would locate remaining variance in the
                  stateful tracker and tell us the route needs more than a flag. Do NOT add seeds,
                  FP32, or anything else to chase agreement -- G190 measured that seeds add nothing
                  and FP32 changes the values.
  n             = 3 runs per arm, 2 arms (EXISTENCE of variance, not a rate)
  eye check     = none; G189 established single-run renders are not evidence about this system
  must not move = every threshold, `conf`, `imgsz`, the coordinate contract, every bar and verdict,
                  `src/` (READ ONLY), the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g193_route_determinism_with_tuner_off_2026-09-03.md with the
six-run table, per-run records, the identical-or-not verdict, the code hashes, and a NOT VERIFIED
list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness you add under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest.
POD: run your six jobs there, sequentially so they do not contend. Never kill, restart or deploy over
the daemon or keeper; do not wait on the daemon.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
